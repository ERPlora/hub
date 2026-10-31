// The hub waits for base's chrome, but not for ever (FIX-HUB-BASE-HOME-ONE-STREAM-FLAKY, hub#473's review): a chunk the
// network leaves hanging, never loaded and never failed, would keep the hub from mounting and the page blank. Past
// `CHROME_WAIT_MS` it mounts with what is here; the piece comes when its chunk does. Its own file: the piece's module
// hangs from the first import of main.ts, which boots on import (main.chrome.test.ts holds one that arrives).
import { afterAll, describe, expect, it, vi } from 'vitest';

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
// Each piece a stub of its own (`__esModule`: Vue takes `default` from a module it recognises); the one beside the pane
// never settles.
vi.mock('../base/frontend/components/TopbarChrome.vue', () => ({ __esModule: true, default: { render: () => null } }));
vi.mock('../base/frontend/components/UpgradePlanLink.vue', () => ({ __esModule: true, default: { render: () => null } }));
vi.mock('../base/frontend/components/BlockingStrip.vue', () => ({ __esModule: true, default: { render: () => null } }));
vi.mock('../base/frontend/components/BackgroundChrome.vue', () => new Promise(() => undefined));

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
const warned = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

// The wait's clock is the test's: the boot starts it, so the timers are fake before main.ts is imported. Imported with
// the file, out of any test's or hook's clock (main.chrome.test.ts says why).
vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
document.body.innerHTML = `
  <script id="spa-config" type="application/json">{"csrfCookieName": "csrftoken", "lang": "es", "loginUrl": "/auth/login"}</script>
  <script id="session-me" type="application/json">${JSON.stringify(ME)}</script>
  <div id="app"></div>`;
vi.mocked(createShell).mockResolvedValue({ app, router } as never);
const main = await import('./main');

afterAll(() => {
  vi.useRealTimers();
  warned.mockRestore();
});

describe("main.ts — base's chrome is waited for, not for ever", () => {
  it('mounts #app once CHROME_WAIT_MS passed with a piece whose chunk never settles, and says so', async () => {
    // Until the boot reaches the router; not `vi.waitFor`, which moves fake timers on (`setImmediate` is a real one).
    for (let turn = 0; turn < 1000 && router.isReady.mock.calls.length === 0; turn += 1) {
      await new Promise((resolve) => setImmediate(resolve));
    }
    expect(router.isReady).toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(main.CHROME_WAIT_MS - 1);
    expect(app.mount).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(app.mount).toHaveBeenCalledExactlyOnceWith('#app');
    expect(warned).toHaveBeenCalledWith(expect.stringContaining('chrome'));
  });
});
