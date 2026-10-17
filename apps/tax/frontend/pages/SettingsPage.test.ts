// Taxes → Settings (TAX-F11, pm#629 VF-17; the WORKBOOK's «Ajustes»): «Your business's tax region» with the
// business's country (read only: it is the one of its ERPlora account) and «Tax region» — «Whole country
// (VAT)», «Canary Islands (IGIC)», «Ceuta (IPSI)» or «Melilla (IPSI)» —, and «Save» → «Tax region saved.».
// The values are the business's (`tax.settings.get`, live): «Loading the tax settings…» first; a failed load
// says so with «Retry» and shows no region as the business's. Whoever only views taxes reads it, locked.
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, errorFrame, flush, type MountOptions, mountTax } from '../__tests__/mount-tax';
import SettingsPage from './SettingsPage.vue';

const toasts = vi.hoisted(() => ({ success: vi.fn() }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: toasts.success,
}));

afterEach(() => toasts.success.mockReset());

const OP = 'tax.settings.get';
const REGIONS = ['ES-CN', 'ES-CE', 'ES-ML'];
const SETTINGS = { country_code: 'ES', region_code: null, regions: REGIONS, updated_at: null };

type Control = HTMLElement & { value?: unknown; disabled?: boolean; errorText?: string };

async function setup(options: MountOptions = {}) {
  const m = await mountTax(SettingsPage, { path: '/tax/settings', ...options });
  const call = await m.live();
  const select = () => m.wrapper.findComponent(IonSelect);
  const show = (data: unknown, rev?: number) => m.result(OP, data, {}, rev);
  async function choose(region: string) {
    await select().vm.$emit('update:modelValue', region);
    await flush();
  }
  async function save() {
    // ion-button submits its form in a browser; happy-dom has no form association for it.
    await m.find('tax-settings-form').trigger('submit');
    await flush();
    await flush();
  }
  return { ...m, call, select, show, choose, save };
}

describe('SettingsPage', () => {
  it('is the Taxes page on its Settings tab, following tax.settings.get, «Loading the tax settings…» first', async () => {
    const s = await setup();
    const app = s.wrapper.findComponent(AppPage);
    expect(app.props('title')).toBe('Taxes');
    expect((app.props('tabs') as Array<{ id: string }>).at(-1)!.id).toBe('settings');
    expect(s.params(OP)).toEqual([{}]);
    expect(s.find('tax-settings-loading').text()).toBe('Loading the tax settings…');
    expect(s.find('tax-settings-form').exists()).toBe(false);
  });

  it('paints the country read only and the region picker with the territories of the country', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    expect(s.wrapper.get('[data-testid="tax-settings-form"] h2').text()).toBe("Your business's tax region");
    expect(s.find('tax-settings-country').text()).toContain('Spain');
    expect(s.find('tax-settings-country-help').text()).toBe('It is the country of your ERPlora account.');
    const select = s.select();
    expect([select.props('label'), select.props('modelValue'), select.props('interface'), select.attributes('mode'), select.props('fill')]).toEqual([
      'Tax region',
      '',
      'popover',
      'md',
      'outline',
    ]);
    expect(s.wrapper.findAllComponents(IonSelectOption).map((o) => [o.props('value'), o.text()])).toEqual([
      ['', 'Whole country (VAT)'],
      ['ES-CN', 'Canary Islands (IGIC)'],
      ['ES-CE', 'Ceuta (IPSI)'],
      ['ES-ML', 'Melilla (IPSI)'],
    ]);
    expect(s.find('tax-settings-region-help').text()).toContain('create one per category in Rules');
  });

  it('«Save» keeps the region chosen and says «Tax region saved.»; the whole country sends none', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    expect((s.find('tax-settings-save').element as Control).disabled).toBe(true);
    s.answer(200, { ...SETTINGS, region_code: 'ES-CN', updated_at: '2026-10-17T10:00:00Z' });
    await s.choose('ES-CN');
    expect((s.find('tax-settings-save').element as Control).disabled).toBe(false);
    await s.save();
    expect(s.sent().filter((c) => c.path === '/api/tax/settings')).toEqual([
      { method: 'POST', path: '/api/tax/settings', query: {}, body: { region_code: 'ES-CN' } },
    ]);
    expect(toasts.success).toHaveBeenCalledWith('Tax region saved.');
    await s.show({ ...SETTINGS, region_code: 'ES-CN' }, 2);
    s.answer(200, SETTINGS);
    await s.choose('');
    await s.save();
    expect(s.sent().filter((c) => c.path === '/api/tax/settings').at(-1)!.body).toEqual({ region_code: null });
  });

  it('a refused save says «The tax region could not be saved.» and paints the message under the picker', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    s.answer(422, {
      error: { code: 'tax.region_not_available', message: 'This region has no taxes of its own.', fields: { region_code: 'This region has no taxes of its own.' } },
    });
    await s.choose('ES-ML');
    await s.save();
    expect((s.select().element as Control).errorText).toBe('This region has no taxes of its own.');
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'tax-settings-save-error')!;
    expect(banner.text()).toContain('The tax region could not be saved.');
    expect(toasts.success).not.toHaveBeenCalled();
  });

  it('a new result does not overwrite what is being chosen; untouched it follows the server', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await s.show({ ...SETTINGS, region_code: 'ES-CE' }, 2);
    expect(s.select().props('modelValue')).toBe('ES-CE');
    await s.choose('ES-CN');
    await s.show({ ...SETTINGS, region_code: 'ES-ML' }, 3);
    expect(s.select().props('modelValue')).toBe('ES-CN');
  });

  it('a failed load says so with Retry and shows no region as the business\'s', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    expect(s.find('tax-settings-load-error').text()).toContain('The tax settings could not be loaded.');
    expect(s.find('tax-settings-retry').exists()).toBe(true);
    expect(s.find('tax-settings-form').exists()).toBe(false);
  });

  it('whoever only views taxes reads the region, locked, and is told why', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show({ ...SETTINGS, region_code: 'ES-CN' });
    expect(s.select().props('modelValue')).toBe('ES-CN');
    expect((s.select().element as Control).disabled).toBe(true);
    expect(s.find('tax-settings-read-only').text()).toBe('You can see the tax region but not change it.');
    expect(s.find('tax-settings-save').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(SETTINGS);
    expect(s.wrapper.get('[data-testid="tax-settings-form"] h2').text()).toBe('Territorio fiscal del negocio');
    expect(s.find('tax-settings-country').text()).toContain('España');
    expect(s.wrapper.findAllComponents(IonSelectOption).map((o) => o.text())).toEqual([
      'Todo el país (IVA)',
      'Canarias (IGIC)',
      'Ceuta (IPSI)',
      'Melilla (IPSI)',
    ]);
  });
});
