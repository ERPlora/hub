// The pricing app's `routes.ts`: its one menu entry (the lists and the rules) and a list's detail → their
// pages, behind a session, and nothing else (main.ts reads the default export; menu, permissions and
// active apps come from the server).
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

describe('pricing routes.ts', () => {
  it('maps the lists and a list’s detail, both behind a session, the id as a prop', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth, r.props ?? false])).toEqual([
      ['/pricing/lists', true, false],
      ['/pricing/lists/:id', true, true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(routes[0])).toBe((await import('./pages/ListsPage.vue')).default);
    expect(await load(routes[1])).toBe((await import('./pages/ListDetailPage.vue')).default);
  }, 30_000);

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('serves the path of the menu entry of apps.py', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/Nav\(.*"(\/pricing\/[a-z]+)"\)/g)].map((m) => m[1]);
    expect(paths).toEqual(['/pricing/lists']);
    expect(routes.map((r) => r.path)).toContain(paths[0]);
  });
});
