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

  // As the old settings: each switch says what it does first and sits at the end of its row.
  it('each switch is its label, then the switch at the end of the row', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    const toggle = s.field('allow_overlapping') as Control & { labelPlacement?: string; justify?: string };
    expect([toggle.labelPlacement, toggle.justify]).toEqual(['start', 'space-between']);
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

  describe('a refusal by fields (hub#854, as FormModal and the Services settings do: ui#102, hub#821)', () => {
    const REFUSAL = {
      error: {
        code: 'invalid_payload',
        message: 'Invalid payload',
        fields: {
          calendar_end_hour: 'The calendar has to end after it starts.',
          slot_interval: 'Ensure this value is greater than or equal to 5.',
        },
      },
    };

    /** Saves an upside-down calendar and a 1-minute slot, and the server refuses both fields. */
    async function refused() {
      const s = await setup();
      await s.show(SETTINGS);
      s.answer(422, REFUSAL);
      await ionValue(s.field('calendar_end_hour'), '7', 'ionInput');
      await ionValue(s.field('slot_interval'), '1', 'ionInput');
      await click(s.field('save'));
      /** Whether the red notice is on screen. */
      const notice = () => s.field('save-error') !== null;
      const says = (name: string) => s.field(name).errorText ?? '';
      const marked = (name: string) => s.field(name).classList.contains('ion-invalid');
      return { ...s, notice, says, marked };
    }

    it('the notice goes as soon as something is changed, and a field’s message as soon as that field is', async () => {
      const s = await refused();
      expect(s.notice()).toBe(true);
      expect([s.says('calendar_end_hour'), s.says('slot_interval')]).toEqual([
        'The calendar has to end after it starts.',
        'Ensure this value is greater than or equal to 5.',
      ]);
      await ionValue(s.field('calendar_end_hour'), '20', 'ionInput');
      expect(s.notice()).toBe(false);
      expect([s.says('calendar_end_hour'), s.marked('calendar_end_hour')]).toEqual(['', false]);
      expect([s.says('slot_interval'), s.marked('slot_interval')]).toEqual(['Ensure this value is greater than or equal to 5.', true]);
    });

    it('a switch is a change too: the notice goes, the fields keep their messages', async () => {
      const s = await refused();
      await ionChecked(s.field('allow_overlapping'), false);
      expect(s.notice()).toBe(false);
      expect([s.says('calendar_end_hour'), s.says('slot_interval')]).toEqual([
        'The calendar has to end after it starts.',
        'Ensure this value is greater than or equal to 5.',
      ]);
    });

    it('the next refusal says it all again', async () => {
      const s = await refused();
      await ionValue(s.field('calendar_end_hour'), '6', 'ionInput');
      await ionValue(s.field('slot_interval'), '2', 'ionInput');
      expect([s.notice(), s.says('calendar_end_hour'), s.says('slot_interval')]).toEqual([false, '', '']);
      await click(s.field('save'));
      expect(s.notice()).toBe(true);
      expect([s.says('calendar_end_hour'), s.says('slot_interval'), s.marked('calendar_end_hour')]).toEqual([
        'The calendar has to end after it starts.',
        'Ensure this value is greater than or equal to 5.',
        true,
      ]);
    });

    it('a refusal that names no field stays until the next try: nothing else says it', async () => {
      const s = await setup();
      await s.show(SETTINGS);
      s.answer(409, { error: { code: 'conflict', message: 'Someone else is saving them.' } });
      await ionValue(s.field('slot_interval'), '30', 'ionInput');
      await click(s.field('save'));
      await ionValue(s.field('slot_interval'), '45', 'ionInput');
      expect(s.field('save-error')?.textContent).toContain('Someone else is saving them.');
    });
  });

  it('is closed to who may not change them', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.field('forbidden')?.textContent).toContain('You do not have permission');
  });
});
