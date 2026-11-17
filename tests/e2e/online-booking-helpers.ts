// What the Online booking specs share: the cast through each app's own API (a service a professional performs, a day
// Schedules opens and the booking page on), a Monday far enough ahead, the clean-up of a spec's rows by the name they
// carry, and the settings of Appointments and of the page read before a spec and put back after it.
import { type Browser, type BrowserContext, expect } from '@playwright/test';

import { A, api, psql } from './helpers';
import { ownerPage, post } from './service-helpers';

/** A Monday `weeks` + five weeks ahead (inside the 90 days of advance), as `YYYY-MM-DD` of the business. */
export function aMonday(weeks: number): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + 7 * weeks + ((8 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}

/** Removes every row a spec named `tag…`: its bookings and appointments, customers, services, staff and open days. */
export function cleanUp(tag: string): void {
  const customers = `select id from customer_customer where name like '${tag}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  const services = `select id from service_service where name like '${tag}%'`;
  const members = `select id from staff_member where first_name like '${tag}%'`;
  psql(
    [
      `delete from online_booking_booking where appointment_id in (${appointments})`,
      `delete from appointment_history where appointment_id in (${appointments})`,
      `delete from appointment_appointmentservice where appointment_id in (${appointments})`,
      `delete from appointment_appointment where id in (${appointments})`,
      `delete from schedule_specialdayinterval where special_day_id in (select id from schedule_specialday where name like '${tag}%')`,
      `delete from schedule_specialday where name like '${tag}%'`,
      `delete from service_assignment where service_id in (${services}) or member_id in (${members})`,
      `delete from service_service where name like '${tag}%'`,
      `delete from staff_member where first_name like '${tag}%'`,
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${tag}%'`,
    ].join('; '),
  );
}

/** The diary's rules the page's settings also change: put back with Appointments' settings, not the page's. */
const RULES = ['min_booking_notice', 'max_advance_booking', 'slot_interval', 'auto_confirm_online', 'allow_customer_cancellation', 'cancellation_notice_hours'];

/** What the business had before a spec: the rules of Appointments and the page's own settings. */
export interface Settings {
  rules: Record<string, unknown>;
  page: Record<string, unknown>;
}

export async function readSettings(browser: Browser): Promise<Settings> {
  const { context } = await ownerPage(browser, '/online_booking/bookings');
  try {
    const rules = await api<Record<string, unknown>>(context, A, 'GET', '/appointment/settings');
    const page = await api<Record<string, unknown>>(context, A, 'GET', '/online_booking/settings');
    expect([rules.status, page.status]).toEqual([200, 200]);
    return {
      rules: Object.fromEntries(Object.entries(rules.data).filter(([key]) => key !== 'timezone')),
      page: Object.fromEntries(Object.entries(page.data).filter(([key]) => key !== 'timezone' && !RULES.includes(key))),
    };
  } finally {
    await context.close();
  }
}

export async function putBack(browser: Browser, saved: Settings | null): Promise<void> {
  if (!saved) return;
  const { context } = await ownerPage(browser, '/online_booking/bookings');
  try {
    await post(context, '/appointment/settings', saved.rules, 200);
    await post(context, '/online_booking/settings', saved.page, 200);
  } finally {
    await context.close();
  }
}

export interface Cast {
  service: { id: string; name: string };
  member: { id: string; full_name: string };
}

/** The cast through each app's own API: a service a professional performs, `day` open, the page on (bookings wait
 *  for the business to confirm them, and the customer may cancel up to 24 h before). `named` names each row. */
export async function cast(context: BrowserContext, named: (label: string) => string, label: string, day: string): Promise<Cast> {
  const service = await post<{ id: string; name: string }>(context, '/service/services', {
    name: named(`Haircut ${label}`),
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', { first_name: named(`Ana ${label}`), last_name: 'Stylist' });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  await post(context, '/schedule/special_days', {
    date: day,
    name: named(`Open ${label}`),
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '18:00' }],
  });
  await post(context, '/online_booking/settings', { is_enabled: true, auto_confirm_online: false, allow_customer_cancellation: true, cancellation_notice_hours: 24 }, 200);
  return { service, member };
}
