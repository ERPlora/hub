// Fixed data of «Ask the assistant» (FIX-HUB-FLOW-ASSISTANT-STEP-ACTS-ON-ANOTHER-CUSTOMER-WITHOUT-ON-BEHALF-OF), end to
// end with its real dependencies: the Hub of this stack, its SaaS's gateway and, behind it, the e2e's provider
// (assistant-provider.ts; the SaaS seeded with it, README «El asistente»). Lucía writes; Marta, another guest, has a
// real reservation. In the editor the step may «Cancel a reservation» and fixes its «On behalf of the customer» to
// Lucía's card; the assistant asks to cancel Marta's reservation without saying on whose behalf. The card in «Waiting
// for your answer» says it goes on Lucía's behalf, and after the owner's yes Reservations refuses it: Marta's
// reservation is still pending (before, the yes cancelled it). «Try it» says each fixed datum with the value it
// would have, and that «Change a reservation», fixed to a card this trial does not bring, would not be used.
// flow: FLOW-F37 FLOW-F38 FLOW-F29 FLOW-F13
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

const KEY = 'FIX-HUB-FLOW-ASSISTANT-STEP-ACTS-ON-ANOTHER-CUSTOMER-WITHOUT-ON-BEHALF-OF';
const TAG = 'E2E FlowPinned';
const CANCEL = 'reservation.reservation.cancel';
const UPDATE = 'reservation.reservation.update';
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
/** The maximum of the slot the run opens: how `cleanUp` knows it (slots have no name). */
const SENTINEL = 78;

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

/** A customer card, and a real reservation on it at 21:00 on `DAY`, the book open that day. */
async function guest(context: BrowserContext, name: string, book: boolean): Promise<{ card: string; reservation: string }> {
  const phone = `6${String(Date.now()).slice(-8)}`;
  const card = await post<{ id: string }>(context, '/customer/customers', { name, phone });
  if (!book) return { card: card.id, reservation: '' };
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
    customer_id: card.id,
    guest_name: name,
    guest_phone: phone,
    date: DAY.date,
    time: '21:00',
    party_size: 2,
  });
  expect(made.status).toBe('pending');
  return { card: card.id, reservation: made.id };
}

async function statusOf(context: BrowserContext, id: string): Promise<string> {
  const read = await api<{ status: string }>(context, A, 'GET', `/reservation/reservations/detail?id=${id}`);
  expect(read.status).toBe(200);
  return read.data.status;
}

