// Tables → Settings (WORKBOOK «Pantallas · Ajustes»; TABLE-F08): only for whoever may save them.
// «Ask for the guests when seating a table», «Amber warning (minutes)» and «Red warning (minutes)», live
// (the factory values until the business saves); «Save» sends only the fields touched and changed and
// says «Settings saved.»; a refusal goes under its field.
import { describe, expect, it } from 'vitest';

import { click, ionChecked, ionValue, MANAGER, type MountOptions, mountTable } from '../__tests__/mount-table';
import { SETTINGS } from '../__tests__/tables';
import SettingsPage from './SettingsPage.vue';

const OP = 'table.settings.get';

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; errorText?: string; helperText?: string; disabled?: boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountTable(SettingsPage, { path: '/table/settings', ...options });
  await m.live();
  const field = (name: string) => m.inDoc(`table-settings-${name}`) as Control;
  return { ...m, field, show: (data: unknown) => m.result(OP, data) };
}

describe('SettingsPage', () => {
  it('paints the room settings with the old labels', async () => {
    const s = await setup();
    expect(s.field('loading')?.textContent).toContain('Loading…');
    await s.show(SETTINGS);
    expect(s.field('prompt_guests_on_seat').textContent?.trim()).toBe('Ask for the guests when seating a table');
    expect(s.field('prompt_guests_on_seat').checked).toBe(true);
    expect([s.field('timer_warning_minutes').label, s.field('timer_critical_minutes').label]).toEqual([
      'Amber warning (minutes)',
      'Red warning (minutes)',
    ]);
    expect([s.field('timer_warning_minutes').value, s.field('timer_critical_minutes').value]).toEqual(['60', '90']);
    expect(s.field('save').disabled).toBe(true);
  });

  it('saves only what was touched and changed, and says so', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    s.answer(200, { ...SETTINGS, prompt_guests_on_seat: false, timer_warning_minutes: 45 });
    await ionChecked(s.field('prompt_guests_on_seat'), false);
    await ionValue(s.field('timer_warning_minutes'), '45', 'ionInput');
    await click(s.field('save'));
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/table/settings', query: {}, body: { prompt_guests_on_seat: false, timer_warning_minutes: 45 } },
    ]);
    expect(s.field('saved')?.textContent).toContain('Settings saved.');
  });

  it('a refusal goes under its field', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    const refusal = { error: { code: 'invalid_payload', message: 'The red warning cannot come before the amber one.', fields: { timer_critical_minutes: 'The red warning cannot come before the amber one.' } } };
    s.answer(422, refusal);
    await ionValue(s.field('timer_warning_minutes'), '120', 'ionInput');
    await click(s.field('save'));
    expect(s.field('timer_critical_minutes').errorText).toBe('The red warning cannot come before the amber one.');
    expect(s.field('save-error')?.textContent).toContain('The red warning cannot come before the amber one.');
  });

  describe('a refusal by fields (hub#854, as FormModal and the Services settings do: ui#102, hub#821)', () => {
    const REFUSAL = {
      error: {
        code: 'invalid_payload',
        message: 'Invalid payload',
        fields: {
          timer_warning_minutes: 'Ensure this value is less than or equal to 600.',
          timer_critical_minutes: 'The red warning cannot come before the amber one.',
        },
      },
    };

    /** Saves an amber of 700 minutes and a red before it, and the server refuses both fields. */
    async function refused() {
      const s = await setup();
      await s.show(SETTINGS);
      s.answer(422, REFUSAL);
      await ionValue(s.field('timer_warning_minutes'), '700', 'ionInput');
      await ionValue(s.field('timer_critical_minutes'), '30', 'ionInput');
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
      expect([s.says('timer_warning_minutes'), s.says('timer_critical_minutes')]).toEqual([
        'Ensure this value is less than or equal to 600.',
        'The red warning cannot come before the amber one.',
      ]);
      await ionValue(s.field('timer_critical_minutes'), '120', 'ionInput');
      expect(s.notice()).toBe(false);
      expect([s.says('timer_critical_minutes'), s.marked('timer_critical_minutes')]).toEqual(['', false]);
      expect([s.says('timer_warning_minutes'), s.marked('timer_warning_minutes')]).toEqual(['Ensure this value is less than or equal to 600.', true]);
    });

    it('a switch is a change too: the notice goes, the fields keep their messages', async () => {
      const s = await refused();
      await ionChecked(s.field('prompt_guests_on_seat'), false);
      expect(s.notice()).toBe(false);
      expect([s.says('timer_warning_minutes'), s.says('timer_critical_minutes')]).toEqual([
        'Ensure this value is less than or equal to 600.',
        'The red warning cannot come before the amber one.',
      ]);
    });

    it('the next refusal says it all again', async () => {
      const s = await refused();
      await ionValue(s.field('timer_warning_minutes'), '800', 'ionInput');
      await ionValue(s.field('timer_critical_minutes'), '20', 'ionInput');
      expect([s.notice(), s.says('timer_warning_minutes'), s.says('timer_critical_minutes')]).toEqual([false, '', '']);
      await click(s.field('save'));
      expect(s.notice()).toBe(true);
      expect([s.says('timer_warning_minutes'), s.says('timer_critical_minutes'), s.marked('timer_critical_minutes')]).toEqual([
        'Ensure this value is less than or equal to 600.',
        'The red warning cannot come before the amber one.',
        true,
      ]);
    });

    it('a refusal that names no field stays until the next try: nothing else says it', async () => {
      const s = await setup();
      await s.show(SETTINGS);
      s.answer(409, { error: { code: 'conflict', message: 'Someone else is saving them.' } });
      await ionValue(s.field('timer_warning_minutes'), '45', 'ionInput');
      await click(s.field('save'));
      await ionValue(s.field('timer_warning_minutes'), '50', 'ionInput');
      expect(s.field('save-error')?.textContent).toContain('Someone else is saving them.');
    });
  });

  it('whoever may not save them is told so', async () => {
    const s = await setup({ session: MANAGER });
    expect(s.field('forbidden')).not.toBeNull();
    expect(s.field('save')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(SETTINGS);
    expect([s.field('timer_warning_minutes').label, s.field('save').textContent?.trim()]).toEqual(['Aviso ámbar (minutos)', 'Guardar']);
    expect(s.field('prompt_guests_on_seat').textContent?.trim()).toBe('Preguntar los comensales al sentar una mesa');
  });
});
