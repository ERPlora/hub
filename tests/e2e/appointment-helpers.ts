// What the e2e that book a real appointment through the apps' own APIs share (WHATSAPP_INBOX-F21, FLOW-F28): the day it
// goes on and how a spec takes away what it made.

/** A Monday five weeks ahead (inside the 90 days of advance and past any notice), as `YYYY-MM-DD`. */
export function aMonday(): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + ((8 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
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
