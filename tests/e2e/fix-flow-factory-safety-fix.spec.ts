// A factory recipe's safety fix reaches the automation already built from it, without waiting for the owner
// (apps/flow/WORKBOOK.md FLOW-F36, with FLOW-F37/F38 and FLOW-F29), end to end with its real dependencies: the Hub of
// this stack, its SaaS's gateway (`/internal/assistant/chat`, `/internal/whatsapp/send`) and, behind it, the e2e's
// provider (assistant-provider.ts, started by this spec; the SaaS seeded with it, README «El asistente») and Meta's
// Graph (README «WhatsApp»).
// The owner turned «Book a table» on before its app fixed whose card its assistant acts for (hub#447) and before it left
// out the inbox's old messages: its «Ask the assistant» step (`s10`) has no fixed data, its «Only when…» has no
// `source` and it is «New version». Nothing waits for the owner: Automatizaciones shows no notice for it, its editor
// shows the condition and the fixed data its app puts on it as set by its app (never to take off from there, and saved
// untouched they are written), an old message of the inbox starts nothing, and when a
// guest asks to cancel another guest's table the assistant is not offered on whose behalf, the card of «Waiting for
// your answer» says the writer's, and after the «Approve» the other guest's reservation is as it was.
// flow: FLOW-F36 FLOW-F38 FLOW-F29
import { expect, test } from '@playwright/test';

import { capture, psql, shown } from './helpers';
import { approve, signedIn } from './flow-helpers';
import { relay, workerAsks } from './provider-helpers';
import { madridDay, reservationStatus } from './reservation-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { answerSpec, askedOnBehalfOfTheWriter, bookingCleanUp, customerWrites, guestWithATable, reservationsQuestion, tablesAnswered } from './whatsapp-answer-helpers';
import { e2ePhone, keepPhoto, receive, restorePhoto } from './whatsapp-helpers';

const KEY = 'FIX-HUB-FLOW-FACTORY-SAFETY-FIX-WAITS-FOR-THE-OWNERS-UPDATE';
const ANSWER = 'whatsapp_inbox/reservation_from_whatsapp';
const CANCEL = 'reservation.reservation.cancel';
/** What the editor says of a condition or a fixed datum its app puts on it, which never comes off from there. */
const SET_BY = 'Set by WhatsApp inbox: you can change it, not take it off.';
/** The day this spec books on, and how its slot and open day are known again (slots have no name). */
const BOOK = { day: madridDay(4), sentinel: 78, reason: 'E2E factory safety fix open' };

/** «Book a table» as an owner who turned it on before hub#447 and before its app left out the inbox's old messages has
 *  it: its assistant's step fixes no data, its «Only when…» says nothing of `source`, and it was built from another
 *  version («New version»). */
function asTurnedOnBeforeTheFix(): string {
  const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);
  expect(flowId, '«Book a table» turned on').not.toBe('');
  psql(
    `update flow_flow set steps = (select jsonb_agg(case when step->>'id' = 's10' then step - 'pinned' else step end order by at) ` +
      `from jsonb_array_elements(steps) with ordinality as listed(step, at)), trigger_filter = trigger_filter - 'input.source', ` +
      `recipe_digest = repeat('0', 64) where id = '${flowId}'`,
  );
  expect(psql(`select count(*) from flow_flow, jsonb_array_elements(steps) as step where id = '${flowId}' and step ? 'pinned'`)).toBe('0');
  expect(psql(`select trigger_filter ? 'input.source' from flow_flow where id = '${flowId}'`)).toBe('f');
  return flowId;
}

// It drives the inbox: a's photo is kept first and put back last (whatsapp-photo.test.ts).
test.beforeAll(keepPhoto);
const provider = answerSpec(() => bookingCleanUp(BOOK));
test.afterAll(restorePhoto);

