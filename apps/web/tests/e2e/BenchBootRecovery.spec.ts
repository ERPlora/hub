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

import { BOOT_RELOAD_LIMIT, expect, test } from '../bench-boot';

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

    // The bootstrap was asked for AGAIN: the bench saw its own code die on the wire and went back
    // for it. This is the assertion that fails if the recovery is removed — before the fix this
    // was 1, and `#app` below stayed empty.
    //
    // 🔴 Bounded, NOT exact, and that is the whole point of hub#1838. `toBe(2)` also asserted that
    // nothing else went wrong on the machine while this navigation was in flight — which is not a
    // fact about our recovery, and is exactly the fact `ci-runner-1` does not provide. Measured on
    // run 34626218384 (job 103351855601), on PR #1834, whose diff is four `data-testid` renames:
    //   [bench] 1 request(s) … died on the wire (net::ERR_CONNECTION_RESET) … reloading (1/2)
    //   [bench] 50 request(s) … died on the wire (net::ERR_NETWORK_CHANGED) … reloading (2/2)
    // The first reload is this spec's injected failure; the second is a REAL network change — the
    // very accident hub#1806 exists for — landing inside the recovery. The bench did its job and
    // the shell mounted, and the spec still went red on `Expected: 2, Received: 3`, putting a PR
    // that touches none of this in red. So this spec had become the flake it was written to cure.
    expect(mainRequests, 'the bench did not re-fetch the bootstrap it lost').toBeGreaterThan(1);
    expect(
      mainRequests,
      'the bench re-fetched the bootstrap past its own limit',
    ).toBeLessThanOrEqual(BOOT_RELOAD_LIMIT + 1);

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

  test('a run of accidents costs the bench its limit and then stops, it does not loop', async ({
    page,
  }) => {
    // The path the CI red of hub#1838 actually took, pinned so it cannot come back untested: the
    // connection dies on MORE than one load of the same navigation. `ci-runner-1` serves six runner
    // slots, so a second network change inside one spec is ordinary, not exotic.
    //
    // Two things are under test here and both are load-bearing:
    //   · the bench keeps going past the first accident — the case the old exact count forbade;
    //   · and it STOPS at `BOOT_RELOAD_LIMIT`. A dev server that keeps dying transiently has to end
    //     as a red test, not as a bench that reloads forever; delete the `reload <=` condition from
    //     `bench-boot.ts` and this test hangs until Playwright kills it, which is how it says so.
    let mainRequests = 0;

    // Never served. Unlike the first test there is no `once`: this is the outage, not the blip.
    await page.route('**/src/main.ts', async (route) => {
      mainRequests += 1;
      await route.abort('connectionreset');
    });

    await page.goto('/settings#data');

    // The first fetch plus one per reload, and not one more. This line is the end-to-end half of
    // the regression test for ERPlora/hub#1842, and it is written OUT rather than derived from
    // `BOOT_RELOAD_LIMIT`, which is the difference between measuring the ceiling and measuring
    // nothing. Derived, this line reads "the bench stops at whatever
    // its budget happens to be", and that is just as true of a budget of 50: moving the constant
    // to 5 left this spec at `3 passed` and `bench-boot.test.ts` at `87 passed`. Spelled out, it
    // goes red however the widening is written — the constant moved, the condition turned into
    // `reload <= BOOT_RELOAD_LIMIT * 2`, or the loop rewritten by hand.
    //
    // The bound in the first test IS derived, on purpose: that one is the tolerance for the
    // runner's own accidents and has to follow the budget wherever it goes. This one is the
    // budget. Both have to be edited to move it, which is what makes moving it a decision.
    expect(mainRequests, 'the bench did not spend exactly its two reloads').toBe(3);

    // And it gives up honestly: the screen is blank and the spec that asked for it goes red on its
    // own assertions. Recovering is the bench's job; pretending to have recovered is not.
    await expect(page.locator('#app')).toBeEmpty();
  });
});
