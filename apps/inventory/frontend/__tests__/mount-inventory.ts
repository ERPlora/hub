// Test helper of the inventory's pages and components: the SDK's live harness (fake clock, fake
// network serving the stream and the API) on the hub's generated op → route map, the shell's i18n
// with the inventory catalogues merged in, a session and a memory router. Pages are mounted as the
// shell would. Tests that open a dialog mock `@ionic/vue`'s IonModal with `IonModalStub` (an overlay
// only presents itself in a real browser).
import { createShellI18n, provideSession, type SessionMe } from '@erplora/ui/shell';
import { ApiError, LIVE_CLIENT_KEY, type LiveClient, type OpName } from '@erplora/ui/sdk';
import { fillHappyDomGaps } from '@erplora/ui/testing';
import { mount } from '@vue/test-utils';
import { type Component, createApp, type Ref, ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

// The hub does not depend on ionicons itself: its registry is global (`window.Ionicons`), so the
// copy @erplora/ui installs registers the shell's icons as `createShell` does at boot (an icon that
// is not registered makes ion-icon try a URL and log «Invalid URL» in happy-dom).
import { addIcons } from '../../../../packages/ui/node_modules/ionicons';
import { ION_ICONS } from '../../../../packages/ui/src/shell/icons';

import {
  createTestClient,
  flush,
  resultFrame,
  type ApiCall,
  type StreamCall,
} from '../../../../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from '../../../../frontend/generated/operation-routes';
import en from '../locale/en.json';
import es from '../locale/es.json';

// happy-dom made to behave as a browser where Ionic's runtime reaches it, by each helper: the hub setup
// (vitest.setup.ts) only unmounts what a test left mounted and fails one that leaves a real timer armed.
fillHappyDomGaps();
addIcons(ION_ICONS);

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../../packages/ui/src/sdk/__tests__/live-harness';
export type { ApiCall, StreamCall };

const ALL = [
  'inventory.view_product',
  'inventory.view_category',
  'inventory.view_stock',
  'inventory.add_product',
  'inventory.change_product',
  'inventory.delete_product',
  'inventory.add_category',
  'inventory.change_category',
  'inventory.delete_category',
  'inventory.import_product',
  'inventory.export_product',
  'inventory.adjust_stock',
  'inventory.manage_settings',
  'tax.view',
  'tax.manage',
];

/** An owner or a manager: every inventory permission (apps.py `role_permissions`). */
export const MANAGER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ALL,
  menu: [],
  apps: [],
  language: 'en',
};

/** An employee: sees products, categories and movements, writes nothing. */
export const EMPLOYEE: SessionMe = {
  ...MANAGER,
  user: { id: 'u2', label: 'Leo' },
  permissions: ['inventory.view_product', 'inventory.view_category', 'inventory.view_stock', 'tax.view'],
};

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  /** A session the test changes while the page is open (a shift change). */
  sessionRef?: Ref<SessionMe>;
  stubs?: Record<string, Component | boolean>;
  attach?: boolean;
  /** How the API answers from the start (what a page asks while mounting). */
  api?: (call: ApiCall) => Response | Promise<Response>;
}

/** The subscription id the stream holds for `op` (the `index`-th one). */
export function subId(client: LiveClient, op: OpName, index = 0): string {
  const sub = client.stream.subscriptions(op)[index];
  if (!sub) throw new Error(`no live subscription for ${op}`);
  return sub.id;
}

/** A JSON answer of the API. */
export const ok = (data: unknown, status = 200): Response => Response.json(data, { status });

/** The error envelope of the API. */
export const refusal = (status: number, code: string, message: string, fields?: Record<string, string>): Response =>
  Response.json({ error: { code, message, ...(fields ? { fields } : {}) } }, { status });

/** The `ApiError` a refusal becomes. */
export const apiError = (status: number, code: string, message: string, fields?: Record<string, string>): ApiError =>
  new ApiError(status, code, message, fields);

/** A page of a list. */
export const page = <T>(rows: T[], total = rows.length, limit = 50, offset = 0) => ({ rows, total, limit, offset });

