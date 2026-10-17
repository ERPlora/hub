// Menus and combos in Chrome (apps/combo/WORKBOOK.md, COMBO-F01 to F09, F12, F13), against hub `a`
// and the real Inventory and Taxes apps (no doubles): the owner creates «menu of the day» eaten in at
// Taxes' restaurant.food, builds its courses from Inventory's products (searched by SKU), gives a
// supplement, marks a dish sold out, reorders; then adds several dishes at once, edits, reorders and
// removes choices, edits and withdraws a course, and changes the menu and takes it off sale (F03). The
// till's catalogue and the line of the menu are read from the API (the TPV sheet is Ventas'), eaten in,
// ordered to take away (split, the beer at retail.alcohol) and as a pack to take away; a product
// deactivated in Inventory shows up live as «Deactivated in Inventory»; the menu is withdrawn after its
// confirmation; a menu withdrawn from another tab while its builder is open says it no longer exists.
// Screenshots of the list, the form and the builder at three viewports, with nothing past the right edge. What it creates is named «E2E Combo …» / «E2E-CMB-…» and deleted before and after.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';

const TAG = 'E2E Combo';
const STAMP = Date.now().toString(36).toUpperCase();
const MENU = `${TAG} Menu ${STAMP}`;
const PACK = `${TAG} Pack ${STAMP}`;
/** The products this file makes, by code: their ids once made. */
const made: Record<string, string> = {};
const sku = (code: string): string => `E2E-CMB-${STAMP}-${code}`;

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

interface Product {
  id: string;
  name: string;
  sku: string;
}

interface Detail {
  id: string;
  groups: { id: string; name: string; options: { id: string; product_name: string; status: string }[] }[];
}

/** Every menu, course, choice and product this file made, from hub `a`'s database. */
function cleanUp(): void {
  const combos = `select id from combo_combo where name like '${TAG}%'`;
  const groups = `select id from combo_choicegroup where combo_id in (${combos})`;
  const products = `select id from inventory_product where sku like 'E2E-CMB-%'`;
  psql(
    [
      `delete from combo_choiceoption where group_id in (${groups}) or product_id in (${products})`,
      `delete from combo_choicegroup where combo_id in (${combos})`,
      `delete from combo_combo where name like '${TAG}%'`,
      `delete from inventory_stockmovement where product_id in (${products})`,
      `delete from inventory_productcategory where product_id in (${products})`,
      `delete from inventory_product where sku like 'E2E-CMB-%'`,
    ].join('; '),
  );
}

test.describe.configure({ mode: 'serial' });
test.beforeAll(cleanUp);
test.afterAll(cleanUp);

