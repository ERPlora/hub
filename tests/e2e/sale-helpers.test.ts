// The Sales, Kitchen and Tables specs open the till's cart through `openTillCart` (sale-helpers.ts), never by reading the cart
// button themselves. The till lays itself out for the window a frame after a resize, so `if (await fab.isVisible())
// await fab.click()` straight after `setViewportSize` reads the previous size's button: at 834 after 390 it taps the
// phone's button on its way out and waits for it until the test's time runs out, and at 390 after 1440 it finds no
// button yet and leaves the drawer shut, with «Send RUSH (1)» out of view. The helper waits until the till's phone
// layout agrees with the window, by the till's own rule, which has to stay the one `PosPage.vue` applies.
// flow: none — the e2e harness
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { NO_CLOCK } from '../../vitest.load';
import { readTexts } from '../../vitest.offload';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));
const POS_PAGE = resolve(E2E_DIR, '..', '..', 'apps', 'sale', 'frontend', 'pages', 'PosPage.vue');
const POS_ITEM_TILE = resolve(E2E_DIR, '..', '..', 'apps', 'sale', 'frontend', 'components', 'pos', 'PosItemTile.vue');

const read = (path: string): string => readFileSync(path, 'utf8');
const tillSpecs = (): string[] => readdirSync(E2E_DIR).filter((name) => /^(sale|kitchen|table)-.*\.spec\.ts$/.test(name));

/** The lines of `source` that decide on the cart button by reading its visibility. */
function fabVisibilityReads(source: string): string[] {
  return source.split('\n').filter((line) => /\bfab\.isVisible\(\)|pos-cart-fab[^\n]*\.isVisible\(\)/.test(line));
}

describe('the Sales, Kitchen and Tables specs and the till’s cart', () => {
  it('there are Sales, Kitchen and Tables specs to look at', () => {
    expect(tillSpecs()).toEqual(expect.arrayContaining(['sale-till-flows.spec.ts', 'kitchen-pos.spec.ts', 'table-flows.spec.ts']));
  });

  it('no Sales, Kitchen or Tables spec decides on the cart button’s visibility: they call openTillCart', () => {
    const offenders = tillSpecs().flatMap((name) => fabVisibilityReads(read(join(E2E_DIR, name))).map((line) => `${name}: ${line.trim()}`));
    expect(offenders).toEqual([]);
  });

  it('the check reads a copy of the old pattern as one', () => {
    expect(fabVisibilityReads("  const fab = page.locator('[data-testid=pos-cart-fab]');\n  if (await fab.isVisible()) await fab.click();")).toHaveLength(1);
    expect(fabVisibilityReads("if (await page.locator('[data-testid=pos-cart-fab]').isVisible()) {")).toHaveLength(1);
    expect(fabVisibilityReads("await expect(shown(page).locator('[data-testid=pos-cart-fab]')).toBeVisible();")).toEqual([]);
  });

  it('openTillCart’s phone rule is the till’s own (PosPage.vue: PHONE, NARROW_TILL)', () => {
    const page = read(POS_PAGE);
    const helper = read(join(E2E_DIR, 'sale-helpers.ts'));
    const media = /const PHONE = '([^']+)';/.exec(page)?.[1];
    const narrow = /const NARROW_TILL = (\d+);/.exec(page)?.[1];
    expect([media, narrow]).not.toContain(undefined);
    expect(helper).toContain(`const TILL_PHONE = { media: '${media}', narrowerThan: ${narrow} };`);
  });
});

// Every tile of the till's grid (product, service, menu, «Open price») is PosItemTile.vue, an Ionic button: a spec that
// looked for the grid's `button` children found none and stayed red while the menus still went first (hub#1363).
let gridScan: Promise<[name: string, text: string][]> | undefined;

/** The specs and helpers of the e2e that read the till's grid, with their text: the e2e's files read once, off the
 *  worker's thread. */
function gridReaders(): Promise<[name: string, text: string][]> {
  gridScan ??= (async () => {
    const names = readdirSync(E2E_DIR).filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts'));
    const texts = await readTexts(names.map((name) => join(E2E_DIR, name)));
    return names.map((name, index): [string, string] => [name, texts[index]]).filter(([, text]) => /pos-grid|tillGrid\(|expectFirstTile\(/.test(text));
  })();
  return gridScan;
}

/** The lines of `source` that look for a tile of the grid as a native button. */
function nativeTileReads(source: string): string[] {
  return source.split('\n').filter((line) => /pos-grid[^'"`]*>\s*button\b|:scope\s*>\s*button\b/.test(line));
}

describe('the till’s grid in the e2e', () => {
  it('there are specs that read the grid to look at, the menus’ among them', async () => {
    expect((await gridReaders()).map(([name]) => name)).toEqual(expect.arrayContaining(['combo-till.spec.ts', 'sale-menus-options.spec.ts']));
  }, NO_CLOCK);

  it('no spec looks for a tile of the grid as a native button: they call expectFirstTile', async () => {
    const offenders = (await gridReaders()).flatMap(([name, text]) => nativeTileReads(text).map((line) => `${name}: ${line.trim()}`));
    expect(offenders).toEqual([]);
  }, NO_CLOCK);

  it('the check reads a copy of the old pattern as one', () => {
    expect(nativeTileReads("  await expect(grid.locator(':scope > button').first()).toHaveAttribute('data-testid', /^pos-menu-/);")).toHaveLength(1);
    expect(nativeTileReads("  await expect(shown(page).locator('.pos-grid > button').first()).toHaveAttribute('data-testid', id);")).toHaveLength(1);
    expect(nativeTileReads("  const keypad = sheet.locator('[data-testid=sale-checkout-keypad] > button');")).toEqual([]);
  });

  it('expectFirstTile looks for the tile the till paints: PosItemTile.vue’s root', () => {
    const root = /<template>\s*<([\w-]+)\b[^>]*?\sclass="([\w-]+)"/.exec(read(POS_ITEM_TILE));
    expect(root?.slice(1)).toEqual(['ion-button', 'pos-tile']);
    expect(read(join(E2E_DIR, 'sale-helpers.ts'))).toContain(`const TILL_TILE = ':scope > ${root?.[1]}.${root?.[2]}';`);
  });
});
