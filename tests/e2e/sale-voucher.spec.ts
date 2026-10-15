// A voucher of Services pays a line at the till and comes back with the refund, in Chrome (SALE-F27,
// F32, F38; SERVICE-F09, F22–F26), with the real Services, Customers and Sales apps: the owner sells a
// haircut from the «Services» chip, pays it with Lucía's voucher in «Lines paid another way» (what is
// left before and after, the line at 0,00 €), charges 0,00 € and the ticket says «Already paid»; a
// voucher applied and then charged to another customer is refused in the sheet (409); taking the line
// off gives the session back; a voucher with no session left offers nothing; a sale paid with a voucher
// gives its session back from «Refund» with no money. Screenshots of the charge sheet in three
// viewports. What this file creates is deleted after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { cleanUp as cleanCustomers, createCard, e2eName } from './customer-helpers';
import { snapshotSeries } from './invoice-helpers';
import { cleanDocumentsOf, shots } from './sale-helpers';
import { cleanUp as cleanServices, named, post } from './service-helpers';

interface Service {
  id: string;
  name: string;
}
interface Grant {
  id: string;
  package_id: string;
  /** The voucher's name in the catalog. */
  name: string;
}

let haircut: Service;
let lucia: { id: string; name: string };
let marta: { id: string; name: string };
/** Lucía's voucher: two haircuts. */
let lucias: Grant;

/** Deletes the checks and sales that sold this file's services (their lines name an `E2E Svc` service). */
const VOUCHER_ORDERS =
  "select distinct order_id as id from sale_orderline where service_id in (select id from service_service where name like 'E2E Svc%')";

function cleanVoucherSales(): void {
  cleanDocumentsOf(VOUCHER_ORDERS);
  psql(
    [
      `create temp table e2e_v_orders as ${VOUCHER_ORDERS}`,
      'create temp table e2e_v_sales as select id from sale_sale where order_id in (select id from e2e_v_orders)',
      'delete from sale_refundline where refund_id in (select id from sale_refund where sale_id in (select id from e2e_v_sales))',
      'delete from sale_refundpayment where refund_id in (select id from sale_refund where sale_id in (select id from e2e_v_sales))',
      'delete from sale_refund where sale_id in (select id from e2e_v_sales)',
      'delete from sale_orderline where order_id in (select id from e2e_v_orders)',
      'delete from sale_salepayment where sale_id in (select id from e2e_v_sales)',
      'delete from sale_saleline where sale_id in (select id from e2e_v_sales)',
      'delete from sale_sale where id in (select id from e2e_v_sales)',
      'delete from customer_orderlink where order_id in (select id from e2e_v_orders)',
      'delete from sale_order where id in (select id from e2e_v_orders)',
    ].join('; '),
  );
}

function cleanAll(): void {
  cleanVoucherSales();
  cleanServices();
  cleanCustomers();
}

test.beforeAll(cleanAll);
test.afterAll(cleanAll);

/** A voucher of `uses` sessions of the haircut, sold to `customer` (as the assistant or the API grant it). */
async function sellVoucher(context: BrowserContext, label: string, uses: number, customer: { id: string }): Promise<Grant> {
  const name = named(label);
  const pkg = await post<{ id: string }>(context, '/service/packages', { name, max_uses: uses, items: [{ service_id: haircut.id }] });
  const grant = await post<{ id: string }>(context, '/service/grants', { package_id: pkg.id, customer_id: customer.id, amount: 9000 });
  return { id: grant.id, package_id: pkg.id, name };
}

/** What is left of a voucher sold, read from Services (server-side evidence). */
async function remainingOf(context: BrowserContext, grant: Grant): Promise<number | null> {
  const page = await api<{ rows: { id: string; remaining: number | null }[] }>(context, A, 'GET', `/service/grants?package_id=${grant.package_id}`);
  return page.data.rows.find((row) => row.id === grant.id)?.remaining ?? null;
}

