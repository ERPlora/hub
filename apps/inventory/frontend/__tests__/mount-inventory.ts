// Test helper of the inventory's pages and components: `mountInShell` with its catalogues over base's, the dashboard,
// its people and the hub's business; the API's answers and the catalogue's rows its tests share. Tests that open a
// dialog mock `@ionic/vue`'s IonModal with `IonModalStub` (an overlay only presents itself in a real browser).
import type { SessionMe } from '@erplora/ui/shell';
import { ApiError, type LiveClient, type OpName } from '@erplora/ui/sdk';
import type { Component, Ref } from 'vue';

import type { ApiCall, StreamCall } from '../../../../packages/ui/src/sdk/__tests__/live-harness';
import { flush, mountInShell, overBase, page, resultFrame } from '../../../../base/frontend/__tests__/mount-in-shell';
import { business } from '../../../../base/frontend/__tests__/business';
import type { Business } from '../../../../base/frontend/operations';
import en from '../locale/en.json';
import es from '../locale/es.json';

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

/** The business of the hub (`base.business.get`): one in Spain, in euros, unless a test says another
 *  (flow business-currency: the money of every screen is the business's). */
export { business, POLISH } from '../../../../base/frontend/__tests__/business';

export interface MountOptions {
  props?: Record<string, unknown>;
  /** What `base.business.get` answers when the stream opens; `null`: it never answers (the currency unknown). */
  business?: Business | null;
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
  const mounted = await mountInShell(
    component,
    { ...options, session: options.sessionRef ?? options.session, attachTo: options.attach ? document.body : undefined },
    { path: '/inventory/dashboard', session: MANAGER, messages: overBase(en, es), business: business() },
  );
  const { client, net } = mounted;
  /** Pushes a result for the `index`-th subscription of `op` and lets Vue render it. */
  async function result(call: StreamCall, op: OpName, data: unknown, rev = 1, index = 0): Promise<void> {
    call.push(resultFrame(subId(client, op, index), data, rev));
    await flush();
  }
  /** API calls made so far to `path` (without the query string). */
  const calls = (path: string): ApiCall[] => net.api.filter((call) => call.url.split('?')[0] === path);
  /** The JSON body of an API call. */
  const body = (call: ApiCall): unknown => JSON.parse(String(call.init.body));
  /** The query of an API call. */
  const query = (call: ApiCall): Record<string, string> => Object.fromEntries(new URL(call.url, 'http://a.localhost').searchParams);
  return { ...mounted, result, calls, body, query };
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
