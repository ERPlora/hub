// Cancelling an appointment with «Ask the assistant» and «Ask me first» (hub#634), end to end with its real dependencies:
// the Hub of this stack, its SaaS's gateway and, behind it, the e2e's provider (assistant-provider.ts; the SaaS seeded
// with it, README «El asistente»). A real appointment of a professional is booked; in the editor the step is given
// «Cancel an appointment», which only «Ask me first» offers; saved, granted and run, the worker asks the assistant
// (`workerAsks`), which wants to cancel it: nothing is cancelled until the owner says yes in «Waiting for your answer»,
// whose card says which appointment it is, and then it is cancelled for real.
// flow: FLOW-F28 FLOW-F12 FLOW-F37 FLOW-F38 APPOINTMENT-F06
import { type BrowserContext, expect, test } from '@playwright/test';

import { aMonday, salonCleanUp } from './appointment-helpers';
import { emptyMonth } from './assistant-real';
import { A, api, capture, psql, shown } from './helpers';
import { approve, saveGrantAndSwitchOn, signedIn } from './flow-helpers';
import { providerSpec, runAndAsk, runFinishes } from './provider-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { post } from './service-helpers';
import { pick } from './task-helpers';

const KEY = 'FIX-HUB-FLOW-ASK-ME-FIRST-CANCEL-APPOINTMENT';
const TAG = 'E2E FlowCancelAppt';
const DAY = aMonday();

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      ...salonCleanUp(TAG),
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
  emptyMonth();
}

providerSpec(cleanUp);

/** A real appointment of a professional at 10:00 on `DAY`, through each app's own API: `DAY` open from 09:00 to 18:00. */
async function booked(context: BrowserContext, stamp: string): Promise<{ id: string; customer: string }> {
  const customer = await post<{ id: string; name: string }>(context, '/customer/customers', {
    name: `${TAG} Lucía ${stamp}`,
    phone: `6${String(Date.now()).slice(-8)}`,
  });
  const service = await post<{ id: string }>(context, '/service/services', {
    name: `${TAG} Haircut ${stamp}`,
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string }>(context, '/staff/members', { first_name: `${TAG} Bea ${stamp}`, last_name: 'Stylist' });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  if (psql(`select count(*) from schedule_specialday where name like '${TAG}%'`) === '0') {
    await post(context, '/schedule/special_days', {
      date: DAY,
      name: `${TAG} open`,
      is_closed: false,
      intervals: [{ open_time: '09:00', close_time: '18:00' }],
    });
  }
  const made = await post<{ id: string; status: string }>(context, '/appointment/appointments', {
    customer_id: customer.id,
    services: [{ service_id: service.id }],
    staff_id: member.id,
    start: `${DAY}T10:00`,
  });
  return { id: made.id, customer: customer.name };
}

async function statusOf(context: BrowserContext, id: string): Promise<string> {
  const read = await api<{ status: string }>(context, A, 'GET', `/appointment/appointments/detail?id=${id}`);
  expect(read.status).toBe(200);
  return read.data.status;
}

for (const viewport of VIEWPORTS) {
  test(`FLOW-F28 an appointment is cancelled only after the owner's yes, with «Ask me first», at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const stamp = `${viewport.label}${Date.now().toString(36)}`;
    const name = `${TAG} ${stamp}`;
    const { context, page } = await signedIn(browser, '/flow/automations/new', viewport);
    try {
      const appointment = await booked(context, stamp);
      const before = await statusOf(context, appointment.id);
      const editor = shown(page);
      await editor.locator('[data-testid=flow-editor-name] input').fill(name);
      await editor.locator('[data-testid=flow-editor-add-assistant]').click();
      // The provider's marker: ask for the cancellation of that appointment, then say how it went.
      const asked = { id: appointment.id, reason: 'The customer wrote to cancel' };
      await editor.locator('[data-testid=flow-assistant-prompt-s1-text-0]').fill(`E2E-ASK appointment__appointment__cancel ${JSON.stringify(asked)}`);
      await pick(page, 'flow-assistant-addtool-s1', 'Cancel an appointment', 'Cancel an appointment');
      await expect(editor.locator('[data-testid="flow-assistant-tool-s1-appointment.appointment.cancel"]')).toHaveText('Cancel an appointment');
      await expect(editor.locator('[data-testid=flow-assistant-askfirst-s1]')).toHaveText(
        'Only after a yes from someone who may do it themselves: «Cancel an appointment».',
      );
      // FLOW-F12: saved, what it needs is granted, the cancellation included, only because its step asks first.
      const flowId = await saveGrantAndSwitchOn(page);
      expect(psql(`select grants::text from flow_flow where id = '${flowId}'`)).toBe('["appointment.appointment.cancel"]');

      // FLOW-F38: the assistant wants to cancel it; nothing is cancelled before a yes.
      await runAndAsk(page, flowId);
      expect(await statusOf(context, appointment.id)).toBe(before);

      // FLOW-F29: the card says the action and which appointment, whose and at what time, never its id.
      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card).toBeVisible();
      await expect(card.locator('[data-testid^=flow-question-action-]')).toHaveText('Cancel an appointment');
      const data = card.locator('[data-testid^=flow-question-data-] li').filter({ hasText: appointment.customer });
      await expect(data).toContainText('Appointment');
      await expect(data).toContainText('10:00');
      await expect(data).toContainText('Stylist');
      await expect(card).not.toContainText(appointment.id);
      await card.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${KEY}-${viewport.label}`);
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });

      // The owner says yes: the appointment of that professional is cancelled for real.
      await approve(page, card);
      expect(await statusOf(context, appointment.id)).toBe('cancelled');
      // The step goes back to the assistant with what happened, and the run finishes.
      await runFinishes(flowId);
    } finally {
      await context.close();
    }
  });
}
