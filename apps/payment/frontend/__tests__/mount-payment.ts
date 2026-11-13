// Test helper of the payment app's pages and components: `mountInShell` with its catalogues, the payments, its people
// and the hub's business (`base.business.get`: one in Spain unless a test says another).
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { type BusinessMountOptions, mountInShell } from '../../../../base/frontend/__tests__/mount-in-shell';
import { business as baseBusiness } from '../../../../base/frontend/__tests__/business';
import type { Business } from '../../../../base/frontend/operations';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** The hub's business (`base.business.get`, the platform's): one in Spain, in euros, unless a test says another
 *  (a new payment, the amount typed and the amount filter are in the business's currency; PAYMENT-F02). */
export function business(fields: Partial<Business> = {}): Business {
  return baseBusiness({ name: 'Taller Norte', settings_url: 'https://erplora.com/hubs/taller-norte/settings', ...fields });
}

export { IN_YEN as JAPANESE, POLISH } from '../../../../base/frontend/__tests__/business';

/** Owner, admin or manager: `payment.*` (apps.py `role_permissions`), listed one by one. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: ['payment.view_payment', 'payment.add_payment', 'payment.approve_payment'],
  menu: [],
  apps: [],
  language: 'en',
};

/** Records, sends and completes payments and manages the methods, but does not approve nor cancel. */
export const RECORDER: SessionMe = {
  ...OWNER,
  user: { id: '3', label: 'Carla' },
  permissions: ['payment.view_payment', 'payment.add_payment'],
};

/** An employee only looks. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Bea' },
  permissions: ['payment.view_payment'],
};

export type MountOptions = BusinessMountOptions;

export async function mountPayment(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/payment/payments',
    session: OWNER,
    messages: { en, es },
    business: business(),
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
