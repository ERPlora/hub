// An appointment that comes by WhatsApp, seen where the salon works: the Diary and the customer's card (hub#514;
// apps/whatsapp_inbox/WORKBOOK.md WHATSAPP_INBOX-F14, F21, F22; apps/customer/WORKBOOK.md CUSTOMER-F26). «Book
// appointments» is on offer in Automations' gallery and in WhatsApp's settings; the owner turns it on with the salon
// reviewing new appointments (F16). A customer with no card writes for a haircut at 10:00: she gets a card whose origin
// is WhatsApp, and after the owner's «Approve» in «Waiting for your answer», which says for whom, with whom and which
// service by its name (hub#835: it said «Services: 1 item»), the Diary shows it on its day, Pending. She then asks
// to come at 12:00 and, after the yes, the Diary shows the new time; then she cancels, and after the yes the Diary shows it Cancelled. Only one answer answers on the number: turning «Book
// a table» on says so and turns this one off.
// End to end with the real dependencies, as reservation-whatsapp.spec.ts does: the Hub of this stack, its SaaS's gateway
// and, behind it, the e2e's provider (assistant-provider.ts, started by this spec; the SaaS seeded with it, README «El
// asistente»). The provider's `E2E-ASK` marker stands for the assistant's choice; whose card it goes on and that she
// herself asks are fixed by the answer's step, never by the assistant.
// flow: WHATSAPP_INBOX-F14 WHATSAPP_INBOX-F16 WHATSAPP_INBOX-F21 WHATSAPP_INBOX-F22 CUSTOMER-F26 FLOW-F33 APPOINTMENT-F18
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { aMonday, salonCleanUp } from './appointment-helpers';
import { emptyMonth } from './assistant-real';
import { cardDeletes } from './customer-helpers';
import { confirmDialog, parkedEvent, signedIn } from './flow-helpers';
import { capture, psql, shown } from './helpers';
import { chats, relay } from './provider-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { post } from './service-helpers';
import { answerSpec, customerWrites } from './whatsapp-answer-helpers';
import { cleanUp as inboxCleanUp, e2ePhone, keepPhoto, restorePhoto } from './whatsapp-helpers';

const TASK = 'FIX-HUB-WHATSAPP-INBOX-OFFER-BOOK-APPOINTMENTS';
const ANSWER = 'whatsapp_inbox/appointment_from_whatsapp';
const NOTICE = 'whatsapp_inbox/appointment_confirmed';
const THANKS = 'Thanks for writing! Let me check the diary and I will come straight back to you.';
const TAG = 'E2E WaAppt';
const CUSTOMER = `${TAG} Marta`;
const DAY = aMonday();

/** The inbox's answers and notices (with their runs and questions), this spec's appointments, cards, service,
 *  professional and open day, the conversations and channel of the inbox's specs, and the month's messages of `a`. */
function cleanUp(): void {
  const flows = "select id from flow_flow where recipe like 'whatsapp_inbox/%'";
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      ...salonCleanUp(TAG),
    ].join('; '),
  );
  inboxCleanUp();
  psql(cardDeletes(`select id from customer_customer where name like '${TAG}%'`).join('; '));
  emptyMonth();
}

test.beforeAll(keepPhoto);
const provider = answerSpec(cleanUp);
test.afterAll(restorePhoto);

/** The salon: a haircut Bea performs, on `DAY` open from 09:00 to 18:00, reviewing every appointment a customer books
 *  herself (F16), through each app's own API. */
async function theSalon(context: BrowserContext, stamp: string): Promise<{ service: { id: string; name: string }; member: { id: string; full_name: string } }> {
  const service = await post<{ id: string; name: string }>(context, '/service/services', {
    name: `${TAG} Haircut ${stamp}`,
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', { first_name: `${TAG} Bea ${stamp}`, last_name: 'Stylist' });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  await post(context, '/schedule/special_days', {
    date: DAY,
    name: `${TAG} open`,
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '18:00' }],
  });
  await post(context, '/appointment/settings', { auto_confirm_online: false }, 200);
  return { service, member };
}

