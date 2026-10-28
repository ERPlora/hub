// Test helper of the invoice app's pages and components, as `mount-sale.ts` is the sale app's: the SDK's live
// harness (fake clock, fake network serving the stream and the API) on the hub's generated op → route
// map, the shell's i18n with the invoice catalogues merged in, a session and a memory router.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `ionModalStub` (imported
// from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
// `platformNotice` paints a page as the hub does: base's blocking strip over it (`chrome.notice`, frontend/main.ts).
import { createShellI18n, provideSession, type SessionMe, SHELL_CONFIG_KEY } from '@erplora/ui/shell';
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
import BlockingStrip from '../../../../base/frontend/components/BlockingStrip.vue';
import baseEn from '../../../../base/frontend/locale/en.json';
import baseEs from '../../../../base/frontend/locale/es.json';
import type { Business, SetupStatus } from '../../../../base/frontend/operations';
import { OPERATION_ROUTES } from '../../../../frontend/generated/operation-routes';
import { ComposableHost } from './composable-host';
import en from '../locale/en.json';
import es from '../locale/es.json';

// happy-dom made to behave as a browser where Ionic's runtime reaches it, by each helper: the hub setup
// (vitest.setup.ts) only unmounts what a test left mounted and fails one that leaves a real timer armed.
fillHappyDomGaps();

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../../packages/ui/src/sdk/__tests__/live-harness';

/** The business of the hub (`base.business.get`): one in Spain, in euros, unless a test says another
 *  (flow business-currency: what a person types is read in the business's money). */
export function business(fields: Partial<Business> = {}): Business {
  return {
    name: 'Peluquería Ana',
    country: 'ES',
    country_name: 'Spain',
    timezone: 'Europe/Madrid',
    language: 'es',
    language_name: 'Spanish',
    currency: 'EUR',
    currency_label: 'EUR · Euro',
    currency_decimals: 2,
    demo: false,
    settings_url: 'https://erplora.com/businesses/1/settings',
    ...fields,
  };
}

export const POLISH: Partial<Business> = { country: 'PL', country_name: 'Poland', currency: 'PLN', currency_label: 'PLN · Polish Zloty' };
export const JAPANESE: Partial<Business> = { country: 'JP', country_name: 'Japan', currency: 'JPY', currency_label: 'JPY · Japanese Yen', currency_decimals: 0 };

/** Every permission of the invoice app (owner, admin: apps.py `role_permissions`) and what its screens
 *  read from the other apps (Customers' cards for the recipient, Taxes' categories). */
export const INVOICE_PERMISSIONS = [
  'invoice.view_invoice',
  'invoice.add_invoice',
  'invoice.rectify_invoice',
  'invoice.manage_series',
  'invoice.manage_issuer',
];
const READS = ['customer.view', 'customer.manage', 'tax.view', 'sale.view_sale'];

/** The owner (and the admin): every permission of the app. */
export const OWNER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: [...INVOICE_PERMISSIONS, ...READS],
  menu: [],
  apps: [],
  language: 'en',
};

/** The manager: everything but the issuer. */
export const MANAGER: SessionMe = {
  ...OWNER,
  permissions: ['invoice.view_invoice', 'invoice.add_invoice', 'invoice.rectify_invoice', 'invoice.manage_series', ...READS],
};

/** The employee: looks, prints, issues by hand and marks paid. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  permissions: ['invoice.view_invoice', 'invoice.add_invoice', ...READS],
};

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** The page behind a session with the hub's chrome: base's blocking strip over it, in base's words too. */
  platformNotice?: boolean;
}

type Params = Record<string, unknown>;

/** One API call the page made: method, path, query and JSON body. */
export interface SentCall {
  method: string;
  path: string;
  query: Params;
  body: unknown;
}

export async function mountInvoice(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' }, meta: options.platformNotice ? { auth: true } : {} }],
  });
  await router.push(options.path ?? '/invoice/invoices');
  await router.isReady();
  // The session is provided app-wide, as createShell does.
  const app = createApp({});
  provideSession(ref(options.session ?? OWNER), ref('live'), { app });
  const messages = options.platformNotice ? { en: { ...baseEn, ...en }, es: { ...baseEs, ...es } } : { en, es };
  const chrome = options.platformNotice ? { [SHELL_CONFIG_KEY as symbol]: { homePath: '/', chrome: { notice: BlockingStrip } } } : {};
  const wrapper = mount(component, {
    props: options.props,
    global: {
      plugins: [router, createShellI18n({ locale: options.locale ?? 'en', messages })],
      provide: { ...app._context.provides, ...chrome, [LIVE_CLIENT_KEY as symbol]: harness.client },
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

export type MountedInvoice = Awaited<ReturnType<typeof mountInvoice>>;

/** Invoicing's ⛔ «Your business details» as `base.setup.status` tells it (apps.py `setup`; gh:hub#435: also to whoever
 *  may not set it up, with `actionable: false`), in the person's language. */
export function issuerStatus(fields: { configured: boolean; actionable: boolean; locale?: 'en' | 'es' }): SetupStatus {
  const pending = fields.configured ? 0 : 1;
  return {
    total: 1,
    pending,
    unavailable: 0,
    blocking_pending: pending,
    items: [
      {
        key: 'invoice.business_identity',
        app: 'invoice',
        state: fields.configured ? 'done' : 'pending',
        level: 'legal',
        required: true,
        actionable: fields.actionable,
        title: fields.locale === 'es' ? 'Los datos de tu negocio' : 'Your business details',
        description: '',
        icon: 'ion:storefront-outline',
        route: '/invoice/issuer',
        order: 40,
      },
    ],
  };
}

/** What the hub answers every live question of a screen about its issuer (the platform's strip and, if the screen
 *  asks, `invoice.issuer.get`): set up or missing, for the person mounted (`actionable` by `invoice.manage_issuer`). */
export async function answerIssuer(m: MountedInvoice, configured: boolean, options: { locale?: 'en' | 'es'; actionable?: boolean; rev?: number } = {}) {
  const status = issuerStatus({ configured, actionable: options.actionable ?? true, locale: options.locale });
  const asked = (op: OpName) => m.client.stream.subscriptions(op).length > 0;
  if (asked('base.setup.status')) await m.result('base.setup.status', status, {}, options.rev);
  if (asked('invoice.issuer.get')) await m.result('invoice.issuer.get', { configured }, {}, options.rev);
}

/** The red notices on the screen, whatever their words: base's strip and any danger notice of the page's own. */
export function redNotices(m: MountedInvoice): number {
  return m.wrapper.findAll('[data-testid="blocking-strip"], [data-tone="danger"]').length;
}

/** How many times `needle` is said in `text`. */
export function said(text: string, needle: string): number {
  return text.split(needle).length - 1;
}

/** Mounts `use` (a composable call) inside a component of the invoice app's harness. */
export function mountComposable(use: () => void, options: Omit<MountOptions, 'props'> = {}) {
  return mountInvoice(ComposableHost, { ...options, props: { use } });
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
