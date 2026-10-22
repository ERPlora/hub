// The website app's `routes.ts`: its one route → page and nothing else (main.ts reads the default export).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The page, stubbed: this file checks which page the route loads and that it loads it on demand (its own test
// mounts it).
vi.mock('./pages/WebsitePage.vue', () => ({ default: { name: 'WebsitePage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

describe('website routes.ts', () => {
  it('maps /website, the menu entry, behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([['/website', true]]);
  });

  it('loads the editor on demand, not at boot', async () => {
    const loader = routes[0].component as () => Promise<{ default: RouteComponent }>;
    expect(typeof loader).toBe('function');
    expect((await loader()).default).toEqual({ name: 'WebsitePage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});
