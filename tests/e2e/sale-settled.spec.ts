// flow: sale-e2e-wait — FIX of the Sales specs' wait (FIX-HUB-SALE-E2E-WAIT-BLIND-TO-SHADOW-ROOTS)
// Before a capture or a measurement, the Sales specs (sale-*.spec.ts) wait for the screen to stop moving with the
// harness's one wait, `untilStill` (helpers.ts). Their own wait asked the document alone for its animations, which
// leaves shadow roots out, and Ionic animates its overlays (`ion-toast`, `ion-modal`, the till's sheets) in theirs: a
// capture could come out with a notice still sliding in and pass for good. Here the till's «… is sold out.» toast
// (SALE-F07: a tap on a sold-out article says why) enters at a fifth of its speed (Chrome's own control), and once
// the Sales specs' wait returns nothing may move, asked with the harness's own detector (`exposeMovingInPage`,
// helpers.ts), at 390, 834 and 1440. What this file creates is deleted after it.
import { type CDPSession, expect, type Page, test } from '@playwright/test';

import { A, api, capture, exposeMovingInPage, hostPage, repeatedTop, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-SALE-E2E-WAIT-BLIND-TO-SHADOW-ROOTS';
const RUN = stamp();

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

let croquettes: Product;

test.use({ locale: 'en-US' });

test.beforeAll(async ({ browser }) => {
  const { context } = await hostPage(browser, A, { next: '/sale/pos' });
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  croquettes = await createProduct(context, { name: `E2E Croquettes ${RUN}`, sku: `E2E-ST-${RUN}`, price: 650, tax_category_key: 'restaurant.food' });
  const marked = await api(context, A, 'POST', '/inventory/products/sold_out', { id: croquettes.id, sold_out: true });
  expect(marked.status, 'mark sold out').toBe(200);
  await context.close();
});

test.afterAll(() => {
  cleanSales();
  cleanInventory();
  restoreDrawer();
});

/** What moves on the page now, by the detector of helpers.ts put in the page (`exposeMovingInPage`). */
async function moving(page: Page): Promise<string[]> {
  await exposeMovingInPage(page);
  return page.evaluate(() => (window as unknown as { __movingInPage: () => string[] }).__movingInPage());
}

/** Every animation of the page at `rate` times its speed. */
async function playbackRate(devtools: CDPSession, rate: number): Promise<void> {
  await devtools.send('Animation.setPlaybackRate', { playbackRate: rate });
}

test('sale-e2e-wait: after the Sales specs’ wait the till’s «sold out» toast has stopped entering, at 390, 834 and 1440', async ({
  browser,
}) => {
  const { context, page } = await hostPage(browser, A, { next: '/sale/pos', viewport: SIZES[2] });
  const devtools = await context.newCDPSession(page);
  await devtools.send('Animation.enable');
  try {
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await playbackRate(devtools, 1);
      await page.goto(`${A}/sale/pos`);
      const tile = shown(page).locator(`[data-testid=pos-product-${croquettes.id}]`);
      await expect(tile).toHaveClass(/pos-tile--sold-out/, { timeout: 30_000 });
      await untilStill(page);
      await playbackRate(devtools, 0.2);
      // The tile is `aria-disabled` but takes the tap (a touchscreen would swallow a native `disabled`).
      await tile.click({ force: true });
      const toast = page.locator('ion-toast').filter({ hasText: `«${croquettes.name}» is sold out.` });
      await expect(toast).toBeVisible();
      await untilStill(page);
      expect(await moving(page), `still moving after the Sales specs’ wait at ${size.label}`).toEqual([]);
      expect(await repeatedTop(page, await capture(page, `${KEY}-${size.label}`))).toBe(0);
    }
  } finally {
    await playbackRate(devtools, 1);
    await context.close();
  }
});
