// Tasks in Chrome, as the owner (WORKBOOK TASK-F01 to F14), crossing the real Staff app: a project is
// made in Projects; a task is made in Tasks for a person of Staff, in that project and already overdue
// (red, «Overdue»); renaming the person in Staff renames the task's assignee live; Start from the row
// says so; the sheet comments, adds a subtask, opens it and comes Back, and completes the task; the
// project's sheet lists both tasks, is deactivated and deleted, and its tasks stay. Both screens are
// captured in the three viewports. Everything is named «E2E Task …» and removed after it.
// flow: TASK-F01 TASK-F02 TASK-F04 TASK-F05 TASK-F06 TASK-F09 TASK-F10 TASK-F12 TASK-F13 TASK-F14
import { expect, test } from '@playwright/test';

import { api, A, capture, shown, untilStill } from './helpers';
import { cleanUp, named, pick, post, rowAction, rowOf, signedIn, TAG, VIEWPORTS } from './task-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('a task for a person of Staff, from its project to done, live', async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const owner = await signedIn(browser, '/task/projects');
  const { page, context } = owner;
  try {
    const member = await post<{ id: string }>(context, '/staff/members', { first_name: `${TAG} Ana`, last_name: `Lopez${stamp}` });

    // TASK-F12: a project, from «+».
    const code = `e2e-${stamp}`;
    const projectName = named('Opening');
    await shown(page).locator('[data-testid=task-projects-empty], [data-testid=task-projects-row]').first().waitFor({ state: 'visible' });
    await shown(page).locator('[data-testid=task-projects-add]').click();
    await expect(page.locator('ion-modal[data-testid=task-project-form] ion-title')).toHaveText('New project');
    await page.locator('[data-testid=task-project-form-code] input').fill(code);
    await page.locator('[data-testid=task-project-form-name] input').fill(projectName);
    await page.locator('[data-testid=task-project-form-color] input').fill('#AA3300');
    await page.locator('[data-testid=task-project-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=task-project-form]')).toBeHidden();
    await expect(rowOf(page, 'task-projects', projectName)).toContainText('Yes');

    // TASK-F01: a task for Ana, in the project, due long ago.
    const title = named('Clean the store room');
    await page.goto(`${A}/task/tasks`);
    await shown(page).locator('[data-testid=task-tasks-empty], [data-testid=task-tasks-row]').first().waitFor({ state: 'visible' });
    await shown(page).locator('[data-testid=task-tasks-add]').click();
    await expect(page.locator('ion-modal[data-testid=task-form] ion-title')).toHaveText('New task');
    await page.locator('[data-testid=task-form-title] input').fill(title);
    await page.locator('[data-testid=task-form-due_date] input').fill('2020-01-01');
    await pick(page, 'task-form-assignee', `Lopez${stamp}`, `Lopez${stamp}`);
    await pick(page, 'task-form-project', projectName, projectName);
    await page.locator('[data-testid=task-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=task-form]')).toBeHidden();
    const row = rowOf(page, 'task-tasks', title);
    await expect(row).toContainText(`${TAG} Ana Lopez${stamp}`);
    await expect(row).toContainText('To Do');
    await expect(row.locator('[data-testid=task-due]')).toHaveAttribute('aria-label', 'Overdue');
    const taskId = (await api<{ rows: { id: string }[] }>(context, A, 'GET', `/task/tasks?search=${encodeURIComponent(title)}`)).data.rows[0].id;

    // Staff renames the person: the task list says the new name without reloading.
    await post(context, '/staff/members/update', { id: member.id, last_name: `Garcia${stamp}` }, 200);
    await expect(row).toContainText(`${TAG} Ana Garcia${stamp}`);

    // TASK-F05: Start from the row, with its notice.
    await rowAction(page, 'task-tasks', taskId, 'start');
    await expect(page.locator('ion-toast')).toContainText('Task started');
    await expect(row).toContainText('In Progress');
    // The notice is still sliding in: the capture waits until nothing moves.
    await untilStill(page);
    await capture(page, 'task-tasks-desktop');

    // TASK-F04, F10, F09: the sheet.
    await row.click();
    const sheet = page.locator('ion-modal[data-testid=task-sheet]');
    await expect(sheet.locator('[data-testid=task-sheet-title]')).toContainText(title);
    await expect(sheet.locator('[data-testid=task-sheet-project]')).toContainText(projectName);
    await sheet.locator('[data-testid=task-sheet-new-comment] textarea').fill('E2E almost done');
    await sheet.locator('[data-testid=task-sheet-add-comment]').click();
    await expect(sheet.locator('[data-testid^=task-sheet-comment-]').first()).toContainText('E2E almost done');
    await expect(sheet.locator('[data-testid=task-sheet-new-comment] textarea')).toHaveValue('');
    const subtitle = named('Buy bleach');
    await sheet.locator('[data-testid=task-sheet-new-subtask] input').fill(subtitle);
    await sheet.locator('[data-testid=task-sheet-add-subtask]').click();
    await expect(sheet.locator('[data-testid=task-sheet-subtasks-heading]')).toHaveText('Subtasks (1)');
    await expect(sheet.locator('[data-testid^=task-sheet-subtask-]', { hasText: subtitle }).first()).toBeVisible();
    await untilStill(page);
    await capture(page, 'task-sheet-desktop');
    await sheet.locator('[data-testid^=task-sheet-subtask-open-]').first().click();
    await expect(sheet.locator('[data-testid=task-sheet-title]')).toContainText(subtitle);
    await sheet.locator('[data-testid=task-sheet-back]').click();
    await expect(sheet.locator('[data-testid=task-sheet-title]')).toContainText(title);

    // TASK-F06: Complete; a done task is no longer late.
    await sheet.locator('[data-testid=task-sheet-complete]').click();
    await expect(sheet.locator('[data-testid=task-sheet-complete]')).toHaveAttribute('aria-disabled', 'true');
    await expect(sheet.locator('[data-testid=task-sheet-completed]')).not.toContainText('—');
    await expect(sheet.locator('[data-testid=task-sheet-due-value]')).not.toHaveAttribute('aria-label', 'Overdue');
    await sheet.locator('[data-testid=task-sheet-close]').click();
    await expect(row).toContainText('Done');

    // TASK-F13, F14: the project's sheet lists both tasks, is deactivated, then deleted; the tasks stay.
    await page.goto(`${A}/task/projects`);
    await rowOf(page, 'task-projects', projectName).click();
    const projectSheet = page.locator('ion-modal[data-testid=task-project-sheet]');
    await expect(projectSheet.locator('[data-testid=task-project-sheet-tasks-heading]')).toHaveText('Tasks in this project (2)');
    await projectSheet.locator('[data-testid=task-project-sheet-toggle]').click();
    await expect(projectSheet.locator('[data-testid=task-project-sheet-state]')).toHaveText('Inactive');
    await untilStill(page);
    await capture(page, 'task-project-sheet-desktop');
    await projectSheet.locator('[data-testid=task-project-sheet-delete]').click();
    await page.locator('[data-testid=task-project-sheet-delete-confirm-submit]').click();
    await expect(projectSheet).toBeHidden();
    await expect(rowOf(page, 'task-projects', projectName)).toHaveCount(0);
    const left = await api<{ total: number; rows: { project_id: string | null }[] }>(context, A, 'GET', `/task/tasks?search=${encodeURIComponent(TAG)}`);
    expect(left.data.total).toBe(2);
    expect(left.data.rows.every((r) => r.project_id === null)).toBe(true);
  } finally {
    await context.close();
  }
});

test('Tasks and Projects in the three viewports', async ({ browser }) => {
  const seeding = await signedIn(browser, '/task/tasks');
  const title = named('Viewport');
  await post(seeding.context, '/task/tasks', { title, priority: 'urgent', due_date: '2020-01-01' });
  await post(seeding.context, '/task/projects', { code: `e2e-vp-${Date.now().toString(36)}`, name: named('Viewport project') });
  await seeding.context.close();
  for (const [name, viewport] of Object.entries(VIEWPORTS)) {
    const { context, page } = await signedIn(browser, '/task/tasks', undefined, viewport);
    try {
      const view = shown(page);
      await expect(view.locator('[data-testid=task-tasks-row]', { hasText: title }).first()).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
      await untilStill(page);
      await capture(page, `task-tasks-${name}`);
      await page.goto(`${A}/task/projects`);
      await shown(page).locator('[data-testid=task-projects-row]').first().waitFor({ state: 'visible' });
      await untilStill(page);
      await capture(page, `task-projects-${name}`);
    } finally {
      await context.close();
    }
  }
});
