// flow: website-e2e — FIX of the website specs' wait (FIX-HUB-WEBSITE-E2E-WAIT-BLIND-TO-SHADOW-ROOTS)
// The website specs wait for the page to be at rest before each capture (`atRest`, website-helpers.ts). That wait
// asked `document.getAnimations()`, which leaves shadow roots out, and Ionic animates its overlays (`ion-modal`,
// `ion-toast`) and an `ion-segment`'s indicator inside theirs: in the editor, right after it, the «Publish your
// website?» dialog was still sliding in. Here that dialog enters at a fifth of its speed (Chrome's own control), and
// once `atRest` returns nothing may move, asked with the harness's own detector (`exposeMovingInPage`, helpers.ts),
// at 390, 834 and 1440. The dialog is cancelled each time: the site is not published.
import { type CDPSession, expect, type Page, test } from '@playwright/test';

import { A, capture, exposeMovingInPage, hostPage, repeatedTop } from './helpers';
import { atRest } from './website-helpers';

const KEY = 'FIX-HUB-WEBSITE-E2E-WAIT-BLIND-TO-SHADOW-ROOTS';

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** What moves on the page now, by the detector of helpers.ts put in the page (`exposeMovingInPage`). */
async function moving(page: Page): Promise<string[]> {
  await exposeMovingInPage(page);
  return page.evaluate(() => (window as unknown as { __movingInPage: () => string[] }).__movingInPage());
}

/** Every animation of the page at `rate` times its speed. */
async function playbackRate(devtools: CDPSession, rate: number): Promise<void> {
  await devtools.send('Animation.setPlaybackRate', { playbackRate: rate });
}

test('website-e2e: after the website specs’ wait the editor’s «Publish» dialog has stopped entering, at 390, 834 and 1440', async ({
  browser,
}) => {
  const { context, page } = await hostPage(browser, A, { next: '/website', viewport: SIZES[2] });
  const devtools = await context.newCDPSession(page);
  await devtools.send('Animation.enable');
  try {
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await playbackRate(devtools, 1);
      await page.goto(`${A}/website`);
      await expect(page.getByTestId('website-editor')).toBeVisible({ timeout: 30_000 });
      await atRest(page);
      await playbackRate(devtools, 0.2);
      await page.getByTestId('website-publish').click();
      const dialog = page.locator('ion-modal.ep-form-modal').filter({ hasText: 'Publish your website?' });
      await expect(dialog).toBeVisible();
      await atRest(page);
      expect(await moving(page), `still moving after atRest() at ${size.label}`).toEqual([]);
      expect(await repeatedTop(page, await capture(page, `${KEY}-${size.label}`))).toBe(0);
      await playbackRate(devtools, 1);
      await dialog.locator('.ep-form-modal__cancel').click();
      await expect(dialog).toBeHidden();
    }
  } finally {
    await playbackRate(devtools, 1);
    await context.close();
  }
});
