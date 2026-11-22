// The reservation app's `routes.ts`: its three sections and Settings → their pages, behind a session, and
// nothing else (main.ts reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/ReservationsPage.vue', () => ({ default: { name: 'ReservationsPage' } }));
vi.mock('./pages/WaitlistPage.vue', () => ({ default: { name: 'WaitlistPage' } }));
vi.mock('./pages/AvailabilityPage.vue', () => ({ default: { name: 'AvailabilityPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

describe('reservation routes.ts', () => {
  it('maps Reservations, Waitlist, Availability and Settings, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/reservation/reservations', true],
      ['/reservation/waitlist', true],
      ['/reservation/availability', true],
      ['/reservation/settings', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['ReservationsPage', 'WaitlistPage', 'AvailabilityPage', 'SettingsPage']);

  it('serves every menu entry of apps.py, Settings among them, entry for entry', () => {
    expect(menuPaths('reservation')).toEqual(routes.map((r) => r.path));
  });
});
