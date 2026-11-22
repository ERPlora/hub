// The appointment app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { namedPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';
import { APPOINTMENT_TABS } from './tabs';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/AgendaPage.vue', () => ({ default: { name: 'AgendaPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

describe('appointment routes.ts', () => {
  it('maps the Agenda and the Settings, both behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/appointment/agenda', true],
      ['/appointment/settings', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['AgendaPage', 'SettingsPage']);

  it('has a page for every tab, and every path apps.py names (its menu entry, its bell counter) is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(APPOINTMENT_TABS.map((tab) => tab.to));
    // Distinct paths: the two menu entries, and the bell's «Appointments to confirm», which leads to the Agenda.
    const paths = namedPaths('appointment');
    expect(paths).toEqual(['/appointment/agenda', '/appointment/settings']);
  });
});
