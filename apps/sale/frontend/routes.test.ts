// The sale app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, namedPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/PosPage.vue', () => ({ default: { name: 'PosPage' } }));
vi.mock('./pages/SalesPage.vue', () => ({ default: { name: 'SalesPage' } }));
vi.mock('./pages/QuickNotesPage.vue', () => ({ default: { name: 'QuickNotesPage' } }));
vi.mock('./pages/DepartmentsPage.vue', () => ({ default: { name: 'DepartmentsPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

describe('sale routes.ts', () => {
  it('maps POS, Sales, Quick notes, Departments and Settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/sale/pos', true],
      ['/sale/sales', true],
      ['/sale/quick-notes', true],
      ['/sale/departments', true],
      ['/sale/settings', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['PosPage', 'SalesPage', 'QuickNotesPage', 'DepartmentsPage', 'SettingsPage']);

  it('has a page for every entry of its menu (its tabs), and every path apps.py names is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(menuPaths('sale'));
    expect(namedPaths('sale').filter((path) => !routes.some((r) => r.path === path))).toEqual([]);
  });
});
