// flow: SALE-F42 — the options of a dish picked in a menu, in Chrome, against the real Inventory, Taxes, Menus,
// Modifiers, Sales and Kitchen apps: the steak asks its doneness (required) and its extras right under it in the menu's
// sheet, the button names the group still short and a tap rings it; with the doneness and the cheese chosen the button
// adds the cheese to the menu; the check names the steak with its options; sent to the kitchen, the steak carries them
// by their kitchen names; charged by card, the receipt names them with the steak and charges what the sheet said. The
// sheet with the options open, the check and the receipt in 375×667, 820×1180 and 1440×900.
// What a run makes — products `E2E-CDO-<run>-…`, its menu «e2e DishOpt …», its groups of Modifiers, checks, sales and
// kitchen tickets — goes.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, login, psql, saveSessionForTheSweep, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { chargeByCard } from './sale-charge-helpers';
import { cleanSales, drawerOff, openTillCart, restoreDrawer, stamp } from './sale-helpers';
import { toastSaying } from './toast-helpers';

const RUN = stamp();
const SKU = `E2E-CDO-${RUN}`;
const MENU = `e2e DishOpt Menu ${RUN}`;
const DONENESS = `e2e DishOpt Doneness ${RUN}`;
const EXTRAS = `e2e DishOpt Extras ${RUN}`;
const FOOD = 'restaurant.food';
const SIZES = [
  { label: '375x667', width: 375, height: 667 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1440x900', width: 1440, height: 900 },
];

const products: Record<string, Product> = {};
let menuId = '';
let card = '';

function cleanRun(): void {
  const lines = `select id from sale_orderline where name like 'e2e DishOpt %'`;
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (${lines})`;
  const combos = "select id from combo_combo where name like 'e2e DishOpt %'";
  const groups = "select id from modifier_modifiergroup where name like 'e2e DishOpt %'";
  psql(
    [
      `create temp table e2e_cdo_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_cdo_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_cdo_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_cdo_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_cdo_tickets)',
      `delete from combo_choiceoption where group_id in (select id from combo_choicegroup where combo_id in (${combos}))`,
      `delete from combo_choicegroup where combo_id in (${combos})`,
      `delete from combo_combo where id in (${combos})`,
      `delete from modifier_modifierlink where group_id in (${groups})`,
      `delete from modifier_modifieroption where group_id in (${groups})`,
      `delete from modifier_modifiergroup where id in (${groups})`,
    ].join('; '),
  );
}

async function post<T>(context: BrowserContext, path: string, body: unknown, status = 201): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

