// The short video of a task in a module's help window, the same in every module that declares one.
import { type Browser, type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

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

/** The address the help's player opens for `video`, with the subtitles and the player in Spanish. */
export const embed = (video: string): string =>
  `https://www.youtube-nocookie.com/embed/${video}?autoplay=1&rel=0&playsinline=1&cc_load_policy=1&cc_lang_pref=es&hl=es`;

/** Where a spec of the help's videos opens and what it records: `turnedOn` is for `leaveHelpVideoPage`. */
export interface HelpVideoPage {
  path: string;
  apps: readonly string[];
  turnedOn: string[];
  /** Every address the page asks of YouTube: its player, its images and its video. */
  requests: string[];
}

/** The owner of `a` in Spanish on `path` at 1440×900, with `apps` turned on and what the page asks YouTube recorded. */
export async function helpVideoPage(browser: Browser, opened: HelpVideoPage): Promise<{ context: BrowserContext; page: Page }> {
  const { path, apps, turnedOn, requests } = opened;
  const { context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, path);
  page.on('request', (request) => {
    if (/youtube|ytimg|googlevideo/.test(new URL(request.url()).hostname)) requests.push(request.url());
  });
  await turnOnMissing(context, A, apps, turnedOn);
  await saveSessionForTheSweep(context);
  return { context, page };
}

/** Turns off what `helpVideoPage` turned on and closes its context, if it got that far. */
export async function leaveHelpVideoPage(context: BrowserContext | undefined, turnedOn: string[]): Promise<void> {
  if (!context) return;
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
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

/** The short video an opened task should show: its poster's title, its id in Spanish and the capture's name. */
export interface TaskVideo {
  title: string;
  video: string;
  shot: string;
}

/**
 * Expects the opened `task` to show one poster titled as its video, before its steps, having asked YouTube nothing
 * (captured as `shot`); and, once tapped, to play its video across the task at 16:9.
 */
export async function expectTaskVideo(page: Page, task: Locator, expected: TaskVideo, requests: string[]): Promise<void> {
  const poster = task.locator('.youtube-embed__poster');
  await expect(poster).toHaveCount(1);
  await expect(poster).toContainText(expected.title);
  const before = await task.evaluate((element) => {
    const video = element.querySelector('.youtube-embed')!;
    const steps = element.querySelector('.assistant-md')!;
    return Boolean(video.compareDocumentPosition(steps) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(before).toBe(true);
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  await poster.scrollIntoViewIfNeeded();
  await settled(page);
  await capture(page, expected.shot);
  expect(requests).toEqual([]);

  await poster.click();
  const player = task.locator('iframe.youtube-embed__player');
  await expect(player).toHaveAttribute('src', embed(expected.video));
  await expect.poll(() => requests.length).toBeGreaterThan(0);
  await expectSixteenByNine(page, player, '.youtube-embed');
}
