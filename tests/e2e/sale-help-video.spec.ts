// Sales' help shows the short video of a task where its steps are read, as Inventory's does (base-help-video.spec.ts).
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, horizontalOverflow, saveSessionForTheSweep, settled, signedInSpanish, turnOffTurnedOn, turnOnMissing } from './helpers';
import { embed, expectSixteenByNine, openTask, recordYouTube, videoBeforeSteps } from './help-video-helpers';
import { THREE_SIZES_TALL_TABLET } from './screen';

/** «Vender y cobrar en efectivo», on the Sell tab, and its short video in Spanish. */
const TASK = 'help-flow-pos-SALE-F01';
const TASK_VIDEO = '0j9NMnpgXWM';

let context: BrowserContext;
let page: Page;
const turnedOn: string[] = [];
const youtubeRequests: string[] = [];

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  ({ context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, '/sale/pos'));
  recordYouTube(page, youtubeRequests);
  await turnOnMissing(context, A, ['tax', 'customer', 'sale'], turnedOn);
  await saveSessionForTheSweep(context);
});

test.afterAll(async () => {
  if (context) {
    await turnOffTurnedOn(context, A, turnedOn);
    await context.close();
  }
});

for (const size of THREE_SIZES_TALL_TABLET) {
  test(`at ${size.label} px «Vender y cobrar en efectivo» shows its own video before its steps, asking YouTube nothing until tapped`, async () => {
    await page.setViewportSize({ width: size.width, height: size.height });
    const task = await openTask(page, `${A}/sale/pos`, TASK, youtubeRequests);
    const poster = task.locator('.youtube-embed__poster');
    await expect(poster).toHaveCount(1);
    await expect(poster).toContainText('Vender y cobrar en efectivo');
    expect(await videoBeforeSteps(task)).toBe(true);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    await poster.scrollIntoViewIfNeeded();
    await settled(page);
    await capture(page, `sale-help-task-video-${size.label}`);
    expect(youtubeRequests).toEqual([]);

    await poster.click();
    const player = task.locator('iframe.youtube-embed__player');
    await expect(player).toHaveAttribute('src', embed(TASK_VIDEO));
    await expect.poll(() => youtubeRequests.length).toBeGreaterThan(0);
    await expectSixteenByNine(page, player, '.youtube-embed');
    await page.getByTestId('help-close').click();
  });
}
