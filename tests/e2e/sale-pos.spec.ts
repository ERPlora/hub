// The till in Chrome (SALE-F01, F02, F04, F05, F07, F13; apps/sale/WORKBOOK.md), crossing the real apps:
// Inventory's products priced at Taxes' real VAT (Spain), a Customers card on the check, a quick note on
// a line. The owner sells in cash with change and sees the ticket with its VAT row; sells by card to a
// customer found in the till; a product without tax category is refused; on a phone the cart is the
// drawer behind the FAB; the employee charges but never voids, refunds nor reads the figures.
// Screenshots of the till in the three viewports. What this file creates is deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, EMPLOYEE, api, hostPage, login, psql, shot, shown } from './helpers';
import { cleanUp as cleanCustomers, createCard, e2eName, spanishMobile } from './customer-helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, newestSale, shots, stamp } from './sale-helpers';

const RUN = stamp();
let water: Product;
let shirt: Product;
let untaxed: Product;
let customer: { id: string; name: string };
let methods: Record<string, string>;

test.afterAll(() => {
  cleanSales();
  cleanCustomers();
  cleanInventory();
});

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  water = await createProduct(context, { name: `E2E Water ${RUN}`, sku: `E2E-POS-W-${RUN}`, price: 110, tax_category_key: 'restaurant.drink' });
  shirt = await createProduct(context, { name: `E2E Shirt ${RUN}`, sku: `E2E-POS-S-${RUN}`, price: 1210, tax_category_key: 'product.generic' });
  untaxed = await createProduct(context, { name: `E2E Untaxed ${RUN}`, sku: `E2E-POS-U-${RUN}`, price: 500, tax_category_key: 'product.generic' });
  psql(`update inventory_product set tax_category_id = null where id = '${untaxed.id}'`);
  const card = await createCard(context, { name: e2eName('Ana'), phone: spanishMobile() });
  customer = { id: card.id, name: card.name };
  const list = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  methods = Object.fromEntries(list.data.rows.map((row) => [row.type, row.id]));
  await context.close();
});

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid^=pos-product-], [data-testid=pos-grid-empty]').first().waitFor({ state: 'visible' });
}

/** Adds a product the way a person finds it: the magnifier, its SKU, the result. */
async function addBySearch(page: Page, product: Product): Promise<void> {
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(product.sku);
  await search.locator(`[data-testid=pos-search-${product.id}]`).click();
}

const lineOf = (page: Page, name: string) =>
  shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: name }).filter({ has: page.locator('[data-testid=pos-qty-plus], [data-testid$=-void]') });

async function openCart(page: Page): Promise<void> {
  const fab = shown(page).locator('[data-testid=pos-cart-fab]');
  if (await fab.isVisible()) await fab.click();
}

test('SALE-F01: the owner sells two shirts in cash, gets the change and the ticket with its 21 % VAT', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addBySearch(page, shirt);
  await expect(lineOf(page, shirt.name)).toBeVisible();
  await lineOf(page, shirt.name).locator('[data-testid=pos-qty-plus]').click();
  // The total is the server's valuation of the check.
  await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/24[.,]20/);
  await shots(page, 'sale-pos', tillReady);

  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toContainText(/24[.,]20/);
  for (const key of ['5', '0']) await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).click();
  await expect(sheet.locator('[data-testid=sale-checkout-change]')).toContainText(/25[.,]80/);
  await page.screenshot({ path: shot('sale-checkout-cash-1440') });
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();

  // The ticket opens on its own: its number, the VAT row and the total.
  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  await expect(receipt).toContainText(/21\s?%/);
  await expect(receipt).toContainText(/24[.,]20/);
  await page.screenshot({ path: shot('sale-pos-ticket-1440') });

  const sale = await newestSale(context);
  expect((({ total, subtotal, tax_total, change_total }) => ({ total, subtotal, tax_total, change_total }))(sale)).toEqual({
    total: 2420,
    subtotal: 2000,
    tax_total: 420,
    change_total: 2580,
  });
  expect(sale.lines.map((line) => [line.tax_rate, line.line_total])).toEqual([['21.00', 2420]]);
  expect(sale.payments.map((p) => [p.method_type, p.tendered, p.change])).toEqual([['cash', 5000, 2580]]);
});

