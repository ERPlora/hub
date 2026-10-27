// Entry of the hub SPA (`LIVE["spa"]["entry"]`): app routes and catalogues → shell, live client, session
// (`base.session.me`, a plain query: embedded by `base/spa.py`, else `GET /api/me`), mount.
// 🔴 Import order (hub#1060): the shell barrel goes first so its boot hooks wrap `customElements.define`
// before anything loads `@ionic/vue` (the SDK does). Vite hoists eager globs above everything, so an
// app's `routes.ts` only imports types; its pages load with `() => import(…)`. Guards: main.test.ts.
import {
  applyUserThemePreferences,
  createShell,
  type CreateShellOptions,
  logout,
  resetUserThemePreferences,
  type SessionMe,
  type SessionStatus,
  type ShellSidebar,
  type ShellUserMenu,
  type ShellUserMenuItem,
  type ThemePalette,
  toastSuccess,
} from '@erplora/ui/shell';
import { createLiveClient, type LiveClient, provideLiveClient, readSpaConfig } from '@erplora/ui/sdk';
import { defineAsyncComponent, ref } from 'vue';
import { isNavigationFailure, type RouteRecordRaw } from 'vue-router';

import { onSessionChanged, readAccess, startWayIn } from '../base/frontend/lib/access';
import { forgetAssistant } from '../base/frontend/lib/assistant';
import { APP_BLOCKED_ROUTE, appOfRouteFile, createAppGate } from '../base/frontend/lib/app-gate';
import { installErrorReport } from '../base/frontend/lib/error-report';
import { approvalPass } from '../base/frontend/lib/approval';
import { type HubHome, readJsonBlock } from '../base/frontend/lib/home';
import { openReportProblem } from '../base/frontend/lib/report-problem';
import { allowedTo, useApiDocsShown } from '../base/frontend/lib/sidebar';
import { OPERATION_ROUTES } from './generated/operation-routes';

/**
 * The old hub's side menu (PLAN-MIGRATIONS §16): the platform's entries in its two groups — Home (the
 * shell's, first), Employees, Files · My plan, Apps, System, API, Settings — and never a module (they open
 * from «My apps» and Home). The shell paints an entry only once its screen exists in the router, so
 * each appears by itself when `base` brings it; and only for whoever may open it (`visible`: the permission
 * its screen's operation asks, APP-BASE-5), «API» only while the business shows its API's documentation.
 * My plan has no screen in the Hub yet: it asks nothing until it has one.
 */
export const SIDEBAR: ShellSidebar = {
  groups: [
    [
      { id: 'employees', labelKey: 'sidebar.employees', icon: 'ion:people-outline', to: '/employees', visible: allowedTo('base.view_home') },
      { id: 'files', labelKey: 'sidebar.files', icon: 'ion:folder-outline', to: '/files', visible: allowedTo('base.view_files') },
    ],
    [
      { id: 'billing', labelKey: 'sidebar.billing', icon: 'ion:card-outline', to: '/billing' },
      { id: 'apps', labelKey: 'sidebar.apps', icon: 'ion:storefront-outline', to: '/apps', visible: allowedTo('base.view_home') },
      { id: 'system', labelKey: 'sidebar.system', icon: 'ion:hardware-chip-outline', to: '/system', visible: allowedTo('base.administer_hub') },
      { id: 'api', labelKey: 'sidebar.api', icon: 'ion:code-slash-outline', to: '/api-docs', visible: useApiDocsShown },
      { id: 'settings', labelKey: 'sidebar.settings', icon: 'ion:settings-outline', to: '/settings', visible: allowedTo('base.view_home') },
    ],
  ],
};

/**
 * base's pieces of the chrome (APP-BASE-1, the old hub's): the assistant's sparkles and the bell at the end of the
 * topbar, «Upgrade plan» in the menu's footer, the blocking strip over every screen and, beside the pane, the device's
 * notices (APPOINTMENT-F28) and the assistant's panel (APP-BASE-9). Loaded on demand: none is needed to paint.
 */
export const CHROME: NonNullable<CreateShellOptions['chrome']> = {
  topbar: defineAsyncComponent(() => import('../base/frontend/components/TopbarChrome.vue')),
  sidebarFooter: defineAsyncComponent(() => import('../base/frontend/components/UpgradePlanLink.vue')),
  notice: defineAsyncComponent(() => import('../base/frontend/components/BlockingStrip.vue')),
  background: defineAsyncComponent(() => import('../base/frontend/components/BackgroundChrome.vue')),
};

/** The Hub's sign out: the assistant's conversation of the tab is forgotten first (BASE-G120), then the shell's. */
export function signOut(doc: Document = document): void {
  forgetAssistant();
  logout(doc);
}

/** An app's `frontend/routes.ts` default-exports its routes → pages, and nothing else. */
export type AppRoutes = { default: RouteRecordRaw[] };

/**
 * Every app's routes, in path order; a page needs a session unless its route says `auth: false`. Each app's carry
 * `meta.app`, its folder, which base's app gate checks (base's own carry none).
 */
