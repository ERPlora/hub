// Appointments → Agenda in Chrome (WORKBOOK APPOINTMENT-F01 to F05, F12, F17, F20, F27), with the real
// Customers, Services, Staff, Schedules and Sales apps: a customer card of Customers, a service of
// Services that a professional of Staff performs, a day Schedules opens. The owner books from «Add
// appointment» with a free time; with overlaps off, the same time is refused (server and screen); «By
// professional» paints the block and a drag moves it one hour; the week board shows it; cancelling asks
// first; «Charge» opens the check in the till; the series and the customer's «Visit history» show what was
// booked. Each screen is captured in three viewports. Everything is named «E2E Apt …» and removed before
// and after; the settings of Citas are read first and put back by API at the end.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { ownerPage, pick, post, rowAction, VIEWPORTS } from './service-helpers';

const TAG = 'E2E Apt';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;

/** A Monday five weeks ahead (inside the 90 days of advance), as `YYYY-MM-DD` of the business. */
function aMonday(): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + ((8 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}
const DAY = aMonday();

function cleanUp(): void {
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  const series = `select id from appointment_recurring where customer_id in (${customers})`;
  const services = `select id from service_service where name like '${TAG}%'`;
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  const orders = `select id from sale_order where appointment_id in (${appointments})`;
  psql(
    [
      `delete from sale_orderline where order_id in (${orders})`,
      `delete from sale_order where id in (${orders})`,
      `delete from appointment_history where appointment_id in (${appointments})`,
      `delete from appointment_appointmentservice where appointment_id in (${appointments})`,
      `delete from appointment_appointment where id in (${appointments})`,
      `delete from appointment_recurringservice where recurring_id in (${series})`,
      `delete from appointment_recurring where id in (${series})`,
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

/** The business's own settings of Citas, kept before the spec turns overlaps off and put back after. */
let savedSettings: Record<string, unknown> | null = null;

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/appointment/agenda');
  try {
    const current = await api<Record<string, unknown>>(context, A, 'GET', '/appointment/settings');
    expect(current.status).toBe(200);
    // The zone is the business's, not a setting of Citas.
    savedSettings = Object.fromEntries(Object.entries(current.data).filter(([key]) => key !== 'timezone'));
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  cleanUp();
  if (!savedSettings) return;
  const { context } = await ownerPage(browser, '/appointment/agenda');
  try {
    await post(context, '/appointment/settings', savedSettings, 200);
  } finally {
    await context.close();
  }
});

interface Cast {
  customer: { id: string; name: string };
  service: { id: string; name: string };
  member: { id: string; full_name: string };
}

/** The cast through each app's own API: a card, a service a professional performs, and an open day. */
async function cast(context: BrowserContext): Promise<Cast> {
  const phone = `6${String(Date.now()).slice(-8)}`;
  const customer = await post<{ id: string; name: string }>(context, '/customer/customers', { name: named('Lucía'), phone });
  const service = await post<{ id: string; name: string }>(context, '/service/services', {
    name: named('Haircut'),
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', { first_name: named('Ana'), last_name: 'Stylist' });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  await post(context, '/schedule/special_days', {
    date: DAY,
    name: named('Open'),
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '18:00' }],
  });
  return { customer, service, member };
}

async function goToDay(page: Page): Promise<void> {
  const calendar = shown(page).locator('[data-testid=appointment-toolbar-calendar] input');
  await calendar.fill(DAY);
  await calendar.press('Tab');
  await expect(shown(page).locator('[data-testid=appointment-toolbar-date]')).not.toBeEmpty();
}

async function fillBooking(page: Page, who: Cast): Promise<void> {
  const form = page.locator('ion-modal[data-testid=appointment-form]');
  await form.locator('[data-testid=customer-search-trigger]').click();
  const search = page.locator('ion-modal[data-testid=customer-search-modal]');
  await search.locator('[data-testid=customer-picker-search] input').fill(who.customer.name);
  await search.locator(`[data-testid=customer-picker-result-${who.customer.id}]`).click();
  await expect(search).toBeHidden();
  await pick(page, 'appointment-form-service-add', who.service.name.split(' ')[2], who.service.name);
  await pick(page, 'appointment-form-staff', who.member.full_name.split(' ')[2], who.member.full_name);
  const day = form.locator('[data-testid=appointment-form-day] input');
  await day.fill(DAY);
  await day.press('Tab');
}

test('Agenda: book with a free time, an overlap refused, the grid and the week, drag, cancel, charge, series and the card', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/appointment/agenda');
  let who!: Cast;
  try {
    who = await cast(context);
    await goToDay(page);
    const view = shown(page);
    await view.locator('[data-testid=appointment-list-empty], [data-testid=appointment-list-row]').first().waitFor({ state: 'visible' });

    // «Add appointment»: the customer from Customers, the service from Services, its professional, a free time.
    await view.locator('[data-testid=appointment-list-add]').click();
    await fillBooking(page, who);
    const free = page.locator('[data-testid=appointment-slots-time]', { hasText: /^10:00\s?AM$/ });
    await expect(free).toBeVisible();
    await page.screenshot({ path: shot('appointment-new') });
    await free.click();
    await page.locator('[data-testid=appointment-form-submit]').click();
    const row = view.locator('[data-testid=appointment-list-row]', { hasText: who.customer.name });
    await expect(row).toContainText('Confirmed');
    await expect(row).toContainText(who.member.full_name);
    const appointment = JSON.parse(
      psql(`select row_to_json(a) from appointment_appointment a where customer_id = '${who.customer.id}'`),
    ) as { id: string; number: string };
    await page.screenshot({ path: shot('appointment-list-desktop') });

    // With overlaps off, the same time of the same professional is refused: by the server and on screen.
    await post(context, '/appointment/settings', { allow_overlapping: false }, 200);
    const clash = await api<{ error: { code: string } }>(context, A, 'POST', '/appointment/appointments', {
      customer_id: who.customer.id,
      services: [{ service_id: who.service.id }],
      staff_id: who.member.id,
      start: `${DAY}T10:15`,
    });
    expect([clash.status, clash.data.error.code]).toEqual([409, 'appointment.slot_taken']);
    await view.locator('[data-testid=appointment-list-add]').click();
    await fillBooking(page, who);
    await page.locator('[data-testid=appointment-form-time] input').fill('10:15');
    await page.locator('[data-testid=appointment-form-submit]').click();
    await expect(page.locator('[data-testid=appointment-form-error]')).toContainText('already has an appointment at that time');
    await page.screenshot({ path: shot('appointment-overlap-refused') });
    await page.locator('[data-testid=appointment-form-cancel]').click();

    // «By professional»: the professional's row with the block; a drag moves it one hour.
    await view.locator('[data-testid=appointment-toolbar-view-staff]').click();
    await expect(view.locator('[data-testid=appointment-toolbar-view-staff]')).toHaveClass(/segment-button-checked/);
    const lane = view.locator(`[data-testid=appointment-grid-lane][data-lane="${who.member.id}"]`);
    const block = lane.locator(`[data-testid=appointment-grid-appointment][data-id="${appointment.id}"]`);
    await expect(block).toContainText(who.customer.name);
    await page.screenshot({ path: shot('appointment-grid-desktop'), animations: 'disabled' });
    const box = (await block.boundingBox())!;
    await page.mouse.move(box.x + 10, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + 60, box.y + box.height / 2, { steps: 5 });
    await page.mouse.move(box.x + 106, box.y + box.height / 2, { steps: 5 });
    await page.mouse.up();
    await expect
      .poll(() => psql(`select to_char(start at time zone 'Europe/Madrid', 'HH24:MI') from appointment_appointment where id = '${appointment.id}'`))
      .toBe('11:00');
    await expect(view.locator('[data-testid=appointment-agenda-notice]')).toContainText('Appointment moved.');

    // «Week»: the week board, the appointment on its day.
    await view.locator('[data-testid=appointment-toolbar-span-week]').click();
    await expect(view.locator('[data-testid=appointment-toolbar-span-week]')).toHaveClass(/segment-button-checked/);
    const cell = view.locator(`[data-testid=appointment-week-cell][data-lane="${who.member.id}"][data-day="${DAY}"]`);
    await expect(cell).toContainText(who.customer.name);
    await expect(cell).toContainText(/11:00\s?AM/);
    // The segment's indicator slides to «Week»: the shot finishes that transition first.
    await page.screenshot({ path: shot('appointment-week-desktop'), animations: 'disabled' });
    await view.locator('[data-testid=appointment-toolbar-span-day]').click();
    await view.locator('[data-testid=appointment-toolbar-view-list]').click();

    // «Charge»: a second appointment, charged at the till: the check opens with the appointment and a
    // service line of the service (SALE-F38), so a voucher could pay it.
    const second = await post<{ id: string; number: string }>(context, '/appointment/appointments', {
      customer_id: who.customer.id,
      services: [{ service_id: who.service.id }],
      staff_id: who.member.id,
      start: `${DAY}T15:00`,
    });
    await rowAction(page, 'appointment-list', second.id, 'charge');
    await page.waitForURL(/\/sale\/pos\?order=/);
    expect(psql(`select label from sale_order where appointment_id = '${second.id}'`)).toBe(`${who.customer.name} · ${second.number}`);
    expect(
      psql(`select l.service_id from sale_orderline l join sale_order o on o.id = l.order_id where o.appointment_id = '${second.id}'`),
    ).toBe(who.service.id);
    await page.goto(`${A}/appointment/agenda`);
    await goToDay(page);
    // While its check is open, «Charge» is «Go to the check» and goes back to the same one.
    await expect(view.locator(`[data-testid=appointment-list-row-${second.id}-charge]`)).toContainText('Go to the check');
    await rowAction(page, 'appointment-list', second.id, 'charge');
    await page.waitForURL(/\/sale\/pos\?order=/);
    expect(psql(`select count(*) from sale_order where appointment_id = '${second.id}'`)).toBe('1');
    await page.goto(`${A}/appointment/agenda`);
    await goToDay(page);

    // «Cancel» asks first, with the reason; the appointment stays, cancelled.
    await rowAction(page, 'appointment-list', appointment.id, 'cancel');
    const cancel = page.locator('ion-modal[data-testid=appointment-cancel]');
    await expect(cancel).toContainText(`Cancel ${who.customer.name}'s appointment`);
    await cancel.locator('[data-testid=appointment-cancel-reason] textarea').fill('Ill');
    await cancel.locator('[data-testid=appointment-cancel-submit]').click();
    await expect(shown(page).locator(`[data-testid=appointment-list-row][data-id="${appointment.id}"]`)).toContainText('Cancelled');
    expect(psql(`select cancellation_reason from appointment_appointment where id = '${appointment.id}'`)).toBe('Ill');

    // «Repeating»: a series of two, booked by the API, in its table.
    await post(context, '/appointment/recurring', {
      customer_id: who.customer.id,
      services: [{ service_id: who.service.id }],
      staff_id: who.member.id,
      frequency: 'weekly',
      start_date: DAY,
      time: '16:00',
      max_occurrences: 2,
    });
    await shown(page).locator('[data-testid=appointment-toolbar-view-series]').click();
    await expect(shown(page).locator('[data-testid=appointment-series-row]', { hasText: who.customer.name })).toContainText(
      'After 2 appointments',
    );
    await page.screenshot({ path: shot('appointment-series-desktop') });

    // The customer's card in Customers: «Visit history».
    await page.goto(`${A}/customer/customers/${who.customer.id}`);
    await expect(shown(page).locator('[data-testid=appointment-visits]')).toContainText('Visit history');
    await expect(shown(page).locator('[data-testid=appointment-visit]').first()).toBeVisible();
    await page.screenshot({ path: shot('appointment-customer-card') });
  } finally {
    await context.close();
  }

  // The same agenda on a tablet and on a phone.
  for (const [name, viewport] of Object.entries(VIEWPORTS).filter(([key]) => key !== 'desktop')) {
    const { context: small, page: device } = await ownerPage(browser, '/appointment/agenda', viewport);
    try {
      await goToDay(device);
      await expect(shown(device).getByText(who.customer.name).first()).toBeVisible();
      await device.screenshot({ path: shot(`appointment-list-${name}`) });
      await shown(device).locator('[data-testid=appointment-toolbar-view-staff]').click();
      await expect(shown(device).locator('[data-testid=appointment-grid]')).toBeVisible();
      await device.screenshot({ path: shot(`appointment-grid-${name}`), animations: 'disabled' });
    } finally {
      await small.close();
    }
  }
});
