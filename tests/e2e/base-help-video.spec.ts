// Inventory's help plays its own video from YouTube, so unlike base-help.spec.ts this spec reaches the real player.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, horizontalOverflow, settled, signedInSpanish, turnOffTurnedOn, turnOnMissing } from './helpers';
import { THREE_SIZES_TALL_TABLET } from './screen';

const VIDEO = 'dIppfjMEKWo';
const SRC =
  `https://www.youtube-nocookie.com/embed/${VIDEO}?autoplay=1&rel=0&playsinline=1&cc_load_policy=1&cc_lang_pref=es&hl=es`;

let context: BrowserContext;
let page: Page;
const turnedOn: string[] = [];

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
  ({ context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, '/inventory/products'));
  await turnOnMissing(context, A, ['inventory'], turnedOn);
});

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
