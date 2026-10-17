// Cart & Checkout in Chrome (WORKBOOK CART_CHECKOUT-F01 to F12), hidden by default: the owner creates a
// cart in Carts (a session code in use is refused under Session), finds it by a piece of its code,
// abandons it and deletes another after confirming; lines and orders are started through the API (as the
// assistant does: the old screens had no form for them), and in Orders each row's own action marks one
// paid and completes it (its cart becomes Converted) and fails another with its reason. An employee only
// looks. Each screen is captured in three viewports. Everything this spec creates carries the session
// prefix «e2e-cc» and is removed before and after it.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shot, shown } from './helpers';

const TAG = 'e2e-cc';
const code = (label: string): string => `${TAG}-${label}-${Date.now().toString(36)}`;
const VIEWPORTS = {
  desktop: { width: 1280, height: 860 },
  tablet: { width: 820, height: 1180 },
  phone: { width: 390, height: 844 },
} as const;
const CARTS = `select id from cart_checkout_cart where session_token like '${TAG}%'`;

/** Deletes what the spec created; the counter of a day goes too when no order of that day is left. */
function cleanUp(): void {
  psql(
    [
      `delete from cart_checkout_order where cart_id in (${CARTS})`,
      `delete from cart_checkout_cartitem where cart_id in (${CARTS})`,
      `delete from cart_checkout_cart where session_token like '${TAG}%'`,
      `delete from cart_checkout_ordercounter c where not exists (select 1 from cart_checkout_order o where o.order_number like 'OS-' || to_char(c.day, 'YYYYMMDD') || '-%')`,
    ].join('; '),
  );
}

async function pageAs(browser: Browser, next: string, viewport: { width: number; height: number } = VIEWPORTS.desktop, employee = false) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, employee ? EMPLOYEE : undefined);
  return { context, page };
}

