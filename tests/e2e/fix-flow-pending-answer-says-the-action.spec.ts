// The action of the assistant's change in «Waiting for your answer» (FIX-HUB-FLOW-PENDING-ANSWER-CARD-DOES-NOT-SAY-THE-ACTION),
// end to end with its real dependencies: the Hub of this stack, its SaaS's gateway and, behind it, the e2e's provider
// (assistant-provider.ts; the SaaS seeded with it, README «El asistente»). A real reservation is booked; an automation
// that asks first, granted «Cancel a reservation», runs, and the worker asks the assistant (`workerAsks`), which wants
// to cancel it. Its card was titled «The assistant wants to change something in «Reservations»» and never said
// CANCEL: now, right under its title, it says «Cancel a reservation» to whoever reads it in English and «Anular una
// reserva», under «El asistente quiere cambiar algo en «Reservas»», to whoever reads it in Spanish. A no cancels nothing,
// and the History says what was refused by its action too («Cancelada: … contestó que no a «Anular una reserva».»), in
// the language of whoever reads it, never «… a «El asistente quiere cambiar algo en «Reservas»»».
// flow: FLOW-F29 FLOW-F38
import { execFile, execSync } from 'node:child_process';
import { promisify } from 'node:util';

import { type BrowserContext, expect, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, HUB_DIR, psql, REPO_DIR, shown } from './helpers';
import { manualFlow, parkedEvent, RELAY, signedIn } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { post } from './service-helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-FLOW-PENDING-ANSWER-CARD-DOES-NOT-SAY-THE-ACTION';
const TAG = 'E2E FlowAction';
const CANCEL = 'reservation.reservation.cancel';
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
/** The maximum of the slot the run opens: how `cleanUp` knows it (slots have no name). */
const SENTINEL = 75;

let provider: Provider;

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, { cwd: REPO_DIR, encoding: 'utf8' }).trim();
}

/** The business's day `days` from now (Madrid in phase 1) and its weekday, Monday 0. */
function madridDay(days: number): { date: string; weekday: number } {
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid' }).format(new Date(Date.now() + days * 86_400_000));
  return { date, weekday: (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7 };
}

const DAY = madridDay(3);

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  const cards = `select id from customer_customer where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from table_hold where source_ref in (select id::text from reservation_reservation where guest_name like '${TAG}%')`,
      `delete from reservation_reservation where guest_name like '${TAG}%'`,
      ...['customer_activity', 'customer_consent', 'customer_customer_groups', 'customer_customer_tags', 'customer_customfieldvalue', 'customer_orderlink', 'customer_purchase'].map(
        (table) => `delete from ${table} where customer_id in (${cards})`,
      ),
      `delete from customer_customer where id in (${cards})`,
      `delete from reservation_timeslot where max_reservations = ${SENTINEL}`,
      `delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason like '${TAG}%')`,
      `delete from schedule_override where reason like '${TAG}%'`,
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
  await promisify(execFile)('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', RELAY], {
    cwd: HUB_DIR,
    env: { ...process.env, FLOW_EVENT: parkedEvent(flowId) },
  });
}

/** A real reservation of `guest` at 21:00 on `DAY`, the book open that day (a slot and Schedules open 24 hours). */
async function booked(context: BrowserContext, guest: string): Promise<string> {
  if (psql(`select count(*) from reservation_timeslot where max_reservations = ${SENTINEL}`) === '0') {
    await post(context, '/reservation/time_slots', { day_of_week: DAY.weekday, start_time: '00:00', end_time: '23:59', max_reservations: SENTINEL });
    await post(context, '/schedule/overrides', {
      start_date: DAY.date,
      end_date: DAY.date,
      reason: `${TAG} open`,
      is_closed: false,
      intervals: [{ open_time: '00:00', close_time: '00:00' }],
    });
  }
  const made = await post<{ id: string; status: string }>(context, '/reservation/reservations', {
    guest_name: guest,
    guest_phone: `6${String(Date.now()).slice(-8)}`,
    date: DAY.date,
    time: '21:00',
    party_size: 2,
  });
  expect(made.status).toBe('pending');
  return made.id;
}

async function statusOf(context: BrowserContext, id: string): Promise<string> {
  const read = await api<{ status: string }>(context, A, 'GET', `/reservation/reservations/detail?id=${id}`);
  expect(read.status).toBe(200);
  return read.data.status;
}

for (const viewport of VIEWPORTS) {
  test(`FLOW-F29 the assistant's change says its action in «Waiting for your answer», in the reader's language, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const stamp = Date.now().toString(36);
    const name = `${TAG} ${viewport.label} ${stamp}`;
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    try {
      const reservation = await booked(context, `${TAG} Ana ${stamp}`);
      // The provider's marker: ask for the cancellation of that reservation, as the model sends it.
      const asked = { id: reservation, reason: 'The guest wrote to cancel' };
      const step = { id: 's1', kind: 'assistant', prompt: `E2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`, tools: [CANCEL] };
      const flowId = await manualFlow(context, name, [step], [CANCEL]);
      expect((await api(context, A, 'POST', '/flow/flows/run', { id: flowId })).status).toBe(200);
      await workerAsks(flowId);
      await expect.poll(() => psql(`select count(*) from flow_question where flow_id = '${flowId}' and status = 'pending'`)).toBe('1');

      // In English: the action, right under the title, before anything else of the change.
      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card).toBeVisible();
      await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText('The assistant wants to change something in «Reservations»');
      const action = card.locator('[data-testid^=flow-question-action-]');
      await expect(action).toHaveText('Cancel a reservation');
      const order = await card.evaluate((article) => [...article.children].map((child) => child.getAttribute('data-testid') ?? ''));
      const at = (prefix: string) => order.findIndex((testid) => testid.startsWith(prefix));
      expect(at('flow-question-action-'), order.join(', ')).toBe(at('flow-question-title-') + 1);
      await expect(card).toContainText(`${TAG} Ana ${stamp}`);
      await expect(card).not.toContainText(reservation);
      await expect(card).not.toContainText(CANCEL);

      // The same question, read in Spanish (the Hub's language cookie, as the sign-in sets it): its title and its action
      // in the reader's language, not in the automation's.
      await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
      await page.reload();
      await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText('El asistente quiere cambiar algo en «Reservas»');
      await expect(action).toHaveText('Anular una reserva');
      await card.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);

      // «No»: nothing is cancelled and the card leaves.
      await card.locator('[data-testid^=flow-question-reject-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Contestada que no.' }).last()).toBeVisible();
      await expect(card).toHaveCount(0);
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('cancelled');
      expect(await statusOf(context, reservation)).toBe('pending');

      // The History names what was refused by its action, in the reader's language.
      const runId = psql(`select id from flow_flowrun where flow_id = '${flowId}'`);
      await page.goto(`/flow/automations/${flowId}`);
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      const why = shown(page).locator(`[data-testid=flow-run-trouble-${runId}] .flow-history__why`);
      await expect(why).toHaveText(/^Cancelada: .+ contestó que no a «Anular una reserva»\.$/);
      await shown(page).locator(`[data-testid=flow-run-trouble-${runId}]`).scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-history-${viewport.label}`);
      await context.addCookies([{ name: 'django_language', value: 'en', domain: new URL(A).hostname, path: '/' }]);
      await page.reload();
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      await expect(why).toHaveText(/^Cancelled: .+ answered no to «Cancel a reservation»\.$/);
    } finally {
      await context.close();
    }
  });
}
