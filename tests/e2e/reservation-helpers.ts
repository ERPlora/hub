// What the e2e that book a real reservation through the apps' own APIs share: the business's day it goes on (hub `a`
// is in Madrid), the book open that day whatever the hours of the database, the reservation booked and read back, and
// how a spec of an automation that acts on reservations takes away what it made.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { emptyMonth } from './assistant-real';
import { cardDeletes } from './customer-helpers';
import { A, api, psql, shown } from './helpers';
import { post } from './service-helpers';

/** A day of the business and its weekday, Monday 0 (as the book's slots count). */
export interface BookingDay {
  date: string;
  weekday: number;
}

/** The business's day `days` from today (hub `a` is in Madrid). */
export function madridDay(days: number): BookingDay {
  const date = new Date(Date.now() + days * 86_400_000).toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' });
  return { date, weekday: (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7 };
}

/** `day` as Reservations says it to an account in English («Nov 2, 2026»). */
export const dayAsSaid = (day: BookingDay): string =>
  new Date(`${day.date}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });

/** How a spec opens the book: on `day`, with a slot whose maximum is `sentinel` and an open day said `reason`, by which it
 *  knows them again to clean them (slots have no name). */
export interface OpenBook {
  day: BookingDay;
  sentinel: number;
  reason: string;
}

/** The Reservations book open on the day of `book`, all day, whatever the hours of the database. */
export async function openTheBook(context: BrowserContext, book: OpenBook): Promise<void> {
  const slot = await api(context, A, 'POST', '/reservation/time_slots', { day_of_week: book.day.weekday, start_time: '00:00', end_time: '23:59', max_reservations: book.sentinel });
  expect(slot.status, JSON.stringify(slot.data)).toBe(201);
  const open = await api(context, A, 'POST', '/schedule/overrides', {
    start_date: book.day.date,
    end_date: book.day.date,
    reason: book.reason,
    is_closed: false,
    intervals: [{ open_time: '00:00', close_time: '00:00' }],
  });
  expect(open.status, JSON.stringify(open.data)).toBe(201);
}

/** How a spec books on the day of `book`: a real reservation of `guest` for two at 21:00, pending, on her `card` if she
 *  has one (with its phone), the book opened that day by the first one. Gives its id. */
export const bookingOn =
  (book: OpenBook) =>
  async (context: BrowserContext, guest: string, card?: { id: string; phone: string }): Promise<string> => {
    if (psql(`select count(*) from reservation_timeslot where max_reservations = ${book.sentinel}`) === '0') await openTheBook(context, book);
    const made = await post<{ id: string; status: string }>(context, '/reservation/reservations', {
      ...(card ? { customer_id: card.id } : {}),
      guest_name: guest,
      guest_phone: card?.phone ?? `6${String(Date.now()).slice(-8)}`,
      date: book.day.date,
      time: '21:00',
      party_size: 2,
    });
    expect(made.status).toBe('pending');
    return made.id;
  };

/** The Reservations book turned `ahead` days on from today, to `day`, and the row of `guest` in it. */
export async function guestRowInTheBook(page: Page, when: { ahead: number; day: BookingDay }, guest: string): Promise<Locator> {
  await page.goto('/reservation/reservations');
  const view = shown(page);
  for (let step = 0; step < when.ahead; step++) await view.locator('[data-testid=reservation-day-next]').click();
  await expect(view.locator('[data-testid=reservation-day]')).toHaveAttribute('data-day', when.day.date);
  return view.locator('[data-testid=reservation-list-row]', { hasText: guest });
}

/** The status of the reservation `id`, as Reservations reads it. */
export async function reservationStatus(context: BrowserContext, id: string): Promise<string> {
  const read = await api<{ status: string }>(context, A, 'GET', `/reservation/reservations/detail?id=${id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  return read.data.status;
}

/** What a spec of an automation that acts on reservations made, all named `<tag>…`: the automations (with their runs and
 *  questions), the reservations (with the tables they hold) and the cards, the book's slot `sentinel` and its open days;
 *  and the month's messages of the business `a`. */
export function cleanUpTagged(tag: string, sentinel: number): void {
  const flows = `select id from flow_flow where name like '${tag}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from table_hold where source_ref in (select id::text from reservation_reservation where guest_name like '${tag}%')`,
      `delete from reservation_reservation where guest_name like '${tag}%'`,
      ...cardDeletes(`select id from customer_customer where name like '${tag}%'`),
      `delete from reservation_timeslot where max_reservations = ${sentinel}`,
      `delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason like '${tag}%')`,
      `delete from schedule_override where reason like '${tag}%'`,
    ].join('; '),
  );
  emptyMonth();
}
