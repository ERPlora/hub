// Entry of the hub SPA (`LIVE["spa"]["entry"]`): app routes and catalogues → shell, live client, session
// (`base.session.me`, a plain query: embedded by `base/spa.py`, else `GET /api/me`), mount.
// 🔴 Import order (hub#1060): the shell barrel goes first so its boot hooks wrap `customElements.define`
// before anything loads `@ionic/vue` (the SDK does). Vite hoists eager globs above everything, so an
// app's `routes.ts` only imports types; its pages load with `() => import(…)`. Guards: main.test.ts.
import { createShell, type CreateShellOptions, logout, type SessionMe, type SessionStatus } from '@erplora/ui/shell';
import { createLiveClient, type LiveClient, provideLiveClient, readSpaConfig } from '@erplora/ui/sdk';
import { ref } from 'vue';
import { isNavigationFailure, type RouteRecordRaw } from 'vue-router';

import { OPERATION_ROUTES } from './generated/operation-routes';

/** An app's `frontend/routes.ts` default-exports its routes → pages, and nothing else. */
export type AppRoutes = { default: RouteRecordRaw[] };

/** Every app's routes, in path order; a page needs a session unless its route says `auth: false`. */
export function appRoutes(routeFiles: Record<string, AppRoutes>): RouteRecordRaw[] {
  return Object.keys(routeFiles)
    .sort()
    .flatMap((file) => routeFiles[file].default)
    .map((route) => ({ ...route, meta: { auth: true, ...route.meta } }) as RouteRecordRaw);
}

/** An app's `frontend/locale/<lang>.json`, all under the app id (guard: main.test.ts). */
export type AppCatalogue = Record<string, unknown>;

/** Every app catalogue, by the language in its file name; distinct app ids, so a spread never collides. */
export function appMessages(catalogues: Record<string, AppCatalogue>): CreateShellOptions['messages'] {
  const messages: Record<string, AppCatalogue> = {};
  for (const [file, catalogue] of Object.entries(catalogues)) {
    const language = file.slice(file.lastIndexOf('/') + 1, -'.json'.length);
    messages[language] = { ...messages[language], ...catalogue };
  }
  return messages;
}

/** A failed `/api/me` ends in `error`, so the auth gate stops waiting and sends to the login. */
function loadSession(client: LiveClient, doc: Document) {
  const text = doc.getElementById('session-me')?.textContent;
  const me = ref<SessionMe | undefined>(text ? (JSON.parse(text) as SessionMe) : undefined);
  const status = ref<SessionStatus>(me.value ? 'live' : 'loading');
  if (!me.value) {
    client.api.call('base.session.me', {}).then(
      (answer) => {
        me.value = answer;
        status.value = 'live';
      },
      (error: unknown) => {
        console.error('hub: base.session.me failed', error);
        status.value = 'error';
      },
    );
  }
  return { session: me, status };
}

/** Boots the shell and mounts it on `#app`; no mount when the gate sent the page to the login. */
export async function boot(
  routeFiles: Record<string, AppRoutes>,
  catalogues: Record<string, AppCatalogue> = {},
  doc: Document = document,
): Promise<void> {
  const config = readSpaConfig(doc);
  const client = createLiveClient(config, { routes: OPERATION_ROUTES });
  const session = loadSession(client, doc);
  const { app, router } = await createShell({
    ...session,
    routes: appRoutes(routeFiles),
    messages: appMessages(catalogues),
    // The hub has no login of its own: the SaaS's, for this hub (Django fills it in spa-config).
    loginPath: config.loginUrl,
    // The apps of the hub as a grid at `/` (where the login lands without `next`).
    home: true,
    // The old hub's shell (PLAN-MIGRATIONS §13): no side menu; Back, the «My apps» sheet and the
    // user are in the topbar.
    nav: 'launcher',
    // Sign out is the Hub's: a form POST to `/auth/logout`, then the SaaS's logout page.
    userMenu: { logout },
  });
  provideLiveClient(client, app);
  try {
    await router.isReady();
  } catch (failure) {
    if (isNavigationFailure(failure)) return;
    throw failure;
  }
  app.mount('#app');
}

void boot(
  import.meta.glob<AppRoutes>('../apps/*/frontend/routes.ts', { eager: true }),
  import.meta.glob<AppCatalogue>('../apps/*/frontend/locale/*.json', { eager: true, import: 'default' }),
);
