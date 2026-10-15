// The combo app's `routes.ts`: Menus and the builder of a menu, behind a session, and nothing else
// (main.ts reads the default export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import routes from './routes';

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('combo routes.ts', () => {
  it('maps Menus and the builder of one menu (its id as a prop), both behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth, Boolean(r.props)])).toEqual([
      ['/combo/menus', true, false],
      ['/combo/menus/:id', true, true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', { timeout: 60_000 }, async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    const pages = await Promise.all(routes.map(load));
    expect(pages).toEqual([(await import('./pages/MenusPage.vue')).default, (await import('./pages/MenuBuilderPage.vue')).default]);
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('has a page for the one menu entry of apps.py', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/"(\/combo\/[a-z-]+)"/g)].map((m) => m[1]);
    expect(paths).toEqual(['/combo/menus']);
    expect(paths.every((path) => routes.some((r) => r.path === path))).toBe(true);
  });
});
