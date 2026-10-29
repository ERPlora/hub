// The bell by the clock (FIX-HUB-BASE-PRINT-BELL-IGNORES-DEVICE-PRESENCE): a counter whose figure moves as time
// passes, with no event, asks the bell to read it again (`bell_refresh_every` of its module); one that does not —
// the demo's «Open demo items» here — moves with its events, as before. Printing asks, for «Nobody is printing …»
// (PRINTING-F01, FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF, whose spec watches its row move by the clock): the
// owner sees Printing, so the bell reads its rows again by itself. The clock itself is HubBell.test.ts's. Each viewport
// leaves `FIX-HUB-BASE-PRINT-BELL-IGNORES-DEVICE-PRESENCE-<width>`.
// flow: PRINTING-F01 BASE-F10
import { expect, test } from '@playwright/test';

import { A, api, bellBadge, clearItems, horizontalOverflow, hostPage, openBell, shot, shown, uniqueName, untilStill } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;
/** The bell's own reading of its counters, which only a counter that asks for the clock makes it do. */
const READ_AGAIN = '/api/home/bell';
/** Longer than the shortest period a counter may ask (30 s): a bell reading by itself would show within it. */
const WATCHED_MS = 35_000;

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`PRINTING-F01 BASE-F10 — the demo's counter moves with its events, and Printing's asks the bell for the clock, at ${width}`, async ({
    browser,
  }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: '/' });
    await clearItems(context, A);
    const reads: string[] = [];
    page.on('request', (request) => {
      if (new URL(request.url()).pathname === READ_AGAIN) reads.push(request.url());
    });
    await page.goto(`${A}/`);
    await expect(shown(page).locator('h1')).toBeVisible();

    // An open demo item raises the demo's counter without a reload: the live query, re-run by its event.
    await api(context, A, 'POST', '/demo/items', { name: uniqueName('Bell clock') });
    await expect(bellBadge(page)).toHaveText('1');
    await openBell(page);
    const rows = page.locator('ion-popover [data-testid="hub-bell-row"]');
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText('(1)');
    await untilStill(page);
    const overflow = await horizontalOverflow(page);
    expect(overflow, `the bell at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot(`FIX-HUB-BASE-PRINT-BELL-IGNORES-DEVICE-PRESENCE-${width}`) });

    if (width === 1440) {
      // Printing's counters ask for the clock (30 s): within more than that period, the bell reads them again by itself.
      await expect.poll(() => reads.length, { timeout: WATCHED_MS }).toBeGreaterThan(0);
    }
    await clearItems(context, A);
    await expect(bellBadge(page)).toBeHidden();
    await context.close();
  });
}
