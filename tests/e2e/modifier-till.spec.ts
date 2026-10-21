// flow: MODIFIER-F06, MODIFIER-F07, MODIFIER-F08, MODIFIER-F09 — the groups of Modifiers at work in Chrome, against
// the real Inventory, Taxes, Sales and Kitchen apps (apps/modifier/WORKBOOK.md): tapping a burger in the till opens
// its sheet with the groups of the dish and of its category, each with its rule, the default already chosen, a
// counter where an option repeats and «Add» waiting while a required group is short (F06); the line charges the
// catalogue's supplements, a soda of another VAT on a line of its own with its base and VAT (F07); the round sent
// from «Current order» reaches the kitchen display with the options by their kitchen names, in the order chosen
// (F08); a product deleted in Inventory lets go of its groups once the worker's outbox relay runs — here as each tick
// runs it: the e2e stack runs no worker — and the group's sheet no longer applies there (F09). Each screen in
// 390×844, 834×1112 and 1440×900 (`APP-MODIFIER-MODIFIER-Fnn-<w>`). What a run makes — products `E2E-MTL-<run>-…`,
// the category «E2E MTL <run>», the groups «E2E Mod Till … <run>», its checks, sales and kitchen tickets — goes.
import { spawnSync } from 'node:child_process';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, HUB_DIR, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const RUN = stamp();
const SKU = `E2E-MTL-${RUN}`;
const CATEGORY = `E2E MTL ${RUN}`;
const named = (what: string) => `E2E Mod Till ${what} ${RUN}`;
const FOOD = 'restaurant.food';
const GENERIC = 'product.generic';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

let burger: Product;
let salad: Product;
let card: string;
let categoryId: string;
const ids: Record<string, string> = {};
const groups: Record<string, string> = {};

/** The kitchen tickets of this run's checks, then its groups. Before the sales: a ticket names the check's lines. */
function cleanRun(): void {
  const lines = `select id from sale_orderline where sku like 'E2E-MTL-%'`;
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (${lines})`;
  const own = "select id from modifier_modifiergroup where name like 'E2E Mod Till %'";
  psql(
    [
      `create temp table e2e_mtl_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_mtl_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_mtl_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_mtl_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_mtl_tickets)',
      `delete from modifier_modifierlink where group_id in (${own})`,
      `delete from modifier_modifieroption where group_id in (${own})`,
      `delete from modifier_modifiergroup where id in (${own})`,
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

