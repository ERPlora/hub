// flow: formato de importes (hub#1090) en Ventas, Facturas y VeriFactu — a sale of four digits (1.234,56 €,
// VAT included) charged by card, as the owner reads it in Spanish: its row in Sales, its ticket in Invoices and
// its record in VeriFactu say «1.234,56 €» with the thousands grouped, never «1234,56 €» (Spanish CLDR only
// groups from five digits on; every other screen of the Hub groups from four), at 390, 834 and 1440.
// What this file creates is deleted after it (`cleanSales()` takes the ticket and its record with the sale).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { ensureIssuer, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-MONEY-4-DIGITS-UNGROUPED-SALE-INVOICE-VERIFACTU';
const SKU = `E2E-MNY-${stamp()}`;
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
/** «1.234,56 €» as Intl paints it in Spanish (a no-break space before «€»). */
const GROUPED = /1\.234,56\s€/;
const UNGROUPED = /1234,56/;

let saleNumber = '';
let ticketNumber = '';

test.beforeAll(async ({ browser }) => {
  // The till issues a ticket (F2) for a card charge when the hub has an issuer, and VeriFactu seals its record.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  await ensureIssuer(context);
  await createProduct(context, { name: 'E2E Thousands', sku: SKU, price: 123456, tax_category_key: 'product.generic' });
  const sale = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  expect(sale.total).toBe(123456);
  saleNumber = sale.number;
  ticketNumber = psql(`select number from invoice_invoice where source_sale_id = '${sale.id}' and source_type = 'sale'`);
  expect(ticketNumber, 'the till issued its ticket').not.toBe('');
  expect(psql(`select count(*) from verifactu_record r join invoice_invoice i on i.id = r.invoice_id where i.number = '${ticketNumber}'`)).toBe('1');
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
  } finally {
    cleanInventory();
  }
});

/** The owner on `a` in Spanish: the Hub's language cookie, as the sign-in sets it from the account. */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/sale/sales`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

async function groupedIn(row: Locator): Promise<void> {
  await expect(row).toBeVisible();
  await expect(row).toContainText(GROUPED);
  await expect(row).not.toContainText(UNGROUPED);
}

for (const size of SIZES) {
  test(`hub#1090 at ${size.label}: Sales, Invoices and VeriFactu paint a four-digit amount with its thousands grouped`, async ({ browser }) => {
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      // Sales: the sale's row, found by its number.
      await shown(page).locator('[data-testid=sales-table-search] input').fill(saleNumber);
      await groupedIn(shown(page).locator('[data-testid=sales-table-row]', { hasText: saleNumber }).first());
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });

      // Invoices: the ticket the till issued for it.
      await page.goto(`${A}/invoice/invoices`);
      await shown(page).locator('[data-testid=invoice-list-search] input').fill(ticketNumber);
      await groupedIn(shown(page).locator('[data-testid=invoice-list-row]', { hasText: ticketNumber }).first());
      await page.screenshot({ path: shot(`${KEY}-invoice-${size.label}`) });

      // VeriFactu: the record sealed with that ticket.
      await page.goto(`${A}/verifactu/records`);
      await shown(page).locator('[data-testid=verifactu-records-search] input').fill(ticketNumber);
      await groupedIn(shown(page).locator('[data-testid=verifactu-records-row]', { hasText: ticketNumber }).first());
      await page.screenshot({ path: shot(`${KEY}-verifactu-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}
