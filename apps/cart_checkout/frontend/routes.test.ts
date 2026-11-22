// The cart_checkout app's `routes.ts`: its two sections → their pages, behind a session, and nothing else
// (main.ts reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, namedPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/CartsPage.vue', () => ({ default: { name: 'CartsPage' } }));
vi.mock('./pages/OrdersPage.vue', () => ({ default: { name: 'OrdersPage' } }));

describe('cart_checkout routes.ts', () => {
  it('maps Carts and Orders, both behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/cart_checkout/carts', true],
      ['/cart_checkout/orders', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['CartsPage', 'OrdersPage']);

  it('has a page for every entry of its menu (its tabs), and every path apps.py names is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(menuPaths('cart_checkout'));
    expect(namedPaths('cart_checkout').filter((path) => !routes.some((r) => r.path === path))).toEqual([]);
  });
});
