// Test helper of the service app's pages and components: `mountInShell` with its catalogues over base's, the services,
// its people and the hub's business.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { type BusinessMountOptions, mountInShell, overBase } from '../../../../base/frontend/__tests__/mount-in-shell';
import { business as baseBusiness } from '../../../../base/frontend/__tests__/business';
import type { Business } from '../../../../base/frontend/operations';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** The hub's business (`base.business.get`, the platform's): one in Spain, in euros, unless a test says another
 *  (the money a price, a voucher and a sale are painted and typed in is the business's; service-business-currency). */
export function business(fields: Partial<Business> = {}): Business {
  return baseBusiness({ name: 'Salón Ana', settings_url: 'https://erplora.com/hubs/salon-ana/settings', ...fields });
}

export { IN_YEN as JAPANESE, POLISH } from '../../../../base/frontend/__tests__/business';

/** Owner or admin: `service.*` (apps.py `role_permissions`), listed one by one; they read customers and staff. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: [
    'service.view_service',
    'service.add_service',
    'service.change_service',
    'service.delete_service',
    'service.view_category',
    'service.add_category',
    'service.change_category',
    'service.delete_category',
    'service.view_package',
    'service.add_package',
    'service.change_package',
    'service.delete_package',
    'service.grant_package',
    'service.redeem_package',
    'service.view_package_balance',
    'service.view_orphan_grant',
    'service.void_grant',
    'service.adjust_grant',
    'service.manage_settings',
    'customer.view',
    'staff.view',
  ],
  menu: [],
  apps: [],
  language: 'en',
};

const ADMIN_ONLY = ['service.delete_service', 'service.delete_category', 'service.delete_package', 'service.manage_settings'];

/** A manager: everything but archiving, deleting and the settings. */
export const MANAGER: SessionMe = {
  ...OWNER,
  permissions: OWNER.permissions.filter((p) => !ADMIN_ONLY.includes(p)),
};

/** An employee views, creates services, grants vouchers and spends sessions. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Bea' },
  permissions: [
    'service.view_service',
    'service.add_service',
    'service.view_category',
    'service.view_package',
    'service.view_package_balance',
    'service.redeem_package',
    'service.grant_package',
    'customer.view',
    'staff.view',
  ],
};

export type MountOptions = BusinessMountOptions;

export async function mountService(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/service/services',
    session: OWNER,
    messages: overBase(en, es),
    business: business(),
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
