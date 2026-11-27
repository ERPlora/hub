/// <reference types="vite/client" />
// The screens screens-text-fits.spec.ts walks: those of every app the salon's and the restaurant's QA journeys
// (qa/journeys/) cite, among the routes the Hub registers, so a new screen or a new app in a journey is walked with
// no list to keep by hand. Here the routes are the ones base and the apps declare in their routes.ts.
import type { RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import { journeyApps, type RouteInfo, screensAmong } from './journey-screens';

const declared = import.meta.glob<{ default: RouteRecordRaw[] }>(['../../base/frontend/routes.ts', '../../apps/*/frontend/routes.ts'], {
  eager: true,
});
const ROUTES: RouteInfo[] = Object.values(declared).flatMap((module) =>
  module.default.map((route) => ({ path: route.path, redirect: 'redirect' in route && !!route.redirect, meta: route.meta ?? {} })),
);

describe('journeyScreens: the screens of the salon and restaurant journeys', () => {
  it('takes the apps from the flows the salon and restaurant journeys cite, base among them, and no other journey’s', () => {
    const apps = journeyApps();
    expect(apps).toEqual(expect.arrayContaining(['appointment', 'service', 'staff', 'customer', 'sale', 'table', 'kitchen', 'base']));
    expect(apps, 'Tasks is only in the tasks journey').not.toContain('task');
    expect(apps, 'Automations is only in the automations journey').not.toContain('flow');
  });

  it('keeps each page of those apps that opens behind a session with no parameter, and nothing that is not such a page', () => {
    const screens = screensAmong(ROUTES, journeyApps());
    expect(screens).toEqual(expect.arrayContaining(['/', '/settings', '/appointment/agenda', '/sale/pos', '/table/floor-plan', '/staff/members']));
    expect(screens, 'a page of one record needs its id').not.toContain('/customer/customers/:id');
    expect(screens, 'a public page is not the business’s').not.toContain('/p/:slug/book');
    expect(screens, 'the way in is not a screen of the business').not.toEqual(expect.arrayContaining(['/login']));
    expect(screens, 'the way in paints its own frame').not.toEqual(expect.arrayContaining(['/switch-user']));
    expect(screens, 'an address that only redirects is not a screen').not.toEqual(expect.arrayContaining(['/import']));
    expect(screens, 'an app of no journey').not.toEqual(expect.arrayContaining(['/task/tasks']));
    expect(new Set(screens).size, 'each screen once').toBe(screens.length);
  });
});
