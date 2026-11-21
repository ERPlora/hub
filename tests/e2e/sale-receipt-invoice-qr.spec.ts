// SALE-F29 and INVOICE-F04: a ticket's paper, on screen and on the receipt printer, carries a second QR after the
// fiscal one, with the code under it; the address it carries opens the business's public page where the customer
// asks for the full invoice of that ticket. A sale charged as a full invoice carries none. What the run makes is
// deleted after it, and the series give their numbers back.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, saveSessionForTheSweep, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, deliver, ensureIssuer, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, type SaleOut, stamp } from './sale-helpers';
import { noHorizontalScroll } from './service-helpers';

const RUN = stamp();
const TILL = `e2e Claim till ${RUN}`;
/** The sizes the document is looked at in: a desk, a tablet and a low phone. */
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
];
let coffee: Product;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  snapshotSeries();
  await ensureIssuer(context);
  coffee = await createProduct(context, { name: `E2E Claim coffee ${RUN}`, sku: `E2E-CLAIM-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  const till = await api(context, A, 'POST', '/printing/printers', { name: TILL, kind: 'network', address: '10.0.0.89', usage: 'receipt' });
  expect(till.status, JSON.stringify(till.data)).toBe(201);
  await context.close();
});

test.afterAll(() => {
  try {
    psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name = '${TILL}')`);
    psql(`delete from printing_printer where name = '${TILL}'`);
    cleanInvoices();
  } finally {
    cleanSales();
    cleanInventory();
  }
});

async function documentOf(page: Page, sale: SaleOut) {
  await page.goto('/sale/sales');
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
  await shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`).click();
  const modal = page.locator('[data-testid=sale-document-modal]');
  await expect(modal.locator('[data-testid=sale-receipt]')).toBeVisible();
  return modal;
}

/** «Print» on the sale's document: the receipt printer's paper, with the address under its second QR and the code
 *  under it (both empty when it carries none). */
async function printedClaim(context: BrowserContext, sale: SaleOut): Promise<{ url: string; code: string }> {
  const printed = await api<{ queued: boolean; job_id: string }>(context, A, 'POST', '/sale/sales/print', { sale_id: sale.id });
  expect(printed.status, JSON.stringify(printed.data)).toBe(200);
  expect(printed.data.queued).toBe(true);
  const [url, code] = psql(
    `select coalesce(document->>'claim_qr_data', '') || '|' || coalesce(document->>'claim_locator', '') ` +
      `from printing_printjob where id = '${printed.data.job_id}'`,
  ).split('|');
  return { url, code };
}

/** The customer, without a session, on her phone, at the address the QR carries. */
async function scan(context: BrowserContext, url: string, ticketNumber: string): Promise<void> {
  const phone = await context.browser()!.newContext({ viewport: { width: 390, height: 844 }, locale: 'es-ES' });
  try {
    const page = await phone.newPage();
    await page.goto(url);
    await expect(page.locator('[data-testid=invoice-public-ticket]')).toContainText(ticketNumber);
    await expect(page.locator('[data-testid=invoice-public-form]')).toBeVisible();
  } finally {
    await phone.close();
  }
}

test('a ticket carries the QR to ask for its full invoice, and its address opens that page', async ({ page, context }) => {
  await login(page, A, '/sale/sales');
  await saveSessionForTheSweep(context);
  const sale = await chargeByApi(context, { lines: [{ product: coffee.sku }], payments: [{ method: 'card' }] });
  const ticketNumber = (await deliver(context, 'sale.sale.completed', sale.id)).number;

  const modal = await documentOf(page, sale);
  const claim = modal.locator('[data-testid=sale-receipt-claim]');
  await expect(claim).toContainText('Scan to ask for your full invoice');
  await expect(claim.locator('img')).toHaveAttribute('src', /^data:image\/png;base64,/);
  const code = (await claim.locator('[data-testid=sale-receipt-claim-hint]').innerText()).trim();
  expect(code).toMatch(new RegExp(`^${sale.number}-[0-9A-Z]{12}$`));
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await claim.scrollIntoViewIfNeeded();
    await noHorizontalScroll(page, `the document at ${size.width} px`);
    await capture(page, `SALE-F29-receipt-invoice-qr-${size.width}x${size.height}`);
  }

  // The receipt printer's paper carries the same code, under the address of the same page.
  const printed = await printedClaim(context, sale);
  expect(printed).toEqual({ url: `${A}/p/a/invoice/${code}`, code });
  await scan(context, printed.url, ticketNumber);
});

test('a sale charged as a full invoice carries no QR to ask for one', async ({ page, context }) => {
  await login(page, A, '/sale/sales');
  const sale = await chargeByApi(context, {
    lines: [{ product: coffee.sku }],
    payments: [{ method: 'card' }],
    document_type: 'invoice',
    customer_name: 'Talleres Pérez SL',
    customer_tax_id: 'B12345674',
    customer_address: 'Calle Luna 3, Madrid',
  });
  const modal = await documentOf(page, sale);
  await expect(modal.locator('[data-testid=sale-receipt-title]')).toBeVisible();
  await expect(modal.locator('[data-testid=sale-receipt-claim]')).toHaveCount(0);
  expect(await printedClaim(context, sale)).toEqual({ url: '', code: '' });
});
