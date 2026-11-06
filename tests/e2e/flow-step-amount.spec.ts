// The amount a step leaves, said as money in «Waiting for your answer» (hub#498): an automation records a payment
// (Payments) and then asks someone first, inserting what it paid. Automations knew an amount only by its words
// («in cents»), so the question asked «Paid 1250 to …». Now it reads the mark of the payment's schema
// (`"money": true`) and says the amount in the currency the payment answers («€12.50»), as the assistant's card does.
// Everything created here is named «E2E FlowAmount …» and removed before and after.
// flow: FLOW-F28 FLOW-F11
import { expect, test } from '@playwright/test';

import { A, api, psql, saveSessionForTheSweep, settledCapture, shown } from './helpers';
import { manualFlow, onAutomations } from './flow-helpers';
import { VIEWPORTS } from './schedule-helpers';

const KEY = 'FLOW-F28-step-amount';
const TAG = 'E2E FlowAmount';
const RECORD = 'payment.payment.create';

/** Deletes what the spec created; the counter of a day goes too when no payment of that day is left. */
function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  const methods = `select id from payment_paymentmethod where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from payment_payment where method_id in (${methods})`,
      `delete from payment_paymentmethod where id in (${methods})`,
      `delete from payment_paymentcounter c where not exists (select 1 from payment_payment p where p.reference like 'PAY-' || to_char(c.day, 'YYYYMMDD') || '-%')`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

for (const viewport of VIEWPORTS) {
  test(`FLOW-F28 the amount of a payment a step records is said as money in its question, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    await onAutomations(browser, viewport, TAG, async ({ context, page, name }) => {
      const method = await api<{ id: string }>(context, A, 'POST', '/payment/methods', { name });
      expect(method.status, JSON.stringify(method.data)).toBe(201);
      const payment = { method_id: method.data.id, payment_date: '2026-11-06', amount: 1250, beneficiary_name: 'Proveedor Norte SL' };
      const steps = [
        { id: 's1', kind: 'command', operation: RECORD, params: payment },
        { id: 's2', kind: 'ask', title: 'Paid {{steps.s1.amount}} to {{steps.s1.beneficiary_name}}?' },
      ];
      const flowId = await manualFlow(context, name, steps, [RECORD]);
      const ran = await api<{ status: string }>(context, A, 'POST', '/flow/flows/run', { id: flowId, input: {} });
      expect(ran.status, JSON.stringify(ran.data)).toBe(200);
      expect(ran.data.status).toBe('asking');

      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      // Before: «Paid 1250 to Proveedor Norte SL?».
      await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText('Paid €12.50 to Proveedor Norte SL?');
      await card.scrollIntoViewIfNeeded();
      await settledCapture(page, `${KEY}-${viewport.label}`);
      await saveSessionForTheSweep(context);

      await card.locator('[data-testid^=flow-question-reject-]').click();
      await expect(card).toHaveCount(0);
    });
  });
}
