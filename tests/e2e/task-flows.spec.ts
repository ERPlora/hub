// Every flow of Tasks that has a screen, as the owner, in the three viewports (390, 834 and 1440 wide),
// crossing the real Staff app: the owner's account hangs a staff record (so «My tasks» and «Assign to
// me» are there) and two people of the team take tasks. Each flow is a step and leaves its capture,
// `APP-TASK-<flow>-<width>`, after checking that nothing scrolls sideways. Everything is named
// «E2E Task …» (projects `e2e-…`) and removed after it.
// flow: TASK-F01 TASK-F02 TASK-F03 TASK-F04 TASK-F05 TASK-F06 TASK-F07 TASK-F08 TASK-F09 TASK-F10 TASK-F11 TASK-F12 TASK-F13 TASK-F14
import { expect, test } from '@playwright/test';

import { A, api, OWNER, shown } from './helpers';
import { choose, cleanUp, FLOW_VIEWPORTS, pick, post, recordOf, rowAction, rowOf, signedIn, snap, TAG } from './task-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

type Row = { id: string; number: string; title: string; status: string; project_id: string | null; assigned_to_id: string | null };

for (const [width, viewport] of Object.entries(FLOW_VIEWPORTS)) {
  test(`TASK-F01 to TASK-F14, every screen of Tasks at ${width} wide`, async ({ browser }) => {
    const stamp = Date.now().toString(36);
    /** `E2E Task <text> <stamp>`: every name of this run holds its stamp, which the search finds. */
    const label = (text: string): string => `${TAG} ${text} ${stamp}`;
    const { context, page } = await signedIn(browser, '/task/tasks', undefined, viewport);
    try {
      const me = await recordOf(context, OWNER.email, 'Owner');
      const ana = await post<{ id: string }>(context, '/staff/members', { first_name: `${TAG} Ana`, last_name: `Lopez${stamp}` });
      await post(context, '/staff/members', { first_name: `${TAG} Bea`, last_name: `Ruiz${stamp}` });
      const find = async (title: string): Promise<Row> =>
        (await api<{ rows: Row[] }>(context, A, 'GET', `/task/tasks?search=${encodeURIComponent(title)}`)).data.rows[0];

      const code = `e2e-${stamp}`;
      const projectName = label('Opening');
      await test.step('TASK-F12 create a project', async () => {
        await page.goto(`${A}/task/projects`);
        await shown(page).locator('[data-testid=task-projects-empty], [data-testid=task-projects-row]').first().waitFor({ state: 'visible' });
        await shown(page).locator('[data-testid=task-projects-add]').click();
        const form = page.locator('ion-modal[data-testid=task-project-form]');
        await expect(form.locator('ion-title')).toHaveText('New project');
        await form.locator('[data-testid=task-project-form-code] input').fill(code);
        await form.locator('[data-testid=task-project-form-name] input').fill(projectName);
        await form.locator('[data-testid=task-project-form-color] input').fill('#AA3300');
        await snap(page, 'TASK-F12', width);
        await form.locator('[data-testid=task-project-form-submit]').click();
        await expect(form).toBeHidden();
        await expect(rowOf(page, 'task-projects', projectName)).toContainText('Yes');
      });

      const title = label('Clean the store room');
      await test.step('TASK-F01 create a task with every field', async () => {
        await page.goto(`${A}/task/tasks`);
        await shown(page).locator('[data-testid=task-tasks-empty], [data-testid=task-tasks-row]').first().waitFor({ state: 'visible' });
        await shown(page).locator('[data-testid=task-tasks-add]').click();
        const form = page.locator('ion-modal[data-testid=task-form]');
        await expect(form.locator('ion-title')).toHaveText('New task');
        await form.locator('[data-testid=task-form-title] input').fill(title);
        await form.locator('[data-testid=task-form-description] textarea').fill('Shelves and floor.');
        await choose(page, form.locator('[data-testid=task-form-priority]'), 'High');
        await form.locator('[data-testid=task-form-due_date] input').fill('2020-01-01');
        await pick(page, 'task-form-assignee', `Lopez${stamp}`, `Lopez${stamp}`);
        await pick(page, 'task-form-project', projectName, projectName);
        await form.locator('[data-testid=task-form-tags] input').fill('cleaning, weekly');
        await snap(page, 'TASK-F01', width);
        await form.locator('[data-testid=task-form-submit]').click();
        await expect(form).toBeHidden();
        // The assignee's column gives way first on a narrow table: the sheet (TASK-F04) shows it.
        const row = rowOf(page, 'task-tasks', title);
        await expect(row).toContainText('To Do');
        await expect(row).toContainText('High');
        await expect(row.locator('[data-testid=task-due]')).toHaveAttribute('aria-label', 'Overdue');
        const created = await find(title);
        expect(created.number).toMatch(/^TSK-\d{8}-\d{4}$/);
        expect([created.assigned_to_id, created.project_id !== null]).toEqual([ana.id, true]);
      });

      const other = label('Order blond dye');
      await test.step('TASK-F02 search and filter the list', async () => {
        await post(context, '/task/tasks', { title: other, priority: 'low' });
        await expect(rowOf(page, 'task-tasks', other)).toBeVisible();
        const search = shown(page).locator('[data-testid=task-tasks-search] input');
        await search.fill(stamp);
        await expect(rowOf(page, 'task-tasks', title)).toBeVisible();
        await expect(rowOf(page, 'task-tasks', other)).toBeVisible();
        // The filters wait behind the toolbar's funnel, in a panel applied by «Apply».
        const view = shown(page);
        const toggle = view.locator('[data-testid=task-tasks-filters-toggle]');
        const panel = view.locator('[data-testid=task-tasks-filters-panel]');
        await expect(view.locator('[data-testid=task-tasks-filter-priority]')).toHaveCount(0);
        await toggle.click();
        await expect(panel).toBeVisible();
        await choose(page, panel.locator('[data-testid=task-tasks-filter-priority]'), 'High');
        await panel.locator('[data-testid=task-tasks-filters-apply]').click();
        await expect(panel).toBeHidden();
        await expect(view.locator('[data-testid=task-tasks-filters-count]')).toHaveText('1');
        await expect(rowOf(page, 'task-tasks', title)).toBeVisible();
        await expect(rowOf(page, 'task-tasks', other)).toHaveCount(0);
        await snap(page, 'TASK-F02', width);
        await toggle.click();
        await expect(panel).toBeVisible();
        await panel.locator('[data-testid=task-tasks-filters-clear]').click();
        if (await panel.isVisible()) await panel.locator('[data-testid=task-tasks-filters-close]').click();
        await expect(panel).toBeHidden();
        await expect(rowOf(page, 'task-tasks', other)).toBeVisible();
      });

      const task = await find(title);
      await test.step('TASK-F05 start a task from its row', async () => {
        await rowAction(page, 'task-tasks', task.id, 'start');
        await expect(page.locator('ion-toast')).toContainText('Task started');
        await expect(rowOf(page, 'task-tasks', title)).toContainText('In Progress');
        await snap(page, 'TASK-F05', width);
      });

      const sheet = page.locator('ion-modal[data-testid=task-sheet]');
      await test.step('TASK-F04 open a task', async () => {
        await rowOf(page, 'task-tasks', title).click();
        await expect(sheet.locator('[data-testid=task-sheet-title]')).toHaveText(`${task.number} — ${title}`);
        await expect(sheet.locator('[data-testid=task-sheet-description]')).toHaveText('Shelves and floor.');
        await expect(sheet.locator('[data-testid=task-sheet-assignee]')).toContainText(`${TAG} Ana Lopez${stamp}`);
        await expect(sheet.locator('[data-testid=task-sheet-project]')).toContainText(projectName);
        await expect(sheet.locator('[data-testid=task-sheet-subtasks-empty]')).toHaveText('No subtasks.');
        await expect(sheet.locator('[data-testid=task-sheet-comments-empty]')).toHaveText('No comments.');
        await snap(page, 'TASK-F04', width);
      });

      await test.step('TASK-F10 comment a task', async () => {
        const box = sheet.locator('[data-testid=task-sheet-new-comment] textarea');
        await box.fill('E2E first');
        await sheet.locator('[data-testid=task-sheet-add-comment]').click();
        await expect(box).toHaveValue('');
        await box.fill('E2E second');
        await sheet.locator('[data-testid=task-sheet-add-comment]').click();
        await expect(sheet.locator('[data-testid=task-sheet-comments-heading]')).toHaveText('Comments (2)');
        await expect(sheet.locator('[data-testid^=task-sheet-comment-]').first()).toContainText('E2E second');
        await expect(box).toHaveValue('');
        await sheet.locator('[data-testid=task-sheet-comments-heading]').scrollIntoViewIfNeeded();
        await snap(page, 'TASK-F10', width);
      });

      const subtitle = label('Buy bleach');
      await test.step('TASK-F09 add a subtask and open it', async () => {
        await sheet.locator('[data-testid=task-sheet-new-subtask] input').fill(subtitle);
        await sheet.locator('[data-testid=task-sheet-add-subtask]').click();
        await expect(sheet.locator('[data-testid=task-sheet-subtasks-heading]')).toHaveText('Subtasks (1)');
        await expect(sheet.locator('[data-testid=task-sheet-new-subtask] input')).toHaveValue('');
        await sheet.locator('[data-testid^=task-sheet-subtask-open-]').first().click();
        await expect(sheet.locator('[data-testid=task-sheet-title]')).toContainText(subtitle);
        await expect(sheet.locator('[data-testid=task-sheet-project]')).toContainText(projectName);
        await expect(sheet.locator('[data-testid=task-sheet-trail]')).toContainText(`${task.number} ›`);
        await snap(page, 'TASK-F09', width);
        await sheet.locator('[data-testid=task-sheet-back]').click();
        await expect(sheet.locator('[data-testid=task-sheet-title]')).toContainText(title);
      });

      await test.step('TASK-F07 assign, assign to me and unassign', async () => {
        const assignee = sheet.locator('[data-testid=task-sheet-assignee]');
        await pick(page, 'task-sheet-assign-to', `Ruiz${stamp}`, `Ruiz${stamp}`);
        await sheet.locator('[data-testid=task-sheet-assign]').click();
        await expect(assignee).toContainText(`${TAG} Bea Ruiz${stamp}`);
        await sheet.locator('[data-testid=task-sheet-assign-me]').click();
        await expect(sheet.locator('[data-testid=task-sheet-assign-me]')).toHaveCount(0);
        expect((await find(title)).assigned_to_id).toBe(me.id);
        await sheet.locator('[data-testid=task-sheet-unassign]').click();
        await expect(assignee).toContainText('Unassigned');
        await expect(sheet.locator('[data-testid=task-sheet-unassign]')).toHaveCount(0);
        await snap(page, 'TASK-F07', width);
        await sheet.locator('[data-testid=task-sheet-assign-me]').click();
        await expect(sheet.locator('[data-testid=task-sheet-unassign]')).toBeVisible();
      });

      const renamed = `${title} and the yard`;
      await test.step('TASK-F08 edit a task', async () => {
        await sheet.locator('[data-testid=task-sheet-edit]').click();
        // The page's «New task» form is there too: this is the one editing the task.
        const editing = `Editing task — ${task.number}`;
        const form = page.locator('ion-modal[data-testid=task-form]').filter({ has: page.locator('ion-title', { hasText: editing }) });
        await expect(form.locator('ion-title')).toHaveText(editing);
        await expect(form.locator('[data-testid=task-form-title] input')).toHaveValue(title);
        await form.locator('[data-testid=task-form-title] input').fill(renamed);
        await choose(page, form.locator('[data-testid=task-form-priority]'), 'Urgent');
        await form.locator('[data-testid=task-form-due_date] input').fill('');
        await snap(page, 'TASK-F08', width);
        await form.locator('[data-testid=task-form-submit]').click();
        await expect(form).toBeHidden();
        await expect(sheet.locator('[data-testid=task-sheet-title]')).toHaveText(`${task.number} — ${renamed}`);
        await expect(sheet.locator('[data-testid=task-sheet-due-value]')).toHaveText('—');
        await expect(sheet).toContainText('Urgent');
      });

      await test.step('TASK-F05 change the status from the sheet', async () => {
        await choose(page, sheet.locator('[data-testid=task-sheet-status]'), 'Blocked');
        await expect(sheet.locator('[data-testid=task-sheet-status]')).toHaveJSProperty('value', 'blocked');
        expect((await find(renamed)).status).toBe('blocked');
      });

      await test.step('TASK-F06 complete a task', async () => {
        await sheet.locator('[data-testid=task-sheet-complete]').click();
        await expect(sheet.locator('[data-testid=task-sheet-complete]')).toHaveAttribute('aria-disabled', 'true');
        await expect(sheet.locator('[data-testid=task-sheet-completed]')).not.toContainText('—');
        await expect(sheet.locator('[data-testid=task-sheet-status]')).toHaveJSProperty('value', 'done');
        await snap(page, 'TASK-F06', width);
        await sheet.locator('[data-testid=task-sheet-close]').click();
        await expect(sheet).toBeHidden();
        await expect(rowOf(page, 'task-tasks', renamed)).toContainText('Done');
      });

      const dated = label('Restock shampoo');
      await test.step('TASK-F03 my open tasks, dated first', async () => {
        await post(context, '/task/tasks', { title: label('Undated'), assigned_to_id: me.id });
        await post(context, '/task/tasks', { title: dated, assigned_to_id: me.id, due_date: '2020-01-02' });
        await shown(page).locator('[data-testid=task-view-mine]').click();
        await expect(rowOf(page, 'task-mine', dated)).toBeVisible();
        await expect(rowOf(page, 'task-mine', renamed)).toHaveCount(0);
        await expect(rowOf(page, 'task-mine', subtitle)).toHaveCount(0);
        // The oldest due date of my open tasks: the first card.
        await expect(shown(page).locator('[data-testid=task-mine-row]').first()).toContainText(dated);
        await snap(page, 'TASK-F03', width);
        await shown(page).locator('[data-testid=task-view-all]').click();
      });

      await test.step('TASK-F11 delete a task with its subtasks and comments', async () => {
        await rowOf(page, 'task-tasks', renamed).click();
        await expect(sheet.locator('[data-testid=task-sheet-title]')).toContainText(renamed);
        await sheet.locator('[data-testid=task-sheet-delete]').click();
        const confirm = page.locator('[data-testid=task-sheet-delete-confirm-submit]');
        await expect(confirm).toBeVisible();
        await snap(page, 'TASK-F11', width);
        await confirm.click();
        await expect(sheet).toBeHidden();
        await expect(rowOf(page, 'task-tasks', renamed)).toHaveCount(0);
        await expect(rowOf(page, 'task-tasks', subtitle)).toHaveCount(0);
      });

      const projectSheet = page.locator('ion-modal[data-testid=task-project-sheet]');
      const renamedProject = `${projectName} summer`;
      await test.step('TASK-F13 open and change a project', async () => {
        await post(context, '/task/tasks', { title: label('In the project'), project: code });
        await page.goto(`${A}/task/projects`);
        await rowOf(page, 'task-projects', projectName).click();
        await expect(projectSheet.locator('[data-testid=task-project-sheet-code]')).toContainText(code);
        await expect(projectSheet.locator('[data-testid=task-project-sheet-tasks-heading]')).toHaveText('Tasks in this project (1)');
        await projectSheet.locator('[data-testid=task-project-sheet-name] input').fill(renamedProject);
        await projectSheet.locator('[data-testid=task-project-sheet-save]').click();
        await expect(projectSheet.locator('[data-testid=task-project-sheet-title]')).toContainText(renamedProject);
        await projectSheet.locator('[data-testid=task-project-sheet-toggle]').click();
        await expect(projectSheet.locator('[data-testid=task-project-sheet-state]')).toHaveText('Inactive');
        await projectSheet.locator('[data-testid=task-project-sheet-new-task] input').fill(label('Paint the door'));
        await projectSheet.locator('[data-testid=task-project-sheet-add-task]').click();
        await expect(projectSheet.locator('[data-testid=task-project-sheet-tasks-heading]')).toHaveText('Tasks in this project (2)');
        await snap(page, 'TASK-F13', width);
      });

      await test.step('TASK-F14 delete a project; its tasks stay', async () => {
        await projectSheet.locator('[data-testid=task-project-sheet-delete]').click();
        const confirm = page.locator('[data-testid=task-project-sheet-delete-confirm-submit]');
        await expect(confirm).toBeVisible();
        await snap(page, 'TASK-F14', width);
        await confirm.click();
        await expect(projectSheet).toBeHidden();
        await expect(rowOf(page, 'task-projects', renamedProject)).toHaveCount(0);
        const left = await api<{ total: number; rows: Row[] }>(context, A, 'GET', `/task/tasks?search=${encodeURIComponent(stamp)}`);
        expect(left.data.rows.some((row) => row.title.includes('Paint the door') && row.project_id === null)).toBe(true);
        expect(left.data.rows.every((row) => row.project_id === null)).toBe(true);
      });
    } finally {
      await context.close();
    }
  });
}
