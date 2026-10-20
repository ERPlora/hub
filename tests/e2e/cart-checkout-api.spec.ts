// Cart & Checkout's flows without a screen, through the hub's real API as the owner (the assistant and the
// integrations call the same operations; the screens have no form for them, WORKBOOK «Pantallas»): add
// lines to a cart named by its customer or its session, change and remove them, empty it, start an order
// from it, and erase a customer's personal data. Every change leaves its event in the outbox in its own
// transaction, and a refused one leaves neither the change nor the event. An employee reads and changes
// nothing. Everything carries the session prefix «e2e-cc» and is removed before and after it.
// flow: CART_CHECKOUT-F02 CART_CHECKOUT-F03 CART_CHECKOUT-F04 CART_CHECKOUT-F08 CART_CHECKOUT-F13 CART_CHECKOUT-F14
import { expect, test } from '@playwright/test';

import { A, api, EMPLOYEE, psql } from './helpers';
import {
  type Cart,
  cleanUp,
  code,
  eventsAbout,
  get,
  type LineChange,
  type Order,
  post,
  signedIn,
  VIEWPORTS,
} from './cart-checkout-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

type Refusal = { error: { code: string; message: string; fields?: Record<string, string> } };

const LINE = { product_ref: 'p-1', product_name: 'Champú', unit_price: 1250 };

