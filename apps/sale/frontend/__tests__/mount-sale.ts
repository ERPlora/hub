// Test helper of the sale app's pages and components: `mountInShell` with its catalogues over base's and Taxes' (whose
// `useTaxName` names the territory's tax on every sale screen), the till, its people and the hub's business; the shared
// assistant configured as the Hub boots it (main.ts), for the till's «Speak», which dictates to it.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `ionModalStub` (imported
// from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import { configureAssistant } from '@erplora/ui/components';
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import type { StreamCall } from '../../../../packages/ui/src/sdk/__tests__/live-harness';
import { mountInShell, overBase, settle } from '../../../../base/frontend/__tests__/mount-in-shell';
import { business, IN_YEN as JAPANESE } from '../../../../base/frontend/__tests__/business';
import { expectSaveWaitsForMoney } from '../../../../base/frontend/__tests__/save-waits-for-money';
import { HUB_ASSISTANT } from '../../../../base/frontend/lib/assistant-hub';
import type { Business } from '../../../../base/frontend/operations';
import taxEn from '../../../tax/frontend/locale/en.json';
import taxEs from '../../../tax/frontend/locale/es.json';
import type { TaxSettingsOut, TerritoryTaxKind } from '../../../tax/frontend/operations';
import { ComposableHost } from './composable-host';
import en from '../locale/en.json';
import es from '../locale/es.json';

configureAssistant(HUB_ASSISTANT);

/** The business of the hub (`base.business.get`): one in Spain, in euros, unless a test says another
 *  (flow business-currency: the till's money is the business's). */
export { business, IN_YEN as JAPANESE, POLISH } from '../../../../base/frontend/__tests__/business';

/** Every permission of the sale app (owner, admin, manager: apps.py `role_permissions`) and what the
 *  till reads from the other apps (Inventory's catalog, Customers, Staff, Taxes). */
export const SALE_PERMISSIONS = [
  'sale.view_sale',
  'sale.add_sale',
  'sale.take_payment',
  'sale.sell_open_price',
  'sale.discount_over_limit',
  'sale.void_sale',
  'sale.refund_sale',
  'sale.view_paymentmethod',
  'sale.add_paymentmethod',
  'sale.view_reports',
  'sale.manage_settings',
];
const READS = ['inventory.view_product', 'inventory.view_category', 'customer.view', 'customer.manage', 'staff.view', 'tax.view'];

export const MANAGER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: [...SALE_PERMISSIONS, ...READS],
  menu: [],
  apps: [],
  language: 'en',
};

/** The employee (the old cashier too): builds the check, charges it, reads the sales. */
export const EMPLOYEE: SessionMe = {
  ...MANAGER,
  permissions: ['sale.view_sale', 'sale.add_sale', 'sale.take_payment', 'sale.view_paymentmethod', ...READS],
};

export interface MountOptions {
  props?: Record<string, unknown>;
  /** What `base.business.get` answers when the stream opens; `null`: it never answers (the currency unknown). */
  business?: Business | null;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** How every API call is answered from the start, the ones made while mounting included. */
  answer?: { status: number; body: unknown };
}

export async function mountSale(component: Component, options: MountOptions = {}) {
  const first = options.answer;
  const api = first && (() => Response.json(first.body, { status: first.status }));
  // The till answers the business itself (`answerBusiness`), so the shell's mount is given none.
  const mounted = await mountInShell(
    component,
    { ...options, business: undefined, api },
    { path: '/sale/pos', session: MANAGER, messages: overBase({ ...taxEn, ...en }, { ...taxEs, ...es }), inDocFrom: 'component' },
  );

  /** The business answers once a piece follows it (on opening the stream, or on reopening it when a piece of the
   *  till appears later): it is the platform's, not what a test of the sale app looks at. */
  let businessAnswered = false;
  async function answerBusiness(): Promise<void> {
    const answer = options.business === undefined ? business() : options.business;
    if (businessAnswered || !answer || !mounted.client.stream.subscriptions('base.business.get').length) return;
    businessAnswered = true;
    await mounted.result('base.business.get', answer);
  }

  /** Opens the stream and answers the business, if a piece follows it; returns the call to push frames into. */
  async function live(): Promise<StreamCall> {
    const call = await mounted.live();
    await answerBusiness();
    return call;
  }

  /** The SDK reopens the stream 150 ms after the subscriptions change: results come on the new one. */
  async function reopen(): Promise<void> {
    await mounted.reopen();
    await answerBusiness();
  }

  return { ...mounted, live, reopen };
}

/** Taxes' settings of a business whose territory declares `tax_kind` (`tax.settings.get`, what every sale
 *  screen names the tax by). */
export function taxSettings(tax_kind: TerritoryTaxKind): TaxSettingsOut {
  const region_code = { vat: null, igic: 'ES-CN', ipsi: 'ES-CE' }[tax_kind];
  return { country_code: 'ES', region_code, regions: ['ES-CN', 'ES-CE', 'ES-ML'], tax_kind, updated_at: null };
}

/** Mounts `use` (a composable call) inside a component of the sale app's harness. */
export function mountComposable(use: () => void, options: Omit<MountOptions, 'props'> = {}) {
  return mountSale(ComposableHost, { ...options, props: { use } });
}

/** A piece of the till mounted with `business: null` waits for the business's money (hub#921, `expectSaveWaitsForMoney`):
 *  pressing `confirm` hands nothing up (`handed`: what it emitted or sent) and it is grey; then the business answers in
 *  yen (no decimals: «1500» read before it would go up as 150000) and `confirm` lights up. `submit`: its door past the
 *  grey button — none for the till's sheets, whose click reaches their handler grey or not. */
export function expectWaitsForTheYen(
  m: Awaited<ReturnType<typeof mountSale>>,
  confirm: string,
  handed: () => unknown[],
  submit: (() => unknown) | null = null,
): Promise<void> {
  const piece = { wrapper: m.wrapper, save: () => m.inDoc(confirm), amount: () => null, sent: handed, settle, submit };
  return expectSaveWaitsForMoney(piece, () => m.result('base.business.get', business(JAPANESE)));
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
