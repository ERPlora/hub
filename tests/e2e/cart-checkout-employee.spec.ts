// Cart & Checkout as an employee (WORKBOOK «Quién la usa»: the employee only looks), in the three
// viewports: Carts and Orders list what there is, with no «New cart» and no row action. The owner leaves a
// cart and an order first, through the API. Captures: `APP-CART_CHECKOUT-CART_CHECKOUT-F12-employee-<width>`.
// Everything carries the session prefix «e2e-cc» and is removed before and after it.
// flow: CART_CHECKOUT-F12
import { expect, test } from '@playwright/test';

import { EMPLOYEE, shown } from './helpers';
import { cleanUp, code, FLOW_VIEWPORTS, listShown, orderFrom, rowOf, signedIn, snap } from './cart-checkout-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('CART_CHECKOUT-F12 an employee looks at the carts and the orders and changes nothing', async ({ browser }) => {
  const owner = await signedIn(browser, '/cart_checkout/carts');
  const order = await orderFrom(owner.context, code('staff'));
  await owner.context.close();
  const cartId = order.cart_id;

  for (const [width, viewport] of Object.entries(FLOW_VIEWPORTS)) {
    const { context, page } = await signedIn(browser, '/cart_checkout/carts', viewport, EMPLOYEE);
    try {
      await listShown(page, 'cart-checkout-carts');
      await expect(rowOf(page, 'cart-checkout-carts', cartId)).toBeVisible();
      await expect(shown(page).locator('[data-testid=cart-checkout-carts-add]')).toHaveCount(0);
      await expect(page.locator(`[data-testid^=cart-checkout-carts-row-${cartId}-]`)).toHaveCount(0);
      await snap(page, 'CART_CHECKOUT-F12-employee', width);

      await shown(page).locator('[data-testid=tab-orders]').click();
      await listShown(page, 'cart-checkout-orders');
      await expect(rowOf(page, 'cart-checkout-orders', order.id)).toContainText(order.order_number);
      await expect(page.locator(`[data-testid^=cart-checkout-orders-row-${order.id}-]`)).toHaveCount(0);
    } finally {
      await context.close();
    }
  }
});
