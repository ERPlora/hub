// Regression tests for ERPlora/hub#2315 — a storm reload that the bench waited out instead of
// recovering.
//
// What happened (run 36425088970, attempt 2, `AppsFiltersApplyOnPhone.spec.ts` at 1440 px, the
// first test of the run): the first load of `/apps#all` worked, then one request of ours died of
// `net::ERR_NETWORK_CHANGED` and the bench reloaded, as it should. In the same millisecond the OLD
// document started two Vite chunks. Playwright reports a request that is in flight when its
// document is replaced with a `request` event and then NOTHING — no `requestfinished`, no
// `requestfailed` (measured on 28/09 with a bare Chromium, with and without `page.route`). The
// bench counted both as still loading, so `settle()` waited its whole `BOOT_SETTLE_MS` for them;
// by then the storm (0.3 s of real losses on the new document) was "10 s old", past
// `NETWORK_CHANGE_BUDGET_MS`, and the bench handed the spec a shell that never mounted — without
// a word, which is why the red read as "the catalog is slow to show on a cold start".
import { bootReloadsOf, expect, test, type Page } from '../bench-boot';

/**
 * The bench's warnings while `load` runs. The bench prints them from this worker's Node process,
 * where `page.on('console')` never looks.
 */
async function warningsDuring(load: () => Promise<unknown>): Promise<string[]> {
  const warnings: string[] = [];
  const warn = console.warn;
  console.warn = (...args: unknown[]) => {
    warnings.push(args.map(String).join(' '));
  };
  try {
    await load();
  } finally {
    console.warn = warn;
  }
  return warnings;
}

const gaveUp = (warnings: string[]): string[] =>
  warnings.filter((line) => line.includes('BENCH_GAVE_UP'));

