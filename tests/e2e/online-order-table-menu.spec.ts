// The table's menu of Online orders, end to end in a browser: a customer without a session opens the page its table's
// QR carries, on a phone first, and reads the menu with the table and its zone above it, the run's dish under its
// category with its description, allergens and price, and the dish's sheet; once the owner regenerates that table's
// QR, the old address says the QR is no longer active and nothing of the business. The run's dish, category, zone and
// table are deleted after it.
// flow: ONLINE_ORDER-F03

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown, turnOffTurnedOn, turnOnMissing, untilStill } from './helpers';
import { createProduct } from './inventory-helpers';
import { stamp } from './sale-helpers';

const RUN = stamp();
const ZONE = `e2e Menu ${RUN}`;
const CATEGORY = `e2e Starters ${RUN}`;
const DISH = `e2e Croquettes ${RUN}`;
const SIZES = [
  { label: 'phone', width: 375, height: 667 },
  { label: 'tablet', width: 820, height: 1180 },
  { label: 'desktop', width: 1440, height: 900 },
] as const;

let owner: BrowserContext;
let visitor: BrowserContext;
let page: Page;
const turnedOn: string[] = [];
let zoneId = '';
let tableId = '';
let categoryId = '';
let productId = '';

async function regenerate(): Promise<string> {
  const made = await api<{ code: string }>(owner, A, 'POST', '/online_order/qr_codes/regenerate', { id: tableId });
  expect(made.status, JSON.stringify(made.data)).toBe(200);
  return made.data.code;
}

test.beforeAll(async ({ browser }) => {
  owner = await browser.newContext({ viewport: SIZES[2] });
  await login(await owner.newPage(), A, '/');
  await turnOnMissing(owner, A, ['online_order'], turnedOn);
  const zone = await api<{ id: string }>(owner, A, 'POST', '/table/zones', { name: ZONE });
  expect(zone.status, JSON.stringify(zone.data)).toBe(201);
  zoneId = zone.data.id;
  const table = await api<{ id: string }>(owner, A, 'POST', '/table/tables', { zone_id: zoneId, number: '903' });
  expect(table.status, JSON.stringify(table.data)).toBe(201);
  tableId = table.data.id;
  const category = await api<{ id: string }>(owner, A, 'POST', '/inventory/categories', { name: CATEGORY });
  expect(category.status, JSON.stringify(category.data)).toBe(201);
  categoryId = category.data.id;
  productId = (
    await createProduct(owner, {
      name: DISH,
      sku: `E2E-MENU-${RUN}`,
      price: 750,
      description: 'Six, of ham',
      allergens: ['gluten', 'milk'],
      category_ids: [categoryId],
    })
  ).id;
  const photo = await api(owner, A, 'POST', '/inventory/products/image', { id: productId, image: 'catalog:hospitality/cafe_con_leche' });
  expect(photo.status, JSON.stringify(photo.data)).toBe(200);
  // A customer's phone: no session of the business.
  visitor = await browser.newContext({ viewport: SIZES[0] });
  page = await visitor.newPage();
});

test.afterAll(async () => {
  try {
    if (tableId) psql(`delete from online_order_tablecode where table_id = '${tableId}'`);
    if (productId) await api(owner, A, 'POST', '/inventory/products/delete', { id: productId });
    if (categoryId) await api(owner, A, 'POST', '/inventory/categories/delete', { id: categoryId });
    if (tableId) await api(owner, A, 'POST', '/table/tables/delete', { id: tableId });
    if (zoneId) await api(owner, A, 'POST', '/table/zones/delete', { id: zoneId });
  } finally {
    await turnOffTurnedOn(owner, A, turnedOn);
    await visitor.close();
    await owner.close();
  }
});

test('ONLINE_ORDER-F03: the table’s QR opens its menu on a phone; a regenerated QR no longer does', async () => {
  const code = await regenerate();
  await page.goto(`${A}/p/a/order/${code}`);
  const view = shown(page);
  await expect(view.locator('[data-testid=oo-menu-table]')).toHaveText(`Table 903 · ${ZONE}`);
  const dish = view.locator(`[data-testid=oo-menu-dish-${productId}]`);
  await expect(dish).toContainText(DISH);
  await expect(dish).toContainText('Six, of ham');
  await expect(dish).toContainText('Allergens: Gluten, Milk');
  await expect(dish).toContainText('€7.50');
  // Its photo, served to a phone without a session.
  await expect.poll(() => dish.locator('img').evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  const group = view.locator('[data-testid=oo-menu-group]', { has: page.locator(`[data-testid=oo-menu-dish-${productId}]`) });
  await expect(group.locator('ion-list-header')).toHaveText(CATEGORY);

  for (const size of SIZES) {
    await page.setViewportSize(size);
    await dish.scrollIntoViewIfNeeded();
    await untilStill(page);
    await capture(page, `ONLINE-ORDER-TABLE-MENU-${size.label}`);
  }
  await page.setViewportSize(SIZES[0]);

  // The dish's sheet: what it is again, and its options when it has any (none here).
  await dish.click();
  const sheet = page.locator('[data-testid=oo-menu-sheet]').last();
  await expect(sheet).toContainText(DISH);
  await expect(sheet).toContainText('€7.50');
  await untilStill(page);
  await capture(page, 'ONLINE-ORDER-TABLE-MENU-dish-phone');
  await page.locator('[data-testid=oo-menu-sheet-done]').last().click();

  // The owner regenerates the table's QR: the printed one, the old address, opens nothing of the business.
  await regenerate();
  await page.goto(`${A}/p/a/order/${code}`);
  const gone = shown(page).locator('[data-testid=oo-menu-not-active]');
  await expect(gone).toContainText('This QR is no longer active');
  await expect(shown(page)).not.toContainText(DISH);
  await expect(shown(page)).not.toContainText(ZONE);
  await untilStill(page);
  await capture(page, 'ONLINE-ORDER-TABLE-MENU-not-active-phone');
});
