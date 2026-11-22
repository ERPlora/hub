// Sales' help shows the short video of a task where its steps are read, as Inventory's does (base-help-video.spec.ts).
import { type BrowserContext, type Page, test } from '@playwright/test';

import { A } from './helpers';
import { expectTaskVideo, helpVideoPage, leaveHelpVideoPage, openTask } from './help-video-helpers';
import { THREE_SIZES_TALL_TABLET } from './screen';

/** «Vender y cobrar en efectivo», on the Sell tab. */
const TASK = 'help-flow-pos-SALE-F01';

let context: BrowserContext;
let page: Page;
const turnedOn: string[] = [];
const youtubeRequests: string[] = [];

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  const opened = { path: '/sale/pos', apps: ['tax', 'customer', 'sale'], turnedOn, requests: youtubeRequests };
  ({ context, page } = await helpVideoPage(browser, opened));
});

test.afterAll(() => leaveHelpVideoPage(context, turnedOn));

for (const size of THREE_SIZES_TALL_TABLET) {
  test(`at ${size.label} px «Vender y cobrar en efectivo» shows its own video before its steps, asking YouTube nothing until tapped`, async () => {
    await page.setViewportSize({ width: size.width, height: size.height });
    const task = await openTask(page, `${A}/sale/pos`, TASK, youtubeRequests);
    const video = { title: 'Vender y cobrar en efectivo', video: '0j9NMnpgXWM', shot: `sale-help-task-video-${size.label}` };
    await expectTaskVideo(page, task, video, youtubeRequests);
    await page.getByTestId('help-close').click();
  });
}
