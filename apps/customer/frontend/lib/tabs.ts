// The sections of Customers as the footer tabbar of its pages (WORKBOOK «Pantallas»), with the
// paths and icons of the menu in apps.py: the product's own, all registered by the shell.
import type { ShellTab } from '@erplora/ui/shell';

export function customerTabs(t: (key: string) => string): ShellTab[] {
  return [
    { id: 'customers', label: t('customer.tabs.customers'), icon: 'ion:people-outline', to: '/customer/customers' },
    { id: 'groups', label: t('customer.tabs.groups'), icon: 'ion:people-outline', to: '/customer/groups' },
    { id: 'tags', label: t('customer.tabs.tags'), icon: 'ion:pricetags', to: '/customer/tags' },
    { id: 'fields', label: t('customer.tabs.fields'), icon: 'ion:layers-outline', to: '/customer/fields' },
  ];
}
