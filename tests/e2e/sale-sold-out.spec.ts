// flow: SALE-F07 (apps/sale/WORKBOOK.md), with INVENTORY-F29 — an article marked sold out («86») in Inventory
// stays in the till, greyed with «Sold out»: a tap adds nothing and says why, and its search row says it
// too, while the article next to it still sells. Through the API (the assistant's way, which never sees the
// grid) a new line of it is a 409 `sale.product_sold_out` and nothing is written. What was ordered before it
// sold out is still charged (apps/sale/tests/test_integration_inventory.py). The notice of a refused tap goes on
// its own once the article is back on sale, and on leaving the till for another screen (hub#442). Screenshots of
// the till in the three viewports. What this file creates is deleted after it.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import {
  type Box,
  cleanSales,
  drawerOff,
  expectTakes,
  linesOf,
  openTillCart,
  restoreDrawer,
  saleByKey,
  stamp,
  TILL_TILE,
  tillGrid,
  tillIsPhone,
} from './sale-helpers';

const RUN = stamp();
let croquettes: Product;
let bread: Product;

/** The widths of this task's screenshots, as the SaaS panel's `VIEWPORTS`. */
const SHOTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  croquettes = await createProduct(context, { name: `E2E Croquettes ${RUN}`, sku: `E2E-SO-C-${RUN}`, price: 650, tax_category_key: 'restaurant.food' });
  bread = await createProduct(context, { name: `E2E Bread ${RUN}`, sku: `E2E-SO-B-${RUN}`, price: 120, tax_category_key: 'restaurant.food' });
  const marked = await api<{ is_sold_out: boolean }>(context, A, 'POST', '/inventory/products/sold_out', { id: croquettes.id, sold_out: true });
  expect(marked.status, 'mark sold out').toBe(200);
  await context.close();
});

test.afterAll(() => {
  cleanSales();
  cleanInventory();
  restoreDrawer();
});

const tile = (page: Page, product: Product): Locator => shown(page).locator(`[data-testid=pos-product-${product.id}]`);

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await tile(page, bread).waitFor({ state: 'visible' });
}

/** Opens `path` from inside the Hub, as one of its links does: the SPA's router, no page load (Ionic keeps the
 *  till mounted under the screen it opens, and brings that same till back). */
async function openInside(page: Page, path: string): Promise<void> {
  type Mounted = { __vue_app__: { config: { globalProperties: { $router: { push: (to: string) => Promise<unknown> } } } } };
  await page.evaluate(
    (to) => (document.querySelector('#app') as unknown as Mounted).__vue_app__.config.globalProperties.$router.push(to),
    path,
  );
}

test('SALE-F07: a sold-out article is greyed «Sold out» in the till; a tap adds nothing and says why', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);

  // In the grid, greyed with its badge; the article beside it sells as always.
  const soldOut = tile(page, croquettes);
  await expect(soldOut).toBeVisible();
  await expect(soldOut).toHaveClass(/pos-tile--sold-out/);
  await expectTakes(soldOut, false);
  await expect(soldOut.locator('.pos-tile__badge')).toHaveText(/^(Sold out|Agotado)$/);
  await expect(tile(page, bread)).not.toHaveClass(/pos-tile--sold-out/);

  // A tap adds nothing: the reason goes above the grid. The tile is `aria-disabled` but takes the tap (a
  // touchscreen would swallow a native `disabled`), so the mouse clicks it as a finger would.
  await soldOut.click({ force: true });
  const notice = shown(page).locator('[data-testid=pos-tap-notice]');
  await expect(notice).toHaveText(new RegExp(`^«${croquettes.name}» (is sold out|está agotado)\\.$`));
  await expect(linesOf(page, croquettes)).toHaveCount(0);

  // The search finds it and says it is sold out instead of its SKU; picking it adds nothing either.
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(croquettes.sku);
  const row = search.locator(`[data-testid=pos-search-${croquettes.id}]`);
  await expectTakes(row, false);
  await expect(search.locator(`[data-testid=pos-search-${bread.id}]`)).toHaveCount(0);
  await expect(row.locator('.pos-search__note')).toHaveText(/^(Sold out|Agotado)$/);
  await page.screenshot({ path: shot('FIX-SALE-SOLD-OUT-LINE-ACCEPTED-search-1440') });
  await row.click({ force: true });
  await expect(search).toBeHidden();
  await expect(notice).toHaveText(new RegExp(`^«${croquettes.name}» (is sold out|está agotado)\\.$`));
  await expect(linesOf(page, croquettes)).toHaveCount(0);

  // In each viewport, a till opened there (on a phone the check is the drawer behind the button): the
  // greyed tile, a tap that adds nothing and its reason above the grid.
  for (const size of SHOTS) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto(`${A}/sale/pos`);
    await tillReady(page);
    await tile(page, croquettes).click({ force: true });
    await expect(notice).toHaveText(new RegExp(`^«${croquettes.name}» (is sold out|está agotado)\\.$`));
    await expect(tile(page, croquettes).locator('.pos-tile__badge')).toBeVisible();
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({ path: shot(`FIX-SALE-SOLD-OUT-LINE-ACCEPTED-${size.label}`) });
  }

  // The article on sale still goes into the check.
  await page.setViewportSize({ width: 1440, height: 900 });
  await tile(page, bread).click();
  await openTillCart(page);
  await expect(linesOf(page, bread).first()).toBeVisible();
  await expect(linesOf(page, croquettes)).toHaveCount(0);
});

