// Test helper of the printing app's pages and components: `mountInShell` with its catalogues, the printers and its
// people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `ionModalStub` (imported
// from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import { ComposableHost } from './composable-host';
import en from '../locale/en.json';
import es from '../locale/es.json';

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

export async function mountPrinting(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/printing/printers',
    session: ADMIN,
    messages: { en, es },
    inDocFrom: 'component',
  });
}

/** Mounts `use` (a composable call) inside a component of the app's harness. */
export function mountComposable(use: () => void, options: Omit<MountOptions, 'props'> = {}) {
  return mountPrinting(ComposableHost, { ...options, props: { use } });
}

/** Flips an `ion-toggle` as Ionic does (`ionChange` with `{ checked }`). */
export { ionChecked as ionToggle } from '../../../../base/frontend/__tests__/mount-in-shell';

export * from '../../../../base/frontend/__tests__/mount-in-shell';
