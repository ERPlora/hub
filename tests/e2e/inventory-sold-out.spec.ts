// flow: INVENTORY-F29, INVENTORY-F27 — an article marked sold out («86») in Inventory stops being sold in
// the till (apps/inventory/WORKBOOK.md; the old QA flow qa:modules/sales/sold-out-item-86), against the
// real Sales and Taxes apps, no doubles:
//   - «Mark sold out» in the row's menu: the «Sold out» mark beside the switch, which stays on, and the
//     till open in another tab greys it out with «Sold out» without a reload (its grid and its search,
//     SALE-F07), while the article next to it sells as always; «Put back on sale» brings it back the same way;
//   - the counts of the till's strip («All» and the category) count what its grid shows, the greyed tile
//     included (FIX-INVENTORY-SOLD-OUT-GREYED-IN-POS), also on a till opened after the mark;
//   - the product sheet marks and unmarks it too, and says so beside its status;
//   - a menu whose only dessert is sold out leaves the till (COMBO-F06), its editor says «Sold out in
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
  shootFlow,
  stamp,
} from './inventory-helpers';
import { drawerOff, restoreDrawer } from './sale-helpers';

const RUN = stamp();
let croquettes: Product;
let bread: Product;
let flan: Product;
/** The croquettes and the bread, a category of their own in the till's strip. */
let starters: { id: string };
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
  const category = await api<{ id: string }>(context, A, 'POST', '/inventory/categories', { name: `E2E 86 Starters ${RUN}` });
  expect(category.status, 'category').toBe(201);
  starters = category.data;
  const inStarters = { category_ids: [starters.id] };
  croquettes = await createProduct(context, { name: `E2E Croquettes ${RUN}`, sku: `E2E-86-C-${RUN}`, price: 650, ...inStarters });
  bread = await createProduct(context, { name: `E2E Bread ${RUN}`, sku: `E2E-86-B-${RUN}`, price: 120, ...inStarters });
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

/** The count beside a tab of the till's strip («2 items»): `all` or a category's id. */
const stripCount = (page: Page, tab: string): Locator => shown(page).locator(`[data-testid=pos-category-${tab}] .pos-cat__count`);

/** The till greys a sold-out article out with «Sold out» and will not take it (SALE-F07); on sale, it is a plain tile. */
async function expectSoldOutTile(page: Page, product: Product, soldOut: boolean): Promise<void> {
  const shownTile = tile(page, product);
  await expect(shownTile).toHaveCount(1);
  if (soldOut) {
    await expect(shownTile).toHaveAttribute('aria-disabled', 'true');
    await expect(shownTile).toContainText(/Sold out|Agotado/);
  } else {
    await expect(shownTile).not.toHaveAttribute('aria-disabled', 'true');
    await expect(shownTile).not.toContainText(/Sold out|Agotado/);
  }
}

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

/** What hides part of the switch or the «Sold out» mark beside it in the row's status (none = both whole): a part is
 *  in sight when it lies inside the cell (or the card's value) and inside every box between them that clips, shadow
 *  roots crossed — the switch's own track included. In a narrow column the mark goes under the switch, never over it
 *  (review of FIX-INVENTORY-PRODUCTS-UNCONFIGURED-CHIP-CLIPPED: at 834 the switch was cut to its first half). */
async function statusProblems(page: Page, product: Product): Promise<string[]> {
  return soldOutMark(page, product).evaluate((mark) => {
    const px = (n: number) => Math.round(n * 10) / 10;
    const box = mark.closest('[role=cell], .data-table__field-value');
    if (!box) return ['no cell around the mark'];
    const parentOf = (node: Element): Element | null => node.parentElement ?? ((node.getRootNode() as ShadowRoot).host || null);
    const problemOf = (name: string, node: Element | null | undefined): string[] => {
      if (!node) return [`no ${name}`];
      const r = node.getBoundingClientRect();
      const c = box.getBoundingClientRect();
      let left = c.left;
      let right = c.right;
      for (let up = parentOf(node); up && up !== box; up = parentOf(up)) {
        if (getComputedStyle(up).overflowX === 'visible') continue;
        const u = up.getBoundingClientRect();
        left = Math.max(left, u.left);
        right = Math.min(right, u.right);
      }
      const ok = r.width >= 1 && r.left >= left - 0.5 && r.right <= right + 0.5;
      return ok ? [] : [`the ${name} (${px(r.left)}–${px(r.right)}) is cut by its box (${px(left)}–${px(right)})`];
    };
    const toggle = box.querySelector('ion-toggle');
    const squeezed = mark.scrollWidth > mark.clientWidth ? [`the mark's text is cut (${mark.scrollWidth} > ${mark.clientWidth})`] : [];
    return [...problemOf('switch', toggle?.shadowRoot?.querySelector('[part~=track]')), ...problemOf('mark', mark), ...squeezed];
  });
}

