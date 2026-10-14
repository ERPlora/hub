// Staff → Settings (WORKBOOK «Pantallas · Ajustes de Personal»; STAFF-F22): the old settings tab, only
// for whoever may save them — Working day starts/ends (HH:MM), Break duration, Minimum booking notice,
// Maximum hours per day, Overtime threshold, with the old hints, and the five switches; «Save» sends only
// what changed (`staff.settings.update`). The values come live (`staff.settings.get`: the proposed ones
// until the business saves); a value out of range is said under its field and nothing is saved.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import type { SettingsOut } from '../operations';
import { click, EMPLOYEE, ionChecked, ionValue, type MountOptions, mountStaff, settle } from '../__tests__/mount-staff';
import SettingsPage from './SettingsPage.vue';

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; type?: string; helperText?: string; errorText?: string; disabled?: boolean };

const PROPOSED: SettingsOut = {
  default_work_start: '09:00',
  default_work_end: '18:00',
  default_break_duration: 60,
  min_advance_booking: 1,
  max_daily_hours: 12,
  overtime_threshold: 40,
  show_staff_photos: true,
  show_staff_bio: true,
  allow_staff_selection: true,
  notify_new_appointment: true,
  notify_cancellation: true,
};

async function setup(options: MountOptions = {}) {
  const m = await mountStaff(SettingsPage, { path: '/staff/settings', ...options });
  await m.live();
  const field = (name: string) => m.find(`staff-settings-${name}`).element as Control;
  const save = () => m.find('staff-settings-save').element as Control;
  return { ...m, field, save };
}

describe('SettingsPage (STAFF-F22)', () => {
  it('follows the settings and shows them in the old fields, with their hints', async () => {
    const s = await setup();
    expect(s.params('staff.settings.get')).toEqual([{}]);
    expect(s.find('staff-settings-loading').exists()).toBe(true);
    await s.result('staff.settings.get', PROPOSED);
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Staff');
    const fields = ['default_work_start', 'default_work_end', 'default_break_duration', 'min_advance_booking', 'max_daily_hours', 'overtime_threshold'];
    expect(fields.map((name) => [s.field(name).label, s.field(name).value, s.field(name).type])).toEqual([
      ['Working day starts (HH:MM)', '09:00', 'time'],
      ['Working day ends (HH:MM)', '18:00', 'time'],
      ['Break duration (minutes)', '60', 'number'],
      ['Minimum booking notice (hours)', '1', 'number'],
      ['Maximum hours per day', '12', 'number'],
      ['Overtime threshold (hours/week)', '40', 'number'],
    ]);
    expect(s.field('default_break_duration').helperText).toBe('Between 0 and 480 minutes.');
    const switches = ['show_staff_photos', 'show_staff_bio', 'allow_staff_selection', 'notify_new_appointment', 'notify_cancellation'];
    expect(switches.map((name) => [s.field(name).textContent?.trim(), s.field(name).checked])).toEqual([
      ['Show staff photos', true],
      ['Show staff bio', true],
      ['Let customers choose the professional', true],
      ['Notify on a new appointment', true],
      ['Notify on a cancellation', true],
    ]);
    expect(s.save().disabled).toBe(true);
  });

  it('«Save» sends only what changed and says it is saved', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    s.answer(200, { ...PROPOSED, default_work_end: '20:00', show_staff_bio: false });
    await ionValue(s.field('default_work_end'), '20:00', 'ionInput');
    await ionChecked(s.field('show_staff_bio'), false);
    expect(s.save().disabled).toBe(false);
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/settings', query: {}, body: { default_work_end: '20:00', show_staff_bio: false } }]);
    expect(s.find('staff-settings-saved').text()).toContain('Settings saved');
  });

  it('a value out of range is said under its field and the typed values stay', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { max_daily_hours: 'Ensure this value is less than or equal to 24.' } } });
    await ionValue(s.field('max_daily_hours'), '30', 'ionInput');
    await click(s.save());
    expect(s.field('max_daily_hours').errorText).toBe('Ensure this value is less than or equal to 24.');
    expect(s.field('max_daily_hours').value).toBe('30');
    expect(s.find('staff-settings-error').text()).toContain('Check the fields.');
  });

  it('a change saved elsewhere repaints the form while nothing is being typed', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    await s.result('staff.settings.get', { ...PROPOSED, overtime_threshold: 35 }, {}, 2);
    expect(s.field('overtime_threshold').value).toBe('35');
  });

  it('a change saved elsewhere while typing: the untouched fields follow it, «Save» sends only what was typed', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    await ionValue(s.field('max_daily_hours'), '10', 'ionInput');
    // Someone else saves another setting meanwhile.
    await s.result('staff.settings.get', { ...PROPOSED, overtime_threshold: 35, show_staff_bio: false }, {}, 2);
    expect([s.field('overtime_threshold').value, s.field('show_staff_bio').checked, s.field('max_daily_hours').value]).toEqual(['35', false, '10']);
    s.answer(200, { ...PROPOSED, overtime_threshold: 35, show_staff_bio: false, max_daily_hours: 10 });
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/settings', query: {}, body: { max_daily_hours: 10 } }]);
  });

  it('a field typed back to what the server has is not sent; nothing left to send turns «Save» off', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    await ionValue(s.field('max_daily_hours'), '10', 'ionInput');
    expect(s.save().disabled).toBe(false);
    await ionValue(s.field('max_daily_hours'), '12', 'ionInput');
    expect(s.save().disabled).toBe(true);
  });

  it('whoever may not save them is told so, and sees no form', async () => {
    const s = await setup({ session: EMPLOYEE });
    await settle();
    expect(s.find('staff-settings-forbidden').text()).toContain('You do not have permission');
    expect(s.find('staff-settings-save').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.result('staff.settings.get', PROPOSED);
    expect([s.field('default_work_start').label, s.field('allow_staff_selection').textContent?.trim(), s.save().textContent?.trim()]).toEqual([
      'Inicio de jornada (HH:MM)',
      'Permitir elegir profesional',
      'Guardar',
    ]);
  });
});
