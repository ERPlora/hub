// A sale paid partly in cash and partly by card in the Sales history (SALE-F28, SALE-F03; apps/sale/WORKBOOK.md):
// its row says both methods under «Payment», in the order they were charged, at every width and in Spanish too, and
// picking «Cash» in the table's payment filter finds it while a card-only sale goes. Setup through the APIs; the checks
// in the browser (hidden). What this file creates is deleted after it (`afterAll`).
import { expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, type SaleOut, stamp } from './sale-helpers';

const SKU = `E2E-SPLIT-${stamp()}`;
/** The three widths the screen is checked at: desk, tablet and a small phone (cards). */
const SIZES = [
  { label: '1440', width: 1440, height: 900 },
  { label: '820', width: 820, height: 1180 },
  { label: '375', width: 375, height: 667 },
];
/** Both methods of the split sale, as an English or a Spanish reader reads them. */
const BOTH = /Cash \+ Card|Efectivo \+ Tarjeta/;
let split: SaleOut;
let cardOnly: SaleOut;

test.beforeAll(async ({ browser }) => {
  // Card charges issue tickets (F2) when the hub has an issuer: the cleanup gives their numbers back.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  await createProduct(context, { name: 'E2E Menu', sku: SKU, price: 500, tax_category_key: 'restaurant.food' });
  split = await chargeByApi(context, {
    lines: [{ product: SKU }],
    payments: [
      { method: 'cash', amount: 200, tendered: 200 },
      { method: 'card', amount: 300 },
    ],
  });
  cardOnly = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  await context.close();
});

test.afterAll(() => {
  cleanSales();
  cleanInventory();
  restoreDrawer();
});

const row = (page: Page, sale: SaleOut) => shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);

async function tableReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
}

test('SALE-F28 and F03: a sale paid in cash and by card says both under «Payment», and filtering by cash finds it', async ({ page, context }) => {
  await login(page, A, '/sale/sales');
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto(`${A}/sale/sales`);
    await tableReady(page);
    await expect(row(page, split)).toContainText(BOTH);
    await expect(row(page, cardOnly)).not.toContainText(BOTH);
    await row(page, split).scrollIntoViewIfNeeded();
    await capture(page, `SALE-F28-split-payment-row-${size.label}`);
  }

  const methods = await api<{ rows: { type: string; name: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  const cashName = methods.data.rows.find((method) => method.type === 'cash')!.name;
  const toggle = shown(page).locator('[data-testid=sales-table-filters-toggle]');
  const panel = shown(page).locator('[data-testid=sales-table-filters-panel]');
  await toggle.click();
  const payment = panel.locator('[data-testid=sales-table-filter-payment_method_name]');
  await payment.locator('[data-testid=sales-table-filter-payment_method_name-search]').click();
  await payment.locator(`[data-testid=sales-table-filter-payment_method_name-option][data-value="${cashName}"]`).click();
  await panel.locator('[data-testid=sales-table-filters-apply]').click();
  await expect(row(page, cardOnly)).toHaveCount(0);
  await expect(row(page, split)).toContainText(BOTH);
});

test('SALE-F28: in Spanish the split sale reads «Efectivo + Tarjeta»', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, '/sale/sales');
  await tableReady(page);
  await expect(row(page, split)).toContainText('Efectivo + Tarjeta');
  await saveSessionForTheSweep(context);
  await context.close();
});
