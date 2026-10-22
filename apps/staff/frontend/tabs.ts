// The sections of Staff, painted as the footer tabbar of each staff page (AppPage `tabs`): the four of
// the app's menu (`navigation` in apps.py), same order, icons and paths, plus «Commissions» (STAFF-F21),
// only for whoever sees the pay, and «Settings», the tab the old shell generated from the module's
// settings block and showed only to whoever may save them. Both depend on a permission, which a menu
// entry of apps.py cannot say. Each tab follows its route; picking one replaces the address, so Back
// leaves Staff instead of walking its tabs.
import type { ShellTab } from '@erplora/ui/shell';

export const STAFF_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'staff', icon: 'ion:people-outline', to: '/staff/members' },
  { id: 'roles', icon: 'ion:shield-outline', to: '/staff/roles' },
  { id: 'time_off', icon: 'ion:calendar-outline', to: '/staff/time-off' },
  { id: 'schedules', icon: 'ion:time-outline', to: '/staff/schedules' },
  { id: 'commissions', icon: 'ion:wallet-outline', to: '/staff/commissions' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/staff/settings' },
]);

/** The tabs in the reader's language; «Commissions» only when `commissions` (sees the pay), «Settings»
 *  only when `settings` (may save them). */
export function staffTabs(t: (key: string) => string, options: { settings: boolean; commissions: boolean }): ShellTab[] {
  const allowed: Record<string, boolean> = { settings: options.settings, commissions: options.commissions };
  return STAFF_TABS.filter((tab) => allowed[tab.id] ?? true).map((tab) => ({
    ...tab,
    label: t(`staff.tabs.${tab.id}`),
  }));
}
