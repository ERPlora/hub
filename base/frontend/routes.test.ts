// base's `routes.ts`: the Home at `/` (APP-BASE-1), Apps at `/apps` and System at `/system` (APP-BASE-4), the way in
// (APP-BASE-3), and Settings at `/settings` (APP-BASE-2, the old hub's address, with its old `/import` and `/export`
// pages landing on Data); main.ts reads the default export.
import type { RouteComponent } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand (their own
// tests mount them).
vi.mock('./pages/HomePage.vue', () => ({ default: { name: 'HomePage' } }));
vi.mock('./pages/AppsPage.vue', () => ({ default: { name: 'AppsPage' } }));
vi.mock('./pages/SystemPage.vue', () => ({ default: { name: 'SystemPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

async function page(path: string): Promise<string> {
  const route = routes.find((r) => r.path === path);
  const loader = route?.component as () => Promise<{ default: RouteComponent }>;
  return ((await loader()).default as { name: string }).name;
}

describe('base routes', () => {
  it("puts the Home at `/`, under a name of its own (the shell's grid keeps `home`), Apps, System and Settings", () => {
    expect(routes.filter((r) => r.component).map((r) => [r.path, r.name, r.meta?.auth])).toEqual([
      ['/', 'base-home', true],
      ['/apps', 'base-apps', true],
      ['/system', 'base-system', true],
      // The way in (APP-BASE-3; routes.access.test.ts).
      ['/login', 'base-login', false],
      ['/pin/setup', 'base-pin-setup', true],
      ['/switch-user', 'base-switch-user', true],
      ['/profile', 'base-profile', true],
      ['/settings', 'base-settings', true],
      // Files (APP-BASE-8): routes.files.test.ts.
      ['/files', 'base-files', true],
    ]);
  });

  it('loads Apps on demand: its tabs are the address hash (`#all`, `#paid`), so one route', async () => {
    const loader = routes[1].component as () => Promise<{ default: RouteComponent }>;
    expect(((await loader()).default as { name: string }).name).toBe('AppsPage');
  });

  it('loads each page on demand', async () => {
    expect(await page('/')).toBe('HomePage');
    expect(await page('/settings')).toBe('SettingsPage');
  });

  it('takes the old `/import` and `/export` pages to Settings › Data, Export already open for the second', () => {
    const redirects = Object.fromEntries(routes.filter((r) => r.redirect).map((r) => [r.path, r.redirect]));
    expect(redirects).toEqual({
      '/import': { path: '/settings', hash: '#data' },
      '/export': { path: '/settings', query: { data: 'export' }, hash: '#data' },
    });
  });

  it('loads System on demand', async () => {
    const loader = routes[2].component as () => Promise<{ default: RouteComponent }>;
    expect(((await loader()).default as { name: string }).name).toBe('SystemPage');
  });
});
