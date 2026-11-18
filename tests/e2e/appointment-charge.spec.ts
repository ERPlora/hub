// «Charge» from the agenda to the till, in Chrome (WORKBOOK APPOINTMENT-F17, SALE-F26): an appointment of
// a professional who does the haircut at her own price (Services · «Who does it») is charged from its row;
// the till opens with that check on screen — titled «customer · number», its service line at the price
// booked, not the catalog's — and back on the agenda the row says «Go to the check», which returns to the
// same check (one per appointment). Everything is named «E2E Apt Charge …» and removed before and after.
import { expect, test } from '@playwright/test';

import { A, psql, shot, shown } from './helpers';
import { ownerPage, post, rowAction } from './service-helpers';

const TAG = 'E2E Apt Charge';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;

/** A Tuesday five weeks ahead, as `YYYY-MM-DD` of the business. */
function aTuesday(): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + ((9 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}
const DAY = aTuesday();

function cleanUp(): void {
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  const orders = `select id from sale_order where appointment_id in (${appointments})`;
  const services = `select id from service_service where name like '${TAG}%'`;
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
      `delete from sale_orderline where order_id in (${orders})`,
      `delete from sale_order where id in (${orders})`,
      `delete from appointment_history where appointment_id in (${appointments})`,
      `delete from appointment_appointmentservice where appointment_id in (${appointments})`,
      `delete from appointment_appointment where id in (${appointments})`,
      `delete from schedule_specialdayinterval where special_day_id in (select id from schedule_specialday where name like '${TAG}%')`,
      `delete from schedule_specialday where name like '${TAG}%'`,
      `delete from service_assignment where service_id in (${services}) or member_id in (${members})`,
      `delete from service_service where name like '${TAG}%'`,
      `delete from staff_member where first_name like '${TAG}%'`,
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('«Charge» ends on the till with the appointment’s check, at the price booked, and «Go to the check» returns to it', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/appointment/agenda');
  try {
    const customer = await post<{ id: string; name: string }>(context, '/customer/customers', {
      name: named('Marta'),
      phone: `6${String(Date.now()).slice(-8)}`,
    });
    const service = await post<{ id: string }>(context, '/service/services', {
      name: named('Haircut'),
      price: 2000,
      duration_minutes: 30,
      tax_category_key: 'service.generic',
    });
    const member = await post<{ id: string }>(context, '/staff/members', { first_name: named('Ana'), last_name: 'Senior' });
    // Ana does the haircut at her own price: €30.00, not the catalog's €20.00.
    await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id, custom_price: 3000 }, 200);
    await post(context, '/schedule/special_days', {
      date: DAY,
      name: named('Open'),
      is_closed: false,
      intervals: [{ open_time: '09:00', close_time: '18:00' }],
    });
    const booked = await post<{ id: string; number: string; total: number }>(context, '/appointment/appointments', {
      customer_id: customer.id,
      services: [{ service_id: service.id }],
      staff_id: member.id,
      start: `${DAY}T10:00`,
    });
    expect(booked.total).toBe(3000);

    const calendar = shown(page).locator('[data-testid=appointment-toolbar-calendar] input');
    await calendar.fill(DAY);
    await calendar.press('Tab');
    await rowAction(page, 'appointment-list', booked.id, 'charge');
    await page.waitForURL(/\/sale\/pos\?order=/);
    const orderId = new URL(page.url()).searchParams.get('order');
    const till = shown(page);
    await expect(till.locator('[data-testid=pos-check-title]')).toHaveValue(`${customer.name} · ${booked.number}`);
    const lineId = psql(`select id from sale_orderline where order_id = '${orderId}'`);
    await expect(till.locator(`[data-testid=pos-line-${lineId}]`)).toContainText(named('Haircut'));
    await expect(till.locator('[data-testid=pos-total]')).toContainText('30.00');
    await page.screenshot({ path: shot('appointment-charge-till') });

    // Back on the agenda: «Go to the check» returns to the same one.
    await page.goto(`${A}/appointment/agenda`);
    await calendar.fill(DAY);
    await calendar.press('Tab');
    await expect(shown(page).locator(`[data-testid=appointment-list-row-${booked.id}-charge]`)).toContainText('Go to the check');
    await rowAction(page, 'appointment-list', booked.id, 'charge');
    await page.waitForURL(new RegExp(`/sale/pos\\?order=${orderId}`));
    await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(`${customer.name} · ${booked.number}`);
    expect(psql(`select count(*) from sale_order where appointment_id = '${booked.id}'`)).toBe('1');
  } finally {
    await context.close();
  }
});
