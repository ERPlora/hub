// The pricing app's `routes.ts`: its one menu entry (the lists and the rules) and a list's detail → their
// pages, behind a session, and nothing else (main.ts reads the default export; menu, permissions and
// active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/ListsPage.vue', () => ({ default: { name: 'ListsPage' } }));
vi.mock('./pages/ListDetailPage.vue', () => ({ default: { name: 'ListDetailPage' } }));

describe('pricing routes.ts', () => {
  it('maps the lists and a list’s detail, both behind a session, the id as a prop', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth, r.props ?? false])).toEqual([
      ['/pricing/lists', true, false],
      ['/pricing/lists/:id', true, true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['ListsPage', 'ListDetailPage']);

  it('serves the path of the menu entry of apps.py', () => {
    const paths = menuPaths('pricing');
    expect(paths).toEqual(['/pricing/lists']);
    expect(routes.map((r) => r.path)).toContain(paths[0]);
  });
});
