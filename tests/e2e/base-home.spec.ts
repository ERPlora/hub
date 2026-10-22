// The Home of the Hub (APP-BASE-1; the old hub's dashboard, docs/reference/old-hub/dashboard-*.png,
// dashboard-activity-*.png and apps-launcher-*.png) in the three viewports, as the owner of hub `a`: the
// heading, «My apps», «Finish setting up your business» (the platform's steps and the demo's example, which a
// development server shows), the board with the demo's panel — followed live: an item created elsewhere moves
// it without a reload —, «Customize panel», the bell, «Upgrade plan» in the side menu and «Activity» at
// `/#actividad`. Each flow leaves its capture `APP-BASE-1-<flow>-<width>` once nothing scrolls sideways.
// flow: BASE-G127 BASE-G22 BASE-G130 BASE-G165 BASE-G166 BASE-G167 BASE-G168 BASE-G129 BASE-G137 BASE-G169
import { expect, type Page, test } from '@playwright/test';

import { A, api, clearItems, hostPage, shot, shown, uniqueName } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** The side menu is pinned from 992 px; below it is a drawer behind the bar's menu button. */
const PINNED_MIN = 992;

async function snap(page: Page, flow: string, width: number): Promise<void> {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== 'running' || a.effect?.getTiming().iterations === Infinity),
  );
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${flow} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APP-BASE-1-${flow}-${width}`) });
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`the Home at ${width}: heading, my apps, setup list, live board, bell, plan and activity`, async ({ browser }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: '/' });
    await clearItems(context, A);

    // BASE-G127 — the Home at `/`, headed by the business (or a greeting) and today's date.
    await page.goto(`${A}/`);
    await expect(shown(page).locator('h1')).toBeVisible();
    await expect(testid(page, 'home-date')).toBeVisible();
    // BASE-G165 — «My apps»: the demo among the apps this person can open.
    const myApps = testid(page, 'home-my-apps');
    await expect(myApps.locator('[data-testid="home-my-app"]').first()).toBeVisible();
    await expect(myApps.locator('[data-testid="home-my-app"][href="/demo/items"]')).toHaveCount(1);
    await snap(page, 'BASE-G127', width);
    await snap(page, 'BASE-G165', width);

    // BASE-G22 / BASE-G164 — the list from base.setup.status: the demo's example step, pending with no items.
    const card = testid(page, 'setup-card');
    await expect(card).toHaveAttribute('aria-busy', 'false');
    await expect(card.locator('[data-testid="setup-row"][data-key="demo.first_item"]')).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await snap(page, 'BASE-G22', width);

    // BASE-G166 / BASE-G168 — the demo's panel «Open items», and a new open item moves it without a reload.
    const panel = testid(page, 'widget-board').locator('[data-testid="widget"][data-key="demo.open_items"]');
    const value = panel.locator('[data-testid="widget-value"]');
    await expect(value).toHaveText('0');
    await api(context, A, 'POST', '/demo/items', { name: uniqueName('Home') });
    await expect(value).toHaveText('1');
    // The step «Create your first item» is done now: the list re-ran on the server too.
    await expect(card.locator('[data-testid="setup-row"][data-key="demo.first_item"]')).toHaveCount(0);
    await panel.scrollIntoViewIfNeeded();
    await snap(page, 'BASE-G166', width);
    await snap(page, 'BASE-G168', width);

    // BASE-G130 — «Set up» of a row leads to its screen (the demo's step, while it was pending).
    await clearItems(context, A);
    const configure = card.locator('[data-testid="setup-configure-demo.first_item"]');
    await expect(configure).toBeVisible();
    await snap(page, 'BASE-G130', width);
    await configure.click();
    await expect(page).toHaveURL(`${A}/demo/items/new`);
    await page.goto(`${A}/`);

    // BASE-G167 — «Customize panel»: the demo's panel among the active ones; removing it empties the board.
    await testid(page, 'widgets-customize').click();
    const picker = page.locator('ion-modal[data-testid="widgets-picker"]:not(.overlay-hidden)');
    await expect(picker.locator('[data-testid="widgets-active-item"][data-key="demo.open_items"]')).toBeVisible();
    await snap(page, 'BASE-G167', width);
    await picker.locator('[data-testid="widgets-remove-demo.open_items"]').click();
    await picker.locator('[data-testid="widgets-close"]').click();
    await expect(picker).toBeHidden();
    await expect(testid(page, 'widgets-empty')).toBeVisible();
    await page.reload();
    await expect(testid(page, 'widgets-empty')).toBeVisible();
    await page.evaluate(() => localStorage.removeItem('dashboard-hub'));
    await page.reload();
    await expect(testid(page, 'widget-board').locator('[data-testid="widget"][data-key="demo.open_items"]')).toBeVisible();

    // BASE-G137 — the bell (base.bell.counters): the demo's «Open demo items» counter once there is one open.
    await api(context, A, 'POST', '/demo/items', { name: uniqueName('Bell') });
    const bell = testid(page, 'hub-bell');
    await expect(bell.locator('[data-testid="hub-bell-badge"]')).toHaveText('1');
    await bell.click();
    const rows = page.locator('ion-popover [data-testid="hub-bell-row"]');
    await expect(rows).toHaveCount(1);
    await snap(page, 'BASE-G137', width);
    await rows.first().click();
    await expect(page).toHaveURL(`${A}/demo/items`);
    await page.goto(`${A}/`);

    // BASE-G169 — «Upgrade plan» at the foot of the side menu, to this hub's plan on the SaaS.
    if (width < PINNED_MIN) await shown(page).locator('ion-menu-button').click();
    const upgrade = page.locator('ion-menu [data-testid="upgrade-plan"]');
    await expect(upgrade).toBeVisible();
    await expect(upgrade).toHaveAttribute('href', /\/store\/plans\?business=[0-9a-f-]{36}$/);
    await expect(upgrade).toHaveAttribute('target', '_blank');
    await snap(page, 'BASE-G169', width);
    // A fresh page, without the drawer (closing it while it still slides in is ignored by Ionic).
    if (width < PINNED_MIN) await page.reload();
    await expect(testid(page, 'home-my-apps')).toBeVisible();

    // BASE-G129 — «Activity» at `/#actividad`: the table of the last sales.
    await page.goto(`${A}/#actividad`);
    await expect(shown(page).locator('[data-testid="tab-activity"]')).toHaveClass(/segment-button-checked/);
    await expect(shown(page).locator('[data-testid="home-activity-search"]')).toBeVisible();
    // «Summary» takes the hash away again (Back leaves the Home instead of walking its tabs).
    await shown(page).locator('[data-testid="tab-summary"]').click();
    await expect(page).toHaveURL(`${A}/`);
    await expect(testid(page, 'home-my-apps')).toBeVisible();
    await page.goto(`${A}/#actividad`);
    await expect(shown(page).locator('[data-testid="home-activity-search"]')).toBeVisible();
    await snap(page, 'BASE-G129', width);

    await clearItems(context, A);
    await context.close();
  });
}
