// flow: combo-e2e-wait — FIX of the Menus specs' wait (FIX-HUB-COMBO-E2E-WAIT-BLIND-TO-SHADOW-ROOTS)
// Before a capture or a measurement, the Menus specs (combo-*.spec.ts) wait for the screen to stop moving with the
// harness's one wait, `untilStill` (helpers.ts). Their own wait asked the document alone for its animations, which
// leaves shadow roots out, and Ionic animates its overlays (`ion-modal`, `ion-toast`) in theirs: a capture could come
// out with a sheet still sliding in and pass for good. Here the till's menu sheet (COMBO-F07: tapping a menu opens
// it) enters at a fifth of its speed (Chrome's own control), and once the Menus specs' wait returns nothing may move,
// asked with the harness's own detector (`exposeMovingInPage`, helpers.ts), at 390, 834 and 1440. What this file
// creates — the products `E2E-CST-<run>-…` and the menu «e2e Combo Settled <run>» — is deleted after it, and nothing else.
import { type BrowserContext, type CDPSession, expect, type Page, test } from '@playwright/test';

import { A, api, capture, exposeMovingInPage, hostPage, psql, shown } from './helpers';
import { createProduct } from './inventory-helpers';
import { drawerOff, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-COMBO-E2E-WAIT-BLIND-TO-SHADOW-ROOTS';
const RUN = stamp();
const SKU = `E2E-CST-${RUN}`;
const MENU = `e2e Combo Settled ${RUN}`;
const FOOD = 'restaurant.food';

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

let menuId = '';

test.use({ locale: 'en-US' });

/** This file's menus and products, and nothing another spec made. */
function cleanOwn(): void {
  const combos = "select id from combo_combo where name like 'e2e Combo Settled %'";
  const products = "select id from inventory_product where sku like 'E2E-CST-%'";
  psql(
    [
      `delete from combo_choiceoption where group_id in (select id from combo_choicegroup where combo_id in (${combos}))`,
      `delete from combo_choicegroup where combo_id in (${combos})`,
      `delete from combo_combo where id in (${combos})`,
      `delete from inventory_stockmovement where product_id in (${products})`,
      `delete from inventory_productcategory where product_id in (${products})`,
      "delete from inventory_product where sku like 'E2E-CST-%'",
    ].join('; '),
  );
}

async function post<T>(context: BrowserContext, path: string, body: unknown): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(201);
  return res.data;
}

test.beforeAll(async ({ browser }) => {
  cleanOwn();
  const { context } = await hostPage(browser, A, { next: '/sale/pos' });
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  menuId = (await post<{ id: string }>(context, '/combo/combos', { name: MENU, price: 1200, tax_category_key: FOOD })).id;
  for (const [course, min] of [
    ['Starters', 1],
    ['Mains', 1],
  ] as const) {
    await post(context, '/combo/groups', { combo: MENU, name: course, min_choices: min, max_choices: 1 });
  }
  for (const [course, code, name] of [
    ['Starters', 'SOU', 'Soup'],
    ['Mains', 'FIS', 'Fish'],
  ] as const) {
    await createProduct(context, { name: `E2E CmbSettled ${name} ${RUN}`, sku: `${SKU}-${code}`, price: 600, tax_category_key: FOOD, initial_stock: '10' });
    await post(context, '/combo/options', { combo: MENU, group: course, product: `${SKU}-${code}` });
  }
  await context.close();
});

test.afterAll(() => {
  cleanOwn();
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

test('combo-e2e-wait: after the Menus specs’ wait the till’s menu sheet has stopped entering, at 390, 834 and 1440', async ({ browser }) => {
  const { context, page } = await hostPage(browser, A, { next: '/sale/pos', viewport: SIZES[2] });
  const devtools = await context.newCDPSession(page);
  await devtools.send('Animation.enable');
  try {
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await playbackRate(devtools, 1);
      await page.goto(`${A}/sale/pos`);
      const tile = shown(page).locator(`[data-testid=pos-menu-${menuId}]`);
      await expect(tile).toBeVisible({ timeout: 30_000 });
      await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
      await playbackRate(devtools, 0.2);
      await tile.click();
      const sheet = page.locator('ion-modal[data-testid=pos-menu]');
      await expect(sheet).toBeVisible();
      await expect(sheet.locator('[data-testid=pos-menu-add]')).toContainText('Choose 1 in «Starters»');
      await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
      expect.soft(await moving(page), `still moving after the Menus specs’ wait at ${size.label}`).toEqual([]);
      await capture(page, `${KEY}-${size.label}`);
    }
  } finally {
    await playbackRate(devtools, 1);
    await context.close();
  }
});
