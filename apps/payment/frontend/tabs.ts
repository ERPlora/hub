// The sections of Payments, painted as the footer tabbar of each payment page (AppPage `tabs`): the two
// of the app's menu (`navigation` in apps.py), same order, icons and paths. Each tab follows its route;
// picking one replaces the address, so Back leaves Payments instead of walking its tabs.
import type { ShellTab } from '@erplora/ui/shell';

export const PAYMENT_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'payments', icon: 'lucide:send', to: '/payment/payments' },
  { id: 'methods', icon: 'ion:wallet-outline', to: '/payment/methods' },
]);

/** The tabs with their labels in the reader's language (`paymentTabs($t)` in a template). */
export function paymentTabs(t: (key: string) => string): ShellTab[] {
  return PAYMENT_TABS.map((tab) => ({ ...tab, label: t(`payment.tabs.${tab.id}`) }));
}
