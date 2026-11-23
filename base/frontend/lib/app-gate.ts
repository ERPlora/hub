// The gate of an app's screens, which the shell's router leaves to the project. It mounts base's gate page in the same
// address, as the shell's web-only gate mounts NotInAppPage (a redirect would lose where the link pointed), in two
// cases. A route of an app whose state in `base.session.me` is anything but `on` — a paid app the business has no
// right to, one it turned off, one still activating — gets «why it does not open» (AppBlockedPage). A route under a
// menu entry this person may not open gets «No access» (NoAccessPage): the session's `locked` entries decide it, by
// the longest entry of the app that covers the address, never its `apps`, which list every app the person holds a
// permission of. A platform screen, which belongs to no app, gets «No access» too when the person lacks the permission
// of the side-menu entry that covers it, the same one that hides the entry. The server refuses what the screen would
// ask anyway (402, 403, or 404 `app_inactive` when it is off): this only spares the person a screen of errors. Nothing
// is decided before the session arrives.
import type { SessionMe } from '@erplora/ui/shell';
import type { Ref } from 'vue';
import type { RouteLocationNormalized, RouteLocationRaw, RouteRecordRaw, Router } from 'vue-router';

import { SIDEBAR } from './sidebar';

declare module 'vue-router' {
  interface RouteMeta {
    /** The app whose `frontend/routes.ts` declares the route (`main.ts` sets it): what the app gate checks. */
    app?: string;
  }
}

/** What a screen the gate stops shows. Registered after the shell's 404, so only reached by name. */
export const APP_BLOCKED_ROUTE: RouteRecordRaw = {
  path: '/:pathMatch(.*)*',
  name: 'base-app-blocked',
  component: () => import('../pages/AppGatePage.vue'),
  meta: { auth: true },
};

const APP_ROUTE_FILE = /\/apps\/([^/]+)\/frontend\/routes\.ts$/;

/** The app a `routes.ts` belongs to (`../apps/<id>/frontend/routes.ts`); base's is none. */
export function appOfRouteFile(file: string): string | undefined {
  return APP_ROUTE_FILE.exec(file)?.[1];
}

/** `open`; `blocked`: the app does not open for anyone; `no-access`: this person may not open the screen. */
export type GateVerdict = 'open' | 'blocked' | 'no-access';

type GatedRoute = Pick<RouteLocationNormalized, 'path' | 'meta'>;

/** What the gate says of a route, for this session. */
export function gateVerdict(me: SessionMe | undefined, to: GatedRoute): GateVerdict {
  if (!me) return 'open';
  const app = to.meta.app;
  if (!app) return isPlatformLocked(me, to.path) ? 'no-access' : 'open';
  const state = me.apps.find((candidate) => candidate.label === app)?.state;
  if (state !== undefined && state !== 'on') return 'blocked';
  return isLocked(me, app, to.path) ? 'no-access' : 'open';
}

function isLocked(me: SessionMe, app: string, path: string): boolean {
  const closed = me.locked?.[app] ?? [];
  if (closed.length === 0) return false;
  const opened = me.menu.find((section) => section.id === app)?.items.map((item) => item.path) ?? [];
  const entry = longestCovering([...opened, ...closed], path);
  return entry !== undefined && closed.includes(entry);
}

function isPlatformLocked(me: SessionMe, path: string): boolean {
  const items = SIDEBAR.groups.flat();
  const entry = longestCovering(
    items.map((item) => item.to),
    path,
  );
  const permission = items.find((item) => item.to === entry)?.permission;
  return permission !== undefined && !me.permissions.includes('*') && !me.permissions.includes(permission);
}

/** The longest of `entries` that is `path` or one of its parents, segment by segment. */
function longestCovering(entries: readonly string[], path: string): string | undefined {
  return entries
    .filter((entry) => path === entry || path.startsWith(`${entry}/`))
    .reduce<string | undefined>(
      (longest, candidate) => (longest === undefined || candidate.length > longest.length ? candidate : longest),
      undefined,
    );
}

/** The screen in front goes through the gate again in the same address: the session it was judged with changed. */
export function gateAgain(router: Router): void {
  const { path, query, hash } = router.currentRoute.value;
  void router.replace({ path, query, hash, force: true });
}

/** The router guard: `true`, or the gate page in the same address. */
export function createAppGate(me: Readonly<Ref<SessionMe | undefined>>) {
  return (to: RouteLocationNormalized): true | RouteLocationRaw => {
    if (to.name === APP_BLOCKED_ROUTE.name || gateVerdict(me.value, to) === 'open') return true;
    return {
      name: APP_BLOCKED_ROUTE.name,
      params: { pathMatch: to.path.slice(1).split('/') },
      query: to.query,
      hash: to.hash,
    };
  };
}
