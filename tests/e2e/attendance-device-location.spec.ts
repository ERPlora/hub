// flow: ATTENDANCE-F03
// Clocking in from a personal device when the business asks for the location (apps/attendance/WORKBOOK.md), end to
// end in each of the three sizes. The owner enters on a device of their own (a real entry: the hub gives the browser
// its `hub_device`), first shared — the counter POS, never asked — and then made personal from the device itself
// (BASE-F62): the clock page follows it live, reads the position, refuses outside the radius saying how far, clocks
// inside it with the distance the Hub measures, and clocks out wherever; the settings say where a device is made
// personal. In English at the three sizes and in Spanish on a phone. What the spec creates carries `E2EAttDev`, and the
// device and the settings go away.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown } from './helpers';
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

async function snap(page: Page, name: string): Promise<void> {
  await noHorizontalScroll(page, `F03 ${name}`);
  await settled(page);
  await capture(page, `${KEY}-${name}`);
}

type Lang = 'en' | 'es';

/** What the screens say, word for word, in each language (the app's `locale/*.json` and its `django.po`). */
const SAYS: Record<Lang, Record<string, string>> = {
  en: {
    hello: 'Hello, ',
    note: 'Your location is checked when you clock in from this device.',
    clockedIn: 'Clocked in at',
    clockedOut: 'Clocked out at',
    outside: 'You are 855 m from the workplace, outside the allowed 100 m. Move closer to clock in, or clock in at the counter.',
    distance: 'You are 56 m from the workplace.',
    devices:
      'Only a device marked as personal is asked for its location; the counter POS never is. Each device is marked shared or personal on the device itself, in Settings › This device.',
  },
  es: {
    hello: 'Hola, ',
    note: 'Al fichar la entrada desde este dispositivo se comprueba tu ubicación.',
    clockedIn: 'Entrada fichada a las',
    clockedOut: 'Salida fichada a las',
    outside: 'Estás a 855 m del lugar de trabajo, fuera de los 100 m permitidos. Acércate para fichar o ficha en el mostrador.',
    distance: 'Estás a 56 m del lugar de trabajo.',
    devices:
      'Solo se pide la ubicación a un dispositivo marcado como personal; al TPV del mostrador, nunca. Cada dispositivo se marca como compartido o personal desde él mismo, en Ajustes › Este dispositivo.',
  },
};

/** The F03 of one size and language: the owner on a real device of the hub, shared and then made personal. */
async function clockOnADevice(browser: Browser, vp: { label: string; width: number; height: number }, lang: Lang): Promise<void> {
  const says = SAYS[lang];
  const shot = lang === 'en' ? vp.label : `${lang}-${vp.label}`;
  const context = await browser.newContext({
    baseURL: A,
    viewport: { width: vp.width, height: vp.height },
    locale: lang === 'en' ? 'en-US' : 'es-ES',
    timezoneId: ZONE,
  });
  await context.grantPermissions(['geolocation'], { origin: A });
  await context.setGeolocation(FAR);
  const page = await context.newPage();
  let deviceId = '';
  try {
    // A real entry with the account: the hub knows this browser as one of its devices, shared until someone says.
    await login(page, A, '/attendance/clock', undefined, { fresh: true });
    if (lang !== 'en') await context.addCookies([{ name: 'django_language', value: lang, domain: new URL(A).hostname, path: '/' }]);
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
    const name = `${TAG}${lang}${vp.label}`;
    const created = await api<{ id: string }>(context, A, 'POST', '/staff/members', {
      first_name: name,
      last_name: 'Clock',
      user_id: accounts.data.rows[0].user_id,
    });
    expect(created.status).toBe(201);
    const memberId = created.data.id;

    // Settings say where a device is made personal, under «Require location…», which can be turned on.
    await page.goto(`${A}/attendance/settings`);
    const settings = shown(page);
    await expect(settings.locator('[data-testid=attendance-settings-location-devices]')).toHaveText(says.devices);
    await expect(settings.locator('[data-testid=attendance-settings-require_location]')).not.toHaveClass(/toggle-disabled/);
    if (lang !== 'en') await snap(page, `settings-${shot}`);

    // The counter POS (shared): never asked, wherever it is; the day keeps no coordinates.
    await page.goto(`${A}/attendance/clock`);
    const view = shown(page);
    await expect(view.locator('[data-testid=attendance-clock-greeting]')).toHaveText(`${says.hello}${name} Clock`);
    await expect(view.locator('[data-testid=attendance-clock-location-note]')).toHaveCount(0);
    await view.locator('[data-testid=attendance-clock-in]').click();
    await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText(says.clockedIn);
    expect(dayOf(memberId)).toBe('shared,false,-,open');
    await view.locator('[data-testid=attendance-clock-out]').click();
    await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText(says.clockedOut);

    // An administrator makes this device personal from the device itself: the page follows it without reloading.
    expect((await api(context, A, 'POST', '/device/mode', { mode: 'personal' })).status).toBe(200);
    const note = view.locator('[data-testid=attendance-clock-location-note]');
    await expect(note).toHaveText(says.note);
    // Its «ⓘ» keeps the size of the note's text, also when the note wraps on a phone (it shrank to a dot there).
    const icon = await note.locator('ion-icon').evaluate((el) => ({
      width: el.getBoundingClientRect().width,
      size: parseFloat(getComputedStyle(el).fontSize),
    }));
    expect(icon.width, `the note's icon at ${vp.label} (${lang})`).toBeGreaterThanOrEqual(icon.size - 0.5);

    // 855 m away: refused, saying how far, and nothing is written.
    await view.locator('[data-testid=attendance-clock-in]').click();
    await expect(view.locator('[data-testid=attendance-clock-message]')).toHaveText(says.outside);
    expect(dayOf(memberId)).toBe('shared,false,-,closed');

    // 55.5 m away: clocked in, with the distance the Hub measured and where it was, which the business asked for.
    await context.setGeolocation(NEAR);
    await view.locator('[data-testid=attendance-clock-in]').click();
    await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText(says.clockedIn);
    await expect(view.locator('[data-testid=attendance-clock-distance]')).toHaveText(says.distance);
    expect(dayOf(memberId)).toBe('personal,true,true,open');
    await snap(page, shot);

    // Clocking out is never blocked by the location, however far.
    await context.setGeolocation(FAR);
    await view.locator('[data-testid=attendance-clock-out]').click();
    await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText(says.clockedOut);
    expect(
      psql(`select status || ',' || out_within_radius from attendance_record where member_id = '${memberId}' order by clock_in_at desc limit 1`),
    ).toBe('closed,false');
    // The owner's session on this personal device for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`),
    // when asked: the device then stays, or its session would end with it.
    if (process.env.E2E_SAVE_STORAGE_STATE) {
      await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
      deviceId = '';
    }
  } finally {
    if (deviceId) await api(context, A, 'POST', '/devices/remove', { id: deviceId });
    await context.close();
  }
}

for (const vp of VIEWPORTS) {
  test(`ATTENDANCE-F03 at ${vp.label}: the counter POS is never asked; a device made personal must be within the radius`, async ({ browser }) => {
    await clockOnADevice(browser, vp, 'en');
  });
}

test('ATTENDANCE-F03 in Spanish at 390: the note, the refusal, the distance and the settings say it in Spanish', async ({ browser }) => {
  await clockOnADevice(browser, VIEWPORTS[0], 'es');
});