/** Runs a row action: its button, or the same entry inside «⋮» when the row folds its actions. */
async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`);
  const menu = shown(page).locator(`[data-testid=${table}-row-${id}-menu]`);
  await button.or(menu).first().waitFor({ state: 'visible' });
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await menu.click();
  await page.locator(`ion-popover [data-testid=${table}-row-${id}-${action}]`).click();
}

const rowOf = (page: Page, table: string, id: string) => shown(page).locator(`[data-testid=${table}-row][data-id="${id}"]`).first();

/** A cart with one line and an order started from it, through the API (the assistant's path). */
async function orderFrom(context: BrowserContext, session: string, unitPrice: number): Promise<{ id: string; number: string }> {
  const cart = await api<{ id: string }>(context, A, 'POST', '/cart_checkout/carts', { session_token: session, customer_email: 'ana@example.com' });
  expect(cart.status).toBe(201);
  const line = await api(context, A, 'POST', '/cart_checkout/items', {
    session_token: session,
    product_ref: 'p-1',
    product_name: 'Champú',
    quantity: '2',
    unit_price: unitPrice,
  });
  expect(line.status).toBe(201);
  const order = await api<{ id: string; order_number: string }>(context, A, 'POST', '/cart_checkout/checkout/initiate', { session_token: session });
  expect(order.status).toBe(201);
  return { id: order.data.id, number: order.data.order_number };
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('Carts: create, refuse a twin, search, abandon, delete after confirming', async ({ browser }) => {
  const first = code('one');
  const second = code('two');
  const { context, page } = await pageAs(browser, '/cart_checkout/carts');
  try {
    const view = shown(page);
    await view.locator('[data-testid=cart-checkout-carts-empty], [data-testid=cart-checkout-carts-row]').first().waitFor({ state: 'visible' });

    // «New cart»: Save stays off until there is a session; the new cart is Active, empty.
    await view.locator('[data-testid=cart-checkout-carts-add]').click();
    await expect(page.locator('[data-testid=cart-checkout-cart-form-submit]')).toHaveAttribute('aria-disabled', 'true');
    await page.locator('[data-testid=cart-checkout-cart-form-session] input').fill(first);
    await page.locator('[data-testid=cart-checkout-cart-form-email] input').fill('ana@example.com');
    await page.locator('[data-testid=cart-checkout-cart-form-name] input').fill('Ana García');
    await page.screenshot({ path: shot('cart-checkout-new-cart-desktop'), animations: 'disabled' });
    await page.locator('[data-testid=cart-checkout-cart-form-submit]').click();
    await expect.poll(() => psql(`select count(*) from cart_checkout_cart where session_token = '${first}'`)).toBe('1');
    const firstId = psql(`select id from cart_checkout_cart where session_token = '${first}'`);
    const firstRow = rowOf(page, 'cart-checkout-carts', firstId);
    await expect(firstRow).toContainText('ana@example.com');
    await expect(firstRow).toContainText('Active');
    await expect(firstRow).toContainText('€0.00');

    // The same session again is refused under Session, with what was typed kept.
    await view.locator('[data-testid=cart-checkout-carts-add]').click();
    await page.locator('[data-testid=cart-checkout-cart-form-session] input').fill(first);
    await page.locator('[data-testid=cart-checkout-cart-form-submit]').click();
    await expect(page.locator('[data-testid=cart-checkout-cart-form]')).toContainText('There is already a cart with that session.');
    await expect(page.locator('[data-testid=cart-checkout-cart-form-session] input')).toHaveValue(first);
    await page.locator('[data-testid=cart-checkout-cart-form-cancel]').click();

    // A second cart, and a piece of the first one's code finds only it.
    await view.locator('[data-testid=cart-checkout-carts-add]').click();
    await page.locator('[data-testid=cart-checkout-cart-form-session] input').fill(second);
    await page.locator('[data-testid=cart-checkout-cart-form-submit]').click();
    await expect.poll(() => psql(`select count(*) from cart_checkout_cart where session_token = '${second}'`)).toBe('1');
    const secondId = psql(`select id from cart_checkout_cart where session_token = '${second}'`);
    await view.locator('[data-testid=cart-checkout-carts-search] input').fill(first.split('-').slice(2).join('-'));
    await expect(firstRow).toBeVisible();
    await expect(rowOf(page, 'cart-checkout-carts', secondId)).toHaveCount(0);
    await view.locator('[data-testid=cart-checkout-carts-search] input').fill('');

    // Abandon the first: it stays, Abandoned, and no longer offers Abandon.
    await rowAction(page, 'cart-checkout-carts', firstId, 'abandon');
    await expect(firstRow).toContainText('Abandoned');
    expect(psql(`select status from cart_checkout_cart where id = '${firstId}'`)).toBe('abandoned');
    await expect(view.locator(`[data-testid=cart-checkout-carts-row-${firstId}-abandon]:visible`)).toHaveCount(0);

    // Delete the second after confirming: it leaves the list.
    await rowAction(page, 'cart-checkout-carts', secondId, 'delete');
    const confirm = page.locator('ion-modal.ep-form-modal').filter({ hasText: `Delete the cart ${second}?` });
    await expect(confirm).toBeVisible();
    await page.screenshot({ path: shot('cart-checkout-delete-desktop') });
    await confirm.locator('.ep-form-modal__submit').click();
    await expect(confirm).toBeHidden();
    await expect(rowOf(page, 'cart-checkout-carts', secondId)).toHaveCount(0);
    expect(psql(`select deleted_at is not null from cart_checkout_cart where id = '${secondId}'`)).toBe('t');
    await page.screenshot({ path: shot('cart-checkout-carts-desktop') });
  } finally {
    await context.close();
  }
});

test('Orders: mark paid and complete one (its cart converts), fail another with its reason, search', async ({ browser }) => {
  const { context, page } = await pageAs(browser, '/cart_checkout/orders');
  try {
    const paid = await orderFrom(context, code('paid'), 1250);
    const failed = await orderFrom(context, code('fail'), 400);
    expect(paid.number).toMatch(/^OS-\d{8}-\d{4}$/);

    const view = shown(page);
    const paidRow = rowOf(page, 'cart-checkout-orders', paid.id);
    await expect(paidRow).toContainText(paid.number);
    await expect(paidRow).toContainText('Initiated');
    await expect(paidRow).toContainText('€25.00');

    // Mark paid, then Complete: each row offers only its next step.
    await rowAction(page, 'cart-checkout-orders', paid.id, 'pay');
    await expect(paidRow).toContainText('Paid');
    await expect(view.locator(`[data-testid=cart-checkout-orders-row-${paid.id}-pay]:visible`)).toHaveCount(0);
    await rowAction(page, 'cart-checkout-orders', paid.id, 'complete');
    await expect(paidRow).toContainText('Completed');
    expect(psql(`select c.status from cart_checkout_cart c join cart_checkout_order o on o.cart_id = c.id where o.id = '${paid.id}'`)).toBe(
      'converted',
    );

    // Fail the other: the form needs the reason, and the row shows it.
    await rowAction(page, 'cart-checkout-orders', failed.id, 'fail');
    await expect(page.locator('[data-testid=cart-checkout-fail-submit]')).toHaveAttribute('aria-disabled', 'true');
    await page.locator('[data-testid=cart-checkout-fail-reason] textarea').fill('Card declined');
    await page.screenshot({ path: shot('cart-checkout-fail-desktop'), animations: 'disabled' });
    await page.locator('[data-testid=cart-checkout-fail-submit]').click();
    const failedRow = rowOf(page, 'cart-checkout-orders', failed.id);
    await expect(failedRow).toContainText('Failed');
    await expect(failedRow).toContainText('Reason: Card declined');

    // A piece of the number finds the order.
    await view.locator('[data-testid=cart-checkout-orders-search] input').fill(paid.number);
    await expect(paidRow).toBeVisible();
    await expect(failedRow).toHaveCount(0);
    await page.screenshot({ path: shot('cart-checkout-orders-desktop') });
  } finally {
    await context.close();
  }
});

test('The three viewports of both screens', async ({ browser }) => {
  for (const [name, viewport] of Object.entries(VIEWPORTS)) {
    const { context, page } = await pageAs(browser, '/cart_checkout/carts', viewport);
    try {
      let view = shown(page);
      await view.locator('[data-testid=cart-checkout-carts-empty], [data-testid=cart-checkout-carts-row]').first().waitFor({ state: 'visible' });
      await expect(view.locator('[data-testid=cart-checkout-carts-add]')).toBeVisible();
      await page.screenshot({ path: shot(`cart-checkout-carts-${name}`) });
      await page.goto(`${A}/cart_checkout/orders`);
      view = shown(page);
      await view.locator('[data-testid=cart-checkout-orders-empty], [data-testid=cart-checkout-orders-row]').first().waitFor({ state: 'visible' });
      await page.screenshot({ path: shot(`cart-checkout-orders-${name}`) });
    } finally {
      await context.close();
    }
  }
});

test('An employee only looks: no New cart, no row action', async ({ browser }) => {
  const { context, page } = await pageAs(browser, '/cart_checkout/carts', VIEWPORTS.desktop, true);
  try {
    const view = shown(page);
    await view.locator('[data-testid=cart-checkout-carts-empty], [data-testid=cart-checkout-carts-row]').first().waitFor({ state: 'visible' });
    await expect(view.locator('[data-testid=cart-checkout-carts-add]')).toHaveCount(0);
    await expect(view.locator('[data-testid$=-abandon]:visible, [data-testid$=-delete]:visible')).toHaveCount(0);
    await page.goto(`${A}/cart_checkout/orders`);
    const orders = shown(page);
    await orders.locator('[data-testid=cart-checkout-orders-empty], [data-testid=cart-checkout-orders-row]').first().waitFor({ state: 'visible' });
    await expect(orders.locator('[data-testid$=-pay]:visible, [data-testid$=-complete]:visible, [data-testid$=-fail]:visible')).toHaveCount(0);
    await page.screenshot({ path: shot('cart-checkout-employee') });
  } finally {
    await context.close();
  }
});
