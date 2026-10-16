// The three sections of Taxes, painted as the footer tabbar of each tax page (AppPage `tabs`): the
// same entries, order and paths as the app's menu (`navigation` in apps.py). Each tab follows its
// route; picking one replaces the address, so Back leaves Taxes instead of walking its tabs.
// Icons: the old menu's (`pricetags`, `receipt`, `swap-horizontal`), all registered in the shell.
import type { ShellTab } from '@erplora/ui/shell';

export const TAX_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'categories', icon: 'ion:pricetags-outline', to: '/tax/categories' },
  { id: 'rules', icon: 'ion:receipt-outline', to: '/tax/rules' },
  { id: 'aliases', icon: 'ion:swap-horizontal-outline', to: '/tax/aliases' },
]);

/** The tabs with their labels in the reader's language (`taxTabs($t)` in a template). */
export function taxTabs(t: (key: string) => string): ShellTab[] {
  return TAX_TABS.map((tab) => ({ ...tab, label: t(`tax.tabs.${tab.id}`) }));
}
