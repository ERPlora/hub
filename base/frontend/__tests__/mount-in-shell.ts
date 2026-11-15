// Mounts a screen as the hub's shell does, for the tests of base and of every app: the SDK's live harness (fake clock,
// fake network serving the stream and the API) on the hub's generated op → route map, a memory router, the session and
// the shell's i18n with the catalogues the app names. Each app's helper (`mount-<app>.ts`) sets its start path, its
// person and its words once; the tools that drive the stream, answer the API and find what the screen painted, and the
// gestures and fixtures those tests share, live here.
import {
  createShellI18n,
  provideSession,
  provideShellConfig,
  type SessionMe,
  type SessionStatus,
  type ShellConfig,
} from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY, type LiveClient, type OpName, stableJson } from '@erplora/ui/sdk';
import { mount } from '@vue/test-utils';
import { type Component, createApp, isRef, type Ref, ref } from 'vue';
import { createMemoryHistory, createRouter, type RouteMeta, type Router } from 'vue-router';

import {
  type ApiHandler,
  createTestClient,
  flush,
  resultFrame,
  type StreamCall,
} from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import baseEn from '../locale/en.json';
import baseEs from '../locale/es.json';
import type { Business } from '../operations';

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../packages/ui/src/sdk/__tests__/live-harness';
export type { LiveClient };

export type Params = Record<string, unknown>;

/** One language's words of the screens under test. */
export type Catalogue = Record<string, unknown>;

/** One API call the page made: method, path, query and JSON body. */
export interface SentCall {
  method: string;
  path: string;
  query: Params;
  body: unknown;
}

/** An answer by path: a status and a body, or a reply the test holds and sends when it wants (a slow read). */
export type Answers = Record<string, [number, unknown] | (() => Promise<Response>)>;

/** What a test says of the mount of an app's page (`mount<App>`); the rest is the app's (`ShellApp`). */
export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** API answers by path, in place before the component mounts (what it reads when it opens). */
  answers?: Answers;
}

/** The options of an app whose pages follow the business. */
export interface BusinessMountOptions extends MountOptions {
  /** What `base.business.get` answers when the stream opens, over the app's (`ShellApp.business`); `null`: it never
   *  answers (the currency unknown). */
  business?: Business | null;
}

/** All `mountInShell` takes from a test: an app's options and what base's own helper and a few apps add. */
export interface ShellMountOptions extends Omit<BusinessMountOptions, 'session'> {
  /** `null`: no session arrived (yet, or ever: see `status`); a ref: a session the test changes while the page is open. */
  session?: SessionMe | Ref<SessionMe> | null;
  status?: SessionStatus;
  attachTo?: HTMLElement;
  /** How the API answers from before the mount (what a component asks as it mounts gets it). */
  api?: ApiHandler;
}

/** What an app's test helper sets once for all its tests. */
export interface ShellApp {
  /** Where the router stands, unless the test says. */
  path: string;
  /** Who is signed in, unless the test says. */
  session: SessionMe;
  /** The screens' words by language: the app's own over those of base or of the apps it requires. */
  messages: { en: Catalogue; es: Catalogue };
  /** By default, `memoryRouter()`. */
  router?: Router;
  /** More of what the shell provides app-wide (Ionic's router API, a config of its own…). */
  provide?: Record<string | symbol, unknown>;
  /** The shell's config, with its defaults filled in as `createShell` does. */
  shell?: Partial<ShellConfig>;
  /** What the platform's `base.business.get` answers as the stream opens, when a piece follows it (none: it is never
   *  answered, unless the test gives one). */
  business?: Business;
  /** Where `inDoc` looks before the document: the mount's container (by default) or the component's own nodes. */
  inDocFrom?: 'container' | 'component';
}

/** The app's words over base's, as the hub loads base's for every app. */
export function overBase(en: Catalogue, es: Catalogue): ShellApp['messages'] {
  return { en: { ...baseEn, ...en }, es: { ...baseEs, ...es } };
}

/** A memory router that opens every path on a blank page, with `meta` on it. */
export function memoryRouter(meta: RouteMeta = {}): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' }, meta }],
  });
}

