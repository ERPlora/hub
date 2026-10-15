// The sections of Cash register, painted as the footer tabbar of each of its pages (AppPage `tabs`): the
// same entries, order and paths as the app's menu (`navigation` in apps.py). Each tab follows its route;
// the detail of a session keeps «Cash register» lit (its path starts with the tab's).
import type { ShellTab } from '@erplora/ui/shell';

export const CASH_REGISTER_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'sessions', icon: 'ion:cash-outline', to: '/cash_register/sessions' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/cash_register/settings' },
]);

/** The tabs with their labels in the reader's language (`cashRegisterTabs($t)` in a template). */
export function cashRegisterTabs(t: (key: string) => string): ShellTab[] {
  return CASH_REGISTER_TABS.map((tab) => ({ ...tab, label: t(`cash_register.tabs.${tab.id}`) }));
}
