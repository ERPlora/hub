// The tax app's `routes.ts`: its three sections → their pages, behind a session, and nothing else
// (main.ts reads the default export; menu, permissions and active apps come from the server).
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
vi.mock('./pages/CategoriesPage.vue', () => ({ default: { name: 'CategoriesPage' } }));
vi.mock('./pages/RulesPage.vue', () => ({ default: { name: 'RulesPage' } }));
vi.mock('./pages/AliasesPage.vue', () => ({ default: { name: 'AliasesPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('tax routes.ts', () => {
  it('maps Categories, Rules, Aliases and Settings (the paths of the menu in apps.py), all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/tax/categories', true],
      ['/tax/rules', true],
      ['/tax/aliases', true],
      ['/tax/settings', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(routes[0])).toEqual({ name: 'CategoriesPage' });
    expect(await load(routes[1])).toEqual({ name: 'RulesPage' });
    expect(await load(routes[2])).toEqual({ name: 'AliasesPage' });
    expect(await load(routes[3])).toEqual({ name: 'SettingsPage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('matches the navigation of apps.py, entry for entry', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/Nav\(.*"(\/tax\/[a-z]+)"\)/g)].map((m) => m[1]);
    expect(paths).toEqual(routes.map((r) => r.path));
  });

  it('has a page where the Home sends its step «Your taxes» (the `route` of apps.py)', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const sent = [...appsPy.matchAll(/route="(\/tax\/[a-z]+)"/g)].map((m) => m[1]);
    expect(sent).toEqual(['/tax/rules']);
    expect(routes.map((r) => r.path)).toContain(sent[0]);
  });
});
