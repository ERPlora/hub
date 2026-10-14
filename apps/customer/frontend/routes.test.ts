// The customer app's `routes.ts`: routes → pages and nothing else (main.ts reads the default export).
// The four sections of the product (Customers, Groups, Tags, Fields: apps.py `navigation`) and the
// card; plus, on the dev server only, the preview page of the till's customer search.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

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

  // Importing every page (and Ionic with them) takes a few seconds on a cold run.
  it('loads each page on demand (one chunk per page), not at boot', { timeout: 30_000 }, async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(route('/customer/customers'))).toBe((await import('./pages/CustomerListPage.vue')).default);
    expect(await load(route('/customer/customers/:id'))).toBe((await import('./pages/CustomerDetailPage.vue')).default);
    expect(await load(route('/customer/groups'))).toBe((await import('./pages/GroupListPage.vue')).default);
    expect(await load(route('/customer/tags'))).toBe((await import('./pages/TagListPage.vue')).default);
    expect(await load(route('/customer/fields'))).toBe((await import('./pages/FieldListPage.vue')).default);
    expect(await load(route('/customer/preview/customer-search'))).toBe(
      (await import('./pages/CustomerSearchPreviewPage.vue')).default,
    );
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
