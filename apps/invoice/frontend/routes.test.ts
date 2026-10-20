// The invoice app's `routes.ts`: its three sections and the detail of an invoice → their pages, behind a
// session, and nothing else (main.ts reads the default export; menu, permissions and active apps come from
// the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand, not
// the page (its own tests mount it). A real page brings its whole graph (Ionic, @erplora/ui): over a
// second idle and past Vitest's 5 s on a loaded machine. A real page where a stub is expected is a page
// this file does not stub.
vi.mock('./pages/InvoicesPage.vue', () => ({ default: { name: 'InvoicesPage' } }));
vi.mock('./pages/InvoiceDetailPage.vue', () => ({ default: { name: 'InvoiceDetailPage' } }));
vi.mock('./pages/SeriesPage.vue', () => ({ default: { name: 'SeriesPage' } }));
vi.mock('./pages/IssuerPage.vue', () => ({ default: { name: 'IssuerPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('invoice routes.ts', () => {
  it('maps Invoices, the detail of one, Series and Issuer, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth, r.props ?? false])).toEqual([
      ['/invoice/invoices', true, false],
      ['/invoice/invoices/:id', true, true],
      ['/invoice/series', true, false],
      ['/invoice/issuer', true, false],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(routes[0])).toEqual({ name: 'InvoicesPage' });
    expect(await load(routes[1])).toEqual({ name: 'InvoiceDetailPage' });
    expect(await load(routes[2])).toEqual({ name: 'SeriesPage' });
    expect(await load(routes[3])).toEqual({ name: 'IssuerPage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('has a page for every entry of the navigation of apps.py', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/Nav\(.*"(\/invoice\/[a-z]+)"\)/g)].map((m) => m[1]);
    expect(paths).toEqual(['/invoice/invoices', '/invoice/series', '/invoice/issuer']);
    for (const path of paths) expect(routes.some((r) => r.path === path), path).toBe(true);
  });
});
