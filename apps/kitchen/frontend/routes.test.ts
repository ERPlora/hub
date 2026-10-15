// The kitchen app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import routes from './routes';
import { KITCHEN_TABS } from './tabs';

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('kitchen routes.ts', () => {
  it('maps Display, Tickets, Stations, History and Settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/kitchen/display', true],
      ['/kitchen/tickets', true],
      ['/kitchen/stations', true],
      ['/kitchen/history', true],
      ['/kitchen/settings', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', { timeout: 60_000 }, async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    const pages = await Promise.all(routes.map(load));
    expect(pages).toEqual([
      (await import('./pages/DisplayPage.vue')).default,
      (await import('./pages/TicketsPage.vue')).default,
      (await import('./pages/StationsPage.vue')).default,
      (await import('./pages/HistoryPage.vue')).default,
      (await import('./pages/SettingsPage.vue')).default,
    ]);
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('has a page for every tab, and every menu entry of apps.py is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(KITCHEN_TABS.map((tab) => tab.to));
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/"(\/kitchen\/[a-z-]+)"/g)].map((m) => m[1]);
    expect(paths.every((path) => routes.some((r) => r.path === path))).toBe(true);
    expect(paths).toHaveLength(4);
  });
});