test.describe('bench boot and the requests of a replaced document (hub#2315)', () => {
  test('a request the old document left in flight does not stop the bench from recovering a storm', async ({
    page,
  }) => {
    // The storm: the login screen's own module dies as soon as it is asked for, until the bench
    // has reloaded TWICE — the first document, the app's own reload of its screen, and the document of the
    // bench's first reload, like the 60 modules of the new document did in the trace.
    let viewRequests = 0;
    await page.route('**/src/views/LoginPage.vue*', async (route) => {
      viewRequests += 1;
      if (bootReloadsOf(page).length >= 2) return route.continue();
      return route.abort('internetdisconnected');
    });

    // The orphan: every document asks for a module of ours as it is being replaced, and the module
    // never answers — its document is gone before it could. That is the trace's pair of chunks,
    // started by the old document in the same millisecond as the bench's reload.
    let orphans = 0;
    await page.route('**/src/__bench_orphan__.ts', () => {
      orphans += 1;
      return new Promise<never>(() => undefined);
    });
    await page.addInitScript(() => {
      addEventListener('beforeunload', () => {
        void import(/* @vite-ignore */ `${location.origin}/src/__bench_orphan__.ts`);
      });
    });

    const warnings = await warningsDuring(() => page.goto('/login'));

    expect(gaveUp(warnings), 'a recovered storm was reported as given up').toEqual([]);
    expect(orphans, 'no replaced document left a request in flight').toBeGreaterThan(0);
    expect(viewRequests, 'the screen was never asked for again').toBeGreaterThan(2);
    const reloads = bootReloadsOf(page);
    expect(reloads.length, 'the storm on the new document got no reload').toBeGreaterThanOrEqual(2);
    expect(reloads.every((reload) => reload.storm)).toBe(true);
    await expect(page.getByTestId('login-box')).toBeVisible();
    await expect(page.locator('#app[data-v-app]')).toBeAttached();
    await page.unrouteAll({ behavior: 'ignoreErrors' });
  });

  test('a request the old document left in flight is dropped when the reload itself died on the wire', async ({
    page,
  }) => {
    // The storm reaches the reload's own document: Chromium commits its error page over the old
    // document, which replaces it as much as a document that answered — so the old document's
    // orphan is not the bench's business either, and waiting for it would age the storm past its
    // budget exactly like in the trace.
    await page.route('**/src/views/LoginPage.vue*', async (route) => {
      if (bootReloadsOf(page).length >= 2) return route.continue();
      return route.abort('internetdisconnected');
    });
    let documents = 0;
    await page.route('**/login', async (route) => {
      if (route.request().resourceType() !== 'document') return route.continue();
      documents += 1;
      if (documents === 2) return route.abort('internetdisconnected');
      return route.continue();
    });
    let orphans = 0;
    await page.route('**/src/__bench_orphan__.ts', () => {
      orphans += 1;
      return new Promise<never>(() => undefined);
    });
    await page.addInitScript(() => {
      addEventListener('beforeunload', () => {
        void import(/* @vite-ignore */ `${location.origin}/src/__bench_orphan__.ts`);
      });
    });

    const warnings = await warningsDuring(() => page.goto('/login'));

    expect(gaveUp(warnings), 'a recovered storm was reported as given up').toEqual([]);
    expect(orphans, 'no replaced document left a request in flight').toBeGreaterThan(0);
    expect(documents, 'the reload of the storm never asked for its document').toBeGreaterThan(2);
    await expect(page.getByTestId('login-box')).toBeVisible();
    await page.unrouteAll({ behavior: 'ignoreErrors' });
  });

  test('a bench that gives up on a storm says so instead of handing the page over in silence', async ({
    page,
  }) => {
    // A storm that never ends: the login screen's module dies of a network change on every load,
    // so the bench reloads until the storm outlives `NETWORK_CHANGE_BUDGET_MS` and hands over. It
    // dies as soon as it is asked for: waiting for `load` first hangs it for good whenever a loaded
    // runner asks for it after `load`.
    await page.route('**/src/views/LoginPage.vue*', (route) => route.abort('internetdisconnected'));

    const warnings = await warningsDuring(() => page.goto('/login'));

    expect(bootReloadsOf(page).length, 'the storm got no reload at all').toBeGreaterThan(0);
    expect(gaveUp(warnings)).toHaveLength(1);
    await page.unrouteAll({ behavior: 'ignoreErrors' });
  });

  // The other side of dropping the old document's requests: only a document that REPLACES the old
  // one may do it. A `pushState` (the router moving the URL while the shell boots), even one that
  // lands while another document is on its way, and a navigation that ends without committing (a
  // download) replace nothing, so a module of the live document still in flight is still the
  // bench's business — here it dies of a reset, and that is a reload.
  const pushState = (page: Page): Promise<void> =>
    page.evaluate(() => history.pushState(history.state, '', '#bench-pushed'));

  /**
   * Starts a navigation of the live document to `path` and waits for it to fail. With
   * `pushWhilePending`, the live document also moves its own URL while that navigation is on its
   * way — from the page, because Playwright's `evaluate` waits for a pending navigation to settle.
   */
  async function navigateAndFail(page: Page, path: string, pushWhilePending = false): Promise<void> {
    // After `load`, i.e. while the bench is settling: before it, a navigation that never commits
    // also leaves Playwright's own `goto` waiting forever for a `load` of its document.
    await page.waitForLoadState('load');
    const failed = page.waitForEvent('requestfailed', (req) => req.url().includes(path));
    await page.evaluate(
      ([to, push]) => {
        location.href = to;
        if (push) {
          void fetch('/__bench_push__').then(() =>
            history.pushState(history.state, '', '#bench-pushed-early'),
          );
        }
      },
      [path, pushWhilePending] as const,
    );
    await failed;
  }

  for (const [name, before] of [
    ['a pushState of the router', async () => undefined],
    [
      // The 1-in-10 of the first version of this fix: the router moved the URL between the
      // cancelled navigation's request and its failure, and that `framenavigated` was taken for
      // the new document's commit.
      'a pushState while another document is on its way',
      (page: Page) => navigateAndFail(page, '/__bench_cancelled__', true),
    ],
    [
      'a navigation that answered with a download',
      (page: Page) => navigateAndFail(page, '/__bench_download__'),
    ],
  ] as const) {
    test(`a module of the live document is still waited for after ${name}`, async ({ page }) => {
      // The navigation on its way lets the page move its URL, and only fails once it has.
      let letThePagePush: () => void = () => undefined;
      const pageMayPush = new Promise<void>((resolve) => {
        letThePagePush = resolve;
      });
      await page.route('**/__bench_push__', async (route) => {
        await pageMayPush;
        return route.fulfill({ status: 204 });
      });
      await page.route('**/__bench_cancelled__', async (route) => {
        const pushed = page.waitForEvent('framenavigated', (frame) =>
          frame.url().endsWith('#bench-pushed-early'),
        );
        letThePagePush();
        await pushed;
        return route.abort('aborted');
      });
      await page.route('**/__bench_download__', (route) =>
        route.fulfill({
          contentType: 'text/csv',
          headers: { 'content-disposition': 'attachment; filename="bench.csv"' },
          body: 'a,b\n',
        }),
      );
      let held = 0;
      await page.route('**/src/__bench_held__.ts', async (route) => {
        held += 1;
        if (held > 1) {
          return route.fulfill({ contentType: 'text/javascript', body: 'export {};' });
        }
        await before(page);
        await pushState(page);
        // Long enough for a bench that forgot the module to decide without it.
        await new Promise((resolve) => setTimeout(resolve, 1_000));
        return route.abort('connectionreset');
      });
      await page.addInitScript(() => {
        void import(/* @vite-ignore */ `${location.origin}/src/__bench_held__.ts`).catch(
          () => undefined,
        );
      });

      await page.goto('/login');

      expect(held, 'the held module was never asked for').toBeGreaterThan(1);
      expect(bootReloadsOf(page)).toEqual([
        { url: '/login', codes: ['net::ERR_CONNECTION_RESET'], storm: false },
      ]);
      await expect(page.getByTestId('login-box')).toBeVisible();
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    });
  }
});
