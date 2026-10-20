// flow: SALE-F11, SALE-F12, SALE-F20, SALE-F28 — the till in Chrome with the real Modifiers, Menus, Kitchen,
// Inventory and Taxes apps: a burger with its options sheet, a menu from «All» with its courses sheet charged by
// card and printed with its dishes, «Current order» sending the round to the kitchen as a rush, and Sales'
// «7 days» with each day's takings. Each screen in 390×844, 834×1112 and 1440×900. What a run creates — its
// products `E2E-SMO-<run>-…`, its options group «E2E SMO <run>», its menu «e2e Menu <run>», its checks, sales,
// kitchen tickets and fiscal documents — is deleted after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const RUN = stamp();
const SKU = `E2E-SMO-${RUN}`;
const GROUP = `E2E SMO ${RUN}`;
const MENU = `e2e Menu ${RUN}`;
const FOOD = 'restaurant.food';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

let burger: Product;
let lentils: Product;
let hake: Product;
let comboId: string;
let cheeseId: string;
let card: string;

/** The kitchen tickets of this run's checks (their lines sell its products or its menu), then its menu and its
 *  options group. Before the sales: a ticket names the check's lines. */
function cleanRun(): void {
  const lines = `select id from sale_orderline where sku like 'E2E-SMO-%' or name like 'e2e Menu %'`;
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (${lines})`;
  const combos = "select id from combo_combo where name like 'e2e Menu %'";
  const groups = "select id from modifier_modifiergroup where name like 'E2E SMO %'";
  psql(
    [
      `create temp table e2e_smo_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_smo_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_smo_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_smo_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_smo_tickets)',
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

