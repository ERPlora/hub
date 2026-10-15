// Appointments → Settings (WORKBOOK «Ajustes de Citas»; APPOINTMENT-F19): only for whoever may save them.
// The values come live (the factory ones until the business saves); «Save» sends only the fields the
// person touched and changed, says «Settings saved.», and a refusal goes under its field.
import { describe, expect, it } from 'vitest';

import type { SettingsOut } from '../operations';
import { click, EMPLOYEE, ionChecked, ionValue, type MountOptions, mountAppointment, settle } from '../__tests__/mount-appointment';
import SettingsPage from './SettingsPage.vue';

const OP = 'appointment.settings.get';
const SETTINGS: SettingsOut = {
  default_duration: 60,
  min_booking_notice: 60,
  max_advance_booking: 90,
  allow_overlapping: true,
  allow_customer_cancellation: true,
  cancellation_notice_hours: 24,
  calendar_start_hour: 8,
  calendar_end_hour: 20,
  slot_interval: 15,
  auto_confirm_online: true,
  timezone: 'Europe/Madrid',
};

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; errorText?: string; disabled?: boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountAppointment(SettingsPage, { path: '/appointment/settings', ...options });
  await m.live();
  const field = (name: string) => m.inDoc(`appointment-settings-${name}`) as Control;
  return { ...m, field, show: (data: unknown) => m.result(OP, data) };
}

describe('SettingsPage', () => {
  it('paints the settings with the old labels', async () => {
    const s = await setup();
    expect(s.field('loading')?.textContent).toContain('Loading settings…');
    await s.show(SETTINGS);
    expect([s.field('default_duration').label, s.field('min_booking_notice').label, s.field('slot_interval').label]).toEqual([
      'Default duration (minutes)',
      'Minimum booking notice (minutes)',
      'Slot interval (minutes)',
    ]);
    expect([s.field('calendar_start_hour').value, s.field('auto_confirm_online').checked]).toEqual(['8', true]);
    expect(s.field('auto_confirm_online').textContent).toBe('Confirm bookings made by the customer automatically');
    expect(s.field('save').disabled).toBe(true);
  });

  it('saves only what was touched and changed, and says so', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await ionValue(s.field('slot_interval'), '30', 'ionInput');
    await ionChecked(s.field('auto_confirm_online'), false);
    s.answer(200, { ...SETTINGS, slot_interval: 30, auto_confirm_online: false });
    await click(s.field('save'));
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/appointment/settings', query: {}, body: { slot_interval: 30, auto_confirm_online: false } },
    ]);
    await settle();
    expect(s.field('saved')?.textContent).toContain('Settings saved.');
  });

  it('puts a refusal under its field', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await ionValue(s.field('calendar_end_hour'), '7', 'ionInput');
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { calendar_end_hour: 'The calendar has to end after it starts.' } } });
    await click(s.field('save'));
    expect(s.field('calendar_end_hour').errorText).toBe('The calendar has to end after it starts.');
    expect(s.field('save-error')?.textContent).toContain('The settings could not be saved.');
  });

  it('is closed to who may not change them', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.field('forbidden')?.textContent).toContain('You do not have permission');
  });
});
