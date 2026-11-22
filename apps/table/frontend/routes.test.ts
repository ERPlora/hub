// The table app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { namedPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';
import { TABLE_TABS } from './tabs';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/FloorPlanPage.vue', () => ({ default: { name: 'FloorPlanPage' } }));
vi.mock('./pages/ZonesPage.vue', () => ({ default: { name: 'ZonesPage' } }));
vi.mock('./pages/TablesPage.vue', () => ({ default: { name: 'TablesPage' } }));
vi.mock('./pages/SessionsPage.vue', () => ({ default: { name: 'SessionsPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

describe('table routes.ts', () => {
  it('maps Floor plan, Zones, Tables, Sessions and Settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/table/floor-plan', true],
      ['/table/zones', true],
      ['/table/tables', true],
      ['/table/sessions', true],
      ['/table/settings', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['FloorPlanPage', 'ZonesPage', 'TablesPage', 'SessionsPage', 'SettingsPage']);

  it('has a page for every tab, and every route apps.py names (its menu and where the Home sends) is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(TABLE_TABS.map((tab) => tab.to));
    const paths = namedPaths('table');
    expect(paths.sort()).toEqual(['/table/floor-plan', '/table/sessions', '/table/settings', '/table/tables', '/table/zones']);
    for (const path of paths) expect(routes.some((r) => r.path === path), path).toBe(true);
  });
});
