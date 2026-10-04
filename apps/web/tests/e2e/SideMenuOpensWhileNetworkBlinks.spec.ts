// Regression test for ERPlora/hub#2325 — a section of the side menu opens on the first tap even if
// the network blinks right at that moment.
//
// Every screen of the shell is loaded on demand, so before the fix tapping «Ajustes» in the side
// menu was the moment its file left for the network. If the connection blinked (CI: a storm of
// `net::ERR_NETWORK_CHANGED`) or the machine was too busy to fetch and compile it in time, the tap
// went nowhere and the person stayed on the screen they were on.
//
// The fix downloads the side menu's screens ahead of time, once the app is idle. This spec waits
// for the shell to go quiet, then cuts the network for every file of the web app — exactly the
// blink — and taps each section of the menu: each one has to open with nothing left to download.
//
// The injected failure is `net::ERR_CONNECTION_RESET`, as in `SectionRetryAfterNetworkBlink.spec.ts`,
// and deliberately not a network-change code: a bench retry that excuses network changes
// (hub#2324) can never retry a regression of this spec away.

import { test, expect, request as pwRequest, type Page } from '../bench-boot';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

interface Session {
  token: string;
  user: unknown;
}

/** REAL runtime session via `/api/auth/pin` (Demo user / PIN 000000 from the dev seed, hub#1929). */
async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '000000', device_id: 'e2e-browser-device' },
  });
  expect(res.ok(), `PIN login failed: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  expect(body.token, 'the runtime returned no session token').toBeTruthy();
  await api.dispose();
  return { token: body.token, user: body.user };
}

/** Injects the session the runtime issued (same keys as `lib/session.ts`). */
async function withSession(page: Page, s: Session): Promise<void> {
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [s.token, s.user] as const,
  );
}

/** A file of the web app itself (Vite serves it from the same origin), never a runtime call. */
function isWebAppFile(url: URL, webOrigin: string): boolean {
  return url.origin === webOrigin && !url.pathname.startsWith('/api/');
}

/**
 * Resolves once the web app has fetched nothing for `quietMs` in a row, with nothing in flight.
 * Without the fix it settles right after boot; with it, once the idle download has finished.
 */
async function webAppFilesSettle(page: Page, webOrigin: string, quietMs = 2_000, capMs = 60_000) {
  let inFlight = 0;
  let lastActivity = Date.now();
  const touch = (delta: number) => (url: string) => {
    if (!isWebAppFile(new URL(url), webOrigin)) return;
    inFlight += delta;
    lastActivity = Date.now();
  };
  const started = touch(1);
  const ended = touch(-1);
  page.on('request', (r) => started(r.url()));
  page.on('requestfinished', (r) => ended(r.url()));
  page.on('requestfailed', (r) => ended(r.url()));
  await expect
    .poll(() => inFlight <= 0 && Date.now() - lastActivity >= quietMs, { timeout: capMs, intervals: [250] })
    .toBe(true);
}

// The sections the side menu paints for the Demo user (labels in Spanish: the bench boots in `es`).
const SECTIONS: ReadonlyArray<{ label: string; path: string }> = [
  { label: 'Empleados', path: '/employees' },
  { label: 'Archivos', path: '/files' },
  { label: 'Mi plan', path: '/billing' },
  { label: 'Apps', path: '/apps' },
  { label: 'Sistema', path: '/system' },
  { label: 'Ajustes', path: '/settings' },
];

test.describe('the side menu while the network blinks (hub#2325)', () => {
  test('every section opens on the first tap once the app has been idle', async ({ page, baseURL }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await withSession(page, await loginByPin());
    const webOrigin = new URL(baseURL ?? 'http://localhost:5173').origin;

    await page.goto('/dashboard');
    await expect(page.locator('ion-item.nav-item').first()).toBeVisible();
    await webAppFilesSettle(page, webOrigin);

    // The blink: from here on not one file of the web app arrives.
    let cutRequests = 0;
    await page.route(
      (url) => isWebAppFile(url, webOrigin),
      (route) => {
        cutRequests += 1;
        return route.abort('connectionreset');
      },
    );

    for (const section of SECTIONS) {
      const item = page
        .locator('ion-item.nav-item')
        .filter({ has: page.locator('ion-label', { hasText: new RegExp(`^\\s*${section.label}\\s*$`) }) });
      await item.click();
      await expect(page, `«${section.label}» did not open`).toHaveURL(new RegExp(`${section.path}(#.*)?$`));
      await expect(item).toHaveAttribute('aria-current', 'page');
    }
    await expect(page.getByTestId('settings-country')).toBeVisible();
    expect(cutRequests, 'opening the menu sections still went to the network').toBe(0);

    // And Profile, which hangs off the user card at the top of the same menu. It opens with a
    // forward page transition whose animation Ionic downloads on first use; without it Ionic just
    // skips the animation, so here what has to hold is that the screen opens and paints.
    await page.locator('#sidebar-user-menu').click();
    await page.locator('ion-popover.sidebar-user-popover ion-item').filter({ hasText: 'Perfil' }).click();
    await expect(page, '«Perfil» did not open').toHaveURL(/\/profile(#.*)?$/);
    await expect(page.getByTestId('profile-change-photo')).toBeVisible();
  });
});
