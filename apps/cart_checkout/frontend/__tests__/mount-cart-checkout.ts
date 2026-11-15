// Test helper of the cart_checkout app's pages and components: `mountInShell` with its catalogues over base's, the carts
// and its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { OpName } from '@erplora/ui/sdk';
import type { Component } from 'vue';

import { flush, mountInShell, type MountOptions, overBase } from '../../../../base/frontend/__tests__/mount-in-shell';
import type { AmountFilterList } from '../../../../base/frontend/__tests__/amount-filter';
import { business } from '../../../../base/frontend/__tests__/business';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Owner, admin or manager: `cart_checkout.*` (apps.py `role_permissions`), listed one by one. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: ['cart_checkout.view_cart', 'cart_checkout.manage_cart', 'cart_checkout.checkout'],
  menu: [],
  apps: [],
  language: 'en',
};

/** Manages carts but does not take orders through checkout (no role has it: a custom grant). */
export const CART_KEEPER: SessionMe = {
  ...OWNER,
  user: { id: '3', label: 'Carla' },
  permissions: ['cart_checkout.view_cart', 'cart_checkout.manage_cart'],
};

/** An employee only looks. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Bea' },
  permissions: ['cart_checkout.view_cart'],
};

export async function mountCartCheckout(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/cart_checkout/carts', session: OWNER, messages: overBase(en, es) });
}

/** The hub's business (`base.business.get`, the platform's): one in Spain, in euros, unless a test says another
 *  (the Total filter is typed in the business's currency; flow cart-checkout-business-currency). */
export { business, IN_YEN as JAPANESE, POLISH } from '../../../../base/frontend/__tests__/business';

/** What a list page's test setup gives: the business's answer, its first page, its table and the list's query. */
export interface TotalFilterPage {
  result: (op: OpName, data: unknown) => Promise<void>;
  show: (data: unknown) => Promise<void>;
  table: () => { vm: { $emit: (event: string, ...args: unknown[]) => void } };
  prop: <T = unknown>(name: string) => T;
  list: () => unknown[];
}

/** The «Total» filter of Carts or Orders as the Hub's table of amount filter texts drives it (hub#1196,
 *  `itReadsAmountFiltersAsTheHub`): the page that `setup` mounts, in the business's money, with `rows` on its first
 *  page; the funnel applies the ends as typed. */
export function totalFilter(setup: () => Promise<TotalFilterPage>, rows: unknown): AmountFilterList {
  return {
    ends: ['total_amount_from', 'total_amount_to'],
    params: ['total_amount_min', 'total_amount_max'],
    async open(money) {
      const s = await setup();
      await s.result('base.business.get', business({ currency: money.currency, currency_decimals: money.decimals }));
      await s.show(rows);
      const filter = async (values: Record<string, string>) => {
        s.table().vm.$emit('filtersChange', values);
        await flush();
      };
      return { filter, query: () => s.list().at(-1) as Record<string, unknown>, says: () => s.prop<Record<string, string>>('filterErrors') };
    },
  };
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
