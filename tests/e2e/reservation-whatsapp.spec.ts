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
import { expect, type Locator, type Page, test } from '@playwright/test';

import { capture, psql } from './helpers';
import { approve, signedIn } from './flow-helpers';
import { askedOnce, chats, workerAsks } from './provider-helpers';
import { guestRowInTheBook, madridDay } from './reservation-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { answerSpec, bookingCleanUp, customerWrites, reservationsQuestion, tablesAnswered } from './whatsapp-answer-helpers';
import { e2ePhone, keepPhoto, restorePhoto } from './whatsapp-helpers';

const TASK = 'CLOSE-RESERVATION';
const ANSWER = 'whatsapp_inbox/reservation_from_whatsapp';
const GUEST = 'E2E WhatsApp Marta';
/** How many days ahead the booking is: past the minimum notice and within the days ahead of the guest's rules. */
const AHEAD = 3;
/** The day this spec books on, and how its slot and open day are known again (slots have no name). */
const BOOK = { day: madridDay(AHEAD), sentinel: 79, reason: 'E2E Reservation WhatsApp open' };
const DAY = BOOK.day;

/** The guest writes `text` from `phone`: the relay starts the answer, which asks the assistant; what it wants waits in
 *  «Waiting for your answer» until the owner's «Approve», and then the assistant hears what Reservas answered. */
async function askAndApprove(page: Page, phone: string, text: string, viewport: string, card: string): Promise<void> {
  await customerWrites(phone, text, GUEST);
  const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);
  await askedOnce(provider(), flowId);

  const question = await reservationsQuestion(page);
  await expect(question).toContainText(card);
  await approve(page, question);
  const answered = chats(provider()).length;
  await workerAsks(flowId);
  expect(chats(provider()), `${viewport}: the assistant heard what Reservas answered`).toHaveLength(answered + 1);
  expect(JSON.stringify(provider().seen.at(-1)?.body)).toContain('"role":"tool"');
}

/** The Reservations book on DAY, and the guest's row in it. */
const bookRow = (page: Page): Promise<Locator> => guestRowInTheBook(page, { ahead: AHEAD, day: DAY }, GUEST);

test.beforeAll(keepPhoto);
const provider = answerSpec(() => bookingCleanUp(BOOK));
test.afterAll(restorePhoto);

for (const viewport of VIEWPORTS) {
  test(`RESERVATION-F17 RESERVATION-F18 a table booked, moved and cancelled by WhatsApp shows in the Reservations book at ${viewport.label}`, async ({ browser }) => {
    // Three requests, each three ticks of the relay (a `manage.py shell` of its own) and a turn of the assistant.
    test.setTimeout(600_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      // The owner turns «Book a table» on, the book reviewing every new reservation (F04).
      await tablesAnswered(context, page, BOOK, true);

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