export function appRoutes(routeFiles: Record<string, AppRoutes>): RouteRecordRaw[] {
  return Object.keys(routeFiles)
    .sort()
    .flatMap((file) => {
      const app = appOfRouteFile(file);
      return routeFiles[file].default.map(
        (route) => ({ ...route, meta: { auth: true, ...(app ? { app } : {}), ...route.meta } }) as RouteRecordRaw,
      );
    });
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

/**
 * The user menu: «Profile» (the person's page in this hub, BASE-G125) and, on a shared till of a business that asks,
 * «Switch user» (BASE-G60), both from `hub-home`'s `access` (APP-BASE-3); then the person's account, erplora.com's
 * page (PLAN-SAAS §1.1), opened from the address `base/spa.py` embeds only in a session opened with the account (a new
 * tab; the system browser in the installed app; gh:hub#2506), and with it «Report a problem», base's own dialog
 * (BASE-F108), since only that session has an account for support to answer to; then the Hub's sign out, a form POST
 * to `/auth/logout` once the assistant's conversation is forgotten (`signOut`). Without `hub-home` (no hub), only the sign out.
 */
export function userMenu(doc: Document): ShellUserMenu {
  const home = readJsonBlock<HubHome>('hub-home', doc);
  if (!home) return { logout: signOut };
  const items: ShellUserMenuItem[] = [
    { id: 'profile', labelKey: 'base.userMenu.profile', icon: 'ion:person-circle-outline', to: '/profile' },
  ];
  if (readAccess(doc).switch_user) {
    items.push({ id: 'switch-user', labelKey: 'base.userMenu.switchUser', icon: 'ion:people-outline', to: '/switch-user' });
  }
  if (home.account_url) {
    items.push(
      { id: 'account', labelKey: 'base.userMenu.account', icon: 'ion:person-outline', href: home.account_url },
      { id: 'report', labelKey: 'base.userMenu.reportProblem', icon: 'ion:chatbubbles-outline', run: openReportProblem },
    );
  }
  return { items, logout: signOut };
}

/** A failed `/api/me` ends in `error`, so the auth gate stops waiting and sends to the login. `reload` reads it again
 *  when base says the person changed (their name in «My profile», BASE-G125); a failed reload keeps the session it had. */
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
  const reload = () =>
    client.api.call('base.session.me', {}).then(
      (answer) => {
        me.value = answer;
      },
      (error: unknown) => console.error('hub: base.session.me failed', error),
    );
  return { session: me, status, reload };
}

/** Boots the shell and mounts it on `#app`; no mount when the gate sent the page to the login. */
export async function boot(
  routeFiles: Record<string, AppRoutes>,
  catalogues: Record<string, AppCatalogue> = {},
  doc: Document = document,
): Promise<void> {
  const config = readSpaConfig(doc);
  // A manager's approval (APP-BASE-5): the pass of the command being repeated travels in `X-Elevation-Token`.
  const client = createLiveClient(config, { routes: OPERATION_ROUTES, getElevationToken: approvalPass });
  const { reload, ...session } = loadSession(client, doc);
  const { app, router } = await createShell({
    ...session,
    routes: appRoutes(routeFiles),
    messages: appMessages(catalogues),
    // The hub has no login of its own: the SaaS's, for this hub (Django fills it in spa-config).
    loginPath: config.loginUrl,
    // «Home» first in the menu, and the shell's grid of apps as the fallback of `/` (where the login lands
    // without `next`): base's Home (base/frontend/routes.ts) is registered before it and wins `/`.
    home: true,
    // The old hub's shell (PLAN-MIGRATIONS §16): its side menu, pinned from 992 px and a drawer below,
    // with the QR in its footer and the rail toggle and «My apps» in the topbar.
    sidebar: SIDEBAR,
    userMenu: userMenu(doc),
    chrome: CHROME,
  });
  provideLiveClient(client, app);
  // base's report of the screen's own errors (BASE-G95): what nobody caught goes to the Hub's log by itself.
  installErrorReport(app);
  // base's app gate (BASE-G132, G134): a screen of an app the session gives `off` mounts «why it does not open» in
  // its address. The page's own after the shell's 404, so only reached by name; the first address is checked once
  // the router is ready, before mounting (the first navigation may have started before the guard was added).
  const appGate = createAppGate(session.session);
  router.addRoute(APP_BLOCKED_ROUTE);
  router.beforeEach(appGate);
  try {
    await router.isReady();
  } catch (failure) {
    if (isNavigationFailure(failure)) return;
    throw failure;
  }
  const blocked = appGate(router.currentRoute.value);
  if (blocked !== true) await router.replace(blocked);
  app.mount('#app');
  // base's way in (APP-BASE-3): the idle lock of a till, the person's appearance, «Now serving» after a switch.
  startWayIn(doc, {
    translate: (key, values) => (app.config.globalProperties as unknown as { $t: Translate }).$t(key, values),
    logout: () => signOut(doc),
    toast: (message) => void toastSuccess(message),
    paint: (mode, palette) => applyUserThemePreferences(mode, palette as ThemePalette | null),
    reset: resetUserThemePreferences,
    label: () => session.session.value?.user?.label,
  });
  onSessionChanged(() => void reload());
}

type Translate = (key: string, values?: Record<string, unknown>) => string;

void boot(
  import.meta.glob<AppRoutes>(['../base/frontend/routes.ts', '../apps/*/frontend/routes.ts'], { eager: true }),
  import.meta.glob<AppCatalogue>(['../base/frontend/locale/*.json', '../apps/*/frontend/locale/*.json'], {
    eager: true,
    import: 'default',
  }),
);
