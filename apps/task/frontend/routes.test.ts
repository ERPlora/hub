// The task app's `routes.ts`: its sections → their pages, behind a session, and nothing else (main.ts
// reads the default export; menu, permissions and active apps come from the server).
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, namedPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/TasksPage.vue', () => ({ default: { name: 'TasksPage' } }));
vi.mock('./pages/ProjectsPage.vue', () => ({ default: { name: 'ProjectsPage' } }));

describe('task routes.ts', () => {
  it('maps Tasks and Projects, both behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/task/tasks', true],
      ['/task/projects', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['TasksPage', 'ProjectsPage']);

  it('has a page for every entry of its menu (its tabs), and every path apps.py names is one of them', () => {
    expect(routes.map((r) => r.path)).toEqual(menuPaths('task'));
    expect(namedPaths('task').filter((path) => !routes.some((r) => r.path === path))).toEqual([]);
  });
});
