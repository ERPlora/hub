// Time clock → Settings (WORKBOOK «Pantallas · Ajustes»; ATTENDANCE-F04), the old `erp-attendance-settings`:
// «Require location when clocking in from a personal device», «Allowed radius», «Workplace location»
// (Latitude, Longitude and «Use my current location») and «Flag for review after (hours)». A manager
// saves only what changed; everyone else reads them with «Only a manager or an administrator can change
// these settings.». What the screen can judge it judges before sending and, like the server's 422, points
// at under its field.
import { describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, click, ionValue, mountAttendance, settle } from '../__tests__/mount-attendance';
import type { SettingsOut } from '../operations';
import SettingsPage from './SettingsPage.vue';

const geo = vi.hoisted(() => ({ getPosition: vi.fn() }));
vi.mock('../lib/geo', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/geo')>()),
  getPosition: geo.getPosition,
}));

type Control = HTMLElement & { value?: unknown; checked?: boolean; disabled?: boolean; errorText?: string; label?: string };

const DEFAULTS: SettingsOut = {
  require_location: false,
  geofence_radius_m: 100,
  workplace_lat: null,
  workplace_lng: null,
  auto_close_after_hours: 12,
  workplace_set: false,
  saved: false,
  updated_at: null,
};

async function setup(options: { session?: typeof EMPLOYEE; locale?: 'en' | 'es'; data?: SettingsOut | null } = {}) {
  const m = await mountAttendance(SettingsPage, { path: '/attendance/settings', session: options.session, locale: options.locale });
  await m.live();
  if (options.data !== null) await m.result('attendance.settings.get', options.data ?? DEFAULTS);
  const field = (name: string) => m.find(`attendance-settings-${name}`).element as Control;
  return { ...m, field };
}

