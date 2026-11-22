// The hub SPA entry: app routes → shell, live client from spa-config, session from the
// `session-me` JSON Django embeds (or GET /api/me), mount only once the router is ready.
// `base.session.me` is a plain query, not a live one: the session is a snapshot of the page load.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { nextTick } from 'vue';
import { createMemoryHistory, createRouter, type NavigationFailure, type RouteRecordRaw } from 'vue-router';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => ({ client: { api: { call: (() => undefined) as (...args: unknown[]) => unknown } } }));

vi.mock('@erplora/ui/shell', () => ({
  createShell: vi.fn(),
  logout: vi.fn(),
  stopNoticeListening: vi.fn(async () => {}),
  toastSuccess: vi.fn(),
  applyUserThemePreferences: vi.fn(),
  resetUserThemePreferences: vi.fn(),
}));
// base's side menu (base/frontend/lib/sidebar.test.ts declares and runs it): here, only that main hands it to the shell.
vi.mock('../base/frontend/lib/sidebar', () => ({
  SIDEBAR: 'SIDEBAR',
  shellSidebar: (sidebar: unknown) => ({ shellSidebarOf: sidebar }),
}));
vi.mock('@erplora/ui/sdk', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  createLiveClient: vi.fn(() => sdk.client),
  provideLiveClient: vi.fn(),
}));

import { createShell, logout, stopNoticeListening } from '@erplora/ui/shell';
import { ApiError, createLiveClient, provideLiveClient } from '@erplora/ui/sdk';
import { assistantConfig, assistantMessages, configureAssistant } from '@erplora/ui/components';
import { approvalPass } from '../base/frontend/lib/approval';
import { HUB_ASSISTANT } from '../base/frontend/lib/assistant-hub';

import { sessionChanged } from '../base/frontend/lib/access';
import { APP_BLOCKED_ROUTE } from '../base/frontend/lib/app-gate';
import { openReportProblem, reportProblemOpen } from '../base/frontend/lib/report-problem';
import { OPERATION_ROUTES } from './generated/operation-routes';

type Main = typeof import('./main');

const HERE = dirname(fileURLToPath(import.meta.url));
const ME = { user: { id: 'u1', label: 'Ana' }, permissions: ['demo.view'], menu: [], apps: [], language: 'es' };
const page = { template: '<div />' };
const LOGIN_URL = '/auth/login';

function fakeShell(isReady: () => Promise<void> = () => Promise.resolve(), current: object = { path: '/', meta: {} }) {
  const app = { mount: vi.fn(), config: {} as { errorHandler?: unknown } };
  const router = {
    isReady: vi.fn(isReady),
    addRoute: vi.fn(),
    beforeEach: vi.fn(),
    replace: vi.fn(() => Promise.resolve()),
    currentRoute: { value: { fullPath: '/', query: {}, hash: '', ...current } },
  };
  vi.mocked(createShell).mockResolvedValue({ app, router } as never);
  return { app, router };
}

function shellOptions() {
  return vi.mocked(createShell).mock.calls.at(-1)![0];
}

function renderShellHtml(session: object | null = ME) {
  document.body.innerHTML = `
    <script id="spa-config" type="application/json">{"csrfCookieName": "csrftoken", "lang": "es", "loginUrl": "${LOGIN_URL}"}</script>
    ${session ? `<script id="session-me" type="application/json">${JSON.stringify(session)}</script>` : ''}
    <div id="app"></div>`;
}

let main: Main;

/** Boots the Hub under the fake shell with `home` as the `hub-home` block base/spa.py embeds in the page. */
async function bootWithHome(home: object): Promise<void> {
  document.body.insertAdjacentHTML('beforeend', `<script id="hub-home" type="application/json">${JSON.stringify(home)}</script>`);
  fakeShell();
  await main.boot({});
}

/** «Profile», the person's own page in this hub, first in every user menu. */
const PROFILE_ITEM = { id: 'profile', labelKey: 'base.userMenu.profile', icon: 'ion:person-circle-outline', to: '/profile' };

beforeAll(async () => {
  sdk.client.api.call = vi.fn();
  renderShellHtml();
  fakeShell();
  main = await import('./main');
});

