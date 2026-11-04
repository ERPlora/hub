// The business's clock on the screens (hub#687): a business in the Canaries reads the hour an automation inserts in a
// question, and until when it waits for an answer, on its own clock (FLOW-F29), whatever the deployment's is (Madrid);
// the agenda says it is on that clock and Schedules names it (SCHEDULE-F09). Its zone is the registry's, as the SaaS
// pushes it: the spec sets it in `base_hub` and puts it back.
// flow: FLOW-F29 SCHEDULE-F09
import { expect, test } from '@playwright/test';

import { manualFlow, signedIn } from './flow-helpers';
import { A, api, psql, shown } from './helpers';
import { VIEWPORTS } from './schedule-helpers';

const ZONE = 'Atlantic/Canary';
const TAG = 'E2E BusinessZone';
let saved = '';

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
    ].join('; '),
  );
}

test.beforeAll(() => {
  cleanUp();
  saved = psql("select timezone from base_hub where slug = 'a'");
  psql(`update base_hub set timezone = '${ZONE}' where slug = 'a'`);
});

test.afterAll(() => {
  // A sweep of the screens looks at what the run leaves: its stack's database is dropped after it.
  if (process.env.E2E_SAVE_STORAGE_STATE) return;
  psql(`update base_hub set timezone = '${saved}' where slug = 'a'`);
  cleanUp();
});

for (const viewport of VIEWPORTS) {
  test(`a question, the agenda and Schedules are on the business's clock, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const name = `${TAG} ${viewport.label} ${Date.now().toString(36)}`;
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    try {
      const step = { id: 's1', kind: 'ask', title: 'Visit {{input.at}}?' };
      const flowId = await manualFlow(context, name, [step], []);
      // 10:00 in Madrid, 9:00 in the Canaries.
      const input = { at: '2026-11-02T10:00:00+01:00' };
      expect((await api(context, A, 'POST', '/flow/flows/run', { id: flowId, input })).status).toBe(200);

      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText('Visit Nov 2, 2026, 9:00 AM?');
      const expires = psql(`select to_char(expires_at at time zone '${ZONE}', 'HH12:MI') from flow_question q join flow_flow f on f.id = q.flow_id where f.name = '${name}'`);
      await expect(card.locator('[data-testid^=flow-question-silence-]')).toContainText(expires.replace(/^0/, ''));

      await page.goto('/appointment/agenda');
      await expect(shown(page).getByText(`The agenda always shows the business clock: ${ZONE}`)).toBeVisible();

      await page.goto('/schedule/settings');
      await expect(shown(page).locator('[data-testid=schedule-settings-timezone]')).toContainText(ZONE);
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    } finally {
      await context.close();
    }
  });
}
