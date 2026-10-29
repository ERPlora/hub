// flow: KITCHEN-F06 y KITCHEN-F07 — the till sends a round to the kitchen (SALE-F11, SALE-F12, SALE-F20) and the
// kitchen display shows it with what the waiter chose, in Chrome with the real Sales, Modifiers, Menus, Kitchen and
// Inventory apps: a burger with its options sheet («+CHEESE» under the dish, before the note) and a menu composed
// course by course (its header with how many dishes, each dish indented under it, at its own station: the grill
// sees only the hake, still under «MENU»); the card names its waiter, never the id of the session. A tap on the menu's header marks its dishes ready. The card in
// 390×844, 834×1112 and 1440×900. KITCHEN-F11: a dish marked ready keeps the width of its name, so its ✓ never splits
// a word («HAMBURGUESA» broke in two at 834 once its dish was done). What a run creates — products
// `E2E-KMO-<run>-…`, the options group «E2E KMO <run>», the menu «e2e KMO Menu <run>», the station
// «E2E KMO <run> Grill», its checks and tickets — is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const RUN = stamp();
const SKU = `E2E-KMO-${RUN}`;
const GROUP = `E2E KMO ${RUN}`;
const MENU = `e2e KMO Menu ${RUN}`;
const STATION = `E2E KMO ${RUN} Grill`;
const FOOD = 'restaurant.food';
const KEY = 'FIX-KITCHEN-TICKET-WITHOUT-MODIFIERS-AND-MENU-DISHES';
/** A long word in capitals, the way a kitchen writes a dish: it fits a dish's name on a tablet card, but not once
 *  something else takes room beside the name. Fixed, so the card looks the same on every run. */
const WIDE = 'HAMBURGUESA';
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
let stationId: string;

/** The kitchen tickets of this run's checks (their dishes name the lines of its products or its menu, or carry the
 *  name of one of its dishes: another spec's cleanup may have taken the checks first), then its station and
 *  routing, its menu and its options group. Before the sales: a ticket names the check's lines. */
function cleanRun(): void {
  const lines = `select id from sale_orderline where sku like 'E2E-KMO-%' or name like 'e2e KMO Menu %'`;
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (${lines}) or name like 'E2E KMO %'`;
  const stations = "select id from kitchen_station where name like 'E2E KMO %'";
  const combos = "select id from combo_combo where name like 'e2e KMO Menu %'";
  const groups = "select id from modifier_modifiergroup where name like 'E2E KMO %'";
  psql(
    [
      `create temp table e2e_kmo_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_kmo_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_kmo_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_kmo_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_kmo_tickets)',
      `delete from kitchen_productroute where station_id in (${stations}) or product_id in (select id from inventory_product where sku like 'E2E-KMO-%')`,
      `update kitchen_ticketitem set station_id = null where station_id in (${stations})`,
      `delete from kitchen_station where id in (${stations})`,
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

const lineOf = (page: Page, name: string) => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: name }).first();
const dishOn = (page: Page, name: string) => shown(page).locator('[data-testid^=kitchen-line-][data-status]').filter({ hasText: name }).first();

/** How `word` of a dish's name is drawn: on how many lines (a name parts between words, never inside one), how wide
 *  it is and how wide the name's box is — what ui-clip-sweep.sh calls SPLIT-WORD, measured on the card. */
async function drawnWord(dish: Locator, word: string): Promise<{ lines: number; word: number; box: number }> {
  return dish.locator('.kds-line__name').evaluate((name, w) => {
    const box = Math.round(name.getBoundingClientRect().width);
    const walker = document.createTreeWalker(name, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const at = (node.textContent ?? '').indexOf(w);
      if (at < 0) continue;
      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, at + w.length);
      const rects = [...range.getClientRects()].filter((rect) => rect.width > 0);
      return {
        lines: new Set(rects.map((rect) => Math.round(rect.top))).size,
        word: Math.round(rects.reduce((sum, rect) => sum + rect.width, 0)),
        box,
      };
    }
    return { lines: 0, word: 0, box };
  }, word);
}

