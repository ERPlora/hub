// The three sections of Taxes, painted as the footer tabbar of each tax page (AppPage `tabs`): the
// same entries, order and paths as the app's menu (`navigation` in apps.py). Each tab follows its
// route; picking one replaces the address, so Back leaves Taxes instead of walking its tabs.
// Icons: registered ones only (`ion:list-outline` and `ion:swap-vertical-outline` stand in for the
// old `pricetags` and `swap-horizontal-outline`, asked for in apps/tax/UI-REQUESTS.md).
import type { ShellTab } from '@erplora/ui/shell';

export const TAX_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'categories', icon: 'ion:list-outline', to: '/tax/categories' },
  { id: 'rules', icon: 'ion:receipt-outline', to: '/tax/rules' },
  { id: 'aliases', icon: 'ion:swap-vertical-outline', to: '/tax/aliases' },
]);

/** The tabs with their labels in the reader's language (`taxTabs($t)` in a template). */
export function taxTabs(t: (key: string) => string): ShellTab[] {
  return TAX_TABS.map((tab) => ({ ...tab, label: t(`tax.tabs.${tab.id}`) }));
}
