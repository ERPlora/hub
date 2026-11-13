// Test helper of the modifier app's pages and components: `mountInShell` with its catalogues, the modifier groups and
// its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import type { Business } from '../../../../base/frontend/operations';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** The hub's business (`base.business.get`, the platform's): one in Spain, in euros, unless a test says another
 *  (the money a supplement is painted and typed in is the business's). */
export { business, IN_YEN as JAPANESE, POLISH } from '../../../../base/frontend/__tests__/business';

/** A business in Kuwait: the dinar has three decimals. */
export const KUWAITI: Partial<Business> = {
  country: 'KW',
  country_name: 'Kuwait',
  currency: 'KWD',
  currency_label: 'KWD · Kuwaiti Dinar',
  currency_decimals: 3,
};

/** Owner, admin or manager: `modifier.*` (apps.py `role_permissions`); they read Inventory and Taxes too. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: ['modifier.view', 'modifier.manage', 'inventory.view_product', 'inventory.view_category', 'tax.view'],
  menu: [],
  apps: [],
  language: 'en',
};

/** An employee (the cashier) reads the groups; never edits the catalog. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Bea' },
  permissions: ['modifier.view', 'inventory.view_product', 'inventory.view_category', 'tax.view'],
};

export async function mountModifier(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/modifier/groups', session: OWNER, messages: { en, es } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
