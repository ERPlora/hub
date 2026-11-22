// The modifier app's `routes.ts`: its one section → its page, behind a session, and nothing else
// (main.ts reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/GroupsPage.vue', () => ({ default: { name: 'GroupsPage' } }));

describe('modifier routes.ts', () => {
  it('maps the groups (the path of the menu in apps.py) behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([['/modifier/groups', true]]);
  });

  routeChecks(import.meta.url, routes, ['GroupsPage']);

  it('matches the navigation of apps.py, entry for entry', () => {
    expect(menuPaths('modifier')).toEqual(routes.map((r) => r.path));
  });
});
