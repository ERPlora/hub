// The customer app's `routes.ts`: routes → pages and nothing else (main.ts reads the default export).
// The four sections of the product (Customers, Groups, Tags, Fields: apps.py `navigation`) and the
// card; plus, on the dev server only, the preview page of the till's customer search.
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
vi.mock('./pages/CustomerListPage.vue', () => ({ default: { name: 'CustomerListPage' } }));
vi.mock('./pages/CustomerDetailPage.vue', () => ({ default: { name: 'CustomerDetailPage' } }));
vi.mock('./pages/GroupListPage.vue', () => ({ default: { name: 'GroupListPage' } }));
vi.mock('./pages/TagListPage.vue', () => ({ default: { name: 'TagListPage' } }));
vi.mock('./pages/FieldListPage.vue', () => ({ default: { name: 'FieldListPage' } }));
vi.mock('./pages/CustomerSearchPreviewPage.vue', () => ({ default: { name: 'CustomerSearchPreviewPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, 'routes.ts'), 'utf8');
const APPS_PY = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');

function route(path: string): RouteRecordRaw {
  const found = routes.find((r) => r.path === path);
  if (!found) throw new Error(`no route ${path}`);
  return found;
}

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('customer routes.ts', () => {
  it('maps the list, the card, groups, tags and fields, all behind a session (and the preview in dev)', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/customer/customers', true],
      ['/customer/customers/:id', true],
      ['/customer/groups', true],
      ['/customer/tags', true],
      ['/customer/fields', true],
      ['/customer/preview/customer-search', true],
    ]);
  });

  it('every menu entry of apps.py has its page', () => {
    const menu = [...APPS_PY.matchAll(/path="([^"]+)"/g)].map((m) => m[1]);
    expect(menu).toEqual(['/customer/customers', '/customer/groups', '/customer/tags', '/customer/fields']);
    for (const path of menu) expect(routes.some((r) => r.path === path), path).toBe(true);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(route('/customer/customers'))).toEqual({ name: 'CustomerListPage' });
    expect(await load(route('/customer/customers/:id'))).toEqual({ name: 'CustomerDetailPage' });
    expect(await load(route('/customer/groups'))).toEqual({ name: 'GroupListPage' });
    expect(await load(route('/customer/tags'))).toEqual({ name: 'TagListPage' });
    expect(await load(route('/customer/fields'))).toEqual({ name: 'FieldListPage' });
    expect(await load(route('/customer/preview/customer-search'))).toEqual({ name: 'CustomerSearchPreviewPage' });
  });

  it('hands the customer id to the card as a prop (Ionic keeps one view per URL)', () => {
    expect(route('/customer/customers/:id').props).toBe(true);
    expect(route('/customer/customers').props).toBeUndefined();
  });

  it('serves the preview of the till search on the dev server only, never in a production build', async () => {
    vi.stubEnv('DEV', false);
    vi.resetModules();
    try {
      const production = (await import('./routes')).default;
      expect(production.map((r) => r.path)).toEqual([
        '/customer/customers',
        '/customer/customers/:id',
        '/customer/groups',
        '/customer/tags',
        '/customer/fields',
      ]);
    } finally {
      vi.unstubAllEnvs();
      vi.resetModules();
    }
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    expect([...SOURCE.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});
