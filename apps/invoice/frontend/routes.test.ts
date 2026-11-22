// The invoice app's `routes.ts`: its three sections and the detail of an invoice → their pages, behind a
// session, and nothing else (main.ts reads the default export; menu, permissions and active apps come from
// the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/InvoicesPage.vue', () => ({ default: { name: 'InvoicesPage' } }));
vi.mock('./pages/InvoiceDetailPage.vue', () => ({ default: { name: 'InvoiceDetailPage' } }));
vi.mock('./pages/SeriesPage.vue', () => ({ default: { name: 'SeriesPage' } }));
vi.mock('./pages/IssuerPage.vue', () => ({ default: { name: 'IssuerPage' } }));
vi.mock('./pages/PublicInvoicePage.vue', () => ({ default: { name: 'PublicInvoicePage' } }));

describe('invoice routes.ts', () => {
  it('maps the invoice pages and the public ticket page without a session or shell chrome', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth, r.meta?.chrome ?? true, r.props ?? false])).toEqual([
      ['/invoice/invoices', true, true, false],
      ['/invoice/invoices/:id', true, true, true],
      ['/invoice/series', true, true, false],
      ['/invoice/issuer', true, true, false],
      ['/p/:slug/invoice/:code', false, false, false],
    ]);
  });

  routeChecks(import.meta.url, routes, ['InvoicesPage', 'InvoiceDetailPage', 'SeriesPage', 'IssuerPage', 'PublicInvoicePage']);

  it('has a page for every entry of the navigation of apps.py', () => {
    const paths = menuPaths('invoice');
    expect(paths).toEqual(['/invoice/invoices', '/invoice/series', '/invoice/issuer']);
    for (const path of paths) expect(routes.some((r) => r.path === path), path).toBe(true);
  });
});
