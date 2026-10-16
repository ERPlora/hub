// Sales & POS history in Chrome (SALE-F28, F29, F30, F31; apps/sale/WORKBOOK.md): sales charged with a
// real Inventory product at its real VAT (Taxes' 21 % for Spain) are listed, searched by number and
// filtered by status; the document shows the ticket with its VAT row and total; the owner voids one with
// its reason and refunds another in full, and the server says so. Screenshots of the list and the
// document in the three viewports. The list filters behind the table's funnel (total in euros, payment
// searched on the server), with its count, at every width; a «to» day before its «from» is said under it.
// What this file creates is deleted after it (`afterAll`).
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, shot, shown } from './helpers';
import { cleanInventory, createProduct, pick } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, type SaleOut, shots, stamp } from './sale-helpers';

const SKU = `E2E-SAL-${stamp()}`;
let cash: SaleOut;
let card: SaleOut;
let toVoid: SaleOut;

test.afterAll(() => {
  cleanSales();
  cleanInventory();
  restoreDrawer();
});

const row = (page: Page, sale: SaleOut) => shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);

async function tableReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
}

async function search(page: Page, text: string): Promise<void> {
  await shown(page).locator('[data-testid=sales-table-search] input').fill(text);
}

/** The table's funnel and its panel. */
const funnel = (page: Page) => ({
  toggle: shown(page).locator('[data-testid=sales-table-filters-toggle]'),
  panel: shown(page).locator('[data-testid=sales-table-filters-panel]'),
  count: shown(page).locator('[data-testid=sales-table-filters-count]'),
});

/** The widths of the filter panel's screenshots: a phone (the panel is a sheet), a tablet and a desk
 *  (two columns), as the SaaS panel's `VIEWPORTS`. */
const FILTER_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

test.beforeAll(async ({ browser }) => {
  // Card charges issue tickets (F2) when the hub has an issuer: the cleanup gives their numbers back.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  await createProduct(context, { name: 'E2E Shirt', sku: SKU, price: 1210, tax_category_key: 'product.generic' });
  cash = await chargeByApi(context, { lines: [{ product: SKU, quantity: '2' }], payments: [{ method: 'cash', tendered: 5000 }] });
  card = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  toVoid = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  await context.close();
});

