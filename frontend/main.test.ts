// The hub SPA entry: app routes → shell, live client from spa-config, session from the
// `session-me` JSON Django embeds (or GET /api/me), mount only once the router is ready.
// `base.session.me` is a plain query, not a live one: the session is a snapshot of the page load.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createMemoryHistory, createRouter, type NavigationFailure, type RouteRecordRaw } from 'vue-router';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => ({ client: { api: { call: (() => undefined) as (...args: unknown[]) => unknown } } }));

vi.mock('@erplora/ui/shell', () => ({
  createShell: vi.fn(),
  logout: vi.fn(),
  toastSuccess: vi.fn(),
  applyUserThemePreferences: vi.fn(),
  resetUserThemePreferences: vi.fn(),
}));
vi.mock('@erplora/ui/sdk', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  createLiveClient: vi.fn(() => sdk.client),
  provideLiveClient: vi.fn(),
}));

import { createShell, logout } from '@erplora/ui/shell';
import { ApiError, createLiveClient, provideLiveClient } from '@erplora/ui/sdk';
import { approvalPass } from '../base/frontend/lib/approval';

import { sessionChanged } from '../base/frontend/lib/access';
import { APP_BLOCKED_ROUTE } from '../base/frontend/lib/app-gate';
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
let importBoot: ReturnType<typeof shellOptions>;

