// A screen whose data could not be read never shows made-up values nor offers to save them
// (hub#2541, the follow-up of hub#2511 for the shell's own screens).
//
// What it pins:
//   · Settings swallowed a failed `GET /api/settings` and painted Spain, EUR and Spanish — the
//     defaults of the empty cache — as if they were the business's. An administrator could change
//     one of them, or press «Save changes» on the Business tab with empty tax-id fields, on top of
//     values nobody had read. The pinpad card read its idle stop and PIN length from the same cache.
//   · My profile kept the form EMPTY after a failed `GET /api/profile` with «Save my details»
//     enabled: pressing it wiped the person's name and e-mail. The PIN card guessed «no PIN yet».
// Both now say «could not load» with Retry, and nothing that saves is on screen until the read works.
//
// Why a bench spec on top of the unit tests: the error state is an `ok-empty-state` with an
// `ion-button` in its `action` slot, and only a real browser with the real OutfitKit and Ionic tells
// whether the card and its button are on screen and inside it at the three widths (hub#2540: a
// wrongly named slot leaves the button invisible and vitest does not notice).
import type { Route } from '@playwright/test';

import { expect, test, type Page } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';

// The three sizes the fleet checks every screen at (pm#529): 375x667 is the narrowest phone we serve.
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;

/** Fails ONLY the read of `path` (a GET), the way a restarting hub answers; writes go through. */
async function failRead(page: Page, path: string): Promise<void> {
  await page.route(
    (url) => url.pathname === path,
    async (route: Route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ ok: false, error: { code: 'service_unavailable', message: 'restarting' } }),
      });
    },
  );
}

/** The element is on screen and whole: nothing of it hangs past the right edge of the viewport. */
async function expectInsideViewport(page: Page, testId: string, width: number): Promise<void> {
  const box = await page.getByTestId(testId).boundingBox();
  expect(box, `${testId} has a box`).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width, `${testId} overflows the ${width}px viewport`).toBeLessThanOrEqual(width + 0.5);
}

test.describe('a screen that could not read its data says so and saves nothing (hub#2541)', () => {
  for (const viewport of VIEWPORTS) {
    test(`at ${viewport.width}px: Settings shows Retry instead of the business settings`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize(viewport);
      await withSession(page, await loginByPin());
      await failRead(page, '/api/settings');
      await page.goto('/settings');

      // General: no country, currency, language, palette, API docs or pinpad made up from defaults.
      await expect(page.getByTestId('settings-load-error')).toBeVisible();
      await expect(page.getByTestId('settings-load-retry')).toBeVisible();
      for (const id of ['settings-country', 'settings-timezone', 'settings-currency', 'settings-hub-language']) {
        await expect(page.getByTestId(id)).toHaveCount(0);
      }
      await expect(page.getByTestId('settings-hub-palette')).toHaveCount(0);
      await expect(page.getByTestId('settings-api-docs')).toHaveCount(0);
      await expect(page.getByTestId('pin-policy-card')).toHaveCount(0);
      await expectInsideViewport(page, 'settings-load-error', viewport.width);
      await expectInsideViewport(page, 'settings-load-retry', viewport.width);
      await page.screenshot({ path: testInfo.outputPath(`settings-general-${viewport.width}x${viewport.height}.png`) });

      // Business: no empty tax-id form and, above all, no «Save changes».
      await page.getByTestId('settings-tab-business').click();
      await expect(page.getByTestId('settings-load-error')).toBeVisible();
      await expect(page.getByTestId('settings-save-business')).toHaveCount(0);
      await expect(page.getByTestId('settings-business-tax-id')).toHaveCount(0);
      await expectInsideViewport(page, 'settings-load-retry', viewport.width);
      await page.screenshot({
        path: testInfo.outputPath(`settings-business-${viewport.width}x${viewport.height}.png`),
      });

      // The hub is back: Retry reads again and the form is there, with the stored values.
      await page.unrouteAll({ behavior: 'wait' });
      await page.getByTestId('settings-load-retry').click();
      await expect(page.getByTestId('settings-save-business')).toBeVisible();
      await expect(page.getByTestId('settings-load-error')).toHaveCount(0);
      await page.getByTestId('settings-tab-hub').click();
      await expect(page.getByTestId('settings-currency')).toBeVisible();
      await expect(page.getByTestId('pin-policy-card')).toBeVisible();
    });

    test(`at ${viewport.width}px: My profile shows Retry instead of an empty form`, async ({ page }, testInfo) => {
      await page.setViewportSize(viewport);
      await withSession(page, await loginByPin());
      await failRead(page, '/api/profile');
      await page.goto('/profile');

      await expect(page.getByTestId('profile-load-error')).toBeVisible();
      await expect(page.getByTestId('profile-load-retry')).toBeVisible();
      for (const id of [
        'profile-change-photo',
        'profile-first-name',
        'profile-save',
        'profile-language',
        'profile-pin-form',
        'profile-save-pin',
      ]) {
        await expect(page.getByTestId(id)).toHaveCount(0);
      }
      await expectInsideViewport(page, 'profile-load-error', viewport.width);
      await expectInsideViewport(page, 'profile-load-retry', viewport.width);
      await page.screenshot({ path: testInfo.outputPath(`profile-${viewport.width}x${viewport.height}.png`) });

      await page.unrouteAll({ behavior: 'wait' });
      await page.getByTestId('profile-load-retry').click();
      await expect(page.getByTestId('profile-first-name')).toBeVisible();
      await expect(page.getByTestId('profile-save')).toBeEnabled();
      await expect(page.getByTestId('profile-load-error')).toHaveCount(0);
    });
  }
});
