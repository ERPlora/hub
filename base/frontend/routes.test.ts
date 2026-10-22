// base's `routes.ts`: the Home at `/` (APP-BASE-1) and nothing else; main.ts reads the default export.
import type { RouteComponent } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The page, stubbed: this file checks which page the route loads and that it loads it on demand (its own
// test mounts it).
vi.mock('./pages/HomePage.vue', () => ({ default: { name: 'HomePage' } }));

describe('base routes', () => {
  it("puts the Home at `/`, under a name of its own: the shell's grid keeps `home`", () => {
    expect(routes.map((r) => [r.path, r.name, r.meta?.auth])).toEqual([['/', 'base-home', true]]);
  });

  it('loads the Home page on demand', async () => {
    const loader = routes[0].component as () => Promise<{ default: RouteComponent }>;
    expect(((await loader()).default as { name: string }).name).toBe('HomePage');
  });
});
