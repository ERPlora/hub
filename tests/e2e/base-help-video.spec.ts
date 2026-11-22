// Inventory's help plays its own video from YouTube, so unlike base-help.spec.ts this spec reaches the real player.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import {
  A,
  capture,
  horizontalOverflow,
  saveSessionForTheSweep,
  settled,
  signedInSpanish,
  turnOffTurnedOn,
  turnOnMissing,
} from './helpers';
import { THREE_SIZES_TALL_TABLET } from './screen';

const VIDEO = 'dIppfjMEKWo';
const embed = (video: string) =>
  `https://www.youtube-nocookie.com/embed/${video}?autoplay=1&rel=0&playsinline=1&cc_load_policy=1&cc_lang_pref=es&hl=es`;
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
const task = () => page.getByTestId(TASK.replace('help-flow-', 'help-flow-content-'));

async function playInventoryVideo(): Promise<void> {
  await page.goto(`${A}/inventory/products`);
  await page.getByTestId('help-button').click();
  await expect(page.getByTestId('help-content')).toBeVisible();
  await page.locator('.youtube-embed__poster').click();
  await expect(player().locator('.html5-video-player')).toBeVisible();
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  ({ context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, '/inventory/products'));
  page.on('request', (request) => {
    const host = new URL(request.url()).hostname;
    if (/youtube|ytimg|googlevideo/.test(host)) youtubeRequests.push(request.url());
  });
  await turnOnMissing(context, A, ['inventory'], turnedOn);
  await saveSessionForTheSweep(context);
});

/** Opens «Dar de alta un producto» on a fresh page: what a player of an earlier test sent while unloading is not counted. */
async function openTask(): Promise<void> {
  await page.goto(`${A}/inventory/products`);
  await expect(page.getByTestId('help-button')).toBeVisible();
  youtubeRequests.length = 0;
  await page.getByTestId('help-button').click();
  await expect(page.getByTestId('help-content')).toBeVisible();
  await page.getByTestId(TASK).click();
  await expect(task()).toBeVisible();
}

test.afterAll(async () => {
  if (context) {
    await turnOffTurnedOn(context, A, turnedOn);
    await context.close();
  }
});

for (const size of THREE_SIZES_TALL_TABLET) {
  test(`at ${size.label} px the Spanish video plays in YouTube's full player, 16:9 across the help window`, async () => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await playInventoryVideo();
    await expect(frame()).toHaveAttribute('src', SRC);
    await expect(frame()).toHaveAttribute('allowfullscreen', '');
    await expect(frame()).toHaveAttribute('allow', 'autoplay; encrypted-media; picture-in-picture; fullscreen');
    const box = await frame().evaluate((element) => {
      const own = element.getBoundingClientRect();
      return { width: own.width, height: own.height, room: element.closest('[data-help-section="video"]')!.clientWidth };
    });
    expect(Math.abs(box.width - box.room)).toBeLessThanOrEqual(1);
    expect(Math.abs(box.height - (box.width * 9) / 16)).toBeLessThanOrEqual(1);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);

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
    await openTask();
    const poster = task().locator('.youtube-embed__poster');
    await expect(poster).toHaveCount(1);
    await expect(poster).toContainText('Dar de alta un producto');
    const before = await task().evaluate((element) => {
      const video = element.querySelector('.youtube-embed')!;
      const steps = element.querySelector('.assistant-md')!;
      return Boolean(video.compareDocumentPosition(steps) & Node.DOCUMENT_POSITION_FOLLOWING);
    });
    expect(before).toBe(true);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    await poster.scrollIntoViewIfNeeded();
    await settled(page);
    await capture(page, `help-task-video-${size.label}`);
    expect(youtubeRequests).toEqual([]);

    await poster.click();
    const own = task().locator('iframe.youtube-embed__player');
    await expect(own).toHaveAttribute('src', embed(TASK_VIDEO));
    await expect.poll(() => youtubeRequests.length).toBeGreaterThan(0);
    const box = await own.evaluate((element) => ({
      width: element.getBoundingClientRect().width,
      height: element.getBoundingClientRect().height,
      room: element.parentElement!.clientWidth,
    }));
    expect(Math.abs(box.width - box.room)).toBeLessThanOrEqual(1);
    expect(Math.abs(box.height - (box.width * 9) / 16)).toBeLessThanOrEqual(1);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    await page.getByTestId('help-close').click();
  });
}

test('offline, an opened task says its video is not available and keeps its steps in view', async () => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await openTask();
  await context.setOffline(true);
  try {
    await expect(task().locator('.youtube-embed__offline')).toContainText('Sin conexión: el vídeo no está disponible');
    await expect(task().locator('.assistant-md').first()).toBeVisible();
    await settled(page);
    await capture(page, 'help-task-video-offline-834');
  } finally {
    await context.setOffline(false);
  }
  await page.getByTestId('help-close').click();
});
