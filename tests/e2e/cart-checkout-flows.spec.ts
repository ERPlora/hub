// Every flow of Cart & Checkout that has a screen, as the owner, in the three viewports (390, 834 and 1440
// wide): in Carts, create one (a session in use is refused under Session), read and search them, see an
// overdue one turn Expired, abandon one and delete another after confirming; in Orders, reached by the
// tabbar, mark one paid and complete it (its cart becomes Converted) and fail another with its reason.
// Lines and orders are started through the API, as the assistant does (the screens have no form for them,
// WORKBOOK «Pantallas»). Each flow is a step and leaves its capture, `APP-CART_CHECKOUT-<flow>-<width>`,
// after checking that nothing scrolls sideways. Everything carries the session prefix «e2e-cc» and is
// removed before and after it.
// flow: CART_CHECKOUT-F01 CART_CHECKOUT-F05 CART_CHECKOUT-F06 CART_CHECKOUT-F07 CART_CHECKOUT-F09 CART_CHECKOUT-F10 CART_CHECKOUT-F11 CART_CHECKOUT-F12
import { expect, test } from '@playwright/test';

import { psql, shown } from './helpers';
import {
  type Cart,
  cleanUp,
  code,
  FLOW_VIEWPORTS,
  get,
  hidden,
  listShown,
  orderFrom,
  post,
  rowAction,
  rowOf,
  signedIn,
  snap,
} from './cart-checkout-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

const cartStatus = (id: string): string => psql(`select status from cart_checkout_cart where id = '${id}'`);

