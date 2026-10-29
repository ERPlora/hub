// flow: COMBO-F07, COMBO-F08, COMBO-F09, COMBO-F10, COMBO-F11 — a menu of Menus sold in the till of Sales, in
// Chrome, against the real Inventory, Taxes, Sales and Kitchen apps (apps/combo/WORKBOOK.md): «All» offers the menu
// first with its «Menu» badge; its sheet shows every course with a dish on offer (a sold-out dessert, and its
// optional course, are left out), the supplements with their sign and the reason the button cannot add yet; two
// coffees, two supplements; charged by card at the closed price plus every supplement, with its dishes on the
// receipt (F07, F08). A pack to take away is split per dish on the receipt, 6,00 → 4,15 at 10 % and 1,85 at 21 %
// (F09). The worker's outbox relay — run here as each tick runs it: the e2e stack runs no worker — lowers each
// dish's stock and never the menu's (F10). A menu sent from «Current order» reaches the kitchen dish by dish,
// under the menu's kitchen name, and the kitchen display shows them under the menu's header (F11; the fire through
// the relay is apps/combo/tests/test_relay.py). Each screen in 390×844, 834×1112 and 1440×900 (`APP-COMBO-COMBO-Fnn-<w>`).
// SALE-F12: in a course of 1 to 4 whose dishes repeat, the rule says both and two dishes taken twice keep each name
// on its line beside its counter and its minus, in the three sizes (`FIX-SALE-MENU-SHEET-REPEATABLE-CHOICE-NAME-BREAKS-<w>`).
// What a run makes — products `E2E-CMT-<run>-…`, its menus and service «e2e Combo …», checks, sales and kitchen
// tickets — goes.
import { spawnSync } from 'node:child_process';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, HUB_DIR, login, psql, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const RUN = stamp();
const SKU = `E2E-CMT-${RUN}`;
const MENU = `e2e Combo Menu ${RUN}`;
const PACK = `e2e Combo Pack ${RUN}`;
const SERVICE = `e2e Combo Service ${RUN}`;
const FOOD = 'restaurant.food';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

interface ForSale {
  rows: { id: string; name: string; groups: { id: string; name: string; options: { id: string; product_id: string; price_delta: number }[] }[] }[];
}

const products: Record<string, Product> = {};
let menuId = '';
let packId = '';
let card = '';

/** The kitchen tickets of this run's checks (they name the check's lines: before the sales), its menus and pack. */
function cleanRun(): void {
  const lines = `select id from sale_orderline where sku like 'E2E-CMT-%' or name like 'e2e Combo %'`;
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (${lines})`;
  const combos = "select id from combo_combo where name like 'e2e Combo %'";
  psql(
    [
      `create temp table e2e_cmt_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_cmt_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_cmt_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_cmt_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_cmt_tickets)',
      `delete from combo_choiceoption where group_id in (select id from combo_choicegroup where combo_id in (${combos}))`,
      `delete from combo_choicegroup where combo_id in (${combos})`,
      `delete from combo_combo where id in (${combos})`,
      "delete from service_service where name like 'e2e Combo %'",
    ].join('; '),
  );
}

/** The outbox relay as the worker runs it on every tick, pass after pass until one finds nothing to do. */
function relayPass(): void {
  const code = [
    'from django.utils import timezone',
    'from base import relay',
    'for _ in range(200):',
    '    done = relay.run(timezone.now())',
    '    if not (done.taken or done.delivered): break',
  ].join('\n');
  const out = spawnSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', code], { cwd: HUB_DIR, env: process.env, encoding: 'utf8' });
  expect(out.status, `relay pass: ${out.stderr}`).toBe(0);
}

async function post<T>(context: BrowserContext, path: string, body: unknown, status = 201): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

const stock = (code: string): string => psql(`select stock::numeric(12,0) from inventory_product where sku = '${SKU}-${code}'`);

