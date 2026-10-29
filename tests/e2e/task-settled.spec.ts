// flow: task-e2e-wait — FIX of the Tasks specs' wait (FIX-HUB-TASK-E2E-WAIT-COUNTS-ONLY-OVERLAYS)
// Every capture of a Tasks flow goes through `snap()` (task-helpers.ts), which waits for the screen to stop moving
// first. Its own wait counted Ionic's modals and popovers while they slid in or out and nothing else: a toast entering
// passed for still, and the capture caught it half in (TASK-F05: «Start» from a row says «Task started»). Here that
// notice enters at a fifth of its speed (Chrome's own control) and, once `snap()` returns, nothing may move, asked
// with the harness's own detector (`exposeMovingInPage`, helpers.ts), at 390, 834 and 1440. The answer to «Start» is
// held until the click's own motion (the row's «⋮» menu leaving, where the row folds its actions) has ended at full
// speed: the toast is the only thing entering slowly. What a run creates is named «E2E Task …» and deleted after it.
import { type CDPSession, expect, type Page, test } from '@playwright/test';

import { A, capture, exposeMovingInPage, shown, untilStill } from './helpers';
import { cleanUp, FLOW_VIEWPORTS, named, post, rowAction, rowOf, signedIn, snap, VIEWPORTS } from './task-helpers';

const KEY = 'FIX-HUB-TASK-E2E-WAIT-COUNTS-ONLY-OVERLAYS';

/** The command behind «Start» (`task.task.set_status`). */
const SET_STATUS = '**/api/task/tasks/set_status';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/** What moves on the page now, by the detector of helpers.ts put in the page (`exposeMovingInPage`). */
async function moving(page: Page): Promise<string[]> {
  await exposeMovingInPage(page);
  return page.evaluate(() => (window as unknown as { __movingInPage: () => string[] }).__movingInPage());
}

/** Every animation of the page at `rate` times its speed. */
async function playbackRate(devtools: CDPSession, rate: number): Promise<void> {
  await devtools.send('Animation.setPlaybackRate', { playbackRate: rate });
}

/** Holds every «Start» the page sends until the returned function is called. */
async function holdStart(page: Page): Promise<() => void> {
  let release = (): void => undefined;
  const released = new Promise<void>((done) => (release = done));
  await page.route(SET_STATUS, async (route) => {
    await released;
    await route.continue();
  });
  return release;
}

test('task-e2e-wait: after snap() the «Task started» notice has stopped entering, at 390, 834 and 1440', async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const { context, page } = await signedIn(browser, '/task/tasks', undefined, VIEWPORTS.desktop);
  const devtools = await context.newCDPSession(page);
  await devtools.send('Animation.enable');
  try {
    for (const [width, viewport] of Object.entries(FLOW_VIEWPORTS)) {
      const title = named(`Settled ${width} ${stamp}`);
      const task = await post<{ id: string }>(context, '/task/tasks', { title });
      await page.setViewportSize(viewport);
      await playbackRate(devtools, 1);
      await page.goto(`${A}/task/tasks`);
      await shown(page).locator('[data-testid=task-tasks-search] input').fill(stamp);
      await expect(rowOf(page, 'task-tasks', title)).toContainText('To Do');
      await untilStill(page);

      const release = await holdStart(page);
      await rowAction(page, 'task-tasks', task.id, 'start');
      // Ionic hides an inline popover again (`overlay-hidden`) once it has left.
      await expect(page.locator('ion-popover:not(.overlay-hidden)')).toHaveCount(0);
      await untilStill(page);
      await playbackRate(devtools, 0.2);
      release();
      const notice = page.locator('ion-toast').filter({ hasText: 'Task started' });
      await expect(notice).toBeVisible();
      await snap(page, 'E2E-WAIT', width);
      expect.soft(await moving(page), `still moving after snap() at ${width}`).toEqual([]);
      await capture(page, `${KEY}-${width}`);

      await page.unroute(SET_STATUS);
      await playbackRate(devtools, 1);
      await expect(rowOf(page, 'task-tasks', title)).toContainText('In Progress');
      await expect(notice).toBeHidden({ timeout: 15_000 });
    }
  } finally {
    await playbackRate(devtools, 1);
    await context.close();
  }
});
