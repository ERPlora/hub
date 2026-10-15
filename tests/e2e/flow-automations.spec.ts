// Automations in Chrome, as the owner (WORKBOOK FLOW-F02 to F16), with the real Tasks app: an automation
// from the gallery opens on its Permissions and is allowed what it needs; another is built from
// scratch — «Do something» → «Create a task» with its title —, saved, allowed, turned on and run by hand,
// and its history says it finished well while the task is in Tasks; the list turns one off, copies one
// and deletes the copy (asked first). The list and the editor are captured in the three viewports.
// What it creates is removed after it by its ids (the task by its unique title).
import { expect, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { rowAction, signedIn, VIEWPORTS } from './task-helpers';

const TAG = 'E2E Flow';

/** The automations and the task this run creates, removed by their ids (and the task by its unique
 *  title) whatever happens: nothing of anybody else's is touched. */
const created: string[] = [];
const titles: string[] = [];

function cleanUp(): void {
  const ids = created.filter((id) => /^[0-9a-f-]{36}$/.test(id)).map((id) => `'${id}'`);
  const statements: string[] = [];
  if (ids.length) {
    statements.push(`delete from flow_flowrun where flow_id in (${ids.join(', ')})`, `delete from flow_flow where id in (${ids.join(', ')})`);
  }
  for (const title of titles) statements.push(`delete from task_task where title = '${title.replaceAll("'", "''")}'`);
  if (statements.length) psql(statements.join('; '));
}

test.afterAll(cleanUp);

/** Picks the option of a `Combo` whose text holds `text`, searching it by `query`. */
async function pick(page: Page, testid: string, query: string, text: string): Promise<void> {
  const input = page.locator(`[data-testid=${testid}] input`);
  await input.click();
  await input.fill(query);
  await page.locator(`[data-testid^=${testid}-option-]`, { hasText: text }).first().click();
}

async function confirmDialog(page: Page, title: string): Promise<void> {
  const dialog = page.locator('ion-modal.ep-form-modal').filter({ hasText: title });
  await expect(dialog).toBeVisible();
  await dialog.locator('.ep-form-modal__submit').click();
}

test('an automation from the gallery and one from scratch, allowed, on, run by hand and read in its history', async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const name = `${TAG} Weekly ${stamp}`;
  const title = `${TAG} task ${stamp}`;
  titles.push(title);
  const { context, page } = await signedIn(browser, '/flow/automations');
  try {
    // FLOW-F04: a card of the gallery, created paused, opens on its Permissions.
    const gallery = shown(page).locator('[data-testid=flow-gallery]');
    await expect(gallery).toContainText('Pick one and it becomes yours, paused');
    await shown(page).locator('[data-testid=flow-card-open-welcome]').click();
    await expect(shown(page).locator('[data-testid=flow-card-panel-welcome]')).toContainText('Create a task');
    await shown(page).locator('[data-testid=flow-card-use-welcome]').click();
    await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+\?tab=permissions$/);
    created.push(new URL(page.url()).pathname.split('/').at(-1)!);
    await expect(shown(page).locator('[data-testid^="flow-perm-missing-task.task.create"]')).toContainText('Waiting for your permission');
    // FLOW-F12: allowed.
    await shown(page).locator('[data-testid=flow-perm-grantall]').click();
    await expect(shown(page).locator('[data-testid^="flow-perm-granted-task.task.create"]')).toContainText('Allowed');

    // FLOW-F09, F11: from scratch, by hand, «Do something» → «Create a task».
    await page.goto(`${A}/flow/automations/new`);
    const editor = shown(page);
    await expect(editor.locator('[data-testid=flow-editor-nosteps]')).toBeVisible();
    await editor.locator('[data-testid=flow-editor-name] input').fill(name);
    await editor.locator('[data-testid=flow-editor-add-command]').click();
    await pick(page, 'flow-step-action-s1', 'task', 'Create a task');
    await editor.locator('[data-testid=flow-step-param-s1-title-text-0]').fill(title);
    await editor.locator('[data-testid=flow-editor-save]').click();
    await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
    const flowId = new URL(page.url()).pathname.split('/').at(-1)!;
    created.push(flowId);
    await page.screenshot({ path: shot('flow-editor-desktop') });

    // FLOW-F13: «Try it» runs nothing.
    await shown(page).locator('[data-testid=flow-editor-test]').click();
    await expect(shown(page).locator('[data-testid=flow-test-banner]')).toContainText('None of this is real.');
    await expect(shown(page).locator('[data-testid=flow-test-step-s1]')).toHaveAttribute('data-outcome', 'not_allowed');

    // FLOW-F12, F14: allowed, on, saved.
    await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
    await shown(page).locator('[data-testid=flow-perm-grantall]').click();
    await expect(shown(page).locator('[data-testid^="flow-perm-granted-task.task.create"]')).toBeVisible();
    await shown(page).locator('[data-testid=flow-editor-enabled]').click();
    await shown(page).locator('[data-testid=flow-editor-save]').click();
    await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
    await expect(shown(page).locator('[data-testid=flow-editor-state]')).toContainText('Active');

    // FLOW-F15, F16: run by hand, asked first; the history says it finished well; the task is in Tasks.
    await shown(page).locator('[data-testid=flow-editor-run]').click();
    await confirmDialog(page, 'Run it now?');
    await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
    await expect(shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: 'Finished well' }).first()).toBeVisible();
    const tasks = await api<{ rows: { title: string }[] }>(context, A, 'GET', `/task/tasks?search=${encodeURIComponent(title)}`);
    expect(tasks.data.rows.map((row) => row.title)).toEqual([title]);

    // FLOW-F02, F03, F06, F07: the list.
    await page.goto(`${A}/flow/automations`);
    const row = shown(page).locator('[data-testid=flow-list-row]', { hasText: name });
    await expect(row).toContainText('Only when you press Run');
    await expect(row).toContainText('Finished well');
    await page.screenshot({ path: shot('flow-list-desktop') });
    await shown(page).locator(`[data-testid=flow-list-toggle-${flowId}]`).click();
    await expect(row).toContainText('Paused');
    await shown(page).locator('[data-testid=flow-list-search] input').fill(stamp);
    await expect(shown(page).locator('[data-testid=flow-list-row]')).toHaveCount(1);
    await rowAction(page, 'flow-list', flowId, 'duplicate');
    const copy = shown(page).locator('[data-testid=flow-list-row]', { hasText: `Copy of ${name}` });
    await expect(copy).toContainText('Paused');
    const copyId = await copy.getAttribute('data-id');
    if (copyId) created.push(copyId);
    await rowAction(page, 'flow-list', copyId!, 'delete');
    await confirmDialog(page, `Delete «Copy of ${name}»?`);
    await expect(copy).toHaveCount(0);

    // The three viewports.
    for (const [label, size] of Object.entries(VIEWPORTS)) {
      await page.setViewportSize(size);
      await page.goto(`${A}/flow/automations`);
      await expect(shown(page).locator('[data-testid=flow-gallery]')).toBeVisible();
      await page.screenshot({ path: shot(`flow-list-${label}`) });
      await page.goto(`${A}/flow/automations/${flowId}`);
      await expect(shown(page).locator('[data-testid=flow-trigger-open]')).toContainText('Only when you press Run');
      await page.screenshot({ path: shot(`flow-editor-${label}`) });
    }
  } finally {
    await context.close();
  }
});
