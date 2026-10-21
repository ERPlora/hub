// Test helper of the sale app's pages and components, as `mount-tax.ts` is the tax app's: the SDK's live
// harness (fake clock, fake network serving the stream and the API) on the hub's generated op → route
// map, the shell's i18n with the sale catalogues merged in (and Taxes', whose `useTaxName` names the
// territory's tax on every sale screen), a session and a memory router.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `ionModalStub` (imported
// from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import { createShellI18n, provideSession, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY, type LiveClient, type OpName } from '@erplora/ui/sdk';
import { fillHappyDomGaps } from '@erplora/ui/testing';
import { mount } from '@vue/test-utils';
import { type Component, createApp, ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import {
  createTestClient,
  flush,
  resultFrame,
  type StreamCall,
} from '../../../../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from '../../../../frontend/generated/operation-routes';
import taxEn from '../../../tax/frontend/locale/en.json';
import taxEs from '../../../tax/frontend/locale/es.json';
import type { TaxSettingsOut, TerritoryTaxKind } from '../../../tax/frontend/operations';
import { ComposableHost } from './composable-host';
import en from '../locale/en.json';
import es from '../locale/es.json';

// happy-dom made to behave as a browser where Ionic's runtime reaches it (the hub has no setup file).
fillHappyDomGaps();

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../../packages/ui/src/sdk/__tests__/live-harness';

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
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** How every API call is answered from the start, the ones made while mounting included. */
  answer?: { status: number; body: unknown };
}

type Params = Record<string, unknown>;

/** One API call the page made: method, path, query and JSON body. */
export interface SentCall {
  method: string;
  path: string;
  query: Params;
  body: unknown;
}

export async function mountSale(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  const first = options.answer;
  if (first) harness.net.onApi(() => Response.json(first.body, { status: first.status }));
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/sale/pos');
  await router.isReady();
  // The session is provided app-wide, as createShell does.
  const app = createApp({});
  provideSession(ref(options.session ?? MANAGER), ref('live'), { app });
  const wrapper = mount(component, {
    props: options.props,
    global: {
      plugins: [
        router,
        createShellI18n({ locale: options.locale ?? 'en', messages: { en: { ...taxEn, ...en }, es: { ...taxEs, ...es } } }),
      ],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: harness.client },
      stubs: options.stubs,
    },
  });

  /** Opens the stream; returns the call to push frames into. */
  const live = (): Promise<StreamCall> => harness.goLive();

  /** The params of every live subscription to `op`. */
  const params = (op: OpName): Params[] => harness.client.stream.subscriptions(op).map((s) => s.params as Params);

  /** The id of the subscription to `op` whose params hold `match` (the first one without it). */
  function subId(op: OpName, match: Params = {}): string {
    const sub = harness.client.stream
      .subscriptions(op)
      .find((s) => Object.entries(match).every(([k, v]) => (s.params as Params)[k] === v));
    if (!sub) throw new Error(`no live subscription for ${op} with ${JSON.stringify(match)}`);
    return sub.id;
  }

  /** Pushes a result for the subscription to `op` (matching `match`) on the newest stream. */
  async function result(op: OpName, data: unknown, match: Params = {}, rev = 1): Promise<void> {
    harness.net.lastStream().push(resultFrame(subId(op, match), data, rev));
    await flush();
  }

  /** The SDK reopens the stream 150 ms after the subscriptions change: results come on the new one. */
  async function reopen(): Promise<void> {
    await harness.clock.advance(150);
  }

  /** The API calls made so far (the stream aside). */
  function sent(): SentCall[] {
    return harness.net.api.map(({ url, init }) => {
      const parsed = new URL(url, 'http://a.localhost');
      return {
        method: String(init.method ?? 'GET').toUpperCase(),
        path: parsed.pathname,
        query: Object.fromEntries(parsed.searchParams),
        body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
      };
    });
  }

  /** Answers every API call with `status` and `body` from now on. */
  function answer(status: number, body: unknown): void {
    harness.net.onApi(() => Response.json(body, { status }));
  }

  const find = (testid: string) => wrapper.find(`[data-testid="${testid}"]`);
  /** In the mounted tree (the test modal renders in place) or in the document (`useConfirm`'s dialog
   *  lives in a host of its own on the body). Not attached: Ionic's icons would try the network. */
  const inDoc = (testid: string): HTMLElement | null => {
    const selector = `[data-testid="${testid}"]`;
    const found = wrapper.find(selector);
    return (found.exists() ? found.element : document.querySelector(selector)) as HTMLElement | null;
  };

  return { ...harness, router, wrapper, live, params, subId, result, reopen, sent, answer, find, inDoc };
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

/** Lets Vue render and a dialog's `didPresent` (next tick) land. */
export async function settle(): Promise<void> {
  await flush();
  await flush();
}

/** Fires an Ionic value event on an element, as Ionic does (`ionInput`/`ionChange` with the value). */
export async function ionValue(el: Element | null, value: unknown, event: 'ionInput' | 'ionChange' = 'ionChange'): Promise<void> {
  if (!el) throw new Error('no element to set');
  (el as HTMLElement & { value?: unknown }).value = value;
  el.dispatchEvent(new CustomEvent(event, { detail: { value }, bubbles: true }));
  await settle();
}

/** Clicks an element the way a person does (a real click event, bubbling). */
export async function click(el: Element | null): Promise<void> {
  if (!el) throw new Error('nothing to click');
  el.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
  await settle();
}

export type { LiveClient };
