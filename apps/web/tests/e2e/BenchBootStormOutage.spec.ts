// Regression test for ERPlora/hub#2270 — the end of a network-change storm, in a file of its own.
//
// The storm budget is TIME, and it ends: a runner whose network never settles has to give the spec
// an empty page, not a bench that reloads forever. It lives apart from `BenchBootRecovery.spec.ts`
// only to run untraced — `trace` can be set per FILE, not per test — because this test reloads
// the whole shell ~25 times in five seconds, and recording that made closing the context take
// 30–55 s on the loaded pre-push gate of 27/09 (the test body itself was done in 6 s; with
// `--trace off`, 5.6 s). Its failure is told by the counts it asserts.

import {
  BOOT_RELOAD_LIMIT,
  BOOT_SETTLE_MS,
  bootReloadsOf,
  expect,
  NETWORK_CHANGE_BUDGET_MS,
  test,
} from '../bench-boot';

test.use({ trace: 'off' });

test.describe('bench boot recovery of network-change storms (hub#2270)', () => {
  test('a network that never comes back still ends red, after its time budget', async ({
    page,
  }) => {
    // The other half of hole B in `BenchBootRecovery.spec.ts`: the storm budget ends. A runner
    // whose network never settles has to give the spec an empty page, not a bench that reloads
    // forever — delete the budget from `nextBootStep` and this test hangs until Playwright kills
    // it.
    //
    // Its own timeout, written from the bench's ceilings: the storm alone runs for
    // `NETWORK_CHANGE_BUDGET_MS` and the load that crosses it can still sit on the settle ceiling,
    // so the default 30 s is no bound on a loaded machine. The missing-budget mutant still ends
    // here — just later.
    test.setTimeout(NETWORK_CHANGE_BUDGET_MS + 2 * BOOT_SETTLE_MS + 30_000);
    let mainRequests = 0;
    await page.route('**/src/main.ts', async (route) => {
      mainRequests += 1;
      await route.abort('internetdisconnected');
    });

    await page.goto('/login');

    const reloads = bootReloadsOf(page);
    expect(reloads.length, 'the storm was not reloaded past the budget').toBeGreaterThan(
      BOOT_RELOAD_LIMIT,
    );
    expect(reloads.every((reload) => reload.storm)).toBe(true);
    expect(mainRequests).toBe(1 + reloads.length);
    await expect(page.locator('#app')).toBeEmpty();
  });
});
