// What the tests that import main.ts (which boots on import) give its boot: the person whose session the page embeds,
// the page itself, the app and the router `createShell` hands back, and the shell and the SDK it boots with. `vi.mock`
// is hoisted above a file's imports, so each file takes those two with a dynamic import inside its factory.
import { vi } from 'vitest';

export const ME = { user: { id: 'u1', label: 'Ana' }, permissions: [], menu: [], apps: [], language: 'es' };

/** `@erplora/ui/shell`, whose `createShell` each file sets to hand back its fakes. */
export function shellModule() {
  return {
    createShell: vi.fn(),
    logout: vi.fn(),
    toastSuccess: vi.fn(),
    applyUserThemePreferences: vi.fn(),
    resetUserThemePreferences: vi.fn(),
  };
}

/** `@erplora/ui/sdk` as it is, with a live client that asks nothing and is provided to no real app. */
export async function sdkModule(importOriginal: () => Promise<unknown>) {
  return {
    ...((await importOriginal()) as object),
    createLiveClient: vi.fn(() => ({ api: { call: vi.fn() } })),
    provideLiveClient: vi.fn(),
  };
}

export function shellFakes() {
  const app = { mount: vi.fn(), config: {} };
  const router = {
    isReady: vi.fn(() => Promise.resolve()),
    addRoute: vi.fn(),
    beforeEach: vi.fn(),
    replace: vi.fn(() => Promise.resolve()),
    currentRoute: { value: { path: '/', fullPath: '/', query: {}, hash: '', meta: {} } },
  };
  return { app, router };
}

/** The page Django serves: its SPA config, the person's session and the mount point. */
export function embedPage(): void {
  document.body.innerHTML = `
  <script id="spa-config" type="application/json">{"csrfCookieName": "csrftoken", "lang": "es", "loginUrl": "/auth/login"}</script>
  <script id="session-me" type="application/json">${JSON.stringify(ME)}</script>
  <div id="app"></div>`;
}
