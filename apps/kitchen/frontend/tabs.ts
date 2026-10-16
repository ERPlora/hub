// The sections of Kitchen, painted as the footer tabbar of each kitchen page (AppPage `tabs`): the four of
// the app's menu (`navigation` in apps.py), same order, icons and paths, plus «Settings», the tab the old
// shell generated from the module's settings block and showed only to whoever may save them. Each tab
// follows its route; picking one replaces the address, so Back leaves Kitchen.
import type { ShellTab } from '@erplora/ui/shell';

export const KITCHEN_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'display', icon: 'ion:desktop-outline', to: '/kitchen/display' },
  { id: 'tickets', icon: 'ion:list-outline', to: '/kitchen/tickets' },
  { id: 'stations', icon: 'ion:layers-outline', to: '/kitchen/stations' },
  { id: 'history', icon: 'ion:time-outline', to: '/kitchen/history' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/kitchen/settings' },
]);

/** The tabs in the reader's language; «Settings» only when `settings` (may save them). */
export function kitchenTabs(t: (key: string) => string, options: { settings: boolean }): ShellTab[] {
  return KITCHEN_TABS.filter((tab) => tab.id !== 'settings' || options.settings).map((tab) => ({
    ...tab,
    label: t(`kitchen.tabs.${tab.id}`),
  }));
}