test('SALE-F07: through the API a new line of a sold-out article is a 409 and nothing is written', async ({ page, context }) => {
  await login(page, A, '/sale/pos');
  const opened = await api<{ error: { code: string; message: string } }>(context, A, 'POST', '/sale/orders', {
    label: `e2e sold out ${RUN}`,
    lines: [{ product: croquettes.sku }],
  });
  expect(opened.status).toBe(409);
  expect(opened.data.error.code).toBe('sale.product_sold_out');
  expect(opened.data.error.message).toMatch(new RegExp(`^«${croquettes.name}» (is sold out|está agotado)\\.$`));
  const charged = await api<{ error: { code: string } }>(context, A, 'POST', '/sale/sales', {
    idempotency_key: `e2e-sold-out-${RUN}`,
    lines: [{ product: croquettes.name }],
    payments: [{ method: 'card' }],
  });
  expect(charged.status).toBe(409);
  expect(charged.data.error.code).toBe('sale.product_sold_out');
  expect(await saleByKey(context, `e2e-sold-out-${RUN}`)).toBeNull();
});

test('SALE-F07 (hub#442): the sold-out notice goes on its own once the article is back on sale, and on leaving the till', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const bravas = await createProduct(context, { name: `E2E Bravas ${RUN}`, sku: `E2E-SO-P-${RUN}`, price: 550, tax_category_key: 'restaurant.food' });
  const mark = async (soldOut: boolean) => {
    const res = await api(context, A, 'POST', '/inventory/products/sold_out', { id: bravas.id, sold_out: soldOut });
    expect(res.status, `sold_out=${soldOut}`).toBe(200);
  };
  const notice = shown(page).locator('[data-testid=pos-tap-notice]');
  const said = new RegExp(`^«${bravas.name}» (is sold out|está agotado)\\.$`);
  await mark(true);
  await page.goto(`${A}/sale/pos`);
  await tillReady(page);
  await expect(tile(page, bravas)).toHaveClass(/pos-tile--sold-out/);
  await tile(page, bravas).click({ force: true });
  await expect(notice).toHaveText(said);

  // Inventory puts it back on sale (another device, the assistant): the till hears it, and the notice goes
  // without another tap; nothing went into the check.
  await mark(false);
  await expect(tile(page, bravas)).not.toHaveClass(/pos-tile--sold-out/);
  await expect(notice).toBeHidden();
  await expect(linesOf(page, bravas)).toHaveCount(0);
  for (const size of SHOTS) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(tile(page, bravas)).toBeVisible();
    // On a phone the check becomes a drawer that slides away (0.25 s): the shot waits until it is gone.
    if (await tillIsPhone(page)) await expect(shown(page).locator('[data-testid=pos-cart-drawer]')).toBeHidden();
    await capture(page, `HUB-442-back-on-sale-${size.label}`);
  }

  // Sold out again and refused again; off to Inventory and back to the till inside the Hub: the notice is gone.
  await page.setViewportSize({ width: 1440, height: 900 });
  await mark(true);
  await expect(tile(page, bravas)).toHaveClass(/pos-tile--sold-out/);
  await tile(page, bravas).click({ force: true });
  await expect(notice).toHaveText(said);
  await openInside(page, '/inventory/products');
  await expect(shown(page).locator('[data-testid=pos-till]')).toHaveCount(0);
  await openInside(page, '/sale/pos');
  await tillReady(page);
  await expect(tile(page, bravas)).toHaveClass(/pos-tile--sold-out/);
  await expect(shown(page).locator('[data-testid=pos-tap-notice]')).toHaveCount(0);
});

/** One tile of the grid on screen: its frames (the tile and its native button, both of which clip what does not fit; the
 *  button's content goes through its slot, so a sweep of the page does not see the cut), its photo and its texts. */
interface TileParts {
  id: string;
  frames: Box[];
  photo: Box | null;
  texts: Record<string, Box | null>;
}

