// Test helper of the online booking app's pages and components: `mountInShell` with its catalogues over Appointments'
// (whose state and clock helpers the inbox reuses), the bookings and its people.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { withMenu } from '../../../../base/frontend/__tests__/app-menu';
import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import appointmentEn from '../../../appointment/frontend/locale/en.json';
import appointmentEs from '../../../appointment/frontend/locale/es.json';
import serviceEn from '../../../service/frontend/locale/en.json';
import serviceEs from '../../../service/frontend/locale/es.json';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** The platform's business (`base.business.get`): the preview's prices are in its currency (BASE-F50). */
export { business, POLISH } from '../../../../base/frontend/__tests__/business';

const ALL = [
  'online_booking.view_booking',
  'online_booking.change_booking',
  'online_booking.confirm_booking',
  'online_booking.delete_booking',
  'online_booking.manage_settings',
  'online_booking.public',
];

// `base.view_customer_contact`: the customers' phone and email, which the four roles see (base/apps.py).
const CONTACT = 'base.view_customer_contact';

/** Owner or admin: `online_booking.*` (apps.py `role_permissions`), and the services' rights. */
export const OWNER: SessionMe = withMenu('online_booking', {
  user: { id: '1', label: 'Ana' },
  permissions: [...ALL, 'service.view_service', 'service.change_service', 'appointment.manage_settings', CONTACT],
  menu: [],
  apps: [],
  language: 'en',
});

/** A manager: the inbox, without deleting, the settings nor the preview. */
export const MANAGER: SessionMe = withMenu('online_booking', {
  ...OWNER,
  permissions: ['online_booking.view_booking', 'online_booking.change_booking', 'online_booking.confirm_booking', CONTACT],
});

/** An employee only looks. */
export const EMPLOYEE: SessionMe = withMenu('online_booking', {
  ...OWNER,
  user: { id: '2', label: 'Bea' },
  permissions: ['online_booking.view_booking', CONTACT],
});

/** An employee in a role the business made without the customers' contact details. */
export const WITHOUT_CONTACT: SessionMe = withMenu('online_booking', {
  ...EMPLOYEE,
  permissions: EMPLOYEE.permissions.filter((p) => p !== CONTACT),
});

export async function mountOnlineBooking(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/online_booking/bookings',
    session: OWNER,
    messages: { en: { ...appointmentEn, ...serviceEn, ...en }, es: { ...appointmentEs, ...serviceEs, ...es } },
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