/** She writes `text` from `phone`: the relay starts the answer, which asks the assistant; what it wants waits in «Waiting
 *  for your answer», saying `says`, until the owner's «Approve», and then the assistant hears what Citas answered. */
async function askAndApprove(page: Page, phone: string, text: string, viewport: string, says: string[], shot?: string): Promise<void> {
  await customerWrites(phone, text, CUSTOMER);
  const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);
  const before = chats(provider()).length;
  await relay(parkedEvent(flowId));
  expect(chats(provider())).toHaveLength(before + 1);

  await page.goto('/flow/automations');
  const question = shown(page)
    .locator('[data-testid=flow-inbox] article')
    .filter({ hasText: 'The assistant wants to change something in «Appointments»' });
  await expect(question).toBeVisible();
  for (const word of says) await expect(question).toContainText(word);
  await expect(question).not.toContainText(/[0-9a-f]{8}-[0-9a-f]{4}-/);
  if (shot) {
    await question.scrollIntoViewIfNeeded();
    await noHorizontalScroll(page, viewport);
    await settled(page);
    await capture(page, shot);
  }
  await question.locator('[data-testid^=flow-question-yes-]').click();
  await expect(page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
  await expect(question).toHaveCount(0);
  const answered = chats(provider()).length;
  await relay(parkedEvent(flowId));
  expect(chats(provider()), `${viewport}: the assistant heard what Citas answered`).toHaveLength(answered + 1);
  expect(JSON.stringify(provider().seen.at(-1)?.body)).toContain('"role":"tool"');
}

/** The Diary on `DAY`, and her appointment's row in it. */
async function diaryRow(page: Page, id: string) {
  await page.goto('/appointment/agenda');
  const view = shown(page);
  const calendar = view.locator('[data-testid=appointment-toolbar-calendar] input');
  await calendar.fill(DAY);
  await calendar.press('Tab');
  await expect(view.locator('[data-testid=appointment-toolbar-date]')).not.toBeEmpty();
  return view.locator(`[data-testid=appointment-list-row][data-id="${id}"]`).first();
}

