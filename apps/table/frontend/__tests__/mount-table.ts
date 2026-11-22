// Test helper of the table app's pages and components: `mountInShell` with its catalogues over Customers' (whose search
// the table window mounts), the floor plan and its people.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { withMenu } from '../../../../base/frontend/__tests__/app-menu';
import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import customerEn from '../../../customer/frontend/locale/en.json';
import customerEs from '../../../customer/frontend/locale/es.json';
import en from '../locale/en.json';
import es from '../locale/es.json';

const SALE = ['sale.view_sale', 'sale.add_sale', 'sale.take_payment', 'customer.view', 'customer.manage'];

/** Owner or admin: `table.*` (apps.py `role_permissions`), listed one by one; they sell and see customers. */
export const OWNER: SessionMe = withMenu('table', {
  user: { id: '1', label: 'Ana' },
  permissions: [
    'table.view_zone',
    'table.add_zone',
    'table.change_zone',
    'table.delete_zone',
    'table.view_table',
    'table.add_table',
    'table.change_table',
    'table.delete_table',
    'table.view_session',
    'table.add_session',
    'table.change_session',
    'table.transfer_session',
    'table.delete_session',
    'table.view_settings',
    'table.manage_settings',
    ...SALE,
  ],
  menu: [],
  apps: [],
  language: 'en',
});

const ADMIN_ONLY = ['table.delete_zone', 'table.delete_table', 'table.delete_session', 'table.manage_settings'];

/** A manager draws the room and serves it; deleting and the settings are the owner's and the admin's. */
export const MANAGER: SessionMe = withMenu('table', {
  ...OWNER,
  permissions: OWNER.permissions.filter((p) => !ADMIN_ONLY.includes(p)),
});

/** A waiter (the old employee and cashier) serves the room, never draws it. */
export const EMPLOYEE: SessionMe = withMenu('table', {
  ...OWNER,
  user: { id: '2', label: 'Luis' },
  permissions: [
    'table.view_zone',
    'table.view_table',
    'table.view_session',
    'table.add_session',
    'table.change_session',
    'table.transfer_session',
    'table.view_settings',
    ...SALE,
  ],
});

export async function mountTable(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/table/floor-plan',
    session: OWNER,
    messages: { en: { ...customerEn, ...en }, es: { ...customerEs, ...es } },
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
