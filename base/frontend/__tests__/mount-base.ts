// Test helper of base's Home and its pieces of the chrome: the SDK's live harness (fake clock, fake network
// serving the stream and the API) on the hub's generated op → route map, the shell's i18n with base's
// catalogues and the shared assistant's words merged in, the assistant configured as the Hub's (both as main.ts
// does), a session, the shell's config, a memory router with the routes a test names and Ionic's router API on it
// (`useIonRouter`).
import {
  createShellI18n,
  provideSession,
  provideShellConfig,
  type SessionMe,
  type SessionStatus,
  type ShellSidebar,
} from '@erplora/ui/shell';
import { assistantMessages, configureAssistant } from '@erplora/ui/components';
import { LIVE_CLIENT_KEY, type LiveClient, type OpName } from '@erplora/ui/sdk';
import { mount } from '@vue/test-utils';
import { vi } from 'vitest';
import { type Component, createApp, ref } from 'vue';
import { createMemoryHistory, createRouter, type RouteLocationRaw, type Router, type RouteRecordRaw } from 'vue-router';

import {
  type ApiHandler,
  createTestClient,
  flush,
  resultFrame,
  type StreamCall,
} from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import { HUB_ASSISTANT } from '../lib/assistant-hub';
import { forgetAppDistribution } from '../lib/management';
import type { Business } from '../operations';
import en from '../locale/en.json';
import es from '../locale/es.json';

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../packages/ui/src/sdk/__tests__/live-harness';

configureAssistant(HUB_ASSISTANT);

export const OWNER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['base.view_home', 'base.administer_hub', 'demo.view', 'demo.manage'],
  menu: [],
  apps: [],
  language: 'en',
};

export const EMPLOYEE: SessionMe = { ...OWNER, user: { id: 'u2', label: 'Leo' }, permissions: ['base.view_home', 'demo.view'] };

/** What `base.business.get` answers for a Spanish business; `fields` change it (BASE-G98: the Home's amounts are in
 *  its currency). */
export function business(fields: Partial<Business> = {}): Business {
  return {
    name: 'Bar Pepe',
    country: 'ES',
    country_name: 'Spain',
    timezone: 'Europe/Madrid',
    language: 'es',
    language_name: 'Spanish',
    currency: 'EUR',
    currency_label: 'EUR · Euro',
    currency_decimals: 2,
    demo: false,
    settings_url: 'https://erplora.com/hubs/bar-pepe/settings',
    ...fields,
  };
}

export const POLISH = { country: 'PL', country_name: 'Poland', currency: 'PLN', currency_label: 'PLN · Polish Zloty' };

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

/** The installed app's bridge, from the copy it is (`device_context`'s `distribution`: `direct`, `play`, `msstore`);
 *  its `invoke`, to look at. `leaveInstalledApp` takes it away and forgets the copy (`managementOffered`). */
export function installedApp(distribution: string) {
  const invoke = vi.fn(async (command: string) => (command === 'device_context' ? { id: 'd1', distribution } : undefined));
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
  return invoke;
}

export function leaveInstalledApp(): void {
  delete (window as TauriWindow).__TAURI__;
  forgetAppDistribution();
}

/** A click on `element` as a person's tap, to read afterwards whether the page stopped the link (`defaultPrevented`). */
export function tap(element: Element): MouseEvent {
  const click = new MouseEvent('click', { bubbles: true, cancelable: true });
  element.dispatchEvent(click);
  return click;
}

const BLANK = { template: '<div />' };

/** The browser's localStorage (the test environment has none): `vi.stubGlobal('localStorage', memoryStorage())`. */
/** The name a screen reader reads. Attached, `ion-button` moves `aria-label` from its host to the native button of its
 *  shadow root (Ionic's `inheritAriaAttributes`), as in a browser — its native link when it has an `href`;
 *  packages/ui's FormModal tests read it the same. */
export function accessibleName(element: Element): string | null | undefined {
  return element.shadowRoot?.querySelector('button, a')?.getAttribute('aria-label') ?? element.getAttribute('aria-label');
}

export function memoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key) => store.get(key) ?? null,
    key: (index) => [...store.keys()][index] ?? null,
    removeItem: (key) => void store.delete(key),
    setItem: (key, value) => void store.set(key, String(value)),
  };
}

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  /** `null`: no session arrived (yet, or ever: see `status`). */
  session?: SessionMe | null;
  status?: SessionStatus;
  /** Paths the router knows (besides the 404 catch-all named `not-found`, as the shell's). */
  routes?: string[];
  stubs?: Record<string, Component | boolean>;
  sidebar?: ShellSidebar;
  /** What the fake API answers, set before mounting (a component may ask on mount). */
  onApi?: ApiHandler;
}

/** Ionic's router API (`useIonRouter`) as the shell's Ionic router provides it app-wide (`navManager`), on the test's
 *  router: `handleNavigate(location, action, direction)` is a spy that navigates. */
function navManager(router: Router) {
  return {
    handleNavigate: vi.fn((location: RouteLocationRaw, action = 'push') =>
      action === 'replace' ? router.replace(location) : router.push(location),
    ),
    canGoBack: () => Boolean(window.history.state?.back),
    goBack: () => router.back(),
    goForward: () => router.forward(),
  };
}

/** The subscription id the stream holds for `op` (the first one). */
export function subId(client: LiveClient, op: OpName): string {
  const sub = client.stream.subscriptions(op)[0];
  if (!sub) throw new Error(`no live subscription for ${op}`);
  return sub.id;
}

export async function mountBase(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  if (options.onApi) harness.net.onApi(options.onApi);
  const known: RouteRecordRaw[] = (options.routes ?? []).map((path) => ({ path, component: BLANK }));
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'base-home', component: BLANK, meta: { auth: true } },
      ...known,
      { path: '/:pathMatch(.*)*', name: 'not-found', component: BLANK },
    ],
  });
  await router.push(options.path ?? '/');
  await router.isReady();
  // The session and the shell's config are provided app-wide, as createShell does.
  const app = createApp({});
  provideSession(ref(options.session === null ? undefined : (options.session ?? OWNER)), ref(options.status ?? 'live'), {
    app,
  });
  provideShellConfig({ homePath: '/', home: true, sidebar: options.sidebar }, app);
  const ionRouter = navManager(router);
  const wrapper = mount(component, {
    props: options.props,
    attachTo: document.body,
    global: {
      plugins: [
        router,
        createShellI18n({
          locale: options.locale ?? 'en',
          messages: { en: { ...assistantMessages.en, ...en }, es: { ...assistantMessages.es, ...es } },
        }),
      ],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: harness.client, navManager: ionRouter },
      stubs: options.stubs,
    },
  });
  /** Opens the stream; returns the call to push frames into. */
  const live = (): Promise<StreamCall> => harness.goLive();
  /** Pushes a result for the first subscription of `op` and lets Vue render it. */
  async function result(call: StreamCall, op: OpName, data: unknown, rev = 1): Promise<void> {
    call.push(resultFrame(subId(harness.client, op), data, rev));
    await flush();
  }
  return { ...harness, router, ionRouter, wrapper, live, result };
}
