// Invoicing in Chrome, crossing the real Sales, Customers, Inventory and Taxes (apps/invoice/WORKBOOK.md):
//   - INVOICE-F02, F16, F17, F18: a sale charged as an invoice at the till (Sales' own checkout, with the
//     customer's name, tax ID and address) becomes a full invoice F1, paid; it is found in Invoices by its
//     number, opened, and printed as the A4 paper;
//   - INVOICE-F01, F09: a ticket refunded whole in Sales gets its rectifying invoice R5, the ticket is
//     cancelled, and the R5 opens the ticket it rectifies;
//   - the list filters behind the table's funnel (the total in euros), with its count, at every width; a
//     «to» day before its «from» is said under it and does not filter.
// Phase 1 has no outbox relay: the sale's real event, read from the outbox, is handed to the operation the
// reaction runs (invoice-helpers.ts `deliver`), as the relay will. Screenshots in the three viewports.
// What this file creates is deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, shot, shown } from './helpers';
import { cleanUp as cleanCustomers } from './customer-helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, deliver, ensureIssuer, invoiceOf, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, newestSaleOf, shots, stamp } from './sale-helpers';

const RUN = stamp();
let shampoo: Product;
let wax: Product;
let methods: Record<string, string>;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/invoice/invoices');
  snapshotSeries();
  await ensureIssuer(context);
  shampoo = await createProduct(context, { name: `E2E Shampoo ${RUN}`, sku: `E2E-INV-S-${RUN}`, price: 1210, tax_category_key: 'product.generic' });
  wax = await createProduct(context, { name: `E2E Wax ${RUN}`, sku: `E2E-INV-W-${RUN}`, price: 605, tax_category_key: 'product.generic' });
  const list = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  methods = Object.fromEntries(list.data.rows.map((row) => [row.type, row.id]));
  await context.close();
});

test.afterAll(() => {
  try {
    cleanInvoices();
  } finally {
    cleanSales();
    cleanCustomers();
    cleanInventory();
  }
});

/** The widths of the filter panel's screenshots: a phone (the panel is a sheet), a tablet and a desk
 *  (two columns), as the SaaS panel's `VIEWPORTS`. */
const FILTER_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid^=pos-product-], [data-testid=pos-grid-empty]').first().waitFor({ state: 'visible' });
}

async function addBySearch(page: Page, product: Product): Promise<void> {
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(product.sku);
  await search.locator(`[data-testid=pos-search-${product.id}]`).click();
}

/** The Invoices list shows `number`, found with its own search box. */
async function findInList(page: Page, number: string): Promise<void> {
  await page.goto(`${A}/invoice/invoices`);
  const list = shown(page);
  await list.locator('[data-testid=invoice-list-search] input').fill(number);
  await expect(list.locator('[data-testid=invoice-list-row]', { hasText: number }).first()).toBeVisible();
}

