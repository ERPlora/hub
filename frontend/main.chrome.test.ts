// base's chrome mounts with the screen (FIX-HUB-BASE-HOME-ONE-STREAM-FLAKY): its pieces load on demand, but the hub
// mounts only once they are here. The bell (topbar) and the apps followed beside the pane (background) read live
// queries: mounted after the screen, they came more than 150 ms after its queries on a slow device, and the one live
// stream was cut and opened again with them (tests/e2e/base-home.spec.ts, «when base's chrome arrives late»). Its own
// file: the pieces' modules are held from the first import of main.ts, which boots on import.
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { createApp, h } from 'vue';

const chrome = vi.hoisted(() => {
  let arrive!: () => void;
  const late = new Promise<void>((resolve) => (arrive = resolve));
  return { late, arrive: () => arrive() };
});

vi.mock('@erplora/ui/shell', () => ({
  createShell: vi.fn(),
  logout: vi.fn(),
  toastSuccess: vi.fn(),
  applyUserThemePreferences: vi.fn(),
  resetUserThemePreferences: vi.fn(),
}));
vi.mock('@erplora/ui/sdk', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  createLiveClient: vi.fn(() => ({ api: { call: vi.fn() } })),
  provideLiveClient: vi.fn(),
}));
// Each piece a stub of its own (`__esModule`: Vue takes `default` from a module it recognises; Vitest's mock is not
// tagged `Module`). The one beside the pane is held until the test lets it arrive; «Upgrade plan» never loads (a
// chunk the network lost): the piece's own load reports it at render.
vi.mock('../base/frontend/components/TopbarChrome.vue', () => ({ __esModule: true, default: { render: () => null } }));
vi.mock('../base/frontend/components/BlockingStrip.vue', () => ({ __esModule: true, default: { render: () => null } }));
vi.mock('../base/frontend/components/BackgroundChrome.vue', async () => {
  await chrome.late;
  return { __esModule: true, default: { render: () => h('span', { 'data-testid': 'background-chrome' }) } };
});
vi.mock('../base/frontend/components/UpgradePlanLink.vue', () => {
  throw new Error('chunk lost');
});

import { createShell } from '@erplora/ui/shell';

const ME = { user: { id: 'u1', label: 'Ana' }, permissions: [], menu: [], apps: [], language: 'es' };
const app = { mount: vi.fn(), config: {} };
const router = {
  isReady: vi.fn(() => Promise.resolve()),
  addRoute: vi.fn(),
  beforeEach: vi.fn(),
  replace: vi.fn(() => Promise.resolve()),
  currentRoute: { value: { path: '/', fullPath: '/', query: {}, hash: '', meta: {} } },
};

let main: typeof import('./main');

// Importing main.ts boots it: out of the test's clock, which the module graph would eat on a loaded machine.
beforeAll(async () => {
  document.body.innerHTML = `
    <script id="spa-config" type="application/json">{"csrfCookieName": "csrftoken", "lang": "es", "loginUrl": "/auth/login"}</script>
    <script id="session-me" type="application/json">${JSON.stringify(ME)}</script>
    <div id="app"></div>`;
  vi.mocked(createShell).mockResolvedValue({ app, router } as never);
  main = await import('./main');
});

describe("main.ts — base's chrome mounts with the screen", () => {
  it('mounts #app only once the pieces of the chrome have loaded, and a piece that fails to load does not keep it from mounting', async () => {
    await vi.waitFor(() => expect(router.isReady).toHaveBeenCalled());
    // The router is ready and the other pieces are here: the one beside the pane is still on its way.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(app.mount).not.toHaveBeenCalled();

    chrome.arrive();
    await vi.waitFor(() => expect(app.mount).toHaveBeenCalledExactlyOnceWith('#app'));

    // Mounted, the piece paints in the same render as the screen around it, with no task in between: a module
    // imported again would resolve in a later one, after the screen's stream opened.
    const host = document.createElement('div');
    createApp({ render: () => h(main.CHROME.background!) }).mount(host);
    expect(host.querySelector('[data-testid="background-chrome"]')).not.toBeNull();
  });
});
