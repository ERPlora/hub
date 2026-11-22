// What the test of every app's `routes.ts` checks the same way: that each route loads its page on demand, one chunk per
// page; that the file imports types only, because `main.ts` globs it eagerly and Vite hoists that glob above the
// shell's boot hooks; and that its paths are those apps.py names.
//
// The test stubs its pages (`vi.mock('./pages/<Page>.vue', () => ({ default: { name: '<Page>' } }))`): it checks which
// page each route loads, not the page, which its own tests mount. A real page brings its whole graph (Ionic,
// @erplora/ui): over a second idle and past Vitest's 5 s on a loaded machine. A real page where a stub is expected is a
// page the test does not stub.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, it } from 'vitest';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';

import { appMenu } from './app-menu';

const HUB = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

/**
 * The two checks, as tests of the `describe` around the call: each of `routes` loads its page on demand (`pages`: the
 * names its stubs carry, in the order of the routes), and the `routes.ts` beside the test (`here`, its
 * `import.meta.url`) imports types only.
 */
export function routeChecks(here: string, routes: RouteRecordRaw[], pages: string[]): void {
  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const route of routes) expect(typeof route.component).toBe('function');
    expect(await Promise.all(routes.map(loadPage))).toEqual(pages.map((name) => ({ name })));
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    expect(valueImports(readFileSync(join(dirname(fileURLToPath(here)), 'routes.ts'), 'utf8'))).toEqual([]);
  });
}

/** The import lines of `source` that bring values, not types only. */
export function valueImports(source: string): string[] {
  return [...source.matchAll(/^import\s+(?!type\b).*$/gm)].map((line) => line[0]);
}

/** The paths of the menu of the Hub's app `app`, in order. */
export function menuPaths(app: string): string[] {
  return appMenu(app).map((entry) => entry.path);
}

/** Every path of `app` its apps.py names (its menu, the Home's steps, the bell's counters), once each, in order. */
export function namedPaths(app: string): string[] {
  const source = readFileSync(join(HUB, 'apps', app, 'apps.py'), 'utf8');
  return [...new Set([...source.matchAll(new RegExp(`"(/${app}/[a-z-]+)"`, 'g'))].map((path) => path[1]))];
}

async function loadPage(route: RouteRecordRaw): Promise<RouteComponent> {
  const loader = route.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}
