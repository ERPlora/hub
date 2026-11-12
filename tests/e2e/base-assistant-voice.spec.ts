// «Read aloud» of the assistant's answers (BASE-F93 step 8), end to end with the stack's Hub and SaaS and the e2e's
// provider (assistant-provider.ts, started here; README «El asistente»). Headless Chrome has no voice of its own to read
// with, so the device's `speechSynthesis.speak` is recorded at the edge.
// - By default there is no server voice (`ASSISTANT_SERVER_VOICE` off): the panel offers no choice
//   of voice and reads with the device's, never asking the Hub.
// - With the stack's Hub started with `ASSISTANT_SERVER_VOICE=True`: nothing to choose
//   (`@erplora/ui` names no voices, and the Hub gives none), and «Read aloud» asks the Hub
//   (`/api/assistant/speak`), which asks the SaaS (`/internal/speech/synthesize`). The SaaS has no engine that reads:
//   the Hub answers 503 in its envelope and the panel reads with the device's voice, with no unhandled error.
//   And the server's audio plays from a `blob:` under the Hub's real CSP (`media-src`): there, and only there, the Hub's
//   answer is replaced in the browser by a short silence made here (a WAV), the one way to hear a server voice without a
//   key; a CSP without `blob:` makes the player fail and the device read instead, which the test catches.
// Each test runs on the stack whose Hub has its setting and is skipped on the other: run the spec once with each.
// flow: BASE-F93
import { expect, type Locator, type Page, test } from '@playwright/test';

import { GREETING, type Provider, startProvider } from './assistant-provider';
import { emptyMonth, openPanel, panel, saasSql } from './assistant-real';
import { capture, login, A } from './helpers';
import { STACK } from './stack';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const KEY = 'APP-BASE-9-SERVER-VOICE';
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);

let provider: Provider;

test.beforeAll(async () => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${STACK.saasDatabase} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
});

test.afterAll(async () => {
  await provider?.close();
});

test.beforeEach(() => {
  emptyMonth();
});

const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]').last();
const voice = (page: Page): Locator => panel(page).locator('[data-testid="assistant-voice"]');
const listen = (page: Page): Locator => lastAnswer(page).locator('[data-testid="assistant-listen"]');

/** What the device's voice was asked to read: its `speak` recorded, each utterance ending a moment later. */
async function recordDevice(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const said: { text: string; lang: string }[] = [];
    (window as unknown as { __deviceSaid: typeof said }).__deviceSaid = said;
    const synth = window.speechSynthesis;
    synth.speak = (utterance: SpeechSynthesisUtterance) => {
      said.push({ text: utterance.text, lang: utterance.lang });
      setTimeout(() => utterance.onend?.(new SpeechSynthesisEvent('end', { utterance })), 300);
    };
    synth.cancel = () => undefined;
  });
}

const deviceSaid = (page: Page): Promise<{ text: string; lang: string }[]> =>
  page.evaluate(() => (window as unknown as { __deviceSaid: { text: string; lang: string }[] }).__deviceSaid);

/** What went wrong in the page and nobody handled: thrown errors and rejected promises, and any CSP refusal. */
function watchProblems(page: Page): string[] {
  const problems: string[] = [];
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error' && /Content Security Policy|Uncaught|Unhandled/i.test(message.text())) {
      problems.push(`console: ${message.text()}`);
    }
  });
  return problems;
}

/** Whether the stack's Hub reads aloud in a server voice (`hub-home.server_voice`, `ASSISTANT_SERVER_VOICE`). */
const serverVoice = (page: Page): Promise<boolean> =>
  page.evaluate(() => JSON.parse(document.getElementById('hub-home')?.textContent || '{}').server_voice === true);

/** The Home in Spanish (the Hub's language cookie, as the sign-in sets it: the e2e's account is in English) with the
 *  panel open and one answer of the e2e's provider. */
async function answered(page: Page): Promise<void> {
  await login(page, A, '/');
  await page.context().addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await box(page).fill('Hola');
  await box(page).press('Enter');
  await expect(lastAnswer(page).locator('[data-testid="assistant-bubble-assistant"]')).toHaveText(GREETING.es);
  await expect(listen(page)).toBeVisible();
}

