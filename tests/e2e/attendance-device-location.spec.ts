// flow: ATTENDANCE-F03
// Clocking in from a personal device when the business asks for the location (apps/attendance/WORKBOOK.md), end to
// end in each of the three sizes. The owner enters on a device of their own (a real entry: the hub gives the browser
// its `hub_device`), first shared — the counter POS, never asked — and then made personal from the device itself
// (BASE-F62): the clock page follows it live, reads the position, refuses outside the radius saying how far, clocks
// inside it with the distance the Hub measures, and clocks out wherever. What the spec creates carries `E2EAttDev`,
// and the device and the settings go away.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';

type Rows<T> = { rows: T[]; total: number };
type Device = { id: string; mode: string; current: boolean };

const KEY = 'CLOSE-ATTENDANCE';
const TAG = 'E2EAttDev';
const ZONE = 'Europe/Madrid';
const WORKPLACE = { latitude: 40.4168, longitude: -3.7038 }; // Puerta del Sol
const NEAR = { latitude: 40.4173, longitude: -3.7038, accuracy: 9 }; // 55.5 m north
const FAR = { latitude: 40.4245, longitude: -3.7038, accuracy: 9 }; // 855 m north
const RECORDS = `select id from attendance_record where member_id in (select id from staff_member where first_name like '${TAG}%')`;
const SETTINGS_ROWS =
  "select format('insert into attendance_attendancesettings (id, slot, require_location, geofence_radius_m, workplace_lat, workplace_lng, auto_close_after_hours, updated_at) values (%L, %s, %L, %s, %L, %L, %s, %L)', id, slot, require_location, geofence_radius_m, workplace_lat, workplace_lng, auto_close_after_hours, updated_at) from attendance_attendancesettings";

function cleanup(): void {
  psql(
    [
      `delete from attendance_correction where record_id in (${RECORDS})`,
      `delete from attendance_break where record_id in (${RECORDS})`,
      `delete from attendance_record where id in (${RECORDS})`,
      `delete from staff_member where first_name like '${TAG}%'`,
    ].join('; '),
  );
}

// The settings the hub had are put back after the file; each test starts without the spec's people.
let savedSettings: string[] = [];
test.beforeAll(() => {
  savedSettings = psql(SETTINGS_ROWS).split('\n').filter(Boolean);
});
test.beforeEach(cleanup);
test.afterAll(() => {
  cleanup();
  psql(['delete from attendance_attendancesettings', ...savedSettings].join('; '));
});

/** The day of `memberId` as `source,coordinates kept,within the radius at clock-in,status`. */
function dayOf(memberId: string): string {
  return psql(
    `select source || ',' || (in_lat is not null) || ',' || coalesce(in_within_radius::text, '-') || ',' || status from attendance_record where member_id = '${memberId}' order by clock_in_at desc limit 1`,
  );
}

async function snap(page: Page, label: string): Promise<void> {
  await noHorizontalScroll(page, `F03 ${label}`);
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-${label}`) });
}

for (const vp of VIEWPORTS) {
  test(`ATTENDANCE-F03 at ${vp.label}: the counter POS is never asked; a device made personal must be within the radius`, async ({ browser }) => {
    const context = await browser.newContext({
      baseURL: A,
      viewport: { width: vp.width, height: vp.height },
      locale: 'en-US',
      timezoneId: ZONE,
    });
    await context.grantPermissions(['geolocation'], { origin: A });
    await context.setGeolocation(FAR);
    const page = await context.newPage();
    let deviceId = '';
    try {
      // A real entry with the account: the hub knows this browser as one of its devices, shared until someone says.
      await login(page, A, '/attendance/clock', undefined, { fresh: true });
      const devices = await api<{ devices: Device[] }>(context, A, 'GET', '/devices');
      const here = devices.data.devices.find((device) => device.current);
      expect(here?.mode, 'this browser is a device of the hub').toBe('shared');
      deviceId = here!.id;

      // The business asks for the location within 100 m of the workplace; the owner has a staff record.
      const asked = await api(context, A, 'POST', '/attendance/settings', {
        require_location: true,
        geofence_radius_m: 100,
        workplace_lat: WORKPLACE.latitude,
        workplace_lng: WORKPLACE.longitude,
      });
      expect(asked.status).toBe(200);
      const accounts = await api<Rows<{ user_id: string }>>(context, A, 'GET', '/staff/accounts?search=owner%40&limit=5');
      const created = await api<{ id: string }>(context, A, 'POST', '/staff/members', {
        first_name: `${TAG}${vp.label}`,
        last_name: 'Clock',
        user_id: accounts.data.rows[0].user_id,
      });
      expect(created.status).toBe(201);
      const memberId = created.data.id;

      // The counter POS (shared): never asked, wherever it is; the day keeps no coordinates.
      await page.goto(`${A}/attendance/clock`);
      const view = shown(page);
      await expect(view.locator('[data-testid=attendance-clock-greeting]')).toHaveText(`Hello, ${TAG}${vp.label} Clock`);
      await expect(view.locator('[data-testid=attendance-clock-location-note]')).toHaveCount(0);
      await view.locator('[data-testid=attendance-clock-in]').click();
      await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked in at');
      expect(dayOf(memberId)).toBe('shared,false,-,open');
      await view.locator('[data-testid=attendance-clock-out]').click();
      await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked out at');

      // An administrator makes this device personal from the device itself: the page follows it without reloading.
      expect((await api(context, A, 'POST', '/device/mode', { mode: 'personal' })).status).toBe(200);
      await expect(view.locator('[data-testid=attendance-clock-location-note]')).toHaveText(
        'Your location is checked when you clock in from this device.',
      );

      // 855 m away: refused, saying how far, and nothing is written.
      await view.locator('[data-testid=attendance-clock-in]').click();
      await expect(view.locator('[data-testid=attendance-clock-message]')).toHaveText(
        'You are 855 m from the workplace, outside the allowed 100 m. Move closer to clock in, or clock in at the counter.',
      );
      expect(dayOf(memberId)).toBe('shared,false,-,closed');

      // 55.5 m away: clocked in, with the distance the Hub measured and where it was, which the business asked for.
      await context.setGeolocation(NEAR);
      await view.locator('[data-testid=attendance-clock-in]').click();
      await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked in at');
      await expect(view.locator('[data-testid=attendance-clock-distance]')).toHaveText('You are 56 m from the workplace.');
      expect(dayOf(memberId)).toBe('personal,true,true,open');
      await snap(page, vp.label);

      // Clocking out is never blocked by the location, however far.
      await context.setGeolocation(FAR);
      await view.locator('[data-testid=attendance-clock-out]').click();
      await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked out at');
      expect(
        psql(`select status || ',' || out_within_radius from attendance_record where member_id = '${memberId}' order by clock_in_at desc limit 1`),
      ).toBe('closed,false');
    } finally {
      if (deviceId) await api(context, A, 'POST', '/devices/remove', { id: deviceId });
      await context.close();
    }
  });
}
