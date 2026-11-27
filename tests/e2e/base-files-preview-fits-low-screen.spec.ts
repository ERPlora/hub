// flow: BASE-F74 — the viewer of Files on a low screen. In Chrome on an Android tablet in landscape the address bar
// takes part of the screen: the page has 665 px of height while `100vh` counts more (a viewer sized `92vh` measured
// 700 px there, hub#2616). The viewer fits the space the page really has, with «Download» and «Close» on view, and a
// video fits its body without scrolling; the same at the fleet's sizes, in English and in Spanish, with a screenshot
// at each.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, settled, shown, testid } from './helpers';
import { CHROME_LANDSCAPE, expectWindowFitsAt, expectWindowOnScreen, FIT_SIZES, underAddressBar, type WindowFit, windowFit } from './screen';
import { dismissToasts } from './toast-helpers';

/** The QA tablet the viewer was measured on: there `100vh` counts 761 px over the page's 665, more than
 *  `CHROME_LANDSCAPE.withoutBar` (at 721 px a viewer of `92vh` still fit). */
const TABLET_WITHOUT_BAR = { width: CHROME_LANDSCAPE.width, height: 761 };
const LANGUAGES = [
  { name: 'English', lang: 'en', locale: 'en-US' },
  { name: 'Spanish', lang: 'es', locale: 'es-ES' },
] as const;
/** What always shows inside the viewer. */
const ON_VIEW = ['«Download»', '«Close»', 'body'] as const;
/** A one-second 1280×720 WebM: wider than the viewer, so its height is what has to fit. */
const VIDEO = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'base', 'frontend', '__tests__', 'files', 'sample.webm'));
const NOTE = 'Pay the supplier on Friday.\n';

function fitOf(preview: Locator): Promise<WindowFit> {
  return windowFit(preview, {
    '«Download»': '[data-testid=file-preview-download]',
    '«Close»': '[data-testid=file-preview-close]',
    body: '.file-preview-body',
  });
}

/** The video ends inside the viewer's body, which shows it whole without scrolling. */
async function expectVideoFits(preview: Locator, where: string): Promise<void> {
  const fit = await preview.evaluate((el) => {
    const body = el.querySelector('.file-preview-body');
    const video = el.querySelector('[data-testid=file-preview-video]');
    if (!body || !video) throw new Error('the viewer shows no video');
    return { video: video.getBoundingClientRect().bottom, body: body.getBoundingClientRect().bottom, scroll: body.scrollHeight - body.clientHeight };
  });
  expect(fit.video, `the video ends inside the viewer's body ${where}`).toBeLessThanOrEqual(fit.body + 0.5);
  expect(fit.scroll, `the video fits the viewer's body without scrolling ${where}`).toBeLessThanOrEqual(1);
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

/** The video with its first frame: its size is known and its box is the one it keeps. */
async function videoReady(page: Page, preview: Locator): Promise<void> {
  const video = preview.locator('[data-testid="file-preview-video"]');
  await expect.poll(() => video.evaluate((el) => (el as HTMLVideoElement).readyState)).toBeGreaterThanOrEqual(2);
  await settled(page);
}

for (const language of LANGUAGES) {
  test(`BASE-F74 (${language.name}): on a low screen the viewer fits with «Download» and «Close» on view, and so does a video`, async ({
    browser,
  }) => {
    const note = `fit-${language.lang}.txt`;
    const video = `fit-${language.lang}.webm`;
    const context = await browser.newContext({ baseURL: A, locale: language.locale, viewport: TABLET_WITHOUT_BAR });
    const page = await context.newPage();
    try {
      await filesIn(page, context, language.lang);
      await upload(page, note, 'text/plain', Buffer.from(NOTE));
      await upload(page, video, 'video/webm', VIDEO);
      await dismissToasts(page);
      const bar = await underAddressBar(page);

      let preview = await open(page, note);
      const fit = await fitOf(preview);
      expect(fit.screen, 'the page is as tall as the screen under the address bar').toBe(CHROME_LANDSCAPE.page);
      expectWindowOnScreen(fit, ON_VIEW, 'under the address bar');
      await capture(page, `BASE-FILE-PREVIEW-FIT-${language.lang}-1280x665-chrome`);
      await preview.locator('[data-testid="file-preview-close"]').click();
      await expect(preview).toBeHidden();

      preview = await open(page, video);
      await videoReady(page, preview);
      expectWindowOnScreen(await fitOf(preview), ON_VIEW, 'showing a video under the address bar');
      await expectVideoFits(preview, 'under the address bar');
      await capture(page, `BASE-FILE-PREVIEW-FIT-${language.lang}-1280x665-chrome-video`);

      await bar.evaluate((style) => (style as Element).remove());
      await expectWindowFitsAt(page, { sizes: FIT_SIZES, measure: () => fitOf(preview), onView: ON_VIEW, name: `BASE-FILE-PREVIEW-FIT-${language.lang}` });
    } finally {
      for (const path of [note, video]) await api(context, A, 'POST', '/files/delete', { path });
      await context.close();
    }
  });
}