test('BASE-F93 — with no server voice (the default) there is no choice of voice and the device reads the answer, never asking the Hub', async ({ page }) => {
  const problems = watchProblems(page);
  const asked: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/assistant/speak')) asked.push(request.url());
  });
  await recordDevice(page);
  await answered(page);
  test.skip(await serverVoice(page), 'the stack reads aloud in a server voice (ASSISTANT_SERVER_VOICE=True)');

  await expect(voice(page)).toHaveCount(0);
  await listen(page).click();
  await expect.poll(() => deviceSaid(page)).toEqual([{ text: GREETING.es, lang: 'es-ES' }]);
  await expect(listen(page)).toHaveText('Leer en voz alta');
  await expect(panel(page).locator('[data-testid="assistant-listen-failed"]')).toHaveCount(0);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(listen(page)).toBeVisible();
    await capture(page, `${KEY}-device-only-${vp.label}`);
  }
  expect(asked).toEqual([]);
  expect(problems).toEqual([]);
});

test('BASE-F93 — with the server’s voice on there is nothing to choose: the Hub asks the SaaS, which has none, and the device reads the answer', async ({ page }) => {
  const problems = watchProblems(page);
  await recordDevice(page);
  await answered(page);
  test.skip(!(await serverVoice(page)), 'the stack has no server voice (ASSISTANT_SERVER_VOICE off, the default)');

  await expect(voice(page)).toHaveCount(0);

  // «Leer en voz alta»: the Hub asks the SaaS, which has no voice here; the device reads it instead.
  await page.setViewportSize({ width: 1440, height: 900 });
  const spoken = page.waitForResponse((response) => response.url().endsWith('/api/assistant/speak'));
  await listen(page).click();
  const response = await spoken;
  expect(response.status()).toBe(503);
  expect((await response.json()).error.code).toMatch(/^base\.assistant_speech_(unavailable|failed)$/);
  expect(JSON.parse(response.request().postData() ?? '{}')).toEqual({
    text: GREETING.es,
    language: 'es',
    voice: '',
  });
  await expect.poll(() => deviceSaid(page)).toEqual([{ text: GREETING.es, lang: 'es-ES' }]);
  await expect(listen(page)).toHaveText('Leer en voz alta');
  await expect(panel(page).locator('[data-testid="assistant-listen-failed"]')).toHaveCount(0);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(listen(page)).toBeVisible();
    await capture(page, `${KEY}-answer-${vp.label}`);
  }
  expect(problems).toEqual([]);
});

/** A short silence as a WAV (8 kHz, 8-bit mono): a server's audio the browser plays without any key. */
function silence(seconds = 1.5): Buffer {
  const samples = Math.round(8000 * seconds);
  const wav = Buffer.alloc(44 + samples, 0x80);
  wav.write('RIFF', 0);
  wav.writeUInt32LE(36 + samples, 4);
  wav.write('WAVEfmt ', 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8000, 24);
  wav.writeUInt32LE(8000, 28);
  wav.writeUInt16LE(1, 32);
  wav.writeUInt16LE(8, 34);
  wav.write('data', 36);
  wav.writeUInt32LE(samples, 40);
  return wav;
}

test('BASE-F93 — the server’s audio plays from a blob: under the Hub’s CSP, and the device reads nothing', async ({ page }) => {
  const problems = watchProblems(page);
  await recordDevice(page);
  await answered(page);
  test.skip(!(await serverVoice(page)), 'the stack has no server voice (ASSISTANT_SERVER_VOICE off, the default)');
  await page.route('**/api/assistant/speak', (route) => route.fulfill({ status: 200, contentType: 'audio/wav', body: silence() }));

  await listen(page).click();
  await expect(listen(page)).toHaveText('Dejar de leer');
  await expect(listen(page)).toHaveText('Leer en voz alta', { timeout: 10_000 });
  expect(await deviceSaid(page)).toEqual([]);
  await expect(panel(page).locator('[data-testid="assistant-listen-failed"]')).toHaveCount(0);
  expect(problems).toEqual([]);
});
