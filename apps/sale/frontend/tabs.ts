// The sections of Sales & POS, painted as the footer tabbar of each sale page (AppPage `tabs`): the
// same entries, order, icons and paths as the app's menu (`navigation` in apps.py). Each tab follows its
// route; picking one replaces the address, so Back leaves Sales & POS instead of walking its tabs.
// Registered icons only: the old `storefront` (filled) and `chatbubble-ellipses-outline` wait in
// apps/sale/UI-REQUESTS.md.
import type { ShellTab } from '@erplora/ui/shell';

export const SALE_TABS: readonly (Omit<ShellTab, 'label'> & { labelKey: string })[] = Object.freeze([
  { id: 'pos', icon: 'ion:storefront-outline', to: '/sale/pos', labelKey: 'sale.tabs.pos' },
  { id: 'sales', icon: 'ion:cart-outline', to: '/sale/sales', labelKey: 'sale.tabs.sales' },
  { id: 'quick_notes', icon: 'ion:chatbubbles-outline', to: '/sale/quick-notes', labelKey: 'sale.tabs.quickNotes' },
  { id: 'departments', icon: 'ion:grid-outline', to: '/sale/departments', labelKey: 'sale.tabs.departments' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/sale/settings', labelKey: 'sale.tabs.settings' },
]);

/** The tabs with their labels in the reader's language (`saleTabs($t)` in a template). */
export function saleTabs(t: (key: string) => string): ShellTab[] {
  return SALE_TABS.map(({ labelKey, ...tab }) => ({ ...tab, label: t(labelKey) }));
}
