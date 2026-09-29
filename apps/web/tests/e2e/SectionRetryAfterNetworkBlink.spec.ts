// Regression test for ERPlora/hub#2312 — a section that failed on a network blink opens on the
// retry the toast asks for.
//
// With the hub already open, a person taps a section just as the network blinks. The file behind
// that section dies on the wire, the navigation is aborted and a toast says "check your connection
// and try again". Before the fix, trying again with the network back failed forever: the browser
// remembers a module URL that failed for the life of the DOCUMENT, so the second tap re-ran the
// same `import()` and it rejected WITHOUT a request (measured in the probe of hub#2296). Only a
// reload of the whole page got the section back, and the toast never said so.
//
// This is the only layer that can prove it: the "remembered as failed" part is the browser's
// module map, which the unit tests (`src/router/*hub2312*`) can only stand in for.
//
// The injected failure is `net::ERR_CONNECTION_RESET`, the same one `BenchBootRecovery.spec.ts`
// uses, and deliberately not a network-change code: a bench retry that excuses network changes
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

test.describe('a section that failed on a network blink (hub#2312)', () => {
  test('opens on the next tap once the network is back', async ({ page }) => {
    await withSession(page, await loginByPin());

    // The module of the Settings screen itself — not its `?vue&type=style` halves, which the
    // browser only asks for once the module arrives. Killed ONCE: the network blinks, then is fine.
    let settingsModuleRequests = 0;
    await page.route(
      (url) => url.pathname.endsWith('/src/views/SettingsPage.vue') && !url.searchParams.has('vue'),
      async (route) => {
        settingsModuleRequests += 1;
        if (settingsModuleRequests === 1) return route.abort('connectionreset');
        return route.continue();
      },
    );

    await page.goto('/dashboard');
    const toSettings = page.locator('ok-widget-board').getByTestId('dashboard-blueprint-cta');
    await expect(toSettings).toBeVisible();

    // 1 · The blink. The person stays on the dashboard and is told the section did not open.
    await toSettings.click();
    await expect(page.locator('ion-toast:not(.overlay-hidden)')).toHaveCount(1);
    await expect(page).toHaveURL(/\/dashboard$/);
    expect(settingsModuleRequests).toBe(1);

    // 2 · They try again, as the toast says. Before the fix this made NO request and failed again.
    await toSettings.click();

    await expect(page).toHaveURL(/\/settings#data$/);
    await expect(page.getByTestId('import-lead')).toBeVisible();
    expect(settingsModuleRequests, 'the retry never went back to the network for the section').toBe(2);
  });
});
