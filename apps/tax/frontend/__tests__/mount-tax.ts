// Test helper of the tax app's pages and components: `mountInShell` with its catalogues, the tax categories and its
// people.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { withMenu } from '../../../../base/frontend/__tests__/app-menu';
import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Owner, admin or manager: `tax.*` (apps.py `role_permissions`). */
export const MANAGER: SessionMe = withMenu('tax', {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['tax.view', 'tax.manage'],
  menu: [],
  apps: [],
  language: 'en',
});

/** An employee only views and calculates. */
export const EMPLOYEE: SessionMe = withMenu('tax', { ...MANAGER, permissions: ['tax.view'] });

export async function mountTax(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/tax/categories',
    session: MANAGER,
    messages: { en, es },
    inDocFrom: 'component',
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
