// Test helper of the demo's pages and components: the SDK's live harness (fake clock, fake network
// serving the stream and the API) on the hub's generated op → route map, the shell's i18n with the
// demo catalogues merged in, a session and a memory router. Pages are mounted as the shell would.
/* eslint-disable vue/one-component-per-file -- a test double of ion-alert and a blank route */
import { createShellI18n, provideSession, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY, type LiveClient, type OpName } from '@erplora/ui/sdk';
import { mount } from '@vue/test-utils';
import { type Component, createApp, defineComponent, h, ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import {
  createTestClient,
  flush,
  resultFrame,
  type StreamCall,
} from '../../../../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from '../../../../frontend/generated/operation-routes';
import en from '../locale/en.json';
import es from '../locale/es.json';

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../../packages/ui/src/sdk/__tests__/live-harness';

/** `ion-alert` presents itself only in a real browser: the stub exposes what it would show. */
export const AlertStub = defineComponent({
  name: 'IonAlert',
  props: { isOpen: Boolean, header: { type: String, default: undefined }, buttons: { type: Array, default: () => [] } },
  emits: ['didDismiss'],
  setup(props) {
    return () => (props.isOpen ? h('div', { 'data-testid': 'alert' }, props.header) : null);
  },
});

export const MANAGER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['demo.view', 'demo.manage'],
  menu: [],
  apps: [],
  language: 'en',
};

export const EMPLOYEE: SessionMe = { ...MANAGER, permissions: ['demo.view'] };

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, unknown>;
}

/** The subscription id the stream holds for `op` (the first one). */
export function subId(client: LiveClient, op: OpName): string {
  const sub = client.stream.subscriptions(op)[0];
  if (!sub) throw new Error(`no live subscription for ${op}`);
  return sub.id;
}

export async function mountDemo(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/demo/items');
  await router.isReady();
  // The session is provided app-wide, as createShell does.
  const app = createApp({});
  provideSession(ref(options.session ?? MANAGER), ref('live'), { app });
  const wrapper = mount(component, {
    props: options.props,
    global: {
      plugins: [router, createShellI18n({ locale: options.locale ?? 'en', messages: { en, es } })],
      provide: { ...app._context.provides, [LIVE_CLIENT_KEY as symbol]: harness.client },
      stubs: { IonAlert: AlertStub, ...options.stubs },
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
