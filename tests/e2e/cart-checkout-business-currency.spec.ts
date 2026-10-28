// flow: cart-checkout-business-currency (FIX-HUB-CART_CHECKOUT-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/cart_checkout/WORKBOOK.md
// «Carritos», CART_CHECKOUT-F01 and CART_CHECKOUT-F12)
// Cart & Checkout works in the business's currency: its country's, as erplora.com registered it (`PUT /internal/hubs/{id}`,
// signed the way the SaaS sends it), never a fixed euro. Against the real stack, no mocks: a cart of the run is created
// while hub `a` is in Spain (euros) and gets its order; then `a` moves to Poland. In 390, 834 and 1440 a cart created
// from Carts → «New cart» is born in złoty, its line and its total read in złoty while the Spanish cart keeps its euros
// (a record is never rewritten), «Total from» is read in złoty («20 zł» leaves the Polish cart, not the Spanish one), and
// in Orders its order reads in złoty beside the Spanish order in euros (captures
// `FIX-HUB-CART_CHECKOUT-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>` and `…-orders-<width>`). Back in Spain a new cart is
// born in euros and the Polish ones keep their złoty (`…-es-1440`). Everything carries the session prefix «e2e-cc» and is
// deleted before and after the run, and `a`'s registration is put back, also when a test fails.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { type Cart, cleanUp, code, FLOW_VIEWPORTS, listShown, type Order, post, rowOf, signedIn } from './cart-checkout-helpers';

const KEY = 'FIX-HUB-CART_CHECKOUT-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
/** One line of 2 × 12,50 in złoty, as a till in Poland writes it in English: «zł 25.00». */
const ZLOTY_25 = /zł\s?25\.00/;
const ZLOTY_0 = /zł\s?0\.00/;
/** The Spanish cart's line: 1 × 12,50 €. */
const EUROS_12 = /€12\.50/;

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
/** The cart and order created while the business was in Spain. */
const spanish = { cart: '', order: '' };

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

const currencyOf = (id: string): string => psql(`select currency from cart_checkout_cart where id = '${id}'`);

/** «New cart» from Carts with session `session`; returns the new cart's id. */
async function newCart(page: Page, session: string): Promise<string> {
  await shown(page).locator('[data-testid=cart-checkout-carts-add]').click();
  await page.locator('[data-testid=cart-checkout-cart-form-session] input').fill(session);
  await page.locator('[data-testid=cart-checkout-cart-form-submit]').click();
  await expect(page.locator('[data-testid=cart-checkout-cart-form-submit]')).toBeHidden();
  await expect.poll(() => psql(`select count(*) from cart_checkout_cart where session_token = '${session}'`)).toBe('1');
  return psql(`select id from cart_checkout_cart where session_token = '${session}'`);
}

/** «Total from» `value` in the funnel's panel, applied («` `» clears it). */
async function totalFrom(page: Page, value: string): Promise<void> {
  const view = shown(page);
  const panel = view.locator('[data-testid=cart-checkout-carts-filters-panel]');
  if (!(await panel.isVisible())) await view.locator('[data-testid=cart-checkout-carts-filters-toggle]').click();
  await panel.locator('[data-testid=cart-checkout-carts-filter-total_amount_from] input').fill(value);
  await view.locator('[data-testid=cart-checkout-carts-filters-apply]').click();
  await expect(panel).toBeHidden();
}

/** Waits until no modal or popover is moving and nothing scrolls sideways, then captures `name`. */
async function capture(page: Page, name: string): Promise<void> {
  await page.waitForFunction(() => ((window as unknown as { __overlaysMoving?: number }).__overlaysMoving ?? 0) === 0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(name) });
}

