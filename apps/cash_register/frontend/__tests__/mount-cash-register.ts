// Test helper of the cash register app's pages and components: `mountInShell` with its catalogues over base's, the
// sessions, its people and the hub's business.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `ionModalStub` (imported
// from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { type BusinessMountOptions, mountInShell, overBase, settle } from '../../../../base/frontend/__tests__/mount-in-shell';
import { business, IN_YEN as JAPANESE } from '../../../../base/frontend/__tests__/business';
import { expectSaveWaitsForMoney } from '../../../../base/frontend/__tests__/save-waits-for-money';
import { ComposableHost } from './composable-host';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Every permission of the cash register app (owner and admin) and the sale read of the shift review. */
export const CASH_PERMISSIONS = [
  'cash_register.view_session',
  'cash_register.add_session',
  'cash_register.close_session',
  'cash_register.view_movement',
  'cash_register.add_movement',
  'cash_register.view_count',
  'cash_register.add_count',
  'cash_register.view_expected_totals',
  'cash_register.manage_settings',
];

export const ADMIN: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: [...CASH_PERMISSIONS, 'sale.view_sale'],
  menu: [],
  apps: [],
  language: 'en',
};

/** The employee (the old cashier too): opens, records, counts and closes; no settings, no blind expected. */
export const EMPLOYEE: SessionMe = {
  ...ADMIN,
  permissions: [
    'cash_register.view_session',
    'cash_register.add_session',
    'cash_register.close_session',
    'cash_register.view_movement',
    'cash_register.add_movement',
    'cash_register.view_count',
    'cash_register.add_count',
    'sale.view_sale',
  ],
};

/** The business of the hub (`base.business.get`): one in Spain, in euros, unless a test says another
 *  (flow business-currency: the money of every screen is the business's). */
export { business, IN_YEN as JAPANESE, POLISH } from '../../../../base/frontend/__tests__/business';

export type MountOptions = BusinessMountOptions;

export async function mountCash(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/cash_register/sessions',
    session: ADMIN,
    messages: overBase(en, es),
    business: business(),
    inDocFrom: 'component',
  });
}

/** Mounts `use` (a composable call) inside a component of the app's harness. */
export function mountComposable(use: () => void, options: Omit<MountOptions, 'props'> = {}) {
  return mountCash(ComposableHost, { ...options, props: { use } });
}

/** A window of the drawer mounted with `business: null` waits for the business's money (hub#921,
 *  `expectSaveWaitsForMoney`): pressing `save` sends nothing, it is grey and the `amount` field says nothing; then the
 *  business answers in yen (no decimals: «1500» read before it would be sent as 150000) and `save` lights up. */
export function expectWaitsForTheYen(m: Awaited<ReturnType<typeof mountCash>>, save: string, amount: string): Promise<void> {
  const window = { wrapper: m.wrapper, save: () => m.inDoc(save), amount: () => m.inDoc(amount), sent: m.sent, settle };
  return expectSaveWaitsForMoney(window, () => m.result('base.business.get', business(JAPANESE)));
}

/** Flips an `ion-toggle` as Ionic does (`ionChange` with `{ checked }`). */
export { ionChecked as ionToggle } from '../../../../base/frontend/__tests__/mount-in-shell';

export * from '../../../../base/frontend/__tests__/mount-in-shell';
