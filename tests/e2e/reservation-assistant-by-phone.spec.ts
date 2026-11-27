// Booking from the assistant for somebody who calls giving only her phone («me llama la del 6xx para mañana a las dos,
// son cuatro»): the card says the reservation is for the customer whose card has that number, by her name, then the day
// and the time, and «Ejecutar» books it under her card. With a phone no card has, no card comes up, no receipt is left
// and nothing is written down: the model hears whom the reservation is for is missing. In Spanish, at the three sizes.
// End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`).
// What this file creates is named «e2e.» and goes away before and after.
// flow: RESERVATION-F06 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { cardSpec, fieldsOf, VIEWPORTS } from './assistant-card-helpers';
import { ask, card, decide, lastAnswer, openPanelAtTheDesk, ownerIn, receipts } from './assistant-panel';
import { DONE, NOT_DONE } from './assistant-provider';
import { cleanUp as customersCleanUp, e2eName, PREFIX, spanishMobile } from './customer-helpers';
import { capture, psql } from './helpers';
import { post } from './service-helpers';

const NEEDED = ['customer', 'tax', 'sale', 'table', 'schedule', 'reservation'];
const TOOL = 'reservation__reservation__create';
/** The slot this file opens, told apart by its ceiling. */
const SENTINEL = 79;
const REASON = `${PREFIX}Reserva por teléfono`;
const AT = new Date(Date.now() + 86_400_000);
const TOMORROW = { date: AT.toISOString().slice(0, 10), weekday: (AT.getUTCDay() + 6) % 7 };

function cleanUp(): void {
  const cards = `select id from customer_customer where name like '${PREFIX}%'`;
  psql(
    [
      `delete from table_hold where source_ref in (select id::text from reservation_reservation where customer_id in (${cards}))`,
      `delete from reservation_reservation where customer_id in (${cards})`,
      `delete from reservation_timeslot where max_reservations = ${SENTINEL}`,
      `delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason = '${REASON}')`,
      `delete from schedule_override where reason = '${REASON}'`,
    ].join('; '),
  );
  customersCleanUp();
}

cardSpec(NEEDED, cleanUp);

/** Tomorrow open all day, in Schedules and in the book. */
async function openTomorrow(context: BrowserContext): Promise<void> {
  const day = { start_date: TOMORROW.date, end_date: TOMORROW.date, reason: REASON, is_closed: false };
  await post(context, '/schedule/overrides', { ...day, intervals: [{ open_time: '00:00', close_time: '00:00' }] });
  const slot = { day_of_week: TOMORROW.weekday, start_time: '00:00', end_time: '23:59', max_reservations: SENTINEL };
  await post(context, '/reservation/time_slots', slot);
}

/** What the model sends for «la del <phone> para mañana a las dos, son cuatro». */
const byPhone = (phone: string) => ({ guest_phone: phone, date: TOMORROW.date, time: '14:00', party_size: 4, source: 'phone' });

test('reservation-assistant-by-phone — the card names the customer the phone is of, and «Ejecutar» books it under her card', async ({
  browser,
}) => {
  const [context, page] = await ownerIn(browser, 'es');
  await openTomorrow(context);
  const name = e2eName('Lucía Gómez');
  const phone = spanishMobile();
  const lucia = await post<{ id: string }>(context, '/customer/customers', { name, phone });
  await openPanelAtTheDesk(page);

  const fields = await fieldsOf(page, TOOL, byPhone(phone));
  expect(fields.slice(0, 3).map((field) => field.name)).toEqual(['customer', 'date', 'time']);
  expect(fields[0].value).toBe(name);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`${name} · `);
    await capture(page, `reservation-by-phone-card-es-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText(DONE.es);
  const booked = `select count(*) from reservation_reservation where customer_id = '${lucia.id}' and guest_name = '${name}'`;
  expect(psql(booked)).toBe('1');
  await context.close();
});

test('reservation-assistant-by-phone — a phone no card has brings no card, no receipt and writes nothing down', async ({
  browser,
}) => {
  const [context, page] = await ownerIn(browser, 'es');
  await openTomorrow(context);
  const cards = psql('select count(*) from customer_customer');
  await openPanelAtTheDesk(page);

  await ask(page, `E2E-ASK ${TOOL} ${JSON.stringify(byPhone(spanishMobile()))}`);
  await expect(lastAnswer(page)).toContainText(NOT_DONE.es);
  await expect(card(page)).toBeHidden();
  await expect(receipts(page)).toHaveCount(0);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await capture(page, `reservation-by-phone-no-card-es-${vp.label}`);
  }
  expect(psql('select count(*) from customer_customer')).toBe(cards);
  expect(psql(`select count(*) from reservation_reservation where date = '${TOMORROW.date}' and time = '14:00'`)).toBe('0');
  await context.close();
});
