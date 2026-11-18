// What the e2e of WhatsApp's automatic answers shares (WHATSAPP_INBOX-F14, F15, F19): the real dependencies of an answer
// that asks the assistant, around each spec's own cleaning. The Hub of the stack, its SaaS's gateway and, behind it, the
// e2e's provider (provider-helpers.ts), with the channel connected before each test. `a`'s photo stays each spec's: it
// keeps it before `answerSpec` and puts it back after, in hooks of its own, where whatsapp-photo.test.ts looks for them.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider } from './assistant-provider';
import { emptyMonth } from './assistant-real';
import { cardDeletes } from './customer-helpers';
import { confirmDialog } from './flow-helpers';
import { A, api, psql, shown } from './helpers';
import { askedOnce, inputsOf, relay, seededProvider } from './provider-helpers';
import { type BookingDay, type OpenBook, openTheBook } from './reservation-helpers';
import { cleanUp as inboxCleanUp, pushChannel, receive } from './whatsapp-helpers';

/** Registers the hooks of a spec of an answer that asks the assistant, and gives its provider once they have run. */
export function answerSpec(cleanUp: () => void): () => Provider {
  let provider: Provider;
  test.beforeAll(async () => {
    provider = await seededProvider();
  });
  test.beforeEach(() => {
    cleanUp();
    pushChannel({ status: 'connected' });
  });
  test.afterAll(async () => {
    cleanUp();
    await provider?.close();
  });
  return () => provider;
}

/** The inbox's answers and notices (with their runs and questions), the reservations and cards their runs made, the
 *  book's slot and open day of the spec (`book`), the conversations and channel of the inbox's specs, and the month's
 *  messages of the business `a`. */
export function bookingCleanUp(book: OpenBook): void {
  const flows = "select id from flow_flow where recipe like 'whatsapp_inbox/%'";
  const reservations = "select id from reservation_reservation where guest_phone like '+3469900%'";
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from table_hold where source_ref in (${reservations.replace('select id', 'select id::text')})`,
      `delete from reservation_reservation where id in (${reservations})`,
      `delete from reservation_timeslot where max_reservations = ${book.sentinel}`,
      `delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason = '${book.reason}')`,
      `delete from schedule_override where reason = '${book.reason}'`,
    ].join('; '),
  );
  inboxCleanUp();
  psql(cardDeletes("select id from customer_customer where source = 'whatsapp' and phone like '%69900%'").join('; '));
  emptyMonth();
}

/** The owner turns «Book a table» on, on the inbox's settings page. */
export async function turnOnBookATable(page: Page): Promise<void> {
  const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables]');
  await card.locator('[data-testid=whatsapp-inbox-autoreply-tables-on]').click();
  await confirmDialog(page, 'Book a table');
  await expect(card).toContainText('On');
}

/** The stage of «Book a table»: the book open (`book`), reviewing every new reservation when `reviewing`, and the answer
 *  turned on by the owner on the inbox's settings page. */
export async function tablesAnswered(context: BrowserContext, page: Page, book: OpenBook, reviewing = false): Promise<void> {
  await openTheBook(context, book);
  if (reviewing) {
    const rules = await api(context, A, 'POST', '/reservation/settings', { auto_confirm: false });
    expect(rules.status, JSON.stringify(rules.data)).toBe(200);
  }
  await turnOnBookATable(page);
}

/** A guest's card from WhatsApp and her reservation at 21:00 on `day` for `party`, made through the apps' APIs. */
export async function guestWithATable(
  context: BrowserContext,
  day: BookingDay,
  guest: { name: string; phone: string },
  party: number,
): Promise<{ card: string; reservation: string }> {
  const card = await api<{ id: string }>(context, A, 'POST', '/customer/customers', { ...guest, source: 'whatsapp' });
  expect(card.status, JSON.stringify(card.data)).toBe(201);
  const made = await api<{ id: string }>(context, A, 'POST', '/reservation/reservations', {
    customer_id: card.data.id,
    guest_name: guest.name,
    guest_phone: guest.phone,
    date: day.date,
    time: '21:00',
    party_size: party,
  });
  expect(made.status, JSON.stringify(made.data)).toBe(201);
  return { card: card.data.id, reservation: made.data.id };
}

/** The assistant's change in Reservations, waiting in «Waiting for your answer» of Automations. */
export async function reservationsQuestion(page: Page): Promise<Locator> {
  await page.goto('/flow/automations');
  const question = shown(page)
    .locator('[data-testid=flow-inbox] article')
    .filter({ hasText: 'The assistant wants to change something in «Reservations»' });
  await expect(question).toBeVisible();
  return question;
}

/** The answer's step asks the assistant once, which is offered neither a cancellation nor a change on whose behalf (the
 *  step fixes it to the card of the number that writes), and its run waits for the owner. */
export async function askedOnBehalfOfTheWriter(provider: Provider, flowId: string): Promise<void> {
  const turn = await askedOnce(provider, flowId);
  expect(inputsOf(turn.body, 'reservation__reservation__cancel')).not.toContain('on_behalf_of');
  expect(inputsOf(turn.body, 'reservation__reservation__update')).not.toContain('on_behalf_of');
  expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('asking');
}

/** The customer writes `text` from `phone`, as erplora.com pushes it, and the relay hands it to the answer; her message. */
export async function customerWrites(phone: string, text: string, name: string): Promise<ReturnType<typeof receive>> {
  const message = receive(phone, text, name);
  const received = psql(`select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${message.id}'`);
  expect(received, 'whatsapp_inbox.message.received of the message in the outbox').not.toBe('');
  await relay(received);
  return message;
}
