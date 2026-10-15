// The three sections of Schedules, painted as the footer tabbar of each schedule page (AppPage `tabs`):
// the same entries, order and paths as the app's menu (`navigation` in apps.py). The old
// `star-outline` of «Special days» is not registered in the shell: `calendar-outline` stands in
// (apps/schedule/UI-REQUESTS.md).
import type { ShellTab } from '@erplora/ui/shell';

export const SCHEDULE_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'hours', icon: 'ion:time-outline', to: '/schedule/hours' },
  { id: 'special_days', icon: 'ion:calendar-outline', to: '/schedule/special-days' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/schedule/settings' },
]);

/** The tabs with their labels in the reader's language (`scheduleTabs($t)` in a template). */
export function scheduleTabs(t: (key: string) => string): ShellTab[] {
  return SCHEDULE_TABS.map((tab) => ({ ...tab, label: t(`schedule.tabs.${tab.id}`) }));
}
