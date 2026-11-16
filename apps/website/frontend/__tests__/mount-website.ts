// Test helper of the website editor's page and components: `mountInShell` with the website catalogues over base's,
// the editor's page and its people.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import type { ApiHandler } from '../../../../packages/ui/src/sdk/__tests__/live-harness';
import { mountInShell, overBase } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

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

export async function mountWebsite(component: Component, options: MountOptions = {}) {
  const mounted = await mountInShell(component, options, { path: '/website', session: OWNER, messages: overBase(en, es) });
  return { ...mounted, result: mounted.resultOn };
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
