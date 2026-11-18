// flow: APPOINTMENT-F28
// Citas's counter of the bell (its `LiveAppConfig.bell`) in the action center: on the Home of hub `a`, as its owner
// reads it in Spanish, a booking the customer made herself with «confirm automatically» off waits for confirmation,
// and the bell counts it without a reload; opened, the notice «N citas por confirmar» leads to the agenda with
// «Confirmar las citas»; confirming it elsewhere takes the notice away, live. In each of the three sizes, on a day of
// its own, leaving a capture with the action center open. What it creates is «E2E Bell …», removed before and after;
// Citas's settings are put back as they were.
import { type Browser, type BrowserContext, expect, test } from '@playwright/test';

import { bellSays, bellTotal, featureNotice, noticeButton, noticeIn, openActionCenter } from './action-center';
import { capturedFitting } from './capture';
import { api } from './hub-api';
import { login } from './login';
import { psql } from './psql';
import { shown } from './screen';
import { A } from './stack';
import { homeRead, spanishOwnerOnMyApps as spanishOwner } from './home-helpers';
import { FLOW_VIEWPORTS, post } from './service-helpers';

const KEY = 'FIX-APPOINTMENT-SETUP-HOOKS';
const TAG = 'E2E Bell';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;

/** A Monday `weeks` + five weeks ahead (inside the 90 days of advance), as `YYYY-MM-DD`. */
function aMonday(weeks: number): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + 7 * weeks + ((8 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}

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

/** Citas's «confirm automatically» as it was before this file (the only setting it changes). */
let autoConfirm: boolean | null = null;

async function asOwner<T>(browser: Browser, run: (context: BrowserContext) => Promise<T>): Promise<T> {
  const context = await browser.newContext({ baseURL: A });
  try {
    await login(await context.newPage(), A, '/appointment/agenda');
    return await run(context);
  } finally {
    await context.close();
  }
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  await asOwner(browser, async (context) => {
    const current = await api<{ auto_confirm_online: boolean }>(context, A, 'GET', '/appointment/settings');
    expect(current.status).toBe(200);
    autoConfirm = current.data.auto_confirm_online;
    // «I review them first»: the customer's own bookings wait for the business (APPOINTMENT-F18).
    await post(context, '/appointment/settings', { auto_confirm_online: false }, 200);
  });
});

test.afterAll(async ({ browser }) => {
  try {
    if (autoConfirm !== null) {
      const before = autoConfirm;
      await asOwner(browser, (context) => post(context, '/appointment/settings', { auto_confirm_online: before }, 200));
    }
  } finally {
    cleanUp();
  }
});

interface Cast {
  customer: { id: string };
  service: { id: string };
  member: { id: string };
}

/** Through each app's own API: a card, a service a professional performs, and `day` open from 09:00 to 18:00. */
async function cast(context: BrowserContext, label: string, day: string): Promise<Cast> {
  const customer = await post<{ id: string }>(context, '/customer/customers', {
    name: named(`Lucía ${label}`),
    phone: `6${String(Date.now()).slice(-8)}`,
  });
  const service = await post<{ id: string }>(context, '/service/services', {
    name: named(`Haircut ${label}`),
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string }>(context, '/staff/members', { first_name: named(`Ana ${label}`), last_name: 'Stylist' });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  await post(context, '/schedule/special_days', {
    date: day,
    name: named(`Open ${day}`),
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '18:00' }],
  });
  return { customer, service, member };
}

/** How many appointments wait for confirmation now, as the server says (`appointment.to_confirm`). */
async function toConfirmNow(context: BrowserContext): Promise<number> {
  const res = await api<{ counters: { key: string; count: number }[] }>(context, A, 'GET', '/home/bell');
  expect(res.status).toBe(200);
  return res.data.counters.find((counter) => counter.key === 'appointment.to_confirm')?.count ?? 0;
}

/** The notice's title, in the singular for one. */
const toConfirmTitle = (count: number): string => (count === 1 ? '1 cita por confirmar' : `${count} citas por confirmar`);
const TO_CONFIRM = /\d+ citas? por confirmar/;

FLOW_VIEWPORTS.forEach(({ label, width, height }, index) => {
  test(`the action center's «citas por confirmar»: a customer's booking waiting counts live, leads to the agenda and goes once confirmed — ${label}`, async ({
    browser,
  }) => {
    const day = aMonday(index);
    const { context, page, streams } = await spanishOwner(browser, { width, height });
    try {
      const who = await cast(context, label, day);
      const [total, toConfirm] = await Promise.all([bellTotal(context), toConfirmNow(context)]);
      await homeRead(page, streams);
      await bellSays(page, total);
      const onTheHome = streams.length;

      // The customer books by WhatsApp: with «I review them first», it waits for the business.
      const book = async (hour: string) => {
        const booked = await post<{ id: string; status: string }>(context, '/appointment/appointments', {
          customer_id: who.customer.id,
          services: [{ service_id: who.service.id }],
          staff_id: who.member.id,
          start: `${day}T${hour}`,
          source: 'whatsapp',
        });
        expect(booked.status).toBe('pending');
        return booked;
      };
      const first = await book('10:00');

      // Counted without a reload, over the stream already open (the booking's event re-runs the bell).
      await bellSays(page, total + 1);
      expect(streams.length, 'the booking reached the bell without a new /api/live').toBe(onTheHome);
      // Confirmed elsewhere, it goes the same way (the confirmation's event re-runs the bell).
      await post(context, '/appointment/appointments/confirm', { id: first.id }, 200);
      await bellSays(page, total);
      expect(streams.length, 'the confirmation reached the bell without a new /api/live').toBe(onTheHome);

      const booked = await book('11:00');
      await bellSays(page, total + 1);
      // The capture: the Home with the action center open on the notice.
      const featured = await featureNotice(page, TO_CONFIRM);
      await expect(featured.locator('h3')).toHaveText(toConfirmTitle(toConfirm + 1));
      const confirmThem = noticeButton(featured, 'Confirmar las citas');
      await expect(confirmThem).toBeVisible();
      await capturedFitting(page, `${KEY}-${label}`, label);

      // Its button leads to the agenda.
      await confirmThem.click();
      await expect(page).toHaveURL(`${A}/appointment/agenda`);
      await expect(shown(page).locator('[data-testid="appointment-toolbar"]')).toBeVisible();

      // Confirmed elsewhere: the bell, in the agenda's bar too, takes it away without a reload.
      await post(context, '/appointment/appointments/confirm', { id: booked.id }, 200);
      await bellSays(page, total);
      expect(psql(`select status from appointment_appointment where id = '${booked.id}'`)).toBe('confirmed');
      if (toConfirm === 0) await expect(noticeIn(await openActionCenter(page), TO_CONFIRM)).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
});
