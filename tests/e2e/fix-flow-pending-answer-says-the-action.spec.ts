// The action of the assistant's change in «Waiting for your answer», end to end with its real dependencies: the Hub of
// this stack, its SaaS's gateway and, behind it, the e2e's provider
// (assistant-provider.ts; the SaaS seeded with it, README «El asistente»). A real reservation is booked; an automation
// that asks first, granted «Cancel a reservation», runs, and the worker asks the assistant (`workerAsks`), which wants
// to cancel it. Its card, titled «The assistant wants to change something in «Reservations»», says right under its
// title «Cancel a reservation» to whoever reads it in English and «Anular una
// reserva», under «El asistente quiere cambiar algo en «Reservas»», to whoever reads it in Spanish. A no cancels nothing,
// and the History says what was refused by its action too («Cancelada: … contestó que no a «Anular una reserva».»), in
// the language of whoever reads it, never «… a «El asistente quiere cambiar algo en «Reservas»»».
// flow: FLOW-F29 FLOW-F38
import { expect, test } from '@playwright/test';

import { A, api, capture, psql, shown } from './helpers';
import { manualFlow, ownerOnAutomations } from './flow-helpers';
import { providerSpec, workerAsks } from './provider-helpers';
import { bookingOn, cleanUpTagged, madridDay, reservationStatus } from './reservation-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';

const KEY = 'FIX-HUB-FLOW-PENDING-ANSWER-CARD-DOES-NOT-SAY-THE-ACTION';
const TAG = 'E2E FlowAction';
const CANCEL = 'reservation.reservation.cancel';
/** Where the run books; its slot's maximum is how the cleanup knows it (slots have no name). */
const STAGE = { day: madridDay(3), sentinel: 75, reason: `${TAG} open` };

const booked = bookingOn(STAGE);

providerSpec(() => cleanUpTagged(TAG, STAGE.sentinel));

for (const viewport of VIEWPORTS) {
  test(`FLOW-F29 the assistant's change says its action in «Waiting for your answer», in the reader's language, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page, name, stamp } = await ownerOnAutomations(browser, viewport, TAG, '/flow/automations');
    try {
      const reservation = await booked(context, `${TAG} Ana ${stamp}`);
      // The provider's marker: ask for the cancellation of that reservation, as the model sends it.
      const asked = { id: reservation, reason: 'The guest wrote to cancel' };
      const step = { id: 's1', kind: 'assistant', prompt: `E2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`, tools: [CANCEL] };
      const flowId = await manualFlow(context, name, [step], [CANCEL]);
      expect((await api(context, A, 'POST', '/flow/flows/run', { id: flowId })).status).toBe(200);
      await workerAsks(flowId);
      await expect.poll(() => psql(`select count(*) from flow_question where flow_id = '${flowId}' and status = 'pending'`)).toBe('1');

      // In English: the action, right under the title, before anything else of the change.
      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card).toBeVisible();
      await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText('The assistant wants to change something in «Reservations»');
      const action = card.locator('[data-testid^=flow-question-action-]');
      await expect(action).toHaveText('Cancel a reservation');
      const order = await card.evaluate((article) => [...article.children].map((child) => child.getAttribute('data-testid') ?? ''));
      const at = (prefix: string) => order.findIndex((testid) => testid.startsWith(prefix));
      expect(at('flow-question-action-'), order.join(', ')).toBe(at('flow-question-title-') + 1);
      await expect(card).toContainText(`${TAG} Ana ${stamp}`);
      await expect(card).not.toContainText(reservation);
      await expect(card).not.toContainText(CANCEL);

      // The same question, read in Spanish (the Hub's language cookie, as the sign-in sets it): its title and its action
      // in the reader's language, not in the automation's.
      await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
      await page.reload();
      await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText('El asistente quiere cambiar algo en «Reservas»');
      await expect(action).toHaveText('Anular una reserva');
      await card.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);

      // «No»: nothing is cancelled and the card leaves.
      await card.locator('[data-testid^=flow-question-reject-]').click();
      await expect(page.locator('ion-toast').filter({ hasText: 'Contestada que no.' }).last()).toBeVisible();
      await expect(card).toHaveCount(0);
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('cancelled');
      expect(await reservationStatus(context, reservation)).toBe('pending');

      // The History names what was refused by its action, in the reader's language.
      const runId = psql(`select id from flow_flowrun where flow_id = '${flowId}'`);
      await page.goto(`/flow/automations/${flowId}`);
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      const why = shown(page).locator(`[data-testid=flow-run-trouble-${runId}] .flow-history__why`);
      await expect(why).toHaveText(/^Cancelada: .+ contestó que no a «Anular una reserva»\.$/);
      await shown(page).locator(`[data-testid=flow-run-trouble-${runId}]`).scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-history-${viewport.label}`);
      await context.addCookies([{ name: 'django_language', value: 'en', domain: new URL(A).hostname, path: '/' }]);
      await page.reload();
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      await expect(why).toHaveText(/^Cancelled: .+ answered no to «Cancel a reservation»\.$/);
    } finally {
      await context.close();
    }
  });
}
