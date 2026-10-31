// A guest cancels their table by WhatsApp (apps/whatsapp_inbox/WORKBOOK.md WHATSAPP_INBOX-F25), answered by «Book a
// table»'s assistant «Ask me first», end to end with its real dependencies: the Hub of this stack, its SaaS's gateway
// (`/internal/assistant/chat`, `/internal/whatsapp/send`) and, behind it, the e2e's provider (assistant-provider.ts,
// started by this spec; the SaaS seeded with it, README «El asistente») and Meta's Graph (README «WhatsApp»).
// The owner turns «Book a table» on; a guest with a card and a reservation writes to cancel it; the worker's relay
// hands the message to Automations, whose run reads their latest reservation by their number and asks the assistant,
// which wants to cancel exactly that one (FLOW-F28: only because its step asks first). On whose behalf is never the
// assistant's to say: the step fixes it to the card of the number that writes (FLOW-F38), so the assistant is not even
// offered it and Reservas refuses another guest's reservation after the «Approve» all the same. Nothing is cancelled
// until the owner's «Approve» in «Waiting for your answer», on a card that names the reservation by its guest, day and
// time, never by its id; then Reservas cancels it and the guest gets the assistant's answer.
// flow: WHATSAPP_INBOX-F25 (sigue hecho) y F22 FLOW-F28 FLOW-F38
import { execFile, execSync } from 'node:child_process';
import { promisify } from 'node:util';

import { type BrowserContext, expect, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, HUB_DIR, psql, REPO_DIR, shown } from './helpers';
import { confirmDialog, parkedEvent, RELAY, signedIn } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { STACK } from './stack';
import { cleanUp as inboxCleanUp, e2ePhone, pushChannel, receive } from './whatsapp-helpers';

const KEY = 'FIX-HUB-WHATSAPP-INBOX-AUTO-REPLY-CANNOT-CANCEL-A-RESERVATION';
const OTHER_KEY = 'FIX-HUB-WHATSAPP-INBOX-TABLE-REPLY-CAN-CANCEL-ANOTHER-CUSTOMERS-RESERVATION';
const ANSWER = 'whatsapp_inbox/reservation_from_whatsapp';
const THANKS = 'Thanks for writing! Let me check the reservations book and I will come straight back to you.';
/** How the book's slot and the open day this spec makes are known again (slots have no name). */
const SENTINEL = 77;
const OPEN_REASON = 'E2E WhatsApp table cancel open';
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

const DAY = madridDay(3);

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

/** One tick of the worker's relay (in `a`'s database; the stack's worker relays too): the outbox event `id` handed to Automations' reaction.
 *  It does not block this process: the provider the SaaS asks lives here, and must answer. */