/** A line of `quantity` × 12,50 in the cart with session `session`, through the API (the assistant's path). */
async function lineOf(context: BrowserContext, session: string, quantity: string): Promise<void> {
  await post(context, '/cart_checkout/items', { session_token: session, product_ref: 'p-1', product_name: 'Champú', quantity, unit_price: 1250 }, 201);
}

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanUp();
  await registerBusinessIn(original, 'ES');
  const { context } = await signedIn(browser, '/cart_checkout/carts');
  try {
    // Created while the business is in Spain, without a currency: the cart and its order keep the euro.
    const session = code('es');
    const cart = await post<Cart>(context, '/cart_checkout/carts', { session_token: session, customer_email: 'ana@example.com' }, 201);
    expect(cart.currency).toBe('EUR');
    await lineOf(context, session, '1');
    spanish.cart = cart.id;
    spanish.order = (await post<Order>(context, '/cart_checkout/checkout/initiate', { session_token: session }, 201)).id;
  } finally {
    await context.close();
  }
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanUp();
});

for (const [width, viewport] of Object.entries(FLOW_VIEWPORTS)) {
  test(`${KEY}: cart-checkout-business-currency a business in Poland creates, reads and filters its carts and orders in złoty at ${width} wide`, async ({
    browser,
  }) => {
    await registerBusinessIn(original, 'PL');
    const { context, page } = await signedIn(browser, '/cart_checkout/carts', viewport);
    try {
      // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
      await listShown(page, 'cart-checkout-carts');
      const session = code(`pl-${width}`);
      const id = await newCart(page, session);
      expect(currencyOf(id), 'a cart created from the screen is born in the business’s currency').toBe('PLN');
      const polish = rowOf(page, 'cart-checkout-carts', id);
      await expect(polish).toContainText(ZLOTY_0);

      await lineOf(context, session, '2');
      await expect(polish).toContainText(ZLOTY_25);
      await expect(polish).not.toContainText('€');
      // Created in Spain: it stays in euros.
      const older = rowOf(page, 'cart-checkout-carts', spanish.cart);
      await expect(older).toContainText(EUROS_12);
      await expect(older).not.toContainText('zł');

      // «Total from» is typed in złoty, with its symbol: «20 zł» leaves the Polish cart (25) and not the Spanish one (12,50).
      await totalFrom(page, '20 zł');
      await expect(polish).toBeVisible();
      await expect(older).toHaveCount(0);
      await capture(page, `${KEY}-${width}`);
      await totalFrom(page, '');
      await expect(older).toBeVisible();

      // Its order, started through the API, reads in złoty in Orders; the Spanish one keeps its euros.
      const order = await post<Order>(context, '/cart_checkout/checkout/initiate', { session_token: session, customer_email: 'jan@example.com' }, 201);
      expect(order.currency).toBe('PLN');
      await page.goto(`${A}/cart_checkout/orders`);
      await listShown(page, 'cart-checkout-orders');
      const polishOrder = rowOf(page, 'cart-checkout-orders', order.id);
      await expect(polishOrder).toContainText(ZLOTY_25);
      await expect(polishOrder).not.toContainText('€');
      await expect(rowOf(page, 'cart-checkout-orders', spanish.order)).toContainText(EUROS_12);
      await capture(page, `${KEY}-orders-${width}`);
    } finally {
      await context.close();
    }
  });
}

test(`${KEY}: cart-checkout-business-currency back in Spain a new cart is born in euros and the Polish ones keep their złoty`, async ({ browser }) => {
  await registerBusinessIn(original, 'ES');
  const { context, page } = await signedIn(browser, '/cart_checkout/carts');
  try {
    await listShown(page, 'cart-checkout-carts');
    const id = await newCart(page, code('es-again'));
    expect(currencyOf(id)).toBe('EUR');
    await expect(rowOf(page, 'cart-checkout-carts', id)).toContainText('€0.00');
    const polish = psql(`select id from cart_checkout_cart where session_token like 'e2e-cc-pl-1440-%'`);
    await expect(rowOf(page, 'cart-checkout-carts', polish)).toContainText(ZLOTY_25);
    await capture(page, `${KEY}-es-1440`);
  } finally {
    await context.close();
  }
});