/** The screen in the three viewports, each once `ready` says it painted; back to 1440×900 after. */
async function shots(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
    await page.screenshot({ path: shot(`APP-MODIFIER-${key}-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function openTill(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator(`[data-testid=pos-product-${burger.id}]`).waitFor({ state: 'visible' });
}

/** What Sales says it charged: the total and each line with its rate, base and VAT. */
interface ChargedSale {
  total: number;
  lines: { name: string; tax_rate: string; line_total: number; net_amount: number; tax_amount: number }[];
}

const optionsSheet = (page: Page) => page.locator('ion-modal[data-testid=pos-options]');
const lineOf = (page: Page, name: string) => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: name }).first();

/** Taps the burger, chooses `picks` (the default «Medium» is already chosen) and adds the line. */
async function addBurger(page: Page, picks: string[]): Promise<void> {
  await shown(page).locator(`[data-testid=pos-product-${burger.id}]`).click();
  const sheet = optionsSheet(page);
  await expect(sheet).toBeVisible();
  for (const pick of picks) await sheet.locator(`[data-testid=pos-option-${ids[pick]}]`).click();
  await sheet.locator('[data-testid=pos-options-add]').click();
  await expect(sheet).toBeHidden();
}

test.beforeAll(async ({ browser }) => {
  cleanRun();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await drawerOff(context);
  // A burger of 8,00 € at 10 % in a category of its own.
  burger = await createProduct(context, { name: `E2E Burger ${RUN}`, sku: `${SKU}-BUR`, price: 800, tax_category_key: FOOD });
  categoryId = (await post<{ id: string }>(context, '/inventory/categories', { name: CATEGORY })).id;
  await post(context, '/inventory/product_categories/add', { product: burger.sku, category: CATEGORY }, 200);
  // «Doneness» (required, one; «Medium» by default) hangs from the category; «Extras» (up to two, repeatable) and
  // «Drink» (a soda at 21 %, a line of its own) from the burger.
  for (const [key, fields] of [
    ['doneness', { name: named('Doneness'), min_choices: 1, max_choices: 1, sort_order: 1 }],
    ['extras', { name: named('Extras'), max_choices: 2, allow_repeat: true, sort_order: 2 }],
    ['drink', { name: named('Drink'), max_choices: 1, sort_order: 3 }],
  ] as const) {
    groups[key] = (await post<{ id: string }>(context, '/modifier/groups', fields)).id;
  }
  for (const [key, group, fields] of [
    ['rare', 'doneness', { name: 'Rare', sort_order: 1 }],
    ['medium', 'doneness', { name: 'Medium', sort_order: 2, is_default: true }],
    ['cheese', 'extras', { name: 'Cheese', kitchen_name: '+CHEESE', price_delta: 100, sort_order: 1 }],
    ['onion', 'extras', { name: 'No onion', kitchen_name: '-ONION', sort_order: 2 }],
    ['soda', 'drink', { name: 'Soda', price_delta: 200, tax_category_key: GENERIC }],
  ] as const) {
    ids[key] = (await post<{ id: string }>(context, '/modifier/options', { group_id: groups[group], ...fields })).id;
  }
  await post(context, '/modifier/links/attach', { group_id: groups.doneness, category_id: categoryId });
  for (const group of ['extras', 'drink']) await post(context, '/modifier/links/attach', { group_id: groups[group], product_id: burger.id });
  // A salad whose groups ask a minimum without a ceiling («Dressing») and a minimum up to a ceiling («Toppings»).
  salad = await createProduct(context, { name: `E2E Salad ${RUN}`, sku: `${SKU}-SAL`, price: 650, tax_category_key: FOOD });
  for (const [key, fields, option] of [
    ['dressing', { name: named('Dressing'), min_choices: 1, max_choices: 0, sort_order: 1 }, 'Vinaigrette'],
    ['toppings', { name: named('Toppings'), min_choices: 1, max_choices: 3, sort_order: 2 }, 'Croutons'],
  ] as const) {
    groups[key] = (await post<{ id: string }>(context, '/modifier/groups', fields)).id;
    await post(context, '/modifier/options', { group_id: groups[key], name: option });
    await post(context, '/modifier/links/attach', { group_id: groups[key], product_id: salad.id });
  }
  const list = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  card = list.data.rows.find((row) => row.type === 'card')?.id ?? '';
  expect(card, 'a card method').not.toBe('');
  await context.close();
});

test.afterAll(() => {
  cleanRun();
  cleanSales();
  cleanInventory();
  restoreDrawer();
});

test('MODIFIER-F06: the till asks the groups of the burger and of its category, each with its rule', async ({ page }) => {
  await openTill(page);
  await shown(page).locator(`[data-testid=pos-product-${burger.id}]`).click();
  const sheet = optionsSheet(page);
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('[data-testid=pos-options-title]')).toHaveText(burger.name);
  // Its category's group first (by its order), each once, with its rule.
  await expect(sheet.locator('[data-testid^=pos-options-group-]')).toHaveCount(3);
  await expect(sheet.locator(`[data-testid=pos-options-rule-${groups.doneness}]`)).toHaveText('Choose 1');
  await expect(sheet.locator(`[data-testid=pos-options-rule-${groups.extras}]`)).toHaveText('Up to 2');
  await expect(sheet.locator(`[data-testid=pos-options-rule-${groups.drink}]`)).toHaveText('Up to 1');
  // The default comes chosen; each option says its supplement with its sign, nothing when it is free.
  await expect(sheet.locator(`[data-testid=pos-option-${ids.medium}]`)).toHaveAttribute('aria-pressed', 'true');
  await expect(sheet.locator(`[data-testid=pos-option-${ids.cheese}]`)).toContainText(/\+€1[.,]00/);
  await expect(sheet.locator(`[data-testid=pos-option-${ids.onion}]`)).not.toContainText('€');
  const add = sheet.locator('[data-testid=pos-options-add]');
  await expect(add).toContainText(/8[.,]00/);

  // A tap on the chosen option of a one-choice group takes it away: «Add» waits and points at the group.
  await sheet.locator(`[data-testid=pos-option-${ids.medium}]`).click();
  await expect(add).toContainText('Choose an option to continue');
  await add.click();
  await expect(sheet.locator(`[data-testid=pos-options-group-${groups.doneness}]`)).toHaveClass(/pos-options__group--missing/);
  await sheet.locator(`[data-testid=pos-option-${ids.rare}]`).click();
  // Cheese twice: its counter says so, and the ceiling of two answers a third tap.
  await sheet.locator(`[data-testid=pos-option-${ids.cheese}]`).click();
  await sheet.locator(`[data-testid=pos-option-${ids.cheese}]`).click();
  await expect(sheet.locator(`[data-testid=pos-option-count-${ids.cheese}]`)).toContainText('2');
  await sheet.locator(`[data-testid=pos-option-${ids.onion}]`).click();
  await expect(sheet.locator(`[data-testid=pos-options-group-${groups.extras}]`)).toContainText(`«${named('Extras')}» is full`);
  await expect(add).toContainText(/10[.,]00/);
  // The chosen cheese, with its «× 2» and its «−», keeps its name on one line in every size (hub#143).
  const cheeseName = sheet.locator(`[data-testid=pos-option-name-${ids.cheese}]`);
  await shots(page, 'MODIFIER-F06', async () => {
    await expect(add).toBeVisible();
    const lines = await cheeseName.evaluate((name) => {
      const range = document.createRange();
      range.selectNodeContents(name);
      return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
    });
    expect(lines, `«Cheese» on ${page.viewportSize()?.width}px`).toBe(1);
  });

  await add.click();
  await expect(sheet).toBeHidden();
  const line = lineOf(page, burger.name);
  await expect(line).toContainText('Rare, Cheese, Cheese');
  await expect(line).toContainText(/10[.,]00/);

  // A minimum without a ceiling, and a minimum up to a ceiling, each say so.
  await shown(page).locator(`[data-testid=pos-product-${salad.id}]`).click();
  await expect(sheet).toBeVisible();
  await expect(sheet.locator(`[data-testid=pos-options-rule-${groups.dressing}]`)).toHaveText('Choose at least 1');
  await expect(sheet.locator(`[data-testid=pos-options-rule-${groups.toppings}]`)).toHaveText('Choose 1 to 3');
  await sheet.locator('[data-testid=pos-options-close]').click();
  await expect(sheet).toBeHidden();
});

test('MODIFIER-F07: the supplements are charged at the catalogue price, the soda on a line of its own with its VAT', async ({ page, context }) => {
  await openTill(page);
  await addBurger(page, ['cheese', 'soda']);
  // The check line paints what the burger and its soda cost together: 8,00 + 1,00 + 2,00.
  await expect(lineOf(page, burger.name)).toContainText(/11[.,]00/);

  await shown(page).locator('[data-testid=pos-charge]').click();
  const checkout = page.locator('[data-testid=sale-checkout-modal]');
  await expect(checkout.locator('[data-testid=sale-checkout-total]')).toContainText(/11[.,]00/);
  await checkout.locator(`[data-testid=sale-checkout-method-${card}]`).click();
  await checkout.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(checkout).toBeHidden();
  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  const receiptLines = receipt.locator('[data-testid=sale-receipt-line]');
  await expect(receiptLines.filter({ hasText: burger.name })).toContainText(/9[.,]00/);
  await expect(receiptLines.filter({ hasText: burger.name }).locator('[data-testid=sale-receipt-options]')).toHaveText('Medium, Cheese');
  await expect(receiptLines.filter({ hasText: '+ Soda' })).toContainText(/2[.,]00/);
  await shots(page, 'MODIFIER-F07', () => expect(receipt).toBeVisible());

  // What Sales charged, line by line: the burger with its cheese at 10 %, the soda at 21 %, each squaring.
  const sales = await api<{ rows: { id: string }[] }>(context, A, 'GET', '/sale/sales?limit=50');
  let charged: ChargedSale | null = null;
  for (const row of sales.data.rows) {
    const sale = (await api<ChargedSale>(context, A, 'GET', `/sale/sales/detail?sale_id=${row.id}`)).data;
    if (sale.lines.some((line) => line.name === burger.name)) {
      charged = sale;
      break;
    }
  }
  expect(charged, 'the sale of this run').not.toBeNull();
  expect(charged!.total).toBe(1100);
  expect(charged!.lines.map((line) => [line.name, Number(line.tax_rate), line.line_total, line.net_amount, line.tax_amount])).toEqual([
    [burger.name, 10, 900, 818, 82],
    ['Soda', 21, 200, 165, 35],
  ]);
});

test('MODIFIER-F08: the round reaches the kitchen display with the options by their kitchen names, in the order chosen', async ({ page }) => {
  await openTill(page);
  // No onion before the cheese: the cook reads them as the waiter tapped them, after the default «Medium».
  await addBurger(page, ['onion', 'cheese']);
  await shown(page).locator('[data-testid=pos-cart-tab-round]').click();
  await shown(page).locator('[data-testid=pos-kitchen-send]').click();
  await expect(page.locator('ion-toast').filter({ hasText: /Order \d+ sent to the kitchen\./ })).toBeVisible();
  relayPass();

  await page.goto('/kitchen/display');
  await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
  await page.reload();
  // This round's burger (another test's charge sent one too): the one whose options say «-ONION».
  const options = shown(page).locator('[data-testid^=kitchen-line-][data-testid$=-modifiers]').filter({ hasText: '-ONION' });
  await expect(options).toHaveText('Medium, -ONION, +CHEESE');
  const dishId = (await options.getAttribute('data-testid'))!.replace(/^kitchen-line-|-modifiers$/g, '');
  const dish = shown(page).locator(`[data-testid=kitchen-line-${dishId}]`);
  await expect(dish).toContainText(burger.name);
  // The ticket is saved by the kitchen through the relay, with the options frozen on the dish.
  expect(psql(`select modifiers::text from kitchen_ticketitem where id = '${dishId}'`)).toBe('["Medium", "-ONION", "+CHEESE"]');
  await shots(page, 'MODIFIER-F08', async () => {
    await dish.scrollIntoViewIfNeeded();
    await expect(options).toBeVisible();
  });
});

test('MODIFIER-F09: a product deleted in Inventory lets go of its groups once the relay runs', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/modifier/groups');
  const fries = await createProduct(context, { name: `E2E Fries ${RUN}`, sku: `${SKU}-FRI`, price: 300, tax_category_key: FOOD });
  await post(context, '/modifier/links/attach', { group_id: groups.extras, product_id: fries.id });
  const linksOf = (product: string) => Number(psql(`select count(*) from modifier_modifierlink where product_id = '${product}'`));
  expect(linksOf(fries.id)).toBe(1);

  await post(context, '/inventory/products/delete', { id: fries.id }, 200);
  relayPass();
  expect(linksOf(fries.id)).toBe(0);
  // The burger keeps its groups.
  expect(linksOf(burger.id)).toBe(2);
  // Another pass of the relay changes nothing.
  relayPass();
  expect(linksOf(burger.id)).toBe(2);

  await page.reload();
  await shown(page).locator('[data-testid=modifier-groups-search] input').fill(named('Extras'));
  const row = shown(page).locator(`[data-testid=modifier-groups-row][data-id="${groups.extras}"]`);
  await expect(row.locator('[role=cell]').nth(4)).toHaveText('1');
  await row.locator('[role=cell]').first().click();
  const sheet = page.locator('ion-modal[data-testid=modifier-sheet]');
  const links = sheet.locator('[data-testid^=modifier-sheet-links-row-]');
  await expect(links).toHaveCount(1);
  await expect(links.first()).toContainText(burger.sku);
  await expect(sheet).not.toContainText(fries.sku);
  await shots(page, 'MODIFIER-F09', () => expect(links).toHaveCount(1));
});
