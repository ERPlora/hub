// The demo's `routes.ts`: its four routes → pages and nothing else (main.ts reads the default export).
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
vi.mock('./pages/ItemListPage.vue', () => ({ default: { name: 'ItemListPage' } }));
vi.mock('./pages/ItemCreatePage.vue', () => ({ default: { name: 'ItemCreatePage' } }));
vi.mock('./pages/ItemDetailPage.vue', () => ({ default: { name: 'ItemDetailPage' } }));
vi.mock('./pages/ItemEditPage.vue', () => ({ default: { name: 'ItemEditPage' } }));

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
    expect(await load(route('/demo/items'))).toEqual({ name: 'ItemListPage' });
    expect(await load(route('/demo/items/new'))).toEqual({ name: 'ItemCreatePage' });
    expect(await load(route('/demo/items/:id'))).toEqual({ name: 'ItemDetailPage' });
    expect(await load(route('/demo/items/:id/edit'))).toEqual({ name: 'ItemEditPage' });
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
