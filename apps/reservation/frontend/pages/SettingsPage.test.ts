// Reservations → Settings (WORKBOOK «Pantallas · Ajustes»; RESERVATION-F03, F04): only for whoever may save
// them. The rules for every reservation (default duration, automatic confirmation, phone and email
// required, minutes to release an unconfirmed one) and for the bookings the guest makes herself (guests,
// notice, days ahead), live (the factory values until the business saves); «Save» sends only the fields
// touched and changed and says «Settings saved.»; a refusal goes under its field.
import { describe, expect, it } from 'vitest';

import { click, EMPLOYEE, ionChecked, ionValue, type MountOptions, mountReservation } from '../__tests__/mount-reservation';
import { settingsOut } from '../__tests__/rows';
import SettingsPage from './SettingsPage.vue';

const OP = 'reservation.settings.get';

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; errorText?: string; disabled?: boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountReservation(SettingsPage, { path: '/reservation/settings', ...options });
  await m.live();
  const field = (name: string) => m.inDoc(`reservation-settings-${name}`) as Control;
  return { ...m, field, show: (data: unknown) => m.result(OP, data) };
}

describe('SettingsPage', () => {
  it('paints the book’s rules', async () => {
    const s = await setup();
    expect(s.field('loading')?.textContent).toContain('Loading…');
    await s.show(settingsOut());
    expect(
      ['default_duration_minutes', 'no_show_window_minutes', 'min_party_size', 'max_party_size', 'min_advance_hours', 'max_advance_days'].map((name) => [
        s.field(name).label,
        s.field(name).value,
      ]),
    ).toEqual([
      ['Default duration (minutes)', '120'],
      ['Release an unconfirmed reservation after (minutes)', '15'],
      ['Minimum guests', '1'],
      ['Maximum guests', '20'],
      ['Minimum notice (hours)', '1'],
      ['Maximum days ahead', '30'],
    ]);
    expect([s.field('auto_confirm').checked, s.field('require_phone').checked, s.field('require_email').checked]).toEqual([false, true, false]);
    expect(s.field('save').disabled).toBe(true);
  });

  it('saves only what was touched and changed, and says so', async () => {
    const s = await setup();
    await s.show(settingsOut());
    s.answer(200, settingsOut({ auto_confirm: true, max_party_size: 12 }));
    await ionChecked(s.field('auto_confirm'), true);
    await ionValue(s.field('max_party_size'), '12', 'ionInput');
    await click(s.field('save'));
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/reservation/settings', query: {}, body: { auto_confirm: true, max_party_size: 12 } }]);
    expect(s.field('saved')?.textContent).toContain('Settings saved.');
  });

  it('a refusal goes under its field', async () => {
    const s = await setup();
    await s.show(settingsOut());
    const message = 'The minimum guests cannot be more than the maximum.';
    s.answer(422, { error: { code: 'invalid_payload', message, fields: { min_party_size: message } } });
    await ionValue(s.field('min_party_size'), '30', 'ionInput');
    await click(s.field('save'));
    expect(s.field('min_party_size').errorText).toBe(message);
    expect(s.field('save-error')?.textContent).toContain(message);
  });

  it('whoever may not save them is told so', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.field('forbidden')).not.toBeNull();
    expect(s.field('save')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(settingsOut());
    expect([s.field('max_party_size').label, s.field('save').textContent?.trim()]).toEqual(['Comensales máximos', 'Guardar']);
    expect(s.field('auto_confirm').textContent?.trim()).toBe('Confirmar solas las reservas nuevas');
  });
});
