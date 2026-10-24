// base's routes of the way in (APP-BASE-3): «Access» and «Create your PIN» paint their own frame, the first without a
// session (where Django's `way_in` sends a browser without one); «Switch user» over the session it replaces; «My
// profile» and Settings in the chrome. Each loads its page on demand.
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

vi.mock('./pages/LoginPage.vue', () => ({ default: { name: 'LoginPage' } }));
vi.mock('./pages/PinSetupPage.vue', () => ({ default: { name: 'PinSetupPage' } }));
vi.mock('./pages/SwitchUserPage.vue', () => ({ default: { name: 'SwitchUserPage' } }));
vi.mock('./pages/ProfilePage.vue', () => ({ default: { name: 'ProfilePage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

const byName = (name: string): RouteRecordRaw => {
  const route = routes.find((r) => r.name === name);
  if (!route) throw new Error(`no route ${name}`);
  return route;
};

describe('base routes of the way in', () => {
  it.each([
    ['base-login', '/login', false, false, 'LoginPage'],
    ['base-pin-setup', '/pin/setup', true, false, 'PinSetupPage'],
    ['base-switch-user', '/switch-user', true, false, 'SwitchUserPage'],
    ['base-profile', '/profile', true, undefined, 'ProfilePage'],
    ['base-settings', '/settings', true, undefined, 'SettingsPage'],
  ])('%s at %s (auth %s, chrome %s) loads %s on demand', async (name, path, auth, chrome, page) => {
    const route = byName(name);
    expect([route.path, route.meta?.auth, route.meta?.chrome]).toEqual([path, auth, chrome]);
    const loader = route.component as () => Promise<{ default: RouteComponent }>;
    expect(((await loader()).default as { name: string }).name).toBe(page);
  });
});
