// The Sales and Kitchen specs open the till's cart through `openTillCart` (sale-helpers.ts), never by reading the cart
// button themselves. The till lays itself out for the window a frame after a resize, so `if (await fab.isVisible())
// await fab.click()` straight after `setViewportSize` read the previous size's button: at 834 after 390 it tapped the
// phone's button on its way out and waited for it until the test's 3 minutes ran out (rv-hub-292; seven specs carried
// the copy), and at 390 after 1440 it found no button yet, left the drawer shut and «Send RUSH (1)» out of view
// (kitchen-pos.spec.ts, FIX-HUB-KITCHEN-E2E-KITCHEN-SEND-OUT-OF-VIEW-AT-390). The helper waits until the till's phone
// layout agrees with the window, by the till's own rule, which has to stay the one `PosPage.vue` applies.
// flow: ninguno — FIX tests/e2e
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));
const POS_PAGE = resolve(E2E_DIR, '..', '..', 'apps', 'sale', 'frontend', 'pages', 'PosPage.vue');

const read = (path: string): string => readFileSync(path, 'utf8');
const tillSpecs = (): string[] => readdirSync(E2E_DIR).filter((name) => /^(sale|kitchen)-.*\.spec\.ts$/.test(name));

/** The lines of `source` that decide on the cart button by reading its visibility. */
function fabVisibilityReads(source: string): string[] {
  return source.split('\n').filter((line) => /\bfab\.isVisible\(\)|pos-cart-fab[^\n]*\.isVisible\(\)/.test(line));
}

describe('the Sales and Kitchen specs and the till’s cart', () => {
  it('there are Sales and Kitchen specs to look at', () => {
    expect(tillSpecs()).toEqual(expect.arrayContaining(['sale-till-flows.spec.ts', 'kitchen-pos.spec.ts']));
  });

  it('no Sales or Kitchen spec decides on the cart button’s visibility: they call openTillCart', () => {
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