/** The screen in the three sizes, each once `ready` says it painted; back to 1440×900 after. */
async function shots(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    // A resize slides the phone's cart drawer and the sheets: the picture waits until nothing moves, Ionic's sheets
    // and notices included (they animate in their shadow roots).
    await untilStill(page);
    await expect
      .poll(() => horizontalOverflow(page), { message: `no horizontal scroll at ${key} ${size.label}` })
      .toBeLessThanOrEqual(0);
    await capture(page, `APP-COMBO-${key}-${size.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function till(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator(`[data-testid=pos-menu-${menuId}]`).waitFor({ state: 'visible' });
}

/** The choices of the menu `id` on offer, by product code. */
async function offer(context: BrowserContext, id: string): Promise<Record<string, string>> {
  const res = await api<ForSale>(context, A, 'GET', '/combo/combos/for_sale?limit=50');
  expect(res.status).toBe(200);
  const row = res.data.rows.find((r) => r.id === id);
  expect(row, 'the menu is on sale').toBeTruthy();
  const byProduct = Object.fromEntries(row!.groups.flatMap((g) => g.options).map((o) => [o.product_id, o.id]));
  return Object.fromEntries(Object.entries(products).flatMap(([code, p]) => (byProduct[p.id] ? [[code, byProduct[p.id]]] : [])));
}

const lineOf = (page: Page, name: string) => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: name }).first();

async function chargeByCard(page: Page): Promise<ReturnType<Page['locator']>> {
  await shown(page).locator('[data-testid=pos-charge]').click();
  const checkout = page.locator('[data-testid=sale-checkout-modal]');
  await checkout.locator(`[data-testid=sale-checkout-method-${card}]`).click();
  await checkout.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(checkout).toBeHidden();
  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  return receipt;
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  cleanRun();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await drawerOff(context);
  for (const [code, name, price, tax] of [
    ['LEN', 'Lentils', 500, FOOD],
    ['SAL', 'Salad', 450, FOOD],
    ['HAK', 'Hake', 1400, FOOD],
    ['STK', 'Steak', 1800, FOOD],
    ['FLA', 'Flan', 400, FOOD],
    ['COF', 'Coffee', 150, FOOD],
    ['SAN', 'Sandwich', 450, FOOD],
    // A restaurant's beer: 10 % at the table, 21 % to take away.
    ['BEE', 'Beer', 200, 'restaurant.alcohol'],
  ] as const) {
    products[code] = await createProduct(context, { name: `E2E CmbTill ${name} ${RUN}`, sku: `${SKU}-${code}`, price, tax_category_key: tax, initial_stock: '10' });
  }
  menuId = (await post<{ id: string }>(context, '/combo/combos', { name: MENU, kitchen_name: `MENU ${RUN}`, price: 1350, tax_category_key: FOOD })).id;
  for (const [course, min, max, repeat] of [
    ['Starters', 1, 1, false],
    ['Mains', 1, 1, false],
    ['Dessert', 0, 1, false],
    ['Coffee', 0, 2, true],
  ] as const) {
    await post(context, '/combo/groups', { combo: MENU, name: course, min_choices: min, max_choices: max, allow_repeat: repeat });
  }
  for (const [course, code, delta] of [
    ['Starters', 'LEN', 0],
    ['Starters', 'SAL', 0],
    ['Mains', 'HAK', 0],
    ['Mains', 'STK', 200],
    ['Dessert', 'FLA', 0],
    ['Coffee', 'COF', 50],
  ] as const) {
    const option = await post<{ id: string }>(context, '/combo/options', { combo: MENU, group: course, product: `${SKU}-${code}`, price_delta: delta });
    // COMBO-F12: tonight there is no flan.
    if (code === 'FLA') await post(context, '/combo/options/update', { id: option.id, is_available: false }, 200);
  }
  packId = (await post<{ id: string }>(context, '/combo/combos', { name: PACK, price: 600, supply_kind: 'goods' })).id;
  for (const [course, code] of [
    ['Sandwich', 'SAN'],
    ['Drink', 'BEE'],
  ] as const) {
    await post(context, '/combo/groups', { combo: PACK, name: course });
    await post(context, '/combo/options', { combo: PACK, group: course, product: `${SKU}-${code}` });
  }
  // A service on sale, as any business with Services has (and as other specs leave): «Services» keeps its own grid
  // in the till, hidden while «All» is chosen, and the menus still go first in «All» (COMBO-F07).
  await post(context, '/service/services', { name: SERVICE, price: 1500, duration_minutes: 30, tax_category_key: 'service.generic' });
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

test('COMBO-F07, COMBO-F08: the menu goes first in «All», its sheet asks every course and it is charged with every supplement', async ({ page, context }) => {
  await till(page);
  const tile = shown(page).locator(`[data-testid=pos-menu-${menuId}]`);
  await expect(tile).toContainText(MENU);
  await expect(tile.locator(`[data-testid=pos-menu-${menuId}-badge]`)).toHaveText('Menu');
  // The till opens in «All», and the grid on screen starts with the menus, before any product. «Services» keeps
  // its own grid in the page, hidden, and earlier in it: the order is read in the grid that shows.
  await expect(shown(page).locator('[data-testid=pos-category-all]')).toHaveClass(/segment-button-checked/);
  const grid = shown(page).locator('.pos-grid').filter({ visible: true });
  await expect(grid).toHaveCount(1);
  await expect(grid.locator(':scope > button').first()).toHaveAttribute('data-testid', /^pos-menu-/);
  // Once this run's products are on screen, none of the grid's products goes before this run's menu.
  await expect(grid.locator(`[data-testid=pos-product-${products.LEN.id}]`)).toBeVisible();
  await expect(grid.locator(`xpath=./*[starts-with(@data-testid, 'pos-product-')][following-sibling::*[@data-testid='pos-menu-${menuId}']]`)).toHaveCount(0);
  const picks = await offer(context, menuId);
  // The sold-out flan is not offered, and its optional course, with nothing left on offer, is not either.
  expect(Object.keys(picks).sort()).toEqual(['COF', 'HAK', 'LEN', 'SAL', 'STK']);

  await tile.click();
  const sheet = page.locator('ion-modal[data-testid=pos-menu]');
  await expect(sheet).toBeVisible();
  await expect(sheet).not.toContainText('Dessert');
  await expect(sheet.locator(`[data-testid=pos-menu-dish-${picks.STK}]`)).toContainText('+€2.00');
  const add = sheet.locator('[data-testid=pos-menu-add]');
  await expect(add).toContainText('Choose 1 in «Starters»');
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.LEN}]`).click();
  await expect(add).toContainText('Choose 1 in «Mains»');
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.STK}]`).click();
  // Two coffees: the course takes the same one twice, a third is refused with the reason.
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.COF}]`).click();
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.COF}]`).click();
  await expect(sheet.locator(`[data-testid=pos-menu-dish-count-${picks.COF}]`)).toHaveText('× 2');
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.COF}]`).click();
  await expect(sheet).toContainText('«Coffee» is full: take one out to choose another.');
  // 13,50 + 2,00 (steak) + 2 × 0,50 (coffees).
  await expect(add).toContainText(/16[.,]50/);
  await shots(page, 'COMBO-F07', async () => {
    await expect(add).toBeVisible();
  });
  await add.click();
  await expect(sheet).toBeHidden();
  const line = lineOf(page, MENU);
  await expect(line).toContainText(products.LEN.name);
  await expect(line).toContainText(/16[.,]50/);

  const receipt = await chargeByCard(page);
  await expect(receipt.locator('[data-testid=sale-receipt-line]').filter({ hasText: MENU })).toContainText(/16[.,]50/);
  const dishes = receipt.locator('[data-testid=sale-receipt-dish]');
  await expect(dishes).toHaveCount(3);
  await expect(dishes.nth(0)).toContainText(products.LEN.name);
  await expect(dishes.nth(1)).toContainText(products.STK.name);
  await expect(dishes.nth(2)).toContainText(products.COF.name);
  await shots(page, 'COMBO-F08', async () => {
    await expect(receipt).toBeVisible();
  });
});

test('COMBO-F09: a pack to take away is split per dish on the receipt, each at its VAT, to the cent', async ({ page, context }) => {
  await till(page);
  const picks = await offer(context, packId);
  await shown(page).locator(`[data-testid=pos-menu-${packId}]`).click();
  const sheet = page.locator('ion-modal[data-testid=pos-menu]');
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.SAN}]`).click();
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.BEE}]`).click();
  await expect(sheet.locator('[data-testid=pos-menu-add]')).toContainText(/6[.,]00/);
  await sheet.locator('[data-testid=pos-menu-add]').click();
  await expect(sheet).toBeHidden();

  const receipt = await chargeByCard(page);
  await expect(receipt.locator('[data-testid=sale-receipt-menu-head]')).toHaveText(PACK);
  const lines = receipt.locator('[data-testid=sale-receipt-line]');
  await expect(lines.filter({ hasText: products.SAN.name })).toContainText(/4[.,]15/);
  await expect(lines.filter({ hasText: products.BEE.name })).toContainText(/1[.,]85/);
  // No line of the pack itself carries money: its two dishes are the receipt's lines.
  await expect(lines).toHaveCount(2);
  const totals = receipt.locator('[data-testid=sale-receipt-total-row]');
  await expect(totals.filter({ hasText: '21' })).toHaveCount(1);
  await expect(totals.filter({ hasText: '10' })).toHaveCount(1);
  await shots(page, 'COMBO-F09', async () => {
    await expect(receipt).toBeVisible();
  });
});

test('COMBO-F10: the relay lowers each dish sold, times the picks, and never the menu', async () => {
  expect([stock('LEN'), stock('STK'), stock('COF'), stock('SAN'), stock('BEE')]).toEqual(['10', '10', '10', '10', '10']);
  relayPass();
  // One menu (lentils, steak, two coffees) and one pack (sandwich, beer); the salad and the hake did not sell.
  expect([stock('LEN'), stock('STK'), stock('COF'), stock('SAN'), stock('BEE')]).toEqual(['9', '9', '8', '9', '9']);
  expect([stock('SAL'), stock('HAK')]).toEqual(['10', '10']);
  relayPass();
  expect([stock('LEN'), stock('COF')]).toEqual(['9', '8']);
});

test('COMBO-F11: a menu sent to the kitchen reaches it dish by dish, under its kitchen name', async ({ page, context }) => {
  await till(page);
  const picks = await offer(context, menuId);
  await shown(page).locator(`[data-testid=pos-menu-${menuId}]`).click();
  const sheet = page.locator('ion-modal[data-testid=pos-menu]');
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.SAL}]`).click();
  await sheet.locator(`[data-testid=pos-menu-dish-${picks.HAK}]`).click();
  await sheet.locator('[data-testid=pos-menu-add]').click();
  await expect(sheet).toBeHidden();
  await expect(lineOf(page, MENU)).toBeVisible();
  await shown(page).locator('[data-testid=pos-cart-tab-round]').click();
  await shown(page).locator('[data-testid=pos-kitchen-send]').click();
  await expect(page.locator('ion-toast').filter({ hasText: /Order \d+ sent to the kitchen\./ })).toBeVisible();
  type Board = { cooking: { saved: boolean; items: { name: string; menu_name: string; quantity: string }[] }[] };
  // The check charged earlier went to the kitchen when it was charged; this one is the one with the salad.
  const sent = async () => {
    const board = await api<Board>(context, A, 'GET', '/kitchen/board');
    expect(board.status).toBe(200);
    return board.data.cooking.find((t) => t.items.some((item) => item.menu_name === `MENU ${RUN}` && item.name === products.SAL.name));
  };
  // «Send» in the till hands the round to the kitchen itself (KITCHEN-F18): its ticket is saved at once.
  const ticket = await sent();
  expect(ticket, 'the kitchen has the menu').toBeTruthy();
  expect(ticket!.saved).toBe(true);
  expect(ticket!.items.filter((item) => item.menu_name === `MENU ${RUN}`).map((item) => item.name)).toEqual([products.SAL.name, products.HAK.name]);

  // The kitchen display, every station: both dishes under the menu's header (KITCHEN-F06).
  await page.goto('/kitchen/display');
  await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
  await page.reload();
  const dishOn = (name: string) => shown(page).locator('[data-testid^=kitchen-line-][data-status]').filter({ hasText: name }).first();
  await expect(dishOn(products.SAL.name)).toBeVisible();
  const menuLine = await dishOn(products.SAL.name).getAttribute('data-menu');
  expect(menuLine, 'the salad is a dish of the menu').toBeTruthy();
  await expect(dishOn(products.HAK.name)).toHaveAttribute('data-menu', menuLine!);
  const header = shown(page).locator(`[data-testid=kitchen-menu-${menuLine}]`);
  await shots(page, 'COMBO-F11', async () => {
    await expect(header).toContainText(`MENU ${RUN}`);
    await expect(header).toContainText('2 dishes');
    await header.scrollIntoViewIfNeeded();
  });
});

test('SALE-F12: two repeatable dishes taken twice keep each name on its line beside its counter and its minus', async ({ page, context }) => {
  // FIX-SALE-MENU-SHEET-REPEATABLE-CHOICE-NAME-BREAKS: the counter and the minus shared a tile with the name, which
  // was left a few pixels wide and broke letter by letter at 390 and 834 px.
  await till(page);
  products.DEC = await createProduct(context, { name: `E2E CmbTill Decaf with oat milk ${RUN}`, sku: `${SKU}-DEC`, price: 180, tax_category_key: FOOD, initial_stock: '10' });
  const coffees = (await post<{ id: string }>(context, '/combo/combos', { name: `e2e Combo Coffees ${RUN}`, price: 300, tax_category_key: FOOD })).id;
  await post(context, '/combo/groups', { combo: `e2e Combo Coffees ${RUN}`, name: 'Coffees', min_choices: 1, max_choices: 4, allow_repeat: true });
  for (const [code, delta] of [
    ['COF', 50],
    ['DEC', 30],
  ] as const) {
    await post(context, '/combo/options', { combo: `e2e Combo Coffees ${RUN}`, group: 'Coffees', product: `${SKU}-${code}`, price_delta: delta });
  }
  await page.reload();
  const picks = await offer(context, coffees);
  await shown(page).locator(`[data-testid=pos-menu-${coffees}]`).click();
  const sheet = page.locator('ion-modal[data-testid=pos-menu]');
  // A course of 1 to 4 says both, not «Choose 1».
  await expect(sheet.locator('[data-testid^=pos-menu-rule-]')).toHaveText('Choose 1 to 4');
  for (const code of ['COF', 'COF', 'DEC', 'DEC']) await sheet.locator(`[data-testid=pos-menu-dish-${picks[code]}]`).click();
  // 3,00 + 2 × 0,50 + 2 × 0,30.
  await expect(sheet.locator('[data-testid=pos-menu-add]')).toContainText(/4[.,]60/);
  /** How many lines the name of the dish `code` takes: a name broken letter by letter takes one per letter. */
  const lines = (code: string) =>
    sheet.locator(`[data-testid=pos-menu-dish-name-${picks[code]}]`).evaluate((name) => {
      const range = document.createRange();
      range.selectNodeContents(name);
      return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
    });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    // The sheet, an `ion-modal`, animates in its shadow root: the measures wait until nothing moves.
    await untilStill(page);
    for (const code of ['COF', 'DEC']) {
      await expect(sheet.locator(`[data-testid=pos-menu-dish-count-${picks[code]}]`)).toHaveText('× 2');
      await expect(sheet.locator(`[data-testid=pos-menu-dish-less-${picks[code]}]`)).toBeVisible();
      await expect.poll(() => lines(code), { message: `the name of ${code} at ${size.label} is one or two lines` }).toBeLessThanOrEqual(2);
    }
    await capture(page, `FIX-SALE-MENU-SHEET-REPEATABLE-CHOICE-NAME-BREAKS-${size.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await sheet.locator('[data-testid=pos-menu-close]').click();
  await expect(sheet).toBeHidden();
});
