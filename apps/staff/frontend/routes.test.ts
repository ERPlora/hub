// The staff app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, namedPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/MembersPage.vue', () => ({ default: { name: 'MembersPage' } }));
vi.mock('./pages/RolesPage.vue', () => ({ default: { name: 'RolesPage' } }));
vi.mock('./pages/TimeOffPage.vue', () => ({ default: { name: 'TimeOffPage' } }));
vi.mock('./pages/SchedulesPage.vue', () => ({ default: { name: 'SchedulesPage' } }));
vi.mock('./pages/CommissionsPage.vue', () => ({ default: { name: 'CommissionsPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

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

  routeChecks(import.meta.url, routes, [
    'MembersPage',
    'RolesPage',
    'TimeOffPage',
    'SchedulesPage',
    'CommissionsPage',
    'SettingsPage',
  ]);

  it('has a page for every entry of its menu (its tabs), and every path apps.py names is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(menuPaths('staff'));
    expect(namedPaths('staff').filter((path) => !routes.some((r) => r.path === path))).toEqual([]);
  });
});
