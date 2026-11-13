// Test helper of the schedule app's pages and components: `mountInShell` with its catalogues, the opening hours and
// its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `ionModalStub` (imported
// from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Owner, admin or manager: `schedule.*` (apps.py `role_permissions`). */
export const MANAGER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['schedule.view', 'schedule.add', 'schedule.change', 'schedule.delete', 'schedule.manage_settings'],
  menu: [],
  apps: [],
  language: 'en',
};

/** An employee only looks. */
export const EMPLOYEE: SessionMe = { ...MANAGER, permissions: ['schedule.view'] };

export async function mountSchedule(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/schedule/hours',
    session: MANAGER,
    messages: { en, es },
    inDocFrom: 'component',
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
