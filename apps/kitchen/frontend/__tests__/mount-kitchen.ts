// Test helper of the kitchen app's pages and components: `mountInShell` with its catalogues, the display and its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Owner, admin or manager: `kitchen.*` (apps.py `role_permissions`), listed one by one. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: [
    'kitchen.view_ticket',
    'kitchen.add_ticket',
    'kitchen.change_ticket',
    'kitchen.complete_ticket',
    'kitchen.cancel_ticket',
    'kitchen.delete_ticket',
    'kitchen.manage_station',
    'kitchen.change_settings',
    'kitchen.view_log',
    'inventory.view_product',
  ],
  menu: [],
  apps: [],
  language: 'en',
};

/** The cook and the waiter: they move states; no cancel, no delete, no stations, no settings. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Luis' },
  permissions: [
    'kitchen.view_ticket',
    'kitchen.add_ticket',
    'kitchen.change_ticket',
    'kitchen.complete_ticket',
    'kitchen.view_log',
    'inventory.view_product',
  ],
};

/** Who may only look at the board (no change, no serve). */
export const VIEWER: SessionMe = {
  ...OWNER,
  user: { id: '3', label: 'Eva' },
  permissions: ['kitchen.view_ticket'],
};

export async function mountKitchen(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/kitchen/display', session: OWNER, messages: { en, es } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
