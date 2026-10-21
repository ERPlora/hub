// Kitchen → Settings (WORKBOOK «Pantallas · Ajustes»; KITCHEN-F26): only for whoever may save them. «Show
// timer», «Amber warning (minutes)», «Red alert (minutes)», «Colour semaphore», «Sound on a new ticket»,
// «Sound volume (0-100)», «Sound tone» (with «Test sound»), «Print the pass when marked ready», «The kitchen
// works from the screen» and «Default order type», live; «Save» sends only what was touched and changed and
// says «Settings saved.»; a refusal goes under its field.
import { describe, expect, it, vi } from 'vitest';

import { SETTINGS } from '../__tests__/kitchen';
import { click, EMPLOYEE, errorFrame, flush, ionChecked, ionValue, type MountOptions, mountKitchen } from '../__tests__/mount-kitchen';
import SettingsPage from './SettingsPage.vue';

const play = vi.fn();
vi.mock('../lib/chime', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/chime')>()),
  Chime: class {
    play = play;
  },
}));

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; errorText?: string; disabled?: boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountKitchen(SettingsPage, { path: '/kitchen/settings', ...options });
  await m.live();
  const field = (name: string) => m.inDoc(`kitchen-settings-${name}`) as Control;
  return { ...m, field, show: (data: unknown) => m.result('kitchen.settings.get', data) };
}

describe('SettingsPage', () => {
  it('paints the settings with the old labels', async () => {
    const s = await setup();
    expect(s.field('loading')?.textContent).toContain('Loading settings…');
    await s.show(SETTINGS);
    expect(s.field('show_timer').textContent?.trim()).toBe('Show timer');
    expect([s.field('warning_minutes').label, s.field('critical_minutes').label, s.field('sound_volume').label]).toEqual([
      'Amber warning (minutes)',
      'Red alert (minutes)',
      'Sound volume (0-100)',
    ]);
    expect([s.field('warning_minutes').value, s.field('critical_minutes').value]).toEqual(['15', '30']);
    expect(s.field('works_from_screen').checked).toBe(true);
    expect(s.field('sound_tone').value).toBe('chime');
    expect(s.field('save').disabled).toBe(true);
  });

  it('saves only what was touched and changed, and says so', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    s.answer(200, { ...SETTINGS, print_pass: true, warning_minutes: 10, sound_tone: 'buzzer' });
    await ionChecked(s.field('print_pass'), true);
    await ionValue(s.field('warning_minutes'), '10', 'ionInput');
    await ionValue(s.field('sound_tone'), 'buzzer');
    await click(s.field('save'));
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/kitchen/settings', query: {}, body: { print_pass: true, warning_minutes: 10, sound_tone: 'buzzer' } },
    ]);
    expect(s.field('saved')?.textContent).toContain('Settings saved.');
  });

  it('a refusal goes under its field', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    const message = 'The amber warning has to come before the red one.';
    s.answer(422, { error: { code: 'invalid_field', message, fields: { warning_minutes: message } } });
    await ionValue(s.field('warning_minutes'), '40', 'ionInput');
    await click(s.field('save'));
    expect(s.field('warning_minutes').errorText).toBe(message);
    expect(s.field('save-error')?.textContent).toContain(message);
  });

  it('plays the tone chosen at the volume chosen', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await ionValue(s.field('sound_tone'), 'bell');
    await ionValue(s.field('sound_volume'), '90', 'ionInput');
    await click(s.field('test-sound'));
    expect(play).toHaveBeenCalledWith({ tone: 'bell', volume: 90 });
  });

  it('says it could not load, without the spinner, and offers Retry', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId('kitchen.settings.get'), 'boom'));
    await flush();
    expect(s.field('load-error')?.textContent).toContain('Could not load the settings.');
    expect(s.field('loading')).toBeNull();
    expect(s.field('retry')).not.toBeNull();
    // kitchen#12: a full-size touch target (44 px), never the small button.
    expect((s.field('retry') as HTMLElement & { size?: string }).size).toBeUndefined();
  });

  it('whoever may not save them is told so', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.field('forbidden')).not.toBeNull();
    expect(s.field('save')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(SETTINGS);
    expect([s.field('warning_minutes').label, s.field('save').textContent?.trim()]).toEqual(['Aviso ámbar (minutos)', 'Guardar']);
    expect(s.field('works_from_screen').textContent?.trim()).toBe('La cocina trabaja con la pantalla');
    // hub#1427, kitchen#159: the tone and the type are chosen by their words, never «chime» or «dine_in».
    const words = (name: string) => [...s.field(name).querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim());
    expect(words('sound_tone')).toEqual(['Campanilla', 'Timbre', 'Zumbador']);
    expect(words('default_order_type')).toEqual(['En sala', 'Para llevar', 'A domicilio']);
  });
});
