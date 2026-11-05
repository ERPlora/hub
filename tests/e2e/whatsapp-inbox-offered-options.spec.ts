// A guest picks one of the times offered by writing its number (apps/whatsapp_inbox/WORKBOOK.md WHATSAPP_INBOX-F19). The
// owner turns «Book a table» on (WHATSAPP_INBOX-F15) with the book reviewing new reservations; a guest asks for 21:00, there
// is no room and the answer offers a short numbered list; the guest writes «el 2» and, since the answer hears the list it
// last wrote them, the second time waits for the owner's «Approve» in «Waiting for your answer» and the Reservations book
// shows it (WHATSAPP_INBOX-F24). The inbox shows the list and the «el 2» in the guest's conversation.
// End to end with the real dependencies, as reservation-whatsapp.spec.ts does: the Hub of this stack, its SaaS's gateway
// and, behind it, the e2e's provider (assistant-provider.ts, started by this spec; the SaaS seeded with it, README «El
// asistente») and Meta's Graph (README «WhatsApp»). The provider's `E2E-OFFER` marker stands for the assistant offering
// the list, and the `E2E-ASK` line in it for the assistant's choice of the option the guest names: a choice it can only
// make if the «el 2» comes with the list.
// flow: WHATSAPP_INBOX-F19
import { execFileSync } from 'node:child_process';
import { join, resolve } from 'node:path';

import { expect, type Page, test } from '@playwright/test';

import { saasSql } from './assistant-real';
import { A, api, capture, psql, REPO_DIR, shown } from './helpers';
import { confirmDialog, parkedEvent, signedIn } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { STACK } from './stack';
import { answerSpec, chats, customerWrites, openTheBook, relay } from './whatsapp-answer-helpers';
import { NUMBER_ID, TOKEN } from './whatsapp-graph';
import { cleanUp as inboxCleanUp, e2ePhone, metaGraph, restorePhoto, seedErplora } from './whatsapp-helpers';

const TASK = 'CLOSE-WHATSAPP_INBOX';
const ANSWER = 'whatsapp_inbox/reservation_from_whatsapp';
const GUEST = 'E2E WhatsApp Nora';
/** How this spec's slot and open day are known again (slots have no name); not reservation-whatsapp.spec.ts's. */
const SENTINEL = 78;
const OPEN_REASON = 'E2E WhatsApp offered options open';
/** How many days ahead the booking is: past the minimum notice and within the days ahead of the guest's rules. */
const AHEAD = 3;
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
const SAAS_DIR = resolve(process.env.E2E_SAAS_DIR || join(REPO_DIR, 'saas'));

