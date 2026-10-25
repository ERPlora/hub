// flow: business-currency (FIX-HUB-APPS-CHARGE-IN-EUR-WHATEVER-THE-COUNTRY; apps/cash_register, apps/invoice and
// apps/inventory WORKBOOK.md)
// The money of Cash register, Invoicing and Inventory is the business's: its country's currency, as erplora.com
// registered it (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to
// Poland: the drawer (the sessions, the count by the zloty's notes and coins and the close), the invoices (list and
// detail) and the products (list and the form's «Cost (PLN)») are in złoty, in 390, 834 and 1440. Back in Spain they
// are in euros, and the invoice issued in Poland keeps its złoty. Each width leaves its captures
// `FIX-HUB-APPS-CHARGE-IN-EUR-WHATEVER-THE-COUNTRY-<width>` (Cash register), `…-invoice-<width>`, `…-inventory-<width>`
// and, back in Spain, `…-es-1440`. What the run creates is deleted after it and `a`'s registration put back.
import { createHmac } from 'node:crypto';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown, untilStill } from './helpers';
import { createProduct, dialog, productsReady } from './inventory-helpers';
import { cleanInvoices, ensureIssuer, issuedIds, issuerNow, type IssuerOut, restoreIssuer, snapshotSeries } from './invoice-helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-APPS-CHARGE-IN-EUR-WHATEVER-THE-COUNTRY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
const RUN = Date.now().toString(36).toUpperCase();
const SKU = `E2E-CUR-${RUN}`;
const CUSTOMER = `e2e Talleres ${RUN}`;

interface Registration {
  id: string;
  slug: string;
  name: string;
  country: string;
  timezone: string;
  language: string;
  vertical: string | null;
}

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let issuer: IssuerOut;
/** The session this run opened (the only one its cleanup deletes). */
let sessionId = '';

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
async function issueInvoice(context: BrowserContext): Promise<{ id: string; number: string; currency: string }> {
  const created = await api<{ id: string; number: string; currency: string }>(context, A, 'POST', '/invoice/invoices', {
    customer_name: CUSTOMER,
    customer_tax_id: 'B12345674',
    customer_address: 'Calle Luna 3, 28004 Madrid',
    lines: [{ description: 'Haircut course', quantity: '2', unit_price: 5000, tax_rate: '21' }],
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  issuedIds.add(created.data.id);
  return created.data;
}

/** The visible copy of `testid` (Ionic keeps each page of the stack mounted). */
const visible = (page: Page, testid: string): Locator => page.locator(`[data-testid="${testid}"]:visible`).first();

async function sessionsReady(page: Page): Promise<void> {
  await shown(page).locator(`[data-testid=cash-register-sessions-row][data-id="${sessionId}"]`).first().waitFor({ state: 'visible' });
}

test.beforeAll(async ({ browser }) => {
  const [id, slug, name, country, timezone, language, vertical] = psql(
    `select id, slug, name, country, timezone, language, coalesce(vertical, '') from base_hub where slug = 'a'`,
  ).split('|');
  original = { id, slug, name, country, timezone, language, vertical: vertical || null };
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/cash_register/sessions');
  issuer = await issuerNow(context);
  await ensureIssuer(context);
  // One drawer open per business: a shift an earlier run left open is closed, at its expected.
  const current = await api<{ session: { id: string; expected_balance: number | null } | null }>(context, A, 'GET', '/cash_register/sessions/current');
  if (current.data.session) {
    const closed = await api(context, A, 'POST', '/cash_register/sessions/close', {
      session_id: current.data.session.id,
      closing_balance: Math.max(current.data.session.expected_balance ?? 0, 0),
      closing_notes: 'e2e: left open by an earlier run',
    });
    expect(closed.status).toBe(200);
  }
  await createProduct(context, { name: `E2E Gambas ${RUN}`, sku: SKU, price: 1250, cost: 820 });
  const opened = await api<{ id: string }>(context, A, 'POST', '/cash_register/sessions/open', { opening_balance: 10000 });
  expect(opened.status, JSON.stringify(opened.data)).toBe(201);
  sessionId = opened.data.id;
  await context.close();
});

test.afterAll(async ({ browser }) => {
  if (original) await registerIn(original.country);
  if (sessionId) {
    psql(`delete from cash_register_count where session_id = '${sessionId}'`);
    psql(`delete from cash_register_movement where session_id = '${sessionId}'`);
    psql(`delete from cash_register_session where id = '${sessionId}'`);
  }
  psql(`delete from inventory_stockmovement where product_id in (select id from inventory_product where sku = '${SKU}')`);
  psql(`delete from inventory_product where sku = '${SKU}'`);
  if (issuer) {
    const context = await browser.newContext({ baseURL: A });
    await login(await context.newPage(), A, '/invoice/invoices');
    await restoreIssuer(context, issuer);
    await context.close();
  }
  cleanInvoices();
});

test(`${KEY}: a business in Poland counts, invoices and prices in złoty in 390, 834 and 1440 (flow business-currency)`, async ({ page, context }) => {
  await registerIn('PL');
  await login(page, A, '/cash_register/sessions');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  const invoice = await issueInvoice(context);
  expect(invoice.currency).toBe('PLN');

  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });

    // Cash register: the open session's float and expected cash, its count by the zloty's notes and coins, its close.
    await page.goto(`${A}/cash_register/sessions`);
    await sessionsReady(page);
    const row = shown(page).locator(`[data-testid=cash-register-sessions-row][data-id="${sessionId}"]`).first();
    await expect(row).toContainText('zł');
    await expect(row).not.toContainText('€');
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`), fullPage: true });

    await visible(page, `cash-register-sessions-row-${sessionId}-count`).click();
    const count = dialog(page, 'cash-register-count');
    await expect(count).toBeVisible();
    // 5 zł is a coin of the zloty (a note of the euro); the 500 zł note leads.
    await expect(count.locator('[data-testid="cash-register-count-denom-500"]')).toBeVisible();
    await expect(count.locator('[data-testid="cash-register-count-denom-0.01"]')).toBeVisible();
    await expect(count).toContainText('zł');
    await expect(count).not.toContainText('€');
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-count-${size.name}`) });
    await page.keyboard.press('Escape');
    await expect(count).toBeHidden();

    await visible(page, `cash-register-sessions-row-${sessionId}-close`).click();
    const close = dialog(page, 'cash-register-close');
    await expect(close).toBeVisible();
    await expect(close.locator('[data-testid=cash-register-close-expected]')).toContainText(/zł\s?100[.,]00|100[.,]00\s?zł/);
    await expect(close).not.toContainText('€');
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-close-${size.name}`) });
    await close.locator('[data-testid=cash-register-close-cancel]').click();
    await expect(close).toBeHidden();

    // Invoicing: the list's total and the detail's totals in złoty.
    await page.goto(`${A}/invoice/invoices`);
    const listed = shown(page).locator('[data-testid=invoice-list-row]', { hasText: invoice.number }).first();
    await expect(listed).toContainText(/zł\s?121[.,]00|121[.,]00\s?zł/);
    await page.goto(`${A}/invoice/invoices/${invoice.id}`);
    const total = shown(page).locator('[data-testid=invoice-detail-total]');
    await expect(total).toContainText(/zł\s?121[.,]00|121[.,]00\s?zł/);
    await expect(shown(page).locator('[data-testid=invoice-detail-base]')).toContainText('zł');
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-invoice-${size.name}`), fullPage: true });

    // Inventory: the product's price in the list and the form's «Cost (PLN)» with its cost.
    await page.goto(`${A}/inventory/products`);
    await productsReady(page);
    const product = shown(page).locator('[data-testid=inventory-products-row]', { hasText: SKU }).first();
    await expect(product).toContainText(/zł\s?12[.,]50|12[.,]50\s?zł/);
    await expect(product).not.toContainText('€');
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-inventory-${size.name}`), fullPage: true });
    await shown(page).locator('[data-testid=inventory-products-add]').click();
    const form = dialog(page, 'inventory-product-form');
    await expect(form).toBeVisible();
    await expect(form.locator('[data-testid=inventory-product-cost]')).toHaveJSProperty('label', 'Cost (PLN)');
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-inventory-form-${size.name}`) });
    await page.keyboard.press('Escape');
    await expect(form).toBeHidden();
  }
});

