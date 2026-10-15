// The sections of the Time clock, painted as the footer tabbar of each attendance page (AppPage `tabs`):
// the two of the app's menu (`navigation` in apps.py), same order, icons and paths, plus «Settings», the
// tab the old shell generated from the module's settings block. Everyone sees it: whoever may not save
// reads it (WORKBOOK «Ajustes»). Each tab follows its route; picking one replaces the address, so Back
// leaves the Time clock instead of walking its tabs.
import type { ShellTab } from '@erplora/ui/shell';

export const ATTENDANCE_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'clock', icon: 'ion:time-outline', to: '/attendance/clock' },
  { id: 'records', icon: 'ion:list-outline', to: '/attendance/records' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/attendance/settings' },
]);

/** The tabs with their labels in the reader's language (`attendanceTabs($t)` in a template). */
export function attendanceTabs(t: (key: string) => string): ShellTab[] {
  return ATTENDANCE_TABS.map((tab) => ({ ...tab, label: t(`attendance.tabs.${tab.id}`) }));
}
