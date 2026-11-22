// Inventory's help plays its own video from YouTube, so unlike base-help.spec.ts this spec reaches the real player.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, settled } from './helpers';
import {
  embed,
  expectSixteenByNine,
  expectTaskVideo,
  helpVideoPage,
  leaveHelpVideoPage,
  openTask as openHelpTask,
} from './help-video-helpers';
import { THREE_SIZES_TALL_TABLET } from './screen';

const VIDEO = 'dIppfjMEKWo';
const SRC = embed(VIDEO);
/** «Dar de alta un producto», on the Products tab, and its short video in Spanish. */
const TASK = 'help-flow-products-INVENTORY-F01';
const TASK_VIDEO = 'L4LipaZOq40';

let context: BrowserContext;
let page: Page;
const turnedOn: string[] = [];
const youtubeRequests: string[] = [];

const frame = () => page.locator('iframe.youtube-embed__player');
const player = () => page.frameLocator('iframe.youtube-embed__player');

async function playInventoryVideo(): Promise<void> {
  await page.goto(`${A}/inventory/products`);
  await page.getByTestId('help-button').click();
  await expect(page.getByTestId('help-content')).toBeVisible();
  await page.locator('.youtube-embed__poster').click();
  await expect(player().locator('.html5-video-player')).toBeVisible();
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  const opened = { path: '/inventory/products', apps: ['inventory'], turnedOn, requests: youtubeRequests };
  ({ context, page } = await helpVideoPage(browser, opened));
});

/** Opens «Dar de alta un producto» on a fresh page. */
const openTask = () => openHelpTask(page, `${A}/inventory/products`, TASK, youtubeRequests);

test.afterAll(() => leaveHelpVideoPage(context, turnedOn));

for (const size of THREE_SIZES_TALL_TABLET) {
  test(`at ${size.label} px the Spanish video plays in YouTube's full player, 16:9 across the help window`, async () => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await playInventoryVideo();
    await expect(frame()).toHaveAttribute('src', SRC);
    await expect(frame()).toHaveAttribute('allowfullscreen', '');
    await expect(frame()).toHaveAttribute('allow', 'autoplay; encrypted-media; picture-in-picture; fullscreen');
    await expectSixteenByNine(page, frame(), '[data-help-section="video"]');

    const { x, y, width, height } = (await frame().boundingBox())!;
    await page.mouse.move(x + width / 2, y + height / 2);
    await settled(page);
    await capture(page, `help-video-${size.label}`);
    await page.getByTestId('help-close').click();
  });
}

test("the player's own YouTube link opens the video in a new tab and leaves the Hub where it was", async () => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await playInventoryVideo();
  const { x, y, width, height } = (await frame().boundingBox())!;
  await page.mouse.move(x + width / 2, y + height / 2);
  const opened = context.waitForEvent('page');
  await player().locator(`a[target="_blank"][href*="watch?v=${VIDEO}"]`).first().click({ force: true });
  const tab = await opened;
  // Decoded, so a consent page that YouTube puts first still names the video it continues to.
  expect(decodeURIComponent(tab.url())).toContain(`https://www.youtube.com/watch?v=${VIDEO}`);
  await tab.close();
  await expect(page).toHaveURL(`${A}/inventory/products`);
  await expect(frame()).toBeVisible();
});

for (const size of THREE_SIZES_TALL_TABLET) {
  test(`at ${size.label} px an opened task shows its own video before its steps, asking YouTube nothing until tapped`, async () => {
    await page.setViewportSize({ width: size.width, height: size.height });
    const task = await openTask();
    const video = { title: 'Dar de alta un producto', video: TASK_VIDEO, shot: `help-task-video-${size.label}` };
    await expectTaskVideo(page, task, video, youtubeRequests);
    await page.getByTestId('help-close').click();
  });
}

test('offline, an opened task says its video is not available and keeps its steps in view', async () => {
  await page.setViewportSize({ width: 834, height: 1194 });
  const task = await openTask();
  await context.setOffline(true);
  try {
    await expect(task.locator('.youtube-embed__offline')).toContainText('Sin conexión: el vídeo no está disponible');
    await expect(task.locator('.assistant-md').first()).toBeVisible();
    await settled(page);
    await capture(page, 'help-task-video-offline-834');
  } finally {
    await context.setOffline(false);
  }
  await page.getByTestId('help-close').click();
});