/** What any run left behind, before this one: its tickets, and also its checks — a round Sales fired and the kitchen
 *  holds no ticket of comes back on the display as «not saved yet», with the same dish names as this run's. */
function cleanUp(): void {
  cleanRun();
  cleanSales();
  cleanInventory();
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await drawerOff(context);
  burger = await createProduct(context, { name: `E2E KMO Burger ${WIDE}`, sku: `${SKU}-BUR`, price: 800, tax_category_key: FOOD });
  lentils = await createProduct(context, { name: `E2E KMO Lentils ${WIDE}`, sku: `${SKU}-LEN`, price: 500, tax_category_key: FOOD });
  hake = await createProduct(context, { name: `E2E KMO Hake ${WIDE}`, sku: `${SKU}-HAK`, price: 1400, tax_category_key: FOOD });
  await post(context, '/modifier/groups', { name: GROUP, max_choices: 2 });
  cheeseId = (await post<{ id: string }>(context, '/modifier/options', { group: GROUP, name: 'Cheese', kitchen_name: '+CHEESE', price_delta: 100 })).id;
  await post(context, '/modifier/links/attach', { group: GROUP, product_id: burger.id });
  comboId = (await post<{ id: string }>(context, '/combo/combos', { name: MENU, kitchen_name: 'MENU', price: 1350, tax_category_key: FOOD })).id;
  for (const [course, product] of [
    ['Starters', lentils],
    ['Mains', hake],
  ] as const) {
    await post(context, '/combo/groups', { combo: MENU, name: course });
    await post(context, '/combo/options', { combo: MENU, group: course, product: product.sku });
  }
  stationId = (await post<{ id: string }>(context, '/kitchen/stations', { name: STATION, color: '#E03131' })).id;
  await post(context, '/kitchen/routing', { station_id: stationId, product_id: hake.id }, 200);
  await context.close();
});

test.afterAll(() => {
  cleanUp();
  restoreDrawer();
});

