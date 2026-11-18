// flow: ninguno — transversal (hub#974): a quantity of four digits or more, as the owner reads it in Spanish, is written
// one way on every screen, with the platform's `formatQuantity` (`@erplora/ui/components`): a stock of 12500 says
// «12.500» in Inventory (it said «12500»), and a ticket of 1500 units says «1.500» on its invoice line, as the till's
// own paper and the assistant's card write it. The till's quantity field holds what a person types and edits: «1500»,
// ungrouped, as a till's quantity field does (what is typed is not grouped). At 1440; the fleet's sweep
// shoots the three sizes. What this file creates is deleted after it.
import { expect, test } from '@playwright/test';

import { A, capture, login, psql, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { cleanInventory, createProduct, type Product, productRow, productsReady, searchProducts } from './inventory-helpers';
import { ensureIssuer, snapshotSeries } from './invoice-helpers';
import { chargeByApi, checkWithDish, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-QUANTITY-ONE-FORMAT';
const RUN = stamp();
const STOCK_SKU = `E2E-QTY-STOCK-${RUN}`;
const SOLD_SKU = `E2E-QTY-SOLD-${RUN}`;
const VIEWPORT = { width: 1440, height: 900 };

let sold: Product;
let ticketId = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  // The till issues a ticket (F2) for a card charge when the hub has an issuer.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/inventory/products');
  await drawerOff(context);
  await ensureIssuer(context);
  await createProduct(context, { name: `E2E Qty Stock ${RUN}`, sku: STOCK_SKU, initial_stock: '12500' });
  // Three cents a unit: 1500 of them are «45,00 €», so no amount on the line reads «1.500».
  sold = await createProduct(context, { name: `E2E Qty Sold ${RUN}`, sku: SOLD_SKU, price: 3 });
  const sale = await chargeByApi(context, { lines: [{ product: SOLD_SKU, quantity: '1500' }], payments: [{ method: 'card' }] });
  expect(sale.lines[0].quantity).toBe('1500.000');
  ticketId = psql(`select id from invoice_invoice where source_sale_id = '${sale.id}' and source_type = 'sale'`);
  expect(ticketId, 'the till issued its ticket').not.toBe('');
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
  } finally {
    try {
      cleanInventory();
    } finally {
      restoreDrawer();
    }
  }
});

test('hub#974: Inventory writes a stock of 12500 as «12.500», as every screen groups a quantity', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, VIEWPORT, '/inventory/products');
  try {
    await saveSessionForTheSweep(context);
    await productsReady(page);
    await searchProducts(page, STOCK_SKU);
    await expect(productRow(page, STOCK_SKU).locator('[data-testid=inventory-product-stock]')).toHaveText('12.500');
    await capture(page, `${KEY}-inventory-1440`);
  } finally {
    await context.close();
  }
});

test('hub#974: the ticket of 1500 units writes «1.500» on its line', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, VIEWPORT, `/invoice/invoices/${ticketId}`);
  try {
    const line = shown(page).locator('[data-testid=invoice-line-row]').filter({ hasText: `E2E Qty Sold ${RUN}` });
    // Its cells: number, description, quantity, unit price…
    await expect(line.locator('td').nth(2)).toHaveText('1.500');
    await capture(page, `${KEY}-invoice-1440`);
  } finally {
    await context.close();
  }
});

test('hub#974: the till’s quantity field takes 1500 as typed and keeps it ungrouped', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A, viewport: VIEWPORT, locale: 'es-ES' });
  const page = await context.newPage();
  try {
    // The till in Spanish with the dish on a new check.
    await checkWithDish(page, context, 'es', sold);
    const line = shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: sold.name }).first();
    const field = line.locator('.pos-qty input');
    await field.fill('1500');
    await field.press('Enter');
    // The server keeps it: the line's total is 1500 × 0,03 €.
    await expect(line).toContainText(/45,00\s€/);
    await expect(field).toHaveValue('1500');
    // And the check's total, once the server's preview of it arrives (a dash while it is on its way).
    await expect(shown(page).locator('[data-testid=pos-total]')).toHaveText(/45,00\s€/);
    await capture(page, `${KEY}-till-1440`);
  } finally {
    await context.close();
  }
});
