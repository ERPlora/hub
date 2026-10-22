// Test helper of the website editor's page and components: the SDK's live harness (fake network serving the stream
// and the API) on the hub's generated op → route map, the shell's i18n with the website catalogues merged in, a
// session and a memory router, as the shell mounts them.
import { createShellI18n, provideSession, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY, type LiveClient, type OpName } from '@erplora/ui/sdk';
import { mount } from '@vue/test-utils';
import { type Component, createApp, ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import {
  type ApiHandler,
  createTestClient,
  flush,
  resultFrame,
  type StreamCall,
} from '../../../../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from '../../../../frontend/generated/operation-routes';
import en from '../locale/en.json';
import es from '../locale/es.json';

export { errorFrame, flush, HELLO, resultFrame } from '../../../../packages/ui/src/sdk/__tests__/live-harness';

export const OWNER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['website.view', 'website.manage'],
  menu: [],
  apps: [
    { label: 'website', state: 'on' },
    { label: 'service', state: 'on' },
  ],
  language: 'en',
};

export const MANAGER: SessionMe = { ...OWNER, permissions: ['website.view'] };

export interface MountOptions {
  props?: Record<string, unknown>;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component>;
  attachTo?: HTMLElement;
  /** What the API answers, from the first call (a component that reads on mount). */
  api?: ApiHandler;
}

/** The subscription id the stream holds for `op` (the first one). */
export function subId(client: LiveClient, op: OpName): string {
  const sub = client.stream.subscriptions(op)[0];
  if (!sub) throw new Error(`no live subscription for ${op}`);
  return sub.id;
}

export async function mountWebsite(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  if (options.api) harness.net.onApi(options.api);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push('/website');
  await router.isReady();
  const app = createApp({});
  provideSession(ref(options.session ?? OWNER), ref('live'), { app });
  const wrapper = mount(component, {
    props: options.props,
    attachTo: options.attachTo,
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

/** Two flushes: an Ionic event's handler, then what it rendered. */
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

/** Toggles an `ion-toggle` as Ionic does (`ionChange` with `checked`). */
export async function ionChecked(el: Element | null, checked: boolean): Promise<void> {
  if (!el) throw new Error('no element to toggle');
  (el as HTMLElement & { checked?: boolean }).checked = checked;
  el.dispatchEvent(new CustomEvent('ionChange', { detail: { checked, value: 'on' }, bubbles: true }));
  await settle();
}
