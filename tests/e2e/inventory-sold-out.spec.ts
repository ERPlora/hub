// flow: INVENTORY-F29, INVENTORY-F27 — an article marked sold out («86») in Inventory leaves the till
// (apps/inventory/WORKBOOK.md; the old QA flow qa:modules/sales/sold-out-item-86), against the real
// Sales and Taxes apps, no doubles:
//   - «Mark sold out» in the row's menu: the «Sold out» mark beside the switch, which stays on, and the
//     till open in another tab stops offering it without a reload (its grid and its search), while the
//     article next to it is still there; «Put back on sale» brings it back the same way;
//   - the product sheet marks and unmarks it too, and says so beside its status;
//   - a menu whose only starter is sold out leaves the till too (COMBO-F06), its editor says «Sold out in
//     Inventory» on that choice, and the menu comes back with it;
//   - screenshots of Products with the mark and of the menu's editor at 390, 834 and 1440.
// What this file creates is deleted after it; the cash register goes back as it was.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import {
  cleanInventory,
  createProduct,
  dialog,
  type Product,
  productBySku,
  productRow,
  productsReady,
  rowAction,
  searchProducts,
  stamp,
} from './inventory-helpers';
import { drawerOff, restoreDrawer } from './sale-helpers';

const RUN = stamp();
let croquettes: Product;
let bread: Product;
let flan: Product;
/** A menu whose only starter is the flan: sold out, nothing completes it. */
let menu: { id: string; optionId: string };
const MENU_TAG = 'e2e 86';

/** The widths of this task's screenshots, as the SaaS panel's `VIEWPORTS`. */
const SHOTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/inventory/products');
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  croquettes = await createProduct(context, { name: `E2E Croquettes ${RUN}`, sku: `E2E-86-C-${RUN}`, price: 650 });
  bread = await createProduct(context, { name: `E2E Bread ${RUN}`, sku: `E2E-86-B-${RUN}`, price: 120 });
  flan = await createProduct(context, { name: `E2E Flan ${RUN}`, sku: `E2E-86-F-${RUN}`, price: 300 });
  const combo = await api<{ id: string }>(context, A, 'POST', '/combo/combos', { name: `${MENU_TAG} Menu ${RUN}`, price: 1200, tax_category_key: 'product.generic' });
  expect(combo.status, 'menu').toBe(201);
  const course = await api<{ id: string }>(context, A, 'POST', '/combo/groups', { combo_id: combo.data.id, name: 'Dessert' });
  expect(course.status, 'course').toBe(201);
  const choice = await api<{ id: string }>(context, A, 'POST', '/combo/options', { group_id: course.data.id, product_id: flan.id });
  expect(choice.status, 'choice').toBe(201);
  menu = { id: combo.data.id, optionId: choice.data.id };
  await context.close();
});

test.afterAll(() => {
  // The menu points at the flan: it goes first.
  const combos = `select id from combo_combo where name like '${MENU_TAG} %'`;
  psql(
    [
      `delete from combo_choiceoption where group_id in (select id from combo_choicegroup where combo_id in (${combos}))`,
      `delete from combo_choicegroup where combo_id in (${combos})`,
      `delete from combo_combo where name like '${MENU_TAG} %'`,
    ].join('; '),
  );
  cleanInventory();
  restoreDrawer();
});

const tile = (page: Page, product: Product): Locator => shown(page).locator(`[data-testid=pos-product-${product.id}]`);

/** The till on «All»: the article that stays on sale is in its grid. */
async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await tile(page, bread).waitFor({ state: 'attached' });
}

/** What the till's magnifier finds for this run's SKUs. */
async function searchTill(page: Page): Promise<Locator> {
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(`E2E-86-`);
  await expect(search.locator(`[data-testid=pos-search-${bread.id}]`)).toBeVisible();
  return search;
}

const soldOutMark = (page: Page, product: Product): Locator =>
  shown(page).locator(`[data-testid=inventory-products-sold-out-${product.id}]`);

