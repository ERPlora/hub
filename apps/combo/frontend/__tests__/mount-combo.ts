// Test helper of the combo app's pages and components: `mountInShell` with its catalogues over base's, the menus, its
// people and the hub's business.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { type BusinessMountOptions, mountInShell, overBase } from '../../../../base/frontend/__tests__/mount-in-shell';
import { business } from '../../../../base/frontend/__tests__/business';
import type { Business } from '../../../../base/frontend/operations';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** The hub's business (`base.business.get`, the platform's): one in Spain, in euros, unless a test says another
 *  (the money a menu's price and a supplement are painted and typed in is the business's). */
export { business, IN_YEN as JAPANESE, POLISH } from '../../../../base/frontend/__tests__/business';

/** A business in Hungary: the server counts the forint in two decimals, where the browser's Intl gives it none. */
export const HUNGARIAN: Partial<Business> = {
  country: 'HU',
  country_name: 'Hungary',
  currency: 'HUF',
  currency_label: 'HUF · Hungarian Forint',
  currency_decimals: 2,
};

/** Owner, admin or manager: `combo.*` (apps.py `role_permissions`); they read Inventory's products and
 *  Taxes' categories for the pickers. */
export const MANAGER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: ['combo.view', 'combo.manage', 'inventory.view_product', 'tax.view'],
  menu: [],
  apps: [],
  language: 'en',
};

/** An employee only reads the menus. */
export const EMPLOYEE: SessionMe = {
  ...MANAGER,
  user: { id: '2', label: 'Bea' },
  permissions: ['combo.view', 'inventory.view_product', 'tax.view'],
};

export type MountOptions = BusinessMountOptions;

export async function mountCombo(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/combo/menus',
    session: MANAGER,
    messages: overBase(en, es),
    business: business(),
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
