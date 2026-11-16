// Test helper of the reservation app's pages and components: `mountInShell` with its catalogues over Customers' (whose
// search the booking form mounts), the reservations and its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import customerEn from '../../../customer/frontend/locale/en.json';
import customerEs from '../../../customer/frontend/locale/es.json';
import en from '../locale/en.json';
import es from '../locale/es.json';

const OTHERS = ['table.view_table', 'table.add_session', 'table.change_session', 'sale.add_sale', 'customer.view', 'customer.manage'];

/** Owner or admin: `reservation.*` (apps.py `role_permissions`), listed one by one. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: [
    'reservation.view_reservation',
    'reservation.add_reservation',
    'reservation.change_reservation',
    'reservation.delete_reservation',
    'reservation.view_timeslot',
    'reservation.change_timeslot',
    'reservation.view_blockeddate',
    'reservation.change_blockeddate',
    'reservation.view_waitlistentry',
    'reservation.change_waitlistentry',
    'reservation.view_settings',
    'reservation.manage_settings',
    ...OTHERS,
  ],
  menu: [],
  apps: [],
  language: 'en',
};

/** A manager runs the book and its rules; deleting a reservation is the owner's and the admin's. */
export const MANAGER: SessionMe = {
  ...OWNER,
  permissions: OWNER.permissions.filter((p) => p !== 'reservation.delete_reservation'),
};

/** The host at the door: takes, confirms, seats, edits and cancels, keeps the waitlist; no rules. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Luis' },
  permissions: [
    'reservation.view_reservation',
    'reservation.add_reservation',
    'reservation.change_reservation',
    'reservation.view_timeslot',
    'reservation.view_blockeddate',
    'reservation.view_waitlistentry',
    'reservation.change_waitlistentry',
    'reservation.view_settings',
    ...OTHERS,
  ],
};

export async function mountReservation(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/reservation/reservations',
    session: OWNER,
    messages: { en: { ...customerEn, ...en }, es: { ...customerEs, ...es } },
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