/** Every tile of `grid` (run in the page, `tillGrid(page).evaluate(tilesOf, TILL_TILE)`). */
function tilesOf(grid: Element, selector: string): TileParts[] {
  const box = (node: Element | null | undefined): Box | null => {
    if (!node) return null;
    const r = node.getBoundingClientRect();
    return { top: r.top, bottom: r.bottom, left: r.left, right: r.right };
  };
  return [...grid.querySelectorAll(selector)].map((tile) => ({
    id: tile.getAttribute('data-testid') ?? '',
    frames: [box(tile)!, box(tile.shadowRoot?.querySelector('button'))!],
    photo: box(tile.querySelector('.pos-tile__thumb')),
    texts: Object.fromEntries(['name', 'badge', 'price'].map((part) => [part, box(tile.querySelector(`.pos-tile__${part}`))])),
  }));
}

/** How far apart the highest and the lowest of `values` are. */
const spread = (values: number[]): number => Math.max(...values) - Math.min(...values);

const TILE_SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1440', width: 1440, height: 900 },
] as const;

// Last in the file: the articles it adds stay until the file's cleanup.
test.describe('SALE-F07 (hub#1366): a catalogue longer than the screen', () => {
  // More tiles than fit in the grid at any of the sizes, as a real catalogue: the grid scrolls and has no room to spare.
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ baseURL: A });
    const page = await context.newPage();
    await login(page, A, '/sale/pos');
    for (let n = 1; n <= 24; n++) {
      await createProduct(context, { name: `E2E Filler ${RUN} ${n}`, sku: `E2E-SO-F${n}-${RUN}`, price: 300, tax_category_key: 'restaurant.food' });
    }
    await context.close();
  });

  for (const size of TILE_SIZES) {
    test(`a sold-out tile shows its name, «Sold out» and its price whole at ${size.label}, lined up with the tiles beside it`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await login(page, A, '/sale/pos');
      await tillReady(page);
      await expect(tile(page, croquettes).locator('.pos-tile__badge')).toBeVisible();
      // The cut only shows in a grid with no room to spare: in one that does not scroll, a fixed-height tile passes too.
      const scrolls = await tillGrid(page).evaluate((grid) => grid.scrollHeight > grid.clientHeight);
      expect(scrolls, `the grid scrolls at ${size.label}: the catalogue is longer than the screen`).toBe(true);
      const tiles = await tillGrid(page).evaluate(tilesOf, TILL_TILE);
      const soldOut = tiles.find((each) => each.id === `pos-product-${croquettes.id}`);
      expect(soldOut?.texts.badge, `${croquettes.name} in the grid with its «Sold out»`).toBeTruthy();

      for (const each of tiles) {
        for (const [part, text] of Object.entries(each.texts)) {
          if (!text) continue;
          for (const frame of each.frames) {
            const where = `${each.id} at ${size.label}: its ${part} ${JSON.stringify(text)} inside its tile ${JSON.stringify(frame)}`;
            expect.soft(text.top, where).toBeGreaterThanOrEqual(frame.top - 0.5);
            expect.soft(text.bottom, where).toBeLessThanOrEqual(frame.bottom + 0.5);
            expect.soft(text.left, where).toBeGreaterThanOrEqual(frame.left - 0.5);
            expect.soft(text.right, where).toBeLessThanOrEqual(frame.right + 0.5);
          }
        }
      }

      // A row is as tall as its tallest tile; the others in it keep their photo at the top, their name under it and
      // their price at the bottom, on the same lines as the sold-out tile's.
      const rows = new Map<number, TileParts[]>();
      for (const each of tiles) rows.set(Math.round(each.frames[0].top), [...(rows.get(Math.round(each.frames[0].top)) ?? []), each]);
      expect(rows.get(Math.round(soldOut!.frames[0].top))!.length, `the sold-out tile has others beside it at ${size.label}`).toBeGreaterThan(1);
      for (const [top, row] of rows) {
        const ids = row.map((each) => each.id).join(', ');
        for (const each of row) {
          expect.soft(Math.abs(each.photo!.top - each.frames[1].top), `${each.id} at ${size.label}: its photo at the top of its tile`).toBeLessThanOrEqual(1);
        }
        expect.soft(spread(row.map((each) => each.texts.name!.top)), `the row at ${top} (${ids}): names on one line`).toBeLessThanOrEqual(1);
        expect.soft(spread(row.map((each) => each.texts.price!.bottom)), `the row at ${top} (${ids}): prices on one line`).toBeLessThanOrEqual(1);
      }
      await capture(page, `HUB-1366-sold-out-tile-${size.label}`);
    });
  }
});
