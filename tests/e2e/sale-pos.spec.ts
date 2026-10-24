// The till in Chrome (SALE-F01, F02, F04, F05, F07, F13; apps/sale/WORKBOOK.md), crossing the real apps:
// Inventory's products priced at Taxes' real VAT (Spain), a Customers card on the check, a quick note on
// a line. The owner sells in cash with change and sees the ticket with its VAT row; sells by card to a
// customer found in the till; a product without tax category is refused; on a phone the cart is the
// drawer behind the FAB; the employee charges and sees «Void» and «Refund» (each asks a manager's approval:
// sale-approval.spec.ts) but never reads the figures. A marked
// line is charged on its own (SALE-F22) with its ticket, and the rest closes the check; on full screen
// the checkout sheet still opens and charges on top of the till.
// Screenshots of the till in the three viewports. What this file creates is deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, EMPLOYEE, api, hostPage, login, psql, shot, shown } from './helpers';
import { cleanUp as cleanCustomers, createCard, e2eName, spanishMobile } from './customer-helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { cleanSales, drawerOff, newestSaleOf, restoreDrawer, shots, stamp } from './sale-helpers';

const RUN = stamp();
let water: Product;
let shirt: Product;
let untaxed: Product;
let juice: Product;
let cake: Product;
let customer: { id: string; name: string };
let methods: Record<string, string>;
/** Kitchen on in `a` when this file starts: then «Charge» sends what is pending first (sales#439). */
let kitchenOn = false;

test.afterAll(() => {
  // The kitchen tickets this file's rounds opened (their dishes name its products): they go with their checks, or
  // the next spec's kitchen display and cash close show them as their own.
  const tickets = psql(`select coalesce(string_agg(distinct quote_literal(ticket_id::text), ','), 'null') from kitchen_ticketitem where name like '% ${RUN}'`);
  // What this worker's `RUN` charged: after a failed test Playwright starts a new worker, whose `beforeAll` makes a new
  // `RUN` that may charge nothing (the tests after the failure), so no round of its own reaches the kitchen.
  const charged = Number(psql(`select count(*) from sale_saleline where sku like 'E2E-POS-%-${RUN}'`));
  cleanSales();
  cleanCustomers();
  cleanInventory();
  restoreDrawer();
  // Charged with Kitchen on, the rounds must be found (the check below is not empty by mistake); otherwise none are sent.
  if (kitchenOn && charged > 0) expect(tickets, `the rounds of ${RUN} reached the kitchen`).not.toBe('null');
  if (tickets === 'null') return;
  expect(
    psql(`select (select count(*) from kitchen_ticket where id::text in (${tickets})) + (select count(*) from kitchen_ticketitem where ticket_id::text in (${tickets})) + (select count(*) from kitchen_logentry where ticket_id::text in (${tickets}))`),
    `kitchen rows of ${RUN} left behind`,
  ).toBe('0');
});

test.beforeAll(async ({ browser }) => {
  // Card charges issue tickets (F2) when the hub has an issuer: the cleanup gives their numbers back.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  const me = await api<{ apps: { label: string; state: string }[] }>(context, A, 'GET', '/me');
  kitchenOn = me.data.apps.some((app) => app.label === 'kitchen' && app.state === 'on');
  water = await createProduct(context, { name: `E2E Water ${RUN}`, sku: `E2E-POS-W-${RUN}`, price: 110, tax_category_key: 'restaurant.drink' });
  shirt = await createProduct(context, { name: `E2E Shirt ${RUN}`, sku: `E2E-POS-S-${RUN}`, price: 1210, tax_category_key: 'product.generic' });
  juice = await createProduct(context, { name: `E2E Juice ${RUN}`, sku: `E2E-POS-J-${RUN}`, price: 250, tax_category_key: 'restaurant.drink' });
  cake = await createProduct(context, { name: `E2E Cake ${RUN}`, sku: `E2E-POS-C-${RUN}`, price: 400, tax_category_key: 'restaurant.drink' });
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

  const sale = await newestSaleOf(context, shirt.sku);
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

  const sale = await newestSaleOf(context, water.sku);
  expect((({ total, customer_id, customer_name }) => ({ total, customer_id, customer_name }))(sale)).toEqual({
    total: 110,
    customer_id: customer.id,
    customer_name: customer.name,
  });
  expect(sale.lines[0].tax_rate).toBe('10.00');
  expect(sale.payments.map((p) => p.method_type)).toEqual(['card']);
});

