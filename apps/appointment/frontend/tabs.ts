// The sections of Appointments, painted as the footer tabbar of each appointment page (AppPage `tabs`):
// the Agenda (the menu's entry of apps.py, same icon and path) and «Settings», the tab the old shell
// generated from the module's settings block and showed only to whoever may save them. Each tab follows
// its route; picking one replaces the address, so Back leaves Appointments.
import type { ShellTab } from '@erplora/ui/shell';

export const APPOINTMENT_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'agenda', icon: 'ion:calendar-outline', to: '/appointment/agenda' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/appointment/settings' },
]);

/** The tabs in the reader's language; «Settings» only when `settings` (may save them). */
export function appointmentTabs(t: (key: string) => string, options: { settings: boolean }): ShellTab[] {
  return APPOINTMENT_TABS.filter((tab) => tab.id !== 'settings' || options.settings).map((tab) => ({
    ...tab,
    label: t(`appointment.tabs.${tab.id}`),
  }));
}
