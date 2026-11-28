// flow: FLOW-F16 FLOW-F24
// An automation that stopped because it lacked a permission names the action as Permissions and «Try it» do
// («Create a task», never «task.task.create») and says «Open Permissions and allow what it needs.» once: in the
// editor's notice after «Run now», on its card in History and with its steps open after it was resumed and stopped
// again. Read in Spanish, the card says «Crear una tarea» and «Abre Permisos y concédele lo que necesita.» once.
// Nothing on those screens is an internal code (`expectInWords`, hub#2629).
// The owner of hub `a` runs a manual automation that creates a task but was granted nothing, at 390, 834 and 1440 px;
// each size leaves its captures. Its automations are deleted however the test ends.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { confirmDialog, deleteFlowsNamed, expectInWords, manualFlow, ownerOnAutomations } from './flow-helpers';
import { A, capture, saveSessionForTheSweep, shown } from './helpers';
import { noHorizontalScroll, VIEWPORTS } from './schedule-helpers';

const KEY = 'FIX-HUB-FLOW-NOT-ALLOWED-NAMES-THE-ACTION';
const TAG = 'E2E FlowNotAllowed';
const WHY = 'It tried to do something you have not allowed it to do («Create a task»), so it stopped.';
const ADVICE = 'Open Permissions and allow what it needs.';
const WHY_ES = 'Ha intentado hacer algo que no le has permitido («Crear una tarea»), así que ha parado.';
const ADVICE_ES = 'Abre Permisos y concédele lo que necesita.';

/** How many times `words` are in what `box` shows. */
async function timesIn(box: Locator, words: string): Promise<number> {
  return (await box.innerText()).split(words).length - 1;
}

async function runNow(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=flow-editor-run]').click();
  await confirmDialog(page, 'Run it now?');
}

test.beforeAll(() => deleteFlowsNamed(TAG));
test.afterAll(() => deleteFlowsNamed(TAG));

for (const viewport of VIEWPORTS) {
  test(`FLOW-F16 a run stopped by a missing permission names the action and says what to do once, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const { context, page, name } = await ownerOnAutomations(browser, viewport, TAG);
    try {
      const step = { id: 's1', kind: 'command', operation: 'task.task.create', params: { title: `${TAG} follow-up` } };
      const flowId = await manualFlow(context, name, [step], []);
      await page.goto(`${A}/flow/automations/${flowId}`);

      await runNow(page);
      const notice = shown(page).locator('[data-testid=flow-editor-error]');
      await expect(notice).toHaveText(`It ran and stopped by an error: ${WHY} ${ADVICE}`);
      await expectInWords(page, context);
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `${KEY}-editor-${viewport.label}`);

      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      const card = shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: 'Stopped by an error' }).first();
      const trouble = card.locator('[data-testid^=flow-run-trouble-]');
      await expect(trouble).toContainText(WHY);
      expect(await timesIn(card, ADVICE)).toBe(1);
      await expect(card).not.toContainText('task.task.create');

      await card.locator('[data-testid^=flow-run-retry-]').click();
      await confirmDialog(page, 'Resume it from the step that failed?');
      await expect(card.locator('[data-testid^=flow-run-retry-problem-]')).toHaveText(`It was resumed and stopped by an error again: ${WHY}`);
      await card.locator('[data-testid^=flow-run-toggle-]').click();
      const steps = card.locator('[data-testid^=flow-run-steps-]');
      await expect(steps).toContainText(`Create a task: ${WHY}`);
      await expect(steps).toContainText('Resumed here, from the step that had failed');
      expect(await timesIn(card, ADVICE)).toBe(1);
      await expect(card).not.toContainText('task.task.create');
      await expectInWords(page, context);
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `${KEY}-history-${viewport.label}`);

      await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
      await page.goto(`${A}/flow/automations/${flowId}?tab=history`);
      const inSpanish = shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: 'Se paró por un error' }).first();
      await expect(inSpanish.locator('[data-testid^=flow-run-trouble-]')).toContainText(WHY_ES);
      expect(await timesIn(inSpanish, ADVICE_ES)).toBe(1);
      await expectInWords(page, context);
      await capture(page, `${KEY}-history-es-${viewport.label}`);
      await saveSessionForTheSweep(context);
    } finally {
      await context.close();
    }
  });
}