/** The screen in the three viewports, each once `ready` says it painted; back to 1440×900 after. */
async function shots(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    // A resize slides the phone's cart drawer: the picture waits until nothing moves.
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
    await page.screenshot({ path: shot(`APP-SALE-${key}-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator(`[data-testid=pos-product-${burger.id}]`).waitFor({ state: 'visible' });
}

const lineOf = (page: Page, name: string) => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: name }).first();

/** The buttons on top of the check (park, table, customer, open checks, close), each with its box: none may sit on
 *  another, or a tap meant for one lands on the other. */
async function toolbarOverlaps(page: Page): Promise<string[]> {
  const ids = ['pos-park', 'pos-table-trigger', 'customer-search-trigger', 'pos-open-checks', 'pos-cart-close'];
  const boxes: { id: string; x: number; right: number }[] = [];
  for (const id of ids) {
    const button = shown(page).locator(`[data-testid=pos-cart] [data-testid=${id}]`);
    if (!(await button.isVisible())) continue;
    const box = await button.boundingBox();
    if (box) boxes.push({ id, x: box.x, right: box.x + box.width });
  }
  const span = (box: { x: number; right: number }) => `[${Math.round(box.x)}–${Math.round(box.right)}]`;
  const overlaps: string[] = [];
  for (const [i, a] of boxes.entries()) {
    for (const b of boxes.slice(i + 1)) {
      if (a.x < b.right - 0.5 && b.x < a.right - 0.5) overlaps.push(`${a.id} ${span(a)} over ${b.id} ${span(b)}`);
    }
  }
  return overlaps;
}

test.beforeAll(async ({ browser }) => {
  cleanRun();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await drawerOff(context);
  burger = await createProduct(context, { name: `E2E Burger ${RUN}`, sku: `${SKU}-BUR`, price: 800, tax_category_key: FOOD });
  lentils = await createProduct(context, { name: `E2E Lentils ${RUN}`, sku: `${SKU}-LEN`, price: 500, tax_category_key: FOOD });
  hake = await createProduct(context, { name: `E2E Hake ${RUN}`, sku: `${SKU}-HAK`, price: 1400, tax_category_key: FOOD });
  await post(context, '/modifier/groups', { name: GROUP, max_choices: 2 });
  cheeseId = (await post<{ id: string }>(context, '/modifier/options', { group: GROUP, name: 'Cheese', price_delta: 100 })).id;
  await post(context, '/modifier/links/attach', { group: GROUP, product_id: burger.id });
  comboId = (await post<{ id: string }>(context, '/combo/combos', { name: MENU, kitchen_name: 'MENU', price: 1350, tax_category_key: FOOD })).id;
  for (const [course, product] of [
    ['Starters', lentils],
    ['Mains', hake],
  ] as const) {
    await post(context, '/combo/groups', { combo: MENU, name: course });
    await post(context, '/combo/options', { combo: MENU, group: course, product: product.sku });
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

test('SALE-F11: a burger with options opens its sheet and enters the check with them and its price', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await shown(page).locator(`[data-testid=pos-product-${burger.id}]`).click();
  const sheet = page.locator('ion-modal[data-testid=pos-options]');
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('[data-testid=pos-options-title]')).toHaveText(burger.name);
  await sheet.locator(`[data-testid=pos-option-${cheeseId}]`).click();
  await expect(sheet.locator('[data-testid=pos-options-add]')).toContainText(/9[.,]00/);
  await shots(page, 'SALE-F11', async () => {
    await expect(sheet.locator('[data-testid=pos-options-add]')).toBeVisible();
  });
  await sheet.locator('[data-testid=pos-options-add]').click();
  await expect(sheet).toBeHidden();
  const line = lineOf(page, burger.name);
  await expect(line).toContainText('Cheese');
  await expect(line).toContainText(/9[.,]00/);
});

test('SALE-F12: a menu from «All» is composed course by course, charged by card and printed with its dishes', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  const tile = shown(page).locator(`[data-testid=pos-menu-${comboId}]`);
  await expect(tile).toContainText(MENU);
  await expect(tile.locator(`[data-testid=pos-menu-${comboId}-badge]`)).toHaveText('Menu');
  // Menus go first in «All», before the products.
  await expect(shown(page).locator('.pos-grid > button').first()).toHaveAttribute('data-testid', `pos-menu-${comboId}`);
  await tile.click();
  const sheet = page.locator('ion-modal[data-testid=pos-menu]');
  await expect(sheet).toBeVisible();
  const add = sheet.locator('[data-testid=pos-menu-add]');
  await expect(add).toContainText('Choose 1 in «Starters»');
  await add.click();
  await expect(sheet.locator('.pos-options__group--missing')).toHaveCount(1);
  const options = await api<{ rows: { id: string; groups: { name: string; options: { id: string; product_id: string }[] }[] }[] }>(
    context,
    A,
    'GET',
    '/combo/combos/for_sale?limit=50',
  );
  const offer = options.data.rows.find((row) => row.id === comboId);
  expect(offer, 'the menu is on sale').toBeTruthy();
  const optionOf = (product: Product) => offer!.groups.flatMap((group) => group.options).find((option) => option.product_id === product.id)!.id;
  await sheet.locator(`[data-testid=pos-menu-dish-${optionOf(lentils)}]`).click();
  await expect(add).toContainText('Choose 1 in «Mains»');
  await sheet.locator(`[data-testid=pos-menu-dish-${optionOf(hake)}]`).click();
  await expect(add).toContainText(/13[.,]50/);
  await shots(page, 'SALE-F12', async () => {
    await expect(add).toBeVisible();
  });
  await add.click();
  await expect(sheet).toBeHidden();
  const line = lineOf(page, MENU);
  await expect(line).toContainText(`${lentils.name}, ${hake.name}`);

  await shown(page).locator('[data-testid=pos-charge]').click();
  const checkout = page.locator('[data-testid=sale-checkout-modal]');
  await expect(checkout.locator('[data-testid=sale-checkout-total]')).toContainText(/13[.,]50/);
  await checkout.locator(`[data-testid=sale-checkout-method-${card}]`).click();
  await checkout.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(checkout).toBeHidden();
  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  await expect(receipt.locator('[data-testid=sale-receipt-line]').filter({ hasText: MENU })).toContainText(/13[.,]50/);
  await expect(receipt.locator('[data-testid=sale-receipt-dish]')).toHaveText([lentils.name, hake.name]);
  await shots(page, 'SALE-F12-receipt', async () => {
    await expect(receipt).toBeVisible();
  });
});

test('SALE-F20: «Current order» says what waits and sends it to the kitchen as a rush', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await shown(page).locator(`[data-testid=pos-product-${lentils.id}]`).click();
  await expect(lineOf(page, lentils.name)).toBeVisible();
  const round = shown(page).locator('[data-testid=pos-cart-tab-round]');
  await expect(round).toHaveAttribute('aria-label', 'Current order, 1 item to send');
  await round.click();
  await expect(shown(page).locator('[data-testid=pos-cart-round-hint]')).toBeVisible();
  await shown(page).locator('[data-testid=pos-kitchen-rush]').click();
  const send = shown(page).locator('[data-testid=pos-kitchen-send]');
  await expect(send).toContainText('Send RUSH (1)');
  await shots(page, 'SALE-F20', async () => {
    // The phone keeps the check in a drawer: its button opens it.
    const fab = page.locator('[data-testid=pos-cart-fab]');
    if (await fab.isVisible()) await fab.click();
    await expect(shown(page).locator('[data-testid=pos-kitchen-send]')).toBeVisible();
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
    // The check's bar fits each width: «Assign customer» once sat on «Open checks» on a phone.
    expect(await toolbarOverlaps(page), `the check's bar at ${page.viewportSize()?.width}px`).toEqual([]);
  });
  await send.click();
  await expect(page.locator('ion-toast').filter({ hasText: /Order \d+ sent to the kitchen\./ })).toBeVisible();
  await expect(shown(page).locator('[data-testid=pos-cart-round-empty]')).toContainText('Everything is sent');
  await expect(round).toHaveAttribute('aria-label', 'Current order');
});

test('SALE-F28: «7 days» shows what was sold each of those days', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/sales');
  await shown(page).locator('[data-testid=sales-range]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-range-week]').click();
  const week = shown(page).locator('[data-testid=sale-week]');
  await expect(week.locator('[data-testid=sale-week-day]')).toHaveCount(7);
  await expect(week).toHaveAttribute('aria-label', 'Last 7 days');
  await shots(page, 'SALE-F28', async () => {
    await expect(week).toBeVisible();
  });
});
