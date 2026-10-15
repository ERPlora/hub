// Test helper of the table app's pages and components, as `mount-service.ts` is the service app's: the SDK's
// live harness (fake clock, fake network serving the stream and the API) on the hub's op → route map,
// the shell's i18n with the table catalogues merged in (and Customers', whose search the table window mounts), a session and a memory router.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
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
import customerEn from '../../../customer/frontend/locale/en.json';
import customerEs from '../../../customer/frontend/locale/es.json';
import en from '../locale/en.json';
import es from '../locale/es.json';

fillHappyDomGaps();

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../../packages/ui/src/sdk/__tests__/live-harness';

const SALE = ['sale.view_sale', 'sale.add_sale', 'sale.take_payment', 'customer.view', 'customer.manage'];

/** Owner or admin: `table.*` (apps.py `role_permissions`), listed one by one; they sell and see customers. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Ana' },
  permissions: [
    'table.view_zone',
    'table.add_zone',
    'table.change_zone',
    'table.delete_zone',
    'table.view_table',
    'table.add_table',
    'table.change_table',
    'table.delete_table',
    'table.view_session',
    'table.add_session',
    'table.change_session',
    'table.transfer_session',
    'table.delete_session',
    'table.view_settings',
    'table.manage_settings',
    ...SALE,
  ],
  menu: [],
  apps: [],
  language: 'en',
};

const ADMIN_ONLY = ['table.delete_zone', 'table.delete_table', 'table.delete_session', 'table.manage_settings'];

/** A manager draws the room and serves it; deleting and the settings are the owner's and the admin's. */
export const MANAGER: SessionMe = {
  ...OWNER,
  permissions: OWNER.permissions.filter((p) => !ADMIN_ONLY.includes(p)),
};

/** A waiter (the old employee and cashier) serves the room, never draws it. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Luis' },
  permissions: [
    'table.view_zone',
    'table.view_table',
    'table.view_session',
    'table.add_session',
    'table.change_session',
    'table.transfer_session',
    'table.view_settings',
    ...SALE,
  ],
};

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** API answers by path, in place before the component mounts (what it reads when it opens). */
  answers?: Record<string, [number, unknown]>;
}

type Params = Record<string, unknown>;

/** One API call the page made: method, path, query and JSON body. */
export interface SentCall {
  method: string;
  path: string;
  query: Params;
  body: unknown;
}

export async function mountTable(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  if (options.answers) answerPaths(harness, options.answers);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/table/floor-plan');
  await router.isReady();
  const app = createApp({});
  provideSession(ref(options.session ?? OWNER), ref('live'), { app });
  const wrapper = mount(component, {
    props: options.props,
    global: {
      plugins: [router, createShellI18n({ locale: options.locale ?? 'en', messages: { en: { ...customerEn, ...en }, es: { ...customerEs, ...es } } })],
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

  /** Answers each API call by its path (a call not listed gets a 404 envelope). */
  function answerBy(routes: Record<string, [number, unknown]>): void {
    answerPaths(harness, routes);
  }

  const find = (testid: string) => wrapper.find(`[data-testid="${testid}"]`);
  /** In the mounted tree (the test modal renders in place) or in the document (`useConfirm`'s dialog
   *  lives in a host of its own on the body). */
  const inDoc = (testid: string): HTMLElement | null => {
    const root = wrapper.element as Element;
    const selector = `[data-testid="${testid}"]`;
    return ((root.parentElement ?? root).querySelector(selector) ?? document.querySelector(selector)) as HTMLElement | null;
  };

  return { ...harness, router, wrapper, live, params, subId, result, reopen, sent, answer, answerBy, find, inDoc };
}

/** Answers each API call of `harness` by its path (a call not listed gets a 404 envelope). */
function answerPaths(harness: ReturnType<typeof createTestClient>, routes: Record<string, [number, unknown]>): void {
  harness.net.onApi(({ url }) => {
    const path = new URL(url, 'http://a.localhost').pathname;
    const [status, body] = routes[path] ?? [404, { error: { code: 'not_found', message: 'Not found' } }];
    return Response.json(body, { status });
  });
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

/** Toggles an `ion-toggle`/`ion-checkbox` as Ionic does (`ionChange` with `checked`). */
export async function ionChecked(el: Element | null, checked: boolean): Promise<void> {
  if (!el) throw new Error('no element to toggle');
  (el as HTMLElement & { checked?: boolean }).checked = checked;
  el.dispatchEvent(new CustomEvent('ionChange', { detail: { checked, value: 'on' }, bubbles: true }));
  await settle();
}

/** Clicks an element the way a person does (a real click event, bubbling). */
export async function click(el: Element | null): Promise<void> {
  if (!el) throw new Error('nothing to click');
  el.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
  await settle();
}

/** A page of a list, as the server answers it. */
export function page<T>(rows: T[], total = rows.length, limit = 50, offset = 0) {
  return { rows, total, limit, offset };
}

export type { LiveClient };