for (const viewport of VIEWPORTS) {
  test(`FLOW-F36 a table answer turned on before its app's safety fixes never answers an old message nor cancels another guest's table, with nothing for the owner to press, at ${viewport.label}`, async ({ browser }) => {
    // The editor's visit on top of the whole WhatsApp round of fix-whatsapp-inbox-table-cancel.spec.ts: 180 s ran out
    // on a loaded machine (load average 32) in the last relay, at 1440.
    test.setTimeout(300_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      await tablesAnswered(context, page, BOOK);
      const flowId = asTurnedOnBeforeTheFix();

      // Automatizaciones has nothing for the owner to update: its card says «New version», as any other change of
      // its app, and no notice over «Your automations» asks for anything.
      await page.goto('/flow/automations');
      await expect(shown(page).locator(`[data-testid="flow-recipe-${ANSWER}"]`)).toContainText('New version');
      const list = shown(page).locator('[data-testid=flow-list-section]');
      await expect(list.locator(`[data-testid="flow-list-toggle-${flowId}"]`)).toBeVisible();
      await expect(shown(page).locator('[data-testid=flow-repairs]')).toHaveCount(0);
      await expect(shown(page).locator(`[data-testid="flow-repair-${ANSWER}"]`)).toHaveCount(0);
      await expect(shown(page).getByText('starts in more cases than it should')).toHaveCount(0);
      await list.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-list-${viewport.label}`);

      // Its editor shows, under «Fixed data» of the assistant's step, the card its app fixes on a cancellation.
      await page.goto(`/flow/automations/${flowId}`);
      const editor = shown(page);
      // Its «Only when…»: the inbound messages, and only the live ones, as its app has it today. Both are its app's:
      // set by it, never to remove from here (FLOW-F36).
      await editor.locator('[data-testid=flow-trigger-open]').click();
      await expect(editor.locator('[data-testid^=flow-trigger-filter-row-]')).toHaveCount(2);
      const locked = editor.locator('[data-testid^=flow-trigger-filter-locked-]');
      await expect(locked).toHaveText([SET_BY, SET_BY]);
      await expect(editor.locator('[data-testid^=flow-trigger-filter-remove-]')).toHaveCount(0);
      // Its steps say each app by its visible name, never its internal one (hub#476: at 390 one said «whatsapp_inbox»
      // while the catalog was on its way).
      await expect(editor.locator('[data-testid=flow-step-open-s1]')).toContainText('Look up: Read · WhatsApp inbox (message)');
      await expect(editor.locator('[data-testid^=flow-step-open-]').filter({ hasText: 'whatsapp_inbox' })).toHaveCount(0);
      await locked.last().scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-editor-filter-${viewport.label}`);
      await editor.locator('[data-testid=flow-step-open-s10]').click();
      const pin = editor.locator(`[data-testid="flow-assistant-pin-s10-${CANCEL}-on_behalf_of"]`);
      await expect(pin).toContainText('Cancel a reservation › On behalf of the customer');
      await expect(editor.locator('[data-testid=flow-assistant-nopins-s10]')).toHaveCount(0);
      // Its datum is its app's too: no ×, only its value would change.
      const setBy = editor.locator(`[data-testid="flow-assistant-setbyapp-s10-${CANCEL}-on_behalf_of"]`);
      await expect(setBy).toHaveText(SET_BY);
      await expect(editor.locator(`[data-testid="flow-assistant-unpin-s10-${CANCEL}-on_behalf_of"]`)).toHaveCount(0);
      await setBy.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-editor-${viewport.label}`);

      // Marta's reservation at 21:00 for 2, on her card; Lucía, from another number and with no card yet, writes.
      const lucia = e2ePhone();
      let marta = e2ePhone();
      while (marta === lucia) marta = e2ePhone();

      // An old message of Lucía's chat that the inbox brings in (`source` «history») starts nothing.
      const old = receive(lucia, 'Do you have a table on Friday?', 'E2E Lucía', { source: 'history' });
      const oldReceived = psql(
        `select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${old.id}'`,
      );
      expect(oldReceived, 'whatsapp_inbox.message.received of the old message in the outbox').not.toBe('');
      await relay(oldReceived);
      expect(psql(`select count(*) from flow_flowrun where flow_id = '${flowId}'`)).toBe('0');
      const theirs = await guestWithATable(context, BOOK.day, { name: 'E2E Marta', phone: marta }, 2);
      const reservation = theirs.reservation;
      const before = await reservationStatus(context, reservation);

      // The assistant names Marta's reservation and, as a model fooled by the message might, says it is on Marta's
      // behalf: what the old step let it choose.
      const asked = { id: reservation, on_behalf_of: theirs.card };
      await customerWrites(lucia, `Cancel E2E Marta's table\nE2E-ASK reservation__reservation__cancel ${JSON.stringify(asked)}`, 'E2E Lucía');

      // Not even offered: on whose behalf is fixed by the step its app fixed after it was turned on.
      await askedOnBehalfOfTheWriter(provider(), flowId);

      // The card says on whose behalf the yes goes: Lucía's, never Marta's.
      const question = await reservationsQuestion(page);
      await expect(question).toContainText('On behalf of the customer: E2E Lucía');
      await expect(question).not.toContainText('On behalf of the customer: E2E Marta');
      await expect(shown(page).locator(`[data-testid="flow-repair-${ANSWER}"]`)).toHaveCount(0);
      await question.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);

      // «Approve»: Reservas refuses it on Lucía's behalf and Marta's reservation is as it was.
      await approve(page, question);
      expect(await reservationStatus(context, reservation)).toBe(before);
      await workerAsks(flowId);
      expect(JSON.stringify(provider().seen.at(-1)?.body)).toContain('reservation.customer_mismatch');
      await expect.poll(() => psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('succeeded');
      expect(await reservationStatus(context, reservation)).toBe(before);
      // Nothing was written behind the owner's back: the automation is still as they had it, and still on.
      expect(psql(`select count(*) from flow_flow, jsonb_array_elements(steps) as step where id = '${flowId}' and step ? 'pinned'`)).toBe('0');
      expect(psql(`select trigger_filter ? 'input.source' from flow_flow where id = '${flowId}'`)).toBe('f');
      expect(psql(`select enabled from flow_flow where id = '${flowId}'`)).toBe('t');

      // Saved from its editor without touching anything, it is taken, and what its app fixes is written down.
      await page.goto(`/flow/automations/${flowId}`);
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      expect(psql(`select trigger_filter->'input.source'->>'eq' from flow_flow where id = '${flowId}'`)).toBe('live');
      expect(psql(`select count(*) from flow_flow, jsonb_array_elements(steps) as step where id = '${flowId}' and step->'pinned' ? '${CANCEL}'`)).toBe('1');
    } finally {
      await context.close();
    }
  });
}
