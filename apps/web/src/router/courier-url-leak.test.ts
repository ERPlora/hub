// @vitest-environment happy-dom
//
// hub#755 — the one-time courier survives boot inside the hub's own URL.
//
// QA reported it byte for byte on Android after `forget_hub`:
//   https://<hub>.a.erplora.com/dashboard?shell=1#courier=<REDACTED>
// and read it back over CDP seconds later. `takeCourierCode()` DOES scrub `window.location`, so
// this is not a race in QA's reading: it is a second writer putting the fragment back.
//
// The writer is Vue Router. `main.ts` imports `./router` (line 7), and ES imports are evaluated
// before the module body, so `createWebHistory()` snapshots `window.location` — courier fragment
// included — BEFORE the scrub on line 26 runs. A bare `history.replaceState` does not tell the
// router anything, so the router keeps the stale snapshot and replays it on its initial
// navigation, writing the credential back into the address bar.
//
// These tests therefore refuse to mock the router: mocking it is exactly what hid this. They boot
// the REAL router the way `main.ts` does, and look at where the credential ends up. Against the
// broken ordering they fail with QA's own URL:
//   http://localhost:3000/dashboard?shell=1#courier=opaque-code
//   /login?redirect=/dashboard?shell=1%23courier=opaque-code
// The second one is the variant nobody reported and the one that costs more.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp } from 'vue';

// The pages the initial navigation lands on are stubbed: this is a test about the URL, and the
// real SFCs drag in the whole Ionic + inline-icon pipeline for nothing. The ROUTER is real — that
// is the whole point.
vi.mock('../views/DashboardPage.vue', () => ({ default: { render: () => null } }));
vi.mock('../views/LoginPage.vue', () => ({ default: { render: () => null } }));

const ANA = { id: 'local-1', name: 'Ana', email: 'ana@example.com', role: 'owner', permissions: ['*'] };

/** Boot the shell the way `main.ts` does: router module first, scrub second, install last. */
async function bootShell() {
  // 1. `import { router } from './router'` — `createWebHistory()` snapshots the location here.
  const { router } = await import('./index');
  const courier = await import('../lib/courier');
  const session = await import('../lib/session');
  return { router, courier, session };
}

describe('the courier never survives boot in the URL (hub#755)', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    sessionStorage.clear();
  });

  it('leaves no fragment behind once the shell has navigated', async () => {
    window.history.replaceState(null, '', '/?shell=1#courier=opaque-code');

    const { router, courier, session } = await bootShell();

    // 2. The scrub. It does clean the browser URL — that half has always worked.
    expect(courier.takeShellCourierCode()).toBe('opaque-code');
    expect(window.location.hash).toBe('');

    // 3. The exchange lands and opens the session, exactly as `bootCourier` does.
    session.setUser(ANA);
    courier.settleCourierBoot();

    // 4. `app.use(router)` — the initial navigation, from whatever the history believes.
    const app = createApp({ render: () => null });
    app.use(router);
    await router.isReady();

    expect(window.location.href).not.toContain('courier');
    expect(window.location.hash).toBe('');
    expect(router.currentRoute.value.hash).toBe('');
  });

  it('never puts the credential in a query string, where it WOULD reach the server', async () => {
    // The variant QA did not see and that costs more: no session (the exchange failed, or the
    // code had already been spent), so the gate bounces to /login carrying `redirect=to.fullPath`.
    // A fragment at least stays in the browser; a query string travels in the request line and
    // lands in access logs and Referer headers.
    window.history.replaceState(null, '', '/?shell=1#courier=opaque-code');

    const { router, courier } = await bootShell();
    expect(courier.takeShellCourierCode()).toBe('opaque-code');
    courier.settleCourierBoot(); // exchange rejected: no session was opened

    const app = createApp({ render: () => null });
    app.use(router);
    await router.isReady();

    expect(router.currentRoute.value.name).toBe('login');
    expect(router.currentRoute.value.fullPath).not.toContain('courier');
    expect(window.location.href).not.toContain('courier');
  });
});
