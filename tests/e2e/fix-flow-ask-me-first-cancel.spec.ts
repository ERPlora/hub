// Cancelling a reservation with «Ask the assistant» and «Ask me first» (FIX-HUB-FLOW-ASK-ME-FIRST-CANNOT-GRANT-A-CANCELLATION),
// end to end with its real dependencies: the Hub of this stack, its SaaS's gateway and, behind it, the e2e's provider
// (assistant-provider.ts; the SaaS seeded with it, README «El asistente»). A real reservation is booked; in the editor
// the step is given «Cancel a reservation», which only «Ask me first» offers, and the card says who may say yes to it;
// saved, granted and run, the worker asks the assistant (`workerAsks`), which wants to cancel it: nothing is cancelled
// until the owner says yes in «Waiting for your answer», and then the reservation is cancelled for real.
// flow: FLOW-F28 FLOW-F12 FLOW-F37 FLOW-F38
import { execFile, execSync } from 'node:child_process';
import { promisify } from 'node:util';

import { type BrowserContext, expect, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, HUB_DIR, psql, REPO_DIR, shown } from './helpers';
import { confirmDialog, idFromUrl, parkedEvent, RELAY, signedIn } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { post } from './service-helpers';
import { STACK } from './stack';
import { pick } from './task-helpers';

const KEY = 'FIX-HUB-FLOW-ASK-ME-FIRST-CANNOT-GRANT-A-CANCELLATION';
const TAG = 'E2E FlowCancel';
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
/** The maximum of the slot the run opens: how `cleanUp` knows it (slots have no name). */
const SENTINEL = 79;

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
  await promisify(execFile)('uv', ['run', 'python', 'manage.py', 'shell', '-c', RELAY], {
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
  test(`FLOW-F28 a reservation is cancelled only after the owner's yes, with «Ask me first», at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const stamp = Date.now().toString(36);
    const name = `${TAG} ${viewport.label} ${stamp}`;
    const { context, page } = await signedIn(browser, '/flow/automations/new', viewport);
    try {
      const reservation = await booked(context, `${TAG} Ana ${stamp}`);
      const editor = shown(page);
      await editor.locator('[data-testid=flow-editor-name] input').fill(name);
      await editor.locator('[data-testid=flow-editor-add-assistant]').click();
      // The provider's marker: ask for the cancellation of that reservation, then say how it went.
      const asked = { id: reservation, reason: 'The guest wrote to cancel' };
      await editor.locator('[data-testid=flow-assistant-prompt-s1-text-0]').fill(`E2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`);
      await pick(page, 'flow-assistant-addtool-s1', 'Cancel a reservation', 'Cancel a reservation');
      await expect(editor.locator('[data-testid="flow-assistant-tool-s1-reservation.reservation.cancel"]')).toHaveText('Cancel a reservation');
      await expect(editor.locator('[data-testid=flow-assistant-askfirst-s1]')).toHaveText(
        'Only after a yes from someone who may do it themselves: «Cancel a reservation».',
      );
      await editor.locator('[data-testid=flow-assistant-askfirst-s1]').scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);
      await editor.locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      const flowId = idFromUrl(page);

      // FLOW-F12: what it needs is granted, the cancellation included, only because its step asks first.
      await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Permissions updated.' }).last()).toBeVisible();
      await shown(page).locator('[data-testid=flow-editor-enabled]').click();
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      expect(psql(`select grants::text from flow_flow where id = '${flowId}'`)).toBe('["reservation.reservation.cancel"]');

      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?');
      await expect(page.locator('ion-toast').filter({ hasText: 'the assistant is on it' }).last()).toBeVisible();
      await workerAsks(flowId);
      // FLOW-F38: the assistant wants to cancel it; nothing is cancelled before a yes.
      await expect.poll(() => psql(`select count(*) from flow_question where flow_id = '${flowId}' and status = 'pending'`)).toBe('1');
      expect(await statusOf(context, reservation)).toBe('pending');

      // FLOW-F29: the owner says yes in «Waiting for your answer»: the reservation is cancelled for real.
      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card).toBeVisible();
      await expect(card).toContainText('The assistant wants to change something in «Reservations»');
      await card.locator('[data-testid^=flow-question-yes-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
      await expect(card).toHaveCount(0);
      expect(await statusOf(context, reservation)).toBe('cancelled');
      // The step goes back to the assistant with what happened, and the run finishes.
      await workerAsks(flowId);
      await expect.poll(() => psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('succeeded');
    } finally {
      await context.close();
    }
  });
}