test('INVENTORY-F29 / INVENTORY-F27: «Mark sold out» takes the article off the till live; «Put back on sale» brings it back', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const till = page;
  await tillReady(till);
  await expect(tile(till, croquettes)).toHaveCount(1);

  // The manager, in another tab of the same session, marks it sold out from the row's menu.
  const office = await context.newPage();
  await office.setViewportSize({ width: 1440, height: 900 });
  await office.goto(`${A}/inventory/products`);
  await productsReady(office);
  await searchProducts(office, croquettes.sku);
  await expect(productRow(office, croquettes.sku)).toBeVisible();
  await expect(soldOutMark(office, croquettes)).toHaveCount(0);
  await rowAction(office, croquettes.id, 'sold_out');
  await expect(soldOutMark(office, croquettes)).toHaveText(/^(Sold out|Agotado)$/);
  // Sold out is not inactive: its switch stays on.
  await expect(office.locator(`[data-testid=inventory-products-active-${croquettes.id}]`).first()).toHaveJSProperty('checked', true);
  expect((await productBySku(context, croquettes.sku)).is_sold_out).toBe(true);

  for (const size of SHOTS) {
    await office.setViewportSize({ width: size.width, height: size.height });
    await office.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(soldOutMark(office, croquettes)).toBeVisible();
    await office.screenshot({ path: shot(`FIX-INVENTORY-SOLD-OUT-86-${size.label}`) });
  }
  await office.setViewportSize({ width: 1440, height: 900 });

  // The till, open all along, stops offering it without a reload: neither its grid nor its search.
  await till.bringToFront();
  await expect(tile(till, croquettes)).toHaveCount(0);
  await expect(tile(till, bread)).toHaveCount(1);
  const search = await searchTill(till);
  await expect(search.locator(`[data-testid=pos-search-${croquettes.id}]`)).toHaveCount(0);
  await search.locator('[data-testid=pos-search-close]').click();
  await expect(search).toBeHidden();
  await till.screenshot({ path: shot('inventory-sold-out-till-1440') });

  // Back on sale: the mark goes and the till offers it again, live.
  await office.bringToFront();
  await rowAction(office, croquettes.id, 'back_on_sale');
  await expect(soldOutMark(office, croquettes)).toHaveCount(0);
  expect((await productBySku(context, croquettes.sku)).is_sold_out).toBe(false);
  await till.bringToFront();
  await expect(tile(till, croquettes)).toHaveCount(1);
  const again = await searchTill(till);
  await expect(again.locator(`[data-testid=pos-search-${croquettes.id}]`)).toBeVisible();
});

test('INVENTORY-F29: the product sheet marks it sold out, says so beside its status and puts it back on sale', async ({ page, context }) => {
  await page.setViewportSize({ width: 834, height: 1112 });
  await login(page, A, '/inventory/products');
  await productsReady(page);
  await searchProducts(page, bread.sku);
  await expect(productRow(page, bread.sku)).toBeVisible();
  await rowAction(page, bread.id, 'detail');
  const sheet = dialog(page, 'inventory-product-detail');
  await expect(sheet).toBeVisible();
  const status = sheet.locator('[data-testid=inventory-product-detail-status] ion-note');
  await expect(status).toHaveText(/^(Yes|Sí)$/);

  await sheet.locator('[data-testid=inventory-product-detail-sold-out]').click();
  await expect(status).toHaveText(/^(Yes · Sold out|Sí · Agotado)$/);
  await expect(sheet.locator('[data-testid=inventory-product-detail-back-on-sale]')).toBeVisible();
  expect((await productBySku(context, bread.sku)).is_sold_out).toBe(true);
  await page.screenshot({ path: shot('inventory-sold-out-sheet-834') });

  await sheet.locator('[data-testid=inventory-product-detail-back-on-sale]').click();
  await expect(status).toHaveText(/^(Yes|Sí)$/);
  await expect(sheet.locator('[data-testid=inventory-product-detail-sold-out]')).toBeVisible();
  expect((await productBySku(context, bread.sku)).is_sold_out).toBe(false);
});

test('INVENTORY-F29 / COMBO-F06: a menu whose only dessert is sold out leaves the till; its editor says why; it comes back', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  const tileOfMenu = shown(page).locator(`[data-testid=pos-menu-${menu.id}]`);
  await expect(tileOfMenu).toHaveCount(1);

  const sold = await api<Product>(context, A, 'POST', '/inventory/products/sold_out', { id: flan.id, sold_out: true });
  expect([sold.status, sold.data.is_sold_out]).toEqual([200, true]);
  // Live, without a reload: the flan and the menu it completes leave the till; the bread stays.
  await expect(tile(page, flan)).toHaveCount(0);
  await expect(tileOfMenu).toHaveCount(0);
  await expect(tile(page, bread)).toHaveCount(1);

  // The menu's editor says which choice and why, as a warning: it comes back.
  const editor = await context.newPage();
  await editor.goto(`${A}/combo/menus/${menu.id}`);
  const status = shown(editor).locator(`[data-testid=combo-choice-${menu.optionId}-status]`);
  await expect(status).toHaveText(/^(Sold out in Inventory|Agotado en Inventario)$/);
  for (const size of SHOTS) {
    await editor.setViewportSize({ width: size.width, height: size.height });
    await editor.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(status).toBeVisible();
    await editor.screenshot({ path: shot(`FIX-INVENTORY-SOLD-OUT-86-menu-${size.label}`) });
  }

  const back = await api<Product>(context, A, 'POST', '/inventory/products/sold_out', { id: flan.id, sold_out: false });
  expect([back.status, back.data.is_sold_out]).toEqual([200, false]);
  await expect(status).toHaveCount(0);
  await page.bringToFront();
  await expect(tileOfMenu).toHaveCount(1);
  await expect(tile(page, flan)).toHaveCount(1);
});
