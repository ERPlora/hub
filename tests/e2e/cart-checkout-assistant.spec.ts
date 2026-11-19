// The assistant's card for a write of Cart & checkout (BASE-F97): the cart a write acts on by its session code, as the
// Carts list and «Delete the cart …?» name it; a line by its product; an order by its number, as the Orders list —
// never by the id the model sent, and never left out for whoever may read them. End to end with the stack's SaaS gateway and the e2e's
// provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder,
// «El asistente»). The owner, in Spanish, asks to empty a cart (CART_CHECKOUT-F04), to remove one of its lines
// (CART_CHECKOUT-F03) and to mark its order paid (CART_CHECKOUT-F09, dangerous): each card names its record; cancelled,
// nothing changes. What this file creates carries the session prefix of the cart_checkout specs and goes away; the app
// it turns on is turned off again. Each card says what its write does (BASE-F97): emptying a cart «Vaciar», never
// «Quitar», the verb of removing one of its lines.
// flow: cart-checkout-assistant-card
// flow: base-assistant-card-verbs
// flow: CART_CHECKOUT-F03 CART_CHECKOUT-F04 CART_CHECKOUT-F09 BASE-F97
// flow: base-assistant-money-mark
import { writeFileSync } from 'node:fs';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { cardSpec } from './assistant-card-helpers';
import { askForACard, cancelAtComputerSize, cancelInSpanish, captureConfirmation, card, openPanelAtTheDesk, sentCard } from './assistant-panel';
import { type Cart, cleanUp, code, get, type Line, type Order, post } from './cart-checkout-helpers';
import { A, capture, login, shot, THREE_SIZES as VIEWPORTS, untilStill } from './helpers';

const KEY = 'FIX-HUB-CART_CHECKOUT-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
/** The captures of the verb of emptying a cart (base-assistant-card-verbs). */
const VERB_KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-SAYS-REMOVE-FOR-EMPTYING-A-CART';
/** The app the writes need: a business is born with every app off. */
const NEEDED = ['cart_checkout'];
/** The products of the cart, as the person would say them. */
const SHAMPOO = 'Champú de argán';
const MASK = 'Mascarilla nutritiva';

type Detail = Cart & { items: (Line & { product_name: string })[] };


cardSpec(NEEDED, cleanUp);

/** The owner, in Spanish, with a cart of two lines made through the app's API: `[context, page, the cart, its lines]`. */
async function ownerWithACart(browser: import('@playwright/test').Browser): Promise<[BrowserContext, Page, Cart, Line[]]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const cart = await post<Cart>(context, '/cart_checkout/carts', { session_token: code('assistant') }, 201);
  const lines: Line[] = [];
  for (const [ref, name] of [['p-1', SHAMPOO], ['p-2', MASK]]) {
    const added = await post<{ item: Line }>(
      context,
      '/cart_checkout/items',
      { cart_id: cart.id, product_ref: ref, product_name: name, quantity: '1', unit_price: 1250 },
      201,
    );
    lines.push(added.item);
  }
  return [context, page, cart, lines];
}

const detail = (context: BrowserContext, cart: Cart): Promise<Detail> =>
  get<Detail>(context, `/cart_checkout/carts/detail?cart_id=${cart.id}`);

test('cart-checkout-assistant-card, base-assistant-card-verbs — in Spanish emptying a cart says «Vaciar» and names it by its session code, never by its id', async ({ browser }) => {
  const [context, page, cart] = await ownerWithACart(browser);
  await openPanelAtTheDesk(page);
  await askForACard(page, `E2E-ASK cart_checkout__cart__clear ${JSON.stringify({ cart_id: cart.id })}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Vaciar en Carrito y pago: ${cart.session_token}`);
    await expect(card(page)).not.toContainText('Quitar');
    await expect(card(page)).not.toContainText(cart.id);
    await untilStill(page);
    writeFileSync(shot(`${VERB_KEY}-${vp.label}`), await capture(page, `${KEY}-${vp.label}`));
  }
  await cancelAtComputerSize(page);
  expect((await detail(context, cart)).items.map((item) => item.product_name)).toEqual([SHAMPOO, MASK]);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

test('cart-checkout-assistant-card, base-assistant-card-verbs — in Spanish removing a line says «Quitar» and names it by its product, never by its id', async ({ browser }) => {
  const [context, page, cart, [, mask]] = await ownerWithACart(browser);
  await openPanelAtTheDesk(page);
  await askForACard(page, `E2E-ASK cart_checkout__item__remove ${JSON.stringify({ item_id: mask.id })}`);
  await expect(card(page)).toContainText(`Quitar en Carrito y pago: ${MASK}`);
  await expect(card(page)).not.toContainText(mask.id);
  await cancelInSpanish(page);
  expect((await detail(context, cart)).items.map((item) => item.product_name)).toEqual([SHAMPOO, MASK]);
  await context.close();
});

test('cart-checkout-assistant-card — in Spanish marking an order paid names it by its number, never by its id', async ({ browser }) => {
  const [context, page, cart] = await ownerWithACart(browser);
  const order = await post<Order>(
    context,
    '/cart_checkout/checkout/initiate',
    { cart_id: cart.id, customer_email: 'ana@example.com' },
    201,
  );
  expect(order.order_number).toMatch(/^OS-\d{8}-\d{4}$/);
  await openPanelAtTheDesk(page);
  await askForACard(page, `E2E-ASK cart_checkout__order__mark_paid ${JSON.stringify({ order_id: order.id })}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Pedido: ${order.order_number}`);
    await expect(card(page)).not.toContainText(order.id);
    await captureConfirmation(page, `${KEY}-order-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  const after = await get<Order>(context, `/cart_checkout/orders/detail?order_id=${order.id}`);
  expect(after.status).toBe('initiated');
  await context.close();
});

// flow: base-assistant-money-mark (BASE-F97)
// A line added to a cart in dollars must not read «12,50 €»: the write names the cart, not its currency. The card
// reads the cart as the person and sends the price in its currency,
// with its decimals (none in yen), as Shopify or Stripe show it. A normal card says its first three data in one line and
// the price is the sixth: the screen that shows every datum (an automation's question, FLOW-F29) gets it from what the
// server sends, checked here as it arrives. Cancelled: nothing is added.
test('base-assistant-money-mark — in Spanish a line added to a cart in another currency carries its price in it', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const dollars = await post<Cart>(context, '/cart_checkout/carts', { session_token: code('usd'), currency: 'USD' }, 201);
  const yen = await post<Cart>(context, '/cart_checkout/carts', { session_token: code('jpy'), currency: 'JPY' }, 201);
  const line = { product_ref: 'p-3', product_name: MASK, quantity: '1', unit_price: 1250 };
  await openPanelAtTheDesk(page);
  for (const [cart, money] of [
    [dollars, { currency: 'USD', decimals: 2 }],
    [yen, { currency: 'JPY', decimals: 0 }],
  ] as const) {
    const sent = sentCard(page);
    await askForACard(page, `E2E-ASK cart_checkout__item__add ${JSON.stringify({ cart_id: cart.id, ...line })}`);
    await expect(card(page)).toContainText(`Añadir en Carrito y pago: ${cart.session_token}`);
    expect((await sent).fields.find((field) => field.name === 'unit_price')).toMatchObject({ kind: 'money', value: 1250, money });
    await cancelInSpanish(page);
  }
  for (const cart of [dollars, yen]) expect((await detail(context, cart)).items).toEqual([]);
  await context.close();
});
