// The flow app's `routes.ts`: its pages behind a session, and nothing else (main.ts reads the default
// export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';

import { routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/AutomationsPage.vue', () => ({ default: { name: 'AutomationsPage' } }));
vi.mock('./pages/NewFlowPage.vue', () => ({ default: { name: 'NewFlowPage' } }));
vi.mock('./pages/FlowEditorPage.vue', () => ({ default: { name: 'FlowEditorPage' } }));
vi.mock('./pages/GuidePage.vue', () => ({ default: { name: 'GuidePage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

describe('flow routes.ts', () => {
  it('maps the list, a new one, a saved one and the guide, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/flow/automations', true],
      ['/flow/automations/new', true],
      ['/flow/automations/:id', true],
      ['/flow/automations/guide', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['AutomationsPage', 'NewFlowPage', 'FlowEditorPage', 'GuidePage']);

  it('the menu entry of apps.py is one of its pages', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/"(\/flow\/[^"]+)"/g)].map((match) => match[1]);
    expect(paths).toEqual(['/flow/automations']);
    for (const path of paths) expect(routes.some((r) => r.path === path)).toBe(true);
  });
});
