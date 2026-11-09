// flow: FLOW-F03
// The selection bar of a list counts the rows marked with its singular and its plural, in Spanish (ERPlora/ui#122):
// one marked automation reads «1 seleccionado» and two «2 seleccionados» — before, one read «1 seleccionados». The
// count is the shared table's (`@erplora/ui` DataTable); Automations is the Hub's list with boxes to mark (FLOW-F03,
// «marca sus casillas»), seen in the three sizes the fleet checks (the list at 1440 and 820, the cards at 375).
// The two automations it makes are named «E2E FlowSelected …» and go before and after.
import { expect, test } from '@playwright/test';

import { manualFlow } from './flow-helpers';
import { capture, psql, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { noHorizontalScroll } from './schedule-helpers';

const KEY = 'ui-122-selection-count';
const TAG = 'E2E FlowSelected';
const VIEWPORTS = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
];

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  psql([`delete from flow_flowrun where flow_id in (${flows})`, `delete from flow_flow where id in (${flows})`].join('; '));
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

for (const viewport of VIEWPORTS) {
  test(`FLOW-F03 says «1 seleccionado» with one automation marked and «2 seleccionados» with two, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const name = `${TAG} ${viewport.label} ${Date.now().toString(36)}`;
    const { context, page } = await signedInSpanish(browser, viewport, '/flow/automations');
    try {
      for (const n of [1, 2]) await manualFlow(context, `${name} ${n}`, [{ id: 's1', kind: 'ask', title: `${name}?` }], []);
      await shown(page).locator('[data-testid=flow-list-search] input').fill(name);
      const rows = shown(page).locator('[data-testid=flow-list-row]');
      await expect(rows).toHaveCount(2);
      const count = shown(page).locator('.data-table__selection-bar strong');
      await expect(count).toHaveCount(0);

      await rows.nth(0).locator('ion-checkbox').click();
      await expect(count).toHaveText('1 seleccionado');
      await count.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `${KEY}-one-${viewport.label}`);

      await rows.nth(1).locator('ion-checkbox').click();
      await expect(count).toHaveText('2 seleccionados');
      await capture(page, `${KEY}-two-${viewport.label}`);
      await saveSessionForTheSweep(context);
    } finally {
      await context.close();
    }
  });
}
