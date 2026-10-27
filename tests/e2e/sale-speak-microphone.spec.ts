// A refused microphone on the till's «Speak» key says where to allow it again (FIX-HUB-SALE-SPEAK-KEY-MIC-DENIED-SAYS-
// BROWSER-INSIDE-THE-APP; apps/sale/WORKBOOK.md «Estados», «Hablando (Vender)»): in a browser, the browser; inside the
// installed app (Android, Windows), which has no browser bar, the device's settings, as the assistant's composer
// (base-assistant-microphone.spec.ts, BASE-F94). The Hub and its SaaS are the real ones. Tauri does not run in
// Playwright: the app's bridge is simulated at the edge (`window.__TAURI__`). The microphone is refused by Chrome
// itself: its fake media prompt answers «Block» (`--use-fake-ui-for-media-stream=deny`, a launch option, so a file of
// its own: the dictation of `sale-speak.spec.ts` needs the prompt that accepts).
// flow: SALE-F01
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, EMPLOYEE, login, shot, untilStill } from './helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const KEY = 'FIX-HUB-SALE-SPEAK-KEY-MIC-DENIED-SAYS-BROWSER-INSIDE-THE-APP';

test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream=deny', '--use-fake-device-for-media-stream'] },
});

const key = (page: Page): Locator => page.locator('[data-testid="pos-speak"]');

/** The till, and a tap on «Speak»: a toast says how to allow the microphone, and nothing records. */
async function refuse(page: Page, label: string, notice: string): Promise<void> {
  await page.goto(`${A}/sale/pos`);
  await expect(key(page)).toHaveText(label);
  await key(page).click();
  await expect(page.locator('ion-toast').filter({ hasText: notice })).toBeVisible();
  await expect(key(page)).toHaveAttribute('aria-pressed', 'false');
  await expect(key(page)).toHaveText(label);
  await expect(page.locator('[data-testid="pos-speak-status"]')).toHaveCount(0);
}

test('SALE-F01 — a refused microphone on «Speak» points to the browser, and inside the installed app to the device settings', async ({ page, context }) => {
  const transcriptions: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/assistant/transcribe')) transcriptions.push(request.url());
  });
  await login(page, A, '/sale/pos', EMPLOYEE);
  await page.setViewportSize({ width: 1440, height: 900 });
  await refuse(page, 'Speak', 'Microphone access is blocked. Allow it in your browser to speak.');

  await page.addInitScript(() => {
    (window as unknown as { __TAURI__: unknown }).__TAURI__ = { core: { invoke: async () => null } };
  });
  await refuse(page, 'Speak', 'Microphone access is blocked. Allow it in your device settings to speak.');

  // In Spanish (the Hub's language cookie, as the sign-in sets it).
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await refuse(page, 'Hablar', 'El acceso al micrófono está denegado. Permítelo en los ajustes del dispositivo para hablar.');
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-${vp.label}`) });
  }
  expect(transcriptions).toEqual([]);
});
