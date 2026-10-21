// flow: FLOW-F21
// «When something happens in the business, the automation starts» (apps/flow/WORKBOOK.md FLOW-F21), end to end
// in each of the three sizes, as the owner and against the real apps: an automation on «A customer card is
// created» that leaves a task, on and allowed; a real customer created through the Customers API; the worker's
// outbox relay pass (`base.relay.run`, as every tick runs it: the e2e stack runs no worker); its History says the
// run finished well, step by step, and the task is in Tasks. A second pass starts nothing more. One screenshot
// per size (`APP-FLOW-3-FLOW-F21-<width>`). What it creates is tagged `E2E FlowR` and goes.
import { spawnSync } from 'node:child_process';

import { expect, test } from '@playwright/test';

import { signedIn } from './flow-helpers';
import { A, api, HUB_DIR, psql, shot, shown } from './helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';

const TAG = 'E2E FlowR';

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from task_task where title like '${TAG}%'`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/** The outbox relay as the worker runs it on every tick, pass after pass until one finds nothing to do (what
 *  other specs recorded is delivered too). */
function relayPass(): void {
  const code = [
    'from django.utils import timezone',
    'from base import relay',
    'for _ in range(200):',
    '    done = relay.run(timezone.now())',
    '    if not (done.taken or done.delivered): break',
  ].join('\n');
  const out = spawnSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', code], { cwd: HUB_DIR, env: process.env, encoding: 'utf8' });
  expect(out.status, `relay pass: ${out.stderr}`).toBe(0);
}

for (const viewport of VIEWPORTS) {
  test(`an automation on «something happens» starts on its own at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const stamp = `${viewport.label}-${Date.now().toString(36)}`;
    const name = `${TAG} ${stamp}`;
    const title = `${TAG} welcome ${stamp}`;
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    try {
      relayPass(); // what other specs left in the outbox, before this one counts its runs
      const created = await api<{ id: string }>(context, A, 'POST', '/flow/flows', {
        name,
        trigger: { kind: 'event', event: 'customer.customer.created' },
        steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title } }],
      });
      expect(created.status, JSON.stringify(created.data)).toBe(201);
      const flowId = created.data.id;
      expect((await api(context, A, 'POST', '/flow/flows/grant', { id: flowId, operations: ['task.task.create'] })).status).toBe(200);
      expect((await api(context, A, 'POST', '/flow/flows/set_enabled', { id: flowId, enabled: true })).status).toBe(200);

      const customer = await api<{ id: string }>(context, A, 'POST', '/customer/customers', { name: `${TAG} ${stamp}` });
      expect(customer.status, JSON.stringify(customer.data)).toBe(201);
      expect(psql(`select count(*) from flow_flowrun where flow_id = '${flowId}'`)).toBe('0');

      relayPass();

      await page.goto(`${A}/flow/automations/${flowId}`);
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      const ran = shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: 'Finished well' }).first();
      await expect(ran).toBeVisible();
      await ran.locator('[data-testid^=flow-run-toggle-]').click();
      await expect(ran.locator('[data-testid^=flow-run-steps-]')).toContainText('Did: Create a task');
      expect(psql(`select trigger_kind || ' ' || event_name from flow_flowrun where flow_id = '${flowId}'`)).toBe('event customer.customer.created');
      expect(psql(`select count(*) from task_task where title = '${title}'`)).toBe('1');
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await page.screenshot({ path: shot(`APP-FLOW-3-FLOW-F21-${viewport.label}`) });

      relayPass();
      expect(psql(`select count(*) from flow_flowrun where flow_id = '${flowId}'`)).toBe('1');
    } finally {
      await context.close();
    }
  });
}
