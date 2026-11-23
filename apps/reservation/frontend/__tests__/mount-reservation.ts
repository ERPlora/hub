// Test helper of the reservation app's pages and components: `mountInShell` with its catalogues over Customers' (whose
// search the booking form mounts), the reservations and its people.
import type { SessionMe } from '@erplora/ui/shell';
import type { VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';

import { withMenu } from '../../../../base/frontend/__tests__/app-menu';
import { mountInShell, type MountOptions, settle } from '../../../../base/frontend/__tests__/mount-in-shell';
import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import customerEn from '../../../customer/frontend/locale/en.json';
import customerEs from '../../../customer/frontend/locale/es.json';
import en from '../locale/en.json';
import es from '../locale/es.json';

// `base.view_customer_contact`: the guests' phone and email, which the four roles see (base/apps.py).
const OTHERS = ['table.view_table', 'table.add_session', 'table.change_session', 'sale.add_sale', 'customer.view', 'customer.manage', 'base.view_customer_contact'];

/** Owner or admin: `reservation.*` (apps.py `role_permissions`), listed one by one. */
export const OWNER: SessionMe = withMenu('reservation', {
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
});

/** A manager runs the book and its rules; deleting a reservation is the owner's and the admin's. */
export const MANAGER: SessionMe = withMenu('reservation', {
  ...OWNER,
  permissions: OWNER.permissions.filter((p) => p !== 'reservation.delete_reservation'),
});

/** The host at the door: takes, confirms, seats, edits and cancels, keeps the waitlist; no rules. */
export const EMPLOYEE: SessionMe = withMenu('reservation', {
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
});

/** The host at the door in a role the business made without the customers' contact details. */
export const WITHOUT_CONTACT: SessionMe = withMenu('reservation', {
  ...EMPLOYEE,
  permissions: EMPLOYEE.permissions.filter((p) => p !== 'base.view_customer_contact'),
});

export async function mountReservation(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/reservation/reservations',
    session: OWNER,
    messages: { en: { ...customerEn, ...en }, es: { ...customerEs, ...es } },
  });
}

/** A form of the app mounted closed and then opened, as its page opens it; it closes itself through `update:open`. */
export async function mountOpenForm(component: Component, options: MountOptions = {}) {
  const form = await mountReservation(component, { ...options, props: { ...options.props, open: false } });
  await form.wrapper.setProps({ 'onUpdate:open': (open: boolean) => form.wrapper.setProps({ open }) });
  await form.wrapper.setProps({ open: true });
  await settle();
  return form;
}

/** A control of a form, as a test reads it. */
export type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; readonly?: boolean; required?: boolean };

/** What Customers' search hands over when Lucía Pérez's card is picked. */
export const LUCIA = { customer_id: 'c1', customer_name: 'Lucía Pérez', customer_tax_id: '', customer_address: '', customer_country: '' };

/** Picks `card` in the Customers' search of the form (`null` leaves the card). */
export async function pickCard(wrapper: VueWrapper, card: typeof LUCIA | null): Promise<void> {
  wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', card);
  await settle();
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
