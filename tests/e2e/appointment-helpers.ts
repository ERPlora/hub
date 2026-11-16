// What the e2e that book a real appointment through the apps' own APIs share (WHATSAPP_INBOX-F21, FLOW-F28): the day it
// goes on, the salon it is booked in and how a spec takes away what it made.
import type { BrowserContext } from '@playwright/test';

import { post } from './service-helpers';

/** A Monday five weeks ahead (inside the 90 days of advance and past any notice), as `YYYY-MM-DD`. */
export function aMonday(): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + ((8 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}

/** A cut (`<tag> Corte`) that a professional (`<tag> Ana <lastName>`) performs, and `day` open from 09:00 to 18:00, through
 *  each app's own API: what a booking needs. `salonCleanUp(tag)` takes it away. */
export async function openForACut(
  context: BrowserContext,
  tag: string,
  day: string,
  lastName = 'López',
): Promise<{ service: { id: string; name: string }; member: { id: string; full_name: string } }> {
  const service = await post<{ id: string; name: string }>(context, '/service/services', {
    name: `${tag} Corte`,
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', {
    first_name: `${tag} Ana`,
    last_name: lastName,
  });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  await post(context, '/schedule/special_days', {
    date: day,
    name: `${tag} Abierto`,
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '18:00' }],
  });
  return { service, member };
}

/** The statements that delete the appointments of the customers a spec named with `tag`, and the open day, the services
 *  and the professionals it named the same way. Its customers stay the spec's: it knows what else it left on them. */
export function salonCleanUp(tag: string): string[] {
  const customers = `select id from customer_customer where name like '${tag}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  const services = `select id from service_service where name like '${tag}%'`;
  const members = `select id from staff_member where first_name like '${tag}%'`;
  return [
    `delete from appointment_history where appointment_id in (${appointments})`,
    `delete from appointment_appointmentservice where appointment_id in (${appointments})`,
    `delete from appointment_appointment where id in (${appointments})`,
    `delete from schedule_specialdayinterval where special_day_id in (select id from schedule_specialday where name like '${tag}%')`,
    `delete from schedule_specialday where name like '${tag}%'`,
    `delete from service_assignment where service_id in (${services}) or member_id in (${members})`,
    `delete from service_service where name like '${tag}%'`,
    `delete from staff_member where first_name like '${tag}%'`,
  ];
}
