// Test helper of the verifactu app's pages and components: `mountInShell` with the verifactu catalogues over
// base's, its records page and its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `ionModalStub` (imported
// from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions, overBase } from '../../../../base/frontend/__tests__/mount-in-shell';
import { ComposableHost } from './composable-host';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Every permission of the verifactu app (owner, admin: apps.py `role_permissions`) and what its screens
 *  use of Invoicing (the test invoice). */
export const VERIFACTU_PERMISSIONS = [
  'verifactu.view_record',
  'verifactu.add_record',
  'verifactu.transmit_record',
  'verifactu.correct_record',
  'verifactu.configure',
];

/** The owner (and the admin): every permission of the app. */
export const OWNER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: [...VERIFACTU_PERMISSIONS, 'invoice.view_invoice', 'invoice.add_invoice'],
  menu: [],
  apps: [],
  language: 'en',
};

/** The manager: watches and pushes the queue; no correcting, cancelling nor configuring. */
export const MANAGER: SessionMe = {
  ...OWNER,
  permissions: ['verifactu.view_record', 'verifactu.add_record', 'verifactu.transmit_record', 'invoice.view_invoice'],
};

/** The employee: looks. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  permissions: ['verifactu.view_record', 'verifactu.add_record', 'invoice.view_invoice'],
};

export async function mountVerifactu(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/verifactu/records', session: OWNER, messages: overBase(en, es), inDocFrom: 'component' });
}

/** Mounts `use` (a composable call) inside a component of the verifactu app's harness. */
export function mountComposable(use: () => void, options: Omit<MountOptions, 'props'> = {}) {
  return mountVerifactu(ComposableHost, { ...options, props: { use } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
