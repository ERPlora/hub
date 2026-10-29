// flow: modifier-e2e-wait — FIX of the Modifiers specs' wait (FIX-HUB-MODIFIER-E2E-WAIT-BLIND-TO-SHADOW-ROOTS)
// Before a capture or a measurement, the Modifiers specs (modifier-*.spec.ts) wait for the screen to stop moving with
// the harness's one wait, `untilStill` (helpers.ts). Their own wait asked the document alone for its animations, which
// leaves shadow roots out, and Ionic animates its overlays (`ion-modal`, `ion-toast`) in theirs: a capture could come
// out with a sheet still sliding in and pass for good. Here the till's options sheet (MODIFIER-F06: tapping a dish
// with groups opens it) enters at a fifth of its speed (Chrome's own control), and once the Modifiers specs' wait
// returns nothing may move, asked with the harness's own detector (`exposeMovingInPage`, helpers.ts), at 390, 834 and
// 1440. What this file creates — the product `E2E-MST-<run>` and the group «E2E Mod Settled … <run>» — is deleted after it.
import { type CDPSession, expect, type Page, test } from '@playwright/test';

import { A, api, capture, exposeMovingInPage, hostPage, psql, repeatedTop, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { drawerOff, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-MODIFIER-E2E-WAIT-BLIND-TO-SHADOW-ROOTS';
const RUN = stamp();
const OWN_GROUPS = "select id from modifier_modifiergroup where name like 'E2E Mod Settled %'";

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

let burger: Product;

test.use({ locale: 'en-US' });

/** This file's groups, their options and where they apply. */
function cleanGroups(): void {
  psql(
    [
      `delete from modifier_modifierlink where group_id in (${OWN_GROUPS})`,
      `delete from modifier_modifieroption where group_id in (${OWN_GROUPS})`,
      `delete from modifier_modifiergroup where id in (${OWN_GROUPS})`,
    ].join('; '),
  );
}

test.beforeAll(async ({ browser }) => {
  cleanGroups();
  const { context } = await hostPage(browser, A, { next: '/sale/pos' });
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  burger = await createProduct(context, { name: `E2E Burger ${RUN}`, sku: `E2E-MST-${RUN}`, price: 800, tax_category_key: 'restaurant.food' });
  const group = await api<{ id: string }>(context, A, 'POST', '/modifier/groups', {
    name: `E2E Mod Settled Doneness ${RUN}`,
    min_choices: 1,
    max_choices: 1,
  });
  expect(group.status, 'create the group').toBe(201);
  for (const option of [
    { name: 'Rare', sort_order: 1 },
    { name: 'Medium', sort_order: 2, is_default: true },
  ]) {
    const made = await api(context, A, 'POST', '/modifier/options', { group_id: group.data.id, ...option });
    expect(made.status, `option ${option.name}`).toBe(201);
  }
  const linked = await api(context, A, 'POST', '/modifier/links/attach', { group_id: group.data.id, product_id: burger.id });
  expect(linked.status, 'apply the group to the burger').toBe(201);
  await context.close();
});

test.afterAll(() => {
  cleanGroups();
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

test('modifier-e2e-wait: after the Modifiers specs’ wait the till’s options sheet has stopped entering, at 390, 834 and 1440', async ({
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
      const tile = shown(page).locator(`[data-testid=pos-product-${burger.id}]`);
      await expect(tile).toBeVisible({ timeout: 30_000 });
      await untilStill(page);
      await playbackRate(devtools, 0.2);
      await tile.click();
      const sheet = page.locator('ion-modal[data-testid=pos-options]');
      await expect(sheet).toBeVisible();
      await expect(sheet.locator('[data-testid=pos-options-title]')).toHaveText(burger.name);
      await untilStill(page);
      expect(await moving(page), `still moving after the Modifiers specs’ wait at ${size.label}`).toEqual([]);
      expect(await repeatedTop(page, await capture(page, `${KEY}-${size.label}`))).toBe(0);
    }
  } finally {
    await playbackRate(devtools, 1);
    await context.close();
  }
});
