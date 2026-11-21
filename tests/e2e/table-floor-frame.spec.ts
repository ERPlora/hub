// A zone whose only table was placed at the bottom right of the plan shows that table in Service without scrolling: at
// 1440x900, on a landscape tablet (1280x800) and a portrait one (820x1180) the plan frames the zone's tables, and on a
// 375x667 phone Service is the cards. The zone this file makes is removed afterwards.
import { expect, type Page, test } from '@playwright/test';

import { capture, psql, settled, shown } from './helpers';
import { ownerPage, post } from './service-helpers';

const ZONE = `E2E Frame ${Date.now().toString(36).toUpperCase()}`;
const SIZES = [
  { label: '1440', width: 1440, height: 900 },
  { label: '1280', width: 1280, height: 800 },
  { label: '820', width: 820, height: 1180 },
  { label: '375', width: 375, height: 667 },
];

const cleanUp = () =>
  psql(
    "delete from table_table where zone_id in (select id from table_zone where name like 'E2E Frame %'); " +
      "delete from table_zone where name like 'E2E Frame %'",
  );

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

interface Seen {
  /** How far the table sticks out of the box it is shown in, on each side (0 when it is whole inside). */
  outside: number;
  /** How far the box it is shown in can still scroll, across and down. */
  scroll: [number, number];
}

/** Where the table is against the plan's stage, or against the screen for the phone's cards. */
async function seen(page: Page, tableId: string): Promise<Seen> {
  return shown(page)
    .locator(`[data-testid="table-floor-tile-${tableId}"]`)
    .evaluate((tile) => {
      const stage = tile.closest<HTMLElement>('[data-testid="table-floor-stage"]');
      const frame = stage?.getBoundingClientRect() ?? { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
      const box = tile.getBoundingClientRect();
      const outside = Math.max(0, frame.left - box.left, frame.top - box.top, box.right - frame.right, box.bottom - frame.bottom);
      const scroll: [number, number] = stage
        ? [stage.scrollWidth - stage.clientWidth, stage.scrollHeight - stage.clientHeight]
        : [0, 0];
      return { outside: Math.round(outside), scroll };
    });
}

test('A zone whose only table is at the bottom right of the plan shows it in Service without scrolling, at every size', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan', { width: SIZES[0].width, height: SIZES[0].height });
  try {
    const zone = await post<{ id: string }>(context, '/table/zones', { name: ZONE });
    const table = await post<{ id: string }>(context, '/table/tables', { zone_id: zone.id, number: '1', position_x: 700, position_y: 500 });
    await page.reload();
    await shown(page).locator(`[data-testid=table-floor-zone-tab-${zone.id}]`).click();
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await expect(shown(page).locator(`[data-testid="table-floor-tile-${table.id}"]`)).toBeVisible();
      await settled(page);
      expect(await seen(page, table.id), `the table whole on the screen, unscrolled, at ${size.label}`).toEqual({ outside: 0, scroll: [0, 0] });
      await capture(page, `table-floor-frame-${size.label}`);
    }
  } finally {
    await context.close();
  }
});
