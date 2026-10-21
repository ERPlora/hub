// A charged sale that could not be invoiced (INVOICE-F06; apps/invoice/WORKBOOK.md): with no issuer the card
// charge goes through and its ticket waits («Document pending» in Sales). Once the issuer is set up, the ticket
// asked of Invoicing by the sale's number (the API, the assistant) is the sale's document when the request
// ends: the pill goes by itself in Sales, live, without «Issue now», and the sale carries that same number.
// Setup and evidence through the APIs; the checks in the browser (hidden). The hub's issuer is put back as it
// was; everything the run creates is deleted after it and the series give their numbers back.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shown } from './helpers';
import { cleanInvoices, ensureIssuer, flowShots, type InvoiceOut, issuedIds, issuerNow, type IssuerOut, snapshotSeries } from './invoice-helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { chargeByApi, cleanSales, type SaleOut, stamp } from './sale-helpers';

const RUN = stamp();
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
  if (original.configured) psql("update invoice_issuer set address = ''");
  expect((await issuerNow(context)).configured).toBe(false);
  coffee = await createProduct(context, { name: `E2E Coffee ${RUN}`, sku: `E2E-INV-PEND-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  await context.close();
});

test.afterAll(() => {
  try {
    putIssuerBack();
    cleanInvoices();
  } finally {
    cleanSales();
    cleanInventory();
  }
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

test('INVOICE-F06: a ticket asked of Invoicing by the sale’s number is the sale’s document at once, without «Issue now»', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/sales');
  const sale = (await chargeByApi(context, { lines: [{ product: coffee.sku }], payments: [{ method: 'card' }] })) as FiscalSale;
  expect([sale.status, sale.invoice_status, sale.documents_pending]).toEqual(['completed', 'pending', true]);
  const row = await findSale(page, sale);
  await expect(row.locator('[data-testid=sales-documents-pending]')).toBeVisible();
  await flowShots(page, 'INVOICE-F06-pending', async (p) => {
    await expect(shown(p).locator(`[data-testid=sales-table-row][data-id="${sale.id}"] [data-testid=sales-documents-pending]`)).toBeVisible();
  });

  // The issuer set up (the hub's own back, or one for the run); the ticket asked of Invoicing by the number.
  putIssuerBack();
  if (!original?.configured) await ensureIssuer(context);
  const asked = await api<{ issued: boolean; invoice: InvoiceOut }>(context, A, 'POST', '/invoice/invoices/from_sale', { sale: sale.number });
  expect([asked.status, asked.data.issued, asked.data.invoice.invoice_type]).toEqual([200, true, 'F2']);
  issuedIds.add(asked.data.invoice.id);

  // Sales has it when the request ends: no «Issue now», the pill goes live and the sale names that number.
  const linked = await saleOf(context, sale.id);
  expect([linked.invoice_status, linked.invoice_number, linked.documents_pending]).toEqual(['issued', asked.data.invoice.number, false]);
  await expect(row.locator('[data-testid=sales-documents-pending]')).toHaveCount(0);
  await flowShots(page, 'INVOICE-F06', async (p) => {
    await expect(shown(p).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`)).toBeVisible();
  });
  // «Issue now» has nothing left: no other document.
  const again = await api<FiscalSale>(context, A, 'POST', '/sale/sales/issue_documents', { sale: sale.number });
  expect([again.status, again.data.invoice_number, again.data.documents_pending]).toEqual([200, asked.data.invoice.number, false]);
  const documents = await api<{ total: number }>(context, A, 'GET', `/invoice/invoices?search=${encodeURIComponent(asked.data.invoice.number)}&limit=10`);
  expect(documents.data.total).toBe(1);
});
