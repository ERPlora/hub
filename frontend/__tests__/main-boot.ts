// What the tests that import main.ts (which boots on import) give its boot: the person whose session the page embeds,
// the page itself, and the app and the router `createShell` hands back (mocked in each test file).
import { vi } from 'vitest';

export const ME = { user: { id: 'u1', label: 'Ana' }, permissions: [], menu: [], apps: [], language: 'es' };

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
