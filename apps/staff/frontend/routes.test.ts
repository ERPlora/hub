// The staff app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';
import { STAFF_TABS } from './tabs';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand, not
// the page (its own tests mount it). A real page brings its whole graph (Ionic, @erplora/ui): over a
// second idle and past Vitest's 5 s on a loaded machine. A real page where a stub is expected is a page
// this file does not stub.
vi.mock('./pages/MembersPage.vue', () => ({ default: { name: 'MembersPage' } }));
vi.mock('./pages/RolesPage.vue', () => ({ default: { name: 'RolesPage' } }));
vi.mock('./pages/TimeOffPage.vue', () => ({ default: { name: 'TimeOffPage' } }));
vi.mock('./pages/SchedulesPage.vue', () => ({ default: { name: 'SchedulesPage' } }));
vi.mock('./pages/CommissionsPage.vue', () => ({ default: { name: 'CommissionsPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('staff routes.ts', () => {
  it('maps Staff, Roles, Time Off, Schedules, Commissions and Settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/staff/members', true],
      ['/staff/roles', true],
      ['/staff/time-off', true],
      ['/staff/schedules', true],
      ['/staff/commissions', true],
      ['/staff/settings', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    const pages = await Promise.all(routes.map(load));
    expect(pages).toEqual([
      { name: 'MembersPage' },
      { name: 'RolesPage' },
      { name: 'TimeOffPage' },
      { name: 'SchedulesPage' },
      { name: 'CommissionsPage' },
      { name: 'SettingsPage' },
    ]);
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('has a page for every tab, and every menu entry of apps.py is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(STAFF_TABS.map((tab) => tab.to));
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/path="(\/staff\/[a-z-]+)"/g)].map((m) => m[1]);
    expect(paths.every((path) => routes.some((r) => r.path === path))).toBe(true);
    expect(paths).toHaveLength(4);
  });
});
