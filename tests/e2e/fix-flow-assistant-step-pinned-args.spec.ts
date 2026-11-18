// Fixed data of «Ask the assistant», end to end with its real dependencies: the Hub of this stack, its SaaS's gateway
// and, behind it, the e2e's provider
// (assistant-provider.ts; the SaaS seeded with it, README «El asistente»). Lucía writes; Marta, another guest, has a
// real reservation. In the editor the step may «Cancel a reservation» and fixes its «On behalf of the customer» to
// Lucía's card; the assistant asks to cancel Marta's reservation without saying on whose behalf. The card in «Waiting
// for your answer» says it goes on Lucía's behalf, and after the owner's yes Reservations refuses it: Marta's
// reservation is still pending. «Try it» says each fixed datum with the value it
// would have, and that «Change a reservation», fixed to a card this trial does not bring, would not be used.
// flow: FLOW-F37 FLOW-F38 FLOW-F29 FLOW-F13
import { type BrowserContext, expect, test } from '@playwright/test';

import { capture, psql, shown } from './helpers';
import { approve, grantAllAndSwitchOn, idFromUrl, ownerOnAutomations } from './flow-helpers';
import { providerSpec, runAndAsk, runFinishes } from './provider-helpers';
import { bookingOn, cleanUpTagged, madridDay, reservationStatus } from './reservation-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { post } from './service-helpers';
import { pick } from './task-helpers';

const KEY = 'FIX-HUB-FLOW-ASSISTANT-STEP-ACTS-ON-ANOTHER-CUSTOMER-WITHOUT-ON-BEHALF-OF';
const TAG = 'E2E FlowPinned';
const CANCEL = 'reservation.reservation.cancel';
const UPDATE = 'reservation.reservation.update';
/** Where the run books; its slot's maximum is how the cleanup knows it (slots have no name). */
const STAGE = { day: madridDay(3), sentinel: 78, reason: `${TAG} open` };

const booked = bookingOn(STAGE);

providerSpec(() => cleanUpTagged(TAG, STAGE.sentinel));

/** A customer card, and a real reservation on it at 21:00 on the stage's day, the book open that day. */
async function guest(context: BrowserContext, name: string, book: boolean): Promise<{ card: string; reservation: string }> {
  const phone = `6${String(Date.now()).slice(-8)}`;
  const card = await post<{ id: string }>(context, '/customer/customers', { name, phone });
  if (!book) return { card: card.id, reservation: '' };
  return { card: card.id, reservation: await booked(context, name, { id: card.id, phone }) };
}

for (const viewport of VIEWPORTS) {
  test(`FLOW-F38 a fixed «On behalf of the customer» keeps the assistant off another guest's reservation, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page, name, stamp } = await ownerOnAutomations(browser, viewport, TAG, '/flow/automations/new');
    try {
      const lucia = `${TAG} Lucía ${stamp}`;
      const writer = await guest(context, lucia, false);
      const other = await guest(context, `${TAG} Marta ${stamp}`, true);
      const editor = shown(page);
      await editor.locator('[data-testid=flow-editor-name] input').fill(name);
      await editor.locator('[data-testid=flow-editor-add-assistant]').click();
      // The provider's marker: cancel Marta's reservation, never saying on whose behalf.
      await editor.locator('[data-testid=flow-assistant-prompt-s1-text-0]').fill(`E2E-ASK reservation__reservation__cancel ${JSON.stringify({ id: other.reservation })}`);
      await expect(editor.locator('[data-testid=flow-assistant-pinned-s1]')).toHaveCount(0);
      await pick(page, 'flow-assistant-addtool-s1', 'Cancel a reservation', 'Cancel a reservation');
      // FLOW-F37: nothing fixed yet; then «On behalf of the customer», fixed to Lucía's card.
      await expect(editor.locator('[data-testid=flow-assistant-nopins-s1]')).toHaveText('None: the assistant fills in every datum itself.');
      await pick(page, 'flow-assistant-addpin-s1', 'behalf', 'On behalf of the customer');
      const pin = `flow-assistant-pin-s1-${CANCEL}-on_behalf_of`;
      await expect(editor.locator(`[data-testid="${pin}"]`)).toContainText('Cancel a reservation › On behalf of the customer');
      await editor.locator(`[data-testid="${pin}-text-0"]`).fill(writer.card);
      await expect(editor.locator('[data-testid=flow-assistant-nopins-s1]')).toHaveCount(0);
      await expect(editor.locator('[data-testid=flow-assistant-pinnedhint-s1]')).toHaveText(
        'The assistant never sees them nor can change them: they are filled in when it is asked, and a tool whose fixed datum is empty is not used.',
      );
      await editor.locator('[data-testid=flow-assistant-pinnedhint-s1]').scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);

      // FLOW-F13: «Try it» says each fixed datum with the value it would have, as the card of the change names it (the
      // guest by her name, never her card's id), and which tool would not be used because one would be empty —
      // «Change a reservation» on behalf of a card the run is never given here.
      await pick(page, 'flow-assistant-addtool-s1', 'Change a reservation', 'Change a reservation');
      await pick(page, 'flow-assistant-addpin-s1', 'behalf', 'On behalf of the customer');
      await editor.locator(`[data-testid="flow-assistant-pin-s1-${UPDATE}-on_behalf_of-text-0"]`).fill('{{input.customer}}');
      await editor.locator('[data-testid=flow-editor-tab-test]').click();
      const tried = editor.locator('[data-testid=flow-test-step-s1]');
      await expect(tried).toContainText('Would ask the assistant');
      const fixed = tried.locator(`[data-testid="flow-test-pinned-s1-${CANCEL}-on_behalf_of"]`);
      await expect(fixed.locator('span')).toHaveText(['Cancel a reservation › On behalf of the customer', lucia]);
      await expect(tried).not.toContainText(writer.card);
      await expect(tried.locator(`[data-testid="flow-test-pinnedempty-s1-${UPDATE}"]`)).toHaveText(
        '«Change a reservation» would not be used: «On behalf of the customer», fixed by this step, would be empty in this run.',
      );
      await tried.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-try-${viewport.label}`);

      await editor.locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      const flowId = idFromUrl(page);
      const saved = JSON.parse(psql(`select steps::text from flow_flow where id = '${flowId}'`))[0].pinned;
      expect(saved[CANCEL]).toEqual({ on_behalf_of: writer.card });
      expect(Object.keys(saved[UPDATE])).toEqual(['on_behalf_of']);

      await grantAllAndSwitchOn(page);

      await runAndAsk(page, flowId);

      // FLOW-F29: the card says on whose behalf it would go, by her name, although the assistant never said it.
      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card).toBeVisible();
      await expect(card.locator('[data-testid^=flow-question-data-] li').filter({ hasText: 'On behalf of the customer' })).toHaveText(
        `On behalf of the customer: ${lucia}`,
      );
      await card.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-card-${viewport.label}`);
      // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });

      // The owner's yes: Reservations refuses another guest's reservation on Lucía's behalf; Marta's stays.
      await approve(page, card);
      expect(await reservationStatus(context, other.reservation)).toBe('pending');
      await runFinishes(flowId);
      expect(psql(`select log::text from flow_flowrun where flow_id = '${flowId}'`)).toContain('"ok": false');
      expect(await reservationStatus(context, other.reservation)).toBe('pending');
    } finally {
      await context.close();
    }
  });
}
