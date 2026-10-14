// The inventory's `routes.ts`: one route per tab of the old module (Dashboard, Products, Movements,
// Categories) plus Settings, all behind a session, each page its own chunk; `/inventory` (the
// menu's entry) lands on the dashboard. Routes → pages and nothing else (main.ts reads the default
// export). `PAGES` lists the pages that exist, in tab order: a route never points at a missing page.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import routes from './routes';

const HERE = dirname(fileURLToPath(import.meta.url));

/** Path → page file, in tab order. */
const PAGES: Array<[string, string]> = [
  ['/inventory/dashboard', 'DashboardPage'],
  ['/inventory/products', 'ProductsPage'],
  ['/inventory/movements', 'MovementsPage'],
  ['/inventory/categories', 'CategoriesPage'],
  ['/inventory/settings', 'SettingsPage'],
];

function route(path: string): RouteRecordRaw {
  const found = routes.find((r) => r.path === path);
  if (!found) throw new Error(`no route ${path}`);
  return found;
}

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('inventory routes.ts', () => {
  it('maps each page that exists behind a session, in tab order; /inventory lands on the dashboard once it exists', () => {
    const dashboard = PAGES.some(([path]) => path === '/inventory/dashboard');
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ...(dashboard ? [['/inventory', true]] : []),
      ...PAGES.map(([path]) => [path, true]),
    ]);
    if (dashboard) expect(route('/inventory').redirect).toBe('/inventory/dashboard');
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const [path, page] of PAGES) {
      const r = route(path);
      expect(typeof r.component, path).toBe('function');
      expect(await load(r)).toBe((await import(`./pages/${page}.vue`)).default);
    }
    // The first import of a page compiles Ionic and the shared components cold: well over 5 s on a busy machine.
  }, 60_000);

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});