/** The screen in the three sizes, each once `ready` says it painted; back to 1440×900 after. */
async function shots(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await untilStill(page);
    await expect.poll(() => horizontalOverflow(page), { message: `no horizontal scroll at ${key} ${size.label}` }).toBeLessThanOrEqual(0);
    await capture(page, `SALE-F42-${key}-${size.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** The choices of the menu on offer, by product code. */
async function offer(context: BrowserContext): Promise<Record<string, string>> {
  type ForSale = { rows: { id: string; groups: { options: { id: string; product_id: string }[] }[] }[] };
  const res = await api<ForSale>(context, A, 'GET', '/combo/combos/for_sale?limit=50');
  const row = res.data.rows.find((r) => r.id === menuId);
  expect(row, 'the menu is on sale').toBeTruthy();
  const byProduct = Object.fromEntries(row!.groups.flatMap((g) => g.options).map((o) => [o.product_id, o.id]));
  return Object.fromEntries(Object.entries(products).map(([code, p]) => [code, byProduct[p.id]]));
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  cleanRun();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await drawerOff(context);
  for (const [code, name, price] of [
    ['LEN', 'Lentils', 500],
    ['STK', 'Steak', 1800],
  ] as const) {
    products[code] = await createProduct(context, { name: `E2E DishOpt ${name} ${RUN}`, sku: `${SKU}-${code}`, price, tax_category_key: FOOD, initial_stock: '10' });
  }
  menuId = (await post<{ id: string }>(context, '/combo/combos', { name: MENU, kitchen_name: `MENU ${RUN}`, price: 1350, tax_category_key: FOOD })).id;
  for (const course of ['Starters', 'Mains']) await post(context, '/combo/groups', { combo: MENU, name: course });
  await post(context, '/combo/options', { combo: MENU, group: 'Starters', product: `${SKU}-LEN` });
  await post(context, '/combo/options', { combo: MENU, group: 'Mains', product: `${SKU}-STK`, price_delta: 200 });
  await post(context, '/modifier/groups', { name: DONENESS, min_choices: 1, max_choices: 1 });
  await post(context, '/modifier/groups', { name: EXTRAS, max_choices: 2 });
  await post(context, '/modifier/options', { group: DONENESS, name: 'Rare', kitchen_name: 'RARE' });
  await post(context, '/modifier/options', { group: DONENESS, name: 'Well done', kitchen_name: 'WELL DONE' });
  await post(context, '/modifier/options', { group: EXTRAS, name: 'Cheese', kitchen_name: '+CHEESE', price_delta: 100 });
  for (const group of [DONENESS, EXTRAS]) await post(context, '/modifier/links/attach', { group, product_id: products.STK.id });
  const methods = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  card = methods.data.rows.find((row) => row.type === 'card')?.id ?? '';
  expect(card, 'a card method').not.toBe('');
  await context.close();
});

test.afterAll(() => {
  cleanRun();
  cleanSales();
  cleanInventory();
  restoreDrawer();
});

test('SALE-F42: the steak of a menu asks its doneness, goes to the kitchen with it and is charged with its cheese', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await saveSessionForTheSweep(context);
  await shown(page).locator(`[data-testid=pos-menu-${menuId}]`).waitFor({ state: 'visible' });
  const picks = await offer(context);
  await shown(page).locator(`[data-testid=pos-menu-${menuId}]`).click();
  const sheet = page.locator('ion-modal[data-testid=pos-menu]');
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.LEN}]`).click();
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.STK}]`).click();
  const options = sheet.locator(`[data-testid=pos-menu-dish-options-${picks.STK}]`);
  await expect(options).toContainText(DONENESS);
  const add = sheet.locator('[data-testid=pos-menu-add]');
  await expect(add).toContainText(`Choose 1 in «${DONENESS}»`);
  await add.click();
  await expect(options.locator('.pos-options__group--missing')).toContainText(DONENESS);
  await options.getByRole('button', { name: 'Rare' }).click();
  await options.getByRole('button', { name: /Cheese/ }).click();
  // 13,50 + 2,00 (steak) + 1,00 (cheese).
  await expect(add).toContainText(/16[.,]50/);
  await shots(page, 'SHEET', async () => {
    await options.scrollIntoViewIfNeeded();
    await expect(add).toBeVisible();
  });
  await add.click();
  await expect(sheet).toBeHidden();

  const line = shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: MENU }).first();
  await expect(line).toContainText(`${products.STK.name} (Rare, Cheese)`);
  await expect(line).toContainText(/16[.,]50/);
  await shots(page, 'CHECK', async () => {
    await openTillCart(page);
    await expect(line).toBeVisible();
  });

  await shown(page).locator('[data-testid=pos-cart-tab-round]').click();
  await shown(page).locator('[data-testid=pos-kitchen-send]').click();
  await expect(toastSaying(page, /Order \d+ sent to the kitchen\./)).toBeVisible();
  type Board = { cooking: { items: { name: string; menu_name: string; modifiers: string[] }[] }[] };
  const board = await api<Board>(context, A, 'GET', '/kitchen/board');
  const steak = board.data.cooking.flatMap((t) => t.items).find((item) => item.menu_name === `MENU ${RUN}` && item.name === products.STK.name);
  expect(steak?.modifiers).toEqual(['RARE', '+CHEESE']);

  await shown(page).locator('[data-testid=pos-cart-tab-check]').click();
  const receipt = await chargeByCard(page, card);
  await expect(receipt.locator('[data-testid=sale-receipt-line]').filter({ hasText: MENU })).toContainText(/16[.,]50/);
  await expect(receipt.locator('[data-testid=sale-receipt-dish]')).toHaveText([products.LEN.name, `${products.STK.name} (Rare, Cheese)`]);
  await shots(page, 'RECEIPT', async () => {
    await expect(receipt).toBeVisible();
  });
});
