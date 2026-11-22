// The short video of a task in a module's help window, the same in every module that declares one.
import { expect, type Locator, type Page } from '@playwright/test';

import { horizontalOverflow } from './helpers';

/** The address the help's player opens for `video`, with the subtitles and the player in Spanish. */
export const embed = (video: string): string =>
  `https://www.youtube-nocookie.com/embed/${video}?autoplay=1&rel=0&playsinline=1&cc_load_policy=1&cc_lang_pref=es&hl=es`;

/** Appends to `requests` every address the page asks of YouTube: its player, its images and its video. */
export function recordYouTube(page: Page, requests: string[]): void {
  page.on('request', (request) => {
    if (/youtube|ytimg|googlevideo/.test(new URL(request.url()).hostname)) requests.push(request.url());
  });
}

/** The opened body of the task whose header is `task` (`help-flow-<tab>-<flow>`). */
export const taskBody = (page: Page, task: string): Locator =>
  page.getByTestId(task.replace('help-flow-', 'help-flow-content-'));

/**
 * Opens `task` in the help of the screen at `path`, on a fresh page: `requests` is emptied once the page has loaded,
 * so what a player of an earlier test sent to YouTube while its page unloaded is not counted.
 */
export async function openTask(page: Page, path: string, task: string, requests: string[]): Promise<Locator> {
  await page.goto(path);
  await expect(page.getByTestId('help-button')).toBeVisible();
  requests.length = 0;
  await page.getByTestId('help-button').click();
  await expect(page.getByTestId('help-content')).toBeVisible();
  await page.getByTestId(task).click();
  await expect(taskBody(page, task)).toBeVisible();
  return taskBody(page, task);
}

/** Whether the first video of an opened task comes before its steps. */
export function videoBeforeSteps(task: Locator): Promise<boolean> {
  return task.evaluate((element) => {
    const video = element.querySelector('.youtube-embed')!;
    const steps = element.querySelector('.assistant-md')!;
    return Boolean(video.compareDocumentPosition(steps) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
}

/** Expects `player` to fill the width of `room` at 16:9, with nothing on the page past its right edge. */
export async function expectSixteenByNine(page: Page, player: Locator, room: string): Promise<void> {
  const box = await player.evaluate((element, selector) => {
    const own = element.getBoundingClientRect();
    return { width: own.width, height: own.height, room: element.closest(selector)!.clientWidth };
  }, room);
  expect(Math.abs(box.width - box.room)).toBeLessThanOrEqual(1);
  expect(Math.abs(box.height - (box.width * 9) / 16)).toBeLessThanOrEqual(1);
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
}
