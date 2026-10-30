// The data of the assistant's change in «Waiting for your answer» (FIX-HUB-FLOW-PENDING-ANSWER-CARD-SHOWS-RAW-VALUES),
// end to end with its real dependencies: the Hub of this stack, its SaaS's gateway and, behind it, the e2e's provider
// (assistant-provider.ts; the SaaS seeded with it, README «El asistente»). An automation that asks first, granted
// «Book an appointment», runs; the worker asks the assistant (`workerAsks`), which wants to book one: its question waits
// in the inbox with each datum as the chat's card says it (BASE-F97 step 2) — the services by how many, the start as
// the owner's language writes it, the channel by its name, the professional left out —, never «[{}]», an id or an ISO
// moment. A no closes it and books nothing. And an «Ask someone first» step whose question inserts a yes or no and an
// instant of what the run brought asks it in words («Paid: Yes», the day and the hour as the owner's language writes
// them at the business's hour), never «true» or an ISO moment.
// flow: FLOW-F29 FLOW-F38 FLOW-F28
import { execFile, execSync } from 'node:child_process';
import { promisify } from 'node:util';

import { expect, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, HUB_DIR, psql, REPO_DIR, shown } from './helpers';
import { manualFlow, parkedEvent, RELAY, signedIn } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-FLOW-PENDING-ANSWER-CARD-SHOWS-RAW-VALUES';
const TAG = 'E2E FlowCard';
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
const BOOK = 'appointment.appointment.create';
/** A service and a professional by ids the card cannot name (their schema marks no read): it leaves them out. */
const SERVICE = '0192f0b2-2222-7000-8000-000000000002';
const MEMBER = '0192f0b2-3333-7000-8000-000000000003';

/** What a datum never shows: an id, a day or a time as ISO 8601 writes them, or a list or an object as code. */
const RAW = [/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i, /\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}/, /\[\{|\{\}|\btrue\b/];

let provider: Provider;

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, { cwd: REPO_DIR, encoding: 'utf8' }).trim();
}

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
    ].join('; '),
  );
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
}

test.beforeAll(async () => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  cleanUp();
});

test.afterAll(async () => {
  cleanUp();
  await provider?.close();
});

/** The worker's part of the step (FLOW-F38), as in fix-flow-assistant-step.spec.ts: it never blocks this process,
 *  where the provider the SaaS asks lives. */
async function workerAsks(flowId: string): Promise<void> {
  await promisify(execFile)('uv', ['run', 'python', 'manage.py', 'shell', '-c', RELAY], {
    cwd: HUB_DIR,
    env: { ...process.env, FLOW_EVENT: parkedEvent(flowId) },
  });
}

for (const viewport of VIEWPORTS) {
  test(`FLOW-F29 the assistant's change says each datum in words in «Waiting for your answer», at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const name = `${TAG} ${viewport.label} ${Date.now().toString(36)}`;
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    try {
      // The provider's marker: ask for that booking, as the model sends it.
      const booking = {
        customer: 'Ana López',
        services: [{ service_id: SERVICE }],
        staff_id: MEMBER,
        start: '2026-11-02T10:00:00+01:00',
        source: 'counter',
        notes: '',
      };
      const step = { id: 's1', kind: 'assistant', prompt: `E2E-ASK appointment__appointment__create ${JSON.stringify(booking)}`, tools: [BOOK] };
      const flowId = await manualFlow(context, name, [step], [BOOK]);
      expect((await api(context, A, 'POST', '/flow/flows/run', { id: flowId })).status).toBe(200);
      await workerAsks(flowId);
      await expect.poll(() => psql(`select count(*) from flow_question where flow_id = '${flowId}' and status = 'pending'`)).toBe('1');

      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card).toBeVisible();
      await expect(card).toContainText('The assistant wants to change something in «Appointments»');
      await expect(card.locator('[data-testid^=flow-question-action-]')).toHaveText('Book an appointment');
      // Before: «Services: [{}]» in its details, as the model sent it.
      const text = await card.innerText();
      for (const raw of RAW) expect(text, `${raw} on the card`).not.toMatch(raw);
      const data = card.locator('[data-testid^=flow-question-data-] li');
      await expect(data).toHaveText([
        'Customer: Ana López',
        'Services: 1 item',
        /^Starts at: Nov 2, 2026, \d{1,2}:00\s(AM|PM)$/,
        'Booked through: Front desk',
      ]);

      await card.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);
      // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });

      // A no books nothing and the card leaves.
      await card.locator('[data-testid^=flow-question-reject-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Answered no.' }).last()).toBeVisible();
      await expect(card).toHaveCount(0);
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('cancelled');
      expect(psql(`select count(*) from flow_flowrun where flow_id = '${flowId}' and log::text like '%assistant_used%'`)).toBe('0');
    } finally {
      await context.close();
    }
  });
}

for (const viewport of VIEWPORTS) {
  test(`FLOW-F28 a question says the data it inserts in words in «Waiting for your answer», at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const name = `${TAG} ask ${viewport.label} ${Date.now().toString(36)}`;
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    try {
      const step = {
        id: 's1',
        kind: 'ask',
        title: 'Refund {{input.name}}? Paid: {{input.paid}}',
        details: 'Bought {{input.at}} · {{input.hour}} the first time',
      };
      const flowId = await manualFlow(context, name, [step], []);
      const input = { name: 'Ana', paid: true, at: '2026-11-02T10:00:00+01:00', hour: '21:30:00' };
      expect((await api(context, A, 'POST', '/flow/flows/run', { id: flowId, input })).status).toBe(200);

      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card).toBeVisible();
      await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText('Refund Ana? Paid: Yes');
      // Before: «Paid: true» and «Bought 2026-11-02T10:00:00+01:00 · 21:30:00».
      const text = await card.innerText();
      for (const raw of RAW) expect(text, `${raw} on the card`).not.toMatch(raw);
      await expect(card).toContainText(/Bought Nov 2, 2026, \d{1,2}:00\s(AM|PM) · 9:30\sPM the first time/);

      await card.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-ask-${viewport.label}`);

      await card.locator('[data-testid^=flow-question-reject-]').click();
      await expect(card).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
}
