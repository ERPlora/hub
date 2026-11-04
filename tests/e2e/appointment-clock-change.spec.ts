// hub#636, APPOINTMENT-F01 and the «By professional · Day» grid: the nights Madrid's clock changes an appointment lasts
// its real minutes and its card ends at the wall time it really ends at. A 60-minute appointment at 01:30 on the day of
// 23 hours (28/03/2027) ends at 03:30, two hours along the axis; a 90-minute one at 01:37 on the day of 25 hours
// (31/10/2027) ends at 02:07, half an hour along it. Everything is booked through the API on those future days, with the
// calendar window at 00:00 to 06:00, and looked at in the three viewports. Everything is named «E2E Dst …» and removed
// before and after; the settings of Citas are read first and put back by API at the end.
import { expect, test } from '@playwright/test';

import { A, api, capture, psql, shown } from './helpers';
import { ownerPage, post, VIEWPORTS } from './service-helpers';

const TAG = 'E2E Dst';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;

const NIGHTS = [
  {
    name: 'day-of-23-hours',
    day: '2027-03-28',
    start: '01:30',
    minutes: 60,
    end: '2027-03-28T03:30:00+02:00',
    left: 144, // 01:30 at 1.6 px a minute
    width: 192, // two hours on the wall
  },
  {
    name: 'day-of-25-hours',
    day: '2027-10-31',
    start: '01:37',
    minutes: 90,
    end: '2027-10-31T02:07:00+01:00',
    left: 155.2, // 01:37 at 1.6 px a minute
    width: 48, // half an hour on the wall
  },
] as const;

function cleanUp(): void {
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  const services = `select id from service_service where name like '${TAG}%'`;
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
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

test('Agenda: an appointment over the change of time lasts its real minutes and its card ends at its real end', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/appointment/agenda');
  try {
    await post(
      context,
      '/appointment/settings',
      { calendar_start_hour: 0, calendar_end_hour: 6, max_advance_booking: 0, min_booking_notice: 0 },
      200,
    );
    const customer = await post<{ id: string }>(context, '/customer/customers', {
      name: named('Lucía'),
      phone: `6${String(Date.now()).slice(-8)}`,
    });
    const service = await post<{ id: string }>(context, '/service/services', {
      name: named('Haircut'),
      price: 2000,
      duration_minutes: 30,
      tax_category_key: 'service.generic',
    });
    const member = await post<{ id: string }>(context, '/staff/members', { first_name: named('Ana'), last_name: 'Stylist' });
    await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);

    for (const night of NIGHTS) {
      await post(context, '/schedule/special_days', {
        date: night.day,
        name: named(`Open ${night.day}`),
        is_closed: false,
        intervals: [{ open_time: '00:00', close_time: '06:00' }],
      });
      const booked = await post<{ id: string; end: string; duration_minutes: number }>(context, '/appointment/appointments', {
        customer_id: customer.id,
        services: [{ service_id: service.id }],
        staff_id: member.id,
        duration_minutes: night.minutes,
        start: `${night.day}T${night.start}`,
      });
      expect(booked.end).toBe(night.end);
      expect(booked.duration_minutes).toBe(night.minutes);

      await page.goto(`/appointment/agenda?date=${night.day}`);
      const view = shown(page);
      await view.locator('[data-testid=appointment-toolbar-view-staff]').click();
      const lane = view.locator(`[data-testid=appointment-grid-lane][data-lane="${member.id}"]`);
      const card = lane.locator(`[data-testid=appointment-grid-appointment][data-id="${booked.id}"]`);
      await expect(card).toBeVisible();

      const style = (await card.getAttribute('style')) ?? '';
      expect(style).toContain(`left: ${night.left}px`);
      expect(style).toContain(`width: ${night.width}px`);

      for (const [size, viewport] of Object.entries(VIEWPORTS)) {
        await page.setViewportSize(viewport);
        await expect(card).toBeVisible();
        await capture(page, `appointment-clock-change-${night.name}-${size}`);
      }
      await page.setViewportSize(VIEWPORTS.desktop);
    }
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  } finally {
    await context.close();
  }
});