/** The tax categories Taxes seeds (`tax.category.list` rows). */
export const TAX_CATEGORIES = page([
  {
    id: 't1',
    key: 'product.generic',
    name: 'Product — generic',
    description: '',
    display_name: 'Product — generic',
    display_description: '',
    is_system: true,
    is_active: true,
    rate_pct: '21.00',
    operation_class: 'subject',
  },
  {
    id: 't2',
    key: 'service.health',
    name: 'Service — healthcare (VAT exempt)',
    description: '',
    display_name: 'Service — healthcare (VAT exempt)',
    display_description: '',
    is_system: true,
    is_active: true,
    rate_pct: '0.00',
    operation_class: 'exempt',
  },
  {
    id: 't3',
    key: 'shop.own',
    name: 'Own category',
    description: '',
    display_name: 'Own category',
    display_description: '',
    is_system: false,
    is_active: true,
    rate_pct: null,
    operation_class: null,
  },
]);

/** The eight units (`inventory.unit.list`), named as the API names them: with their code. */
export const UNITS = page(
  [
    ['ud', 'Unit (ud)', 'count', '1'],
    ['kg', 'Kilogram (kg)', 'mass', '0.001'],
    ['g', 'Gram (g)', 'mass', '1'],
    ['t', 'Tonne (t)', 'mass', '0.001'],
    ['l', 'Litre (l)', 'volume', '0.001'],
    ['ml', 'Millilitre (ml)', 'volume', '1'],
    ['min', 'Minute (min)', 'time', '1'],
    ['h', 'Hour (h)', 'time', '0.25'],
  ].map(([code, name, category, increment]) => ({
    code,
    name,
    category,
    factor_num: 1,
    factor_den: 1,
    increment,
    is_reference: false,
  })),
  8,
  100,
);

/** A product as the API returns it. */
export function product(overrides: Record<string, unknown> = {}) {
  return {
    id: 'p1',
    name: 'Coffee',
    sku: 'CAF-1',
    ean13: null,
    description: '',
    product_type: 'physical',
    price: 220,
    cost: 80,
    stock: '5.000',
    low_stock_threshold: '10.000',
    unit: 'ud',
    price_quantity: '1.000',
    pricing_unit: 'ud',
    tax_category_id: 't1',
    tax_category_key: 'product.generic',
    needs_tax_setup: false,
    track_stock: null,
    tracks_stock: true,
    is_active: true,
    is_sold_out: false,
    category_ids: [],
    created_at: '2026-10-13T10:00:00Z',
    updated_at: '2026-10-13T10:00:00Z',
    ...overrides,
  };
}

/** A product category as the API returns it. */
export function category(overrides: Record<string, unknown> = {}) {
  return {
    id: 'c1',
    name: 'Drinks',
    slug: 'drinks',
    description: '',
    icon: 'ion:cube-outline',
    color: '#3880ff',
    order: 0,
    tax_category_id: null,
    tax_category_key: null,
    product_count: 2,
    ...overrides,
  };
}

export async function mountInventory(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  if (options.api) harness.net.onApi(options.api);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/inventory/dashboard');
  await router.isReady();
  // The session is provided app-wide, as createShell does.
  const app = createApp({});
  provideSession(options.sessionRef ?? ref(options.session ?? MANAGER), ref('live'), { app });
  const wrapper = mount(component, {
    props: options.props,
    attachTo: options.attach ? document.body : undefined,
    global: {
      plugins: [router, createShellI18n({ locale: options.locale ?? 'en', messages: { en, es } })],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: harness.client },
      stubs: options.stubs,
    },
  });
  /** Opens the stream; returns the call to push frames into. */
  const live = (): Promise<StreamCall> => harness.goLive();
  /** Pushes a result for the `index`-th subscription of `op` and lets Vue render it. */
  async function result(call: StreamCall, op: OpName, data: unknown, rev = 1, index = 0): Promise<void> {
    call.push(resultFrame(subId(harness.client, op, index), data, rev));
    await flush();
  }
  /** The live params of every subscription of `op`. */
  const params = (op: OpName): unknown[] => harness.client.stream.subscriptions(op).map((s) => s.params);
  /** API calls made so far to `path` (without the query string). */
  const calls = (path: string): ApiCall[] => harness.net.api.filter((call) => call.url.split('?')[0] === path);
  /** The JSON body of an API call. */
  const body = (call: ApiCall): unknown => JSON.parse(String(call.init.body));
  /** The query of an API call. */
  const query = (call: ApiCall): Record<string, string> => Object.fromEntries(new URL(call.url, 'http://a.localhost').searchParams);
  return { ...harness, router, wrapper, live, result, params, calls, body, query };
}