test('SALE-F28 and F29: the history lists the sales, finds one by number and shows its ticket with the VAT', async ({ page }) => {
  // The server priced it with tax's rule: 2 × 12.10 € VAT included = 20.00 € + 4.20 € at 21 %.
  expect((({ total, subtotal, tax_total, change_total }) => ({ total, subtotal, tax_total, change_total }))(cash)).toEqual({
    total: 2420,
    subtotal: 2000,
    tax_total: 420,
    change_total: 2580,
  });
  expect(cash.lines[0].tax_rate).toBe('21.00');

  await login(page, A, '/sale/sales');
  await tableReady(page);
  await expect(shown(page).locator('[data-testid=sales-kpis]')).toBeVisible();
  await expect(row(page, cash)).toBeVisible();

  await search(page, cash.number);
  await expect.poll(() => shown(page).locator('[data-testid=sales-table-row]').count()).toBe(1);
  await expect(row(page, cash)).toContainText(cash.number);
  await shots(page, 'sale-sales-list', tableReady);

  await shown(page).locator(`[data-testid=sales-table-row-${cash.id}-document]`).first().click();
  const document = page.locator('[data-testid=sale-document-modal]');
  const receipt = document.locator('[data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  await expect(receipt.locator('[data-testid=sale-receipt-number]')).toContainText(cash.number);
  await expect(receipt).toContainText(/21\s?%/);
  await expect(receipt).toContainText(/24[.,]20/);
  await expect(receipt.locator('[data-testid=sale-receipt-duplicate]')).toBeVisible();
  await shots(page, 'sale-document', async (p) => {
    await p.locator('[data-testid=sale-receipt]').waitFor({ state: 'visible' });
  });
  await document.locator('[data-testid=sale-document-close]').click();
  await expect(receipt).toBeHidden();
});

test('SALE-F30: the owner voids a sale with its reason', async ({ page, context }) => {
  await login(page, A, '/sale/sales');
  await tableReady(page);
  await search(page, toVoid.number);
  await expect(row(page, toVoid)).toBeVisible();
  await shown(page).locator(`[data-testid=sales-table-row-${toVoid.id}-void]`).first().click();
  const modal = page.locator('ion-modal[data-testid=sale-void]');
  await expect(modal).toBeVisible();
  await expect(modal.locator('[data-testid=sale-void-explain]')).toBeVisible();
  await modal.locator('[data-testid=sale-void-reason] textarea').fill('e2e wrong ticket');
  await modal.locator('[data-testid=sale-void-submit]').click();
  await expect(modal).toBeHidden();
  await expect(row(page, toVoid)).toContainText(/Voided|Anulada/);
  const stored = await context.request.get(`${A}/api/sale/sales/detail?sale_id=${toVoid.id}`);
  expect((await stored.json()).void_reason).toBe('e2e wrong ticket');

  // Filtered by status «Voided» behind the funnel, the voided sale is there and the cash one is not.
  await search(page, '');
  const { toggle, panel } = funnel(page);
  await toggle.click();
  await pick(page, panel.locator('[data-testid=sales-table-filter-status]'), /^(Voided|Anulada)$/);
  await panel.locator('[data-testid=sales-table-filters-apply]').click();
  await expect(row(page, toVoid)).toBeVisible();
  await expect(row(page, cash)).toHaveCount(0);
});

test('SALE-F31: the owner refunds a sale in full by its card', async ({ page, context }) => {
  await login(page, A, '/sale/sales');
  await tableReady(page);
  await search(page, card.number);
  await expect(row(page, card)).toBeVisible();
  await shown(page).locator(`[data-testid=sales-table-row-${card.id}-refund]`).first().click();
  const modal = page.locator('ion-modal[data-testid=sale-refund]');
  await expect(modal).toBeVisible();
  await expect(modal.locator(`[data-testid=refund-tender-${card.payments[0].id}]`)).toBeVisible();
  await modal.locator('[data-testid=refund-propose-all]').click();
  await modal.locator('[data-testid=refund-reason] textarea, [data-testid=refund-reason] input').first().fill('e2e returned');
  await modal.locator('[data-testid=refund-confirm]').click();
  await expect(modal).toBeHidden();
  await expect
    .poll(async () => (await (await context.request.get(`${A}/api/sale/sales/detail?sale_id=${card.id}`)).json()).status)
    .toBe('refunded');
  await expect(row(page, card)).toContainText(/Refunded|Devuelta/);
});

// flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
test('FIX-DATATABLE-HUB-FILTERS-2A: Sales filter by total in euros and by payment behind the funnel, with its count; a «to» day before its «from» is said under it', async ({ page, context }) => {
  await login(page, A, '/sale/sales');
  const { toggle, panel, count } = funnel(page);
  for (const vp of FILTER_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/sale/sales`);
    await tableReady(page);
    await expect(row(page, cash)).toBeVisible();
    await expect(row(page, card)).toBeVisible();
    await toggle.click();
    await expect(panel).toBeVisible();
    // «Total from 20» is twenty euros (sales#428): the 24,20 € sale stays, the 12,10 € one goes.
    await panel.locator('[data-testid=sales-table-filter-total_min] input').fill('20');
    await panel.locator('[data-testid=sales-table-filters-apply]').click();
    await expect(panel).toBeHidden();
    await expect(count).toHaveText('1');
    await expect(row(page, cash)).toBeVisible();
    await expect(row(page, card)).toHaveCount(0);
    // The period and the figures stay outside the table, as in the old screen.
    await expect(shown(page).locator('[data-testid=sales-range]')).toBeVisible();
    await toggle.click();
    await expect(panel).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-FILTERS-2A-sale-${vp.label}`) });
    await panel.locator('[data-testid=sales-table-filters-clear]').click();
    await expect(count).toHaveCount(0);
    await panel.locator('[data-testid=sales-table-filters-close]').click();
    await expect(panel).toBeHidden();
    await expect(row(page, card)).toBeVisible();
  }

  // «Payment»: the business's methods from the server, as the reader reads them; picked, only its sales.
  const methods = await api<{ rows: { type: string; name: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  const cardName = methods.data.rows.find((method) => method.type === 'card')!.name;
  await toggle.click();
  const payment = panel.locator('[data-testid=sales-table-filter-payment_method_name]');
  await payment.locator('[data-testid=sales-table-filter-payment_method_name-search]').click();
  await payment.locator(`[data-testid=sales-table-filter-payment_method_name-option][data-value="${cardName}"]`).click();
  await panel.locator('[data-testid=sales-table-filters-apply]').click();
  await expect(count).toHaveText('1');
  await expect(row(page, card)).toBeVisible();
  await expect(row(page, cash)).toHaveCount(0);
  await toggle.click();
  await panel.locator('[data-testid=sales-table-filters-clear]').click();

  // From the 14th to the 1st: said under «to», the funnel turns red, nothing is filtered and the period rules.
  await panel.locator('[data-testid=sales-table-filter-date_from] input').fill('2026-10-14');
  await panel.locator('[data-testid=sales-table-filter-date_to] input').fill('2026-10-01');
  await panel.locator('[data-testid=sales-table-filters-apply]').click();
  await expect(toggle).toHaveAttribute('data-invalid', 'true');
  await expect(row(page, cash)).toBeVisible();
  await expect(row(page, card)).toBeVisible();
  await toggle.click();
  const to = panel.locator('[data-testid=sales-table-filter-date_to]');
  await expect(to).toHaveClass(/ion-invalid/);
  await expect(to.locator('.error-text')).toHaveText(/The end date cannot be before the start date\.|La fecha final no puede ser anterior a la inicial\./);
  await page.screenshot({ path: shot('FIX-DATATABLE-HUB-FILTERS-2A-sale-error-1440') });
});
