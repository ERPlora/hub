// **A reload has to get the photo credential back too** (hub#791).
//
// `setHubSession` mints the media cookie whenever a session STARTS, which covers every login. It
// does not cover the commonest case of all: the till that is already logged in and the browser is
// reloaded — the F5 at opening time, the webview restarted, the PWA resumed. No session starts
// there, the session was already in `localStorage`, so nothing would ask for the cookie and the
// grid would come up blank until the next login. On a shared till that can be days.
//
// So boot asks too. Asserted against the source of `main.ts` — the same technique
// `dashboard-import-refresh.test.ts` uses — because importing that module in a unit test would boot
// the entire shell: Ionic, the router, the service worker and the print listeners.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const main = readFileSync(fileURLToPath(new URL('../main.ts', import.meta.url)), 'utf8');

describe('boot asks for the media cookie', () => {
  it('imports it from the runtime module', () => {
    expect(main).toMatch(/import\s*\{[^}]*\bensureMediaCookie\b[^}]*\}\s*from\s*'\.\/lib\/runtime'/);
  });

  it('calls it while booting', () => {
    // `ensureMediaCookie` is a no-op without a session, so calling it unconditionally at boot is
    // safe: on the login screen it returns false without knocking on any door.
    expect(main).toMatch(/^\s*(void\s+)?ensureMediaCookie\(\)/m);
  });
});
