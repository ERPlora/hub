// The three sections of Invoicing, painted as the footer tabbar of each invoice page (AppPage `tabs`): the
// same entries, order and paths as the app's menu (`navigation` in apps.py). Each tab follows its route;
// picking one replaces the address, so Back leaves Invoicing instead of walking its tabs. Icons: registered
// ones only (the old `document-text-outline` and `bookmark-outline` are asked for in UI-REQUESTS.md).
import type { ShellTab } from '@erplora/ui/shell';

export const INVOICE_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'invoices', icon: 'ion:receipt-outline', to: '/invoice/invoices' },
  { id: 'series', icon: 'ion:layers-outline', to: '/invoice/series' },
  { id: 'issuer', icon: 'ion:storefront-outline', to: '/invoice/issuer' },
]);

/** The tabs with their labels in the reader's language (`invoiceTabs($t)` in a template). */
export function invoiceTabs(t: (key: string) => string): ShellTab[] {
  return INVOICE_TABS.map((tab) => ({ ...tab, label: t(`invoice.tabs.${tab.id}`) }));
}
