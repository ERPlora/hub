// The modifier app's `routes.ts`: its one section → its page, behind a session, and nothing else
// (main.ts reads the default export; menu, permissions and active apps come from the server).
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
vi.mock('./pages/GroupsPage.vue', () => ({ default: { name: 'GroupsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('modifier routes.ts', () => {
  it('maps the groups (the path of the menu in apps.py) behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([['/modifier/groups', true]]);
  });

  it('loads the page on demand (its own chunk), not at boot', async () => {
    expect(typeof routes[0].component).toBe('function');
    expect(await load(routes[0])).toEqual({ name: 'GroupsPage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });

  it('matches the navigation of apps.py, entry for entry', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const paths = [...appsPy.matchAll(/Nav\(.*"(\/modifier\/[a-z]+)"\)/g)].map((m) => m[1]);
    expect(paths).toEqual(routes.map((r) => r.path));
  });
});
