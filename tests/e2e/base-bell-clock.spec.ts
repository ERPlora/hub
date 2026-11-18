// The action center by the clock: a counter whose figure moves as time passes, with no event, asks the bell to read
// it again (`bell_refresh_every` of its module); one that does not — the demo's «open demo items» here — moves with its
// events. Printing asks, for «Nobody is printing …» (PRINTING-F01; fix-hub-printing-bell-silent-with-device-off.spec.ts
// watches its notice move by the clock): the owner sees Printing, so the bell reads its counters again by itself. The
// clock itself is bell-counters.test.ts's. Each viewport leaves a capture.
// flow: PRINTING-F01 BASE-F10
import { expect, test } from '@playwright/test';

import { bellSays, bellTotal, closeActionCenter, noticeIn, openActionCenter } from './action-center';
import { A, api, capture, clearItems, horizontalOverflow, shown, signedInSpanish, uniqueName } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;
/** The bell's own reading of its counters, which only a counter that asks for the clock makes it do. */
const READ_AGAIN = '/api/home/bell';
/** Longer than the shortest period a counter may ask (30 s): a bell reading by itself would show within it. */
const WATCHED_MS = 35_000;
const DEMO_NOTICE = '1 elemento de demo abierto';

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`PRINTING-F01 BASE-F10 — the demo's counter moves with its events, and Printing's asks the bell for the clock, at ${width}`, async ({
    browser,
  }) => {
    const { context, page } = await signedInSpanish(browser, viewport, '/');
    await clearItems(context, A);
    const reads: string[] = [];
    page.on('request', (request) => {
      if (new URL(request.url()).pathname === READ_AGAIN) reads.push(request.url());
    });
    await page.reload();
    await expect(shown(page).locator('h1')).toBeVisible();
    const before = await bellTotal(context);
    await bellSays(page, before);

    // An open demo item raises the demo's counter without a reload: the live query, re-run by its event.
    await api(context, A, 'POST', '/demo/items', { name: uniqueName('Bell clock') });
    await bellSays(page, before + 1);
    const panel = await openActionCenter(page);
    await expect(noticeIn(panel, DEMO_NOTICE)).toHaveCount(1);
    const overflow = await horizontalOverflow(page);
    expect(overflow, `the action center at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
    await capture(page, `FIX-HUB-BASE-PRINT-BELL-IGNORES-DEVICE-PRESENCE-${width}`);
    await closeActionCenter(page);

    if (width === 1440) {
      // Printing's counters ask for the clock (30 s): within more than that period, the bell reads them again by itself.
      await expect.poll(() => reads.length, { timeout: WATCHED_MS }).toBeGreaterThan(0);
    }
    await clearItems(context, A);
    await bellSays(page, before);
    await context.close();
  });
}
