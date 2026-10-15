// The fiscal chain in Chrome (SALE-F04, F29, F30, F31; INVOICE-F01, F02, F07, F09; apps/sale/WORKBOOK.md):
// Invoicing numbers a sale's document IN the charge itself. The owner charges as an invoice to a company
// whose tax ID checks and the ticket that opens says «Invoice FACT-…», the number Invoicing gave it (never
// the sale's own); a tax ID that does not check is said under its box and nothing is charged; a ticket
// charged and voided from Sales gets its rectifying invoice (R5) in the same void; a refund, its own.
// Setup and evidence through the APIs (the issuer, the products); the checks in the browser. Everything
// it creates is deleted after it, and the series give their numbers back.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, shot, shown } from './helpers';
import { ensureIssuer, snapshotSeries } from './invoice-helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { chargeByApi, cleanSales, newestSaleOf, stamp } from './sale-helpers';

const RUN = stamp();
const YEAR = new Date().getFullYear();
let tapa: Product;
let cane: Product;
let methods: Record<string, string>;

interface FiscalSale {
  id: string;
  number: string;
  total: number;
  invoice_status: string;
  invoice_type: string;
  invoice_number: string;
  void_invoice_status: string;
  void_invoice_number: string;
}

test.beforeAll(async ({ browser }) => {
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await ensureIssuer(context);
  tapa = await createProduct(context, { name: `E2E Tapa ${RUN}`, sku: `E2E-CHAIN-T-${RUN}`, price: 150, tax_category_key: 'restaurant.food' });
  cane = await createProduct(context, { name: `E2E Cane ${RUN}`, sku: `E2E-CHAIN-C-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  const list = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  methods = Object.fromEntries(list.data.rows.map((row) => [row.type, row.id]));
  await context.close();
});

test.afterAll(() => {
  cleanSales();
  cleanInventory();
});

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid^=pos-product-], [data-testid=pos-grid-empty]').first().waitFor({ state: 'visible' });
}

async function addBySearch(page: Page, product: Product): Promise<void> {
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(product.sku);
  await search.locator(`[data-testid=pos-search-${product.id}]`).click();
  await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: product.name }).first()).toBeVisible();
}

async function recipient(page: Page, taxId: string): Promise<void> {
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await sheet.locator('[data-testid=sale-checkout-doc-invoice]').click();
  await sheet.locator('[data-testid=sale-checkout-recipient-name] input').fill('e2e Talleres Pérez SL');
  await sheet.locator('[data-testid=sale-checkout-recipient-tax-id] input').fill(taxId);
  await sheet.locator('[data-testid=sale-checkout-recipient-address] input').fill('Calle Luna 3, Madrid');
}

test('SALE-F04: charged as an invoice, the ticket says the number Invoicing gave it in the same charge', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addBySearch(page, tapa);
  await addBySearch(page, cane);
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();

  // A tax ID that does not check is said under its box, and the button does not charge.
  await recipient(page, 'B12345678');
  await expect(sheet.locator('[data-testid=sale-checkout-recipient-tax-id-error]')).toHaveText(/That tax ID is not valid\.|Ese NIF no es válido\./);
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.card}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeVisible();
  await page.screenshot({ path: shot('sale-invoice-tax-id-1440') });

  // Corrected, it charges: one commit for the sale and its invoice.
  await sheet.locator('[data-testid=sale-checkout-recipient-tax-id] input').fill('B12345674');
  await expect(sheet.locator('[data-testid=sale-checkout-recipient-tax-id-error]')).toHaveCount(0);
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();

  const sale = (await api<FiscalSale>(context, A, 'GET', `/sale/sales/detail?sale_id=${(await newestSaleOf(context, tapa.sku)).id}`)).data;
  expect([sale.invoice_status, sale.invoice_type]).toEqual(['issued', 'F1']);
  expect(sale.invoice_number).toMatch(new RegExp(`^FACT-${YEAR}-\\d{6}$`));
  const found = await api<{ found: boolean; invoice: { number: string; total_amount: number; tax_breakdown: { base: number; quota: number }[] } }>(
    context,
    A,
    'GET',
    `/invoice/invoices/by_source?sale_id=${sale.id}`,
  );
  expect([found.data.found, found.data.invoice.number, found.data.invoice.total_amount]).toEqual([true, sale.invoice_number, 300]);
  // Two categories at 10 %: one fiscal key, closed once in the ticket and in the invoice (2,73 + 0,27).
  expect(found.data.invoice.tax_breakdown.map((row) => [row.base, row.quota])).toEqual([[273, 27]]);

  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt.locator('[data-testid=sale-receipt-number]')).toContainText(sale.invoice_number);
  await expect(receipt.locator('[data-testid=sale-receipt-number]')).not.toContainText(sale.number);
  await expect(receipt.locator('[data-testid=sale-receipt-title]')).toHaveText(/Invoice|Factura/);
  await page.screenshot({ path: shot('sale-invoice-receipt-1440') });
});

test('SALE-F30 and F31: a voided ticket and a refund get their rectifying invoices in the same operation', async ({ page, context }) => {
  await login(page, A, '/sale/sales');
  const ticket = (await chargeByApi(context, { lines: [{ product: tapa.sku }], payments: [{ method: 'card' }] })) as unknown as FiscalSale;
  expect([ticket.invoice_status, ticket.invoice_type]).toEqual(['issued', 'F2']);
  expect(ticket.invoice_number).toMatch(new RegExp(`^TICKET-${YEAR}-\\d{6}$`));

  await page.reload();
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-table-search] input').fill(ticket.number);
  await shown(page).locator(`[data-testid=sales-table-row-${ticket.id}-void]`).first().click();
  const modal = page.locator('ion-modal[data-testid=sale-void]');
  await modal.locator('[data-testid=sale-void-reason] textarea').fill('e2e wrong table');
  await modal.locator('[data-testid=sale-void-submit]').click();
  await expect(modal).toBeHidden();
  const voided = (await api<FiscalSale>(context, A, 'GET', `/sale/sales/detail?sale_id=${ticket.id}`)).data;
  expect(voided.void_invoice_status).toBe('issued');
  expect(voided.void_invoice_number).toMatch(new RegExp(`^RECT-${YEAR}-\\d{6}$`));

  const other = (await chargeByApi(context, { lines: [{ product: cane.sku }], payments: [{ method: 'card' }] })) as unknown as FiscalSale & {
    payments: { id: string }[];
  };
  const refunded = await api<{ invoice_status: string; invoice_type: string; invoice_number: string }>(context, A, 'POST', '/sale/sales/refund', {
    sale_id: other.id,
    reason: 'e2e returned',
    allocations: [{ payment_id: other.payments[0].id, amount: other.total }],
  });
  expect(refunded.status).toBe(200);
  expect([refunded.data.invoice_status, refunded.data.invoice_type]).toEqual(['issued', 'R5']);
  expect(refunded.data.invoice_number).toMatch(new RegExp(`^RECT-${YEAR}-\\d{6}$`));
});
