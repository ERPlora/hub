// «Insert a datum» offers what a step leaves inside another datum (hub#963): after «Add something to a cart», the price
// and total of the line it adds and the cart's total after it, each named with the object it is in («1. Add something
// to a cart › Item › Unit price»); before, only «Item», «Cart» and «Removed», whole. What it inserts is a path the
// engine resolves (hub#961), so the question the automation asks says that price as money.
// Everything created here is named «E2E FlowNested …» and removed before and after.
// flow: FLOW-F11 FLOW-F28
import { expect, test } from '@playwright/test';

import { VIEWPORTS } from './assistant-card-helpers';
import { addToANewCart, manualFlow, onAutomations, questionSays } from './flow-helpers';
import { A, api, capture, psql, shown } from './helpers';

const KEY = 'FLOW-F11-insert-nested-datum';
const TAG = 'E2E FlowNested';
const ADD = 'cart_checkout.item.add';
const SESSION = 'e2e-flownested';

/** Deletes what the spec created. */
function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  const carts = `select id from cart_checkout_cart where session_token like '${SESSION}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from cart_checkout_cartitem where cart_id in (${carts})`,
      `delete from cart_checkout_cart where id in (${carts})`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

for (const viewport of VIEWPORTS) {
  test(`FLOW-F11 «Insert a datum» offers the price of the line a step adds to a cart, and the question says it as money, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(150_000);
    await onAutomations(browser, viewport, TAG, async ({ context, page, name }) => {
      const steps = [await addToANewCart(context, `${SESSION}-${viewport.label}`), { id: 's2', kind: 'ask', title: 'Line price' }];
      const flowId = await manualFlow(context, name, steps, [ADD]);

      // The question's title: «Insert a datum» → what the first step left inside the line it added.
      await page.goto(`/flow/automations/${flowId}`);
      const editor = shown(page);
      await editor.locator('[data-testid=flow-step-open-s2]').click();
      const picker = page.locator('ion-modal[data-testid=flow-picker]');
      const price = picker.locator('[data-testid="flow-picker-steps.s1.item.unit_price"]');
      // Opened before the editor has its catalog of actions, the picker says there is nothing to insert and stays so
      // until it is opened again (hub#969): opened again, as a person does.
      await expect(async () => {
        if (await picker.isVisible()) {
          await picker.locator('[data-testid=flow-picker-close]').click();
          await expect(picker).toBeHidden();
        }
        await editor.locator('[data-testid=flow-ask-title-s2-insert]').click();
        await expect(picker).toBeVisible();
        await expect(price).toBeVisible({ timeout: 1_000 });
      }).toPass({ timeout: 30_000 });
      await expect(price).toHaveText('1. Add something to a cart › Item › Unit price');
      await expect(picker.locator('[data-testid="flow-picker-steps.s1.item.line_total"]')).toHaveText('1. Add something to a cart › Item › Line total');
      await expect(picker.locator('[data-testid="flow-picker-steps.s1.cart.total_amount"]')).toHaveText('1. Add something to a cart › Cart › Total amount');
      // The first level stays: the line and the cart whole.
      await expect(picker.locator('[data-testid="flow-picker-steps.s1.item"]')).toHaveText('1. Add something to a cart › Item');
      await price.scrollIntoViewIfNeeded();
      await capture(page, `${KEY}-picker-${viewport.label}`);
      await price.click();
      await expect(picker).toBeHidden();
      await expect(editor.locator('[data-testid=flow-ask-title-s2-pill-1]')).toHaveText('1. Add something to a cart › Item › Unit price');
      // A title's last space does not survive saving: the words before the datum are written with it once it is in.
      await editor.locator('[data-testid=flow-ask-title-s2-text-0]').fill('Line price: ');
      await editor.locator('[data-testid=flow-editor-save]').click();
      await expect(editor.locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      const saved = await api<{ steps: { title?: string }[] }>(context, A, 'GET', `/flow/flows/detail?id=${flowId}`);
      expect(saved.status, JSON.stringify(saved.data)).toBe(200);
      expect(saved.data.steps[1]?.title).toBe('Line price: {{steps.s1.item.unit_price}}');

      // Run, the question says the price as money in the cart's currency: before, «Line price: 1250».
      const ran = await api<{ status: string }>(context, A, 'POST', '/flow/flows/run', { id: flowId, input: {} });
      expect(ran.status, JSON.stringify(ran.data)).toBe(200);
      expect(ran.data.status).toBe('asking');
      await questionSays({ context, page, name }, 'Line price: €12.50', `${KEY}-question-${viewport.label}`);
    });
  });
}
