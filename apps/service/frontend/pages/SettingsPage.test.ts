// Services → Settings (WORKBOOK «Pantallas · Ajustes de Servicios»; SERVICE-F11): only for whoever may
// save them. The values come live (the factory ones until the business saves); «Save» sends only the
// fields the person touched and changed, says «Settings saved.», and a refusal goes under its field.
import { Combo, InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import type { SettingsOut } from '../operations';
import { click, ionChecked, ionValue, MANAGER, type MountOptions, mountService, settle } from '../__tests__/mount-service';
import SettingsPage from './SettingsPage.vue';

const OP = 'service.settings.get';
const SETTINGS: SettingsOut = {
  default_duration: 60,
  default_buffer_time: 0,
  default_tax_category_id: 't1',
  default_tax_category_key: 'service.generic',
  default_tax_category_name: 'Service — generic',
  show_prices: true,
  show_duration: true,
  allow_online_booking: true,
  updated_at: null,
};

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; errorText?: string; disabled?: boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountService(SettingsPage, { path: '/service/settings', ...options });
  await m.live();
  const field = (name: string) => m.inDoc(`service-settings-${name}`) as Control;
  const tax = () => m.wrapper.findComponent(Combo);
  return { ...m, field, tax, show: (data: unknown) => m.result(OP, data) };
}

describe('SettingsPage', () => {
  it('paints the settings with the old labels, the default tax category chosen', async () => {
    const s = await setup();
    expect(s.field('loading')?.textContent).toContain('Loading…');
    await s.show(SETTINGS);
    expect([s.field('default_duration').label, s.field('default_buffer_time').label, s.tax().props('label')]).toEqual([
      'Default duration (min)',
      'Default buffer time (min)',
      'Default tax category',
    ]);
    expect([s.field('default_duration').value, s.tax().props('modelValue')]).toEqual(['60', { id: 'service.generic', label: 'Service — generic' }]);
    expect([s.field('show_prices').textContent, s.field('show_duration').textContent, s.field('allow_online_booking').textContent]).toEqual([
      'Show prices',
      'Show duration',
      'Allow online booking',
    ]);
    expect(s.field('save').disabled).toBe(true);
  });

  it('saves only what was touched and changed, and says so', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    s.answer(200, { ...SETTINGS, default_duration: 45, show_prices: false, default_tax_category_key: null });
    await ionValue(s.field('default_duration'), '45', 'ionInput');
    await ionChecked(s.field('show_prices'), false);
    s.tax().vm.$emit('update:modelValue', null);
    await settle();
    await click(s.field('save'));
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/service/settings',
        query: {},
        body: { default_duration: 45, show_prices: false, default_tax_category_key: null },
      },
    ]);
    expect(s.field('saved')?.textContent).toContain('Settings saved.');
  });

  it('a refusal goes under its field', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { default_duration: 'Ensure this value is greater than or equal to 1.' } } });
    await ionValue(s.field('default_duration'), '0', 'ionInput');
    await click(s.field('save'));
    expect(s.field('default_duration').errorText).toBe('Ensure this value is greater than or equal to 1.');
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'service-settings-save-error');
    expect(banner?.props('heading')).toBe('The settings could not be saved.');
  });

  it('whoever may not save them is told so', async () => {
    const s = await setup({ session: MANAGER });
    expect(s.field('forbidden')).not.toBeNull();
    expect(s.field('save')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(SETTINGS);
    expect([s.field('default_duration').label, s.tax().props('label'), s.field('save').textContent?.trim()]).toEqual([
      'Duración por defecto (min)',
      'Categoría fiscal por defecto',
      'Guardar',
    ]);
  });
});
