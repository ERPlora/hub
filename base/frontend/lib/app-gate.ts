// The gate of an app's screens (BASE-G132, G134; the old hub's entitlement and activation gates of
// `router/index.ts`, which the shell's router leaves to the project): a route of an app that `base.session.me` gives
// `off` — a paid app the business has no right to (`base.entitlement`); phase 2 adds turned off and activating —
// mounts base's «why it does not open» (AppBlockedPage) in the same address, as the shell's web-only gate mounts
// NotInAppPage: a redirect would lose where the link pointed. The server refuses the app's operations anyway (402):
// this only spares the person a screen of errors. An app the session does not list (this person may not see it) is
// left to its own screens, which say so; nothing is decided before the session arrives.
import type { SessionMe } from '@erplora/ui/shell';
import type { Ref } from 'vue';
import type { RouteLocationNormalized, RouteLocationRaw, RouteRecordRaw } from 'vue-router';

declare module 'vue-router' {
  interface RouteMeta {
    /** The app whose `frontend/routes.ts` declares the route (`main.ts` sets it): what the app gate checks. */
    app?: string;
  }
}

/** What a screen of an app that does not open shows. Registered after the shell's 404, so only reached by name. */
export const APP_BLOCKED_ROUTE: RouteRecordRaw = {
  path: '/:pathMatch(.*)*',
  name: 'base-app-blocked',
  component: () => import('../pages/AppBlockedPage.vue'),
  meta: { auth: true },
};

const APP_ROUTE_FILE = /\/apps\/([^/]+)\/frontend\/routes\.ts$/;

/** The app a `routes.ts` belongs to (`../apps/<id>/frontend/routes.ts`); base's is none. */
export function appOfRouteFile(file: string): string | undefined {
  return APP_ROUTE_FILE.exec(file)?.[1];
}

/** The router guard: `true`, or the blocked page in the same address. */
export function createAppGate(me: Readonly<Ref<SessionMe | undefined>>) {
  return (to: RouteLocationNormalized): true | RouteLocationRaw => {
    const app = to.meta.app;
    const entry = app ? me.value?.apps.find((candidate) => candidate.label === app) : undefined;
    if (!entry || entry.state === 'on') return true;
    return {
      name: APP_BLOCKED_ROUTE.name,
      params: { pathMatch: to.path.slice(1).split('/') },
      query: to.query,
      hash: to.hash,
    };
  };
}
