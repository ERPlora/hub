// A refused microphone in the assistant's composer says where to allow it again (BASE-F94): in a browser, the
// browser; inside the installed app (Android, Windows), which has no browser bar, the device's settings. Hub and SaaS
// are the real ones. Tauri does not run in Playwright: the app's bridge is simulated at the edge (`window.__TAURI__`),
// as `fix-ui-shell-appointment-notices.spec.ts` does. The microphone is refused by Chrome itself: its fake media prompt
// answers «Block» (`--use-fake-ui-for-media-stream=deny`, a launch option, so a file of its own: the dictation of
// `base-assistant.spec.ts` needs the prompt that accepts).
// flow: BASE-F94
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, compactBar, login, shot, shown, untilStill } from './helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const KEY = 'FIX-HUB-BASE-MIC-DENIED-SAYS-BROWSER-INSIDE-THE-APP';

test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream=deny', '--use-fake-device-for-media-stream'] },
});

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const mic = (page: Page): Locator => panel(page).locator('[data-testid="assistant-mic"]');
const problem = (page: Page): Locator => panel(page).locator('[data-testid="assistant-composer-problem"]');
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

/** The Home with the assistant's panel open, and a tap on «Dictate by voice». */
async function refuse(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(opener(page)).toBeVisible();
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await mic(page).click();
}

test('BASE-F94 — a refused microphone points to the browser, and inside the installed app to the device settings', async ({ page, context }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await refuse(page);
  await expect(problem(page)).toHaveText('Microphone access is blocked. Allow it in your browser to dictate.');

  await page.addInitScript(() => {
    (window as unknown as { __TAURI__: unknown }).__TAURI__ = { core: { invoke: async () => null } };
  });
  await refuse(page);
  await expect(problem(page)).toHaveText('Microphone access is blocked. Allow it in your device settings to dictate.');

  // In Spanish (the Hub's language cookie, as the sign-in sets it).
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await refuse(page);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(problem(page)).toHaveText(
      'El acceso al micrófono está denegado. Permítelo en los ajustes del dispositivo para dictar.',
    );
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-${vp.label}`) });
  }
});
