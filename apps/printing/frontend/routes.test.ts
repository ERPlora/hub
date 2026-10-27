// The printing app's `routes.ts`: its three sections → their pages, behind a session, and nothing else
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
vi.mock('./pages/PrintersPage.vue', () => ({ default: { name: 'PrintersPage' } }));
vi.mock('./pages/DevicesPage.vue', () => ({ default: { name: 'DevicesPage' } }));
vi.mock('./pages/JobsPage.vue', () => ({ default: { name: 'JobsPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('printing routes.ts', () => {
  it('maps the printers, the devices, the queue and the settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/printing/printers', true],
      ['/printing/devices', true],
      ['/printing/jobs', true],
      ['/printing/settings', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    expect(await load(routes[0])).toEqual({ name: 'PrintersPage' });
    expect(await load(routes[1])).toEqual({ name: 'DevicesPage' });
    expect(await load(routes[2])).toEqual({ name: 'JobsPage' });
    expect(await load(routes[3])).toEqual({ name: 'SettingsPage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('has a page for every route apps.py names: its menu and where the Home sends (its step, its bell)', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...new Set([...appsPy.matchAll(/"(\/printing\/[a-z_]+)"/g)].map((m) => m[1]))];
    expect(paths.sort()).toEqual(['/printing/devices', '/printing/jobs', '/printing/printers', '/printing/settings']);
    for (const path of paths) expect(routes.some((r) => r.path === path), path).toBe(true);
  });
});
