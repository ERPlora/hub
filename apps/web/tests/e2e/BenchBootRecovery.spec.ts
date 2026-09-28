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

import {
  BOOT_RELOAD_LIMIT,
  BOOT_SETTLE_MS,
  bootReloadsOf,
  expect,
  NETWORK_CHANGE_BUDGET_MS,
  test,
  type Page,
} from '../bench-boot';

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
    //
    // hub#2270 moved the bound once more: a network-change STORM is reloaded outside the budget, so
    // `BOOT_RELOAD_LIMIT + 1` is no longer a ceiling on fetches. What stays exact is the accounting:
    // every extra fetch is a reload the bench wrote down, and the ones paid from the budget stay
    // within it.
    const reloads = bootReloadsOf(page);
    expect(mainRequests, 'the bench did not re-fetch the bootstrap it lost').toBeGreaterThan(1);
    expect(mainRequests, 'every extra fetch has to be a reload the bench accounted for').toBe(
      1 + reloads.length,
    );
    expect(
      reloads.filter((reload) => !reload.storm).length,
      'the bench spent more than its reload budget',
    ).toBeLessThanOrEqual(BOOT_RELOAD_LIMIT);

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

    const started = Date.now();
    await page.goto('/settings#data');

    // hub#2270: since the bench waits for a load to settle, a defect of ours has to END that wait
    // — the spec gets its red page at once, not after the bench's settle ceiling.
    expect(Date.now() - started, 'the bench sat on a failure of ours').toBeLessThan(BOOT_SETTLE_MS);

    // hub#1839: «no reload was spent on IT», not «no reload at all». A genuine accident of the
    // runner inside this navigation makes the bench reload — that is its job — and the next
    // request for `main.ts` fails again, so a bare `toBe(1)` went red on a PR that touched none of
    // this. The bench now keeps its books: every reload it spent, and on which codes.
    const reloads = bootReloadsOf(page);
    expect(
      reloads.flatMap((reload) => reload.codes),
      'a failure that is not a lost connection must not be reloaded away',
    ).not.toContain('net::ERR_FAILED');
    expect(
      failed,
      'every extra attempt at the bootstrap has to be a reload the bench accounted for',
    ).toBe(1 + reloads.length);
    await expect(page.locator('#app')).toBeEmpty();
  });

  test('a real accident during our own failure is recovered, and our failure still stays red', async ({
    page,
  }) => {
    // hub#1839, reproduced instead of waited for: the runner's network drops ONE request while the
    // bootstrap is failing for a reason of ours. The bench reloads for the accident; it does not
    // reload for `ERR_FAILED`; and the screen stays blank, because our defect is still there.
    let failed = 0;
    let accidents = 0;

    await page.route('**/src/main.ts', async (route) => {
      failed += 1;
      await route.abort('failed');
    });
    await page.route('**/@vite/client', async (route) => {
      accidents += 1;
      if (accidents === 1) return route.abort('connectionreset');
      return route.continue();
    });

    await page.goto('/settings#data');

    const reloads = bootReloadsOf(page);
    expect(reloads.length, 'the accident was not recovered').toBeGreaterThanOrEqual(1);
    expect(reloads.flatMap((reload) => reload.codes)).toContain('net::ERR_CONNECTION_RESET');
    expect(reloads.flatMap((reload) => reload.codes)).not.toContain('net::ERR_FAILED');
    expect(failed).toBe(1 + reloads.length);
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

// Regression tests for ERPlora/hub#2270 — the two holes the CI traces of 27/09 showed in the
// recovery above. Every red of that day (MenuButtonFirstFrame at 1440 and 390 px, AppsVisual,
// DashboardVisual) was `net::ERR_NETWORK_CHANGED` and nothing else:
//   · A — the loss came 60 ms AFTER `goto` resolved: the router was still fetching the screen, and
//     the bench only looked at what died before the `load` event;
//   · B — the losses came in a STORM of bursts spread over 0.3–1.4 s, and each reload takes
//     ~300 ms, so the two reloads of the budget were spent in under a second.
// `route.abort('internetdisconnected')` is the injectable twin of a network change: Chromium
// derives both from the machine's network moving, and `NETWORK_CHANGE_ERRORS` holds both.
test.describe('bench boot recovery of network-change storms (hub#2270)', () => {
  /** Resolves on the next `load` event of the page, i.e. once the current document has loaded. */
  function nextLoad(page: Page): Promise<void> {
    return new Promise((resolve) => page.once('load', () => resolve()));
  }

  test('a screen that dies after the load event is still recovered by the bench', async ({
    page,
  }) => {
    // Hole A. The screen's own module is fetched by the router, and it dies twice AFTER the
    // document has loaded — once for the first document and once for the app's own reload
    // (`view-load-recovery`), which is what the 1440 trace shows. Before the fix `goto` handed the
    // page over at `load`, the app's second failure painted its failure notice, and the login
    // form never came.
    let viewRequests = 0;
    await page.route('**/src/views/LoginPage.vue*', async (route) => {
      viewRequests += 1;
      if (viewRequests > 2) return route.continue();
      await nextLoad(page);
      return route.abort('internetdisconnected');
    });

    await page.goto('/login');

    expect(viewRequests, 'the screen was never asked for again').toBeGreaterThan(2);
    await expect(page.getByTestId('login-box')).toBeVisible();
    await expect(page.locator('#app[data-v-app]')).toBeAttached();
  });

  test('a storm longer than the reload budget is recovered without spending it', async ({
    page,
  }) => {
    // Hole B. Four loads in a row die of a network change — more than `BOOT_RELOAD_LIMIT` can pay
    // for, fewer than a real outage. Before the fix the bench stopped after two reloads with
    // `#app` empty.
    let mainRequests = 0;
    await page.route('**/src/main.ts', async (route) => {
      mainRequests += 1;
      if (mainRequests <= 4) return route.abort('internetdisconnected');
      return route.continue();
    });

    await page.goto('/login');

    // At least the four injected losses, each paid outside the budget; a real network change of
    // the runner inside the same navigation may add more, and is accounted for the same way.
    const reloads = bootReloadsOf(page);
    expect(reloads.length).toBeGreaterThanOrEqual(4);
    expect(reloads.length, 'the storm was paid from the reload budget').toBeGreaterThan(
      BOOT_RELOAD_LIMIT,
    );
    expect(reloads.every((reload) => reload.storm)).toBe(true);
    expect(mainRequests).toBe(1 + reloads.length);
    await expect(page.locator('#app[data-v-app]')).toBeAttached();
  });

  test('a storm that starts after a slow first load still gets its reloads', async ({ page }) => {
    // The storm budget is the age of the STORM, not of the navigation. A first load that is slow
    // before anything dies — Vite transforming the shell cold, a runner six jobs deep — used to
    // spend the whole budget before the first decision, and the bench handed over an empty `#app`
    // without a single reload (measured on the loaded pre-push gate of 27/09: 0 reloads).
    test.setTimeout(NETWORK_CHANGE_BUDGET_MS + 60_000);
    let mainRequests = 0;
    await page.route('**/src/main.ts', async (route) => {
      mainRequests += 1;
      if (mainRequests > 1) return route.continue();
      await new Promise((resolve) => setTimeout(resolve, NETWORK_CHANGE_BUDGET_MS + 1_000));
      return route.abort('internetdisconnected');
    });
    // And the runner's own network moves again inside the recovery — run 36340311649 (PR #2275):
    // 0.7 s after the injected loss, 54 requests of the reload died of a REAL
    // `ERR_NETWORK_CHANGED`. The bench reloaded once more, as it should, and a spec that counted
    // exactly two fetches went red on a recovery that worked (the trap hub#1838 already named).
    let clientRequests = 0;
    await page.route('**/@vite/client', async (route) => {
      clientRequests += 1;
      if (clientRequests === 2) return route.abort('internetdisconnected');
      return route.continue();
    });

    await page.goto('/login');

    // Accounting, not an exact count: every extra fetch is a reload the bench wrote down, the
    // injected loss got one of its own, and none of them came out of the budget.
    const reloads = bootReloadsOf(page);
    expect(reloads.length, 'the storm got no reload of its own').toBeGreaterThanOrEqual(1);
    expect(reloads[0]?.codes).toContain('net::ERR_INTERNET_DISCONNECTED');
    expect(reloads.every((reload) => reload.storm)).toBe(true);
    expect(mainRequests).toBe(1 + reloads.length);
    await expect(page.locator('#app[data-v-app]')).toBeAttached();
  });

  test('a document that dies of a network change is fetched again instead of throwing', async ({
    page,
  }) => {
    // Seen in the local replay of the storm: when the burst lands on the DOCUMENT, Playwright's
    // `goto` throws `net::ERR_INTERNET_DISCONNECTED` and the page sits on Chromium's error page.
    // Before the fix that throw reached the spec as its own failure.
    let documents = 0;
    await page.route(
      (url) => url.pathname === '/login',
      async (route) => {
        if (route.request().resourceType() !== 'document') return route.continue();
        documents += 1;
        if (documents === 1) return route.abort('internetdisconnected');
        return route.continue();
      },
    );

    await page.goto('/login');

    const reloads = bootReloadsOf(page);
    expect(reloads.length).toBeGreaterThanOrEqual(1);
    expect(reloads.every((reload) => reload.storm)).toBe(true);
    expect(documents).toBe(1 + reloads.length);
    await expect(page.locator('#app[data-v-app]')).toBeAttached();
  });

  test('a document that fails for a reason of ours still throws, from goto and from reload', async ({
    page,
  }) => {
    // The other side of the catch above: only a document the NETWORK killed is swallowed. Let the
    // catch swallow every throw and a navigation that fails for a reason of ours (or times out)
    // hands the spec `null` and a half-loaded page instead of its red — the blanket retry this
    // bench must never become. Both doors go through that catch, so both are pinned.
    await page.goto('/login');
    await expect(page.locator('#app[data-v-app]')).toBeAttached();

    await page.route(
      (url) => url.pathname === '/login',
      async (route) => {
        if (route.request().resourceType() !== 'document') return route.continue();
        return route.abort('failed');
      },
    );

    await expect(page.reload()).rejects.toThrow('net::ERR_FAILED');
    await expect(page.goto('/login')).rejects.toThrow('net::ERR_FAILED');
    expect(bootReloadsOf(page), 'a failure of ours must not be reloaded away').toEqual([]);
  });

  test('a reload the spec asks for is recovered like a navigation', async ({ page }) => {
    // hub#2274, the same storm on the other door: `SettingsBillingBox.spec.ts` reloads the page to
    // prove a save persisted, and in run 36311751240 seven of the app's own modules died of
    // `ERR_NETWORK_CHANGED` ~500 ms after that `page.reload()`. The bench only wrapped `goto`, so
    // the reload handed the spec a shell that never mounted. Here the screen dies twice AFTER the
    // reload's `load` event — the first navigation is left alone on purpose.
    await page.goto('/login');
    await expect(page.locator('#app[data-v-app]')).toBeAttached();

    let viewRequests = 0;
    await page.route('**/src/views/LoginPage.vue*', async (route) => {
      viewRequests += 1;
      if (viewRequests > 2) return route.continue();
      await nextLoad(page);
      return route.abort('internetdisconnected');
    });

    await page.reload();

    expect(viewRequests, 'the screen was never asked for again after the reload').toBeGreaterThan(2);
    expect(bootReloadsOf(page).every((reload) => reload.storm)).toBe(true);
    await expect(page.getByTestId('login-box')).toBeVisible();
    await expect(page.locator('#app[data-v-app]')).toBeAttached();
  });
});
