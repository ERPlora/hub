// flow: BASE-F05, BASE-F73, TASK-F09, TASK-F13 and CUSTOMER-F18 (hub#1046). «New folder» of Files and a project's sheet
// of Tasks: a half-written new task asks before Back drops it, and after «Discard changes» the sheet opens blank again —
// it stays mounted, so it empties itself on closing. «New folder» asks on its own ways out too (hub#1156), and so do the
// sheets of a task and of a project and the till's quick add of a customer, which are `ion-modal`s of their own
// (hub#1233). The other remaining windows are covered by their component tests.
import { test } from '@playwright/test';

import { cleanUp as cleanUpCustomers, e2eName } from './customer-helpers';
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

const TASK = named('Ways out');

const TASK_SHEET: UnsavedFormCase = {
  app: 'task',
  flow: 'TASK-F09',
  route: '/task/tasks',
  add: (page) => rowOf(page, 'task-tasks', TASK).first(),
  form: 'task-sheet',
  field: 'task-sheet-new-subtask',
};

/** The till's search, on its preview page: a name nobody has, then «+ New customer «…»» — which puts it in «Name» and
 *  leaves «Phone» blank. */
const QUICK_ADD: UnsavedFormCase = {
  app: 'customer',
  flow: 'CUSTOMER-F18',
  route: '/customer/preview/customer-search',
  add: 'customer-search-trigger',
  form: 'customer-search-modal',
  field: 'customer-search-quick-phone',
  value: '600 000 000',
  prepare: async (form) => {
    await form.locator('[data-testid=customer-picker-search] input').fill(e2eName('Ways out'));
    await form.locator('[data-testid=customer-search-quick-add]').click();
  },
};

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const owner = await signedIn(browser, '/task/projects');
  await post(owner.context, '/task/projects', { code: `e2e-back-${Date.now().toString(36)}`, name: PROJECT });
  await post(owner.context, '/task/tasks', { title: TASK });
  await owner.context.close();
});
test.afterAll(() => {
  cleanUp();
  cleanUpCustomers();
});

test('BASE-F73 files: Android Back asks before discarding a dirty form and closes a clean one', async ({ page }) => {
  await expectBackAsksOnDirtyForm(page, NEW_FOLDER, 'HUB-1046');
});

test('BASE-F73 files: Cancel, ×, Escape and a tap outside ask before discarding a dirty form and close a clean one (hub#1156)', async ({ page }) => {
  await expectWaysOutAskOnDirtyForm(page, NEW_FOLDER, 'HUB-1156');
});

test('TASK-F13 task: Android Back asks before discarding a half-written task and the sheet reopens blank', async ({ page }) => {
  await expectBackAsksOnDirtyForm(page, PROJECT_SHEET, 'HUB-1046');
});

test('TASK-F13 task: «Close», Escape and a tap outside of the project sheet ask before discarding and close it untouched (hub#1233)', async ({ page }) => {
  await expectWaysOutAskOnDirtyForm(page, PROJECT_SHEET, 'HUB-1233');
});

test('TASK-F09 task: «Close», Escape and a tap outside of the task sheet ask before discarding a half-written subtask (hub#1233)', async ({ page }) => {
  await expectWaysOutAskOnDirtyForm(page, TASK_SHEET, 'HUB-1233');
});

test('CUSTOMER-F18 customer: the «×», Escape and a tap outside of the quick add of the till ask before discarding (hub#1233)', async ({ page }) => {
  await expectWaysOutAskOnDirtyForm(page, QUICK_ADD, 'HUB-1233');
});
