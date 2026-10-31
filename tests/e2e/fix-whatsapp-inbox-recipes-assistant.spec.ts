// «Book a table» (apps/whatsapp_inbox/WORKBOOK.md WHATSAPP_INBOX-F15), turned on from WhatsApp's settings, and the
// WhatsApp of a guest who asks for a table answered by the assistant «Ask me first» (F24), end to end with its real
// dependencies: the Hub of this stack, its SaaS's gateway (`/internal/assistant/chat`) and, behind it, the e2e's
// provider (assistant-provider.ts, an OpenAI-compatible server on 127.0.0.1 that this spec starts): no mock between the
// Hub and the provider. The SaaS must be seeded with that provider (README «El asistente»).
// No card books appointments (F14). The owner turns «Book a table» on (its answer and its notice, in Automations'
// gallery too: FLOW-F33); the message of a guest who wrote before (their card, come by WhatsApp, already in Customers)
// comes in as erplora.com pushes it; the worker's relay hands its event to Automations, whose run reads it, thanks them,
// finds their card and asks the assistant with only what the answer was granted, never naming that card: the step fixes
// it on the booking (FLOW-F38); the reservation it wants, with only their name and phone, waits in «Waiting for your
// answer» with whom it is for, and the owner's «Approve» books it in Reservas, on that card.
// «Turn off» pauses both, never deleting them (F17).
// flow: WHATSAPP_INBOX-F15 WHATSAPP_INBOX-F14 WHATSAPP_INBOX-F17 WHATSAPP_INBOX-F24 FLOW-F33 FLOW-F12
import { execFile, execSync } from 'node:child_process';
import { promisify } from 'node:util';

import { expect, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, HUB_DIR, psql, REPO_DIR, shown } from './helpers';
import { confirmDialog, parkedEvent, RELAY, signedIn } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { STACK } from './stack';
import { cleanUp as inboxCleanUp, e2ePhone, pushChannel, receive } from './whatsapp-helpers';

const TASK = 'FIX-HUB-WHATSAPP-INBOX-RECIPES-USE-ASSISTANT-STEP';
const ANSWER = 'whatsapp_inbox/reservation_from_whatsapp';
const NOTICE = 'whatsapp_inbox/reservation_confirmed';
const THANKS = 'Thanks for writing! Let me check the reservations book and I will come straight back to you.';
/** How the book's slot and the open day this spec makes are known again (slots have no name). */
const SENTINEL = 78;
const OPEN_REASON = 'E2E WhatsApp table open';
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

/** The inbox's answers and notices (with their runs and questions), the reservations and cards their runs made, the
 *  book's slot and open day of this spec, the conversations and channel of the inbox's specs, and the month's
 *  messages of the business `a`: each size starts with the card off. */
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

const built = (ref: string): string =>
  psql(`select enabled::text || ' ' || (deleted_at is null)::text from flow_flow where recipe = '${ref}'`);

/** One tick of the worker's relay (in `a`'s database; the stack's worker relays too): the outbox event `id` handed to Automations' reaction,
 *  and what it leaves for after its COMMIT made at once. It does not block this process: the provider the SaaS asks
 *  lives here, and must answer. */
async function relay(id: string): Promise<void> {
  await promisify(execFile)('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', RELAY], {
    cwd: HUB_DIR,
    env: { ...process.env, FLOW_EVENT: id },
  });
}

