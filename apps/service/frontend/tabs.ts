// The sections of Services, painted as the footer tabbar of each service page (AppPage `tabs`): the
// three of the app's menu (`navigation` in apps.py), same order, icons and paths, plus «Settings», the
// tab the old shell generated from the module's settings block and showed only to whoever may save
// them. Each tab follows its route; picking one replaces the address, so Back leaves Services.
import type { ShellTab } from '@erplora/ui/shell';

export const SERVICE_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'services', icon: 'ion:pricetag-outline', to: '/service/services' },
  { id: 'categories', icon: 'ion:pricetags-outline', to: '/service/categories' },
  { id: 'packages', icon: 'ion:ticket-outline', to: '/service/packages' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/service/settings' },
]);

/** The tabs in the reader's language; «Settings» only when `settings` (may save them). */
export function serviceTabs(t: (key: string) => string, options: { settings: boolean }): ShellTab[] {
  return SERVICE_TABS.filter((tab) => tab.id !== 'settings' || options.settings).map((tab) => ({
    ...tab,
    label: t(`service.tabs.${tab.id}`),
  }));
}
