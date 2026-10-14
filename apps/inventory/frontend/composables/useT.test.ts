// Translations in a script, not only in a template: hub-next does not depend on vue-i18n (only
// @erplora/ui does), so a component reads the shell's i18n through its own `$t` and `$i18n`, the
// public API the i18n plugin installs (UI-REQUESTS.md asks @erplora/ui to re-export `useI18n`).
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { mountInventory } from '../__tests__/mount-inventory';
import { useT } from './useT';

async function probe(locale: 'en' | 'es') {
  let api: ReturnType<typeof useT> | undefined;
  const Probe = defineComponent({
    setup() {
      api = useT();
      return () => h('div');
    },
  });
  await mountInventory(Probe, { locale });
  return api!;
}

describe('useT', () => {
  it('translates with the page language, plurals and placeholders included', async () => {
    const en = await probe('en');
    expect(en.t('inventory.tabs.products')).toBe('Products');
    expect(en.t('inventory.dashboard.withoutCost', 2)).toBe('2 products without recorded cost: the value shown is partial');
    expect(en.t('inventory.form.editTitle', { name: 'Coffee' })).toBe('Editing product — Coffee');
    expect(en.locale.value).toBe('en');
    const es = await probe('es');
    expect(es.t('inventory.tabs.products')).toBe('Productos');
    expect(es.locale.value).toBe('es');
  });

  it('outside a component it says so', () => {
    expect(() => useT()).toThrow(/setup/);
  });
});
