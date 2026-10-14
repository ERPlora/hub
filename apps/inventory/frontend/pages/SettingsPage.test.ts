// Inventory → Settings (WORKBOOK «Ajustes», INVENTORY-F19): header «Inventory» with «Allow selling
// without stock», «Low stock threshold» (whole units, with its explanation) and «Track stock», and
// «Save» → «Settings saved.». The values are the business's (`inventory.config.get`, live): while
// loading «Loading settings…»; a failed load says so with «Retry» and never shows the factory values
// as the business's. Only whoever can manage the inventory settings sees it: anyone else typing its
// address gets «This page does not exist»; if the person changes with the tab open (shift change),
// the fields lock, «Save» goes and the page says why.
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { IonInput, IonToggle } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

import { EMPLOYEE, errorFrame, flush, MANAGER, type MountOptions, mountInventory, ok, refusal, subId } from '../__tests__/mount-inventory';
import SettingsPage from './SettingsPage.vue';

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: toasts.success,
  toastError: toasts.error,
}));

afterEach(() => {
  toasts.success.mockReset();
  toasts.error.mockReset();
});

type Control = HTMLElement & { checked?: boolean; value?: unknown; disabled?: boolean; errorText?: string; helperText?: string };

const CONFIG = { allow_sell_without_stock: false, low_stock_threshold: 10, track_stock: true };

async function setup(options: MountOptions = {}) {
  const m = await mountInventory(SettingsPage, { path: '/inventory/settings', ...options });
  const call = await m.live().catch(() => undefined);
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const field = (id: string) => m.wrapper.get(`[data-testid="inventory-settings-${id}"]`);
  const show = (data: unknown, rev?: number) => m.result(call!, 'inventory.config.get', data, rev);
  async function save() {
    // ion-button submits its form in a browser; happy-dom has no form association for it.
    await testid('inventory-settings-form').trigger('submit');
    await flush();
  }
  return { ...m, call, testid, field, show, save };
}

