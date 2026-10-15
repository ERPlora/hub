// Cash only with the drawer open, in Chrome (SALE-F08, CASH_REGISTER-F04; apps/sale/WORKBOOK.md): with Cash
// register on and no session open, the till charges a card as ever, but refuses cash INSIDE the charge sheet
// — «The cash register is closed…» — with «Open a cash session», which goes to Cash register; the check
// stays on the till. With a session open (set up through Cash register's API) the same cash charges.
// What this file creates (its sales, its products, the session it opened) is deleted after it, and the
// cash register's setting goes back as it was.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { cleanSales, newestSaleOf, stamp } from './sale-helpers';

const RUN = stamp();
let coffee: Product;
let methods: Record<string, string>;
let wasOn = true;
/** The cash sessions this run opened (deleted after). */
const sessions: string[] = [];

interface Current {
  required: boolean;
  session: { id: string } | null;
}

test.beforeAll(async ({ browser }) => {
  // A card charge issues its ticket (F2) when the hub has an issuer: the cleanup gives its number back.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  const settings = await api<{ enable_cash_register: boolean }>(context, A, 'GET', '/cash_register/settings');
  wasOn = settings.data.enable_cash_register;
  if (!wasOn) expect((await api(context, A, 'POST', '/cash_register/settings', { enable_cash_register: true })).status).toBe(200);
  const current = await api<Current>(context, A, 'GET', '/cash_register/sessions/current');
  expect(current.data.session, 'no cash session open in the hub before this spec (another run left one?)').toBeNull();
  coffee = await createProduct(context, { name: `E2E Coffee ${RUN}`, sku: `E2E-GATE-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  const list = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  methods = Object.fromEntries(list.data.rows.map((row) => [row.type, row.id]));
  await context.close();
});

test.afterAll(() => {
  if (sessions.length) {
    const ids = sessions.map((id) => `'${id}'`).join(',');
    psql(`delete from cash_register_count where session_id in (${ids})`);
    psql(`delete from cash_register_movement where session_id in (${ids})`);
    psql(`delete from cash_register_session where id in (${ids})`);
  }
  if (!wasOn) psql('update cash_register_settings set enable_cash_register = false');
  cleanSales();
  cleanInventory();
});

const coffeeLine = (page: Page) => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: coffee.name }).first();

/** The till with a check of one coffee (a new one: the till starts empty). */
async function tillWithCoffee(page: Page): Promise<void> {
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-cart-empty]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(coffee.sku);
  await search.locator(`[data-testid=pos-search-${coffee.id}]`).click();
  await expect(coffeeLine(page)).toBeVisible();
}

async function chargeInCash(page: Page) {
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.cash}]`).click();
  await sheet.locator('[data-testid=sale-checkout-keypad-5]').click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  return sheet;
}

test('SALE-F08: with the drawer closed, cash is refused in the sheet and «Open a cash session» goes to Cash register', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await tillWithCoffee(page);
  const sheet = await chargeInCash(page);
  await expect(sheet.locator('[data-testid=sale-checkout-error]')).toHaveText(
    /The cash register is closed: open a cash session to charge in cash\.|La caja está cerrada: abre una sesión de caja para cobrar en efectivo\./,
  );
  await expect(sheet.locator('[data-testid=sale-checkout-open-drawer]')).toBeVisible();
  await page.screenshot({ path: shot('sale-cash-gate-1280') });
  // Nothing was charged.
  await expect(newestSaleOf(context, coffee.sku)).rejects.toThrow(/no recent sale/);

  // A card charges as ever, with the drawer closed.
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.card}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  expect((await newestSaleOf(context, coffee.sku)).payments.map((p) => p.method_type)).toEqual(['card']);
});

test('SALE-F08: «Open a cash session» leads to Cash register; with a session open, the same cash charges', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await tillWithCoffee(page);
  const sheet = await chargeInCash(page);
  await sheet.locator('[data-testid=sale-checkout-open-drawer]').click();
  await expect(sheet).toBeHidden();
  await expect(page).toHaveURL(/\/cash_register\/sessions$/);

  const opened = await api<{ id: string }>(context, A, 'POST', '/cash_register/sessions/open', { opening_balance: 10000 });
  expect(opened.status).toBe(201);
  sessions.push(opened.data.id);

  // Back on the till, the check is still there, as it was, and cash charges now.
  await login(page, A, '/sale/pos');
  await expect(coffeeLine(page)).toBeVisible();
  const again = await chargeInCash(page);
  await expect(again).toBeHidden();
  const sale = await newestSaleOf(context, coffee.sku);
  expect(sale.payments.map((p) => [p.method_type, p.amount, p.tendered, p.change])).toEqual([['cash', 150, 500, 350]]);
});