/** The business's day `days` from today (Madrid in phase 1) and its weekday, Monday 0. */
function madridDay(days: number): { date: string; weekday: number } {
  const date = new Date(Date.now() + days * 86_400_000).toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' });
  return { date, weekday: (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7 };
}

const DAY = madridDay(AHEAD);

/** The inbox's answers (with their runs and questions), this spec's reservations and cards, its slot and open day, the
 *  conversations and channel of the inbox's specs, and the month's messages of the business `a`. */
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

/** erplora.com's seed gives `a`'s number a made-up permission that the run's Meta refuses, so whatever the Hub writes
 *  a customer ends «Not sent» (flow-send-message.spec.ts). A list she never got is not one she can answer (F19), so this
 *  spec gives the number the business's token the run's Graph takes (`TOKEN`, whatsapp-graph.ts): what the answer
 *  writes her gets there. The `afterAll` seeds again, which puts the made-up permission back for the next spec. */
function numberSends(): void {
  const code = `from whatsapp.models import PhoneNumber
for number in PhoneNumber.objects.filter(phone_number_id='${NUMBER_ID}'):
    number.access_token = '${TOKEN}'
    number.needs_reconnect = False
    number.save()`;
  execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', code], { cwd: SAAS_DIR, env: { ...process.env, DB_NAME: SAAS_DB } });
}

/** The guest writes `text` from `phone` and the answer asks the assistant once: what the user turn of that request
 *  said (the Hub's prompt, with her words and what the business last wrote her). */
async function writes(phone: string, text: string): Promise<string> {
  await customerWrites(phone, text, GUEST);
  const before = chats(provider()).length;
  await relay(parkedEvent(psql(`select id from flow_flow where recipe = '${ANSWER}'`)));
  expect(chats(provider())).toHaveLength(before + 1);
  return JSON.stringify(chats(provider()).at(-1)?.body);
}

/** What the Hub last wrote to `phone`. */
const lastWritten = (phone: string): string =>
  psql(
    `select m.body from whatsapp_inbox_message m join whatsapp_inbox_conversation c on c.id = m.conversation_id where c.phone = '${phone}' and m.origin = 'hub' order by m.created_at desc, m.id desc limit 1`,
  );

/** The Reservations book on DAY, and the guest's row in it. */
async function bookRow(page: Page) {
  await page.goto('/reservation/reservations');
  const view = shown(page);
  for (let step = 0; step < AHEAD; step++) await view.locator('[data-testid=reservation-day-next]').click();
  await expect(view.locator('[data-testid=reservation-day]')).toHaveAttribute('data-day', DAY.date);
  return view.locator('[data-testid=reservation-list-row]', { hasText: GUEST });
}

test.beforeAll(async () => {
  // erplora.com takes `a`'s number (connected) and this Hub keeps its photo; it reaches Meta only through the run's
  // Graph, so what the answer writes the guest gets there (a list that did not is not one she can answer).
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  await metaGraph();
  numberSends();
});
const provider = answerSpec(cleanUp);
test.afterAll(() => {
  seedErplora(); // the seed's made-up permission back, for the specs after this one
  restorePhoto();
});

for (const viewport of VIEWPORTS) {
  test(`WHATSAPP_INBOX-F19 a guest who writes «el 2» to the times offered is booked at the second after the owner's yes at ${viewport.label}`, async ({ browser }) => {
    // Two messages, each two ticks of the relay (a `manage.py shell` of its own) and a turn of the assistant, and the yes.
    test.setTimeout(600_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      await openTheBook(context, DAY, SENTINEL, OPEN_REASON);
      const rules = await api(context, A, 'POST', '/reservation/settings', { auto_confirm: false });
      expect(rules.status, JSON.stringify(rules.data)).toBe(200);

      // The owner turns «Book a table» on.
      const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables]');
      await card.locator('[data-testid=whatsapp-inbox-autoreply-tables-on]').click();
      await confirmDialog(page, 'Book a table');
      await expect(card).toContainText('On');

      // No room at 21:00: the answer offers two other times and nothing waits for the owner yet.
      const phone = e2ePhone();
      const booking = { guest_name: GUEST, date: DAY.date, time: '21:30', party_size: 4, source: 'whatsapp' };
      const list = ['No table at 21:00, sorry. I have:', '1. 20:00', '2. 21:30', `E2E-ASK reservation__reservation__create ${JSON.stringify(booking)}`];
      const first = await writes(phone, `Table for 4 at 21:00, please\nE2E-OFFER ${list.join(' | ')}`);
      expect(first).toContain('———\\n\\n———'); // nothing was offered to her before
      expect(lastWritten(phone)).toBe(list.join('\n'));
      expect(psql(`select count(*) from flow_question where flow_id in (select id from flow_flow where recipe = '${ANSWER}')`)).toBe('0');

      // She writes «el 2»: the answer hears the list it wrote her, and the second time waits for the owner's yes.
      const second = await writes(phone, 'el 2');
      expect(second).toContain('———\\nel 2\\n———');
      expect(second).toContain(JSON.stringify(list.join('\n')).slice(1, -1));
      await page.goto('/flow/automations');
      const question = shown(page)
        .locator('[data-testid=flow-inbox] article')
        .filter({ hasText: 'The assistant wants to change something in «Reservations»' });
      await expect(question).toBeVisible();
      await expect(question).toContainText(phone);
      await question.locator('[data-testid^=flow-question-yes-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
      const answered = chats(provider()).length;
      await relay(parkedEvent(psql(`select id from flow_flow where recipe = '${ANSWER}'`)));
      expect(chats(provider()), `${viewport.label}: the assistant heard what Reservas answered`).toHaveLength(answered + 1);

      // The book has the second time, Pending.
      const row = await bookRow(page);
      await expect(row).toHaveCount(1);
      await expect(row).toContainText('9:30 PM');
      await expect(row).toContainText('Pending');
      expect(psql(`select time::text || ' ' || guest_phone from reservation_reservation where guest_phone = '${phone}'`)).toBe(`21:30:00 ${phone}`);

      // The inbox shows the list and her «el 2» in her conversation.
      const conversation = psql(`select id from whatsapp_inbox_conversation where phone = '${phone}'`);
      await page.goto(`/whatsapp_inbox/inbox?conversation=${conversation}`);
      const bubbles = (side: 'inbound' | 'outbound') => shown(page).locator(`[data-testid=whatsapp-inbox-message][data-side=${side}]`);
      // The list as the business wrote it, one option a line, and it got to her.
      const offered = bubbles('outbound').filter({ hasText: /I have:\s+1\. 20:00\s+2\. 21:30/ });
      await expect(offered).toHaveCount(1);
      await expect(offered).not.toContainText('Not sent');
      const answer = bubbles('inbound').last();
      await expect(bubbles('inbound')).toHaveCount(2);
      await expect(answer).toContainText('el 2');
      await answer.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-${viewport.label}`);
    } finally {
      await context.close();
    }
  });
}
