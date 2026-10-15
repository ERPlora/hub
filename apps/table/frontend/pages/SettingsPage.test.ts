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
