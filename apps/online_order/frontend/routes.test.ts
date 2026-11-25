// Online orders' `routes.ts`: its one screen, the tables' QR codes, behind a session and loaded on demand, on the path
// of its menu entry in apps.py, and the table's page that its QR opens without a session; nothing else (main.ts reads
// the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { appMenu } from '../../../base/frontend/__tests__/app-menu';
import { routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/QrCodesPage.vue', () => ({ default: { name: 'QrCodesPage' } }));
vi.mock('./pages/TableMenuPage.vue', () => ({ default: { name: 'TableMenuPage' } }));

describe('online_order routes.ts', () => {
  it('maps the tables’ QR codes behind a session and the table’s page without one, without the shell', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth, r.meta?.chrome])).toEqual([
      ['/online_order/qr-codes', true, undefined],
      ['/p/:slug/order/:code', false, false],
    ]);
  });

  routeChecks(import.meta.url, routes, ['QrCodesPage', 'TableMenuPage']);

  it('every menu entry of apps.py has its page, opened by whoever may see the codes', () => {
    expect(appMenu('online_order').map((entry) => [entry.path, entry.permission])).toEqual([
      ['/online_order/qr-codes', 'online_order.view_qr_code'],
    ]);
    for (const entry of appMenu('online_order')) expect(routes.some((r) => r.path === entry.path), entry.path).toBe(true);
  });
});
