// Staff → Settings (WORKBOOK «Pantallas · Ajustes de Personal»; STAFF-F22): the default working day,
// only for whoever may save it — Working day starts/ends (HH:MM) and Break duration, which a new
// schedule proposes (STAFF-F13). «Save» sends only what changed (`staff.settings.update`). The values come
// live (`staff.settings.get`: the proposed ones until the business saves); a value the server refuses is
// said under its field and nothing is saved.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { between, pressEnter, refusalMarks } from '../../../../base/frontend/__tests__/settings-form';
import type { SettingsOut } from '../operations';
import { click, EMPLOYEE, errorFrame, flush, ionValue, type MountOptions, mountStaff, settle } from '../__tests__/mount-staff';
import SettingsPage from './SettingsPage.vue';

type Control = HTMLElement & { label?: string; value?: unknown; type?: string; helperText?: string; errorText?: string; disabled?: boolean };

const PROPOSED: SettingsOut = {
  default_work_start: '09:00',
  default_work_end: '18:00',
  default_break_duration: 60,
};
const RETIRED = [
  'min_advance_booking',
  'max_daily_hours',
  'overtime_threshold',
  'show_staff_photos',
  'show_staff_bio',
  'allow_staff_selection',
  'notify_new_appointment',
  'notify_cancellation',
];

async function setup(options: MountOptions = {}) {
  const m = await mountStaff(SettingsPage, { path: '/staff/settings', ...options });
  await m.live();
  const field = (name: string) => m.find(`staff-settings-${name}`).element as Control;
  const save = () => m.find('staff-settings-save').element as Control;
  return { ...m, field, save };
}

