// The payment app's `routes.ts`: its two sections → their pages, behind a session, and nothing else
// (main.ts reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, namedPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/PaymentsPage.vue', () => ({ default: { name: 'PaymentsPage' } }));
vi.mock('./pages/MethodsPage.vue', () => ({ default: { name: 'MethodsPage' } }));

describe('payment routes.ts', () => {
  it('maps Payments and Methods, both behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/payment/payments', true],
      ['/payment/methods', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['PaymentsPage', 'MethodsPage']);

  it('has a page for every entry of its menu (its tabs), and every path apps.py names is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(menuPaths('payment'));
    expect(namedPaths('payment').filter((path) => !routes.some((r) => r.path === path))).toEqual([]);
  });
});
