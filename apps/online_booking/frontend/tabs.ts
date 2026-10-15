// The sections of Online booking, painted as the footer tabbar of each of its pages (AppPage `tabs`): the
// old module's two menu entries (apps.py `navigation`: same icons and paths), «Settings» only for whoever
// may save them. Each tab follows its route; picking one replaces the address, so Back leaves the app.
import type { ShellTab } from '@erplora/ui/shell';

export const ONLINE_BOOKING_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'bookings', icon: 'ion:calendar-outline', to: '/online_booking/bookings' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/online_booking/settings' },
]);

/** The tabs in the reader's language; «Settings» only when `settings` (may save them). */
export function onlineBookingTabs(t: (key: string) => string, options: { settings: boolean }): ShellTab[] {
  return ONLINE_BOOKING_TABS.filter((tab) => tab.id !== 'settings' || options.settings).map((tab) => ({
    ...tab,
    label: t(`online_booking.tabs.${tab.id}`),
  }));
}
