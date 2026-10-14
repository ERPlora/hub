// The inventory's sections, painted by `AppPage` as the footer tabbar of every inventory page: the
// old module's navigation (Dashboard, Products, Movements, Categories) plus the Settings tab the old
// shell generated, which only whoever can manage the inventory settings sees (WORKBOOK «Ajustes»).
// Each tab follows its route. Icons: registered stand-ins for the old `stats-chart` and `pricetags`
// until the shell registers them (UI-REQUESTS.md).
import type { ShellTab } from '@erplora/ui/shell';
import { useSession } from '@erplora/ui/shell';
import { computed, type ComputedRef } from 'vue';

import { useT } from './useT';

export function useInventoryTabs(): ComputedRef<ShellTab[]> {
  const { t } = useT();
  const session = useSession();
  return computed(() => [
    { id: 'dashboard', label: t('inventory.tabs.dashboard'), icon: 'ion:speedometer-outline', to: '/inventory/dashboard' },
    { id: 'products', label: t('inventory.tabs.products'), icon: 'ion:cube-outline', to: '/inventory/products' },
    { id: 'movements', label: t('inventory.tabs.movements'), icon: 'ion:swap-vertical-outline', to: '/inventory/movements' },
    { id: 'categories', label: t('inventory.tabs.categories'), icon: 'ion:list-outline', to: '/inventory/categories' },
    ...(session.can('inventory.manage_settings')
      ? [{ id: 'settings', label: t('inventory.tabs.settings'), icon: 'ion:settings-outline', to: '/inventory/settings' }]
      : []),
  ]);
}