beforeEach(() => {
  vi.clearAllMocks();
  sdk.client.api.call = vi.fn();
  renderShellHtml();
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('main.ts', () => {
  // From the menu and from the idle lock alike.
  it('signing out forgets the conversation with the assistant, then leaves', async () => {
    sessionStorage.setItem('erplora.assistant.history', JSON.stringify({ user: 'u1', bubbles: [], conversation: [] }));
    await main.signOut();
    expect(sessionStorage.getItem('erplora.assistant.history')).toBeNull();
    expect(logout).toHaveBeenCalledOnce();
  });

  // HUB_APP-F26 (hub#836): once the form leaves, this page is no longer the linked hub and the app refuses its orders.
  it('signing out stops the listening with the screen off and waits for the app before leaving', async () => {
    let stopped!: () => void;
    vi.mocked(stopNoticeListening).mockReturnValueOnce(new Promise<void>((resolve) => (stopped = resolve)));

    const leaving = main.signOut();
    await Promise.resolve();
    expect(stopNoticeListening).toHaveBeenCalledOnce();
    expect(logout).not.toHaveBeenCalled();

    stopped();
    await leaving;
    expect(logout).toHaveBeenCalledOnce();
  });

  it('collects the routes of every app, in path order, behind a session by default', async () => {
    fakeShell();
    await main.boot({
      '../apps/zeta/frontend/routes.ts': { default: [{ path: '/zeta', component: page }] },
      '../apps/alpha/frontend/routes.ts': {
        default: [
          { path: '/alpha', component: page },
          { path: '/alpha/public', component: page, meta: { auth: false } },
        ],
      },
    });
    const routes = shellOptions().routes as RouteRecordRaw[];
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/alpha', true],
      ['/alpha/public', false],
      ['/zeta', true],
    ]);
  });

  it('feeds the shell every app catalogue, merged per language from apps/*/frontend/locale/<lang>.json', async () => {
    fakeShell();
    await main.boot(
      {},
      {
        '../apps/demo/frontend/locale/en.json': { demo: { items: { title: 'Demo items' } } },
        '../apps/demo/frontend/locale/es.json': { demo: { items: { title: 'Elementos' } } },
        '../apps/zeta/frontend/locale/en.json': { zeta: { title: 'Zeta' } },
        '../apps/zeta/frontend/locale/es.json': { zeta: { title: 'Zeta ES' } },
      },
    );
    expect(shellOptions().messages).toEqual({
      en: { ...assistantMessages.en, demo: { items: { title: 'Demo items' } }, zeta: { title: 'Zeta' } },
      es: { ...assistantMessages.es, demo: { items: { title: 'Elementos' } }, zeta: { title: 'Zeta ES' } },
    });
  });

  it("configures the shared assistant as the Hub's before the shell mounts (HUB_ASSISTANT)", async () => {
    const shell = fakeShell();
    configureAssistant(undefined);
    let configured: unknown;
    vi.mocked(createShell).mockImplementationOnce(async () => {
      configured = assistantConfig();
      return shell as never;
    });
    await main.boot({});
    expect(configured).toBe(HUB_ASSISTANT);
  });

  it('configures the server’s voice only when the page says there is one (hub-home server_voice)', async () => {
    document.body.insertAdjacentHTML('beforeend', `<script id="hub-home" type="application/json">${JSON.stringify({ server_voice: true })}</script>`);
    const shell = fakeShell();
    configureAssistant(undefined);
    let configured: { speak?: unknown } | undefined;
    vi.mocked(createShell).mockImplementationOnce(async () => {
      configured = assistantConfig();
      return shell as never;
    });
    await main.boot({});
    expect(typeof configured?.speak).toBe('function');
  });

  it('builds the live client from spa-config with the generated op → route map and provides it to the app', async () => {
    const { app } = fakeShell();
    await main.boot({});
    expect(createLiveClient).toHaveBeenCalledWith(expect.objectContaining({ csrfCookieName: 'csrftoken', lang: 'es' }), {
      routes: OPERATION_ROUTES,
      getElevationToken: approvalPass,
      reload: expect.any(Function),
    });
    expect(provideLiveClient).toHaveBeenCalledWith(sdk.client, app);
  });

  it('feeds the shell the session Django embedded, live at once and without a request', async () => {
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    expect(session.value).toEqual(ME);
    expect(status.value).toBe('live');
    expect(sdk.client.api.call).not.toHaveBeenCalled();
  });

  it("sends a visitor without a session to the Hub's jump to the SaaS login (spa-config.loginUrl), never the admin", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().loginPath).toBe(LOGIN_URL);
  });

  it("turns the shell's Home on: the apps grid at / (where the login lands)", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().home).toBe(true);
  });

  // The side menu is base's (each entry for whoever holds the permission its screen asks), never a module: modules open
  // from «My apps» and Home.
  it("paints base's side menu, as the shell takes it, and no module", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().sidebar).toEqual({ shellSidebarOf: 'SIDEBAR' });
    expect(shellOptions()).not.toHaveProperty('nav');
  });

  it("without this hub's addresses on erplora.com (no hub-home), the user menu has only the Hub's sign out", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().userMenu).toEqual({ logout: main.signOut });
  });

  // The account lives on erplora.com, which the Hub links in a new tab from the address base/spa.py
  // embeds (never written here); «Report a problem» is the Hub's own dialog, offered with it: only a
  // session opened with the account has an account for support to answer to.
  it("gives the user menu «My account» on erplora.com and «Report a problem» in the Hub, then the Hub's sign out", async () => {
    const home = {
      name: 'Bar A',
      plan_url: 'https://erplora.com/store/plans?business=h1',
      account_url: 'https://erplora.com/account',
    };
    await bootWithHome(home);
    expect(shellOptions().userMenu).toEqual({
      items: [
        PROFILE_ITEM,
        { id: 'account', labelKey: 'base.userMenu.account', icon: 'ion:person-outline', href: home.account_url },
        { id: 'report', labelKey: 'base.userMenu.reportProblem', icon: 'ion:chatbubbles-outline', run: openReportProblem },
      ],
      logout: main.signOut,
    });
  });

  it('«Report a problem» opens the dialog in the Hub, never an address of erplora.com', async () => {
    const home = { name: 'Bar A', plan_url: '', account_url: 'https://erplora.com/account' };
    await bootWithHome(home);
    const report = shellOptions().userMenu?.items?.find((item) => item.id === 'report');
    expect(report).not.toHaveProperty('href');
    expect(reportProblemOpen.value).toBe(false);
    report?.run?.();
    expect(reportProblemOpen.value).toBe(true);
    reportProblemOpen.value = false;
  });

  // A PIN session on a shared till has «Switch user» and never erplora.com's pages.
  it('on a till, the user menu has «Profile» and «Switch user», and nothing of erplora.com', async () => {
    const home = {
      name: 'Bar A',
      plan_url: '',
      account_url: '',
      access: { credential: 'pin', switch_user: true, idle_minutes: null },
    };
    await bootWithHome(home);
    expect(shellOptions().userMenu).toEqual({
      items: [
        PROFILE_ITEM,
        { id: 'switch-user', labelKey: 'base.userMenu.switchUser', icon: 'ion:people-outline', to: '/switch-user' },
      ],
      logout: main.signOut,
    });
  });

  // Once mounted, a till of a business that always asks signs out after its idle minutes.
  it('arms the idle lock of the session once mounted', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    try {
      const home = { name: 'Bar A', access: { credential: 'pin', switch_user: true, idle_minutes: 1 } };
      await bootWithHome(home);
      expect(logout).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(60_000);
      expect(stopNoticeListening).toHaveBeenCalledOnce();
      expect(logout).toHaveBeenCalledOnce();
    } finally {
      vi.useRealTimers();
    }
  });

  it('without an embedded session, asks GET /api/me (base.session.me) and goes live with its answer', async () => {
    renderShellHtml(null);
    let answer!: (me: object) => void;
    vi.mocked(sdk.client.api.call).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    fakeShell();
    await main.boot({});
    expect(sdk.client.api.call).toHaveBeenCalledExactlyOnceWith('base.session.me', {});
    const { session, status } = shellOptions();
    expect([session.value, status.value]).toEqual([undefined, 'loading']);
    answer(ME);
    await vi.waitFor(() => expect(status.value).toBe('live'));
    expect(session.value).toEqual(ME);
  });

  it('marks the session as errored when /api/me fails, so the gate stops waiting and sends to the login', async () => {
    renderShellHtml(null);
    vi.mocked(sdk.client.api.call).mockRejectedValue(new ApiError(0, 'network_error', 'Network error'));
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    await vi.waitFor(() => expect(status.value).toBe('error'));
    expect(session.value).toBeUndefined();
    expect(logged).toHaveBeenCalledWith('hub: base.session.me failed', expect.any(ApiError));
    logged.mockRestore();
  });

  // Saving one's name in «My profile» renames the side menu at once, without a reload.
  it('reads base.session.me again when base says the person changed, and the shell paints its answer', async () => {
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    vi.mocked(sdk.client.api.call).mockResolvedValue({ ...ME, user: { id: 'u1', label: 'Ana María' } });
    sessionChanged();
    expect(sdk.client.api.call).toHaveBeenCalledWith('base.session.me', {});
    await vi.waitFor(() => expect(session.value?.user?.label).toBe('Ana María'));
    expect(status.value).toBe('live');
  });

  // BASE-F64, BASE-F02 (hub#1038): the server writes the texts of every live read (the checklist, the panels, the bell)
  // in the stream's language, so a new language reopens the tab's one stream, whichever screens are mounted.
  it('reopens the live stream once when the session comes back in another language, and not for any other change', async () => {
    // Its own client: every boot of this file listens to `sessionChanged` on the same window.
    const own = { api: { call: vi.fn() }, stream: { reconnect: vi.fn() } };
    vi.mocked(createLiveClient).mockReturnValueOnce(own as never);
    vi.mocked(sdk.client.api.call).mockResolvedValue(ME);
    fakeShell();
    await main.boot({});
    const { session } = shellOptions();
    own.api.call.mockResolvedValue({ ...ME, user: { id: 'u1', label: 'Ana María' } });
    sessionChanged();
    await vi.waitFor(() => expect(session.value?.user?.label).toBe('Ana María'));
    await nextTick();
    expect(own.stream.reconnect).not.toHaveBeenCalled();
    own.api.call.mockResolvedValue({ ...ME, language: 'en' });
    sessionChanged();
    await vi.waitFor(() => expect(session.value?.language).toBe('en'));
    await nextTick();
    expect(own.stream.reconnect).toHaveBeenCalledOnce();
  });

  it('does not reopen the live stream for the first session it reads (no embedded one): the stream opens in it', async () => {
    renderShellHtml(null);
    let answer!: (me: object) => void;
    const own = { api: { call: vi.fn(() => new Promise((resolve) => (answer = resolve))) }, stream: { reconnect: vi.fn() } };
    vi.mocked(createLiveClient).mockReturnValueOnce(own as never);
    fakeShell();
    await main.boot({});
    const { status } = shellOptions();
    answer(ME);
    await vi.waitFor(() => expect(status.value).toBe('live'));
    await nextTick();
    expect(own.stream.reconnect).not.toHaveBeenCalled();
  });

  it('keeps the session it had when reading it again fails: a name not refreshed never signs anyone out', async () => {
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    vi.mocked(sdk.client.api.call).mockRejectedValue(new ApiError(0, 'network_error', 'Network error'));
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    sessionChanged();
    await vi.waitFor(() => expect(logged).toHaveBeenCalledWith('hub: base.session.me failed', expect.any(ApiError)));
    expect([session.value, status.value]).toEqual([ME, 'live']);
    logged.mockRestore();
  });

  it('mounts #app only after the router is ready, and after providing the live client', async () => {
    let ready!: () => void;
    const { app } = fakeShell(() => new Promise<void>((resolve) => (ready = resolve)));
    const booted = main.boot({});
    await vi.waitFor(() => expect(createShell).toHaveBeenCalled());
    await Promise.resolve();
    expect(app.mount).not.toHaveBeenCalled();
    ready();
    await booted;
    expect(app.mount).toHaveBeenCalledExactlyOnceWith('#app');
    expect(vi.mocked(provideLiveClient).mock.invocationCallOrder[0]).toBeLessThan(app.mount.mock.invocationCallOrder[0]);
  });

  it('does not mount when the auth gate cancels the first navigation (the page is going to the login)', async () => {
    const gate = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: page }] });
    gate.beforeEach(() => false);
    const cancelled = (await gate.push('/')) as NavigationFailure;
    const { app } = fakeShell(() => Promise.reject(cancelled));
    await expect(main.boot({})).resolves.toBeUndefined();
    expect(app.mount).not.toHaveBeenCalled();
  });

  // ── The app gate ──

  it("marks each app's routes with its app (meta.app), for the app gate; base's have none", async () => {
    fakeShell();
    await main.boot({
      '../base/frontend/routes.ts': { default: [{ path: '/apps', component: page }] },
      '../apps/cash_register/frontend/routes.ts': { default: [{ path: '/cash_register', component: page }] },
    });
    const routes = shellOptions().routes as RouteRecordRaw[];
    expect(routes.map((r) => [r.path, r.meta?.app])).toEqual([
      ['/cash_register', 'cash_register'],
      ['/apps', undefined],
    ]);
  });

  it("adds base's «why it does not open» after the shell's routes and guards every navigation with the app gate", async () => {
    const { router } = fakeShell();
    await main.boot({});
    expect(router.addRoute).toHaveBeenCalledExactlyOnceWith(APP_BLOCKED_ROUTE);
    expect(router.beforeEach).toHaveBeenCalledOnce();
  });

  it('checks the first address too, before mounting: a screen of an app that is off opens base’s page there', async () => {
    renderShellHtml({ ...ME, apps: [{ label: 'stock', state: 'off' }] });
    const { app, router } = fakeShell(undefined, { path: '/stock/items', fullPath: '/stock/items', meta: { app: 'stock' } });
    await main.boot({});
    expect(router.replace).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ name: APP_BLOCKED_ROUTE.name }));
    expect(router.replace.mock.invocationCallOrder[0]).toBeLessThan(app.mount.mock.invocationCallOrder[0]);
  });

  it('leaves the first address alone when its app is on', async () => {
    renderShellHtml({ ...ME, apps: [{ label: 'stock', state: 'on' }] });
    const { router } = fakeShell(undefined, { path: '/stock/items', meta: { app: 'stock' } });
    await main.boot({});
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("hands the screen's uncaught errors to base's report before mounting", async () => {
    const { app } = fakeShell();
    await main.boot({});
    expect(app.config.errorHandler).toBeTypeOf('function');
    expect(app.mount).toHaveBeenCalledOnce();
  });

  it('lets any other boot failure surface', async () => {
    fakeShell(() => Promise.reject(new Error('boom')));
    await expect(main.boot({})).rejects.toThrow('boom');
  });
});

describe('import order guards', () => {
  it('imports the shell before anything that loads @ionic/vue (the SDK, the generated routes)', () => {
    const source = readFileSync(join(HERE, 'main.ts'), 'utf8');
    const runtimeImports = [...source.matchAll(/^import\s+(?!type\b)[^;]*?from\s+'([^']+)';/gms)].map((m) => m[1]);
    expect(runtimeImports[0]).toBe('@erplora/ui/shell');
  });

  it('keeps base/frontend/routes.ts and every apps/*/frontend/routes.ts free of runtime imports: Vite hoists eager globs above the shell', () => {
    const appsDir = join(HERE, '..', 'apps');
    const files = readdirSync(appsDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => join(appsDir, entry.name, 'frontend', 'routes.ts'))
      .concat(join(HERE, '..', 'base', 'frontend', 'routes.ts'))
      .filter((file) => existsSync(file));
    expect(files).toContain(join(HERE, '..', 'base', 'frontend', 'routes.ts'));
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      const staticImports = [...source.matchAll(/^import\s+(?!type\b).*$/gm)].map((m) => m[0]);
      expect(staticImports, `${file}: pages load with () => import('./pages/…')`).toEqual([]);
    }
  });
});
