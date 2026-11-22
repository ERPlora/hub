// The service app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, namedPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/ServicesPage.vue', () => ({ default: { name: 'ServicesPage' } }));
vi.mock('./pages/CategoriesPage.vue', () => ({ default: { name: 'CategoriesPage' } }));
vi.mock('./pages/PackagesPage.vue', () => ({ default: { name: 'PackagesPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

describe('service routes.ts', () => {
  it('maps Services, Categories, Packages and Settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/service/services', true],
      ['/service/categories', true],
      ['/service/packages', true],
      ['/service/settings', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['ServicesPage', 'CategoriesPage', 'PackagesPage', 'SettingsPage']);

  it('has a page for every entry of its menu (its tabs), and every route apps.py names (its menu and where the Home sends) is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(menuPaths('service'));
    const paths = namedPaths('service');
    expect(paths.sort()).toEqual(['/service/categories', '/service/packages', '/service/services', '/service/settings']);
    for (const path of paths) expect(routes.some((r) => r.path === path), path).toBe(true);
  });
});
