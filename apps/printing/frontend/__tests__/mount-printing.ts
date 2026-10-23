// Test helper of the printing app's pages and components (the pattern of the sale app's): the SDK's live
// harness (fake clock, fake network serving the stream and the API) on the hub's generated op → route
// map, the shell's i18n with the printing catalogues, a session and a memory router.
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
import { ComposableHost } from './composable-host';
import en from '../locale/en.json';
import es from '../locale/es.json';

// happy-dom made to behave as a browser where Ionic's runtime reaches it, by each helper: the hub setup
// (vitest.setup.ts) only unmounts what a test left mounted and fails one that leaves a real timer armed.
fillHappyDomGaps();

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../../packages/ui/src/sdk/__tests__/live-harness';

/** Every permission of the printing app (owner and admin). */
export const PRINTING_PERMISSIONS = ['printing.view_settings', 'printing.manage_settings', 'printing.print', 'printing.manage_jobs'];

export const ADMIN: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: [...PRINTING_PERMISSIONS],
  menu: [],
  apps: [],
  language: 'en',
};

/** The manager: sets printers up and prints; the queue's retry and cancel are not theirs. */
export const MANAGER: SessionMe = {
  ...ADMIN,
  permissions: ['printing.view_settings', 'printing.manage_settings', 'printing.print'],
};

/** The employee: sees printers, settings and queue, and prints (a test, a receipt). */
export const EMPLOYEE: SessionMe = { ...ADMIN, permissions: ['printing.view_settings', 'printing.print'] };

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
}

type Params = Record<string, unknown>;

/** One API call the page made: method, path, query and JSON body. */
export interface SentCall {
  method: string;
  path: string;
  query: Params;
  body: unknown;
}

export async function mountPrinting(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/printing/printers');
  await router.isReady();
  // The session is provided app-wide, as createShell does.
  const app = createApp({});
  provideSession(ref(options.session ?? ADMIN), ref('live'), { app });
  const wrapper = mount(component, {
    props: options.props,
    global: {
      plugins: [router, createShellI18n({ locale: options.locale ?? 'en', messages: { en, es } })],
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

/** Mounts `use` (a composable call) inside a component of the app's harness. */
export function mountComposable(use: () => void, options: Omit<MountOptions, 'props'> = {}) {
  return mountPrinting(ComposableHost, { ...options, props: { use } });
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

/** What a person reads in `el`: its texts in order, one space apart (no-break spaces as plain ones). */
export function words(el: Element): string {
  const out: string[] = [];
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = (node.textContent ?? '').replace(/[  ]/g, ' ').replace(/\s+/g, ' ').trim();
    if (text) out.push(text);
  }
  return out.join(' ');
}

/** Flips an `ion-toggle` as Ionic does (`ionChange` with `{ checked }`). */
export async function ionToggle(el: Element | null, checked: boolean): Promise<void> {
  if (!el) throw new Error('no toggle to flip');
  (el as HTMLElement & { checked?: boolean }).checked = checked;
  el.dispatchEvent(new CustomEvent('ionChange', { detail: { checked, value: 'on' }, bubbles: true }));
  await settle();
}
