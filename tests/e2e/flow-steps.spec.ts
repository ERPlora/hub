// flow: FLOW-F24 FLOW-F25 FLOW-F26 FLOW-F27 FLOW-F28 FLOW-F29
// The steps of part 2 of Automations (apps/flow/WORKBOOK.md), end to end in each of the three sizes, against
// the real Tasks app, with one screenshot per flow and size (`APP-FLOW-2-<flow>-<width>`). A run stopped by a
// permission is resumed from the step that failed once allowed (F24); a step that fails carries on and the
// next one runs only if it failed (F25); a secret is saved in «Call another system» and never comes back
// (F26); the call is built, tried, allowed and run: «Run now» answers with the run «calling», the worker's
// pass makes the call, and it is not made because its server is inside a private network (F27, the SSRF
// guard: no call leaves the machine); a question is built (F28) and the
// employee answers it in «Waiting for your answer», which is all they see of the app (F29). What a run
// creates is tagged `E2E FlowG` and goes.
import { expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, psql, shot, shown } from './helpers';
import { choose, confirmDialog, idFromUrl, manualFlow, signedIn, workerCalls } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { pick } from './task-helpers';

const TAG = 'E2E FlowG';
const SECRET = 'E2E_FLOWG';

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from flow_secret where name like '${SECRET}%'`,
      `delete from task_task where title like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/** The run of the history that says `status`, opened. */
async function openRun(page: Page, status: string) {
  const run = shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: status }).first();
  await expect(run).toBeVisible();
  await run.locator('[data-testid^=flow-run-toggle-]').click();
  return run;
}

async function taskTitles(context: Parameters<typeof api>[0], search: string): Promise<string[]> {
  const tasks = await api<{ rows: { title: string }[] }>(context, A, 'GET', `/task/tasks?search=${encodeURIComponent(search)}`);
  return tasks.data.rows.map((row) => row.title);
}

