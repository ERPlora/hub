// The gate of an app's screens (BASE-G132, G134): a route of an app the session gives `off` (a paid app the business
// has no right to; phase 2 adds turned off and activating) mounts base's «why it does not open» in the same address,
// as the shell's web-only gate does. An app that is on, one the session does not list (this person may not see it:
// its own screens say so) and a session that has not arrived yet pass.
import type { SessionMe } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import type { RouteLocationNormalized } from 'vue-router';

import { APP_BLOCKED_ROUTE, appOfRouteFile, createAppGate } from './app-gate';

const ME: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: [],
  menu: [],
  apps: [
    { label: 'tax', state: 'on' },
    { label: 'stock', state: 'off' },
  ],
  language: 'en',
};

function to(path: string, app?: string, extra: Partial<RouteLocationNormalized> = {}): RouteLocationNormalized {
  return { path, fullPath: path, query: {}, hash: '', meta: app ? { app } : {}, ...extra } as RouteLocationNormalized;
}

describe('the app of a route file', () => {
  it('is the folder of apps/<id>/frontend/routes.ts; base is none', () => {
    expect(appOfRouteFile('../apps/cash_register/frontend/routes.ts')).toBe('cash_register');
    expect(appOfRouteFile('../base/frontend/routes.ts')).toBeUndefined();
  });
});

describe('createAppGate', () => {
  const gate = createAppGate(ref(ME));

  it('lets an app that is on through', () => {
    expect(gate(to('/tax/rules', 'tax'))).toBe(true);
  });

  it('mounts «why it does not open» in the same address for an app that is off', () => {
    expect(gate(to('/stock/items/42', 'stock', { query: { q: 'x' }, hash: '#a' }))).toEqual({
      name: APP_BLOCKED_ROUTE.name,
      params: { pathMatch: ['stock', 'items', '42'] },
      query: { q: 'x' },
      hash: '#a',
    });
  });

  it('lets through what is no app’s, an app the session does not list and a session not here yet', () => {
    expect(gate(to('/apps'))).toBe(true);
    expect(gate(to('/reports', 'reports'))).toBe(true);
    expect(createAppGate(ref(undefined))(to('/stock', 'stock'))).toBe(true);
  });

  it('is reached only by name: a catch-all registered after the 404, which keeps every unknown address', () => {
    expect(APP_BLOCKED_ROUTE).toMatchObject({ path: '/:pathMatch(.*)*', name: 'base-app-blocked', meta: { auth: true } });
  });
});
