// The amount a step leaves, said as money in «Waiting for your answer» (hub#498): an automation records a payment
// (Payments) and then asks someone first, inserting what it paid. Automations knew an amount only by its words
// («in cents»), so the question asked «Paid 1250 to …». Now it reads the mark of the payment's schema
// (`"money": true`) and says the amount in the currency the payment answers («€12.50»), as the assistant's card does.
// hub#926: the cash and ticket limits a charge preview leaves were said as «100000»; now as money in the euros the law
// writes them in, which the preview says beside them (`limits_currency`), and its total in the business's currency.
// hub#941: an amount a step leaves inside another datum — the line it adds to a cart (`item.unit_price`), the cart after
// it (`cart.total_amount`) — was said as «1250»; now as money in the currency that same datum answers.
// Everything created here is named «E2E FlowAmount …» and removed before and after.
// flow: FLOW-F28 FLOW-F11
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, psql, saveSessionForTheSweep, settledCapture, shown } from './helpers';
import { manualFlow, onAutomations } from './flow-helpers';
import { createProduct } from './inventory-helpers';
import { VIEWPORTS } from './schedule-helpers';

const KEY = 'FLOW-F28-step-amount';
const TAG = 'E2E FlowAmount';
const RECORD = 'payment.payment.create';
const PREVIEW = 'sale.checkout.preview';
const ADD = 'cart_checkout.item.add';
const SESSION = 'e2e-flowamount';

/** Deletes what the spec created; the counter of a day goes too when no payment of that day is left. */
function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  const methods = `select id from payment_paymentmethod where name like '${TAG}%'`;
  const checks = `select id from sale_order where label like '${TAG}%'`;
  const carts = `select id from cart_checkout_cart where session_token like '${SESSION}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from sale_orderline where order_id in (${checks})`,
      `delete from sale_order where id in (${checks})`,
      `delete from inventory_product where name like '${TAG}%'`,
      `delete from cart_checkout_cartitem where cart_id in (${carts})`,
      `delete from cart_checkout_cart where id in (${carts})`,
      `delete from payment_payment where method_id in (${methods})`,
      `delete from payment_paymentmethod where id in (${methods})`,
      `delete from payment_paymentcounter c where not exists (select 1 from payment_payment p where p.reference like 'PAY-' || to_char(c.day, 'YYYYMMDD') || '-%')`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/** Runs the manual automation `name` with `steps` (granted `grants`) until it asks, checks on Automations that its
 *  question says `said`, captures it as `shot` and answers no, which takes its card away. */
async function askedSaying(
  stage: { context: BrowserContext; page: Page; name: string },
  steps: unknown[],
  grants: string[],
  said: string,
  shot: string,
): Promise<void> {
  const { context, page, name } = stage;
  const flowId = await manualFlow(context, name, steps, grants);
  const ran = await api<{ status: string }>(context, A, 'POST', '/flow/flows/run', { id: flowId, input: {} });
  expect(ran.status, JSON.stringify(ran.data)).toBe(200);
  expect(ran.data.status).toBe('asking');

  await page.goto('/flow/automations');
  const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
  await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText(said);
  await card.scrollIntoViewIfNeeded();
  await settledCapture(page, shot);
  await saveSessionForTheSweep(context);

  await card.locator('[data-testid^=flow-question-reject-]').click();
  await expect(card).toHaveCount(0);
}

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
      // Before: «Paid 1250 to Proveedor Norte SL?».
      await askedSaying({ context, page, name }, steps, [RECORD], 'Paid €12.50 to Proveedor Norte SL?', `${KEY}-${viewport.label}`);
    });
  });
}

for (const viewport of VIEWPORTS) {
  test(`FLOW-F28 the legal limits of a charge preview are said in euros in its question, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    await onAutomations(browser, viewport, TAG, async ({ context, page, name }) => {
      const sku = `E2E-FLOWAMOUNT-${viewport.label}-${Date.now().toString(36).toUpperCase()}`;
      await createProduct(context, { name, sku, price: 1250 });
      const check = await api<{ id: string }>(context, A, 'POST', '/sale/orders', { label: name, lines: [{ product: sku }] });
      expect(check.status, JSON.stringify(check.data)).toBe(201);
      const steps = [
        { id: 's1', kind: 'query', operation: PREVIEW, params: { order_id: check.data.id } },
        { id: 's2', kind: 'ask', title: 'No cash from {{steps.s1.cash_limit}}, ticket up to {{steps.s1.ticket_limit}}: {{steps.s1.total}}?' },
      ];
      // Before: «No cash from 100000, ticket up to 300000: €12.50?».
      const said = 'No cash from €1,000.00, ticket up to €3,000.00: €12.50?';
      await askedSaying({ context, page, name }, steps, [PREVIEW], said, `${KEY}-limits-${viewport.label}`);
    });
  });
}

for (const viewport of VIEWPORTS) {
  test(`FLOW-F28 the amounts inside the line a step adds to a cart are said as money in its question, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    await onAutomations(browser, viewport, TAG, async ({ context, page, name }) => {
      const session = `${SESSION}-${viewport.label}-${Date.now().toString(36)}`;
      const cart = await api<{ id: string }>(context, A, 'POST', '/cart_checkout/carts', { session_token: session });
      expect(cart.status, JSON.stringify(cart.data)).toBe(201);
      const line = { session_token: session, product_ref: 'p-1', product_name: 'Champú', quantity: '2', unit_price: 1250 };
      const steps = [
        { id: 's1', kind: 'command', operation: ADD, params: line },
        { id: 's2', kind: 'ask', title: '{{steps.s1.item.unit_price}} / {{steps.s1.item.line_total}} / {{steps.s1.cart.total_amount}}?' },
      ];
      // Before: «1250 / 2500 / 2500?».
      await askedSaying({ context, page, name }, steps, [ADD], '€12.50 / €25.00 / €25.00?', `${KEY}-inside-${viewport.label}`);
    });
  });
}
