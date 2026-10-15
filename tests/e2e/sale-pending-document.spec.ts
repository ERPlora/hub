// A fiscal document that waits has a way out in phase 1 (SALE-F29; INVOICE-F06; apps/sale/WORKBOOK.md):
// with no issuer the card charge goes through and its ticket waits; Sales says «Document pending» under
// the sale's status and on its document, and once the issuer is set up «Issue now» issues its F2 — the
// pill goes by itself (live) and the paper prints the ticket's number. Setup and evidence through the
// APIs; the checks in the browser (hidden). The hub's issuer is put back as it was; everything the run
// creates is deleted after it and the series give their numbers back.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { ensureIssuer, issuerNow, type IssuerOut, snapshotSeries } from './invoice-helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { chargeByApi, cleanSales, type SaleOut, stamp } from './sale-helpers';

const RUN = stamp();
const YEAR = new Date().getFullYear();
let coffee: Product;
/** The hub's issuer before the run (its address is blanked while the run needs «no issuer»). */
let original: IssuerOut | null = null;

interface FiscalSale extends SaleOut {
  invoice_status: string;
  invoice_type: string;
  invoice_number: string;
  documents_pending: boolean;
}

const quoted = (text: string): string => `'${text.replace(/'/g, "''")}'`;

/** The issuer as it was: its address back (the hub had one), or none (cleanInvoices removes the run's). */
function putIssuerBack(): void {
  if (original?.configured) psql(`update invoice_issuer set address = ${quoted(original.address)}`);
}

test.beforeAll(async ({ browser }) => {
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  original = await issuerNow(context);
  // No issuer while the run charges: a configured one loses its address (put back after).
  if (original.configured) psql("update invoice_issuer set address = ''");
  expect((await issuerNow(context)).configured).toBe(false);
  coffee = await createProduct(context, { name: `E2E Coffee ${RUN}`, sku: `E2E-PEND-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  await context.close();
});

test.afterAll(() => {
  putIssuerBack();
  cleanSales();
  cleanInventory();
});

async function saleOf(context: BrowserContext, id: string): Promise<FiscalSale> {
  const res = await api<FiscalSale>(context, A, 'GET', `/sale/sales/detail?sale_id=${id}`);
  expect(res.status).toBe(200);
  return res.data;
}

async function findSale(page: Page, sale: SaleOut) {
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
  const row = shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);
  await expect(row).toBeVisible();
  return row;
}

test('SALE-F29: a ticket that waits says so, and «Issue now» issues it once the issuer exists', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/sales');
  const sale = (await chargeByApi(context, { lines: [{ product: coffee.sku }], payments: [{ method: 'card' }] })) as FiscalSale;
  expect([sale.status, sale.invoice_status, sale.documents_pending]).toEqual(['completed', 'pending', true]);

  // The list says it under the status; its document says it above the paper and on it.
  const row = await findSale(page, sale);
  await expect(row.locator('[data-testid=sales-documents-pending]')).toHaveText(/Document pending|Documento pendiente/);
  await row.click();
  const modal = page.locator('[data-testid=sale-document-modal]');
  await expect(modal.locator('[data-testid=sale-documents-pending]')).toBeVisible();
  await expect(modal.locator('[data-testid=sale-receipt-pending]')).toHaveText(/Fiscal document pending|Documento fiscal pendiente/);
  // Still no issuer: «Issue now» says why, and nothing changes.
  await modal.locator('[data-testid=sale-documents-issue]').click();
  await expect(modal.locator('[data-testid=sale-documents-error]')).toBeVisible();
  expect((await saleOf(context, sale.id)).invoice_status).toBe('pending');
  await page.screenshot({ path: shot('sale-pending-document-1280') });
  await modal.locator('[data-testid=sale-document-close]').click();
  await expect(modal).toBeHidden();

  // The issuer set up (the hub's own back, or one for the run), «Issue now» from the row issues its F2.
  putIssuerBack();
  if (!original?.configured) await ensureIssuer(context);
  await shown(page).locator(`[data-testid=sales-table-row-${sale.id}-issue]`).first().click();
  await expect(row.locator('[data-testid=sales-documents-pending]')).toHaveCount(0);
  const issued = await saleOf(context, sale.id);
  expect([issued.invoice_status, issued.invoice_type, issued.documents_pending]).toEqual(['issued', 'F2', false]);
  expect(issued.invoice_number).toMatch(new RegExp(`^TICKET-${YEAR}-\\d{6}$`));
  await row.click();
  await expect(modal.locator('[data-testid=sale-receipt-number]')).toContainText(issued.invoice_number);
  await expect(modal.locator('[data-testid=sale-documents-pending]')).toHaveCount(0);
});