describe('SettingsPage (STAFF-F22)', () => {
  it('follows the settings and shows the default working day, with what it is for', async () => {
    const s = await setup();
    expect(s.params('staff.settings.get')).toEqual([{}]);
    expect(s.find('staff-settings-loading').exists()).toBe(true);
    await s.result('staff.settings.get', PROPOSED);
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Staff');
    expect(s.find('staff-settings-workday').text()).toContain('Default working day');
    expect(s.find('staff-settings-workday-intro').text()).toBe(
      'A new schedule proposes this working day from Monday to Friday, with the break in the middle of the day.',
    );
    const fields = ['default_work_start', 'default_work_end', 'default_break_duration'];
    expect(fields.map((name) => [s.field(name).label, s.field(name).value, s.field(name).type, s.field(name).helperText])).toEqual([
      ['Working day starts (HH:MM)', '09:00', 'time', 'When each working day of a new schedule starts.'],
      ['Working day ends (HH:MM)', '18:00', 'time', 'After the start: a schedule’s day does not cross midnight.'],
      ['Break duration (minutes)', '60', 'number', 'From 0 (no break) to 480 minutes, shorter than the working day.'],
    ]);
    for (const name of RETIRED) expect(s.find(`staff-settings-${name}`).exists(), name).toBe(false);
    expect(s.save().disabled).toBe(true);
  });

  // As every settings page and FormModal (hub#897): what a save says is said where the person tapped «Save»; and Enter in
  // a field submits the form (Ionic puts a hidden submit button in it), the same save.
  it('«Save» sends only what changed and says it is saved right above it; Enter in a field saves too', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    s.answer(200, { ...PROPOSED, default_work_end: '20:00', default_break_duration: 30 });
    await ionValue(s.field('default_work_end'), '20:00', 'ionInput');
    await ionValue(s.field('default_break_duration'), '30', 'ionInput');
    expect(s.save().disabled).toBe(false);
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/staff/settings', query: {}, body: { default_work_end: '20:00', default_break_duration: 30 } },
    ]);
    expect(s.find('staff-settings-saved').text()).toContain('Settings saved');
    expect(between(s.field('default_break_duration'), s.find('staff-settings-saved').element, s.save())).toBe(true);
    await ionValue(s.field('default_work_start'), '08:00', 'ionInput');
    await pressEnter(s.find('staff-settings-form').element);
    expect(s.sent().at(-1)?.body).toEqual({ default_work_start: '08:00' });
  });

  it('while saving, «Save» spins and is off; once saved, it stops', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    let answer!: (response: Response) => void;
    s.net.onApi(() => new Promise<Response>((resolve) => (answer = resolve)));
    await ionValue(s.field('default_break_duration'), '30', 'ionInput');
    await click(s.save());
    const spins = () => !!s.save().querySelector('ion-spinner');
    expect([s.save().disabled, spins()]).toEqual([true, true]);
    answer(Response.json({ ...PROPOSED, default_break_duration: 30 }));
    await flush();
    await flush();
    expect([spins(), s.find('staff-settings-saved').exists()]).toEqual([false, true]);
  });

  it('a value the server refuses is said under its field, the typed values stay and the notice sits right above «Save»', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    s.answer(422, {
      error: { code: 'invalid_payload', message: 'The start time must be before the end time.', fields: { default_work_end: 'The start time must be before the end time.' } },
    });
    await ionValue(s.field('default_work_end'), '06:00', 'ionInput');
    await click(s.save());
    expect(s.field('default_work_end').errorText).toBe('The start time must be before the end time.');
    expect(s.field('default_work_end').value).toBe('06:00');
    expect(s.find('staff-settings-save-error').text()).toContain('The start time must be before the end time.');
    expect(between(s.field('default_break_duration'), s.find('staff-settings-save-error').element, s.save())).toBe(true);
  });

  describe('a refusal by fields (hub#854, as FormModal and the Services settings do: hub#821)', () => {
    const REFUSAL = {
      error: {
        code: 'invalid_payload',
        message: 'The start time must be before the end time.',
        fields: {
          default_work_end: 'The start time must be before the end time.',
          default_break_duration: 'Ensure this value is less than or equal to 480.',
        },
      },
    };

    /** Saves a day that ends before it starts and a 10-hour break, and the server refuses both fields. */
    async function refused() {
      const s = await setup();
      await s.result('staff.settings.get', PROPOSED);
      s.answer(422, REFUSAL);
      await ionValue(s.field('default_work_end'), '06:00', 'ionInput');
      await ionValue(s.field('default_break_duration'), '600', 'ionInput');
      await click(s.save());
      return { ...s, ...refusalMarks(s.field, () => s.find('staff-settings-save-error').exists()) };
    }

    it('the notice goes as soon as something is changed, and a field’s message as soon as that field is', async () => {
      const s = await refused();
      expect(s.notice()).toBe(true);
      expect([s.says('default_work_end'), s.says('default_break_duration')]).toEqual([
        'The start time must be before the end time.',
        'Ensure this value is less than or equal to 480.',
      ]);
      await ionValue(s.field('default_work_end'), '19:00', 'ionInput');
      expect(s.notice()).toBe(false);
      expect([s.says('default_work_end'), s.marked('default_work_end')]).toEqual(['', false]);
      expect([s.says('default_break_duration'), s.marked('default_break_duration')]).toEqual(['Ensure this value is less than or equal to 480.', true]);
    });
  });

  it('a change saved elsewhere repaints the form while nothing is being typed', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    await s.result('staff.settings.get', { ...PROPOSED, default_break_duration: 45 }, {}, 2);
    expect(s.field('default_break_duration').value).toBe('45');
  });

  it('a change saved elsewhere while typing: the untouched fields follow it, «Save» sends only what was typed', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    await ionValue(s.field('default_break_duration'), '30', 'ionInput');
    // Someone else saves another setting meanwhile.
    await s.result('staff.settings.get', { ...PROPOSED, default_work_end: '17:00' }, {}, 2);
    expect([s.field('default_work_end').value, s.field('default_break_duration').value]).toEqual(['17:00', '30']);
    s.answer(200, { ...PROPOSED, default_work_end: '17:00', default_break_duration: 30 });
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/settings', query: {}, body: { default_break_duration: 30 } }]);
  });

  it('a field typed back to what the server has is not sent; nothing left to send turns «Save» off', async () => {
    const s = await setup();
    await s.result('staff.settings.get', PROPOSED);
    await ionValue(s.field('default_break_duration'), '30', 'ionInput');
    expect(s.save().disabled).toBe(false);
    await ionValue(s.field('default_break_duration'), '60', 'ionInput');
    expect(s.save().disabled).toBe(true);
  });

  // A read that failed never passes for the business's settings (no proposed values to save).
  it('a read that fails says so with «Retry» instead of «Loading…», with no form; «Retry» asks again', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId('staff.settings.get'), 'boom'));
    await flush();
    expect(s.find('staff-settings-load-error').text()).toContain('msg boom');
    expect(s.find('staff-settings-loading').exists()).toBe(false);
    expect(s.find('staff-settings-form').exists()).toBe(false);
    const streams = s.net.streams.length;
    await click(s.find('staff-settings-retry').element);
    await s.clock.advance(3000);
    expect(s.net.streams.length).toBeGreaterThan(streams);
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
    expect([
      s.find('staff-settings-workday').text(),
      s.find('staff-settings-workday-intro').text(),
      s.field('default_work_start').label,
      s.field('default_break_duration').helperText,
      s.save().textContent?.trim(),
    ]).toEqual([
      'Jornada por defecto',
      'Un horario nuevo propone esta jornada de lunes a viernes, con el descanso en mitad del día.',
      'Inicio de jornada (HH:MM)',
      'De 0 (sin descanso) a 480 minutos, más corto que la jornada.',
      'Guardar',
    ]);
  });
});
