// The inventory's sections as the footer tabbar of every inventory page (the old module's navigation:
// Dashboard, Products, Movements, Categories, plus the Settings tab the old shell generated), each
// tab following its route. Settings is only for whoever can manage the inventory settings
// (WORKBOOK «Ajustes»). Icons are registered ones (UI-REQUESTS.md asks for the old stats-chart and
// pricetags).
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { EMPLOYEE, mountInventory } from '../__tests__/mount-inventory';
import { useInventoryTabs } from './useInventoryTabs';

async function tabsFor(options: Parameters<typeof mountInventory>[1] = {}) {
  let tabs: ReturnType<typeof useInventoryTabs> | undefined;
  const Probe = defineComponent({
    setup() {
      tabs = useInventoryTabs();
      return () => h('div');
    },
  });
  await mountInventory(Probe, options);
  return tabs!.value;
}

describe('useInventoryTabs', () => {
  it('gives a manager the five sections, each with its icon and route', async () => {
    expect(await tabsFor()).toEqual([
      { id: 'dashboard', label: 'Dashboard', icon: 'ion:speedometer-outline', to: '/inventory/dashboard' },
      { id: 'products', label: 'Products', icon: 'ion:cube-outline', to: '/inventory/products' },
      { id: 'movements', label: 'Movements', icon: 'ion:swap-vertical-outline', to: '/inventory/movements' },
      { id: 'categories', label: 'Categories', icon: 'ion:list-outline', to: '/inventory/categories' },
      { id: 'settings', label: 'Settings', icon: 'ion:settings-outline', to: '/inventory/settings' },
    ]);
  });

  it('does not show Settings to whoever cannot manage the settings', async () => {
    expect((await tabsFor({ session: EMPLOYEE })).map((tab) => tab.id)).toEqual(['dashboard', 'products', 'movements', 'categories']);
  });

  it('speaks Spanish', async () => {
    expect((await tabsFor({ locale: 'es' })).map((tab) => tab.label)).toEqual(['Panel', 'Productos', 'Movimientos', 'Categorías', 'Ajustes']);
  });
});
