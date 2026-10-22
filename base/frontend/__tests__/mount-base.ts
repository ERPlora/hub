// Test helper of base's Home and its pieces of the chrome: the SDK's live harness (fake clock, fake network
// serving the stream and the API) on the hub's generated op → route map, the shell's i18n with base's
// catalogues merged in, a session, the shell's config and a memory router with the routes a test names.
import {
  createShellI18n,
  provideSession,
  provideShellConfig,
  type SessionMe,
  type SessionStatus,
  type ShellSidebar,
} from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY, type LiveClient, type OpName } from '@erplora/ui/sdk';
import { mount } from '@vue/test-utils';
import { type Component, createApp, ref } from 'vue';
import { createMemoryHistory, createRouter, type RouteRecordRaw } from 'vue-router';

import { createTestClient, flush, resultFrame, type StreamCall } from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import en from '../locale/en.json';
import es from '../locale/es.json';

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../packages/ui/src/sdk/__tests__/live-harness';

export const OWNER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['base.view_home', 'base.administer_hub', 'demo.view', 'demo.manage'],
  menu: [],
  apps: [],
  language: 'en',
};

export const EMPLOYEE: SessionMe = { ...OWNER, user: { id: 'u2', label: 'Leo' }, permissions: ['base.view_home', 'demo.view'] };

const BLANK = { template: '<div />' };

/** The browser's localStorage (the test environment has none): `vi.stubGlobal('localStorage', memoryStorage())`. */
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
  stubs?: Record<string, unknown>;
  sidebar?: ShellSidebar;
}

/** The subscription id the stream holds for `op` (the first one). */
export function subId(client: LiveClient, op: OpName): string {
  const sub = client.stream.subscriptions(op)[0];
  if (!sub) throw new Error(`no live subscription for ${op}`);
  return sub.id;
}

export async function mountBase(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
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
  const wrapper = mount(component, {
    props: options.props,
    attachTo: document.body,
    global: {
      plugins: [router, createShellI18n({ locale: options.locale ?? 'en', messages: { en, es } })],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: harness.client },
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
  return { ...harness, router, wrapper, live, result };
}
