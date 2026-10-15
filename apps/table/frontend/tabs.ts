// The sections of Tables, painted as the footer tabbar of each table page (AppPage `tabs`): the four of
// the app's menu (`navigation` in apps.py), same order, icons and paths, plus «Settings», the tab the old
// shell generated from the module's settings block and showed only to whoever may save them. Each tab
// follows its route; picking one replaces the address, so Back leaves Tables.
import type { ShellTab } from '@erplora/ui/shell';

export const TABLE_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'floor_plan', icon: 'ion:apps-outline', to: '/table/floor-plan' },
  { id: 'zones', icon: 'ion:layers-outline', to: '/table/zones' },
  { id: 'tables', icon: 'ion:grid-outline', to: '/table/tables' },
  { id: 'sessions', icon: 'ion:time-outline', to: '/table/sessions' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/table/settings' },
]);

/** The tabs in the reader's language; «Settings» only when `settings` (may save them). */
export function tableTabs(t: (key: string) => string, options: { settings: boolean }): ShellTab[] {
  return TABLE_TABS.filter((tab) => tab.id !== 'settings' || options.settings).map((tab) => ({
    ...tab,
    label: t(`table.tabs.${tab.id}`),
  }));
}
