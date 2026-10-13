// The demo's `routes.ts`: its four routes → pages and nothing else (main.ts reads the default export).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import routes from './routes';

const HERE = dirname(fileURLToPath(import.meta.url));

function route(path: string): RouteRecordRaw {
  const found = routes.find((r) => r.path === path);
  if (!found) throw new Error(`no route ${path}`);
  return found;
}

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('demo routes.ts', () => {
  it('maps the list, «new», the detail and its edit page, all behind a session; «new» before `:id`', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/demo/items', true],
      ['/demo/items/new', true],
      ['/demo/items/:id', true],
      ['/demo/items/:id/edit', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(route('/demo/items'))).toBe((await import('./pages/ItemListPage.vue')).default);
    expect(await load(route('/demo/items/new'))).toBe((await import('./pages/ItemCreatePage.vue')).default);
    expect(await load(route('/demo/items/:id'))).toBe((await import('./pages/ItemDetailPage.vue')).default);
    expect(await load(route('/demo/items/:id/edit'))).toBe((await import('./pages/ItemEditPage.vue')).default);
  });

  it('hands the item id to the detail and edit pages as a prop (Ionic keeps one view per URL)', () => {
    expect(route('/demo/items/:id').props).toBe(true);
    expect(route('/demo/items/:id/edit').props).toBe(true);
    expect(route('/demo/items/new').props).toBeUndefined();
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});
