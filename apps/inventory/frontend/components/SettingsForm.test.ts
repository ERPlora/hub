// The inventory settings form on its own (the Settings page mounts it only for whoever can manage
// the settings, so nobody else subscribes): it follows `inventory.config.get` and saves through
// `inventory.config.update`. Its whole behaviour is specified in pages/SettingsPage.test.ts.
import { IonToggle } from '@ionic/vue';
import { describe, expect, it, vi } from 'vitest';

import { mountInventory } from '../__tests__/mount-inventory';
import SettingsForm from './SettingsForm.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(),
}));

describe('SettingsForm', () => {
  it('follows inventory.config.get and paints its two switches once it arrives', async () => {
    const m = await mountInventory(SettingsForm);
    const call = await m.live();
    expect(m.params('inventory.config.get')).toEqual([{}]);
    await m.result(call, 'inventory.config.get', { allow_sell_without_stock: false, low_stock_threshold: 10, track_stock: true });
    expect(m.wrapper.findAllComponents(IonToggle).map((t) => t.props('modelValue'))).toEqual([false, true]);
  });
});