for (const viewport of VIEWPORTS) {
  test(`the steps of part 2 of Automations at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(240_000);
    const stamp = `${viewport.label}-${Date.now().toString(36)}`;
    const secret = `${SECRET}_${viewport.label}_${Date.now().toString(36).toUpperCase()}`;
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    const snap = async (flow: string): Promise<void> => {
      await settled(page);
      await page.screenshot({ path: shot(`APP-FLOW-2-${flow}-${viewport.label}`) });
    };
    try {
      // FLOW-F24: a run stopped because a step was not allowed is resumed from it once allowed.
      const resumedTitle = `${TAG} resumed ${stamp}`;
      const resumable = await manualFlow(context, `${TAG} resume ${stamp}`, [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: resumedTitle } }], []);
      expect((await api(context, A, 'POST', '/flow/flows/run', { id: resumable })).status).toBe(200);
      await page.goto(`/flow/automations/${resumable}?tab=permissions`);
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await expect(shown(page).locator('[data-testid="flow-perm-granted-task.task.create"]')).toBeVisible();
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      const failed = await openRun(page, 'Stopped by an error');
      await failed.locator('[data-testid^=flow-run-retry-]').first().click();
      await confirmDialog(page, 'Resume it from the step that failed?', () => snap('FLOW-F24'));
      await expect(page.locator('ion-toast').filter({ hasText: 'Resumed: it finished well.' }).last()).toBeVisible();
      expect(await taskTitles(context, resumedTitle)).toEqual([resumedTitle]);

      // FLOW-F25: a step that fails carries on, and the next one runs only if it failed.
      const afterTitle = `${TAG} after a failure ${stamp}`;
      const carrying = await manualFlow(
        context,
        `${TAG} carry on ${stamp}`,
        [
          { id: 's1', kind: 'command', operation: 'customer.customer.create', params: { name: `${TAG} nobody` }, on_error: 'continue' },
          { id: 's2', kind: 'command', operation: 'task.task.create', params: { title: afterTitle }, run_if: { 'steps.s1.failed': { eq: true } } },
        ],
        ['task.task.create'],
      );
      await page.goto(`/flow/automations/${carrying}`);
      await expect(shown(page).locator('[data-testid=flow-step-summary-s1]')).toHaveText('If it fails, it carries on');
      await expect(shown(page).locator('[data-testid=flow-step-summary-s2]')).toContainText('Only if: 1. Create a customer › Failed');
      await shown(page).locator('[data-testid=flow-step-open-s2]').click();
      // A step with options opens with them shown.
      await expect(shown(page).locator('[data-testid=flow-step-runif-hint-s2]')).toContainText('this step is skipped and the automation goes on');
      // «Failed» is a yes or no: its value is chosen, never typed.
      const failedValue = shown(page).locator('[data-testid=flow-step-runif-cond-s2-value-0]');
      await expect(failedValue).toHaveJSProperty('tagName', 'ION-SELECT');
      await expect(failedValue).toHaveJSProperty('value', 'true');
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F25');
      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?');
      await expect(page.locator('ion-toast').filter({ hasText: 'See it in History' }).last()).toBeVisible();
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      const carried = await openRun(page, 'Finished well');
      await expect(carried.locator('[data-testid^=flow-run-steps-]')).toContainText('It carried on with the next steps.');
      expect(await taskTitles(context, afterTitle)).toEqual([afterTitle]);

      // FLOW-F26: a secret saved in the call's box comes back by its name only.
      await page.goto('/flow/automations/new');
      const editor = shown(page);
      await editor.locator('[data-testid=flow-editor-name] input').fill(`${TAG} call ${stamp}`);
      await editor.locator('[data-testid=flow-editor-add-http]').click();
      await editor.locator('[data-testid=flow-http-secrets-s1-name] input').fill(secret.toLowerCase());
      await editor.locator('[data-testid=flow-http-secrets-s1-value] input').fill('sk_test_e2e_never_shown');
      await editor.locator('[data-testid=flow-http-secrets-s1-save]').click();
      await expect(page.locator('ion-toast').filter({ hasText: `${secret} saved. Its value can no longer be shown.` }).last()).toBeVisible();
      await expect(editor.locator(`[data-testid=flow-http-secrets-s1-name-${secret}]`)).toHaveText(secret);
      await expect(editor.locator('[data-testid=flow-http-secrets-s1-value] input')).toHaveValue('');
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F26');

      // FLOW-F27: the call, with the secret in a header, tried (secret masked), allowed and run; its server
      // is the machine itself, so it is never called and the history says why and what to do.
      await editor.locator('[data-testid=flow-http-url-s1-text-0]').fill('https://localhost/e2e-hook');
      await expect(editor.locator('[data-testid=flow-http-host-s1]')).toHaveText('This step will ask your permission to call localhost.');
      await editor.locator('[data-testid=flow-http-addheader-s1]').click();
      await editor.locator('[data-testid=flow-http-header-name-s1-0] input').fill('Authorization');
      await editor.locator('[data-testid=flow-http-header-value-s1-0-text-0]').fill('Bearer ');
      await editor.locator('[data-testid=flow-http-header-value-s1-0-insert]').click();
      const picker = page.locator('ion-modal[data-testid=flow-picker]');
      await expect(picker.locator('[data-testid=flow-picker-group-secret]')).toHaveText('Secrets');
      await picker.locator(`[data-testid="flow-picker-secret.${secret}"]`).click();
      await expect(picker).toBeHidden();
      await editor.locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      const callId = idFromUrl(page);
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await shown(page).locator('[data-testid=flow-editor-test]').click();
      const tried = shown(page).locator('[data-testid=flow-test-step-s1]');
      await expect(tried).toHaveAttribute('data-outcome', 'not_allowed');
      await expect(tried).toContainText('Bearer ••••');
      await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await expect(shown(page).locator('[data-testid="flow-perm-granted-http:https://localhost"]')).toContainText('Call localhost');
      await shown(page).locator('[data-testid=flow-editor-enabled]').click();
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await shown(page).locator('[data-testid=flow-editor-test]').click();
      await expect(shown(page).locator('[data-testid=flow-test-step-s1]')).toContainText('Would call localhost with this');
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F27');
      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?');
      await expect(page.locator('ion-toast').filter({ hasText: 'calling another system' }).last()).toBeVisible();
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      // «Run now» answered without calling: the run waits for the worker, which makes the call on its next pass.
      const calling = await openRun(page, 'Calling another system');
      await expect(calling).toContainText('Calling localhost…');
      workerCalls(callId);
      const blocked = await openRun(page, 'Stopped by an error');
      await expect(blocked).toContainText('«localhost» is inside a private network, so it was not called.');
      await expect(blocked).toContainText('Use the public address of the other system');
      expect(await page.content(), 'the secret never reaches the page').not.toContain('sk_test_e2e_never_shown');
      const detail = await api<{ steps: unknown[] }>(context, A, 'GET', `/flow/flows/detail?id=${callId}`);
      expect(JSON.stringify(detail.data)).not.toContain('sk_test_e2e_never_shown');

      // FLOW-F28: a question to the employees, filled in with words, waiting a day; run, it waits.
      const questionTitle = `${TAG} may we refund ${stamp}?`;
      const answeredTitle = `${TAG} refunded ${stamp}`;
      await page.goto('/flow/automations/new');
      const asker = shown(page);
      await asker.locator('[data-testid=flow-editor-name] input').fill(`${TAG} ask ${stamp}`);
      await asker.locator('[data-testid=flow-editor-add-ask]').click();
      await asker.locator('[data-testid=flow-ask-title-s1-text-0]').fill(questionTitle);
      await choose(page, 'flow-ask-role-s1', 'An employee');
      await expect(asker.locator('[data-testid=flow-ask-who-s1]')).toHaveText(
        'The employees answer it in Automations, under «Waiting for your answer»; whoever runs the business can too.',
      );
      await asker.locator('[data-testid=flow-ask-hours-s1] input').fill('24');
      await choose(page, 'flow-ask-ontimeout-s1', 'Carry on with the next steps');
      await expect(asker.locator('[data-testid=flow-ask-continuehint-s1]')).toContainText('«Approved»');
      await asker.locator('[data-testid=flow-editor-add-command]').click();
      await pick(page, 'flow-step-action-s2', 'task', 'Create a task');
      await asker.locator('[data-testid=flow-step-param-s2-title-text-0]').fill(answeredTitle);
      await asker.locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      await expect(shown(page).locator('[data-testid=flow-step-open-s1]')).toContainText(`Ask: ${questionTitle}`);
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F28');
      await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await shown(page).locator('[data-testid=flow-editor-enabled]').click();
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?');
      await expect(page.locator('ion-toast').filter({ hasText: 'waiting for an answer in «Waiting for your answer»' }).last()).toBeVisible();
      expect(await taskTitles(context, answeredTitle)).toEqual([]);

      // FLOW-F29: the employee sees only «Waiting for your answer», approves with a note; the run goes on.
      const employee = await signedIn(browser, '/flow/automations', viewport, EMPLOYEE);
      try {
        const inbox = shown(employee.page).locator('[data-testid=flow-inbox]');
        const card = inbox.locator('article').filter({ hasText: questionTitle });
        await expect(card).toBeVisible();
        await expect(card).toContainText('Asked of the employees. Whoever runs the business can answer too.');
        await expect(card).toContainText('the automation carries on anyway');
        await expect(shown(employee.page).locator('[data-testid=flow-gallery]')).toHaveCount(0);
        await expect(shown(employee.page).locator('[data-testid=flow-new]')).toHaveCount(0);
        await card.locator('[data-testid^=flow-question-note-] input').fill('go ahead');
        await noHorizontalScroll(employee.page, viewport.label);
        await settled(employee.page);
        await employee.page.screenshot({ path: shot(`APP-FLOW-2-FLOW-F29-${viewport.label}`) });
        await card.locator('[data-testid^=flow-question-yes-]').click();
        await expect(employee.page.locator('ion-toast').filter({ hasText: 'Approved: the automation carries on.' }).last()).toBeVisible();
        await expect(card).toHaveCount(0);
      } finally {
        await employee.context.close();
      }
      await expect.poll(() => taskTitles(context, answeredTitle)).toEqual([answeredTitle]);
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      const answered = await openRun(page, 'Finished well');
      await expect(answered.locator('[data-testid^=flow-run-steps-]')).toContainText('answered yes: «go ahead»');
    } finally {
      await context.close();
    }
  });
}
