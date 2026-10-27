// flow: VERIFACTU-F01 (with VERIFACTU-F13, F17 and F19; FIX-HUB-VERIFACTU-ON-FOR-A-BUSINESS-OUTSIDE-SPAIN)
// VeriFactu is only for businesses in Spain. erplora.com registers `a`'s business in Poland (`PUT /internal/hubs/{id}`,
// signed the way the SaaS sends it): with VeriFactu on, an invoice is issued without a record («unavailable») and its
// detail shows no «VeriFactu receipt»; a ticket sealed while the business was in Spain stays unsent, its invoice shows
// no receipt either, and its record says why it does not leave (never «it goes out by itself», nothing to send);
// VeriFactu › Settings says why it cannot go live. In
// 390, 834 and 1440, with the captures `<KEY>-<width>` (the invoice), `<KEY>-record-<width>` and
// `<KEY>-settings-<width>`. Back in Spain an invoice is sealed and shows its receipt (`<KEY>-es-1440`). What the run
// creates is deleted after it and `a`'s registration put back. Nothing is sent: no local server has the gateway.
import { createHmac } from 'node:crypto';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown, untilStill } from './helpers';
import { cleanInvoices, ensureIssuer, issuedIds, issuerNow, type IssuerOut, restoreIssuer, snapshotSeries } from './invoice-helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-VERIFACTU-ON-FOR-A-BUSINESS-OUTSIDE-SPAIN';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
const RUN = Date.now().toString(36).toUpperCase();
const CUSTOMER = `e2e Kowalski ${RUN}`;
/** What VeriFactu says of a business outside Spain (the record's wait and what keeps it from going live). */
const NOT_IN_SPAIN = 'this business is not in Spain: VeriFactu is only for businesses in Spain, so nothing is sent to the AEAT';

interface Registration {
  id: string;
  slug: string;
  name: string;
  country: string;
  timezone: string;
  language: string;
  vertical: string | null;
}

interface Issued {
  id: string;
  number: string;
  verifactu_status: string | null;
}

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let issuer: IssuerOut;

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

/** erplora.com registers `a`'s business in `country`, the way the SaaS does (`PUT /internal/hubs/{id}`, signed). */
async function registerIn(country: string): Promise<void> {
  const body = JSON.stringify({ ...original, country });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', SECRET).update(`${timestamp}.${body}`).digest('hex');
  const response = await fetch(`http://127.0.0.1:${STACK.hubPort}/internal/hubs/${original.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(psql(`select country from base_hub where slug = 'a'`)).toBe(country);
}

/** A manual invoice of the run, issued through Invoicing's API (setup; the check is the screen's). */
async function issueInvoice(context: BrowserContext): Promise<Issued> {
  const created = await api<Issued>(context, A, 'POST', '/invoice/invoices', {
    customer_name: CUSTOMER,
    customer_tax_id: 'B12345674',
    customer_address: 'Calle Luna 3, 28004 Madrid',
    lines: [{ description: 'Haircut course', quantity: '2', unit_price: 5000, tax_rate: '21' }],
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  issuedIds.add(created.data.id);
  return created.data;
}

/** The record VeriFactu sealed for `invoiceId`, read from the database (setup: the screen reads it by the API). */
function recordOf(invoiceId: string): string {
  return psql(`select id from verifactu_record where invoice_id = '${invoiceId}'`);
}

/** The open invoice's detail, once its totals are painted (Ionic keeps each page of the stack mounted). */
async function invoiceDetail(page: Page, id: string): Promise<Locator> {
  await page.goto(`${A}/invoice/invoices/${id}`);
  await expect(shown(page).locator('[data-testid=invoice-detail-total]')).toBeVisible();
  return shown(page);
}

test.beforeAll(async ({ browser }) => {
  const [id, slug, name, country, timezone, language, vertical] = psql(
    `select id, slug, name, country, timezone, language, coalesce(vertical, '') from base_hub where slug = 'a'`,
  ).split('|');
  original = { id, slug, name, country, timezone, language, vertical: vertical || null };
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/invoice/invoices');
  issuer = await issuerNow(context);
  await ensureIssuer(context);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  if (original) await registerIn(original.country);
  if (issuer) {
    const context = await browser.newContext({ baseURL: A });
    await login(await context.newPage(), A, '/invoice/invoices');
    await restoreIssuer(context, issuer);
    await context.close();
  }
  cleanInvoices();
});

test(`${KEY}: VERIFACTU-F01 a business in Poland issues its invoices without a VeriFactu record or receipt, in 390, 834 and 1440`, async ({ page, context }) => {
  // A ticket sealed while the business was in Spain: its record waits («Pendiente»).
  await registerIn('ES');
  await login(page, A, '/invoice/invoices');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  const before = await issueInvoice(context);
  expect(before.verifactu_status).toBe('sealed');
  const waiting = recordOf(before.id);
  expect(waiting).not.toBe('');

  await registerIn('PL');
  const invoice = await issueInvoice(context);
  expect(invoice.verifactu_status).toBe('unavailable');
  expect(recordOf(invoice.id)).toBe('');

  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });

    // The invoice issued in Poland: no «VeriFactu receipt»; nor the one sealed before, which is never sent.
    const detail = await invoiceDetail(page, invoice.id);
    await expect(detail.locator('[data-testid=invoice-detail-total]')).toContainText('zł');
    await expect(detail.locator('[data-testid=invoice-verifactu]')).toHaveCount(0);
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`), fullPage: true });
    const earlier = await invoiceDetail(page, before.id);
    await expect(earlier.locator('[data-testid=invoice-verifactu]')).toHaveCount(0);

    // Its record says why it does not leave.
    await page.goto(`${A}/verifactu/records/${waiting}`);
    const why = shown(page).locator('[data-testid=verifactu-record-waiting]');
    await expect(why).toContainText(NOT_IN_SPAIN);
    // It never goes out: no «it goes out by itself», and nothing to send.
    await expect(why).not.toContainText('It goes out by itself');
    await expect(shown(page).locator('[data-testid=verifactu-record-transmit]')).toHaveCount(0);
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-record-${size.name}`), fullPage: true });

    // VeriFactu › Settings: it cannot go live, and says why.
    await page.goto(`${A}/verifactu/settings`);
    const blockers = shown(page).locator('[data-testid=verifactu-settings-live-blockers]');
    await expect(blockers).toContainText(NOT_IN_SPAIN);
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-settings-${size.name}`), fullPage: true });
  }
});

test(`${KEY}: VERIFACTU-F13 back in Spain an invoice is sealed and shows its VeriFactu receipt`, async ({ page, context }) => {
  await registerIn('ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/invoices');
  const invoice = await issueInvoice(context);
  expect(invoice.verifactu_status).toBe('sealed');
  const detail = await invoiceDetail(page, invoice.id);
  const receipt = detail.locator('[data-testid=invoice-verifactu]');
  await expect(receipt).toBeVisible();
  await expect(receipt.locator('[data-testid=invoice-verifactu-status]')).toContainText('Pending');
  await page.goto(`${A}/verifactu/settings`);
  await expect(shown(page).locator('[data-testid=verifactu-settings-environment]')).toBeVisible();
  await expect(shown(page).locator('[data-testid=verifactu-settings-live-blockers]')).not.toContainText(NOT_IN_SPAIN);
  await page.goto(`${A}/invoice/invoices/${invoice.id}`);
  await expect(shown(page).locator('[data-testid=invoice-verifactu]')).toBeVisible();
  await untilStill(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`), fullPage: true });
});
