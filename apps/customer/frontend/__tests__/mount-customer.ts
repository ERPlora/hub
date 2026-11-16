// Test helper of the customer app's pages and components: `mountInShell` with the customer catalogues over base's,
// its list page and its people.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import type { ApiCall } from '../../../../packages/ui/src/sdk/__tests__/live-harness';
import { mountInShell, overBase } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

export type { ApiCall } from '../../../../packages/ui/src/sdk/__tests__/live-harness';
export { business, IN_YEN as JAPANESE, POLISH } from '../../../../base/frontend/__tests__/business';

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
  const mounted = await mountInShell(component, options, { path: '/customer/customers', session: OWNER, messages: overBase(en, es) });
  return { ...mounted, result: mounted.resultOn };
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
