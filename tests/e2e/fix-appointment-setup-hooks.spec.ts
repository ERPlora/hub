// flow: APPOINTMENT-F28
// flow: área: los ganchos del Inicio de Citas (`setup`, `widgets` y `bell` de `LiveAppConfig`; ronda PLAN-HUB 2026-10-21): el contador «Citas por confirmar» de la campana
// Citas's counter of the bell (FIX-APPOINTMENT-SETUP-HOOKS; the old module's `bell`, appointments#169, hub#1678; the
// old hub's dashboard, docs/reference/old-hub/dashboard-*.png): on the Home of hub `a`, as its owner reads it in
// Spanish, a booking the customer made herself with «confirm automatically» off waits for confirmation, and the bell's
// badge counts it without a reload; opened, the row «Citas por confirmar (N)» leads to the agenda; confirming it
// elsewhere takes the row away, live. In each of the three sizes, on a day of its own, leaving the capture
// `FIX-APPOINTMENT-SETUP-HOOKS-<width>` with the bell open. What it creates is «E2E Bell …», removed before and after;
// Citas's settings are put back as they were.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown, untilStill } from './helpers';
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

interface Counter {
  key: string;
  count: number;
}

/** What the bell counts now, as the server says (`base.bell.counters`). */
async function counters(context: BrowserContext): Promise<{ total: number; toConfirm: number }> {
  const res = await api<{ counters: Counter[] }>(context, A, 'GET', '/home/bell');
  expect(res.status).toBe(200);
  const total = res.data.counters.reduce((sum, counter) => sum + counter.count, 0);
  const toConfirm = res.data.counters.find((counter) => counter.key === 'appointment.to_confirm')?.count ?? 0;
  return { total, toConfirm };
}

/**
 * The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home, with
 * the instant of every `/api/live` the page opens: a new stream brings every result again, so a count that changes
 * without one came over the stream already open, re-run by the counter's own events.
 */
async function spanishOwner(
  browser: Browser,
  viewport: { width: number; height: number },
): Promise<{ context: BrowserContext; page: Page; streams: number[] }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  const streams: number[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/live')) streams.push(Date.now());
  });
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(shown(page).locator('[data-testid="home-my-apps"]')).toBeVisible();
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page, streams };
}

/** Waits until the page has opened no `/api/live` for a second: every subscription of the screen is declared. */
async function settled(streams: number[]): Promise<void> {
  await expect.poll(() => Date.now() - (streams.at(-1) ?? 0), { timeout: 15_000 }).toBeGreaterThan(1_000);
}

const bell = (page: Page): Locator => shown(page).locator('[data-testid="hub-bell"]');
const badge = (page: Page): Locator => bell(page).locator('[data-testid="hub-bell-badge"]');
const toConfirmRow = (page: Page): Locator =>
  page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: /^\s*Citas por confirmar \(\d+\)\s*$/ });

/** Opens the bell and waits until its popover is presented (Ionic animates it in a shadow root). */
async function openBell(page: Page): Promise<void> {
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await bell(page).click();
  await presented;
}

/** The badge says `total`, or is not shown at zero. */
async function badgeSays(page: Page, total: number): Promise<void> {
  if (total > 0) await expect(badge(page)).toHaveText(String(total));
  else await expect(badge(page)).toHaveCount(0);
}

FLOW_VIEWPORTS.forEach(({ label, width, height }, index) => {
  test(`${KEY} el contador «Citas por confirmar» de la campana: a customer's booking waiting counts live, leads to the agenda and goes once confirmed — ${label}`, async ({
    browser,
  }) => {
    const day = aMonday(index);
    const { context, page, streams } = await spanishOwner(browser, { width, height });
    try {
      const who = await cast(context, label, day);
      const before = await counters(context);
      // The Home as it is read: its panels answered and its stream settled, before anything changes the bell.
      await expect(shown(page).locator('[data-testid="widget-board"] [data-testid="widget"]').first()).toBeVisible();
      await expect(shown(page).locator('[data-testid="widget-board"] [data-testid="widget"][aria-busy="true"]')).toHaveCount(0);
      await settled(streams);
      await badgeSays(page, before.total);
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
      await badgeSays(page, before.total + 1);
      expect(streams.length, 'the booking reached the bell without a new /api/live').toBe(onTheHome);
      // Confirmed elsewhere, it goes the same way (the confirmation's event re-runs the bell).
      await post(context, '/appointment/appointments/confirm', { id: first.id }, 200);
      await badgeSays(page, before.total);
      expect(streams.length, 'the confirmation reached the bell without a new /api/live').toBe(onTheHome);

      const booked = await book('11:00');
      await badgeSays(page, before.total + 1);
      // The capture: the Home with the bell open.
      await openBell(page);
      const row = toConfirmRow(page);
      await expect(row).toHaveText(`Citas por confirmar (${before.toConfirm + 1})`);
      await expect(row).toHaveAttribute('data-reachable', 'true');
      await untilStill(page);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `no sideways scroll at ${label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${label}`) });

      // The row leads to the agenda.
      await row.click();
      await expect(page).toHaveURL(`${A}/appointment/agenda`);
      await expect(shown(page).locator('[data-testid="appointment-toolbar"]')).toBeVisible();

      // Confirmed elsewhere: the bell, in the agenda's bar too, takes it away without a reload.
      await post(context, '/appointment/appointments/confirm', { id: booked.id }, 200);
      await badgeSays(page, before.total);
      expect(psql(`select status from appointment_appointment where id = '${booked.id}'`)).toBe('confirmed');
      if (before.toConfirm === 0) {
        await openBell(page);
        await expect(page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: 'Citas por confirmar' })).toHaveCount(0);
      }
    } finally {
      await context.close();
    }
  });
});