describe('SettingsPage', () => {
  it('is the inventory page on its Settings tab, following inventory.config.get, «Loading settings…» first', async () => {
    const s = await setup();
    const app = s.wrapper.findComponent(AppPage);
    expect(app.props('title')).toBe('Inventory');
    expect((app.props('tabs') as Array<{ id: string }>).at(-1)!.id).toBe('settings');
    expect(s.params('inventory.config.get')).toEqual([{}]);
    expect(s.testid('inventory-settings-loading').text()).toBe('Loading settings…');
    expect(s.testid('inventory-settings-form').exists()).toBe(false);
  });

  it('paints the business values under the «Inventory» header, each with its explanation', async () => {
    const s = await setup();
    await s.show({ allow_sell_without_stock: true, low_stock_threshold: 4, track_stock: false });
    expect(s.wrapper.get('[data-testid="inventory-settings-form"] h2').text()).toBe('Inventory');
    const toggles = s.wrapper.findAllComponents(IonToggle);
    expect(toggles.map((t) => [t.attributes('data-testid'), t.props('modelValue'), t.find('span').text()])).toEqual([
      ['inventory-settings-allow-negative', true, 'Allow selling without stock'],
      ['inventory-settings-track-stock', false, 'Track stock'],
    ]);
    const threshold = s.wrapper.findComponent(IonInput);
    expect([threshold.props('label'), threshold.props('modelValue'), threshold.props('helperText'), threshold.attributes('mode'), threshold.props('fill')]).toEqual([
      'Low stock threshold',
      '4',
      'In whole units: the threshold a product created without its own starts with. Changing it does not touch the products that already exist.',
      'md',
      'outline',
    ]);
    expect(s.testid('inventory-settings-allow-negative-help').text()).toContain('a sale lowers the stock even below zero');
  });

  it('«Save» sends the three settings and says «Settings saved.»', async () => {
    const s = await setup();
    await s.show(CONFIG);
    s.net.onApi(() => ok({ allow_sell_without_stock: true, low_stock_threshold: 6, track_stock: true }));
    await s.wrapper.findAllComponents(IonToggle)[0].setValue(true);
    await s.wrapper.findComponent(IonInput).setValue('6');
    await s.save();
    const [call] = s.calls('/api/inventory/config');
    expect(call.init.method).toBe('POST');
    expect(s.body(call)).toEqual({ allow_sell_without_stock: true, low_stock_threshold: 6, track_stock: true });
    expect(toasts.success).toHaveBeenCalledWith('Settings saved.');
  });

  it('a refused save says «The settings could not be saved.» and paints a field message under its field', async () => {
    const s = await setup();
    await s.show(CONFIG);
    s.net.onApi(() => refusal(422, 'invalid_payload', 'Invalid payload', { low_stock_threshold: 'Input should be a valid integer' }));
    await s.wrapper.findComponent(IonInput).setValue('2.5');
    await s.save();
    expect((s.field('threshold').element as Control).errorText).toBe('Input should be a valid integer');
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'inventory-settings-save-error')!;
    expect(banner.text()).toContain('The settings could not be saved.');
    expect(toasts.success).not.toHaveBeenCalled();
  });

  it('«Save» is off while the threshold is empty', async () => {
    const s = await setup();
    await s.show(CONFIG);
    await s.wrapper.findComponent(IonInput).setValue('');
    expect((s.testid('inventory-settings-save').element as Control).disabled).toBe(true);
  });

  it('a new result does not overwrite what is being changed; untouched it follows the server', async () => {
    const s = await setup();
    await s.show(CONFIG);
    await s.show({ ...CONFIG, low_stock_threshold: 12 }, 2);
    expect(s.wrapper.findComponent(IonInput).props('modelValue')).toBe('12');
    await s.wrapper.findComponent(IonInput).setValue('3');
    await s.show({ ...CONFIG, low_stock_threshold: 20 }, 3);
    expect(s.wrapper.findComponent(IonInput).props('modelValue')).toBe('3');
  });

  it('a failed load says so with Retry, never the factory values', async () => {
    const s = await setup();
    s.call!.push(errorFrame(subId(s.client, 'inventory.config.get'), 'inventory.boom'));
    await flush();
    expect(s.testid('inventory-settings-load-error').text()).toContain('The settings could not be loaded.');
    expect(s.testid('inventory-settings-form').exists()).toBe(false);
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.testid('inventory-settings-retry').trigger('click');
    expect(reconnect).toHaveBeenCalled();
  });

  it('whoever cannot manage the settings gets «This page does not exist» and asks nothing', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.testid('inventory-settings-not-found').exists()).toBe(true);
    expect(s.wrapper.text()).toContain('This page does not exist');
    expect(s.params('inventory.config.get')).toEqual([]);
  });

  it('if the person loses the permission with the tab open, the fields lock and «Save» goes', async () => {
    const me = ref(MANAGER);
    const s = await setup({ sessionRef: me });
    await s.show(CONFIG);
    me.value = EMPLOYEE;
    await flush();
    expect(s.testid('inventory-settings-save').exists()).toBe(false);
    expect(s.wrapper.findAllComponents(IonToggle).every((t) => t.props('disabled'))).toBe(true);
    expect(s.wrapper.findComponent(IonInput).props('disabled')).toBe(true);
    expect(s.testid('inventory-settings-no-permission').text()).toContain('You do not have permission to change these settings.');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.testid('inventory-settings-loading').text()).toBe('Cargando ajustes…');
    await s.show(CONFIG);
    expect(s.wrapper.findAllComponents(IonToggle).map((t) => t.find('span').text())).toEqual(['Permitir vender sin stock', 'Controlar stock']);
    expect(s.wrapper.findComponent(IonInput).props('label')).toBe('Umbral de stock bajo');
    expect(s.testid('inventory-settings-save').text()).toBe('Guardar');
  });
});