test('KITCHEN-F06 y KITCHEN-F07: the round sent from the till reaches the display with its options and its menu', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await shown(page).locator(`[data-testid=pos-product-${burger.id}]`).waitFor({ state: 'visible' });

  // SALE-F11: the burger with cheese and a note.
  await shown(page).locator(`[data-testid=pos-product-${burger.id}]`).click();
  const options = page.locator('ion-modal[data-testid=pos-options]');
  await options.locator(`[data-testid=pos-option-${cheeseId}]`).click();
  await options.locator('[data-testid=pos-options-add]').click();
  await expect(options).toBeHidden();
  await expect(lineOf(page, burger.name)).toContainText('Cheese');

  // SALE-F12: the menu, course by course.
  await shown(page).locator(`[data-testid=pos-menu-${comboId}]`).click();
  const sheet = page.locator('ion-modal[data-testid=pos-menu]');
  await expect(sheet).toBeVisible();
  const offer = await api<{ rows: { id: string; groups: { options: { id: string; product_id: string }[] }[] }[] }>(
    context,
    A,
    'GET',
    '/combo/combos/for_sale?limit=50',
  );
  const optionOf = (product: Product) =>
    offer.data.rows.find((row) => row.id === comboId)!.groups.flatMap((group) => group.options).find((option) => option.product_id === product.id)!.id;
  await sheet.locator(`[data-testid=pos-menu-dish-${optionOf(lentils)}]`).click();
  await sheet.locator(`[data-testid=pos-menu-dish-${optionOf(hake)}]`).click();
  await sheet.locator('[data-testid=pos-menu-add]').click();
  await expect(sheet).toBeHidden();
  await expect(lineOf(page, MENU)).toBeVisible();

  // SALE-F20: «Current order» → «Send».
  await shown(page).locator('[data-testid=pos-cart-tab-round]').click();
  await shown(page).locator('[data-testid=pos-kitchen-send]').click();
  await expect(page.locator('ion-toast').filter({ hasText: /Order \d+ sent to the kitchen\./ })).toBeVisible();

  // The kitchen display, every station: the burger with «+CHEESE» under it; the menu's header with its two dishes.
  await page.goto('/kitchen/display');
  await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
  await page.reload();
  const burgerDish = dishOn(page, burger.name);
  await expect(burgerDish).toBeVisible();
  const burgerId = (await burgerDish.getAttribute('data-testid'))!.replace('kitchen-line-', '');
  await expect(shown(page).locator(`[data-testid=kitchen-line-${burgerId}-modifiers]`)).toHaveText('+CHEESE');
  const lentilsDish = dishOn(page, lentils.name);
  const hakeDish = dishOn(page, hake.name);
  const menuLine = await lentilsDish.getAttribute('data-menu');
  expect(menuLine, 'the lentils are a dish of the menu').toBeTruthy();
  await expect(hakeDish).toHaveAttribute('data-menu', menuLine!);
  const header = shown(page).locator(`[data-testid=kitchen-menu-${menuLine}]`);
  await expect(header).toContainText('MENU');
  await expect(header).toContainText('2 dishes');
  const card = shown(page)
    .locator('[data-testid^=kitchen-card-][aria-label]')
    .filter({ has: page.locator(`[data-testid=kitchen-menu-${menuLine}]`) });
  await expect(card.locator(`[data-testid=kitchen-line-${burgerId}]`)).toBeVisible();
  // Who sent it, by the name a person reads: never the id of the session («saas:…»).
  await expect(card.locator('[data-testid$=-waiter]')).toContainText('Waiter: ');
  await expect(card.locator('[data-testid$=-waiter]')).not.toContainText('saas:');

  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(header).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    // The picture waits until nothing moves, Ionic's own animations in their shadow roots too.
    await untilStill(page);
    await capture(page, `${KEY}-${size.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  // The grill sees only its dish of the menu (the hake), still under the menu's header: «1 dish».
  await shown(page).locator(`[data-testid=kitchen-display-station-${stationId}]`).click();
  await expect(hakeDish).toBeVisible();
  await expect(dishOn(page, lentils.name)).toHaveCount(0);
  await expect(header).toContainText('1 dish');
  await expect(header).not.toContainText('1 dishes');

  // Every station again: a tap on the menu's header marks its dishes ready, and the burger keeps cooking.
  await shown(page).locator('[data-testid=kitchen-display-station-all]').click();
  await expect(dishOn(page, lentils.name)).toBeVisible();
  await expect(header).toContainText('2 dishes');
  await header.click();
  await expect(dishOn(page, lentils.name)).toHaveAttribute('data-status', 'ready');
  await expect(dishOn(page, hake.name)).toHaveAttribute('data-status', 'ready');
  await expect(shown(page).locator(`[data-testid=kitchen-line-${burgerId}]`)).toHaveAttribute('data-status', 'pending');

  // KITCHEN-F11: the dishes done keep the whole width of their name, like the burger still cooking — the ✓ never
  // breaks «HAMBURGUESA» in two, in any of the three sizes.
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await card.scrollIntoViewIfNeeded();
    for (const dish of [burgerDish, dishOn(page, lentils.name), dishOn(page, hake.name)]) {
      const name = (await dish.locator('.kds-line__name').textContent())?.trim();
      const drawn = await drawnWord(dish, WIDE);
      expect(drawn.lines, `${size.label}: «${WIDE}» of «${name}» is ${drawn.word}px, its name ${drawn.box}px`).toBe(1);
    }
    // ...and its ✓ is where it always was: at the dish's right edge, level with the first line of the name.
    for (const dish of [dishOn(page, lentils.name), dishOn(page, hake.name)]) {
      const off = await dish.evaluate((line) => {
        const tick = line.querySelector('.kds-line__tick')!.getBoundingClientRect();
        const name = line.querySelector('.kds-line__name')!.getBoundingClientRect();
        const edge = line.getBoundingClientRect().right - parseFloat(getComputedStyle(line).paddingRight);
        return { top: Math.abs(tick.top - name.top), right: Math.abs(tick.right - edge) };
      });
      expect(off.top, `${size.label}: the ✓ starts level with the name`).toBeLessThan(8);
      expect(off.right, `${size.label}: the ✓ ends at the dish's right edge`).toBeLessThanOrEqual(1);
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
});
