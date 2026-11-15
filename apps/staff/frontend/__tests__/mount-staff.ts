// Test helper of the staff app's pages and components: `mountInShell` with its catalogues, the team and its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** The hub's business (`base.business.get`, the platform's): one in Spain, in euros, unless a test says another
 *  (the money the staff screens paint and read is the business's). */
export { business, IN_YEN as JAPANESE, POLISH } from '../../../../base/frontend/__tests__/business';

/** The platform's query of the business (its currency). */
export const BUSINESS = 'base.business.get';

/** Owner or admin: `staff.*` (apps.py `role_permissions`), listed one by one. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: [
    'staff.view',
    'staff.view_compensation',
    'staff.add_member',
    'staff.change_member',
    'staff.delete_member',
    'staff.view_time_off',
    'staff.view_time_off_detail',
    'staff.manage_time_off',
    'staff.manage_settings',
    'staff.request_time_off',
  ],
  menu: [],
  apps: [],
  language: 'en',
};

/** A manager: everything but deactivating and terminating. */
export const MANAGER: SessionMe = {
  ...OWNER,
  permissions: OWNER.permissions.filter((p) => p !== 'staff.delete_member'),
};

/** An employee views the directory, the schedules and who is away, and asks for their own time off. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Bea' },
  permissions: ['staff.view', 'staff.view_time_off', 'staff.request_time_off'],
};

export async function mountStaff(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/staff/members', session: OWNER, messages: { en, es } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