async function relay(id: string): Promise<void> {
  await promisify(execFile)('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', RELAY], {
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
  test(`WHATSAPP_INBOX-F25 a guest cancels their table by WhatsApp, and it is cancelled after the owner's yes at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      await openTheBook(context);

      // The owner turns «Book a table» on (F15).
      const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables]');
      await card.locator('[data-testid=whatsapp-inbox-autoreply-tables-on]').click();
      await confirmDialog(page, 'Book a table');
      await expect(card).toContainText('On');

      // A guest with a card and a reservation at 21:00 for 4.
      const phone = e2ePhone();
      const guest = await api<{ id: string }>(context, A, 'POST', '/customer/customers', { name: 'E2E Lucía', phone, source: 'whatsapp' });
      expect(guest.status, JSON.stringify(guest.data)).toBe(201);
      const made = await api<{ id: string; status: string }>(context, A, 'POST', '/reservation/reservations', {
        customer_id: guest.data.id,
        guest_name: 'E2E Lucía',
        guest_phone: phone,
        date: DAY.date,
        time: '21:00',
        party_size: 4,
      });
      expect(made.status, JSON.stringify(made.data)).toBe(201);
      const reservation = made.data.id;
      const before = await statusOf(context, reservation);
      expect(['pending', 'confirmed']).toContain(before);

      // They write to cancel it; the provider's marker stands for the assistant's choice: cancel that reservation, as
      // the answer's instructions tell it, saying nothing of on whose behalf (the step fixes it).
      const asked = { id: reservation, reason: 'The guest asked by WhatsApp' };
      const message = receive(phone, `I can't make it, please cancel my table\nE2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`, 'E2E Lucía');
      const received = psql(
        `select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${message.id}'`,
      );
      expect(received, 'whatsapp_inbox.message.received of the message in the outbox').not.toBe('');
      await relay(received);
      const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);
      const first = chats();
      await relay(parkedEvent(flowId));

      // The assistant was told their latest reservation, read by their number, and offered the cancellation; it
      // wanted it, and nothing is cancelled yet.
      const turns = provider.seen.filter((seen) => seen.path === '/v1/chat/completions').slice(first);
      expect(turns).toHaveLength(1);
      expect(JSON.stringify(turns[0].body)).toContain(`id ${reservation})`);
      const tools = ((turns[0].body as { tools?: Tool[] }).tools ?? []).map((tool) => tool.function.name);
      expect(tools).toContain('reservation__reservation__cancel');
      expect(inputsOf(turns[0].body, 'reservation__reservation__cancel')).not.toContain('on_behalf_of');
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('asking');
      expect(await statusOf(context, reservation)).toBe(before);
      expect(
        psql(`select body from whatsapp_inbox_message where conversation_id = '${message.conversation_id}' and direction = 'outbound'`),
      ).toBe(THANKS);

      // The owner finds the cancellation in «Waiting for your answer», naming the reservation by its guest, day and
      // time, never by its id.
      await page.goto('/flow/automations');
      const question = shown(page)
        .locator('[data-testid=flow-inbox] article')
        .filter({ hasText: 'The assistant wants to change something in «Reservations»' });
      await expect(question).toBeVisible();
      await expect(question).toContainText('From «WhatsApp → table booked»');
      // The account is in English: Reservas says the reservation «E2E Lucía · Nov 2, 2026 · 9:00 PM».
      const said = new Date(`${DAY.date}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
      await expect(question).toContainText(`E2E Lucía · ${said} · 9:00`);
      await expect(question).toContainText('On behalf of the customer: E2E Lucía');
      await expect(question).not.toContainText(reservation);
      await question.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);

      // «Approve» (the owner may cancel reservations, FLOW-F28): Reservas cancels it, and the assistant hears so.
      await question.locator('[data-testid^=flow-question-yes-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
      await expect(question).toHaveCount(0);
      expect(await statusOf(context, reservation)).toBe('cancelled');
      const answered = chats();
      await relay(parkedEvent(flowId));
      expect(chats()).toBe(answered + 1);
      expect(JSON.stringify(provider.seen.at(-1)?.body)).toContain('"role":"tool"');
      await expect.poll(() => psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('succeeded');
      // What the assistant said then went to them, after the thanks.
      expect(
        psql(`select count(*) from whatsapp_inbox_message where conversation_id = '${message.conversation_id}' and direction = 'outbound'`),
      ).toBe('2');
    } finally {
      await context.close();
    }
  });
}

for (const viewport of VIEWPORTS) {
  test(`WHATSAPP_INBOX-F25 a guest who asks to cancel another guest's table gets no cancellation, even after the owner's yes, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      await openTheBook(context);
      const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables]');
      await card.locator('[data-testid=whatsapp-inbox-autoreply-tables-on]').click();
      await confirmDialog(page, 'Book a table');
      await expect(card).toContainText('On');

      // Marta's reservation at 21:00 for 2, on her card; Lucía, from another number and with no card yet, writes.
      const lucia = e2ePhone();
      let marta = e2ePhone();
      while (marta === lucia) marta = e2ePhone();
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

      // The assistant names Marta's reservation by its id and, as a model fooled by the message might, says it is on
      // Marta's behalf: the step puts Lucía's card over it.
      const asked = { id: reservation, on_behalf_of: theirs.data.id };
      const message = receive(lucia, `Cancel E2E Marta's table on Saturday\nE2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`, 'E2E Lucía');
      const received = psql(
        `select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${message.id}'`,
      );
      expect(received, 'whatsapp_inbox.message.received of the message in the outbox').not.toBe('');
      await relay(received);
      const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);
      const first = chats();
      await relay(parkedEvent(flowId));

      const turns = provider.seen.filter((seen) => seen.path === '/v1/chat/completions').slice(first);
      expect(turns).toHaveLength(1);
      expect(inputsOf(turns[0].body, 'reservation__reservation__cancel')).not.toContain('on_behalf_of');
      expect(inputsOf(turns[0].body, 'reservation__reservation__update')).not.toContain('on_behalf_of');
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('asking');

      // The card says whose reservation it is and on whose behalf it would go: Lucía's, never Marta's.
      await page.goto('/flow/automations');
      const question = shown(page)
        .locator('[data-testid=flow-inbox] article')
        .filter({ hasText: 'The assistant wants to change something in «Reservations»' });
      await expect(question).toBeVisible();
      const said = new Date(`${DAY.date}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
      await expect(question).toContainText(`E2E Marta · ${said} · 9:00`);
      await expect(question).toContainText('On behalf of the customer: E2E Lucía');
      await expect(question).not.toContainText('On behalf of the customer: E2E Marta');
      await question.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${OTHER_KEY}-${viewport.label}`);

      // «Approve»: Reservas refuses it on Lucía's behalf, Marta's reservation is as it was and Lucía is told no.
      await question.locator('[data-testid^=flow-question-yes-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
      await expect(question).toHaveCount(0);
      expect(await statusOf(context, reservation)).toBe(before);
      await relay(parkedEvent(flowId));
      expect(JSON.stringify(provider.seen.at(-1)?.body)).toContain('reservation.customer_mismatch');
      await expect.poll(() => psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('succeeded');
      expect(await statusOf(context, reservation)).toBe(before);
      expect(
        psql(
          `select body from whatsapp_inbox_message where conversation_id = '${message.conversation_id}' and direction = 'outbound' order by created_at desc, id desc limit 1`,
        ),
      ).toBe('No lo he hecho.');
    } finally {
      await context.close();
    }
  });
}
