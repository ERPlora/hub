// Test helper of the customer app's pages and components, copied from the demo's: the SDK's live
// harness (fake clock, fake network serving the stream and the API) on the hub's op → route map, the
// shell's i18n with the customer catalogues merged in, a session and a memory router.
import { createShellI18n, provideSession, type SessionMe } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY, type LiveClient, type OpName, stableJson } from '@erplora/ui/sdk';
import { fillHappyDomGaps } from '@erplora/ui/testing';
import { mount } from '@vue/test-utils';
import { type Component, createApp, ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import { addIcons } from '../../../../packages/ui/node_modules/ionicons';
import { ION_ICONS } from '../../../../packages/ui/src/shell/icons';

import {
  type ApiCall,
  createTestClient,
  flush,
  resultFrame,
  type StreamCall,
} from '../../../../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from '../../../../frontend/generated/operation-routes';
import en from '../locale/en.json';
import es from '../locale/es.json';

// happy-dom made to behave as a browser where Ionic's runtime reaches it (the hub has no setup file).
fillHappyDomGaps();
// What `createShell` does at boot: `ion:` icons paint by name from this registry.
addIcons(ION_ICONS);

export { BYE, errorFrame, flush, HELLO, resultFrame } from '../../../../packages/ui/src/sdk/__tests__/live-harness';
export type { ApiCall } from '../../../../packages/ui/src/sdk/__tests__/live-harness';

const ALL = ['view', 'manage', 'configure', 'merge', 'export', 'delete', 'erase', 'record_activity'].map((p) => `customer.${p}`);

/** `hub_owner` / `hub_admin`: every customer permission. */
export const OWNER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ALL,
  menu: [],
  apps: [],
  language: 'en',
};

/** `hub_manager`: everything but deleting and erasing. */
export const MANAGER: SessionMe = {
  ...OWNER,
  permissions: ALL.filter((p) => p !== 'customer.delete' && p !== 'customer.erase'),
};

/** `hub_employee`: views and manages cards (role_permissions of apps.py). */
export const EMPLOYEE: SessionMe = { ...OWNER, permissions: ['customer.view', 'customer.manage'] };

/** Only sees. */
export const VIEWER: SessionMe = { ...OWNER, permissions: ['customer.view'] };

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  attachTo?: HTMLElement;
}

/** The subscription id the stream holds for `op` (the first one, or the one with `params`). */
export function subId(client: LiveClient, op: OpName, params?: unknown): string {
  const subs = client.stream.subscriptions(op);
  const sub = params === undefined ? subs[0] : subs.find((s) => stableJson(s.params) === stableJson(params));
  if (!sub) throw new Error(`no live subscription for ${op}`);
  return sub.id;
}

/** A JSON answer of the fake API. */
export const json = (data: unknown, status = 200): Response => Response.json(data, { status });

/** The error envelope of the API (`{"error": {code, message, fields?}}`). */
export const refusal = (status: number, code: string, message: string, fields?: Record<string, string>): Response =>
  Response.json({ error: { code, message, ...(fields ? { fields } : {}) } }, { status });

/** What the page sent in a call: its path and its body (POST) or query (GET). */
export function sent(call: ApiCall): { path: string; body: unknown; query: Record<string, string> } {
  const url = new URL(call.url, 'http://a.localhost');
  const body = typeof call.init.body === 'string' ? JSON.parse(call.init.body) : undefined;
  return { path: url.pathname, body, query: Object.fromEntries(url.searchParams) };
}

export async function mountCustomer(component: Component, options: MountOptions = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:path(.*)*', component: { template: '<div />' } }],
  });
  await router.push(options.path ?? '/customer/customers');
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
  /** Pushes a result for the subscription of `op` (the first, or the one with `params`) and renders. */
  async function result(call: StreamCall, op: OpName, data: unknown, rev = 1, params?: unknown): Promise<void> {
    call.push(resultFrame(subId(harness.client, op, params), data, rev));
    await flush();
  }
  /** The live subscriptions' params of `op`. */
  const params = (op: OpName): unknown[] => harness.client.stream.subscriptions(op).map((s) => s.params);
  return { ...harness, router, wrapper, live, result, params };
}
