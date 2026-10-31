// A table that comes by WhatsApp, seen where the restaurant works: the Reservations book (apps/reservation/WORKBOOK.md
// RESERVATION-F17 and F18). The owner turns «Book a table» on (WHATSAPP_INBOX-F15) with the book reviewing new
// reservations (RESERVATION-F04); a guest with no card writes for a table for 4 at 21:00, and after the owner's «Approve»
// in «Waiting for your answer» the book shows it on its day, Pending, under the guest's name and number, booked through
// WhatsApp on a card made from WhatsApp (WHATSAPP_INBOX-F24). The guest then asks to come at 22:00 and, after the yes,
// the book shows the new time; then cancels, and after the yes the book shows it Cancelled (WHATSAPP_INBOX-F25).
// End to end with the real dependencies, as fix-whatsapp-inbox-table-cancel.spec.ts does: the Hub of this stack, its
// SaaS's gateway and, behind it, the e2e's provider (assistant-provider.ts, started by this spec; the SaaS seeded with
// it, README «El asistente») and Meta's Graph (README «WhatsApp»). The provider's `E2E-ASK` marker stands for the
// assistant's choice; whose card and number it goes on is fixed by the answer's step, never by the assistant.
// flow: RESERVATION-F17 RESERVATION-F18 (and WHATSAPP_INBOX-F24 WHATSAPP_INBOX-F25)
import { execFile, execSync } from 'node:child_process';
import { promisify } from 'node:util';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, HUB_DIR, psql, REPO_DIR, shown } from './helpers';
import { confirmDialog, parkedEvent, RELAY, signedIn } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { STACK } from './stack';
import { cleanUp as inboxCleanUp, e2ePhone, pushChannel, receive } from './whatsapp-helpers';

const TASK = 'CLOSE-RESERVATION';
const ANSWER = 'whatsapp_inbox/reservation_from_whatsapp';
const GUEST = 'E2E WhatsApp Marta';
/** How the book's slot and the open day this spec makes are known again (slots have no name). */
const SENTINEL = 79;
const OPEN_REASON = 'E2E Reservation WhatsApp open';
/** How many days ahead the booking is: past the minimum notice and within the days ahead of the guest's rules. */
const AHEAD = 3;
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

const DAY = madridDay(AHEAD);

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
      `delete from table_hold where source_ref in (${reservations.replace('select id', 'select id::text')})`,
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

const chats = (): number => provider.seen.filter((seen) => seen.path === '/v1/chat/completions').length;

/** The book open on DAY, all day, whatever the hours of the database, reviewing every new reservation (F04). */
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
  const rules = await api(context, A, 'POST', '/reservation/settings', { auto_confirm: false });
  expect(rules.status, JSON.stringify(rules.data)).toBe(200);
}

/** The guest writes `text` from `phone`: the relay starts the answer, which asks the assistant; what it wants waits in
 *  «Waiting for your answer» until the owner's «Approve», and then the assistant hears what Reservas answered. */
async function askAndApprove(page: Page, phone: string, text: string, viewport: string, card: string): Promise<void> {
  const message = receive(phone, text, GUEST);
  const received = psql(`select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${message.id}'`);
  expect(received, 'whatsapp_inbox.message.received of the message in the outbox').not.toBe('');
  await relay(received);
  const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);
  const before = chats();
  await relay(parkedEvent(flowId));
  expect(chats()).toBe(before + 1);

  await page.goto('/flow/automations');
  const question = shown(page)
    .locator('[data-testid=flow-inbox] article')
    .filter({ hasText: 'The assistant wants to change something in «Reservations»' });
  await expect(question).toBeVisible();
  await expect(question).toContainText(card);
  await question.locator('[data-testid^=flow-question-yes-]').click();
  await expect(page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
  await expect(question).toHaveCount(0);
  const answered = chats();
  await relay(parkedEvent(flowId));
  expect(chats(), `${viewport}: the assistant heard what Reservas answered`).toBe(answered + 1);
  expect(JSON.stringify(provider.seen.at(-1)?.body)).toContain('"role":"tool"');
}

/** The Reservations book on DAY, and the guest's row in it. */
async function bookRow(page: Page) {
  await page.goto('/reservation/reservations');
  const view = shown(page);
  for (let step = 0; step < AHEAD; step++) await view.locator('[data-testid=reservation-day-next]').click();
  await expect(view.locator('[data-testid=reservation-day]')).toHaveAttribute('data-day', DAY.date);
  return view.locator('[data-testid=reservation-list-row]', { hasText: GUEST });
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
  test(`RESERVATION-F17 RESERVATION-F18 a table booked, moved and cancelled by WhatsApp shows in the Reservations book at ${viewport.label}`, async ({ browser }) => {
    // Three requests, each three ticks of the relay (a `manage.py shell` of its own) and a turn of the assistant.
    test.setTimeout(600_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      await openTheBook(context);

      // The owner turns «Book a table» on.
      const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables]');
      await card.locator('[data-testid=whatsapp-inbox-autoreply-tables-on]').click();
      await confirmDialog(page, 'Book a table');
      await expect(card).toContainText('On');

      // F17: a guest with no card yet asks for a table for 4 at 21:00; after the yes, the book has it.
      const phone = e2ePhone();
      const booking = { guest_name: GUEST, date: DAY.date, time: '21:00', party_size: 4, source: 'whatsapp' };
      await askAndApprove(page, phone, `Table for 4 at 21:00, please\nE2E-ASK reservation__reservation__create ${JSON.stringify(booking)}`, viewport.label, phone);
      const row = await bookRow(page);
      await expect(row).toHaveCount(1);
      await expect(row).toContainText('9:00 PM');
      await expect(row).toContainText('Pending');
      const id = (await row.getAttribute('data-id'))!;
      // Booked through WhatsApp, on the card WhatsApp made for that number, with that number.
      expect(
        psql(
          `select r.party_size || ' ' || r.source || ' ' || r.guest_phone || ' ' || c.source from reservation_reservation r join customer_customer c on c.id = r.customer_id where r.id = '${id}'`,
        ),
      ).toBe(`4 whatsapp ${phone} whatsapp`);
      await row.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-${viewport.label}`);

      // F18: they ask to come at 22:00; after the yes, the book shows the new time.
      const move = { id, time: '22:00' };
      await askAndApprove(page, phone, `Can we come at 22:00?\nE2E-ASK reservation__reservation__update ${JSON.stringify(move)}`, viewport.label, GUEST);
      const moved = await bookRow(page);
      await expect(moved).toContainText('10:00 PM');
      await expect(moved).toContainText('Pending');
      await expect(moved).not.toContainText('9:00 PM');

      // F18: they cannot come; after the yes, the book shows it cancelled.
      const cancel = { id, reason: 'The guest asked by WhatsApp' };
      await askAndApprove(page, phone, `We can't make it, please cancel\nE2E-ASK reservation__reservation__cancel ${JSON.stringify(cancel)}`, viewport.label, GUEST);
      const cancelled = await bookRow(page);
      await expect(cancelled).toContainText('Cancelled');
      await expect(cancelled).toContainText('10:00 PM');
      await cancelled.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-cancelled-${viewport.label}`);
    } finally {
      await context.close();
    }
  });
}
