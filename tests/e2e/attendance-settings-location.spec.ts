// A denied location on «Use my current location» in the time clock's Settings says where to allow it again
// (FIX-HUB-ATTENDANCE-SETTINGS-LOCATION-DENIED-SAYS-BROWSER-INSIDE-THE-APP; apps/attendance/WORKBOOK.md
// ATTENDANCE-F04 «Si falla»): in a browser, the browser; inside the installed app (Android, Windows), which has
// no browser bar, the device's settings, as the till's «Speak» key (sale-speak-microphone.spec.ts, SALE-F01).
// The Hub and its SaaS are the real ones. Tauri does not run in Playwright: the app's bridge is simulated at the
// edge (`window.__TAURI__`). The location is refused by Chrome itself (no permission granted to the hub), in a
// file of its own: attendance-flows.spec.ts grants it for F04. Nothing is saved: what was typed stays on screen.
// flow: ATTENDANCE-F04
import { expect, type Page, test } from '@playwright/test';

import { A, login, shot, shown, untilStill } from './helpers';
import { noHorizontalScroll, VIEWPORTS } from './schedule-helpers';

const KEY = 'FIX-HUB-ATTENDANCE-SETTINGS-LOCATION-DENIED-SAYS-BROWSER-INSIDE-THE-APP';

/** Settings, a latitude typed and a tap on «Use my current location»: the notice says how to allow it. */
async function deny(page: Page, notice: string): Promise<void> {
  await page.goto(`${A}/attendance/settings`);
  const view = shown(page);
  const lat = view.locator('[data-testid=attendance-settings-workplace_lat] input');
  await lat.fill('40.4');
  await view.locator('[data-testid=attendance-settings-use-location]').click();
  const shownNotice = view.locator('[data-testid=attendance-settings-location-error]');
  await expect(shownNotice).toHaveText(notice);
  // Where the person tapped: on a phone the button sits below the fold, so a notice up top went unseen.
  await expect(shownNotice).toBeInViewport();
  await expect(view.locator('[data-testid=attendance-settings-error]')).toHaveCount(0);
  await expect(lat).toHaveValue('40.4');
  await expect(view.locator('[data-testid=attendance-settings-workplace_lng] input')).toHaveValue('');
  await expect(view.locator('[data-testid=attendance-settings-accuracy]')).toHaveCount(0);
}

test('ATTENDANCE-F04 — a denied location on «Use my current location» points to the browser, and inside the installed app to the device settings', async ({
  page,
  context,
}) => {
  await login(page, A, '/attendance/settings');
  // Every permission refused for the hub: its geolocation answers «denied», as a person who said «Block».
  await context.grantPermissions([], { origin: A });
  await page.setViewportSize({ width: 1440, height: 900 });
  await deny(page, 'Location access is denied. Allow location in this browser to read the workplace position, or type the coordinates.');

  await page.addInitScript(() => {
    (window as unknown as { __TAURI__: unknown }).__TAURI__ = { core: { invoke: async () => null } };
  });
  await deny(page, 'Location access is denied. Allow location in your device settings to read the workplace position, or type the coordinates.');

  // In Spanish (the Hub's language cookie, as the sign-in sets it).
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await deny(
      page,
      'El acceso a la ubicación está denegado. Permite la ubicación en los ajustes del dispositivo para leer la posición del lugar de trabajo o escribe las coordenadas.',
    );
    await noHorizontalScroll(page, vp.label);
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-${vp.label}`) });
  }
});
