// flow: BASE-F74 — the viewer of Files on a low screen. In Chrome on an Android tablet in landscape the address bar
// takes part of the screen: the page has 665 px of height while `100vh` still counts the 761 px it would have without
// the bar (a viewer sized `92vh` measured 700 px there, hub#2616). The viewer fits the space the page really has, with
// «Download» and «Close» on view, and a video fits its body without scrolling; the same at the fleet's sizes, in
// English and in Spanish, with a screenshot at each.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, settled, shown, testid } from './helpers';

/** The tablet's screen with Chrome's address bar shown: what the page has, and what `100vh` counts. */
const CHROME_LANDSCAPE = { width: 1280, page: 665, withoutBar: 761 };
const SIZES = [
  { width: 1280, height: 665 },
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;
const LANGUAGES = [
  { name: 'English', lang: 'en', locale: 'en-US' },
  { name: 'Spanish', lang: 'es', locale: 'es-ES' },
] as const;
/** A one-second 1280×720 WebM: wider than the viewer, so its height is what has to fit. */
const VIDEO = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'base', 'frontend', '__tests__', 'files', 'sample.webm'));
const NOTE = 'Pay the supplier on Friday.\n';

interface Box {
  top: number;
  bottom: number;
}

interface PreviewFit {
  screen: number;
  window: Box;
  download: Box;
  close: Box;
  body: Box;
  /** How far the viewer's body scrolls: 0 when what it shows fits. */
  bodyScroll: number;
  video: Box | null;
}

/** Where the window (Ionic's wrapper, in the modal's shadow root), «Download», «Close», the body and the video sit,
 *  and the height the page has (the modal's own box, which covers it). */
function fitOf(preview: Locator): Promise<PreviewFit> {
  return preview.evaluate((el) => {
    const box = (part: Element | null | undefined): Box => {
      if (!part) throw new Error('the viewer lost one of its parts');
      const { top, bottom } = part.getBoundingClientRect();
      return { top, bottom };
    };
    const body = el.querySelector('.file-preview-body');
    const video = el.querySelector('[data-testid=file-preview-video]');
    return {
      screen: el.getBoundingClientRect().height,
      window: box(el.shadowRoot?.querySelector('.modal-wrapper')),
      download: box(el.querySelector('[data-testid=file-preview-download]')),
      close: box(el.querySelector('[data-testid=file-preview-close]')),
      body: box(body),
      bodyScroll: body ? body.scrollHeight - body.clientHeight : 0,
      video: video ? box(video) : null,
    };
  });
}

function expectInside(fit: PreviewFit, where: string): void {
  expect(fit.window.top, `the viewer starts on the screen ${where}`).toBeGreaterThanOrEqual(-0.5);
  expect(fit.window.bottom, `the viewer ends on the screen ${where}`).toBeLessThanOrEqual(fit.screen + 0.5);
  for (const [name, part] of [
    ['«Download»', fit.download],
    ['«Close»', fit.close],
    ['body', fit.body],
  ] as const) {
    expect(part.top, `the ${name} starts inside the viewer ${where}`).toBeGreaterThanOrEqual(fit.window.top - 0.5);
    expect(part.bottom, `the ${name} ends inside the viewer ${where}`).toBeLessThanOrEqual(fit.window.bottom + 0.5);
  }
  if (!fit.video) return;
  expect(fit.video.bottom, `the video ends inside the viewer's body ${where}`).toBeLessThanOrEqual(fit.body.bottom + 0.5);
  expect(fit.bodyScroll, `the video fits the viewer's body without scrolling ${where}`).toBeLessThanOrEqual(1);
}

/** Files on screen in `lang` (the Hub's language cookie, which the sign-in has just set from the account). */
async function filesIn(page: Page, context: BrowserContext, lang: string): Promise<void> {
  await login(page, A, '/files');
  await context.addCookies([{ name: 'django_language', value: lang, domain: new URL(A).hostname, path: '/' }]);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${lang}`));
}

async function upload(page: Page, name: string, mimeType: string, buffer: Buffer): Promise<void> {
  await testid(page, 'files-upload-input').setInputFiles({ name, mimeType, buffer });
  await expect(shown(page).locator(`[data-item="${name}"]`)).toBeVisible();
}

/** Opens `name`'s viewer and waits until it stopped entering. */
async function open(page: Page, name: string): Promise<Locator> {
  await shown(page).locator(`[data-item="${name}"] [data-testid="files-item-main"]`).click();
  const preview = page.locator('[data-testid="file-preview"]').last();
  await expect(preview.locator('[data-testid="file-preview-title"]')).toHaveText(name);
  await expect(preview.locator('[data-testid="file-preview-close"]')).toBeVisible();
  await settled(page);
  return preview;
}

/** The video's size is known once its metadata loaded: only then is its box the one it keeps. */
async function videoReady(page: Page, preview: Locator): Promise<void> {
  const video = preview.locator('[data-testid="file-preview-video"]');
  await expect.poll(() => video.evaluate((el) => (el as HTMLVideoElement).readyState)).toBeGreaterThanOrEqual(1);
  await settled(page);
}

for (const language of LANGUAGES) {
  test(`BASE-F74 (${language.name}): on a low screen the viewer fits with «Download» and «Close» on view, and so does a video`, async ({
    browser,
  }) => {
    const note = `fit-${language.lang}.txt`;
    const video = `fit-${language.lang}.webm`;
    const context = await browser.newContext({
      baseURL: A,
      locale: language.locale,
      viewport: { width: CHROME_LANDSCAPE.width, height: CHROME_LANDSCAPE.withoutBar },
    });
    const page = await context.newPage();
    try {
      await filesIn(page, context, language.lang);
      await upload(page, note, 'text/plain', Buffer.from(NOTE));
      await upload(page, video, 'video/webm', VIDEO);
      // Chrome's address bar, as on the tablet: the page is 96 px shorter than what `100vh` counts.
      const bar = await page.addStyleTag({ content: `body { height: ${CHROME_LANDSCAPE.page}px !important; max-height: ${CHROME_LANDSCAPE.page}px !important; }` });

      let preview = await open(page, note);
      const fit = await fitOf(preview);
      expect(fit.screen, 'the page is as tall as the screen under the address bar').toBe(CHROME_LANDSCAPE.page);
      expectInside(fit, 'under the address bar');
      await capture(page, `BASE-FILE-PREVIEW-FIT-${language.lang}-1280x665-chrome`);
      await preview.locator('[data-testid="file-preview-close"]').click();
      await expect(preview).toBeHidden();

      preview = await open(page, video);
      await videoReady(page, preview);
      expectInside(await fitOf(preview), 'showing a video under the address bar');
      await capture(page, `BASE-FILE-PREVIEW-FIT-${language.lang}-1280x665-chrome-video`);

      await bar.evaluate((style) => (style as Element).remove());
      for (const size of SIZES) {
        const label = `${size.width}x${size.height}`;
        await page.setViewportSize(size);
        await settled(page);
        const at = await fitOf(preview);
        expect(at.screen, `the page fills the window at ${label}`).toBe(size.height);
        expectInside(at, `at ${label}`);
        await capture(page, `BASE-FILE-PREVIEW-FIT-${language.lang}-${label}`);
      }
    } finally {
      for (const path of [note, video]) await api(context, A, 'POST', '/files/delete', { path });
      await context.close();
    }
  });
}
