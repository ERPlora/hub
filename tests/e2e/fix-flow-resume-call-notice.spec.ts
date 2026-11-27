// flow: FLOW-F24 FLOW-F27
// Resuming a run whose call to another system failed says what the run is doing, never «finished well»: the call is
// made again by the worker, so «Resume» answers «it is calling another system», and when that call fails again the
// run says «It was resumed and stopped by an error again: …» with why. The owner of hub `a` runs a manual automation
// that calls an address that does not exist (`.invalid`, never resolved, so nothing leaves the machine), in English
// and then in Spanish, at 390, 834 and 1440 px; each size leaves its captures. Its automations are deleted however
// the test ends.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { confirmDialog, deleteFlowsNamed, manualFlow, ownerOnAutomations, workerCalls } from './flow-helpers';
import { A, api, capture, saveSessionForTheSweep, shown } from './helpers';
import { noHorizontalScroll, VIEWPORTS } from './schedule-helpers';
import { toastSaying } from './toast-helpers';

const KEY = 'FIX-HUB-FLOW-RESUME-CALL-NOTICE';
const TAG = 'E2E FlowResumeCall';
const ORIGIN = 'https://qa-resume.invalid';
const CALLING = 'Resumed: it is calling another system. See how it goes here.';
const AGAIN = 'It was resumed and stopped by an error again: It could not reach «qa-resume.invalid», so it stopped.';
const CALLING_ES = 'Reanudada: está llamando a otro sistema. Mira aquí cómo sigue.';
const AGAIN_ES = 'Se reanudó y volvió a pararse por un error: No ha podido llegar a «qa-resume.invalid», así que se ha parado.';

/** Resumes the run stopped by an error on `page` and checks the notice says it is calling, not that it finished. */
async function resume(page: Page, stopped: string, retryTitle: string, calling: string): Promise<Locator> {
  const card = shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: stopped }).first();
  await card.locator('[data-testid^=flow-run-retry-]').click();
  await confirmDialog(page, retryTitle);
  await expect(toastSaying(page, calling)).toBeVisible();
  return card;
}

test.beforeAll(() => deleteFlowsNamed(TAG));
test.afterAll(() => deleteFlowsNamed(TAG));

for (const viewport of VIEWPORTS) {
  test(`FLOW-F24 resuming a call says it is calling and then that it stopped again, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page, name } = await ownerOnAutomations(browser, viewport, TAG);
    try {
      const step = { id: 's1', kind: 'http', method: 'POST', url: `${ORIGIN}/notice`, headers: {}, body: '', timeout: 5 };
      const flowId = await manualFlow(context, name, [step], [`http:${ORIGIN}`]);
      expect((await api(context, A, 'POST', '/flow/flows/run', { id: flowId })).status).toBe(200);
      workerCalls(flowId);

      await page.goto(`${A}/flow/automations/${flowId}?tab=history`);
      const card = await resume(page, 'Stopped by an error', 'Resume it from the step that failed?', CALLING);
      await expect(toastSaying(page, 'Resumed: it finished well.')).toHaveCount(0);
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `${KEY}-calling-${viewport.label}`);
      workerCalls(flowId);
      await expect(card.locator('[data-testid^=flow-run-retry-problem-]')).toHaveText(AGAIN);
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `${KEY}-stopped-again-${viewport.label}`);

      await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
      await page.goto(`${A}/flow/automations/${flowId}?tab=history`);
      const inSpanish = await resume(page, 'Se paró por un error', '¿Reanudarla desde el paso que falló?', CALLING_ES);
      workerCalls(flowId);
      await expect(inSpanish.locator('[data-testid^=flow-run-retry-problem-]')).toHaveText(AGAIN_ES);
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `${KEY}-stopped-again-es-${viewport.label}`);
      await saveSessionForTheSweep(context);
    } finally {
      await context.close();
    }
  });
}