test('INVOICE-F02 and F18: a sale charged as an invoice at the till is a full invoice, found and printed', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addBySearch(page, shampoo);
  await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/12[.,]10/);
  await shown(page).locator('[data-testid=pos-charge]').click();

  // Sales' own checkout: «Invoice», the recipient, by card.
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await sheet.locator('[data-testid=sale-checkout-doc-invoice]').click();
  await sheet.locator('[data-testid=sale-checkout-recipient-name] input').fill(`e2e Talleres ${RUN}`);
  await sheet.locator('[data-testid=sale-checkout-recipient-tax-id] input').fill('B12345674');
  await sheet.locator('[data-testid=sale-checkout-recipient-address] input').fill('Calle Luna 3, Madrid');
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.card}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  // Sales opens the sale's own document; closed, the till is free again.
  const documentModal = page.locator('[data-testid=sale-document-modal]');
  await expect(documentModal).toBeVisible();
  await documentModal.locator('[data-testid=sale-document-close]').click();
  await expect(documentModal).toBeHidden();

  // The relay's part: the charge's real event, to Invoicing.
  const sale = await newestSaleOf(context, shampoo.sku);
  const invoice = await deliver(context, 'sale.sale.completed', sale.id);
  expect([invoice.invoice_type, invoice.status, invoice.total_amount, invoice.customer_tax_id]).toEqual(['F1', 'paid', 1210, 'B12345674']);

  // Found in Invoices by its number: «Invoice», «Paid», its total.
  await findInList(page, invoice.number);
  const row = shown(page).locator('[data-testid=invoice-list-row]', { hasText: invoice.number }).first();
  await expect(row).toContainText(/12[.,]10/);
  await expect(row.locator('[data-testid=invoice-list-status]')).toHaveText('Paid');
  await shots(page, 'invoice-list', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-list-row]', { hasText: invoice.number }).first()).toBeVisible();
  });

  // Opened: its header, its recipient, its lines and totals.
  await row.click();
  await page.waitForURL(new RegExp(`/invoice/invoices/${invoice.id}$`));
  const detail = shown(page);
  await expect(detail.locator('[data-testid=invoice-detail-title]')).toHaveText(`Invoice ${invoice.number}`);
  await expect(detail.locator('[data-testid=invoice-detail-customer-tax-id]')).toHaveText('B12345674');
  await expect(detail.locator('[data-testid=invoice-detail-source]')).toHaveText('POS sale');
  await expect(detail.locator('[data-testid=invoice-detail-sale]')).toHaveText(sale.number);
  await expect(detail.locator('[data-testid=invoice-detail-total]')).toContainText(/12[.,]10/);
  await shots(page, 'invoice-detail', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-detail-title]')).toBeVisible();
  });

  // «Print / PDF»: the browser's dialog prints the A4 paper alone (captured at the moment it prints).
  await page.evaluate(() => {
    const w = window as unknown as { __printed?: string[]; print: () => void };
    w.__printed = [];
    w.print = () => {
      const paper = document.querySelector('body > .sale-print-root [data-testid=invoice-paper]');
      w.__printed!.push(paper?.textContent ?? '');
    };
  });
  await detail.locator('[data-testid=invoice-detail-print]').click();
  const printed = await page.evaluate(() => (window as unknown as { __printed: string[] }).__printed);
  expect(printed).toHaveLength(1);
  expect(printed[0]).toContain(invoice.number);
  expect(printed[0]).toContain(`e2e Talleres ${RUN}`);
  expect(printed[0]).toContain('Copy');
});

test('INVOICE-F01 and F09: a ticket refunded whole in Sales gets its rectifying invoice R5 and is cancelled', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/invoice/invoices');
  const sale = await chargeByApi(context, { lines: [{ product: wax.sku, quantity: '2' }], payments: [{ method: 'card' }] });
  const ticket = await deliver(context, 'sale.sale.completed', sale.id);
  expect([ticket.invoice_type, ticket.status, ticket.total_amount]).toEqual(['F2', 'paid', 1210]);

  const refund = await api(context, A, 'POST', '/sale/sales/refund', {
    sale_id: sale.id,
    reason: `e2e broken ${RUN}`,
    allocations: [{ payment_id: sale.payments[0].id, amount: sale.total }],
  });
  expect(refund.status).toBe(200);
  const rectifying = await deliver(context, 'sale.sale.refunded', sale.id);
  expect([rectifying.invoice_type, rectifying.total_amount, rectifying.rectifies?.number]).toEqual(['R5', -1210, ticket.number]);
  expect((await invoiceOf(context, ticket.id)).status).toBe('cancelled');

  // In Invoices: the rectifying one, negative; the ticket, «Cancelled» and no longer rectifiable.
  await findInList(page, rectifying.number);
  await expect(shown(page).locator('[data-testid=invoice-list-row]', { hasText: rectifying.number }).first()).toContainText(/-.?12[.,]10|−.?12[.,]10/);
  await page.goto(`${A}/invoice/invoices/${rectifying.id}`);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=invoice-detail-title]')).toHaveText(`Invoice ${rectifying.number}`);
  await expect(detail.locator('[data-testid=invoice-detail-notes]')).toHaveText(`Rectifies invoice ${ticket.number}. Reason: e2e broken ${RUN}`);
  await detail.locator('[data-testid=invoice-detail-rectifies-link]').click();
  await page.waitForURL(new RegExp(`/invoice/invoices/${ticket.id}$`));
  await expect(shown(page).locator('[data-testid=invoice-detail-status]')).toHaveText('Cancelled');
  await expect(shown(page).locator('[data-testid=invoice-detail-rectify]')).toHaveCount(0);
  await shots(page, 'invoice-cancelled-ticket', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-detail-status]')).toHaveText('Cancelled');
  });
});

// flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
test('FIX-DATATABLE-HUB-FILTERS-2A: Invoices filter by total in euros behind the funnel, with its count; a «to» day before its «from» is said under it', async ({ page, context }) => {
  await login(page, A, '/invoice/invoices');
  // Two tickets, 12,10 € and 6,05 €, each handed to Invoicing as the relay will.
  const dearSale = await chargeByApi(context, { lines: [{ product: shampoo.sku }], payments: [{ method: 'card' }] });
  const cheapSale = await chargeByApi(context, { lines: [{ product: wax.sku }], payments: [{ method: 'card' }] });
  const dear = await deliver(context, 'sale.sale.completed', dearSale.id);
  const cheap = await deliver(context, 'sale.sale.completed', cheapSale.id);
  expect([dear.total_amount, cheap.total_amount]).toEqual([1210, 605]);
  const rowOf = (number: string) => shown(page).locator('[data-testid=invoice-list-row]', { hasText: number });
  const panel = shown(page).locator('[data-testid=invoice-list-filters-panel]');
  const toggle = shown(page).locator('[data-testid=invoice-list-filters-toggle]');
  const count = shown(page).locator('[data-testid=invoice-list-filters-count]');
  for (const vp of FILTER_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/invoice/invoices`);
    await expect(rowOf(dear.number)).toBeVisible();
    await expect(rowOf(cheap.number)).toBeVisible();
    await toggle.click();
    await expect(panel).toBeVisible();
    // «Total from 10» is ten euros (invoice#113): the 12,10 € ticket stays, the 6,05 € one goes.
    await panel.locator('[data-testid=invoice-list-filter-total_amount_from] input').fill('10');
    await panel.locator('[data-testid=invoice-list-filters-apply]').click();
    await expect(panel).toBeHidden();
    await expect(count).toHaveText('1');
    await expect(rowOf(dear.number)).toBeVisible();
    await expect(rowOf(cheap.number)).toHaveCount(0);
    await toggle.click();
    await expect(panel).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-FILTERS-2A-invoice-${vp.label}`) });
    await panel.locator('[data-testid=invoice-list-filters-clear]').click();
    await expect(count).toHaveCount(0);
    await panel.locator('[data-testid=invoice-list-filters-close]').click();
    await expect(panel).toBeHidden();
    await expect(rowOf(cheap.number)).toBeVisible();
  }

  // «Issued» from the 14th to the 1st: said under «to», the funnel turns red, and nothing is filtered.
  await toggle.click();
  await panel.locator('[data-testid=invoice-list-filter-issue_date_from] input').fill('2026-10-14');
  await panel.locator('[data-testid=invoice-list-filter-issue_date_to] input').fill('2026-10-01');
  await panel.locator('[data-testid=invoice-list-filters-apply]').click();
  await expect(toggle).toHaveAttribute('data-invalid', 'true');
  await expect(rowOf(dear.number)).toBeVisible();
  await expect(rowOf(cheap.number)).toBeVisible();
  await toggle.click();
  const to = panel.locator('[data-testid=invoice-list-filter-issue_date_to]');
  await expect(to).toHaveClass(/ion-invalid/);
  await expect(to.locator('.error-text')).toHaveText(/The end date cannot be before the start date\.|La fecha final no puede ser anterior a la inicial\./);
  await page.screenshot({ path: shot('FIX-DATATABLE-HUB-FILTERS-2A-invoice-error-1440') });
});
