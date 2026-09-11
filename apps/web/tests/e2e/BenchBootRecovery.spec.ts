// Regression test for ERPlora/hub#1806 — the bench survives the network change that used to put
// somebody else's PR in red.
//
// What happened (run 34532770133, job 103057220159, on PR #1795, which only touches a stylesheet
// and a unit test): ONE network-configuration change on `ci-runner-1` made Chromium cancel every
// in-flight socket at once — 79 requests to the Vite dev server died inside 33.7 ms with
// `net::ERR_NETWORK_CHANGED`. The module graph of the shell arrived half-loaded, Vue never
// mounted, the page was blank white, and `ImportPanel.spec.ts:66` reported `import-lead` as
// "element(s) not found". The rerun of the same commit passed in 3 m 44 s.
//
// It is the DEV SERVER that makes this catastrophic: a page load there is ~440 separate module
// requests, so a single instantaneous event has 440 chances to hit one that the shell cannot boot
// without. Chromium has no switch to ignore the notifier (checked against the shipped binary:
// no `network-change` switch exists), and the app cannot retry the fetch of its own bootstrap
// because that bootstrap is what failed to arrive. So the recovery belongs to the bench, and this
// spec is what proves it is still there.
//
// The injected failure is `net::ERR_CONNECTION_RESET` and not `net::ERR_NETWORK_CHANGED` because
// `route.abort()` has no code for a network change; both are in `TRANSIENT_TRANSPORT_ERRORS` and
// take the same path. The real code is pinned by name in `tests/bench-boot.test.ts`.

import { expect, test } from '../bench-boot';

test.describe('bench boot recovery (hub#1806)', () => {
  test('a network change that kills the module graph costs a reload, not a red build', async ({
    page,
  }) => {
    // The page under test is the one that fell: Settings → Data, reached by deep link. No session
    // is injected on purpose — the shell has to MOUNT to redirect to /login, and mounting is
    // exactly what the half-loaded module graph prevented.
    //
    // The bootstrap alone is enough to reproduce it, and measuring that is what this spec is for:
    // with `/src/main.ts` dead the browser never discovers the rest of the graph, so it requests
    // nothing else and the page stays blank. In CI 79 requests died together; here one does, and
    // the screen ends up in the same state.
    let mainRequests = 0;

    // Killed ONCE, not for the run. The `once` is what makes this a test of the RECOVERY rather
    // than of an outage — a dev server that is genuinely down must still fail, and
    // `isBootTransportFailure` refuses to excuse that case (`ERR_CONNECTION_REFUSED`).
    await page.route('**/src/main.ts', async (route) => {
      mainRequests += 1;
      if (mainRequests === 1) return route.abort('connectionreset');
      return route.continue();
    });

    await page.goto('/settings#data');

    // The bootstrap was asked for TWICE: the bench saw its own code die on the wire and went back
    // for it. This is the assertion that fails if the recovery is removed — before the fix this
    // was 1, and `#app` below stayed empty.
    expect(mainRequests, 'the bench did not re-fetch the bootstrap it lost').toBe(2);

    // And the shell is on screen. `#app` with children IS the mount: while it was empty every
    // `getByTestId` in the suite reported "element(s) not found", which is the red that landed on
    // PR #1795.
    await expect(page.locator('#app > *').first()).toBeVisible();
  });

  test('a failure that is NOT a lost connection is not retried away', async ({ page }) => {
    // The other half of the contract, and the one that keeps this from becoming a blanket retry:
    // a failure that is a defect of OURS has to stay red, first time, every time.
    //
    // `net::ERR_FAILED` and not a blocked request, and that choice is measured rather than
    // assumed: `route.abort('blockedbyclient')` is reported by this Chromium as
    // `net::ERR_BLOCKED_BY_CLIENT.Inspector` — suffix included — so a list widened with the plain
    // `net::ERR_BLOCKED_BY_CLIENT` would never have matched it and this test would have passed
    // while the guard it is meant to be was gone. `ERR_FAILED` is reported verbatim, and it is the
    // catch-all a careless widening reaches for first.
    let failed = 0;

    await page.route('**/src/main.ts', async (route) => {
      failed += 1;
      await route.abort('failed');
    });

    await page.goto('/settings#data');

    // Exactly one attempt: no reload was spent on it.
    expect(failed, 'a failure that is not a lost connection must not be reloaded away').toBe(1);
    await expect(page.locator('#app')).toBeEmpty();
  });
});