beforeAll(async () => {
  sdk.client.api.call = vi.fn();
  renderShellHtml();
  fakeShell();
  main = await import('./main');
  importBoot = shellOptions();
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
  it('boots on import with the routes Vite globs from apps/*/frontend/routes.ts (the demo pages among them)', () => {
    const routes = importBoot.routes as RouteRecordRaw[];
    expect(routes.map((r) => r.path)).toEqual(expect.arrayContaining(['/demo/items', '/demo/items/:id']));
  });

  it("boots with base's Home at `/`: its route goes before the shell's grid, under a name of its own (APP-BASE-1)", () => {
    const routes = importBoot.routes as RouteRecordRaw[];
    const home = routes.filter((r) => r.path === '/');
    expect(home.map((r) => [r.name, r.meta?.auth])).toEqual([['base-home', true]]);
    // The shell's grid (`home: true`) stays registered after it, as the fallback of `/` and «Home» first in the menu.
    expect(importBoot.home).toBe(true);
  });

  it("plugs base's pieces into the chrome: the bell in the topbar, «Upgrade plan» in the menu, the blocking strip and the device's notices", () => {
    const chrome = importBoot.chrome as Record<string, unknown>;
    expect(Object.keys(chrome).sort()).toEqual(['background', 'notice', 'sidebarFooter', 'topbar']);
    for (const piece of Object.values(chrome)) expect(piece).toBeTruthy();
  });

  it("on import, globs base's catalogue next to the apps' (the Home would show raw keys otherwise)", () => {
    const messages = importBoot.messages as Record<string, { base: { home: { title: string } } }>;
    expect([messages.en.base.home.title, messages.es.base.home.title]).toEqual(['Home', 'Inicio']);
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
      en: { demo: { items: { title: 'Demo items' } }, zeta: { title: 'Zeta' } },
      es: { demo: { items: { title: 'Elementos' } }, zeta: { title: 'Zeta ES' } },
    });
  });

  it('on import, globs the real app catalogues (the demo pages would show raw keys otherwise)', () => {
    const messages = importBoot.messages as Record<string, { demo: { items: { title: string } } }>;
    expect([messages.en.demo.items.title, messages.es.demo.items.title]).toEqual(['Demo items', 'Elementos']);
  });

  it('builds the live client from spa-config with the generated op → route map and provides it to the app', async () => {
    const { app } = fakeShell();
    await main.boot({});
    expect(createLiveClient).toHaveBeenCalledWith(expect.objectContaining({ csrfCookieName: 'csrftoken', lang: 'es' }), {
      routes: OPERATION_ROUTES,
      getElevationToken: approvalPass,
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

  // PLAN-MIGRATIONS §16 (Ioan, 2026-10-17): the old hub's shell, side menu included. Its entries are the
  // platform's, in the old hub's two groups and order, never a module (they open from «My apps» and
  // Home); each shows once its screen exists (the shell checks the router), so today only Home does.
  it("paints the old hub's side menu: the platform's entries in its two groups, no module", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().sidebar).toEqual({
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
    });
    expect(shellOptions()).not.toHaveProperty('nav');
  });

  it("without this hub's addresses on erplora.com (no hub-home), the user menu has only the Hub's sign out", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().userMenu).toEqual({ logout });
  });

  // PLAN-SAAS §1.1: «Report a problem» is the SaaS's form (saas `/report-a-problem`), and the account lives there
  // too: the Hub links both, in a new tab, from the addresses base/spa.py embeds (never written here).
  it("gives the user menu «My account» and «Report a problem» on erplora.com, then the Hub's sign out", async () => {
    const home = {
      name: 'Bar A',
      plan_url: 'https://erplora.com/store/plans?business=h1',
      account_url: 'https://erplora.com/account',
      report_url: 'https://erplora.com/report-a-problem',
    };
    document.body.insertAdjacentHTML('beforeend', `<script id="hub-home" type="application/json">${JSON.stringify(home)}</script>`);
    fakeShell();
    await main.boot({});
    expect(shellOptions().userMenu).toEqual({
      items: [
        // APP-BASE-3 (BASE-G125): «Profile», the person's own page in this hub, first.
        { id: 'profile', labelKey: 'base.userMenu.profile', icon: 'ion:person-circle-outline', to: '/profile' },
        { id: 'account', labelKey: 'base.userMenu.account', icon: 'ion:person-outline', href: home.account_url },
        { id: 'report', labelKey: 'base.userMenu.reportProblem', icon: 'ion:chatbubbles-outline', href: home.report_url },
      ],
      logout,
    });
  });

  // APP-BASE-3 (BASE-G60, gh:hub#2506): a PIN session on a shared till has «Switch user» and never erplora.com's pages.
  it('on a till, the user menu has «Profile» and «Switch user», and nothing of erplora.com', async () => {
    const home = {
      name: 'Bar A',
      plan_url: '',
      account_url: '',
      report_url: '',
      access: { credential: 'pin', switch_user: true, idle_minutes: null },
    };
    document.body.insertAdjacentHTML('beforeend', `<script id="hub-home" type="application/json">${JSON.stringify(home)}</script>`);
    fakeShell();
    await main.boot({});
    expect(shellOptions().userMenu).toEqual({
      items: [
        { id: 'profile', labelKey: 'base.userMenu.profile', icon: 'ion:person-circle-outline', to: '/profile' },
        { id: 'switch-user', labelKey: 'base.userMenu.switchUser', icon: 'ion:people-outline', to: '/switch-user' },
      ],
      logout,
    });
  });

  // APP-BASE-3 (BASE-G59): once mounted, a till of a business that always asks signs out after its idle minutes.
  it('arms the idle lock of the session once mounted', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    try {
      const home = { name: 'Bar A', access: { credential: 'pin', switch_user: true, idle_minutes: 1 } };
      document.body.insertAdjacentHTML('beforeend', `<script id="hub-home" type="application/json">${JSON.stringify(home)}</script>`);
      fakeShell();
      await main.boot({});
      expect(logout).not.toHaveBeenCalled();
      vi.advanceTimersByTime(60_000);
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

  // APP-BASE-3 (BASE-G125): saving one's name in «My profile» renames the side menu at once, without a reload.
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

  // ── The app gate (APP-BASE-4: BASE-G132, G134) ──

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

  it("hands the screen's uncaught errors to base's report before mounting (BASE-G95)", async () => {
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

describe('import order guards (hub#1060)', () => {
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

describe('app catalogue guards', () => {
  it('keeps base/frontend/locale/<lang>.json under base and every apps/<id>/frontend/locale/<lang>.json under its own <id>, so merging apps never collides', () => {
    const appsDir = join(HERE, '..', 'apps');
    const baseLocale = join(HERE, '..', 'base', 'frontend', 'locale');
    const catalogues = readdirSync(appsDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && existsSync(join(appsDir, entry.name, 'frontend', 'locale')))
      .flatMap((entry) => {
        const dir = join(appsDir, entry.name, 'frontend', 'locale');
        return readdirSync(dir)
          .filter((name) => name.endsWith('.json'))
          .map((name) => ({ app: entry.name, file: join(dir, name) }));
      })
      .concat(
        (existsSync(baseLocale) ? readdirSync(baseLocale) : [])
          .filter((name) => name.endsWith('.json'))
          .map((name) => ({ app: 'base', file: join(baseLocale, name) })),
      );
    expect(catalogues.map(({ app }) => app)).toContain('base');
    for (const { app, file } of catalogues) {
      expect(Object.keys(JSON.parse(readFileSync(file, 'utf8')) as object), file).toEqual([app]);
    }
  });
});
