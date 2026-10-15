// Sales & POS history in Chrome (SALE-F28, F29, F30, F31; apps/sale/WORKBOOK.md): sales charged with a
// real Inventory product at its real VAT (Taxes' 21 % for Spain) are listed, searched by number and
// filtered by status; the document shows the ticket with its VAT row and total; the owner voids one with
// its reason and refunds another in full, and the server says so. Screenshots of the list and the
// document in the three viewports. What this file creates is deleted after it (`afterAll`).
import { expect, type Page, test } from '@playwright/test';

import { A, login, shown } from './helpers';
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

  // Filtered by status «Voided», the voided sale is there and the cash one is not.
  await search(page, '');
  await shown(page).locator('[data-testid=sales-filters]').click();
  await pick(page, page.locator('[data-testid=sales-filter-status]'), /^(Voided|Anulada)$/);
  await page.locator('[data-testid=sales-filters-done]').click();
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
