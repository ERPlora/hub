// The six sections of VeriFactu, painted as the footer tabbar of each VeriFactu page (AppPage `tabs`): the same
// entries, order and paths as the app's menu (`navigation` in apps.py). Each tab follows its route; picking one
// replaces the address, so Back leaves VeriFactu instead of walking its tabs. Icons: registered ones only (the
// old `document-text-outline` is asked for in UI-REQUESTS.md).
import type { ShellTab } from '@erplora/ui/shell';

export const VERIFACTU_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'records', icon: 'ion:list-outline', to: '/verifactu/records' },
  { id: 'contingency', icon: 'ion:warning-outline', to: '/verifactu/contingency' },
  { id: 'events', icon: 'ion:time-outline', to: '/verifactu/events' },
  { id: 'recovery', icon: 'ion:shield-checkmark-outline', to: '/verifactu/recovery' },
  { id: 'config', icon: 'ion:key-outline', to: '/verifactu/config' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/verifactu/settings' },
]);

/** The tabs with their labels in the reader's language (`verifactuTabs($t)` in a template). */
export function verifactuTabs(t: (key: string) => string): ShellTab[] {
  return VERIFACTU_TABS.map((tab) => ({ ...tab, label: t(`verifactu.tabs.${tab.id}`) }));
}