for (const viewport of VIEWPORTS) {
  test(`WHATSAPP_INBOX-F14 F21 F22 CUSTOMER-F26 «Book appointments»: a new customer gets her card from WhatsApp and her appointment after the owner's yes, at ${viewport.label}`, async ({ browser }) => {
    // Three requests, each three ticks of the relay (a `manage.py shell` of its own) and a turn of the assistant.
    test.setTimeout(900_000);
    const stamp = `${viewport.label}${Date.now().toString(36)}`;
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    try {
      const { service, member } = await theSalon(context, stamp);

      // FLOW-F33: on offer in Automations' gallery, «Comes with WhatsApp inbox».
      await expect(shown(page).locator(`[data-testid="flow-recipe-${ANSWER}"]`)).toContainText('WhatsApp → appointment booked');

      // F14: in WhatsApp's settings the card says what it does; on, after a question, with its notice.
      await page.goto('/whatsapp_inbox/settings');
      const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-appointments]');
      await expect(card).toContainText('Book appointments');
      await expect(card).toContainText('checks the free times');
      await expect(card).toContainText('Off');
      await card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-on]').click();
      await confirmDialog(page, 'Book appointments');
      await expect(card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-done]')).toHaveText(
        'Done. Write to yourself from another phone: “I want an appointment tomorrow”.',
      );
      await expect(card).toContainText('On');
      for (const ref of [ANSWER, NOTICE]) {
        expect(psql(`select enabled::text from flow_flow where recipe = '${ref}'`)).toBe('true');
      }
      // F16: how they confirm is Citas' own rule, read from it.
      await expect(card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-confirm] ion-radio')).toHaveCount(2);
      await expect(card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-review]')).toHaveText(
        'Each new appointment waits for you in the Diary with “Confirm”.',
      );
      await card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-off]').scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-settings-${viewport.label}`);

      // F21, CUSTOMER-F26: she has no card yet and asks for a haircut at 10:00; the card is made before the assistant is
      // asked, and the booking waits saying for whom, with whom and which service (hub#835).
      const phone = e2ePhone();
      const booking = { services: [{ service_id: service.id }], staff_id: member.id, start: `${DAY}T10:00` };
      await askAndApprove(
        page,
        phone,
        `A haircut at 10:00, please\nE2E-ASK appointment__appointment__create ${JSON.stringify(booking)}`,
        viewport.label,
        [CUSTOMER, member.full_name, `Services: ${service.name}`],
        `${TASK}-question-${viewport.label}`,
      );
      expect(psql(`select name || ' ' || source from customer_customer where phone = '${phone}'`)).toBe(`${CUSTOMER} whatsapp`);
      const cardId = psql(`select id from customer_customer where phone = '${phone}'`);
      const id = psql(`select id from appointment_appointment where customer_id = '${cardId}'`);
      expect(psql(`select source || ' ' || status || ' ' || customer_phone from appointment_appointment where id = '${id}'`)).toBe(`whatsapp pending ${phone}`);
      expect(psql(`select count(*) from whatsapp_inbox_message where body = '${THANKS}'`)).toBe('1');

      // Her card, with its origin, in Customers.
      await page.goto(`/customer/customers/${cardId}`);
      await expect(shown(page).locator('[data-testid=customer-facts]')).toContainText('WhatsApp');
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-card-${viewport.label}`);

      // In the Diary, on its day and at its time, waiting for the salon.
      const row = await diaryRow(page, id);
      await expect(row).toContainText('10:00');
      await expect(row).toContainText('Pending');
      await expect(row).toContainText(CUSTOMER);
      await row.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-diary-${viewport.label}`);

      // F22: she asks to come at 12:00; after the yes, the Diary shows the new time, with the same professional.
      const move = { id, start: `${DAY}T12:00` };
      await askAndApprove(page, phone, `Can I come at 12:00?\nE2E-ASK appointment__appointment__reschedule ${JSON.stringify(move)}`, viewport.label, [CUSTOMER]);
      const moved = await diaryRow(page, id);
      await expect(moved).toContainText('12:00');
      await expect(moved).not.toContainText('10:00');
      expect(psql(`select staff_id from appointment_appointment where id = '${id}'`)).toBe(member.id);

      // F22: she cannot come; after the yes, the Diary shows it cancelled, by her.
      const cancel = { id, reason: 'She asked by WhatsApp' };
      await askAndApprove(page, phone, `I can't make it, please cancel\nE2E-ASK appointment__appointment__cancel ${JSON.stringify(cancel)}`, viewport.label, [CUSTOMER]);
      expect(psql(`select status || ' ' || cancelled_by_customer::text from appointment_appointment where id = '${id}'`)).toBe('cancelled true');
      await page.goto('/whatsapp_inbox/settings');

      // Only one answer answers on the number: «Book a table» says so, and this one goes off with its notice.
      const tables = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-tables]');
      await tables.locator('[data-testid=whatsapp-inbox-autoreply-tables-on]').click();
      await confirmDialog(page, 'Book a table', async () => {
        await expect(page.locator('ion-modal.ep-form-modal').filter({ hasText: 'Book a table' })).toContainText(
          'Only one automatic answer can answer on your number: turning this one on turns «Book appointments» off.',
        );
      });
      await expect(tables).toContainText('On');
      const appointments = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-appointments]');
      await expect(appointments).toContainText('Off');
      await expect(appointments.locator('[data-testid=whatsapp-inbox-autoreply-appointments-on]')).toBeVisible();
      for (const ref of [ANSWER, NOTICE]) {
        expect(psql(`select enabled::text from flow_flow where recipe = '${ref}'`)).toBe('false');
      }
      await noHorizontalScroll(page, viewport.label);
    } finally {
      await context.close();
    }
  });
}
