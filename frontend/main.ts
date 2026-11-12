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
  stopNoticeListening,
  type ThemePalette,
  toastSuccess,
} from '@erplora/ui/shell';
import { assistantMessages, configureAssistant, forgetAssistant } from '@erplora/ui/components';
import { createLiveClient, type LiveClient, provideLiveClient, readSpaConfig } from '@erplora/ui/sdk';
import { defineAsyncComponent, ref, watch } from 'vue';
import { isNavigationFailure, type RouteRecordRaw } from 'vue-router';

import { onSessionChanged, readAccess, startWayIn } from '../base/frontend/lib/access';
import { APP_BLOCKED_ROUTE, appOfRouteFile, createAppGate } from '../base/frontend/lib/app-gate';
import { installErrorReport } from '../base/frontend/lib/error-report';
import { approvalPass } from '../base/frontend/lib/approval';
import { hubAssistant } from '../base/frontend/lib/assistant-hub';
import { type HubHome, readJsonBlock } from '../base/frontend/lib/home';
import { openReportProblem } from '../base/frontend/lib/report-problem';
import { allowedTo, useApiDocsShown } from '../base/frontend/lib/sidebar';
import { OPERATION_ROUTES } from './generated/operation-routes';

/**
 * The old hub's side menu: the platform's entries in its two groups — Home (the
 * shell's, first), Employees, Files · My plan, Apps, System, API, Settings — and never a module (they open
 * from «My apps» and Home). The shell paints an entry only once its screen exists in the router, so
 * each appears by itself when `base` brings it; and only for whoever may open it (`visible`: the permission
 * its screen's operation asks), «API» only while the business shows its API's documentation.
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
 * base's pieces of the chrome, as in the old hub: the assistant's sparkles and the bell at the end of the
 * topbar, «Upgrade plan» and right below it «Manage on erplora.com» in the menu's footer, the blocking strip over every
 * screen and, beside the pane, the device's notices and the assistant's panel. Each in its
 * own chunk, which `boot` loads beside the first screen's: the hub mounts once they are here (`chromeLoaded`).
 */
export const CHROME: NonNullable<CreateShellOptions['chrome']> = {
  topbar: defineAsyncComponent(() => import('../base/frontend/components/TopbarChrome.vue')),
  sidebarFooter: defineAsyncComponent(() => import('../base/frontend/components/SidebarFooter.vue')),
  notice: defineAsyncComponent(() => import('../base/frontend/components/BlockingStrip.vue')),
  background: defineAsyncComponent(() => import('../base/frontend/components/BackgroundChrome.vue')),
};

/**
 * Vue's own loader of a `defineAsyncComponent` (`__asyncLoader`): once it resolved, the wrapper paints its piece in the
 * same render as the screen. Internal to Vue (no public type), but it is how Vue itself tells an async wrapper
 * (`isAsyncWrapper`: KeepAlive, hydration) and what vue-router reads too; calling it again returns the same request.
 * Should a Vue upgrade drop it (or make it throw), the piece is simply not waited for (as before this wait), and
 * main.chrome.test.ts fails.
 */
type AsyncPiece = { __asyncLoader?: () => Promise<unknown> };

/** How long the hub waits for its chrome before mounting without it: a chunk left hanging never keeps it blank. */
export const CHROME_WAIT_MS = 3000;

/**
 * Loads the chrome's pieces, settled whether they load or not, for at most `CHROME_WAIT_MS`. The bell, the apps followed
 * beside the pane and the blocking strip read live queries: mounted with the screen, they go in its one stream; mounted
 * once their chunk arrived, more than 150 ms after the screen's queries on a slow device (the tab's CPU ×6), they cut it
 * and opened it again (FIX-HUB-BASE-HOME-ONE-STREAM-FLAKY). Through each piece's own loader, not another `import()`: a
 * module already here still resolves in a later task, after the stream opened. A piece that does not load never keeps
 * the hub from mounting: it loads again at render, and Vue hands that failure to base's report (`installErrorReport`);
 * one still loading past the wait paints when its chunk comes.
 */
