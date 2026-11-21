// flow: FLOW-F02
// The list of automations opens sorted by «Últimas tocadas primero», and the order does what its name says: the
// automation touched last is the first row, also after touching an older one. Seen in Spanish in the three sizes
// the fleet checks (the list at 1440 and 820, the cards at 375). Its automations are named «E2E FlowTouched …».
import { expect, test } from '@playwright/test';

import { manualFlow } from './flow-helpers';
import { A, api, capture, psql, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { noHorizontalScroll } from './schedule-helpers';

const KEY = 'hub-2076-last-touched-first';
const TAG = 'E2E FlowTouched';
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
  test(`FLOW-F02 «Últimas tocadas primero» puts the automation touched last at the top, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const name = `${TAG} ${viewport.label} ${Date.now().toString(36)}`;
    const step = { id: 's1', kind: 'ask', title: `${name}?` };
    const { context, page } = await signedInSpanish(browser, viewport, '/flow/automations');
    try {
      const older = await manualFlow(context, `${name} older`, [step], []);
      await manualFlow(context, `${name} newer`, [step], []);
      await expect(shown(page).locator('[data-testid=flow-list-sort]')).toContainText('Últimas tocadas primero');
      await shown(page).locator('[data-testid=flow-list-search] input').fill(name);
      const rows = shown(page).locator('[data-testid=flow-list-row]');
      await expect(rows).toHaveCount(2);
      await expect(rows.nth(0)).toContainText(`${name} newer`);

      expect((await api(context, A, 'POST', '/flow/flows/set_enabled', { id: older, enabled: false })).status).toBe(200);
      await expect(rows.nth(0)).toContainText(`${name} older`);
      await expect(rows.nth(1)).toContainText(`${name} newer`);
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `${KEY}-${viewport.label}`);
      await saveSessionForTheSweep(context);
    } finally {
      await context.close();
    }
  });
}
