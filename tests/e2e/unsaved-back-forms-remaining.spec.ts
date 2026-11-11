// flow: BASE-F05, BASE-F73 and TASK-F13 (hub#1046). «New folder» of Files and a project's sheet of Tasks: a half-written
// new task asks before Back drops it, and after «Discard changes» the sheet opens blank again — it stays mounted, so it
// empties itself on closing. «New folder» asks on its own ways out too (hub#1156); the project's sheet does not yet
// (hub#1233). The other remaining windows are covered by their component tests.
import { test } from '@playwright/test';

import { cleanUp, named, post, rowOf, signedIn } from './task-helpers';
import { expectBackAsksOnDirtyForm, expectWaysOutAskOnDirtyForm, type UnsavedFormCase } from './unsaved-back-helpers';

const NEW_FOLDER: UnsavedFormCase = {
  app: 'files',
  flow: 'BASE-F73',
  route: '/files',
  add: 'files-new-folder',
  form: 'files-new-folder-dialog',
  field: 'files-new-folder-name',
};

const PROJECT = named('Back');

const PROJECT_SHEET: UnsavedFormCase = {
  app: 'task',
  flow: 'TASK-F13',
  route: '/task/projects',
  add: (page) => rowOf(page, 'task-projects', PROJECT).first(),
  form: 'task-project-sheet',
  field: 'task-project-sheet-new-task',
};

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const owner = await signedIn(browser, '/task/projects');
  await post(owner.context, '/task/projects', { code: `e2e-back-${Date.now().toString(36)}`, name: PROJECT });
  await owner.context.close();
});
test.afterAll(cleanUp);

test('BASE-F73 files: Android Back asks before discarding a dirty form and closes a clean one', async ({ page }) => {
  await expectBackAsksOnDirtyForm(page, NEW_FOLDER, 'HUB-1046');
});

test('BASE-F73 files: Cancel, ×, Escape and a tap outside ask before discarding a dirty form and close a clean one (hub#1156)', async ({ page }) => {
  await expectWaysOutAskOnDirtyForm(page, NEW_FOLDER, 'HUB-1156');
});

test('TASK-F13 task: Android Back asks before discarding a half-written task and the sheet reopens blank', async ({ page }) => {
  await expectBackAsksOnDirtyForm(page, PROJECT_SHEET, 'HUB-1046');
});