for (const viewport of VIEWPORTS) {
  test(`FLOW-F38 a fixed «On behalf of the customer» keeps the assistant off another guest's reservation, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const stamp = Date.now().toString(36);
    const name = `${TAG} ${viewport.label} ${stamp}`;
    const { context, page } = await signedIn(browser, '/flow/automations/new', viewport);
    try {
      const lucia = `${TAG} Lucía ${stamp}`;
      const writer = await guest(context, lucia, false);
      const other = await guest(context, `${TAG} Marta ${stamp}`, true);
      const editor = shown(page);
      await editor.locator('[data-testid=flow-editor-name] input').fill(name);
      await editor.locator('[data-testid=flow-editor-add-assistant]').click();
      // The provider's marker: cancel Marta's reservation, never saying on whose behalf.
      await editor.locator('[data-testid=flow-assistant-prompt-s1-text-0]').fill(`E2E-ASK reservation__reservation__cancel ${JSON.stringify({ id: other.reservation })}`);
      await expect(editor.locator('[data-testid=flow-assistant-pinned-s1]')).toHaveCount(0);
      await pick(page, 'flow-assistant-addtool-s1', 'Cancel a reservation', 'Cancel a reservation');
      // FLOW-F37: nothing fixed yet; then «On behalf of the customer», fixed to Lucía's card.
      await expect(editor.locator('[data-testid=flow-assistant-nopins-s1]')).toHaveText('None: the assistant fills in every datum itself.');
      await pick(page, 'flow-assistant-addpin-s1', 'behalf', 'On behalf of the customer');
      const pin = `flow-assistant-pin-s1-${CANCEL}-on_behalf_of`;
      await expect(editor.locator(`[data-testid="${pin}"]`)).toContainText('Cancel a reservation › On behalf of the customer');
      await editor.locator(`[data-testid="${pin}-text-0"]`).fill(writer.card);
      await expect(editor.locator('[data-testid=flow-assistant-nopins-s1]')).toHaveCount(0);
      await expect(editor.locator('[data-testid=flow-assistant-pinnedhint-s1]')).toHaveText(
        'The assistant never sees them nor can change them: they are filled in when it is asked, and a tool whose fixed datum is empty is not used.',
      );
      await editor.locator('[data-testid=flow-assistant-pinnedhint-s1]').scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);

      // FLOW-F13: «Try it» says each fixed datum with the value it would have, as the card of the change names it (the
      // guest by her name, never her card's id), and which tool would not be used because one would be empty —
      // «Change a reservation» on behalf of a card the run is never given here.
      await pick(page, 'flow-assistant-addtool-s1', 'Change a reservation', 'Change a reservation');
      await pick(page, 'flow-assistant-addpin-s1', 'behalf', 'On behalf of the customer');
      await editor.locator(`[data-testid="flow-assistant-pin-s1-${UPDATE}-on_behalf_of-text-0"]`).fill('{{input.customer}}');
      await editor.locator('[data-testid=flow-editor-tab-test]').click();
      const tried = editor.locator('[data-testid=flow-test-step-s1]');
      await expect(tried).toContainText('Would ask the assistant');
      const fixed = tried.locator(`[data-testid="flow-test-pinned-s1-${CANCEL}-on_behalf_of"]`);
      await expect(fixed.locator('span')).toHaveText(['Cancel a reservation › On behalf of the customer', lucia]);
      await expect(tried).not.toContainText(writer.card);
      await expect(tried.locator(`[data-testid="flow-test-pinnedempty-s1-${UPDATE}"]`)).toHaveText(
        '«Change a reservation» would not be used: «On behalf of the customer», fixed by this step, would be empty in this run.',
      );
      await tried.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-try-${viewport.label}`);

      await editor.locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      const flowId = idFromUrl(page);
      const saved = JSON.parse(psql(`select steps::text from flow_flow where id = '${flowId}'`))[0].pinned;
      expect(saved[CANCEL]).toEqual({ on_behalf_of: writer.card });
      expect(Object.keys(saved[UPDATE])).toEqual(['on_behalf_of']);

      await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Permissions updated.' }).last()).toBeVisible();
      await shown(page).locator('[data-testid=flow-editor-enabled]').click();
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');

      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?');
      await expect(page.locator('ion-toast').filter({ hasText: 'the assistant is on it' }).last()).toBeVisible();
      await workerAsks(flowId);
      await expect.poll(() => psql(`select count(*) from flow_question where flow_id = '${flowId}' and status = 'pending'`)).toBe('1');

      // FLOW-F29: the card says on whose behalf it would go, by her name, although the assistant never said it.
      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card).toBeVisible();
      await expect(card.locator('[data-testid^=flow-question-data-] li').filter({ hasText: 'On behalf of the customer' })).toHaveText(
        `On behalf of the customer: ${lucia}`,
      );
      await card.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-card-${viewport.label}`);
      // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });

      // The owner's yes: Reservations refuses another guest's reservation on Lucía's behalf; Marta's stays.
      await card.locator('[data-testid^=flow-question-yes-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
      await expect(card).toHaveCount(0);
      expect(await statusOf(context, other.reservation)).toBe('pending');
      await workerAsks(flowId);
      await expect.poll(() => psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('succeeded');
      expect(psql(`select log::text from flow_flowrun where flow_id = '${flowId}'`)).toContain('"ok": false');
      expect(await statusOf(context, other.reservation)).toBe('pending');
    } finally {
      await context.close();
    }
  });
}