test(`${KEY}: back in Spain the same screens are in euros, and the invoice issued in Poland keeps its złoty (flow business-currency)`, async ({ page, context }) => {
  await registerIn('ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/cash_register/sessions');
  await sessionsReady(page);
  const row = shown(page).locator(`[data-testid=cash-register-sessions-row][data-id="${sessionId}"]`).first();
  await expect(row).toContainText(/€\s?100[.,]00|100[.,]00\s?€/);
  await untilStill(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`), fullPage: true });

  const euros = await issueInvoice(context);
  expect(euros.currency).toBe('EUR');
  await page.goto(`${A}/invoice/invoices/${euros.id}`);
  await expect(shown(page).locator('[data-testid=invoice-detail-total]')).toContainText(/€\s?121[.,]00|121[.,]00\s?€/);
  // What was issued in Poland is not rewritten: it keeps the złoty it was issued in.
  const polish = [...issuedIds].find((id) => id !== euros.id);
  await page.goto(`${A}/invoice/invoices/${polish}`);
  await expect(shown(page).locator('[data-testid=invoice-detail-total]')).toContainText('zł');

  await page.goto(`${A}/inventory/products`);
  await productsReady(page);
  await expect(shown(page).locator('[data-testid=inventory-products-row]', { hasText: SKU }).first()).toContainText(/€\s?12[.,]50|12[.,]50\s?€/);
  await shown(page).locator('[data-testid=inventory-products-add]').click();
  const form = dialog(page, 'inventory-product-form');
  await expect(form.locator('[data-testid=inventory-product-cost]')).toHaveJSProperty('label', 'Cost (EUR)');
});