/** `statusProblems` once the layout settles: the table refits its columns after a resize and a step on its way may
 *  look right, so a measurement counts only when the next one finds it unchanged. */
async function expectWholeStatus(page: Page, product: Product, message: string): Promise<void> {
  let last = '';
  await expect
    .poll(
      async () => {
        const problems = await statusProblems(page, product);
        const now = JSON.stringify(problems);
        const settled = now === last;
        last = now;
        return settled ? problems : ['settling'];
      },
      { message },
    )
    .toEqual([]);
}

test('INVENTORY-F29 / INVENTORY-F27: «Mark sold out» greys the article out in the till live; «Put back on sale» brings it back', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const till = page;
  await tillReady(till);
  await expectSoldOutTile(till, croquettes, false);
  await expect(stripCount(till, starters.id)).toHaveText(/^2\b/);
  await expect(stripCount(till, 'all')).toHaveText(/^\d+\b/);
  const allBefore = (await stripCount(till, 'all').textContent())!;

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
    await expectWholeStatus(office, croquettes, `status at ${size.label}`);
    await office.screenshot({ path: shot(`FIX-INVENTORY-SOLD-OUT-86-${size.label}`) });
  }
  await office.setViewportSize({ width: 1440, height: 900 });

  // The till, open all along, greys it out without a reload, in its grid and in its search; the bread sells.
  await till.bringToFront();
  await expectSoldOutTile(till, croquettes, true);
  await expectSoldOutTile(till, bread, false);
  const search = await searchTill(till);
  await expect(search.locator(`[data-testid=pos-search-${croquettes.id}]`)).toHaveAttribute('aria-disabled', 'true');
  await expect(search.locator(`[data-testid=pos-search-${croquettes.id}]`)).toContainText(/Sold out|Agotado/);
  await search.locator('[data-testid=pos-search-close]').click();
  await expect(search).toBeHidden();
  await till.screenshot({ path: shot('inventory-sold-out-till-1440') });

  // The strip counts what the grid shows, the greyed tile included, on a till opened now as well: the
  // category keeps its 2 and «All» what it said before the mark.
  await till.goto(`${A}/sale/pos`);
  await tillReady(till);
  await expectSoldOutTile(till, croquettes, true);
  await expect(stripCount(till, starters.id)).toHaveText(/^2\b/);
  await expect(stripCount(till, 'all')).toHaveText(allBefore);

  // Back on sale: the mark goes and the till offers it again, live.
  await office.bringToFront();
  await rowAction(office, croquettes.id, 'back_on_sale');
  await expect(soldOutMark(office, croquettes)).toHaveCount(0);
  expect((await productBySku(context, croquettes.sku)).is_sold_out).toBe(false);
  await till.bringToFront();
  await expectSoldOutTile(till, croquettes, false);
  const again = await searchTill(till);
  await expect(again.locator(`[data-testid=pos-search-${croquettes.id}]`)).toBeVisible();
  await expect(again.locator(`[data-testid=pos-search-${croquettes.id}]`)).not.toHaveAttribute('aria-disabled', 'true');
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
  await shootFlow(page, 'INVENTORY-F29', { width: 834, height: 1112 });

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
  // Live, without a reload: the flan greys out, the menu it completes leaves the till; the bread sells.
  await expectSoldOutTile(page, flan, true);
  await expect(tileOfMenu).toHaveCount(0);
  await expectSoldOutTile(page, bread, false);

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
  await expectSoldOutTile(page, flan, false);
});
