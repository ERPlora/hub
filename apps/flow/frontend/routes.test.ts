// The flow app's `routes.ts`: its pages behind a session, and nothing else (main.ts reads the default
// export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand, not
// the page (its own tests mount it). A real page brings its whole graph (Ionic, @erplora/ui): over a
// second idle and past Vitest's 5 s on a loaded machine. A real page where a stub is expected is a page
// this file does not stub.
vi.mock('./pages/AutomationsPage.vue', () => ({ default: { name: 'AutomationsPage' } }));
vi.mock('./pages/NewFlowPage.vue', () => ({ default: { name: 'NewFlowPage' } }));
vi.mock('./pages/FlowEditorPage.vue', () => ({ default: { name: 'FlowEditorPage' } }));
vi.mock('./pages/GuidePage.vue', () => ({ default: { name: 'GuidePage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('flow routes.ts', () => {
  it('maps the list, a new one, a saved one and the guide, all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/flow/automations', true],
      ['/flow/automations/new', true],
      ['/flow/automations/:id', true],
      ['/flow/guide', true],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    for (const r of routes) expect(typeof r.component).toBe('function');
    const pages = await Promise.all(routes.map(load));
    expect(pages).toEqual([
      { name: 'AutomationsPage' },
      { name: 'NewFlowPage' },
      { name: 'FlowEditorPage' },
      { name: 'GuidePage' },
    ]);
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('the menu entry of apps.py is one of its pages', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/"(\/flow\/[^"]+)"/g)].map((match) => match[1]);
    expect(paths).toEqual(['/flow/automations']);
    for (const path of paths) expect(routes.some((r) => r.path === path)).toBe(true);
  });
});