describe('SettingsPage (ATTENDANCE-F04)', () => {
  it('says it is loading until the settings arrive', async () => {
    const s = await setup({ data: null });
    expect(s.find('attendance-settings-loading').exists()).toBe(true);
  });

  it('paints the values, the defaults until the business saves', async () => {
    const s = await setup();
    expect(s.field('require_location').checked).toBe(false);
    expect(s.field('geofence_radius_m').value).toBe('100');
    expect([s.field('workplace_lat').value, s.field('workplace_lng').value]).toEqual(['', '']);
    expect(s.field('auto_close_after_hours').value).toBe('12');
    expect(s.find('attendance-settings-geofence_radius_m').findAll('ion-select-option').map((o) => o.text())).toEqual([
      '50 m',
      '100 m',
      '250 m',
      '500 m',
      '1000 m',
    ]);
    expect(s.find('attendance-settings-read-only').exists()).toBe(false);
  });

  it('saves only what changed and says so', async () => {
    const s = await setup();
    s.answerBy({ '/api/attendance/settings': [200, { ...DEFAULTS, auto_close_after_hours: 10, saved: true }] });
    await ionValue(s.field('auto_close_after_hours'), '10', 'ionInput');
    await click(s.field('save'));
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/attendance/settings', query: {}, body: { auto_close_after_hours: 10 } }]);
    expect(s.find('attendance-settings-saved').text()).toContain('Settings saved.');
  });

  it('keeps «Require location» off until devices have a mode, and says why (review of 2026-10-15, finding 6)', async () => {
    const s = await setup();
    expect(s.field('require_location').disabled).toBe(true);
    expect(s.find('attendance-settings-location-pending').text()).toContain(
      'which this Hub does not tell yet: until it does, every device clocks as the counter',
    );
  });

  it('saves the radius and the workplace, ready for when it applies', async () => {
    const s = await setup();
    s.answerBy({ '/api/attendance/settings': [200, DEFAULTS] });
    await ionValue(s.field('geofence_radius_m'), '250');
    await ionValue(s.field('workplace_lat'), '40.4168', 'ionInput');
    await ionValue(s.field('workplace_lng'), '-3.7038', 'ionInput');
    await click(s.field('save'));
    await settle();
    expect(s.sent()[0].body).toEqual({ geofence_radius_m: 250, workplace_lat: 40.4168, workplace_lng: -3.7038 });
  });

  it('a business that asks for the location without a workplace is told', async () => {
    const s = await setup({ data: { ...DEFAULTS, require_location: true } });
    expect(s.field('require_location').checked).toBe(true);
    expect(s.find('attendance-settings-workplace-missing').text()).toContain('Set the workplace location');
  });

  it('«Use my current location» fills the workplace and tells the accuracy', async () => {
    geo.getPosition.mockResolvedValueOnce({ lat: 40.41681234567, lng: -3.70381234567, accuracy_m: 12.4 });
    const s = await setup();
    await click(s.field('use-location'));
    await settle();
    expect([s.field('workplace_lat').value, s.field('workplace_lng').value]).toEqual(['40.416812', '-3.703812']);
    expect(s.find('attendance-settings-accuracy').text()).toContain('±12 m');
  });

  it('a denied location says so and keeps what was typed', async () => {
    const { GeoError } = await import('../lib/geo');
    geo.getPosition.mockRejectedValueOnce(new GeoError('denied'));
    const s = await setup();
    await click(s.field('use-location'));
    await settle();
    expect(s.find('attendance-settings-error').text()).toContain('Location access is denied');
  });

  // WORKBOOK ATTENDANCE-F04 «Si falla»: what is wrong is pointed at in its own field, not in a banner.
  it.each([
    [{ workplace_lat: '40.4' }, 'workplace_lng', 'Fill in both latitude and longitude, or leave both empty.'],
    [{ workplace_lng: '-3.7' }, 'workplace_lat', 'Fill in both latitude and longitude, or leave both empty.'],
    [{ workplace_lat: '95', workplace_lng: '0' }, 'workplace_lat', 'Latitude must be a number between -90 and 90.'],
    [{ workplace_lat: '0', workplace_lng: '200' }, 'workplace_lng', 'Longitude must be a number between -180 and 180.'],
    [{ auto_close_after_hours: '0' }, 'auto_close_after_hours', 'Enter a whole number of hours between 1 and 24.'],
    [{ auto_close_after_hours: '2.5' }, 'auto_close_after_hours', 'Enter a whole number of hours between 1 and 24.'],
  ])('judges %o before sending, under the field %s', async (typed, name, message) => {
    const s = await setup();
    for (const [key, value] of Object.entries(typed)) await ionValue(s.field(key), value, 'ionInput');
    await click(s.field('save'));
    await settle();
    expect(s.sent()).toEqual([]);
    expect(s.field(name).errorText).toBe(message);
    expect(s.field(name).classList.contains('ion-invalid')).toBe(true);
    expect(s.find('attendance-settings-error').exists()).toBe(false);
  });

  it('clears a field’s mark once it is fixed, and then saves', async () => {
    const s = await setup();
    await ionValue(s.field('auto_close_after_hours'), '30', 'ionInput');
    await click(s.field('save'));
    await settle();
    expect(s.field('auto_close_after_hours').errorText).toBe('Enter a whole number of hours between 1 and 24.');
    s.answerBy({ '/api/attendance/settings': [200, { ...DEFAULTS, auto_close_after_hours: 10, saved: true }] });
    await ionValue(s.field('auto_close_after_hours'), '10', 'ionInput');
    expect(s.field('auto_close_after_hours').errorText ?? '').toBe('');
    await click(s.field('save'));
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/attendance/settings', query: {}, body: { auto_close_after_hours: 10 } }]);
    expect(s.find('attendance-settings-saved').exists()).toBe(true);
  });

  it('puts the server’s 422 under its field', async () => {
    const s = await setup();
    s.answerBy({
      '/api/attendance/settings': [422, { error: { code: 'invalid_payload', message: 'Invalid', fields: { auto_close_after_hours: 'Too many' } } }],
    });
    await ionValue(s.field('auto_close_after_hours'), '20', 'ionInput');
    await click(s.field('save'));
    await settle();
    expect(s.field('auto_close_after_hours').errorText).toBe('Too many');
  });

  it('an employee reads them, read-only, without Save', async () => {
    const s = await setup({ session: EMPLOYEE, data: { ...DEFAULTS, require_location: true, workplace_lat: 40.4, workplace_lng: -3.7, workplace_set: true } });
    expect(s.find('attendance-settings-read-only').text()).toContain('Only a manager or an administrator can change these settings.');
    expect([s.field('require_location').disabled, s.field('workplace_lat').disabled, s.field('auto_close_after_hours').disabled]).toEqual([true, true, true]);
    expect(s.find('attendance-settings-save').exists()).toBe(false);
    expect(s.find('attendance-settings-use-location').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.field('auto_close_after_hours').label).toBe('Marcar a revisar tras (horas)');
    expect(s.find('attendance-settings-use-location').text()).toContain('Usar mi ubicación actual');
  });
});
