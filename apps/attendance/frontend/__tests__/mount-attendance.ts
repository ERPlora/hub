// Test helper of the attendance app's pages and components: `mountInShell` with its catalogues, the clock and its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Owner, admin or manager: `attendance.*` (apps.py `role_permissions`), listed one by one. */
export const MANAGER: SessionMe = {
  user: { id: '1', label: 'Marta' },
  permissions: [
    'attendance.clock',
    'attendance.view_all',
    'attendance.correct',
    'attendance.clock_others',
    'attendance.manage_settings',
  ],
  menu: [],
  apps: [],
  language: 'en',
};

/** An employee clocks, sees their own days and history, and reads the settings. */
export const EMPLOYEE: SessionMe = {
  ...MANAGER,
  user: { id: '2', label: 'Ana' },
  permissions: ['attendance.clock'],
};

export async function mountAttendance(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/attendance/clock', session: MANAGER, messages: { en, es } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
