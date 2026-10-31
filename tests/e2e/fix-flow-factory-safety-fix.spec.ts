// A factory recipe's safety fix reaches the automation already built from it, without waiting for the owner
// (apps/flow/WORKBOOK.md FLOW-F36, with FLOW-F37/F38 and FLOW-F29), end to end with its real dependencies: the Hub of
// this stack, its SaaS's gateway (`/internal/assistant/chat`, `/internal/whatsapp/send`) and, behind it, the e2e's
// provider (assistant-provider.ts, started by this spec; the SaaS seeded with it, README «El asistente») and Meta's
// Graph (README «WhatsApp»).
// The owner turned «Book a table» on before its app fixed whose card its assistant acts for (hub#447) and before it left
// out the inbox's old messages: its «Ask the assistant» step (`s10`) has no fixed data, its «Only when…» has no
// `source` and it is «New version». Nothing waits for the owner: Automatizaciones shows no notice for it, its editor
// shows the condition and the fixed data its app puts on it as set by its app (never to take off from there, and saved
// untouched they are written), an old message of the inbox starts nothing, and when a
// guest asks to cancel another guest's table the assistant is not offered on whose behalf, the card of «Waiting for
// your answer» says the writer's, and after the «Approve» the other guest's reservation is as it was.
// flow: FLOW-F36 FLOW-F38 FLOW-F29
import { execFile, execSync } from 'node:child_process';
import { promisify } from 'node:util';

import { type BrowserContext, expect, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, HUB_DIR, psql, REPO_DIR, shown } from './helpers';
import { confirmDialog, parkedEvent, RELAY, signedIn } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { STACK } from './stack';
import { cleanUp as inboxCleanUp, e2ePhone, pushChannel, receive } from './whatsapp-helpers';

const KEY = 'FIX-HUB-FLOW-FACTORY-SAFETY-FIX-WAITS-FOR-THE-OWNERS-UPDATE';
const ANSWER = 'whatsapp_inbox/reservation_from_whatsapp';
const CANCEL = 'reservation.reservation.cancel';
/** How the book's slot and the open day this spec makes are known again (slots have no name). */
const SENTINEL = 78;
const OPEN_REASON = 'E2E factory safety fix open';
/** What the editor says of a condition or a fixed datum its app puts on it, which never comes off from there. */
const SET_BY = 'Set by WhatsApp inbox: you can change it, not take it off.';
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);

let provider: Provider;

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, { cwd: REPO_DIR, encoding: 'utf8' }).trim();
}

/** The business's day `days` from today (Madrid in phase 1) and its weekday, Monday 0. */
function madridDay(days: number): { date: string; weekday: number } {
  const date = new Date(Date.now() + days * 86_400_000).toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' });
  return { date, weekday: (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7 };
}

const DAY = madridDay(4);

/** The inbox's answers and notices (with their runs and questions), this spec's reservations and cards, its slot and
 *  open day, the conversations and channel of the inbox's specs, and the month's messages of the business `a`. */
function cleanUp(): void {
  const flows = "select id from flow_flow where recipe like 'whatsapp_inbox/%'";
  const reservations = "select id from reservation_reservation where guest_phone like '+3469900%'";
  const cards = "select id from customer_customer where source = 'whatsapp' and phone like '%69900%'";
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from table_hold where source_ref in (select id::text from reservation_reservation where guest_phone like '+3469900%')`,
      `delete from reservation_reservation where id in (${reservations})`,
      `delete from reservation_timeslot where max_reservations = ${SENTINEL}`,
      `delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason = '${OPEN_REASON}')`,
      `delete from schedule_override where reason = '${OPEN_REASON}'`,
    ].join('; '),
  );
  inboxCleanUp();
  psql(
    [
      ...['customer_activity', 'customer_consent', 'customer_customer_groups', 'customer_customer_tags', 'customer_customfieldvalue', 'customer_orderlink', 'customer_purchase'].map(
        (table) => `delete from ${table} where customer_id in (${cards})`,
      ),
      `delete from customer_customer where id in (${cards})`,
    ].join('; '),
  );
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
}

/** One tick of the worker's relay (this stack runs no worker): the outbox event `id` handed to Automations' reaction.
 *  It does not block this process: the provider the SaaS asks lives here, and must answer. */
async function relay(id: string): Promise<void> {
  await promisify(execFile)('uv', ['run', 'python', 'manage.py', 'shell', '-c', RELAY], {
    cwd: HUB_DIR,
    env: { ...process.env, FLOW_EVENT: id },
  });
}

async function statusOf(context: BrowserContext, id: string): Promise<string> {
  const read = await api<{ status: string }>(context, A, 'GET', `/reservation/reservations/detail?id=${id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  return read.data.status;
}

const chats = (): number => provider.seen.filter((seen) => seen.path === '/v1/chat/completions').length;

type Tool = { function: { name: string; parameters?: { properties?: Record<string, unknown> } } };

/** The inputs the assistant was offered for `name` in a turn's request. */
function inputsOf(body: unknown, name: string): string[] {
  const tool = ((body as { tools?: Tool[] }).tools ?? []).find((offered) => offered.function.name === name);
  expect(tool, `${name} offered`).toBeTruthy();
  return Object.keys(tool!.function.parameters?.properties ?? {});
}

/** The book open on DAY, all day, whatever the hours of the database (as reservation-book.spec.ts does). */
async function openTheBook(context: BrowserContext): Promise<void> {
  const slot = await api(context, A, 'POST', '/reservation/time_slots', { day_of_week: DAY.weekday, start_time: '00:00', end_time: '23:59', max_reservations: SENTINEL });
  expect(slot.status, JSON.stringify(slot.data)).toBe(201);
  const open = await api(context, A, 'POST', '/schedule/overrides', {
    start_date: DAY.date,
    end_date: DAY.date,
    reason: OPEN_REASON,
    is_closed: false,
    intervals: [{ open_time: '00:00', close_time: '00:00' }],
  });
  expect(open.status, JSON.stringify(open.data)).toBe(201);
}

/** «Book a table» as an owner who turned it on before hub#447 and before its app left out the inbox's old messages has
 *  it: its assistant's step fixes no data, its «Only when…» says nothing of `source`, and it was built from another
 *  version («New version»). */
function asTurnedOnBeforeTheFix(): string {
  const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);
  expect(flowId, '«Book a table» turned on').not.toBe('');
  psql(
    `update flow_flow set steps = (select jsonb_agg(case when step->>'id' = 's10' then step - 'pinned' else step end order by at) ` +
      `from jsonb_array_elements(steps) with ordinality as listed(step, at)), trigger_filter = trigger_filter - 'input.source', ` +
      `recipe_digest = repeat('0', 64) where id = '${flowId}'`,
  );
  expect(psql(`select count(*) from flow_flow, jsonb_array_elements(steps) as step where id = '${flowId}' and step ? 'pinned'`)).toBe('0');
  expect(psql(`select trigger_filter ? 'input.source' from flow_flow where id = '${flowId}'`)).toBe('f');
  return flowId;
}

