// Online booking in Chrome (hidden; WORKBOOK ONLINE_BOOKING-F01, F02, F05, F07, F08, F10, F11), with the real
// Appointments, Customers, Services, Staff and Schedules apps: a service of Services that a professional of
// Staff performs and a day Schedules opens. In the dev preview of the public page a customer books (no
// preference of professional, a free time, name and mobile); with manual confirmation the booking lands
// pending in the inbox and in the agenda, and her card is created in Customers by her mobile. The inbox
// confirms it; her link shows it confirmed and cancels it, and the inbox follows live. The settings save the
// page's fields. Each screen is captured in three viewports. Everything is named «E2E OB …» and removed before
// and after; the settings of Appointments and of this app are read first and put back by API at the end.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { ownerPage, post, rowAction, VIEWPORTS } from './service-helpers';

const TAG = 'E2E OB';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;
/** A Spanish mobile unique to the run (`6` + eight digits). */
const MOBILE = `6${String(Date.now()).slice(-8)}`;

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
  const services = `select id from service_service where name like '${TAG}%'`;
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
      `delete from online_booking_booking where appointment_id in (${appointments})`,
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

/** What the business had, put back at the end: the rules of Appointments and the page's settings. */
let savedRules: Record<string, unknown> | null = null;
let savedPage: Record<string, unknown> | null = null;
const RULES = ['min_booking_notice', 'max_advance_booking', 'slot_interval', 'auto_confirm_online', 'allow_customer_cancellation', 'cancellation_notice_hours'];

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/online_booking/bookings');
  try {
    const rules = await api<Record<string, unknown>>(context, A, 'GET', '/appointment/settings');
    const page = await api<Record<string, unknown>>(context, A, 'GET', '/online_booking/settings');
    expect([rules.status, page.status]).toEqual([200, 200]);
    savedRules = Object.fromEntries(Object.entries(rules.data).filter(([key]) => key !== 'timezone'));
    savedPage = Object.fromEntries(Object.entries(page.data).filter(([key]) => key !== 'timezone' && !RULES.includes(key)));
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/online_booking/bookings');
  try {
    if (savedRules) await post(context, '/appointment/settings', savedRules, 200);
    if (savedPage) await post(context, '/online_booking/settings', savedPage, 200);
  } finally {
    await context.close();
  }
});

interface Cast {
  service: { id: string; name: string };
  member: { id: string; full_name: string };
}

/** The cast through each app's own API: a service a professional performs, an open day, the page on. */
async function cast(context: BrowserContext): Promise<Cast> {
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
  await post(context, '/online_booking/settings', { is_enabled: true, auto_confirm_online: false, allow_customer_cancellation: true, cancellation_notice_hours: 24 }, 200);
  return { service, member };
}

async function inboxRow(page: Page, number: string) {
  const view = shown(page);
  const search = view.locator('[data-testid=ob-bookings-search] input');
  await search.fill(number);
  const row = view.locator('[data-testid=ob-bookings-row]', { hasText: number });
  await expect(row).toBeVisible();
  return row;
}

