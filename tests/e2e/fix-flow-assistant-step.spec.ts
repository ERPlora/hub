// «Ask the assistant», a step of Automations, end to end with its real dependencies: the
// Hub of this stack, its SaaS's gateway (`/internal/assistant/chat`, the turn answered at once) and, behind it, the
// e2e's provider (assistant-provider.ts, an OpenAI-compatible server on 127.0.0.1 that this spec starts): no mock
// between the Hub and the provider. The SaaS must be seeded with that provider (README «El asistente»).
// The step is added in the editor, saved, granted, run; the worker asks the assistant (`workerAsks`), which looks
// up the tasks with the read the step names (a read asks nobody) and answers; the history says it.
// And the Hub's chat leaves a draft automation (FLOW-F17), which waits in Automations.
// flow: FLOW-F37 FLOW-F38 FLOW-F39 FLOW-F17
import { expect, test } from '@playwright/test';

import { box, card, decide, lastAnswer, panel } from './assistant-panel';
import { DONE } from './assistant-provider';
import { emptyMonth, saasSql } from './assistant-real';
import { capture, psql, shown } from './helpers';
import { confirmDialog, idFromUrl, openRun, signedIn } from './flow-helpers';
import { chats, providerSpec, workerAsks } from './provider-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { pick } from './task-helpers';
import { toastSaying } from './toast-helpers';
import { openAssistant } from './topbar';

const TAG = 'E2E FlowAI';

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from flow_draft where name like '${TAG}%'`,
    ].join('; '),
  );
  // The month's messages of the business `a`: a run never spends the plan's allowance.
  emptyMonth();
}

const provider = providerSpec(cleanUp);

for (const viewport of VIEWPORTS) {
  test(`FLOW-F37 «Ask the assistant» is added, saved and run, and the history tells what it did at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const name = `${TAG} ${viewport.label} ${Date.now().toString(36)}`;
    const { context, page } = await signedIn(browser, '/flow/automations/new', viewport);
    try {
      const editor = shown(page);
      await editor.locator('[data-testid=flow-editor-name] input').fill(name);
      await editor.locator('[data-testid=flow-editor-add-assistant]').click();
      await expect(editor.locator('[data-testid=flow-assistant-notools-s1]')).toHaveText('Nothing yet: it can only answer with words.');
      // The provider's marker: look up the tasks with the read the step names, then answer.
      await editor.locator('[data-testid=flow-assistant-prompt-s1-text-0]').fill('E2E-ASK task__task__list {}');
      await pick(page, 'flow-assistant-addtool-s1', 'Look for tasks', 'Look for tasks');
      await expect(editor.locator('[data-testid="flow-assistant-tool-s1-task.task.list"]')).toHaveText('Look for tasks');
      await expect(editor.locator('[data-testid=flow-assistant-addtool-s1] input')).toHaveValue('');
      await expect(editor.locator('[data-testid=flow-assistant-modehint-s1]')).toHaveText(
        'A change it wants waits for a yes in Automations, under «Waiting for your answer». What it only looks up never waits.',
      );
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `FIX-FLOW-ASSISTANT-STEP-editor-${viewport.label}`);
      await editor.locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      const flowId = idFromUrl(page);
      await expect(shown(page).locator('[data-testid=flow-step-open-s1]')).toContainText('Ask the assistant: E2E-ASK task__task__list {}');

      await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await shown(page).locator('[data-testid=flow-editor-enabled]').click();
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await shown(page).locator('[data-testid=flow-editor-test]').click();
      await expect(shown(page).locator('[data-testid=flow-test-step-s1]')).toContainText('Would ask the assistant: E2E-ASK task__task__list {}');

      const spent = (): number => Number(saasSql("select coalesce(sum(messages), 0) from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')"));
      const spentBefore = spent();
      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?');
      await expect(toastSaying(page, 'the assistant is on it')).toBeVisible();
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      // «Run now» answered without asking: the run waits for the worker, which asks the assistant.
      const waiting = await openRun(page, 'Waiting for the assistant');
      await expect(waiting).toContainText('Asked the assistant; it answers in a moment.');
      const before = chats(provider()).length;
      await workerAsks(flowId);
      // The same run, still open, now finished: what the assistant did, step by step.
      const done = shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: 'Finished well' }).first();
      await expect(done).toContainText('The assistant used «Look for tasks».');
      await expect(done).toContainText(`The assistant answered: «${DONE.en}»`);
      // Two turns of the model through the SaaS: the task, and the answer to its read; nobody was asked.
      const turns = chats(provider()).slice(before);
      expect(turns).toHaveLength(2);
      expect(JSON.stringify(turns[0].body)).toContain('task__task__list');
      expect(psql(`select count(*) from flow_question where flow_id = '${flowId}'`)).toBe('0');
      // FLOW-F39: one message of the month for the step, none for the answer to its read.
      expect(spent() - spentBefore).toBe(1);
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `FIX-FLOW-ASSISTANT-STEP-${viewport.label}`);
    } finally {
      await context.close();
    }
  });
}

for (const viewport of VIEWPORTS) {
  test(`FLOW-F17 the Hub’s assistant leaves a draft automation, which waits in Automations at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const name = `${TAG} draft ${viewport.label} ${Date.now().toString(36)}`;
    const { context, page } = await signedIn(browser, '/', viewport);
    try {
      const draft = {
        name,
        definition: { trigger: { kind: 'manual' }, steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Call back' } }] },
        notes: ['I did not know who to assign it to.'],
      };
      await openAssistant(page);
      await expect(box(page)).toBeVisible();
      await box(page).fill(`E2E-ASK flow__draft__propose ${JSON.stringify(draft)}`);
      await box(page).press('Enter');
      await expect(card(page)).toBeVisible();
      await decide(page, 'submit');
      await expect(lastAnswer(page)).toContainText(DONE.en);
      // The chat stays open from page to page; on a phone it covers the page, so it is closed to look at Automations.
      await panel(page).locator('[data-testid="assistant-close"]').click();
      await expect(panel(page)).not.toHaveAttribute('data-open', 'true');
      await page.goto('/flow/automations');
      await expect(shown(page).locator('[data-testid=flow-drafts]')).toContainText(name);
      expect(psql(`select count(*) from flow_flow where name = '${name}'`)).toBe('0');
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `FIX-FLOW-ASSISTANT-STEP-draft-${viewport.label}`);
    } finally {
      await context.close();
    }
  });
}
