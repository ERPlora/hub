// The cart_checkout app's entries of the hub's op → route map (`frontend/generated/operations.json`),
// which the SDK's API client uses: the nineteen operations of apps/cart_checkout/api.py, queries by GET
// and commands by POST, one input each (no path parameters). tests/test_api.py pins the same routes on
// the server.
import { describe, expect, it } from 'vitest';

import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';

const ROUTES = {
  'cart_checkout.cart.list': { method: 'get', path: '/api/cart_checkout/carts' },
  'cart_checkout.cart.get': { method: 'get', path: '/api/cart_checkout/carts/detail' },
  'cart_checkout.cart.create': { method: 'post', path: '/api/cart_checkout/carts' },
  'cart_checkout.cart.mark_abandoned': { method: 'post', path: '/api/cart_checkout/carts/mark_abandoned' },
  'cart_checkout.cart.delete': { method: 'post', path: '/api/cart_checkout/carts/delete' },
  'cart_checkout.cart.clear': { method: 'post', path: '/api/cart_checkout/carts/clear' },
  'cart_checkout.cart.cleanup_expired': { method: 'post', path: '/api/cart_checkout/carts/cleanup_expired' },
  'cart_checkout.item.list': { method: 'get', path: '/api/cart_checkout/items' },
  'cart_checkout.item.get': { method: 'get', path: '/api/cart_checkout/items/detail' },
  'cart_checkout.item.add': { method: 'post', path: '/api/cart_checkout/items' },
  'cart_checkout.item.update': { method: 'post', path: '/api/cart_checkout/items/update' },
  'cart_checkout.item.remove': { method: 'post', path: '/api/cart_checkout/items/remove' },
  'cart_checkout.checkout.initiate': { method: 'post', path: '/api/cart_checkout/checkout/initiate' },
  'cart_checkout.order.list': { method: 'get', path: '/api/cart_checkout/orders' },
  'cart_checkout.order.get': { method: 'get', path: '/api/cart_checkout/orders/detail' },
  'cart_checkout.order.mark_paid': { method: 'post', path: '/api/cart_checkout/orders/mark_paid' },
  'cart_checkout.order.fail': { method: 'post', path: '/api/cart_checkout/orders/fail' },
  'cart_checkout.order.complete': { method: 'post', path: '/api/cart_checkout/orders/complete' },
  'cart_checkout.customer.erase': { method: 'post', path: '/api/cart_checkout/customers/erase' },
} as const;

describe('cart_checkout routes in the op → route map', () => {
  it('binds its nineteen operations: queries by GET, commands by POST', () => {
    const own = Object.fromEntries(Object.entries(OPERATION_ROUTES).filter(([op]) => op.startsWith('cart_checkout.')));
    expect(own).toEqual(ROUTES);
  });
});
