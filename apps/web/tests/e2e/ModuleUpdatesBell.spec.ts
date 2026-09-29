// Regression test for ERPlora/hub#1172 — a hub ran 9 apps behind the marketplace and the owner had
// no way of knowing: the only place that said «Update to X» was Apps → «My apps».
//
// The bell now carries one row («3 apps have a new version») that leads to «My apps», from any
// screen, on every viewport. On a phone the bell folds into the «More» menu, so that path is walked
// too. The bench has no Cloud, so `GET /api/modules/updates` is answered here; everything else —
// shell, session, Ionic, the popover — is the real thing.
import type { Page } from '@playwright/test';
import { test, expect } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';

const UPDATES = ['sales', 'kitchen', 'tables'].map((module_id) => ({
  module_id,
  installed: '1.0.0',
  latest: '1.1.0',
  update_available: true,
  pinned: null,
  latest_min_erplora_version: null,
}));

const SIZES = [
  { width: 1920, height: 1080 },
  { width: 834, height: 1112 },
  { width: 390, height: 844 },
];

async function openNotifications(page: Page): Promise<void> {
  const bell = page.getByTestId('topbar-notifications');
  if (await bell.isVisible()) {
    await bell.click();
  } else {
    await page.getByTestId('topbar-more').click();
    await page.getByTestId('topbar-more-notifications').click();
  }
}

test.describe('the bell says how many apps have a new version (hub#1172)', () => {
  for (const { width, height } of SIZES) {
    test(`${width}x${height}: the row is on screen and leads to «My apps»`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.route(/\/api\/modules\/updates/, (r) => r.fulfill({ json: { ok: true, data: UPDATES } }));
      await loggedInSession(page);
      await page.goto('/dashboard');

      await openNotifications(page);
      const row = page.getByTestId('topbar-module-updates');
      await expect(row).toBeVisible();
      await expect(row).toContainText('Actualizaciones de apps');
      await expect(row).toContainText('3 apps tienen una versión nueva');
      if (process.env.HUB1172_SHOTS) {
        await page.waitForTimeout(600); // popover enter animation
        await page.screenshot({ path: `${process.env.HUB1172_SHOTS}/bell-${width}x${height}.png` });
      }
      // The whole row on screen. Measured by its box and not `toBeInViewport({ ratio: 1 })`: the
      // popover's scroll container clips half a pixel of it on a phone (ratio 0.996).
      const box = await row.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      expect(box!.y + box!.height).toBeLessThanOrEqual(height);

      await row.click();
      await expect(page).toHaveURL(/\/apps#mine$/);
    });
  }
});
