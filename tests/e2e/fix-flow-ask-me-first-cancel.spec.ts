// Cancelling a reservation with «Ask the assistant» and «Ask me first», end to end with its real dependencies: the Hub
// of this stack, its SaaS's gateway and, behind it, the e2e's provider
// (assistant-provider.ts; the SaaS seeded with it, README «El asistente»). A real reservation is booked; in the editor
// the step is given «Cancel a reservation», which only «Ask me first» offers, and the card says who may say yes to it;
// saved, granted and run, the worker asks the assistant (`workerAsks`), which wants to cancel it: nothing is cancelled
// until the owner says yes in «Waiting for your answer», and then the reservation is cancelled for real.
// flow: FLOW-F28 FLOW-F12 FLOW-F37 FLOW-F38
import { expect, test } from '@playwright/test';

import { capture, psql, shown } from './helpers';
import { approve, ownerOnAutomations, saveGrantAndSwitchOn } from './flow-helpers';
import { providerSpec, runAndAsk, runFinishes } from './provider-helpers';
import { bookingOn, cleanUpTagged, madridDay, reservationStatus } from './reservation-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { pick } from './task-helpers';

const KEY = 'FIX-HUB-FLOW-ASK-ME-FIRST-CANNOT-GRANT-A-CANCELLATION';
const TAG = 'E2E FlowCancel';
/** Where the run books; its slot's maximum is how the cleanup knows it (slots have no name). */
const STAGE = { day: madridDay(3), sentinel: 79, reason: `${TAG} open` };

const booked = bookingOn(STAGE);

providerSpec(() => cleanUpTagged(TAG, STAGE.sentinel));

for (const viewport of VIEWPORTS) {
  test(`FLOW-F28 a reservation is cancelled only after the owner's yes, with «Ask me first», at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page, name, stamp } = await ownerOnAutomations(browser, viewport, TAG, '/flow/automations/new');
    try {
      const reservation = await booked(context, `${TAG} Ana ${stamp}`);
      const editor = shown(page);
      await editor.locator('[data-testid=flow-editor-name] input').fill(name);
      await editor.locator('[data-testid=flow-editor-add-assistant]').click();
      // The provider's marker: ask for the cancellation of that reservation, then say how it went.
      const asked = { id: reservation, reason: 'The guest wrote to cancel' };
      await editor.locator('[data-testid=flow-assistant-prompt-s1-text-0]').fill(`E2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`);
      await pick(page, 'flow-assistant-addtool-s1', 'Cancel a reservation', 'Cancel a reservation');
      await expect(editor.locator('[data-testid="flow-assistant-tool-s1-reservation.reservation.cancel"]')).toHaveText('Cancel a reservation');
      await expect(editor.locator('[data-testid=flow-assistant-askfirst-s1]')).toHaveText(
        'Only after a yes from someone who may do it themselves: «Cancel a reservation».',
      );
      await editor.locator('[data-testid=flow-assistant-askfirst-s1]').scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);
      // FLOW-F12: saved, what it needs is granted, the cancellation included, only because its step asks first.
      const flowId = await saveGrantAndSwitchOn(page);
      expect(psql(`select grants::text from flow_flow where id = '${flowId}'`)).toBe('["reservation.reservation.cancel"]');

      // FLOW-F38: the assistant wants to cancel it; nothing is cancelled before a yes.
      await runAndAsk(page, flowId);
      expect(await reservationStatus(context, reservation)).toBe('pending');

      // FLOW-F29: the owner says yes in «Waiting for your answer»: the reservation is cancelled for real.
      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card).toBeVisible();
      await expect(card).toContainText('The assistant wants to change something in «Reservations»');
      // It says the action, not only that something changes.
      await expect(card.locator('[data-testid^=flow-question-action-]')).toHaveText('Cancel a reservation');
      await approve(page, card);
      expect(await reservationStatus(context, reservation)).toBe('cancelled');
      // The step goes back to the assistant with what happened, and the run finishes.
      await runFinishes(flowId);
    } finally {
      await context.close();
    }
  });
}