async function call<T>(context: BrowserContext, method: 'GET' | 'POST', path: string, body?: unknown, status = 200): Promise<T> {
  const res = await api<T>(context, A, method, path, body);
  expect(res.status, `${method} ${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

async function product(context: BrowserContext, code: string, name: string, price: number, tax = 'restaurant.food'): Promise<Product> {
  const created = await call<Product>(
    context,
    'POST',
    '/inventory/products',
    { name: `${TAG} ${name} ${STAMP}`, sku: sku(code), price, tax_category_key: tax },
    201,
  );
  made[code] = created.id;
  return created;
}

/** The SKU picks of `resolve`'s query string, one JSON object per pick. */
const picks = (...codes: string[]): string => codes.map((code) => `choices=${encodeURIComponent(JSON.stringify({ product: sku(code) }))}`).join('&');

interface Line {
  amount: number;
  split: boolean;
  supply_kind: string;
  tax_category_key: string | null;
  components: { product_name: string; tax_category_key: string; amount: number | null }[];
}

async function menuId(context: BrowserContext): Promise<string> {
  return (await call<Detail>(context, 'GET', `/combo/combos/detail?combo=${encodeURIComponent(MENU)}`)).id;
}

/** When the document was loaded: a different value later means the page was reloaded. */
const loadedAt = (page: Page): Promise<number> => page.evaluate(() => performance.timeOrigin);

/** Picks the option of a `Combo` whose text holds `text`, searching it by `query`, as a person does:
 *  wait until no list of a previous pick is still closing, click the field, wait for its list, type,
 *  choose. Reopening a Combo while its previous popover is still animating out loses the typing: the
 *  late `didDismiss` of the old presentation closes the new one and reverts the text, and no search
 *  reaches the server (measured 2026-10-15 on the second pick of a course; reported for
 *  `@erplora/ui`'s Combo). The dev server is shared with other sessions: a search cut by its restart
 *  shows the list's own «Retry», which is pressed; a page Vite reloaded is picked again; anything else
 *  fails at once. */
async function pick(page: Page, testid: string, query: string, text: string): Promise<void> {
  const input = page.locator(`[data-testid=${testid}] input`);
  const option = page.locator(`[data-testid^=${testid}-option-]`, { hasText: text }).first();
  const failed = page.locator(`[data-testid=${testid}-error]`);
  for (let attempt = 1; ; attempt += 1) {
    const before = await loadedAt(page);
    try {
      await expect(page.locator('ion-popover.combo__popover:not(.overlay-hidden)')).toHaveCount(0);
      await input.click();
      await expect(input).toHaveAttribute('aria-expanded', 'true');
      await page
        .locator(`[data-testid=${testid}-loading], [data-testid=${testid}-empty], [data-testid^=${testid}-option-], [data-testid=${testid}-error]`)
        .first()
        .waitFor({ state: 'visible' });
      await input.fill(query);
      await option.or(failed).first().waitFor({ state: 'visible', timeout: 15_000 });
      if (await failed.isVisible()) {
        await page.locator(`[data-testid=${testid}-retry]`).click();
      }
      await option.click({ timeout: 15_000 });
      return;
    } catch (error) {
      const reloaded = (await loadedAt(page).catch(() => before)) !== before;
      if (!reloaded || attempt === 3) throw error;
    }
  }
}

async function fill(page: Page, testid: string, value: string): Promise<void> {
  const input = page.locator(`[data-testid=${testid}] input`).first();
  await input.fill(value);
  await input.blur();
}

/** No horizontal scroll: the page is not wider than the window (polled while the layout settles). */
async function noHorizontalScroll(page: Page, label: string): Promise<void> {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), { message: `no horizontal scroll at ${label}` })
    .toBeLessThanOrEqual(0);
}

/** Nothing inside `selector` reaches past the window's right edge (clipped content is not a scroll):
 *  the hooks of whatever does, with how far, so a failure says which element it is. */
async function nothingPastTheEdge(page: Page, selector: string, label: string): Promise<void> {
  await expect
    .poll(
      () =>
        page.evaluate((css) => {
          const past: string[] = [];
          for (const el of document.querySelectorAll(css)) {
            const box = el.getBoundingClientRect();
            if (box.width > 0 && box.right - window.innerWidth > 1) {
              past.push(`${el.getAttribute('data-testid')} +${Math.round(box.right - window.innerWidth)}px`);
            }
          }
          return past;
        }, selector),
      { message: `nothing past the right edge at ${label}` },
    )
    .toEqual([]);
}

async function shoot(page: Page, name: string, inside?: string): Promise<void> {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await noHorizontalScroll(page, `${name} ${viewport.label}`);
    if (inside) await nothingPastTheEdge(page, inside, `${name} ${viewport.label}`);
    await page.screenshot({ path: shot(`${name}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

/** Adds a course with the form at the foot of the builder and waits for its card. */
async function addCourse(page: Page, name: string): Promise<string> {
  await fill(page, 'combo-course-form-name', name);
  await shown(page).locator('[data-testid=combo-course-form-save]').click();
  const title = shown(page).locator('[data-testid$=-name]', { hasText: new RegExp(`^${name}$`) });
  await expect(title).toBeVisible();
  const testid = await title.getAttribute('data-testid');
  return testid!.replace(/^combo-course-/, '').replace(/-name$/, '');
}

/** Adds the product `code` to the course `id`, with `delta` as its supplement. */
async function addChoice(page: Page, id: string, code: string, text: string, delta = ''): Promise<void> {
  await pick(page, `combo-course-${id}-picker`, sku(code), text);
  if (delta) await fill(page, `combo-course-${id}-delta`, delta);
  await shown(page).locator(`[data-testid=combo-course-${id}-save]`).click();
  await expect(shown(page).locator(`[data-testid=combo-course-${id}] [data-testid^=combo-choice-]`, { hasText: text }).first()).toBeVisible();
}

test('COMBO-F02, F05, F06, F12: the owner builds the menu of the day from Inventory’s products', async ({ page, context }) => {
  await login(page, A, '/combo/menus');
  await shown(page).locator('[data-testid=combo-menus-row], [data-testid=combo-menus-empty]').first().waitFor();
  await product(context, 'LEN', 'Lentils', 700);
  await product(context, 'SAL', 'Salad', 650);
  await product(context, 'SOU', 'Soup', 600);
  await product(context, 'HAK', 'Hake', 1400);
  await product(context, 'WAT', 'Water', 200);
  // A restaurant tags its beer restaurant.alcohol (10 % at the table); to take away it is 21 %.
  await product(context, 'BEE', 'Beer', 200, 'restaurant.alcohol');
  await product(context, 'SAN', 'Sandwich', 450);

  // COMBO-F02: «+» → «New menu», eaten in at Taxes' «Restaurant — food».
  await shown(page).locator('[data-testid=combo-menus-add]').click();
  const form = page.locator('ion-modal[data-testid=combo-menu-form]');
  await expect(form).toBeVisible();
  await fill(page, 'combo-menu-form-name', MENU);
  await fill(page, 'combo-menu-form-price', '13,50');
  await expect(page.locator('[data-testid=combo-menu-form-help-service]')).toHaveAttribute('data-active', 'true');
  await pick(page, 'combo-menu-form-tax_category', 'food', 'Restaurant — food');
  await shoot(page, 'combo-menu-form', 'ion-modal[data-testid=combo-menu-form] [data-testid]');
  await page.locator('[data-testid=combo-menu-form-submit]').click();
  await expect(form).toBeHidden();
  const row = shown(page).locator('[data-testid=combo-menus-row]', { hasText: MENU });
  await expect(row).toContainText('€13.50');
  await expect(row).toContainText('Eat in');

  // The row opens the builder: no course yet, so the till does not offer it.
  await row.click();
  await page.waitForURL(/\/combo\/menus\/[0-9a-f-]+$/);
  await expect(shown(page).locator('[data-testid=combo-builder-name]')).toHaveText(MENU);
  await expect(shown(page).locator('[data-testid=combo-builder-supply]')).toContainText('one line at its VAT category');
  await expect(shown(page).locator('[data-testid=combo-builder-empty]')).toBeVisible();
  await expect(shown(page).locator('[data-testid=combo-builder-blockers]')).toContainText('No course has a choice on offer.');

  // COMBO-F05 and F06: Starters (lentils, salad −0,50), Mains (hake +2,00), Drink (water).
  const starters = await addCourse(page, 'Starters');
  await addChoice(page, starters, 'LEN', 'Lentils');
  await addChoice(page, starters, 'SAL', 'Salad', '-0,50');
  const mains = await addCourse(page, 'Mains');
  await addChoice(page, mains, 'HAK', 'Hake', '2');
  const drink = await addCourse(page, 'Drink');
  await addChoice(page, drink, 'WAT', 'Water');
  await expect(shown(page).locator(`[data-testid=combo-course-${starters}-rule]`)).toHaveText('Compulsory · pick 1 · up to 1 · no repeats');
  await expect(shown(page).locator(`[data-testid=combo-course-${mains}]`)).toContainText('+€2.00');
  await expect(shown(page).locator('[data-testid=combo-builder-blockers]')).toHaveCount(0);

  // The same product twice in a course is refused before anything is sent.
  await pick(page, `combo-course-${starters}-picker`, sku('LEN'), 'Lentils');
  await shown(page).locator(`[data-testid=combo-course-${starters}-save]`).click();
  await expect(shown(page).locator(`[data-testid=combo-course-${starters}-reason]`)).toContainText('This course already offers that product.');

  // COMBO-F12: water sold out → the drink course has nothing on offer → off the till, and back.
  const water = shown(page).locator(`[data-testid=combo-course-${drink}] [data-testid^=combo-choice-][data-status]`).first();
  const waterId = (await water.getAttribute('data-testid'))!.replace('combo-choice-', '');
  await shown(page).locator(`[data-testid=combo-choice-${waterId}-availability]`).click();
  await expect(shown(page).locator(`[data-testid=combo-choice-${waterId}-status]`)).toHaveText('Sold out');
  await expect(shown(page).locator('[data-testid=combo-builder-blockers]')).toContainText('The course “Drink” has fewer choices on offer than it asks for.');
  await shown(page).locator(`[data-testid=combo-choice-${waterId}-availability]`).click();
  await expect(shown(page).locator(`[data-testid=combo-choice-${waterId}-status]`)).toHaveCount(0);

  // The order: Mains up, saved whole, and it stays after a reload.
  await shown(page).locator(`[data-testid=combo-course-${mains}-up]`).click();
  const order = () => shown(page).locator('[data-testid=combo-builder-courses] > section [data-testid$=-name]').allTextContents();
  await expect.poll(order).toEqual(['Mains', 'Starters', 'Drink']);
  await page.reload();
  await expect.poll(order).toEqual(['Mains', 'Starters', 'Drink']);
  await shoot(page, 'combo-builder', '.ion-page:not(.ion-page-hidden) .combo-builder [data-testid]');
});

/** The id of the course called `name` in the builder shown. */
async function courseId(page: Page, name: string): Promise<string> {
  const title = shown(page).locator('[data-testid^=combo-course-][data-testid$=-name]', { hasText: new RegExp(`^${name}$`) });
  return (await title.getAttribute('data-testid'))!.replace(/^combo-course-/, '').replace(/-name$/, '');
}

/** The products of course `id`, in the order shown. */
const choicesOf = (page: Page, id: string) =>
  shown(page).locator(`[data-testid=combo-course-${id}] [data-testid^=combo-choice-][data-status] .combo-course__choice-name`).allTextContents();

const dish = (name: string): string => `${TAG} ${name} ${STAMP}`;

test('COMBO-F03, F05, F06: several dishes at once, choices and courses changed, the menu off sale and back', async ({ page, context }) => {
  await login(page, A, '/combo/menus');
  await page.goto(`${A}/combo/menus/${await menuId(context)}`);
  await expect(shown(page).locator('[data-testid=combo-builder-name]')).toHaveText(MENU);
  const starters = await courseId(page, 'Starters');

  // «Add several»: Soup ticked among the products of this run; Lentils is already in, greyed.
  await shown(page).locator(`[data-testid=combo-course-${starters}-bulk]`).click();
  // Every course card has its own picker and confirmation: the one presented is the visible one.
  const bulk = page.locator('ion-modal[data-testid=combo-bulk]:visible');
  await expect(bulk).toBeVisible();
  await page.locator('[data-testid=combo-bulk-search] input').fill(STAMP);
  await expect(page.locator(`[data-testid=combo-bulk-item-${made.LEN}]`)).toContainText('Already in this course');
  await page.locator(`[data-testid=combo-bulk-row-${made.SOU}]`).click();
  await expect(page.locator('[data-testid=combo-bulk-submit]')).toContainText('Add 1 selected');
  await page.locator('[data-testid=combo-bulk-submit]').click();
  await expect(bulk).toBeHidden();
  await expect.poll(() => choicesOf(page, starters)).toEqual([dish('Lentils'), dish('Salad'), dish('Soup')]);

  // Edit a choice: its supplement changes and it keeps its place.
  const salad = shown(page).locator(`[data-testid=combo-course-${starters}] [data-testid^=combo-choice-][data-status]`, { hasText: 'Salad' });
  const saladId = (await salad.getAttribute('data-testid'))!.replace('combo-choice-', '');
  await shown(page).locator(`[data-testid=combo-choice-${saladId}-edit]`).click();
  await expect(shown(page).locator(`[data-testid=combo-course-${starters}-editing]`)).toContainText('It keeps its position in the course.');
  await fill(page, `combo-course-${starters}-delta`, '-1');
  await shown(page).locator(`[data-testid=combo-course-${starters}-save]`).click();
  await expect(salad).toContainText('-€1.00');
  await expect.poll(() => choicesOf(page, starters)).toEqual([dish('Lentils'), dish('Salad'), dish('Soup')]);

  // Reorder a choice with its arrow, then remove one after its confirmation.
  const lentils = shown(page).locator(`[data-testid=combo-course-${starters}] [data-testid^=combo-choice-][data-status]`, { hasText: 'Lentils' });
  const lentilsId = (await lentils.getAttribute('data-testid'))!.replace('combo-choice-', '');
  await shown(page).locator(`[data-testid=combo-choice-${lentilsId}-down]`).click();
  await expect.poll(() => choicesOf(page, starters)).toEqual([dish('Salad'), dish('Lentils'), dish('Soup')]);
  const soup = shown(page).locator(`[data-testid=combo-course-${starters}] [data-testid^=combo-choice-][data-status]`, { hasText: 'Soup' });
  const soupId = (await soup.getAttribute('data-testid'))!.replace('combo-choice-', '');
  await shown(page).locator(`[data-testid=combo-choice-${soupId}-delete]`).click();
  await expect(page.locator('ion-modal[data-testid=combo-choice-delete]:visible')).toContainText('Remove «');
  await page.locator('[data-testid=combo-choice-delete-submit]').click();
  await expect.poll(() => choicesOf(page, starters)).toEqual([dish('Salad'), dish('Lentils')]);

  // Edit a course: Mains takes up to two.
  const mains = await courseId(page, 'Mains');
  await shown(page).locator(`[data-testid=combo-course-${mains}-edit]`).click();
  await expect(shown(page).locator('[data-testid=combo-course-form-title]')).toHaveText('Course · Mains');
  await fill(page, 'combo-course-form-max', '2');
  await shown(page).locator('[data-testid=combo-course-form-save]').click();
  await expect(shown(page).locator(`[data-testid=combo-course-${mains}-rule]`)).toHaveText('Compulsory · pick at least 1 · up to 2 · no repeats');

  // Withdraw a course after its confirmation.
  const dessert = await addCourse(page, 'Dessert');
  await shown(page).locator(`[data-testid=combo-course-${dessert}-delete]`).click();
  await expect(page.locator('ion-modal[data-testid=combo-course-delete]')).toContainText('Remove the course «Dessert» and its choices?');
  await page.locator('[data-testid=combo-course-delete-submit]').click();
  await expect(shown(page).locator(`[data-testid=combo-course-${dessert}]`)).toHaveCount(0);

  // COMBO-F03: «Edit details» on the list: 14,00 € and off sale; the till stops offering it; back on sale.
  await page.goto(`${A}/combo/menus`);
  await shown(page).locator('[data-testid=combo-menus-search] input').fill(STAMP);
  const id = await menuId(context);
  const row = shown(page).locator(`[data-testid=combo-menus-row][data-id="${id}"]`);
  await expect(row).toBeVisible();
  const edit = async () => {
    const action = shown(page).locator(`[data-testid=combo-menus-row-${id}-edit]`);
    const menu = shown(page).locator(`[data-testid=combo-menus-row-${id}-menu]`);
    await action.or(menu).first().waitFor({ state: 'visible' });
    if (await action.isVisible()) await action.click();
    else {
      await menu.click();
      await page.locator(`ion-popover [data-testid=combo-menus-row-${id}-edit]`).click();
    }
    await expect(page.locator('ion-modal[data-testid=combo-menu-form]')).toBeVisible();
  };
  await edit();
  // Ionic moves the dialog's name into its shadow root: its title is what the person reads.
  await expect(page.locator('ion-modal[data-testid=combo-menu-form]')).toContainText(`Menu · ${MENU}`);
  await fill(page, 'combo-menu-form-price', '14');
  await page.locator('[data-testid=combo-menu-form-is_active]').click();
  await page.locator('[data-testid=combo-menu-form-submit]').click();
  await expect(row).toContainText('€14.00');
  await expect(row).toContainText('No');
  const offered = async () =>
    (await call<{ rows: { name: string }[] }>(context, 'GET', `/combo/combos/for_sale?search=${encodeURIComponent(STAMP)}`)).rows.map((r) => r.name);
  expect(await offered()).toEqual([]);
  await edit();
  await page.locator('[data-testid=combo-menu-form-is_active]').click();
  await page.locator('[data-testid=combo-menu-form-submit]').click();
  await expect(row).toContainText('Yes');
  expect(await offered()).toEqual([MENU]);
});

test('COMBO-F07, F08, F09: the till sells it, priced with its supplements, eaten in or to take away', async ({ page, context }) => {
  await login(page, A, '/combo/menus');
  const forSale = await call<{ rows: { name: string; groups: { name: string }[] }[] }>(context, 'GET', `/combo/combos/for_sale?search=${encodeURIComponent(MENU)}`);
  expect(forSale.rows.map((row) => [row.name, row.groups.map((g) => g.name)])).toEqual([[MENU, ['Mains', 'Starters', 'Drink']]]);
  const resolve = (query: string) => call<Line>(context, 'GET', `/combo/combos/resolve?${query}`);
  // 14,00 − 1,00 (salad) + 2,00 (hake), one line at restaurant.food; the dishes in the order of the courses.
  const eatenIn = await resolve(`combo=${encodeURIComponent(MENU)}&${picks('SAL', 'HAK', 'WAT')}`);
  expect([eatenIn.amount, eatenIn.split, eatenIn.tax_category_key]).toEqual([1500, false, 'restaurant.food']);
  expect(eatenIn.components.map((c) => c.product_name)).toEqual([dish('Hake'), dish('Salad'), dish('Water')]);

  // The same menu with a beer, ordered to take away (Ventas' channel): split, the beer at 21 %.
  const menu = await call<Detail>(context, 'GET', `/combo/combos/detail?combo=${encodeURIComponent(MENU)}`);
  const drink = menu.groups.find((g) => g.name === 'Drink')!;
  await call(context, 'POST', '/combo/options', { group_id: drink.id, product: sku('BEE') }, 201);
  const toGo = await resolve(`combo=${encodeURIComponent(MENU)}&channel=takeaway&${picks('SAL', 'HAK', 'BEE')}`);
  expect([toGo.supply_kind, toGo.split]).toEqual(['goods', true]);
  expect(toGo.components.map((c) => [c.product_name, c.tax_category_key])).toEqual([
    [dish('Hake'), 'restaurant.food'],
    [dish('Salad'), 'restaurant.food'],
    [dish('Beer'), 'retail.alcohol'],
  ]);
  expect(toGo.components.reduce((sum, c) => sum + (c.amount ?? 0), 0)).toBe(1500);

  // COMBO-F09: a pack sold to take away, split in proportion to the catalogue: 6,00 → 4,15 + 1,85.
  await call(context, 'POST', '/combo/combos', { name: PACK, price: 600, supply_kind: 'goods' }, 201);
  for (const [course, code] of [
    ['Sandwich', 'SAN'],
    ['Drink', 'BEE'],
  ]) {
    await call(context, 'POST', '/combo/groups', { combo: PACK, name: course }, 201);
    await call(context, 'POST', '/combo/options', { combo: PACK, group: course, product: sku(code) }, 201);
  }
  const pack = await resolve(`combo=${encodeURIComponent(PACK)}&${picks('SAN', 'BEE')}`);
  expect(pack.split).toBe(true);
  expect(pack.components.map((c) => [c.tax_category_key, c.amount])).toEqual([
    ['restaurant.food', 415],
    ['retail.alcohol', 185],
  ]);
});

test('COMBO-F13: a product deactivated in Inventory shows up live in the builder', async ({ page, context }) => {
  await login(page, A, '/combo/menus');
  await page.goto(`${A}/combo/menus/${await menuId(context)}`);
  await expect(shown(page).locator('[data-testid=combo-builder-name]')).toHaveText(MENU);
  await call(context, 'POST', '/inventory/products/update', { product: sku('HAK'), is_active: false });
  const hake = shown(page).locator('[data-testid^=combo-choice-][data-status]', { hasText: 'Hake' });
  await expect(hake.locator('[data-testid$=-status]')).toHaveText('Deactivated in Inventory');
  await expect(shown(page).locator('[data-testid=combo-builder-blockers]')).toContainText('The course “Mains” has fewer choices on offer than it asks for.');
  await call(context, 'POST', '/inventory/products/update', { product: sku('HAK'), is_active: true });
  await expect(hake.locator('[data-testid$=-status]')).toHaveCount(0);
});

// flow: ninguno — FIX de una carrera: el detalle de un menú borrado a la vez da 500 en vez de 404
test('a menu withdrawn from another tab while its builder is open says it no longer exists', async ({ page, context }) => {
  const name = `${TAG} Gone ${STAMP}`;
  await login(page, A, '/combo/menus');
  const gone = await call<Detail>(context, 'POST', '/combo/combos', { name, price: 1000, tax_category_key: 'restaurant.food' }, 201);
  await page.goto(`${A}/combo/menus/${gone.id}`);
  await expect(shown(page).locator('[data-testid=combo-builder-name]')).toHaveText(name);
  await expect(shown(page).locator('[data-testid=combo-course-form-name]')).toBeVisible();
  // The other tab: the same withdrawal the list's «Withdraw» makes.
  await call(context, 'POST', '/combo/combos/delete', { id: gone.id });
  await expect(shown(page).locator('[data-testid=combo-builder-gone]')).toContainText('This menu no longer exists');
  await expect(shown(page).locator('[data-testid=combo-builder-name], [data-testid=combo-course-form-name], [data-testid=combo-builder-error]')).toHaveCount(0);
  await shoot(page, 'FIX-COMBO-DETAIL-RACE', '.ion-page:not(.ion-page-hidden) [data-testid^=combo-builder]');
  await shown(page).locator('[data-testid=combo-builder-back]').click();
  await expect(page).toHaveURL(/\/combo\/menus$/);
});

test('COMBO-F01, F04: the list finds the menu and withdraws it after its confirmation', async ({ page, context }) => {
  await login(page, A, '/combo/menus');
  const id = await menuId(context);
  await shown(page).locator('[data-testid=combo-menus-search] input').fill(STAMP);
  const row = shown(page).locator(`[data-testid=combo-menus-row][data-id="${id}"]`);
  await expect(row).toBeVisible();
  await shoot(page, 'combo-menus', '.ion-page:not(.ion-page-hidden) [data-testid^=combo-menus]');
  const action = shown(page).locator(`[data-testid=combo-menus-row-${id}-delete]`);
  const menu = shown(page).locator(`[data-testid=combo-menus-row-${id}-menu]`);
  await action.or(menu).first().waitFor({ state: 'visible' });
  if (await action.isVisible()) await action.click();
  else {
    await menu.click();
    await page.locator(`ion-popover [data-testid=combo-menus-row-${id}-delete]`).click();
  }
  const dialog = page.locator('ion-modal[data-testid=combo-menus-delete]');
  await expect(dialog).toContainText(`«${MENU}» stops being on sale`);
  await page.locator('[data-testid=combo-menus-delete-submit]').click();
  await expect(row).toHaveCount(0);
  expect((await api(context, A, 'GET', `/combo/combos/detail?id=${id}`)).status).toBe(404);
});
