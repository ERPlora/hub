// A refused microphone in the assistant's composer says where to allow it again (BASE-F94): in a browser, the
// browser; inside the installed app (Android, Windows), which has no browser bar, the device's settings. Hub and SaaS
// are the real ones. Tauri does not run in Playwright: the app's bridge is simulated at the edge (`window.__TAURI__`),
// as `fix-ui-shell-appointment-notices.spec.ts` does. The microphone is refused by Chrome itself: its fake media prompt
// answers «Block» (`--use-fake-ui-for-media-stream=deny`, a launch option, so a file of its own: the dictation of
// `base-assistant.spec.ts` needs the prompt that accepts).
// And one recording per tap (FIX-HUB-BASE-ASSISTANT-MIC-DOUBLE-TAP-OPENS-TWO-RECORDINGS): a second tap while the
// browser still asks for the microphone opens no second one. There the browser's question takes a moment and its
// microphone is a tone of the page's own (`getUserMedia` replaced at the edge: Chrome's fake prompt of this file
// blocks), recorded by the browser's real `MediaRecorder`; erplora.com transcribes it with the e2e's provider
// (assistant-provider.ts, started by that test; README «El asistente»).
// flow: BASE-F94
import { expect, type Locator, type Page, test } from '@playwright/test';

import { DICTATION, startProvider } from './assistant-provider';
import { A, compactBar, login, shot, shown, untilStill } from './helpers';
import { STACK } from './stack';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const KEY = 'FIX-HUB-BASE-MIC-DENIED-SAYS-BROWSER-INSIDE-THE-APP';
const DOUBLE_TAP_KEY = 'FIX-HUB-BASE-ASSISTANT-DICTATION-NOT-EXPORTED';

const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** How long the browser takes to ask for the microphone: time enough for a second tap. */
const ASKING_MS = 1500;

test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream=deny', '--use-fake-device-for-media-stream'] },
});

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const mic = (page: Page): Locator => panel(page).locator('[data-testid="assistant-mic"]');
const problem = (page: Page): Locator => panel(page).locator('[data-testid="assistant-composer-problem"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

/** The Home with the assistant's panel open. */
async function openPanel(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(opener(page)).toBeVisible();
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
}

/** The Home with the assistant's panel open, and a tap on «Dictate by voice». */
async function refuse(page: Page): Promise<void> {
  await openPanel(page);
  await mic(page).click();
}

/** How many times the page asked for the microphone. */
const asked = (page: Page): Promise<number> =>
  page.evaluate(() => (window as unknown as { __microphoneAsked: number }).__microphoneAsked);

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

test('BASE-F94 — two taps while the browser asks for the microphone open one recording, and the next tap transcribes it into the box', async ({ page }) => {
  const provider = await startProvider(PROVIDER_PORT);
  try {
    const transcriptions: string[] = [];
    page.on('request', (request) => {
      if (request.url().includes('/api/assistant/transcribe')) transcriptions.push(request.url());
    });
    await page.addInitScript((waits: number) => {
      const counted = window as unknown as { __microphoneAsked: number };
      counted.__microphoneAsked = 0;
      navigator.mediaDevices.getUserMedia = async () => {
        counted.__microphoneAsked += 1;
        await new Promise((resolve) => setTimeout(resolve, waits));
        const audio = new AudioContext();
        const tone = audio.createOscillator();
        const microphone = audio.createMediaStreamDestination();
        tone.connect(microphone);
        tone.start();
        await audio.resume();
        return microphone.stream;
      };
    }, ASKING_MS);
    await login(page, A, '/');
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    await mic(page).click();
    await mic(page).click();
    await expect(mic(page)).toHaveAttribute('aria-pressed', 'true');
    expect(await asked(page)).toBe(1);
    await page.waitForTimeout(1200);
    await mic(page).click();
    await expect(box(page)).toHaveValue(DICTATION);
    await expect(mic(page)).toHaveAttribute('aria-pressed', 'false');
    await expect(problem(page)).toHaveCount(0);
    expect([await asked(page), transcriptions.length]).toEqual([1, 1]);
    // Nothing was asked: the words wait in the box for «Send».
    expect(provider.seen.filter((seen) => seen.path === '/v1/chat/completions')).toEqual([]);

    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(box(page)).toHaveValue(DICTATION);
      await untilStill(page);
      await page.screenshot({ path: shot(`${DOUBLE_TAP_KEY}-${vp.label}`) });
    }
  } finally {
    await provider.close();
  }
});