test('Online booking: book in the preview, pending in the inbox and the agenda, confirm, see and cancel by link, settings', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/online_booking/preview');
  try {
    const who = await cast(context);

    // The preview of the public page: the service, no preference, the day and a free time, name and mobile.
    await page.goto('/online_booking/preview');
    const preview = shown(page);
    await expect(preview.locator('[data-testid=ob-preview-title]')).toBeVisible();
    await preview.locator(`[data-testid=ob-preview-service-${who.service.id}]`).click();
    const day = preview.locator('[data-testid=ob-preview-day] input');
    await day.fill(DAY);
    await day.press('Tab');
    const ten = preview.locator('[data-testid="ob-preview-time-10:00"]');
    await expect(ten).toBeVisible();
    await ten.click();
    await preview.locator('[data-testid=ob-preview-name] input').fill(named('Marta'));
    await preview.locator('[data-testid=ob-preview-phone] input').fill(MOBILE);
    await page.screenshot({ path: shot('online-booking-preview-form') });
    await preview.locator('[data-testid=ob-preview-book]').click();
    const booked = preview.locator('[data-testid=ob-preview-booked]');
    await expect(booked).toContainText('Booking APT-');
    await expect(booked).toContainText('We have received your booking.');
    const number = ((await booked.textContent()) ?? '').match(/APT-\d{8}-\d{4}/)![0];
    const token = ((await preview.locator('[data-testid=ob-preview-token] code').textContent()) ?? '').trim();
    expect(token.length).toBeGreaterThanOrEqual(43);
    await page.screenshot({ path: shot('online-booking-preview-booked') });

    // In the diary: an online appointment, pending, with the professional; the card in Customers by her mobile.
    const appointment = JSON.parse(
      psql(`select row_to_json(a) from (select id, status, source, staff_id, customer_id from appointment_appointment where number = '${number}') a`),
    ) as { id: string; status: string; source: string; staff_id: string; customer_id: string };
    expect([appointment.status, appointment.source, appointment.staff_id]).toEqual(['pending', 'online', who.member.id]);
    expect(psql(`select phone from customer_customer where id = '${appointment.customer_id}'`)).toBe(`+34${MOBILE}`);
    const agenda = await api<{ status: string; booked_by_customer: boolean }>(context, A, 'GET', `/appointment/appointments/detail?number=${number}`);
    expect([agenda.data.status, agenda.data.booked_by_customer]).toEqual(['pending', true]);

    // The inbox: pending, confirmed from its row.
    await page.goto('/online_booking/bookings');
    let row = await inboxRow(page, number);
    await expect(row).toContainText('Pending');
    await expect(row).toContainText(named('Marta'));
    await page.screenshot({ path: shot('online-booking-inbox-desktop') });
    await rowAction(page, 'ob-bookings', appointment.id, 'confirm');
    row = shown(page).locator('[data-testid=ob-bookings-row]', { hasText: number });
    await expect(row).toContainText('Confirmed');
    expect(psql(`select status from appointment_appointment where id = '${appointment.id}'`)).toBe('confirmed');

    // Her link: it shows the booking confirmed, and cancels it within the policy; the inbox follows live.
    const seen = await api<{ status: string; can_cancel: boolean }>(context, A, 'GET', `/online_booking/public/booking?token=${token}`);
    expect([seen.status, seen.data.status, seen.data.can_cancel]).toEqual([200, 'confirmed', true]);
    const cancelled = await api<{ status: string }>(context, A, 'POST', '/online_booking/public/cancel', { token });
    expect([cancelled.status, cancelled.data.status]).toEqual([200, 'cancelled']);
    await expect(row).toContainText('Cancelled');
    expect(psql(`select cancelled_by_customer from appointment_appointment where id = '${appointment.id}'`)).toBe('t');

    // Settings: the page's title saved, said so.
    await page.goto('/online_booking/settings');
    const settings = shown(page);
    await settings.locator('[data-testid=ob-settings-page_title] input').fill(named('Salon'));
    await settings.locator('[data-testid=ob-settings-save]').click();
    await expect(settings.locator('[data-testid=ob-settings-saved]')).toContainText('Settings saved.');
    const saved = await api<{ page_title: string }>(context, A, 'GET', '/online_booking/settings');
    expect(saved.data.page_title).toBe(named('Salon'));
    await expect(settings.locator(`[data-testid=ob-settings-service-${who.service.id}]`)).toBeVisible();
    await page.screenshot({ path: shot('online-booking-settings-desktop'), fullPage: true });
  } finally {
    await context.close();
  }
});

test('Online booking: the inbox and the settings in the tablet and phone viewports', async ({ browser }) => {
  for (const [name, viewport] of Object.entries({ tablet: VIEWPORTS.tablet, phone: VIEWPORTS.phone })) {
    const { context, page } = await ownerPage(browser, '/online_booking/bookings', viewport);
    try {
      const view = shown(page);
      await expect(view.locator('[data-testid=ob-bookings-row], [data-testid=ob-bookings-empty]').first()).toBeVisible();
      await page.screenshot({ path: shot(`online-booking-inbox-${name}`) });
      await page.goto('/online_booking/settings');
      await expect(shown(page).locator('[data-testid=ob-settings]')).toBeVisible();
      await page.screenshot({ path: shot(`online-booking-settings-${name}`) });
    } finally {
      await context.close();
    }
  }
});
