// Test helper of the appointment app's pages and components: `mountInShell` with its catalogues over Customers' (whose
// `CustomerSearch` the forms mount), the agenda and its people.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { withMenu } from '../../../../base/frontend/__tests__/app-menu';
import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import customerEn from '../../../customer/frontend/locale/en.json';
import customerEs from '../../../customer/frontend/locale/es.json';
import { ComposableHost } from './composable-host';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** The platform's business (`base.business.get`): the diary's money is its currency (BASE-F50). */
export { business, POLISH } from '../../../../base/frontend/__tests__/business';

const ALL = [
  'appointment.view_appointment',
  'appointment.view_own_appointment',
  'appointment.add_appointment',
  'appointment.add_own_appointment',
  'appointment.change_appointment',
  'appointment.change_own_appointment',
  'appointment.delete_appointment',
  'appointment.view_schedule',
  'appointment.manage_schedule',
  'appointment.manage_settings',
];
// `base.view_customer_contact`: the customers' email and phone, which the four roles see (base/apps.py).
const READ_OTHERS = ['customer.view', 'customer.manage', 'base.view_customer_contact', 'service.view_service', 'staff.view', 'schedule.view'];

/** Owner or admin: `appointment.*` (apps.py `role_permissions`), listed one by one. */
export const OWNER: SessionMe = withMenu('appointment', {
  user: { id: '1', label: 'Ana' },
  permissions: [...ALL, ...READ_OTHERS, 'sale.add_sale'],
  menu: [],
  apps: [],
  language: 'en',
});

/** A manager: everything but deleting and the settings. */
export const MANAGER: SessionMe = withMenu('appointment', {
  ...OWNER,
  permissions: OWNER.permissions.filter((p) => p !== 'appointment.delete_appointment' && p !== 'appointment.manage_settings'),
});

/** An employee sees and manages their own agenda. */
export const EMPLOYEE: SessionMe = withMenu('appointment', {
  ...OWNER,
  user: { id: '2', label: 'Bea' },
  permissions: [
    'appointment.view_own_appointment',
    'appointment.add_own_appointment',
    'appointment.change_own_appointment',
    'appointment.view_schedule',
    'customer.view',
    'base.view_customer_contact',
    'service.view_service',
    'staff.view',
    'schedule.view',
    'sale.add_sale',
  ],
});

export async function mountAppointment(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/appointment/agenda',
    session: OWNER,
    messages: { en: { ...customerEn, ...en }, es: { ...customerEs, ...es } },
  });
}

/** Mounts a composable alone (``use`` runs in a host's setup) in the app's harness. */
export function mountComposable(use: () => void, options: Omit<MountOptions, 'props'> = {}) {
  return mountAppointment(ComposableHost, { ...options, props: { use } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