test('SALE-F05 and F13: a check with a customer found in the till and a quick note is charged by card', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/pos');
  const note = await api<{ id: string }>(context, A, 'POST', '/sale/quick_notes', { text: `e2e no ice ${RUN}`, sort_order: 1 });
  expect(note.status).toBe(201);
  await tillReady(page);
  await addBySearch(page, water);
  const line = lineOf(page, water.name);
  await expect(line).toBeVisible();

  // The quick note, from its chip.
  await line.locator('[data-testid$=-note]').first().click();
  await page.locator(`[data-testid=pos-quick-note-${note.data.id}]`).click();
  await page.locator('[data-testid=pos-note-save]').click();
  await expect(line).toContainText(`e2e no ice ${RUN}`);

  // The customer, searched in Customers' own search from the cart.
  await shown(page).locator('[data-testid=customer-search-trigger]').click();
  const search = page.locator('[data-testid=customer-search-modal]');
  await search.locator('[data-testid=customer-picker-search] input').fill(customer.name);
  await search.locator(`[data-testid=customer-picker-result-${customer.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-customer-chip]')).toContainText(customer.name);

  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.card}]`).click();
  await expect(sheet.locator('[data-testid=sale-checkout-exact]')).toBeVisible();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();

  const sale = await newestSale(context);
  expect((({ total, customer_id, customer_name }) => ({ total, customer_id, customer_name }))(sale)).toEqual({
    total: 110,
    customer_id: customer.id,
    customer_name: customer.name,
  });
  expect(sale.lines[0].tax_rate).toBe('10.00');
  expect(sale.payments.map((p) => p.method_type)).toEqual(['card']);
});

test('SALE-F07: a product without tax category is marked and never enters the check', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await expect(shown(page).locator('[data-testid=pos-catalog-health]')).toBeVisible();
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(untaxed.sku);
  const result = search.locator(`[data-testid=pos-search-${untaxed.id}]`);
  await expect(result).toBeVisible();
  await expect(result).toContainText(/tax|IVA/);
  await result.click();
  await expect(lineOf(page, untaxed.name)).toHaveCount(0);
  await page.screenshot({ path: shot('sale-pos-untaxed') });
});

test('the till on a phone: the cart is the drawer behind the button with its count and total', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addBySearch(page, water);
  const fab = shown(page).locator('[data-testid=pos-cart-fab]');
  await expect(fab).toBeVisible();
  await expect(shown(page).locator('[data-testid=pos-cart-fab-count]')).toHaveText('1');
  await expect(shown(page).locator('[data-testid=pos-cart-fab-total]')).toContainText(/1[.,]10/);
  await page.screenshot({ path: shot('sale-pos-phone-catalog') });
  await openCart(page);
  // The drawer slides in (.25 s): the screenshot waits until Charge is fully on screen.
  await expect(shown(page).locator('[data-testid=pos-charge]')).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: shot('sale-pos-phone-cart') });
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.card}]`).click();
  await page.screenshot({ path: shot('sale-checkout-phone') });
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  expect((await newestSale(context)).total).toBe(110);
});

test('the employee charges at the till but never voids, refunds nor reads the figures', async ({ browser }) => {
  const { context, page } = await hostPage(browser, A, { next: '/sale/pos', credentials: EMPLOYEE });
  try {
    await tillReady(page);
    await addBySearch(page, water);
    await shown(page).locator('[data-testid=pos-charge]').click();
    const sheet = page.locator('[data-testid=sale-checkout-modal]');
    await expect(sheet).toBeVisible();
    await sheet.locator(`[data-testid=sale-checkout-method-${methods.card}]`).click();
    await sheet.locator('[data-testid=sale-checkout-confirm]').click();
    await expect(sheet).toBeHidden();
    await page.screenshot({ path: shot('sale-pos-employee') });

    await page.goto(`${A}/sale/sales`);
    await shown(page).locator('[data-testid=sales-table-row]').first().waitFor({ state: 'visible' });
    await expect(shown(page).locator('[data-testid=sales-kpis]')).toHaveCount(0);
    await expect(shown(page).locator('[data-testid$=-void], [data-testid$=-refund]')).toHaveCount(0);
    await page.screenshot({ path: shot('sale-sales-employee') });
  } finally {
    await context.close();
  }
});

