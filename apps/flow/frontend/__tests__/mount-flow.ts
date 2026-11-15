// Test helper of the flow app's pages and components: `mountInShell` with its catalogues over base's and the shared
// assistant's (as the shell merges them: the assistant's card speaks with their words), the automations and its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import { assistantMessages } from '@erplora/ui/components';
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import baseEn from '../../../../base/frontend/locale/en.json';
import baseEs from '../../../../base/frontend/locale/es.json';
import en from '../locale/en.json';
import es from '../locale/es.json';
import type { CatalogOut, Step } from '../operations';

/** A catalog with one action, Tasks' «Create a task», which leaves its «Number». */
export const TASK_CATALOG = { events: [], actions: [{ name: 'task.task.create', kind: 'command', app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: ['number'] }] } as unknown as CatalogOut;
/** One step that creates a task: what a later value names as «1. Create a task › …». */
export const TASK_STEPS: Step[] = [{ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }];

/** Owner or admin: `flow.*` (apps.py `role_permissions`). */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Marta' },
  permissions: ['flow.view', 'flow.manage'],
  menu: [],
  apps: [],
  language: 'en',
};

/** Someone who may look but not change (no role has it alone; a test of the read-only screen). */
export const VIEWER: SessionMe = { ...OWNER, permissions: ['flow.view'] };

export async function mountFlow(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/flow/automations',
    session: OWNER,
    messages: { en: { ...assistantMessages.en, ...baseEn, ...en }, es: { ...assistantMessages.es, ...baseEs, ...es } },
  });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
