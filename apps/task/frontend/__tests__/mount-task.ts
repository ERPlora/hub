// Test helper of the task app's pages and components: `mountInShell` with its catalogues, the task list and its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `IonModalStub`
// (imported from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
import type { SessionMe } from '@erplora/ui/shell';
import { expect } from 'vitest';
import type { Component } from 'vue';

import { click, ionValue, mountInShell, type MountOptions, settle } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Owner, admin or manager: `task.*` (apps.py `role_permissions`), listed one by one; they read Staff. */
export const OWNER: SessionMe = {
  user: { id: '1', label: 'Marta' },
  permissions: [
    'task.view',
    'task.view_all',
    'task.add',
    'task.change',
    'task.change_all',
    'task.delete',
    'task.manage_project',
    'staff.view',
  ],
  menu: [],
  apps: [],
  language: 'en',
};

/** An employee sees, creates and changes their own tasks; no deleting, no projects. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  user: { id: '2', label: 'Bea' },
  permissions: ['task.view', 'task.add', 'task.change', 'staff.view'],
};

export async function mountTask(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/task/tasks', session: OWNER, messages: { en, es } });
}

/** A sheet of this app (`TaskSheet`, `ProjectSheet`), mounted with `open` as the test's prop. */
interface MountedSheet {
  wrapper: { setProps(props: { open: boolean }): Promise<void>; props(name: 'open'): unknown };
  inDoc(testid: string): HTMLElement | null;
}

/** Something half-written in a sheet's `field`: «Close» asks «Discard changes?», and «Discard changes» closes it
 *  (hub#1233, BASE-F05). */
export async function expectSheetDiscardsOnClose(sheet: MountedSheet, testid: string, field: string, typed: string): Promise<void> {
  const { answerUnsavedQuestion } = await import('../../../../base/frontend/__tests__/unsaved-form');
  await ionValue(sheet.inDoc(field), typed, 'ionInput');
  await click(sheet.inDoc(`${testid}-close`));
  await answerUnsavedQuestion('discard');
  await settle();
  expect(sheet.wrapper.props('open')).toBe(false);
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
