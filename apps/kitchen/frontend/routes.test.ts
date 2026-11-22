// The kitchen app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { namedPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';
import { KITCHEN_TABS } from './tabs';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/DisplayPage.vue', () => ({ default: { name: 'DisplayPage' } }));
vi.mock('./pages/TicketsPage.vue', () => ({ default: { name: 'TicketsPage' } }));
vi.mock('./pages/StationsPage.vue', () => ({ default: { name: 'StationsPage' } }));
vi.mock('./pages/HistoryPage.vue', () => ({ default: { name: 'HistoryPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

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

  routeChecks(import.meta.url, routes, ['DisplayPage', 'TicketsPage', 'StationsPage', 'HistoryPage', 'SettingsPage']);

  it('has a page for every tab, and every menu entry of apps.py is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(KITCHEN_TABS.map((tab) => tab.to));
    const paths = namedPaths('kitchen');
    expect(paths.every((path) => routes.some((r) => r.path === path))).toBe(true);
    expect(paths).toHaveLength(5);
  });
});
