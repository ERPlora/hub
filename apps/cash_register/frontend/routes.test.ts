// The cash register app's `routes.ts`: its sections and the detail of a session → their pages, behind a
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
vi.mock('./pages/SessionsPage.vue', () => ({ default: { name: 'SessionsPage' } }));
vi.mock('./pages/SessionDetailPage.vue', () => ({ default: { name: 'SessionDetailPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('cash register routes.ts', () => {
  it('maps the sessions, the detail of one and the settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/cash_register/sessions', true],
      ['/cash_register/sessions/:id', true],
      ['/cash_register/settings', true],
    ]);
  });

  it('hands the detail its session id as a prop: Ionic keeps one view per URL, never a stale route', () => {
    expect(routes[1].props).toBe(true);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(routes[0])).toEqual({ name: 'SessionsPage' });
    expect(await load(routes[1])).toEqual({ name: 'SessionDetailPage' });
    expect(await load(routes[2])).toEqual({ name: 'SettingsPage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('has a page for every path apps.py names: its menu and where the Home\'s «Your cash drawer» leads', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...new Set([...appsPy.matchAll(/"(\/cash_register\/[a-z_]+)"/g)].map((m) => m[1]))];
    expect(paths).toEqual(['/cash_register/sessions', '/cash_register/settings']);
    for (const path of paths) expect(routes.some((r) => r.path === path), path).toBe(true);
  });
});