const chats = (): number => provider.seen.filter((seen) => seen.path === '/v1/chat/completions').length;

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
  test(`WHATSAPP_INBOX-F15 «Book a table» turned on, and a WhatsApp asking for a table is booked after the owner's yes at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      // The book open that day, all day, whatever the hours of the database (as reservation-book.spec.ts does).
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

      // F14: no card books appointments. F15: the card says what it does; on, after a question, with its notice.
      await expect(shown(page).locator('[data-testid=whatsapp-inbox-autoreply-appointments]')).toHaveCount(0);
      const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables]');
      await expect(card).toContainText('Book a table');
      await expect(card).toContainText('Off');
      await card.locator('[data-testid=whatsapp-inbox-autoreply-tables-on]').click();
      await confirmDialog(page, 'Book a table');
      await expect(card.locator('[data-testid=whatsapp-inbox-autoreply-tables-done]')).toHaveText(
        'Done. Write to yourself from another phone: “I want a table for two tomorrow”.',
      );
      await expect(card).toContainText('On');
      await expect(card.locator('[data-testid=whatsapp-inbox-autoreply-tables-confirm] ion-radio')).toHaveCount(2);
      expect(built(ANSWER)).toBe('true true');
      expect(built(NOTICE)).toBe('true true');
      // «Ask me first», and only Reservas' free tables, booking, changing, cancelling and waiting list among the
      // assistant's tools (F25: cancelling only because its step asks first, FLOW-F28).
      const steps = JSON.parse(psql(`select steps from flow_flow where recipe = '${ANSWER}'`)) as {
        kind: string;
        mode?: string;
        tools?: string[];
      }[];
      const assistant = steps.find((each) => each.kind === 'assistant');
      expect(assistant?.mode).toBe('ask');
      expect(assistant?.tools).toEqual([
        'reservation.availability.day',
        'reservation.availability.tables',
        'reservation.reservation.create',
        'reservation.reservation.update',
        'reservation.reservation.cancel',
        'reservation.waitlist.create',
      ]);
      await card.locator('[data-testid=whatsapp-inbox-autoreply-tables-off]').scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-settings-${viewport.label}`);

      // F24: they write; the relay starts the answer, which thanks them, finds their card and asks the assistant, who
      // books with only their name and phone: Reservas finds the card by that phone itself, though the step holds no
      // right in Customers (FLOW-F12, FIX-HUB-FLOW-STEP-RESERVATION-BY-PHONE-DENIED).
      const phone = e2ePhone();
      const guest = await api<{ id: string }>(context, A, 'POST', '/customer/customers', { name: 'E2E Lucía', phone, source: 'whatsapp' });
      expect(guest.status, JSON.stringify(guest.data)).toBe(201);
      const booking = {
        guest_name: 'E2E Lucía',
        guest_phone: phone,
        date: DAY.date,
        time: '21:00',
        party_size: 4,
        source: 'whatsapp',
      };
      const message = receive(phone, `E2E-ASK reservation__reservation__create ${JSON.stringify(booking)}`, 'E2E Lucía');
      const received = psql(
        `select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${message.id}'`,
      );
      expect(received, 'whatsapp_inbox.message.received of the message in the outbox').not.toBe('');
      await relay(received);
      const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);
      const before = chats();
      await relay(parkedEvent(flowId));

      // The assistant was never told their card nor offered to say it (the step fixes it), was offered only what the
      // answer grants of the Hub's operations (`<app>__<entity>__<action>`; the SaaS adds its own clock), and wanted to
      // book: nothing is booked yet.
      const turns = provider.seen.filter((seen) => seen.path === '/v1/chat/completions').slice(before);
      expect(turns).toHaveLength(1);
      expect(JSON.stringify(turns[0].body)).not.toContain(guest.data.id);
      type Tool = { function: { name: string; parameters?: { properties?: Record<string, unknown> } } };
      const offered = (turns[0].body as { tools?: Tool[] }).tools ?? [];
      const create = offered.find((tool) => tool.function.name === 'reservation__reservation__create');
      expect(Object.keys(create?.function.parameters?.properties ?? {})).not.toContain('customer_id');
      const tools = offered.map((tool) => tool.function.name).filter((name) => name.includes('__'));
      expect(tools).toEqual([
        'reservation__availability__day',
        'reservation__availability__tables',
        'reservation__reservation__create',
        'reservation__reservation__update',
        'reservation__reservation__cancel',
        'reservation__waitlist__create',
      ]);
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('asking');
      expect(psql(`select count(*) from reservation_reservation where guest_phone = '${phone}'`)).toBe('0');
      expect(psql(`select count(*) from customer_customer where source = 'whatsapp' and phone like '%${phone.slice(-9)}'`)).toBe('1');
      expect(
        psql(`select body from whatsapp_inbox_message where conversation_id = '${message.conversation_id}' and direction = 'outbound'`),
      ).toBe(THANKS);

      // The owner finds the reservation in «Waiting for your answer», with whom it is for.
      await page.goto('/flow/automations');
      const question = shown(page)
        .locator('[data-testid=flow-inbox] article')
        .filter({ hasText: 'The assistant wants to change something in «Reservations»' });
      await expect(question).toBeVisible();
      await expect(question).toContainText('From «WhatsApp → table booked»');
      await expect(question).toContainText(phone);
      await question.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-${viewport.label}`);

      // «Approve»: Reservas books it, on their card (no second one), and the assistant hears what Reservas answered.
      await question.locator('[data-testid^=flow-question-yes-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
      await expect(question).toHaveCount(0);
      expect(
        psql(
          `select r.party_size || ' ' || r.time::text || ' ' || r.source || ' ' || r.customer_id::text from reservation_reservation r where r.guest_phone = '${phone}'`,
        ),
        `what Reservas answered: ${psql(`select outputs->'_turn'->'messages' from flow_flowrun where flow_id = '${flowId}'`)}`,
      ).toBe(`4 21:00:00 whatsapp ${guest.data.id}`);
      expect(psql(`select count(*) from customer_customer where source = 'whatsapp' and phone like '%${phone.slice(-9)}'`)).toBe('1');
      const asked = chats();
      await relay(parkedEvent(flowId));
      expect(chats()).toBe(asked + 1);
      expect(JSON.stringify(provider.seen.at(-1)?.body)).toContain('"role":"tool"');
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('succeeded');

      // F17: off from the same card, both paused and kept.
      await page.goto('/whatsapp_inbox/settings');
      await shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables-off]').click();
      await expect(shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables]')).toContainText('Off');
      await expect(shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables-on]')).toBeVisible();
      expect(built(ANSWER)).toBe('false true');
      expect(built(NOTICE)).toBe('false true');
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    } finally {
      await context.close();
    }
  });
}
