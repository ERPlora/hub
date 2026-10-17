// The hub SPA entry: app routes → shell, live client from spa-config, session from the
// `session-me` JSON Django embeds (or GET /api/me), mount only once the router is ready.
// `base.session.me` is a plain query, not a live one: the session is a snapshot of the page load.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createMemoryHistory, createRouter, type NavigationFailure, type RouteRecordRaw } from 'vue-router';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => ({ client: { api: { call: (() => undefined) as (...args: unknown[]) => unknown } } }));

vi.mock('@erplora/ui/shell', () => ({ createShell: vi.fn(), logout: vi.fn() }));
vi.mock('@erplora/ui/sdk', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  createLiveClient: vi.fn(() => sdk.client),
  provideLiveClient: vi.fn(),
}));

import { createShell, logout } from '@erplora/ui/shell';
import { ApiError, createLiveClient, provideLiveClient } from '@erplora/ui/sdk';

import { OPERATION_ROUTES } from './generated/operation-routes';

type Main = typeof import('./main');

const HERE = dirname(fileURLToPath(import.meta.url));
const ME = { user: { id: 'u1', label: 'Ana' }, permissions: ['demo.view'], menu: [], apps: [], language: 'es' };
const page = { template: '<div />' };
const LOGIN_URL = '/auth/login';

function fakeShell(isReady: () => Promise<void> = () => Promise.resolve()) {
  const app = { mount: vi.fn() };
  const router = { isReady: vi.fn(isReady) };
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

  it("gives the user menu the Hub's sign out (a form POST to /auth/logout), and nothing else", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().userMenu).toEqual({ logout });
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

  it('keeps every apps/*/frontend/routes.ts free of runtime imports: Vite hoists eager globs above the shell', () => {
    const appsDir = join(HERE, '..', 'apps');
    const files = readdirSync(appsDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => join(appsDir, entry.name, 'frontend', 'routes.ts'))
      .filter((file) => existsSync(file));
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      const staticImports = [...source.matchAll(/^import\s+(?!type\b).*$/gm)].map((m) => m[0]);
      expect(staticImports, `${file}: pages load with () => import('./pages/…')`).toEqual([]);
    }
  });
});

describe('app catalogue guards', () => {
  it('keeps every apps/<id>/frontend/locale/<lang>.json under its own <id>, so merging apps never collides', () => {
    const appsDir = join(HERE, '..', 'apps');
    const catalogues = readdirSync(appsDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && existsSync(join(appsDir, entry.name, 'frontend', 'locale')))
      .flatMap((entry) => {
        const dir = join(appsDir, entry.name, 'frontend', 'locale');
        return readdirSync(dir)
          .filter((name) => name.endsWith('.json'))
          .map((name) => ({ app: entry.name, file: join(dir, name) }));
      });
    expect(catalogues.length).toBeGreaterThan(0);
    for (const { app, file } of catalogues) {
      expect(Object.keys(JSON.parse(readFileSync(file, 'utf8')) as object), file).toEqual([app]);
    }
  });
});
