// The sections of Cart & Checkout, painted as the footer tabbar of each of its pages (AppPage `tabs`): the
// two of the app's menu (`navigation` in apps.py), same order, icons and paths. Each tab follows its
// route; picking one replaces the address, so Back leaves the app instead of walking its tabs.
import type { ShellTab } from '@erplora/ui/shell';

export const CART_CHECKOUT_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'carts', icon: 'lucide:shopping-bag', to: '/cart_checkout/carts' },
  { id: 'orders', icon: 'ion:receipt-outline', to: '/cart_checkout/orders' },
]);

/** The tabs with their labels in the reader's language (`cartCheckoutTabs($t)` in a template). */
export function cartCheckoutTabs(t: (key: string) => string): ShellTab[] {
  return CART_CHECKOUT_TABS.map((tab) => ({ ...tab, label: t(`cart_checkout.tabs.${tab.id}`) }));
}