for (const [width, viewport] of Object.entries(FLOW_VIEWPORTS)) {
  test(`CART_CHECKOUT-F01, F05 to F07 and F09 to F12, every screen of Cart & Checkout at ${width} wide`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, '/cart_checkout/carts', viewport);
    try {
      const view = shown(page);
      await listShown(page, 'cart-checkout-carts');
      await expect(page.locator('ion-title').filter({ hasText: 'Cart & Checkout' }).first()).toBeVisible();

      const first = code(`one-${width}`);
      let firstId = '';
      await test.step('CART_CHECKOUT-F01 create a cart; a session in use is refused under Session', async () => {
        await view.locator('[data-testid=cart-checkout-carts-add]').click();
        const submit = page.locator('[data-testid=cart-checkout-cart-form-submit]');
        await expect(submit).toHaveAttribute('aria-disabled', 'true');
        await page.locator('[data-testid=cart-checkout-cart-form-session] input').fill(first);
        await page.locator('[data-testid=cart-checkout-cart-form-email] input').fill('ana@example.com');
        await page.locator('[data-testid=cart-checkout-cart-form-name] input').fill('Ana García');
        await expect(submit).not.toHaveAttribute('aria-disabled', 'true');
        await snap(page, 'CART_CHECKOUT-F01', width);
        await submit.click();
        await expect.poll(() => psql(`select count(*) from cart_checkout_cart where session_token = '${first}'`)).toBe('1');
        firstId = psql(`select id from cart_checkout_cart where session_token = '${first}'`);
        const row = rowOf(page, 'cart-checkout-carts', firstId);
        await expect(row).toContainText('ana@example.com');
        await expect(row).toContainText('Active');
        await expect(row).toContainText('€0.00');
        expect(psql(`select currency || ' ' || total_amount from cart_checkout_cart where id = '${firstId}'`)).toBe('EUR 0');

        // The same session again: refused under Session, with what was typed kept.
        await view.locator('[data-testid=cart-checkout-carts-add]').click();
        await page.locator('[data-testid=cart-checkout-cart-form-session] input').fill(first);
        await submit.click();
        await expect(page.locator('[data-testid=cart-checkout-cart-form]')).toContainText('There is already a cart with that session.');
        await expect(page.locator('[data-testid=cart-checkout-cart-form-session] input')).toHaveValue(first);
        await page.locator('[data-testid=cart-checkout-cart-form-cancel]').click();
        await expect(page.locator('[data-testid=cart-checkout-cart-form-submit]')).toBeHidden();
        expect(psql(`select count(*) from cart_checkout_cart where session_token = '${first}'`)).toBe('1');
      });

      const second = code(`two-${width}`);
      let secondId = '';
      await test.step('CART_CHECKOUT-F12 read the carts with their items and totals, and search them', async () => {
        // Its lines through the API (CART_CHECKOUT-F02, the assistant's path): 2 × 617,28 € and 0,5 × 3 €.
        secondId = (await post<Cart>(context, '/cart_checkout/carts', { session_token: second, customer_email: 'bea@example.com', customer_name: 'Bea López' }, 201)).id;
        await post(context, '/cart_checkout/items', { session_token: second, product_ref: 'p-1', product_name: 'Champú', quantity: '2', unit_price: 61728 }, 201);
        await post(context, '/cart_checkout/items', { session_token: second, product_ref: 'p-2', product_name: 'Peine', quantity: '0.5', unit_price: 300 }, 201);
        const row = rowOf(page, 'cart-checkout-carts', secondId);
        await expect(row).toContainText('bea@example.com');
        await expect(row).toContainText('2.5');
        // Four-digit totals are grouped (hub#1090).
        await expect(row).toContainText('€1,236.06');

        // A piece of the first one's code finds only it.
        const search = view.locator('[data-testid=cart-checkout-carts-search] input');
        await search.fill(first.split('-').slice(2).join('-'));
        await expect(rowOf(page, 'cart-checkout-carts', firstId)).toBeVisible();
        await expect(rowOf(page, 'cart-checkout-carts', secondId)).toHaveCount(0);
        await snap(page, 'CART_CHECKOUT-F12', width);
        await search.fill('');
        await expect(row).toBeVisible();

        // At every width the filters wait behind the funnel, as the old list (CART_CHECKOUT-F12,
        // FIX-HUB-CART-CHECKOUT-ORDERS-FILTERS-BEHIND-FUNNEL): written in its panel (a sheet in the cards) and applied.
        const funnel = view.locator('[data-testid=cart-checkout-carts-filters-toggle]');
        const sheet = view.locator('[data-testid=cart-checkout-carts-filters-panel]');
        await expect(view.locator('[data-testid=cart-checkout-carts-filters]'), 'no open row of filters').toHaveCount(0);
        await expect(funnel).toBeVisible();
        async function totalFrom(value: string): Promise<void> {
          if (!(await sheet.isVisible())) await funnel.click();
          await sheet.locator('[data-testid=cart-checkout-carts-filter-total_amount_from] input').fill(value);
          await view.locator('[data-testid=cart-checkout-carts-filters-apply]').click();
        }
        // «Total from» reads an amount as it is pasted (pm#521): «1.236,06» leaves that cart only.
        await totalFrom('1.236,06');
        await expect(row).toBeVisible();
        await expect(rowOf(page, 'cart-checkout-carts', firstId)).toHaveCount(0);
        // «1.250» is 1.250 € or 1,25 €: it says so under its box (in the panel) and filters nothing.
        await totalFrom('1.250');
        await funnel.click();
        await expect(view.getByText('Type an amount, like 12.50')).toBeVisible();
        await expect(rowOf(page, 'cart-checkout-carts', firstId)).toBeVisible();
        await totalFrom('');
        // «Apply» closed the panel: opened again, its box no longer warns (else the check below proves nothing).
        await funnel.click();
        await expect(sheet).toBeVisible();
        await expect(view.getByText('Type an amount, like 12.50')).toHaveCount(0);
        await view.locator('[data-testid=cart-checkout-carts-filters-close]').click();
        await expect(sheet).toBeHidden();
      });

      const soon = code(`soon-${width}`);
      await test.step('CART_CHECKOUT-F07 a cart past its expiry reads Expired, and expiring stores it', async () => {
        const cart = await post<Cart>(context, '/cart_checkout/carts', { session_token: soon, expires_at: new Date(Date.now() + 4000).toISOString() }, 201);
        const row = rowOf(page, 'cart-checkout-carts', cart.id);
        await expect(row).toContainText('Active');
        await expect.poll(() => psql(`select expires_at < now() from cart_checkout_cart where id = '${cart.id}'`), { timeout: 15_000 }).toBe('t');
        // Read again, it is Expired before anybody stores it.
        expect((await get<Cart>(context, `/cart_checkout/carts/detail?session_token=${soon}`)).status).toBe('expired');
        expect(cartStatus(cart.id)).toBe('active');
        // The order the assistant, the API and the worker's task give: it is stored, and the open list hears it.
        expect((await post<{ expired: number }>(context, '/cart_checkout/carts/cleanup_expired', {})).expired).toBeGreaterThanOrEqual(1);
        expect(cartStatus(cart.id)).toBe('expired');
        await expect(row).toContainText('Expired');
        await expect(view.locator(`[data-testid=cart-checkout-carts-row-${cart.id}-abandon]`)).toHaveCount(0);
        await snap(page, 'CART_CHECKOUT-F07', width);
      });

      await test.step('CART_CHECKOUT-F05 abandon an active cart: it stays, Abandoned, with its lines', async () => {
        await rowAction(page, 'cart-checkout-carts', firstId, 'abandon');
        const row = rowOf(page, 'cart-checkout-carts', firstId);
        await expect(row).toContainText('Abandoned');
        expect(cartStatus(firstId)).toBe('abandoned');
        await expect(page.locator(`[data-testid=cart-checkout-carts-row-${firstId}-abandon]`)).toHaveCount(0);
        await snap(page, 'CART_CHECKOUT-F05', width);
      });

      await test.step('CART_CHECKOUT-F06 delete a cart after confirming; Cancel keeps it', async () => {
        const confirm = page.locator('ion-modal.ep-form-modal').filter({ hasText: `Delete the cart ${second}?` });
        await rowAction(page, 'cart-checkout-carts', secondId, 'delete');
        await expect(confirm).toBeVisible();
        await confirm.locator('.ep-form-modal__cancel').click();
        await expect(confirm).toBeHidden();
        await expect(rowOf(page, 'cart-checkout-carts', secondId)).toBeVisible();
        expect(psql(`select deleted_at is null from cart_checkout_cart where id = '${secondId}'`)).toBe('t');

        await rowAction(page, 'cart-checkout-carts', secondId, 'delete');
        await expect(confirm).toBeVisible();
        await snap(page, 'CART_CHECKOUT-F06', width);
        await confirm.locator('.ep-form-modal__submit').click();
        await expect(confirm).toBeHidden();
        await expect(rowOf(page, 'cart-checkout-carts', secondId)).toHaveCount(0);
        expect(psql(`select deleted_at is not null from cart_checkout_cart where id = '${secondId}'`)).toBe('t');
        // Its session is free again for another cart.
        await post(context, '/cart_checkout/carts', { session_token: second }, 201);
      });

      const paid = await orderFrom(context, code(`paid-${width}`), { unitPrice: 1250 });
      const failed = await orderFrom(context, code(`fail-${width}`), { unitPrice: 400 });
      expect(paid.order_number).toMatch(/^OS-\d{8}-\d{4}$/);
      await view.locator('[data-testid=tab-orders]').click();
      await expect(page).toHaveURL(/\/cart_checkout\/orders$/);
      const orders = shown(page);
      await listShown(page, 'cart-checkout-orders');
      const paidRow = rowOf(page, 'cart-checkout-orders', paid.id);

      await test.step('CART_CHECKOUT-F09 mark an initiated order as paid', async () => {
        await expect(paidRow).toContainText(paid.order_number);
        // The number tells one order from the next: it is never cut («OS-20261021-00…» twice).
        expect(await hidden(paidRow, paid.order_number), `${paid.order_number} at ${width}`).toBeLessThanOrEqual(0);
        await expect(paidRow).toContainText('Initiated');
        await expect(paidRow).toContainText('€25.00');
        await rowAction(page, 'cart-checkout-orders', paid.id, 'pay');
        await expect(paidRow).toContainText('Paid');
        expect(psql(`select status || ' ' || (paid_at is not null) from cart_checkout_order where id = '${paid.id}'`)).toBe('paid true');
        await expect(page.locator(`[data-testid=cart-checkout-orders-row-${paid.id}-pay]`)).toHaveCount(0);
        await snap(page, 'CART_CHECKOUT-F09', width);
      });

      await test.step('CART_CHECKOUT-F11 complete a paid order: its cart becomes Converted', async () => {
        await rowAction(page, 'cart-checkout-orders', paid.id, 'complete');
        await expect(paidRow).toContainText('Completed');
        expect(psql(`select o.status || ' ' || c.status from cart_checkout_order o join cart_checkout_cart c on c.id = o.cart_id where o.id = '${paid.id}'`)).toBe(
          'completed converted',
        );
        await expect(page.locator(`[data-testid^=cart-checkout-orders-row-${paid.id}-]:not([data-testid$=-menu])`)).toHaveCount(0);
        await snap(page, 'CART_CHECKOUT-F11', width);
      });

      await test.step('CART_CHECKOUT-F10 fail an order with its reason', async () => {
        await rowAction(page, 'cart-checkout-orders', failed.id, 'fail');
        const submit = page.locator('[data-testid=cart-checkout-fail-submit]');
        await expect(submit).toHaveAttribute('aria-disabled', 'true');
        await page.locator('[data-testid=cart-checkout-fail-reason] textarea').fill('Card declined');
        await expect(submit).not.toHaveAttribute('aria-disabled', 'true');
        await snap(page, 'CART_CHECKOUT-F10-form', width);
        await submit.click();
        const failedRow = rowOf(page, 'cart-checkout-orders', failed.id);
        await expect(failedRow).toContainText('Failed');
        await expect(failedRow).toContainText('Reason: Card declined');
        expect(await hidden(failedRow, 'Reason: Card declined'), `the reason at ${width}`).toBeLessThanOrEqual(0);
        await snap(page, 'CART_CHECKOUT-F10', width);
        expect(psql(`select status || ' ' || failure_reason from cart_checkout_order where id = '${failed.id}'`)).toBe('failed Card declined');
        // The order's cart stays as it was.
        expect(psql(`select c.status from cart_checkout_cart c join cart_checkout_order o on o.cart_id = c.id where o.id = '${failed.id}'`)).toBe('active');
      });

      await test.step('CART_CHECKOUT-F12 search the orders by their number', async () => {
        await orders.locator('[data-testid=cart-checkout-orders-search] input').fill(paid.order_number);
        await expect(paidRow).toBeVisible();
        await expect(rowOf(page, 'cart-checkout-orders', failed.id)).toHaveCount(0);
      });
    } finally {
      await context.close();
    }
  });
}