export async function mountInShell(component: Component, options: ShellMountOptions, app: ShellApp) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  if (options.api) harness.net.onApi(options.api);
  if (options.answers) answerPaths(harness, options.answers);
  const router = app.router ?? memoryRouter();
  await router.push(options.path ?? app.path);
  await router.isReady();
  // The session and the shell's config are provided app-wide, as createShell does.
  const shell = createApp({});
  const session = isRef(options.session) ? options.session : ref(options.session === null ? undefined : (options.session ?? app.session));
  provideSession(session, ref(options.status ?? 'live'), { app: shell });
  if (app.shell) provideShellConfig(app.shell, shell);
  const i18n = createShellI18n({ locale: options.locale ?? 'en', messages: app.messages });
  const wrapper = mount(component, {
    props: options.props,
    attachTo: options.attachTo,
    global: {
      plugins: [router, i18n],
      provide: { ...shell._context.provides, ...app.provide, [LIVE_CLIENT_KEY as symbol]: harness.client },
      stubs: options.stubs,
    },
  });

  /** Opens the stream and answers the business, if there is one and a piece follows it; returns the call. */
  async function live(): Promise<StreamCall> {
    const call = await harness.goLive();
    const answer = options.business === undefined ? app.business : options.business;
    if (answer && harness.client.stream.subscriptions('base.business.get').length) await result('base.business.get', answer);
    return call;
  }

  /** The params of every live subscription to `op`. */
  const params = (op: OpName): Params[] => harness.client.stream.subscriptions(op).map((s) => s.params as Params);

  /** The id of the subscription to `op` whose params hold `match` (the first one without it). */
  function matchingSubId(op: OpName, match: Params = {}): string {
    const sub = harness.client.stream
      .subscriptions(op)
      .find((s) => Object.entries(match).every(([k, v]) => (s.params as Params)[k] === v));
    if (!sub) throw new Error(`no live subscription for ${op} with ${JSON.stringify(match)}`);
    return sub.id;
  }

  /** Pushes a result for the subscription to `op` (matching `match`) on the newest stream. */
  async function result(op: OpName, data: unknown, match: Params = {}, rev = 1): Promise<void> {
    harness.net.lastStream().push(resultFrame(matchingSubId(op, match), data, rev));
    await flush();
  }

  /** Pushes a result on `call` for the subscription of `op` (the first, or the one with exactly `params`). */
  async function resultOn(call: StreamCall, op: OpName, data: unknown, rev = 1, params?: unknown): Promise<void> {
    call.push(resultFrame(subId(harness.client, op, params), data, rev));
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
  function answerBy(routes: Answers): void {
    answerPaths(harness, routes);
  }

  const find = (testid: string) => wrapper.find(`[data-testid="${testid}"]`);

  /** In the mounted tree (the test modal renders in place) or in the document (`useConfirm`'s dialog lives in a host
   *  of its own on the body). Not attached: Ionic's icons would try the network. */
  const inDoc = (testid: string): HTMLElement | null => {
    const selector = `[data-testid="${testid}"]`;
    if (app.inDocFrom === 'component') {
      const found = wrapper.find(selector);
      return (found.exists() ? found.element : document.querySelector(selector)) as HTMLElement | null;
    }
    const root = wrapper.element as Element;
    return ((root.parentElement ?? root).querySelector(selector) ?? document.querySelector(selector)) as HTMLElement | null;
  };

  /** The person changes the app's language (the shell's selector): what is on screen follows it. */
  async function setLocale(locale: 'en' | 'es'): Promise<void> {
    i18n.global.locale.value = locale;
    await flush();
  }

  return {
    ...harness,
    router,
    wrapper,
    live,
    params,
    subId: matchingSubId,
    result,
    resultOn,
    reopen,
    sent,
    answer,
    answerBy,
    find,
    inDoc,
    setLocale,
  };
}

/** The subscription id the stream holds for `op`: the first one, or the one whose params are exactly `params`. */
export function subId(client: LiveClient, op: OpName, params?: unknown): string {
  const subs = client.stream.subscriptions(op);
  const sub = params === undefined ? subs[0] : subs.find((s) => stableJson(s.params) === stableJson(params));
  if (!sub) throw new Error(`no live subscription for ${op}`);
  return sub.id;
}

function answerPaths(harness: ReturnType<typeof createTestClient>, routes: Answers): void {
  harness.net.onApi(({ url }) => {
    const path = new URL(url, 'http://a.localhost').pathname;
    const route = routes[path] ?? [404, { error: { code: 'not_found', message: 'Not found' } }];
    if (typeof route === 'function') return route();
    const [status, body] = route;
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
