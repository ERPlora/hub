// The drawer settings (CASH_REGISTER-F01; WORKBOOK «Pantallas · Ajustes de Caja»): the heading «Cash
// register» and one row per setting — six switches and the auto-close hour (00:00 to 23:00) — and «Save»,
// which sends only what changed and says «Settings saved.». The values are the business's, live; a read
// that fails shows no values (never the factory ones as if they were the business's). Whoever may not
// change them sees them blocked, without «Save».
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, errorFrame, flush, ionToggle, ionValue, mountCash } from '../__tests__/mount-cash-register';
import SettingsCard from './SettingsCard.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const OP = 'cash_register.settings.get';
const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];
const FACTORY = {
  enable_cash_register: true,
  require_opening_balance: false,
  require_closing_balance: true,
  allow_negative_balance: false,
  require_blind_count: false,
  auto_close_enabled: false,
  auto_close_time: '04:00',
  updated_at: null,
};

async function setup(editable = true, locale: 'en' | 'es' = 'en') {
  const m = await mountCash(SettingsCard, { props: { editable }, locale });
  await m.live();
  const field = (key: string) => m.inDoc(`cash-register-setting-${key}`);
  return { ...m, field };
}

describe('SettingsCard', () => {
  it('says it is loading, then paints the business’s values', async () => {
    const s = await setup();
    expect(s.find('cash-register-settings-loading').text()).toBe('Loading settings…');
    await s.result(OP, FACTORY);
    expect(s.find('cash-register-settings-heading').text()).toBe('Cash register');
    expect(prop(s.field('require_closing_balance'), 'checked')).toBe(true);
    expect(prop(s.field('require_blind_count'), 'checked')).toBe(false);
    expect(prop(s.field('auto_close_time'), 'value')).toBe('04:00');
    expect(s.field('auto_close_time')?.querySelectorAll('ion-select-option')).toHaveLength(24);
  });

  it('«Save» sends only what changed and says «Settings saved.»', async () => {
    const s = await setup();
    await s.result(OP, FACTORY);
    expect(prop(s.inDoc('cash-register-settings-save'), 'disabled')).toBe(true);
    await ionToggle(s.field('require_blind_count'), true);
    await ionValue(s.field('auto_close_time'), '23:00');
    s.answer(200, { ...FACTORY, require_blind_count: true, auto_close_time: '23:00', updated_at: '2026-10-14T10:00:00Z' });
    await click(s.inDoc('cash-register-settings-save'));
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/cash_register/settings', query: {}, body: { require_blind_count: true, auto_close_time: '23:00' } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Settings saved.');
  });

  it('a refused save says so with the server’s words', async () => {
    const s = await setup();
    await s.result(OP, FACTORY);
    await ionToggle(s.field('allow_negative_balance'), true);
    s.answer(403, { error: { code: 'permission_denied', message: 'Permission “cash_register.manage_settings” is required.' } });
    await click(s.inDoc('cash-register-settings-save'));
    expect(s.find('cash-register-settings-save-error').text()).toContain('Could not save the settings.');
  });

  it('a failed read shows no values and offers to retry', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    expect(s.find('cash-register-settings-load-error').text()).toContain('Could not load the settings.');
    expect(s.field('require_blind_count')).toBeNull();
  });

  it('without the permission the values are blocked and there is no «Save»', async () => {
    const s = await setup(false);
    await s.result(OP, FACTORY);
    expect(prop(s.field('enable_cash_register'), 'disabled')).toBe(true);
    expect(s.inDoc('cash-register-settings-save')).toBeNull();
    expect(s.find('cash-register-settings-read-only').text()).toContain('You do not have permission');
  });

  it('speaks Spanish', async () => {
    const s = await setup(true, 'es');
    await s.result(OP, FACTORY);
    expect(s.find('cash-register-settings-label-enable_cash_register').text()).toBe('Activar caja');
    expect(s.inDoc('cash-register-settings-save')?.textContent?.trim()).toBe('Guardar');
  });
});
