// Entry of the hub SPA (`LIVE["spa"]["entry"]`): app routes and catalogues → shell, live client, session
// (`base.session.me`, a plain query: embedded by `base/spa.py`, else `GET /api/me`), mount.
// 🔴 Import order (hub#1060): the shell barrel goes first so its boot hooks wrap `customElements.define`
// before anything loads `@ionic/vue` (the SDK does). Vite hoists eager globs above everything, so an
// app's `routes.ts` only imports types; its pages load with `() => import(…)`. Guards: main.test.ts.
import {
  createShell,
  type CreateShellOptions,
  logout,
  type SessionMe,
  type SessionStatus,
  type ShellSidebar,
} from '@erplora/ui/shell';
import { createLiveClient, type LiveClient, provideLiveClient, readSpaConfig } from '@erplora/ui/sdk';
import { ref } from 'vue';
import { isNavigationFailure, type RouteRecordRaw } from 'vue-router';

import { OPERATION_ROUTES } from './generated/operation-routes';

/**
 * The old hub's side menu (PLAN-MIGRATIONS §16): the platform's entries in its two groups — Home (the
 * shell's, first), Employees, Files · My plan, Apps, System, Settings — and never a module (they open
 * from «My apps» and Home). The shell paints an entry only once its screen exists in the router, so
 * each appears by itself when `base` brings it.
 */
export const SIDEBAR: ShellSidebar = {
  groups: [
    [
      { id: 'employees', labelKey: 'sidebar.employees', icon: 'ion:people-outline', to: '/employees' },
      { id: 'files', labelKey: 'sidebar.files', icon: 'ion:folder-outline', to: '/files' },
    ],
    [
      { id: 'billing', labelKey: 'sidebar.billing', icon: 'ion:card-outline', to: '/billing' },
      { id: 'apps', labelKey: 'sidebar.apps', icon: 'ion:storefront-outline', to: '/apps' },
      { id: 'system', labelKey: 'sidebar.system', icon: 'ion:hardware-chip-outline', to: '/system' },
      { id: 'settings', labelKey: 'sidebar.settings', icon: 'ion:settings-outline', to: '/settings' },
    ],
  ],
};

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
    // The old hub's shell (PLAN-MIGRATIONS §16): its side menu, pinned from 992 px and a drawer below,
    // with the QR in its footer and the rail toggle and «My apps» in the topbar.
    sidebar: SIDEBAR,
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
