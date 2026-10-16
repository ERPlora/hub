// The sections of Reservations, painted as the footer tabbar of each reservation page (AppPage `tabs`): the
// three of the app's menu (`navigation` in apps.py), same order, icons and paths, plus «Settings», shown
// only to whoever may save them. Each tab follows its route; picking one replaces the address, so Back
// leaves Reservations.
import type { ShellTab } from '@erplora/ui/shell';

export const RESERVATION_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'reservations', icon: 'ion:calendar-outline', to: '/reservation/reservations' },
  { id: 'waitlist', icon: 'ion:people-outline', to: '/reservation/waitlist' },
  { id: 'availability', icon: 'ion:time-outline', to: '/reservation/availability' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/reservation/settings' },
]);

/** The tabs in the reader's language; «Settings» only when `settings` (may save them). */
export function reservationTabs(t: (key: string) => string, options: { settings: boolean }): ShellTab[] {
  return RESERVATION_TABS.filter((tab) => tab.id !== 'settings' || options.settings).map((tab) => ({
    ...tab,
    label: t(`reservation.tabs.${tab.id}`),
  }));
}
