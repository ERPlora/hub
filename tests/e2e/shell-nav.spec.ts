// FIX-SHELL-NAV (PLAN-MIGRATIONS §13, Ioan 2026-10-15): the hub's shell is the old hub's. No side menu
// at any width; the topbar carries the way around: Back on the left on every screen but Home (also the
// root of an app), the title in the middle, the ⠿ «My apps» sheet and the user on the right; the
// sections of an app stay in its bottom tabbar.
import { type Locator, type Page, expect, test } from '@playwright/test';

import { customersReady } from './customer-helpers';
import { A, listReady, login, openApps, record, shot, shown, topbarApps } from './helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

type Box = { x: number; y: number; width: number; height: number };

const overlaps = (a: Box, b: Box): boolean =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

/** The topbar of the screen on view and its four pieces. */
function topbar(page: Page): Record<'title' | 'back' | 'apps' | 'user', Locator> {
  const bar = shown(page).locator('ion-header.app-topbar');
  return {
    title: bar.locator('ion-title'),
    back: bar.locator('[data-testid=topbar-back]'),
    apps: bar.locator('[data-testid=topbar-apps]'),
    user: bar.locator('[data-testid=topbar-user]'),
  };
}

/** Enabled tiles of the sheet other than Demo (the app the specs start in). */
const otherApps = (sheet: Locator): Locator =>
  sheet.locator('[data-testid=apps-launcher-app]:not([disabled])').filter({ hasNotText: /^\s*Demo\s*$/ });

test('390 / 834 / 1440: no side menu; Back, ⠿ apps and the user in the topbar, clear of the title', async ({ page }) => {
  await login(page, A);
  const results: Record<string, unknown> = {};
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    // The root of an app with sections (Customers, the old hub's reference screen).
    await page.goto('/customer/customers');
    const bar = topbar(page);
    // hub#1831: the way out is there on the first paint, not once an `ion-menu` registers.
    for (const piece of [bar.back, bar.apps, bar.user]) await expect(piece).toBeVisible();
    await expect(page.locator('ion-menu, ion-split-pane, ion-menu-button')).toHaveCount(0);
    await customersReady(page);
    await page.waitForTimeout(400);

    // hub#690: on a phone (ios) the icons covered the title.
    const title = (await bar.title.boundingBox())!;
    const boxes = { back: (await bar.back.boundingBox())!, apps: (await bar.apps.boundingBox())!, user: (await bar.user.boundingBox())! };
    results[vp.label] = { title, ...boxes };
    for (const [name, box] of Object.entries(boxes)) {
      expect(overlaps(title, box), `${vp.label}: the title runs over ${name}`).toBe(false);
      expect(box.x + box.width, `${vp.label}: ${name} inside the screen`).toBeLessThanOrEqual(vp.width);
    }
    expect(boxes.back.x, `${vp.label}: Back on the left`).toBeLessThan(title.x);
    expect(boxes.apps.x, `${vp.label}: apps on the right`).toBeGreaterThan(title.x);
    expect(boxes.user.x, `${vp.label}: the user after the apps`).toBeGreaterThan(boxes.apps.x);
    // The sections of the app are its bottom tabbar.
    await expect(shown(page).locator('ion-footer ion-segment-button').first()).toBeVisible();
    await page.screenshot({ path: shot(`FIX-SHELL-NAV-${vp.label}`) });

    if (vp.label === '390') {
      const sheet = await openApps(page);
      await expect(sheet.locator('ion-title')).toBeVisible();
      await page.waitForTimeout(500); // the sheet's slide-in
      await page.screenshot({ path: shot('FIX-SHELL-NAV-apps-390') });
      await sheet.locator('[data-testid=apps-launcher-close]').click();
      await expect(sheet).toHaveCount(0);
    }
  }
  record('FIX-SHELL-NAV-topbar', results);
});

test('Back from the root of an app goes Home; Home has no Back and paints the apps', async ({ page }) => {
  await login(page, A);
  await page.goto('/demo/items'); // a link straight into the app: no history to go back to
  await listReady(page);
  await topbar(page).back.click();
  await expect(page).toHaveURL(`${A}/`);
  await expect(shown(page).locator('[data-testid=home-app]').first()).toBeVisible();
  await expect(topbar(page).back).toHaveCount(0);
  await expect(topbar(page).apps).toBeVisible();
});

test('the «My apps» sheet opens another app, and closes', async ({ page }) => {
  await login(page, A);
  await page.goto('/demo/items');
  await listReady(page);
  const sheet = await openApps(page);
  const target = otherApps(sheet).first();
  const name = (await target.getAttribute('title'))!;
  await target.click();
  await expect(sheet).toHaveCount(0);
  await expect(page).not.toHaveURL(/\/demo\//);
  await expect(topbar(page).back).toBeVisible();
  record('FIX-SHELL-NAV-open-app', { opened: name, url: page.url() });
});

// hub#2242 / hub#2241: going to an app and back fast left the address and the page out of step, or
// the page stuck on its skeleton.
test('apps and Back, fast and repeated: the address and the page stay in step', async ({ page }) => {
  await login(page, A, '/');
  await expect(shown(page).locator('[data-testid=home-app]').first()).toBeVisible();
  for (let round = 0; round < 4; round += 1) {
    const sheet = await openApps(page);
    await sheet.locator('[data-testid=apps-launcher-app]', { hasText: 'Demo' }).click();
    await topbar(page).back.click();
  }
  await expect(page).toHaveURL(`${A}/`);
  await expect(shown(page).locator('[data-testid=home-app]').first()).toBeVisible();
  await expect(page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)')).toHaveCount(1);

  const sheet = await openApps(page);
  await sheet.locator('[data-testid=apps-launcher-app]', { hasText: 'Demo' }).click();
  await expect(page).toHaveURL(`${A}/demo/items`);
  await listReady(page);
  await expect(page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)')).toHaveCount(1);
});

// hub#2489 / hub#2325: with a flaky network, tapping an app opened nothing and said nothing.
test('an app whose page does not load says so, with a Retry; never silent', async ({ page }) => {
  await login(page, A);
  await page.goto('/demo/items');
  await listReady(page);
  await page.route(/\/frontend\/pages\//, (route) => route.abort('internetdisconnected'));
  const sheet = await openApps(page);
  // Customers, whose root screen is known: Retry has to land there.
  const target = otherApps(sheet).filter({ hasText: /^\s*Customers\s*$/ });
  const name = (await target.getAttribute('title'))!;
  await target.click();
  const toast = page.locator('ion-toast#apps-launcher-open');
  await expect(toast).toBeVisible();
  await expect(toast).toContainText(name);
  await expect(page).toHaveURL(`${A}/demo/items`);
  await page.screenshot({ path: shot('FIX-SHELL-NAV-open-failed-390') });

  // The network is back: the toast's Retry opens the app and the toast goes away.
  await page.unroute(/\/frontend\/pages\//);
  await toast.locator('button', { hasText: /retry|reintentar/i }).click();
  await expect(page).toHaveURL(`${A}/customer/customers`);
  await customersReady(page);
  await expect(topbarApps(page)).toBeVisible();
  await expect(toast).toBeHidden();
});
