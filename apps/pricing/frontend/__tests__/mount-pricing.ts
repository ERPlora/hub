// Test helper of the pricing app's pages and components: `mountInShell` with its catalogues, the price lists and its
// people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Owner, admin or manager: `pricing.*` (apps.py `role_permissions`); they read Inventory, Services and
 *  Customers for the pickers. */
export const MANAGER: SessionMe = {
  user: { id: '1', label: 'Marta' },
  permissions: ['pricing.view', 'pricing.manage', 'inventory.view_product', 'service.view_service', 'customer.view'],
  menu: [],
  apps: [],
  language: 'en',
};

/** An employee only views the lists and the rules and asks for prices. */
export const EMPLOYEE: SessionMe = { ...MANAGER, user: { id: '2', label: 'Bea' }, permissions: ['pricing.view'] };

export async function mountPricing(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/pricing/lists', session: MANAGER, messages: { en, es } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