test.beforeAll(async ({ browser }) => {
  // Card charges issue tickets (F2) when the hub has an issuer: the cleanup gives their numbers back.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  haircut = await post<Service>(context, '/service/services', { name: named('Corte'), price: 2500, tax_category_key: 'service.generic' });
  const ana = await createCard(context, { name: e2eName('Lucía') });
  const other = await createCard(context, { name: e2eName('Marta') });
  lucia = { id: ana.id, name: ana.name };
  marta = { id: other.id, name: other.name };
  lucias = await sellVoucher(context, 'Bono 2 cortes', 2, lucia);
  await context.close();
});

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
}

/** The haircut from the «Services» chip of the strip, as a person finds it. */
async function addHaircut(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-category-services]').click();
  await shown(page).locator(`[data-testid=pos-service-${haircut.id}]`).click();
  await expect(haircutLine(page)).toBeVisible();
}

const haircutLine = (page: Page) => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: haircut.name }).first();

async function chooseCustomer(page: Page, customer: { id: string; name: string }): Promise<void> {
  await shown(page).locator('[data-testid=customer-search-trigger]').click();
  const search = page.locator('[data-testid=customer-search-modal]');
  await search.locator('[data-testid=customer-picker-search] input').fill(customer.name);
  await search.locator(`[data-testid=customer-picker-result-${customer.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-customer-chip]')).toContainText(customer.name);
}

async function openCharge(page: Page) {
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  return sheet;
}

test('SALE-F38, F27: a haircut from «Services» paid with Lucía’s voucher is charged at 0,00 € and the session is spent', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addHaircut(page);
  await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/25[.,]00/);
  await chooseCustomer(page, lucia);

  const sheet = await openCharge(page);
  const section = sheet.locator('[data-testid=voucher-lines]');
  await expect(section.locator('[data-testid=voucher-lines-title]')).toHaveText(/Lines paid another way|Líneas pagadas de otra forma/);
  const option = section.locator(`[data-testid$=-option-${lucias.id}]`);
  await expect(option).toContainText(lucias.name);
  await expect(option).toContainText(/2 sessions left · 1 after this one|Quedan 2 sesiones · 1 después de esta/);
  await expect(option).toHaveAttribute('aria-checked', 'true');
  await shots(page, 'sale-voucher-sheet', async (p) => {
    await p.locator('[data-testid=sale-checkout-modal] [data-testid=voucher-lines]').waitFor({ state: 'visible' });
  }, { width: 1440, height: 900 });

  await section.locator('[data-testid$=-confirm]').click();
  await expect(section.locator('[data-testid$=-held]')).toContainText(/session spent\. 1 left|sesión gastada\. Quedan 1/);
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toContainText(/0[.,]00/);
  await page.screenshot({ path: shot('sale-voucher-held-1440') });
  expect(await remainingOf(context, lucias)).toBe(1);

  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  await expect(receipt.locator('[data-testid=sale-receipt-voucher]')).toContainText(lucias.name);
  await page.screenshot({ path: shot('sale-voucher-ticket-1440') });

  // Server-side: the session is spent and linked to a sale of 0,00 € whose line the voucher paid.
  const moves = await api<{ rows: { kind: string; sale_id: string | null }[] }>(context, A, 'GET', `/service/movements?package_id=${lucias.package_id}`);
  expect(moves.data.rows[0].kind).toBe('consumed');
  const sale = await api<{ total: number; payments: unknown[]; lines: { paid_by_voucher: boolean; voucher_name: string }[] }>(
    context,
    A,
    'GET',
    `/sale/sales/detail?sale_id=${moves.data.rows[0].sale_id}`,
  );
  expect([sale.data.total, sale.data.payments, sale.data.lines.map((line) => [line.paid_by_voucher, line.voucher_name])]).toEqual([0, [], [[true, lucias.name]]]);
  expect(await remainingOf(context, lucias)).toBe(1);
});

test('SALE-F27, SERVICE-F23: charged to another customer it is refused in the sheet; taking the line off gives the session back', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addHaircut(page);
  await chooseCustomer(page, lucia);
  let sheet = await openCharge(page);
  const section = sheet.locator('[data-testid=voucher-lines]');
  await section.locator(`[data-testid$=-option-${lucias.id}]`).waitFor({ state: 'visible' });
  await section.locator('[data-testid$=-confirm]').click();
  await expect(section.locator('[data-testid$=-held]')).toBeVisible();
  const before = await remainingOf(context, lucias);
  await sheet.locator('[data-testid=sale-checkout-close]').click();
  await expect(sheet).toBeHidden();
  await expect(haircutLine(page).locator('[data-testid$=-voucher]')).toContainText(lucias.name);

  // The check now goes to Marta: the voucher is Lucía's, so nothing is charged and the sheet says why.
  await chooseCustomer(page, marta);
  sheet = await openCharge(page);
  await expect(sheet.locator('[data-testid=voucher-lines] [data-testid$=-held]')).toBeVisible();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet.locator('[data-testid=sale-checkout-error]')).toContainText(/belongs to another customer|es de otro cliente/);
  await page.screenshot({ path: shot('sale-voucher-refused-1280') });
  await sheet.locator('[data-testid=sale-checkout-close]').click();
  await expect(sheet).toBeHidden();

  // Taking the line off releases the session at once.
  await haircutLine(page).locator('[data-testid$=-remove]').click();
  await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: haircut.name })).toHaveCount(0);
  await expect.poll(() => remainingOf(context, lucias)).toBe((before ?? 0) + 1);
});

test('SERVICE-F22: a voucher with no session left offers nothing', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/pos');
  const spent = await sellVoucher(context, 'Bono 1 corte', 1, marta);
  await post(context, '/service/grants/redeem', { id: spent.id, service_id: haircut.id }, 200);
  await page.reload();
  await tillReady(page);
  await addHaircut(page);
  await chooseCustomer(page, marta);
  const sheet = await openCharge(page);
  await expect(sheet.locator('[data-testid=voucher-lines] [data-testid$=-none]')).toHaveText(
    /This customer has no voucher that covers this service\.|Este cliente no tiene ningún bono que cubra este servicio\./,
  );
  await sheet.locator('[data-testid=sale-checkout-close]').click();
  await haircutLine(page).locator('[data-testid=pos-qty-minus]').click();
});

test('SALE-F32, SERVICE-F26: a sale paid with a voucher gives its session back from «Refund», with no money', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/sales');
  // A sale paid whole with Lucía's voucher, charged through the API (the till's own charge is above).
  const opened = await post<{ id: string; lines: { id: string }[] }>(context, '/sale/orders', { service_lines: [{ service_id: haircut.id }] });
  await post(context, '/sale/orders/apply_voucher', { order_id: opened.id, line_id: opened.lines[0].id, grant_id: lucias.id }, 200);
  const sale = await post<{ id: string; number: string; total: number; lines: { id: string }[] }>(context, '/sale/sales', {
    idempotency_key: `e2e-voucher-${Date.now().toString(36)}`,
    order_id: opened.id,
    customer_id: lucia.id,
  });
  expect(sale.total).toBe(0);
  const before = await remainingOf(context, lucias);

  await page.reload();
  await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
  const row = shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);
  await expect(row).toBeVisible();
  await shown(page).locator(`[data-testid=sales-table-row-${sale.id}-refund]`).first().click();
  const modal = page.locator('ion-modal[data-testid=sale-refund]');
  await expect(modal).toBeVisible();
  const line = sale.lines[0].id;
  await expect(modal.locator(`[data-testid=refund-line-amount-${line}]`)).toContainText(lucias.name);
  await modal.locator(`[data-testid=refund-line-check-${line}]`).click();
  await expect(modal.locator(`[data-testid=refund-line-session-${line}]`)).toContainText(lucias.name);
  await modal.locator('[data-testid=refund-reason] textarea, [data-testid=refund-reason] input').first().fill('e2e did not come');
  await expect(modal.locator('[data-testid=refund-confirm]')).toHaveText(/Give the session back|Devolver la sesión/);
  await page.screenshot({ path: shot('sale-voucher-refund-1280') });
  await modal.locator('[data-testid=refund-confirm]').click();
  await expect(modal).toBeHidden();
  await expect.poll(() => remainingOf(context, lucias)).toBe((before ?? 0) + 1);
  await expect
    .poll(async () => (await api<{ status: string }>(context, A, 'GET', `/sale/sales/detail?sale_id=${sale.id}`)).data.status)
    .toBe('refunded');
});
