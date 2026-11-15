// Test helper of the tax app's pages and components: `mountInShell` with its catalogues, the tax categories and its
// people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `ionModalStub` (imported
// from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Owner, admin or manager: `tax.*` (apps.py `role_permissions`). */
export const MANAGER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['tax.view', 'tax.manage'],
  menu: [],
  apps: [],
  language: 'en',
};

/** An employee only views and calculates. */
export const EMPLOYEE: SessionMe = { ...MANAGER, permissions: ['tax.view'] };

export async function mountTax(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/tax/categories',
    session: MANAGER,
    messages: { en, es },
    inDocFrom: 'component',
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