test.beforeAll(async () => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
});

test.beforeEach(() => {
  cleanUp();
  pushChannel({ status: 'connected' });
});

test.afterAll(async () => {
  cleanUp();
  await provider?.close();
});

for (const viewport of VIEWPORTS) {
  test(`FLOW-F36 a table answer turned on before its app's safety fixes never answers an old message nor cancels another guest's table, with nothing for the owner to press, at ${viewport.label}`, async ({ browser }) => {
    // The editor's visit on top of the whole WhatsApp round of fix-whatsapp-inbox-table-cancel.spec.ts: 180 s ran out
    // on a loaded machine (load average 32) in the last relay, at 1440.
    test.setTimeout(300_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      await openTheBook(context);
      const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables]');
      await card.locator('[data-testid=whatsapp-inbox-autoreply-tables-on]').click();
      await confirmDialog(page, 'Book a table');
      await expect(card).toContainText('On');
      const flowId = asTurnedOnBeforeTheFix();

      // Automatizaciones has nothing for the owner to update: its card says «New version», as any other change of
      // its app, and no notice over «Your automations» asks for anything.
      await page.goto('/flow/automations');
      await expect(shown(page).locator(`[data-testid="flow-recipe-${ANSWER}"]`)).toContainText('New version');
      const list = shown(page).locator('[data-testid=flow-list-section]');
      await expect(list.locator(`[data-testid="flow-list-toggle-${flowId}"]`)).toBeVisible();
      await expect(shown(page).locator('[data-testid=flow-repairs]')).toHaveCount(0);
      await expect(shown(page).locator(`[data-testid="flow-repair-${ANSWER}"]`)).toHaveCount(0);
      await expect(shown(page).getByText('starts in more cases than it should')).toHaveCount(0);
      await list.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-list-${viewport.label}`);

      // Its editor shows, under «Fixed data» of the assistant's step, the card its app fixes on a cancellation.
      await page.goto(`/flow/automations/${flowId}`);
      const editor = shown(page);
      // Its «Only when…»: the inbound messages, and only the live ones, as its app has it today. Both are its app's:
      // set by it, never to remove from here (FLOW-F36).
      await editor.locator('[data-testid=flow-trigger-open]').click();
      await expect(editor.locator('[data-testid^=flow-trigger-filter-row-]')).toHaveCount(2);
      const locked = editor.locator('[data-testid^=flow-trigger-filter-locked-]');
      await expect(locked).toHaveText([SET_BY, SET_BY]);
      await expect(editor.locator('[data-testid^=flow-trigger-filter-remove-]')).toHaveCount(0);
      await locked.last().scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-editor-filter-${viewport.label}`);
      await editor.locator('[data-testid=flow-step-open-s10]').click();
      const pin = editor.locator(`[data-testid="flow-assistant-pin-s10-${CANCEL}-on_behalf_of"]`);
      await expect(pin).toContainText('Cancel a reservation › On behalf of the customer');
      await expect(editor.locator('[data-testid=flow-assistant-nopins-s10]')).toHaveCount(0);
      // Its datum is its app's too: no ×, only its value would change.
      const setBy = editor.locator(`[data-testid="flow-assistant-setbyapp-s10-${CANCEL}-on_behalf_of"]`);
      await expect(setBy).toHaveText(SET_BY);
      await expect(editor.locator(`[data-testid="flow-assistant-unpin-s10-${CANCEL}-on_behalf_of"]`)).toHaveCount(0);
      await setBy.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-editor-${viewport.label}`);

      // Marta's reservation at 21:00 for 2, on her card; Lucía, from another number and with no card yet, writes.
      const lucia = e2ePhone();
      let marta = e2ePhone();
      while (marta === lucia) marta = e2ePhone();

      // An old message of Lucía's chat that the inbox brings in (`source` «history») starts nothing.
      const old = receive(lucia, 'Do you have a table on Friday?', 'E2E Lucía', { source: 'history' });
      const oldReceived = psql(
        `select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${old.id}'`,
      );
      expect(oldReceived, 'whatsapp_inbox.message.received of the old message in the outbox').not.toBe('');
      await relay(oldReceived);
      expect(psql(`select count(*) from flow_flowrun where flow_id = '${flowId}'`)).toBe('0');
      const theirs = await api<{ id: string }>(context, A, 'POST', '/customer/customers', { name: 'E2E Marta', phone: marta, source: 'whatsapp' });
      expect(theirs.status, JSON.stringify(theirs.data)).toBe(201);
      const made = await api<{ id: string }>(context, A, 'POST', '/reservation/reservations', {
        customer_id: theirs.data.id,
        guest_name: 'E2E Marta',
        guest_phone: marta,
        date: DAY.date,
        time: '21:00',
        party_size: 2,
      });
      expect(made.status, JSON.stringify(made.data)).toBe(201);
      const reservation = made.data.id;
      const before = await statusOf(context, reservation);

      // The assistant names Marta's reservation and, as a model fooled by the message might, says it is on Marta's
      // behalf: what the old step let it choose.
      const asked = { id: reservation, on_behalf_of: theirs.data.id };
      const message = receive(lucia, `Cancel E2E Marta's table\nE2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`, 'E2E Lucía');
      const received = psql(
        `select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${message.id}'`,
      );
      expect(received, 'whatsapp_inbox.message.received of the message in the outbox').not.toBe('');
      await relay(received);
      const first = chats();
      await relay(parkedEvent(flowId));

      // Not even offered: on whose behalf is fixed by the step its app fixed after it was turned on.
      const turns = provider.seen.filter((seen) => seen.path === '/v1/chat/completions').slice(first);
      expect(turns).toHaveLength(1);
      expect(inputsOf(turns[0].body, 'reservation__reservation__cancel')).not.toContain('on_behalf_of');
      expect(inputsOf(turns[0].body, 'reservation__reservation__update')).not.toContain('on_behalf_of');
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('asking');

      // The card says on whose behalf the yes goes: Lucía's, never Marta's.
      await page.goto('/flow/automations');
      const question = shown(page)
        .locator('[data-testid=flow-inbox] article')
        .filter({ hasText: 'The assistant wants to change something in «Reservations»' });
      await expect(question).toBeVisible();
      await expect(question).toContainText('On behalf of the customer: E2E Lucía');
      await expect(question).not.toContainText('On behalf of the customer: E2E Marta');
      await expect(shown(page).locator(`[data-testid="flow-repair-${ANSWER}"]`)).toHaveCount(0);
      await question.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);

      // «Approve»: Reservas refuses it on Lucía's behalf and Marta's reservation is as it was.
      await question.locator('[data-testid^=flow-question-yes-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
      await expect(question).toHaveCount(0);
      expect(await statusOf(context, reservation)).toBe(before);
      await relay(parkedEvent(flowId));
      expect(JSON.stringify(provider.seen.at(-1)?.body)).toContain('reservation.customer_mismatch');
      await expect.poll(() => psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('succeeded');
      expect(await statusOf(context, reservation)).toBe(before);
      // Nothing was written behind the owner's back: the automation is still as they had it, and still on.
      expect(psql(`select count(*) from flow_flow, jsonb_array_elements(steps) as step where id = '${flowId}' and step ? 'pinned'`)).toBe('0');
      expect(psql(`select trigger_filter ? 'input.source' from flow_flow where id = '${flowId}'`)).toBe('f');
      expect(psql(`select enabled from flow_flow where id = '${flowId}'`)).toBe('t');

      // Saved from its editor without touching anything, it is taken, and what its app fixes is written down.
      await page.goto(`/flow/automations/${flowId}`);
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      expect(psql(`select trigger_filter->'input.source'->>'eq' from flow_flow where id = '${flowId}'`)).toBe('live');
      expect(psql(`select count(*) from flow_flow, jsonb_array_elements(steps) as step where id = '${flowId}' and step->'pinned' ? '${CANCEL}'`)).toBe('1');
    } finally {
      await context.close();
    }
  });
}
