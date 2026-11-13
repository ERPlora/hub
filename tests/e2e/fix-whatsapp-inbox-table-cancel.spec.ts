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
import { expect, test } from '@playwright/test';

import { NOT_DONE } from './assistant-provider';
import { capture, psql } from './helpers';
import { approve, signedIn } from './flow-helpers';
import { askedOnce, chats, inputsOf, workerAsks } from './provider-helpers';
import { dayAsSaid, madridDay, reservationStatus } from './reservation-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { answerSpec, askedOnBehalfOfTheWriter, bookingCleanUp, customerWrites, guestWithATable, reservationsQuestion, tablesAnswered } from './whatsapp-answer-helpers';
import { e2ePhone, keepPhoto, restorePhoto } from './whatsapp-helpers';

const KEY = 'FIX-HUB-WHATSAPP-INBOX-AUTO-REPLY-CANNOT-CANCEL-A-RESERVATION';
const OTHER_KEY = 'FIX-HUB-WHATSAPP-INBOX-TABLE-REPLY-CAN-CANCEL-ANOTHER-CUSTOMERS-RESERVATION';
const ANSWER = 'whatsapp_inbox/reservation_from_whatsapp';
const THANKS = 'Thanks for writing! Let me check the reservations book and I will come straight back to you.';
/** The day this spec books on, and how its slot and open day are known again (slots have no name). */
const BOOK = { day: madridDay(3), sentinel: 77, reason: 'E2E WhatsApp table cancel open' };
const DAY = BOOK.day;

test.beforeAll(keepPhoto);
const provider = answerSpec(() => bookingCleanUp(BOOK));
test.afterAll(restorePhoto);

for (const viewport of VIEWPORTS) {
  test(`WHATSAPP_INBOX-F25 a guest cancels their table by WhatsApp, and it is cancelled after the owner's yes at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      // The owner turns «Book a table» on (F15), the book open.
      await tablesAnswered(context, page, BOOK);

      // A guest with a card and a reservation at 21:00 for 4.
      const phone = e2ePhone();
      const { reservation } = await guestWithATable(context, DAY, { name: 'E2E Lucía', phone }, 4);
      const before = await reservationStatus(context, reservation);
      expect(['pending', 'confirmed']).toContain(before);

      // They write to cancel it; the provider's marker stands for the assistant's choice: cancel that reservation, as
      // the answer's instructions tell it, saying nothing of on whose behalf (the step fixes it).
      const asked = { id: reservation, reason: 'The guest asked by WhatsApp' };
      const message = await customerWrites(phone, `I can't make it, please cancel my table\nE2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`, 'E2E Lucía');
      const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);

      // The assistant was told their latest reservation, read by their number, and offered the cancellation; it
      // wanted it, and nothing is cancelled yet.
      const turn = await askedOnce(provider(), flowId);
      expect(JSON.stringify(turn.body)).toContain(`id ${reservation})`);
      const tools = ((turn.body as { tools?: { function: { name: string } }[] }).tools ?? []).map((tool) => tool.function.name);
      expect(tools).toContain('reservation__reservation__cancel');
      expect(inputsOf(turn.body, 'reservation__reservation__cancel')).not.toContain('on_behalf_of');
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('asking');
      expect(await reservationStatus(context, reservation)).toBe(before);
      expect(
        psql(`select body from whatsapp_inbox_message where conversation_id = '${message.conversation_id}' and direction = 'outbound'`),
      ).toBe(THANKS);

      // The owner finds the cancellation in «Waiting for your answer», naming the reservation by its guest, day and
      // time, never by its id.
      const question = await reservationsQuestion(page);
      await expect(question).toContainText('From «WhatsApp → table booked»');
      // The account is in English: Reservas says the reservation «E2E Lucía · Nov 2, 2026 · 9:00 PM».
      await expect(question).toContainText(`E2E Lucía · ${dayAsSaid(DAY)} · 9:00`);
      await expect(question).toContainText('On behalf of the customer: E2E Lucía');
      await expect(question).not.toContainText(reservation);
      await question.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);

      // «Approve» (the owner may cancel reservations, FLOW-F28): Reservas cancels it, and the assistant hears so.
      await approve(page, question);
      expect(await reservationStatus(context, reservation)).toBe('cancelled');
      const answered = chats(provider()).length;
      await workerAsks(flowId);
      expect(chats(provider())).toHaveLength(answered + 1);
      expect(JSON.stringify(provider().seen.at(-1)?.body)).toContain('"role":"tool"');
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
      await tablesAnswered(context, page, BOOK);

      // Marta's reservation at 21:00 for 2, on her card; Lucía, from another number and with no card yet, writes.
      const lucia = e2ePhone();
      let marta = e2ePhone();
      while (marta === lucia) marta = e2ePhone();
      const theirs = await guestWithATable(context, DAY, { name: 'E2E Marta', phone: marta }, 2);
      const before = await reservationStatus(context, theirs.reservation);

      // The assistant names Marta's reservation by its id and, as a model fooled by the message might, says it is on
      // Marta's behalf: the step puts Lucía's card over it.
      const asked = { id: theirs.reservation, on_behalf_of: theirs.card };
      const message = await customerWrites(lucia, `Cancel E2E Marta's table on Saturday\nE2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`, 'E2E Lucía');
      const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);

      await askedOnBehalfOfTheWriter(provider(), flowId);

      // The card says whose reservation it is and on whose behalf it would go: Lucía's, never Marta's.
      const question = await reservationsQuestion(page);
      await expect(question).toContainText(`E2E Marta · ${dayAsSaid(DAY)} · 9:00`);
      await expect(question).toContainText('On behalf of the customer: E2E Lucía');
      await expect(question).not.toContainText('On behalf of the customer: E2E Marta');
      await question.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${OTHER_KEY}-${viewport.label}`);

      // «Approve»: Reservas refuses it on Lucía's behalf, Marta's reservation is as it was and Lucía is told no.
      await approve(page, question);
      expect(await reservationStatus(context, theirs.reservation)).toBe(before);
      await workerAsks(flowId);
      expect(JSON.stringify(provider().seen.at(-1)?.body)).toContain('reservation.customer_mismatch');
      await expect.poll(() => psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('succeeded');
      expect(await reservationStatus(context, theirs.reservation)).toBe(before);
      expect(
        psql(
          `select body from whatsapp_inbox_message where conversation_id = '${message.conversation_id}' and direction = 'outbound' order by created_at desc, id desc limit 1`,
        ),
      ).toBe(NOT_DONE.en);
    } finally {
      await context.close();
    }
  });
}