test('CART_CHECKOUT-F02 to F04, F08, F13 and F14 through the API, as the assistant does', async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const name = `Marta Ruiz ${stamp}`;
  const email = `marta.${stamp}@example.com`;
  const session = code('api');
  const { context, page } = await signedIn(browser, '/cart_checkout/carts');
  try {
    const refused = async (path: string, body: unknown, status: number) => {
      const res = await api<Refusal>(context, A, 'POST', path, body);
      expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
      return res.data.error;
    };
    const cart = await post<Cart>(context, '/cart_checkout/carts', { session_token: session, customer_email: email, customer_name: name }, 201);
    let lines: LineChange[] = [];

    await test.step('CART_CHECKOUT-F02 add lines to the cart named by its customer or its session', async () => {
      // By a piece of the customer's name, as the assistant hears it: 0,5 × 19,99 € is 10,00 € (half up).
      const half = await post<LineChange>(
        context,
        '/cart_checkout/items',
        { ...LINE, customer: name.split(' ').slice(1).join(' '), sku: 'SH-1', quantity: '0.5', unit_price: 1999, variant_attributes: { size: '250 ml' } },
        201,
      );
      expect([half.item?.line_total, half.cart.id, half.cart.total_amount, Number(half.cart.total_items)]).toEqual([1000, cart.id, 1000, 0.5]);
      const two = await post<LineChange>(context, '/cart_checkout/items', { ...LINE, session_token: session, quantity: '2' }, 201);
      expect([two.item?.line_total, two.cart.total_amount, Number(two.cart.total_items)]).toEqual([2500, 3500, 2.5]);
      lines = [half, two];

      // Refused under their field, and nothing is stored: no quantity, a negative price, an unknown cart.
      expect((await refused('/cart_checkout/items', { ...LINE, session_token: session, quantity: '0' }, 422)).fields).toHaveProperty('quantity');
      expect((await refused('/cart_checkout/items', { ...LINE, session_token: session, quantity: '1', unit_price: -1 }, 422)).fields).toHaveProperty('unit_price');
      expect((await refused('/cart_checkout/items', { ...LINE, session_token: code('nobody'), quantity: '1' }, 404)).code).toBe('cart_checkout.cart_not_found');
      const read = await get<{ rows: { id: string }[]; total: number }>(context, `/cart_checkout/items?session_token=${session}`);
      expect(read.rows.map((row) => row.id)).toEqual(lines.map((line) => line.item?.id));
    });

    await test.step('CART_CHECKOUT-F03 change a quantity with the price kept on the line, or remove the line', async () => {
      const [half, two] = lines;
      const three = await post<LineChange>(context, '/cart_checkout/items/update', { item_id: two.item?.id, quantity: '3' });
      expect([three.item?.unit_price, three.item?.line_total, three.cart.total_amount]).toEqual([1250, 3750, 4750]);
      // The price is the line's: whoever calls cannot send another one.
      expect((await refused('/cart_checkout/items/update', { item_id: two.item?.id, quantity: '1', unit_price: 1 }, 422)).code).toBe('invalid_payload');
      const zero = await post<LineChange>(context, '/cart_checkout/items/update', { item_id: half.item?.id, quantity: '0' });
      expect([zero.removed, zero.item, zero.cart.total_amount]).toEqual([true, null, 3750]);
      const gone = await post<LineChange>(context, '/cart_checkout/items/remove', { item_id: two.item?.id });
      expect([gone.removed, gone.cart.total_amount, Number(gone.cart.total_items)]).toEqual([true, 0, 0]);
      expect((await refused('/cart_checkout/items/remove', { item_id: two.item?.id }, 404)).code).toBe('cart_checkout.item_not_found');
    });

    await test.step('CART_CHECKOUT-F04 empty the cart: it stays active with its totals at zero', async () => {
      await post(context, '/cart_checkout/items', { ...LINE, session_token: session, quantity: '1' }, 201);
      await post(context, '/cart_checkout/items', { ...LINE, session_token: session, quantity: '2' }, 201);
      const cleared = await post<Cart>(context, '/cart_checkout/carts/clear', { session_token: session });
      expect([cleared.status, cleared.total_amount, Number(cleared.total_items)]).toEqual(['active', 0, 0]);
      expect((await get<{ total: number }>(context, `/cart_checkout/items?session_token=${session}`)).total).toBe(0);
      // Emptying an empty cart changes nothing and says nothing.
      await post(context, '/cart_checkout/carts/clear', { session_token: session });
      expect(eventsAbout(cart.id).filter((event) => event === 'cart_checkout.cart.cleared')).toHaveLength(1);
    });

    const anon = code('anon');
    let order: Order | undefined;
    await test.step('CART_CHECKOUT-F08 start an order from a cart: its number of the day, no gap after a refusal', async () => {
      await post(context, '/cart_checkout/carts', { session_token: anon }, 201);
      // An empty cart, or one without any email, makes no order and spends no number.
      expect((await refused('/cart_checkout/checkout/initiate', { session_token: anon, customer_email: 'x@example.com' }, 409)).code).toBe('cart_checkout.cart_empty');
      await post(context, '/cart_checkout/items', { ...LINE, session_token: anon, quantity: '2' }, 201);
      expect((await refused('/cart_checkout/checkout/initiate', { session_token: anon }, 422)).fields).toHaveProperty('customer_email');
      const address = { line1: 'Calle Mayor 1', city: 'Madrid', postal_code: '28013' };
      order = await post<Order>(
        context,
        '/cart_checkout/checkout/initiate',
        { session_token: anon, customer_email: 'x@example.com', shipping_address: address, shipping_method: 'Courier', payment_method: 'Transfer', notes: 'At the door' },
        201,
      );
      expect(order.order_number).toMatch(/^OS-\d{8}-\d{4}$/);
      expect([order.status, order.total_amount, order.currency, order.billing_address]).toEqual(['initiated', 2500, 'EUR', address]);
      // The cart stays active: another line and another order, the next number of the day.
      await post(context, '/cart_checkout/items', { ...LINE, session_token: anon, quantity: '1' }, 201);
      const next = await post<Order>(context, '/cart_checkout/checkout/initiate', { session_token: anon, customer_email: 'x@example.com' }, 201);
      const number = (text: string) => Number(text.slice(-4));
      expect([next.order_number.slice(0, 12), number(next.order_number)]).toEqual([order.order_number.slice(0, 12), number(order.order_number) + 1]);
      expect(next.total_amount).toBe(3750);
      const read = await get<Order>(context, `/cart_checkout/orders/detail?order_number=${order.order_number}`);
      expect([read.total_amount, read.shipping_address, read.customer_email]).toEqual([2500, address, 'x@example.com']);
    });

    await test.step('CART_CHECKOUT-F13 every change left its event in the outbox, a refused one none', async () => {
      expect(eventsAbout(cart.id)).toEqual([
        'cart_checkout.cart.created',
        'cart_checkout.item.added',
        'cart_checkout.item.added',
        'cart_checkout.item.updated',
        'cart_checkout.item.updated',
        'cart_checkout.item.removed',
        'cart_checkout.item.added',
        'cart_checkout.item.added',
        'cart_checkout.cart.cleared',
      ]);
      const anonId = psql(`select id from cart_checkout_cart where session_token = '${anon}'`);
      expect(eventsAbout(anonId)).toEqual([
        'cart_checkout.cart.created',
        'cart_checkout.item.added',
        'cart_checkout.checkout.initiated',
        'cart_checkout.item.added',
        'cart_checkout.checkout.initiated',
      ]);
      // Its shape: the order's number, its total and its currency; the scope of the hub it happened in.
      const initiated = psql(
        `select payload->>'order_number' || ' ' || (payload->>'total_amount') || ' ' || (payload->>'currency') || ' ' || scope_key from live_outboxevent where name = 'cart_checkout.checkout.initiated' and payload->>'id' = '${order?.id}'`,
      );
      expect(initiated).toBe(`${order?.order_number} 2500 EUR a`);
    });

    await test.step('CART_CHECKOUT-F14 erase a customer’s personal data by their email, whatever its capitals', async () => {
      await post(context, '/cart_checkout/items', { ...LINE, session_token: session, quantity: '1' }, 201);
      const own = await post<Order>(context, '/cart_checkout/checkout/initiate', { session_token: session, shipping_address: { line1: 'Calle Real 2' }, notes: 'Gift' }, 201);
      expect(own.customer_email).toBe(email);
      const before = Number(psql(`select count(*) from live_outboxevent where name = 'cart_checkout.customer.erased'`));
      expect(await post(context, '/cart_checkout/customers/erase', { email: email.toUpperCase() })).toEqual({ carts: 1, orders: 1 });
      expect(psql(`select customer_email || '|' || customer_name || '|' || notes from cart_checkout_cart where id = '${cart.id}'`)).toBe('||');
      expect(psql(`select customer_email || '|' || shipping_address::text || '|' || notes || '|' || order_number from cart_checkout_order where id = '${own.id}'`)).toBe(
        `|{}||${own.order_number}`,
      );
      // How many, never whose: the event outlives the erasure.
      const erased = psql(`select payload::text from live_outboxevent where name = 'cart_checkout.customer.erased' order by created_at desc, id desc limit 1`);
      expect(JSON.parse(erased)).toEqual({ carts: 1, orders: 1 });
      expect(erased).not.toContain(stamp);
      // Nothing left: zero, and no event; an email that is not one, under its field.
      expect(await post(context, '/cart_checkout/customers/erase', { email })).toEqual({ carts: 0, orders: 0 });
      expect(Number(psql(`select count(*) from live_outboxevent where name = 'cart_checkout.customer.erased'`))).toBe(before + 1);
      expect((await refused('/cart_checkout/customers/erase', { email: 'marta' }, 422)).fields).toHaveProperty('email');
    });
  } finally {
    await page.close();
    await context.close();
  }
});

