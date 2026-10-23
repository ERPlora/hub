// flow: APPOINTMENT-F28
// The device's notice of a booking the customer made herself (apps/appointment/WORKBOOK.md APPOINTMENT-F28; the old
// hub's HUB_SHELL-F66, hub#2168): in the installed app, a booking by WhatsApp sends ONE system notice
// (`erplora_notify`) with «New appointment · {customer}», the service, «{day} at {hour}» and the professional, while
// one of the front desk sends none; a reload (or a reconnection) brings the last 24 hours back and tells nothing
// again; and a tap on the notice opens the agenda on the appointment's day. Tauri does not run in Playwright: the
// app's bridge is simulated at the edge (`window.__TAURI__`, which records what it is asked); Hub, SaaS, live
// stream and database are the real ones. In each of the three sizes, on a day of its own; what it creates is
// «E2E Apn …», removed before and after.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { psql, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, ownerPage, post, settled } from './service-helpers';

const TAG = 'E2E Apn';
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

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/**
 * The installed app's bridge, at the edge: every command it is asked is kept in `window.__asked`, the plugin's tap
 * listener in `window.__tap`, and each write of the device's memory of notices counts in `window.__told` (the door
 * writes it every time it reads a live result). Any other command answers nothing, as on a computer.
 */
function nativeApp(): void {
  const win = window as unknown as Record<string, unknown>;
  win.__asked = [];
  win.__told = 0;
  const setItem = Storage.prototype.setItem;
  Storage.prototype.setItem = function (key: string, value: string) {
    if (key === 'erplora.notices.told') win.__told = (win.__told as number) + 1;
    return setItem.call(this, key, value);
  };
  win.__TAURI__ = {
    core: {
      invoke: async (command: string, args?: unknown) => {
        (win.__asked as unknown[]).push([command, args ?? null]);
        return null;
      },
      addPluginListener: async (_plugin: string, _event: string, cb: (payload: unknown) => void) => {
        win.__tap = cb;
        return { unregister: async () => {} };
      },
    },
  };
}

interface Notified {
  title: string;
  body: string;
  id: number;
  path: string | null;
}

const notified = (page: Page): Promise<Notified[]> =>
  page.evaluate(() =>
    ((window as unknown as { __asked: [string, unknown][] }).__asked ?? [])
      .filter(([command]) => command === 'erplora_notify')
      .map(([, args]) => args as Notified),
  );

const toldWrites = (page: Page): Promise<number> => page.evaluate(() => (window as unknown as { __told: number }).__told);

interface Cast {
  customer: { id: string; name: string };
  service: { id: string; name: string };
  member: { id: string; full_name: string };
}

/** Through each app's own API: a card, a service a professional performs, and `day` open from 09:00 to 18:00. */
async function cast(context: BrowserContext, label: string, day: string): Promise<Cast> {
  const customer = await post<{ id: string; name: string }>(context, '/customer/customers', {
    name: named(`Lucía ${label}`),
    phone: `6${String(Date.now()).slice(-8)}`,
  });
  const service = await post<{ id: string; name: string }>(context, '/service/services', {
    name: named(`Haircut ${label}`),
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', {
    first_name: named(`Ana ${label}`),
    last_name: 'Stylist',
  });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  await post(context, '/schedule/special_days', {
    date: day,
    name: named(`Open ${day}`),
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '18:00' }],
  });
  return { customer, service, member };
}

async function book(context: BrowserContext, who: Cast, start: string, source: string): Promise<{ id: string }> {
  return post(context, '/appointment/appointments', {
    customer_id: who.customer.id,
    services: [{ service_id: who.service.id }],
    staff_id: who.member.id,
    start,
    source,
  });
}

FLOW_VIEWPORTS.forEach(({ label, width, height }, index) => {
  test(`APPOINTMENT-F28 a booking by WhatsApp rings the device once and its tap opens the agenda on its day — ${label}`, async ({
    browser,
  }) => {
    const day = aMonday(index);
    const { context, page } = await ownerPage(browser, '/appointment/agenda', { width, height });
    try {
      const who = await cast(context, label, day);
      // The installed app from now on; its first day only learns what is already there.
      await context.addInitScript(nativeApp);
      await page.reload();
      await expect(page.locator('[data-testid=device-notices]')).toBeAttached();
      await expect.poll(() => toldWrites(page)).toBeGreaterThan(0);
      expect(await notified(page)).toEqual([]);

      // The front desk's booking: nobody is told (who booked it knows). Then the customer's own, by WhatsApp.
      await book(context, who, `${day}T09:00`, 'counter');
      const theirs = await book(context, who, `${day}T10:00`, 'whatsapp');

      await expect.poll(() => notified(page).then((sent) => sent.length)).toBe(1);
      const [notice] = await notified(page);
      expect(notice.title).toBe(`New appointment · ${who.customer.name}`);
      const [service, when, professional] = notice.body.split(' · ');
      expect([service, professional]).toEqual([who.service.name, who.member.full_name]);
      expect(when).toMatch(/ at 10:00$/);
      expect(notice.path).toBe(`/appointment/agenda?date=${day}`);
      expect(notice.id).toEqual(expect.any(Number));
      expect(psql(`select source from appointment_appointment where id = '${theirs.id}'`)).toBe('whatsapp');

      // A tap on it opens the agenda on that day, where the booking is.
      await page.evaluate((id) => (window as unknown as { __tap: (payload: unknown) => void }).__tap({ notification: { id } }), notice.id);
      await expect(page).toHaveURL(new RegExp(`/appointment/agenda\\?date=${day}$`));
      await expect(shown(page).locator(`[data-testid=appointment-list-row][data-id="${theirs.id}"]`).first()).toBeVisible();
      await settled(page);
      await page.screenshot({ path: shot(`FIX-UI-SHELL-BELL-APPOINTMENT-NOTICES-${label}`), fullPage: false });

      // A reload brings the last 24 hours back: told already on this device, so nothing rings again.
      await page.reload();
      await expect.poll(() => toldWrites(page)).toBeGreaterThan(0);
      expect(await notified(page)).toEqual([]);
    } finally {
      await context.close();
    }
  });
});