export function chromeLoaded(pieces: object = CHROME): Promise<unknown> {
  // Called inside a promise's executor: a loader that throws (none of Vue's does) is a piece that failed, like one that
  // rejects, never a `boot` that dies before `app.mount`.
  const loaded = Promise.allSettled(
    Object.values(pieces).map((piece) => new Promise((resolve) => resolve((piece as AsyncPiece).__asyncLoader?.()))),
  );
  let timer: ReturnType<typeof setTimeout> | undefined;
  const waited = new Promise<void>((resolve) => {
    timer = setTimeout(() => {
      console.warn(`hub: base's chrome did not load within ${CHROME_WAIT_MS} ms; the hub mounts without it`);
      resolve();
    }, CHROME_WAIT_MS);
  });
  return Promise.race([loaded.finally(() => clearTimeout(timer)), waited]);
}

/**
 * The Hub's sign out: the assistant's conversation of the tab is forgotten (BASE-G120) and the installed app stops
 * listening with the screen off (HUB_APP-F26), waited for because once the form leaves this page is no longer the
 * linked hub and the app refuses its orders; then the shell's.
 */
export async function signOut(doc: Document = document): Promise<void> {
  forgetAssistant();
  await stopNoticeListening();
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

/** Every app catalogue, by the language in its file name, over the shared assistant's words (`assistant`, its panel's);
 *  distinct app ids, so a spread never collides. */
export function appMessages(catalogues: Record<string, AppCatalogue>): CreateShellOptions['messages'] {
  const messages: Record<string, AppCatalogue> = { en: { ...assistantMessages.en }, es: { ...assistantMessages.es } };
  for (const [file, catalogue] of Object.entries(catalogues)) {
    const language = file.slice(file.lastIndexOf('/') + 1, -'.json'.length);
    messages[language] = { ...messages[language], ...catalogue };
  }
  return messages;
}

/**
 * The user menu: «Profile» (the person's page in this hub) and, on a shared till of a business that asks,
 * «Switch user», both from `hub-home`'s `access`; then the person's account, erplora.com's
 * page, opened from the address `base/spa.py` embeds only in a session opened with the account (a new
 * tab; the system browser in the installed app), and with it «Report a problem», base's own dialog,
 * since only that session has an account for support to answer to; then the Hub's sign out, a form POST
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
  // The shared assistant's panel as the Hub's: its routes, base's operations and words, who uses it.
  configureAssistant(hubAssistant(doc));
  // A manager's approval: the pass of the command being repeated travels in `X-Elevation-Token`.
  const client = createLiveClient(config, { routes: OPERATION_ROUTES, getElevationToken: approvalPass });
  const { reload, ...session } = loadSession(client, doc);
  const chrome = chromeLoaded();
  const { app, router } = await createShell({
    ...session,
    routes: appRoutes(routeFiles),
    messages: appMessages(catalogues),
    // The hub has no login of its own: the SaaS's, for this hub (Django fills it in spa-config).
    loginPath: config.loginUrl,
    // «Home» first in the menu, and the shell's grid of apps as the fallback of `/` (where the login lands
    // without `next`): base's Home (base/frontend/routes.ts) is registered before it and wins `/`.
    home: true,
    // The old hub's shell: its side menu, pinned from 992 px and a drawer below,
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
  await chrome;
  app.mount('#app');
  // base's way in: the idle lock of a till, the person's appearance, «Now serving» after a switch.
  startWayIn(doc, {
    translate: (key, values) => (app.config.globalProperties as unknown as { $t: Translate }).$t(key, values),
    logout: () => void signOut(doc),
    toast: (message) => void toastSuccess(message),
    paint: (mode, palette, scale) => applyUserThemePreferences(mode, palette as ThemePalette | null, undefined, scale),
    reset: resetUserThemePreferences,
    label: () => session.session.value?.user?.label,
  });
  onSessionChanged(() => void reload());
  // The server writes the texts of every live read in the stream's language (BASE-F64, hub#1038): a session back in
  // another language reopens the tab's one stream, so the checklist, the panels and the bell answer in it at once,
  // whichever screens are mounted.
  watch(
    () => session.session.value?.language,
    (language, previous) => {
      if (language && previous && language !== previous) client.stream.reconnect();
    },
  );
}

type Translate = (key: string, values?: Record<string, unknown>) => string;

void boot(
  import.meta.glob<AppRoutes>(['../base/frontend/routes.ts', '../apps/*/frontend/routes.ts'], { eager: true }),
  import.meta.glob<AppCatalogue>(['../base/frontend/locale/*.json', '../apps/*/frontend/locale/*.json'], {
    eager: true,
    import: 'default',
  }),
);
