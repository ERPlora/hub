// base's `routes.ts`: the Home at `/` (APP-BASE-1), Apps at `/apps` and System at `/system` (APP-BASE-4) and the way in
// (APP-BASE-3); main.ts reads the default export.
import type { RouteComponent } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The page, stubbed: this file checks which page the route loads and that it loads it on demand (its own
// test mounts it).
vi.mock('./pages/HomePage.vue', () => ({ default: { name: 'HomePage' } }));
vi.mock('./pages/AppsPage.vue', () => ({ default: { name: 'AppsPage' } }));
vi.mock('./pages/SystemPage.vue', () => ({ default: { name: 'SystemPage' } }));

describe('base routes', () => {
  it("puts the Home at `/`, under a name of its own: the shell's grid keeps `home`", () => {
    expect(routes.map((r) => [r.path, r.name, r.meta?.auth])).toEqual([
      ['/', 'base-home', true],
      ['/apps', 'base-apps', true],
      ['/system', 'base-system', true],
      // The way in (APP-BASE-3; routes.access.test.ts).
      ['/login', 'base-login', false],
      ['/pin/setup', 'base-pin-setup', true],
      ['/switch-user', 'base-switch-user', true],
      ['/profile', 'base-profile', true],
      ['/settings', 'base-settings', true],
    ]);
  });

  it('loads Apps on demand: its tabs are the address hash (`#all`, `#paid`), so one route', async () => {
    const loader = routes[1].component as () => Promise<{ default: RouteComponent }>;
    expect(((await loader()).default as { name: string }).name).toBe('AppsPage');
  });

  it('loads the Home page on demand', async () => {
    const loader = routes[0].component as () => Promise<{ default: RouteComponent }>;
    expect(((await loader()).default as { name: string }).name).toBe('HomePage');
  });

  it('loads System on demand', async () => {
    const loader = routes[2].component as () => Promise<{ default: RouteComponent }>;
    expect(((await loader()).default as { name: string }).name).toBe('SystemPage');
  });
});
