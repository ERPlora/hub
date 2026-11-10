// flow: FLOW-F10 FLOW-F11 (hub#1054). An automation saved on «A task is created» that creates a task, and Tasks turned
// off afterwards: the editor keeps both, and says next to the notice and next to the step that Tasks is off in this
// business and where it comes back on, in 390, 834 and 1440 (`FLOW-APP-OFF-<width>`); with Tasks on again, neither
// says anything. Tasks is turned on again and the automation removed however the test ends.
import { expect, test } from '@playwright/test';

import { A, api, capture, psql, shown } from './helpers';
import { signedIn } from './flow-helpers';
import { noHorizontalScroll, VIEWPORTS } from './schedule-helpers';

const TAG = 'E2E FlowOff';
const OFF_EVENT = 'Its app, Tasks, is off in this business: turn it on in Apps, or choose another event.';
const OFF_ACTION = 'Its app, Tasks, is off in this business: turn it on in Apps, or choose another action.';

function cleanUp(): void {
  psql(
    [
      `delete from flow_flowrun where flow_id in (select id from flow_flow where name like '${TAG}%')`,
      `delete from flow_flow where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('FLOW-F11 flow: a saved notice and step of an app turned off say so in the editor in 390, 834 and 1440', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/flow/automations', VIEWPORTS[2]);
  try {
    const created = await api<{ id: string }>(context, A, 'POST', '/flow/flows', {
      name: `${TAG} ${Date.now().toString(36)}`,
      trigger: { kind: 'event', event: 'task.task.created' },
      steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: `${TAG} follow-up` } }],
    });
    expect(created.status, JSON.stringify(created.data)).toBe(201);
    const off = await api(context, A, 'POST', '/apps/disable', { app: 'task' });
    expect(off.status, JSON.stringify(off.data)).toBe(200);

    const event = () => shown(page).locator('[data-testid=flow-trigger-event] .error-text');
    const action = () => shown(page).locator('[data-testid=flow-step-action-s1] .error-text');
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(`${A}/flow/automations/${created.data.id}`);
      await shown(page).locator('[data-testid=flow-trigger-open]').click();
      await expect(event()).toHaveText(OFF_EVENT);
      await expect(event()).toBeInViewport();
      await shown(page).locator('[data-testid=flow-step-open-s1]').click();
      await expect(action()).toHaveText(OFF_ACTION);
      await action().scrollIntoViewIfNeeded();
      await expect(action()).toBeInViewport();
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `FLOW-APP-OFF-${viewport.label}`);
    }

    const on = await api(context, A, 'POST', '/apps/enable', { app: 'task' });
    expect(on.status, JSON.stringify(on.data)).toBe(200);
    await page.goto(`${A}/flow/automations/${created.data.id}`);
    await shown(page).locator('[data-testid=flow-trigger-open]').click();
    await shown(page).locator('[data-testid=flow-step-open-s1]').click();
    await expect(shown(page).locator('[data-testid=flow-step-action-s1]')).toBeVisible();
    await expect(event()).toBeHidden();
    await expect(action()).toBeHidden();
  } finally {
    await api(context, A, 'POST', '/apps/enable', { app: 'task' });
    await context.close();
  }
});