test('An employee reads the carts but changes nothing through the API', async ({ browser }) => {
  const session = code('staff');
  const owner = await signedIn(browser, '/cart_checkout/carts');
  const employee = await signedIn(browser, '/cart_checkout/carts', VIEWPORTS.desktop, EMPLOYEE);
  try {
    await post(owner.context, '/cart_checkout/carts', { session_token: session }, 201);
    expect((await get<{ rows: unknown[] }>(employee.context, `/cart_checkout/carts?session_token=${session}`)).rows).toHaveLength(1);
    for (const [path, body] of [
      ['/cart_checkout/items', { ...LINE, session_token: session, quantity: '1' }],
      ['/cart_checkout/carts/clear', { session_token: session }],
      ['/cart_checkout/checkout/initiate', { session_token: session, customer_email: 'x@example.com' }],
      ['/cart_checkout/customers/erase', { email: 'x@example.com' }],
    ] as const) {
      const res = await api<Refusal>(employee.context, A, 'POST', path, body);
      expect([path, res.status, res.data.error.code]).toEqual([path, 403, 'permission_denied']);
    }
    expect(Number(psql(`select count(*) from cart_checkout_cartitem i join cart_checkout_cart c on c.id = i.cart_id where c.session_token = '${session}'`))).toBe(0);
  } finally {
    await owner.context.close();
    await employee.context.close();
  }
});