test('SALE-F22: a marked line is charged on its own with its ticket, and the rest closes the check', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addBySearch(page, juice);
  await expect(lineOf(page, juice.name)).toBeVisible();
  await addBySearch(page, cake);
  await expect(lineOf(page, cake.name)).toBeVisible();
  await lineOf(page, juice.name).locator('[data-testid$=-mark]').click();

  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('[data-testid=sale-checkout-partial]')).toContainText(/6[.,]50/);
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toContainText(/2[.,]50/);
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.card}]`).click();
  await page.screenshot({ path: shot('sale-checkout-partial-1280') });
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();

  // The part's own ticket opens too; behind it, the check stays open with what is left.
  const documentModal = page.locator('[data-testid=sale-document-modal]');
  await expect(documentModal.locator('[data-testid=sale-receipt]')).toContainText(/2[.,]50/);
  await documentModal.locator('[data-testid=sale-document-close]').click();
  await expect(documentModal).toBeHidden();
  await expect(lineOf(page, cake.name)).toBeVisible();
  await expect(lineOf(page, juice.name)).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/4[.,]00/);
  const part = await newestSaleOf(context, juice.sku);
  expect([part.total, part.lines.map((line) => line.sku)]).toEqual([250, [juice.sku]]);

  // The rest closes the check: its ticket, and the till starts afresh.
  await shown(page).locator('[data-testid=pos-charge]').click();
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toContainText(/4[.,]00/);
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.card}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  await expect(documentModal.locator('[data-testid=sale-receipt]')).toContainText(/4[.,]00/);
  await documentModal.locator('[data-testid=sale-document-close]').click();
  await expect(shown(page).locator('[data-testid=pos-cart-empty]')).toBeVisible();
  const rest = await newestSaleOf(context, cake.sku);
  expect([rest.total, rest.lines.map((line) => line.sku)]).toEqual([400, [cake.sku]]);
});

test('full screen: the whole page goes full screen and the checkout sheet opens and charges on top', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await shown(page).locator('[data-testid=pos-screen-menu]').click();
  await shown(page).locator('[data-testid=pos-fullscreen]').click();
  // The page itself, not a piece of it: the sheets live in the app's root, outside the till.
  await expect.poll(() => page.evaluate(() => document.fullscreenElement === document.documentElement)).toBe(true);
  try {
    await addBySearch(page, water);
    await shown(page).locator('[data-testid=pos-charge]').click();
    const sheet = page.locator('[data-testid=sale-checkout-modal]');
    await expect(sheet).toBeVisible();
    await sheet.locator(`[data-testid=sale-checkout-method-${methods.card}]`).click();
    await page.screenshot({ path: shot('sale-pos-fullscreen-checkout') });
    // Playwright clicks only what is on top at that point: the sheet is above the full-screen page.
    await sheet.locator('[data-testid=sale-checkout-confirm]').click();
    await expect(sheet).toBeHidden();
    await expect(page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]')).toBeVisible();
    expect((await newestSaleOf(context, water.sku)).total).toBe(110);
  } finally {
    await page.evaluate(() => (document.fullscreenElement ? document.exitFullscreen() : undefined));
  }
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
  // Announced as unavailable in the browser too (an ion-item drops a hand-set aria-disabled).
  await expect(result).toHaveAttribute('aria-disabled', 'true');
  // It still takes the tap (to say why), so the mouse clicks it as a finger would.
  await result.click({ force: true });
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
  expect((await newestSaleOf(context, water.sku)).total).toBe(110);
});

test('the employee charges at the till and sees «Void» and «Refund» on their sale, but never reads the figures', async ({ browser }) => {
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
    // Since FIX-SALE-VOID-REFUND-ASKS-NO-APPROVAL (hub#250) the cashier sees «Void» and «Refund»: either asks a
    // manager's approval, which sale-approval.spec.ts walks end to end.
    const sold = await newestSaleOf(context, water.sku);
    await expect(shown(page).locator(`[data-testid=sales-table-row-${sold.id}-void]`).first()).toBeVisible();
    await expect(shown(page).locator(`[data-testid=sales-table-row-${sold.id}-refund]`).first()).toBeVisible();
    await page.screenshot({ path: shot('sale-sales-employee') });
  } finally {
    await context.close();
  }
});


test('a check opened by its address (/sale/pos?order=<id>, as the agenda’s «Charge» does) is on the till', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  const opened = await api<{ id: string }>(context, A, 'POST', '/sale/orders', { label: `e2e link ${RUN}`, lines: [{ product_id: juice.id }] });
  expect(opened.status).toBe(201);
  await page.goto(`${A}/sale/pos?order=${opened.data.id}`);
  await tillReady(page);
  await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(`e2e link ${RUN}`);
  await expect(lineOf(page, juice.name)).toBeVisible();
  await expect(page).toHaveURL(/\/sale\/pos$/);

  // One no longer open is said, and the till carries on with the one it had.
  const voided = await api<{ id: string }>(context, A, 'POST', '/sale/orders', { label: `e2e gone ${RUN}`, lines: [{ product_id: cake.id }] });
  expect((await api(context, A, 'POST', '/sale/orders/void', { order_id: voided.data.id })).status).toBe(200);
  await page.goto(`${A}/sale/pos?order=${voided.data.id}`);
  await tillReady(page);
  await expect(page.locator('ion-toast')).toContainText(/not open any more|ya no está abierta/);
  await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(`e2e link ${RUN}`);
  // The check opened by its address goes, as every other this file opened (afterAll).
  expect((await api(context, A, 'POST', '/sale/orders/void', { order_id: opened.data.id })).status).toBe(200);
});
