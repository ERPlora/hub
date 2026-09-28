// Boot recovery for the e2e bench (ERPlora/hub#1806).
//
// ── What this is for ─────────────────────────────────────────────────────────────────────────
// `ci-runner-1` is one machine serving six runner slots, so its network configuration changes
// under the tests as a matter of routine (a neighbour job starting a container is enough).
// Chromium answers a configuration change by cancelling every in-flight socket at once, with
// `net::ERR_NETWORK_CHANGED` — loopback included. Measured on run 34532770133: 79 requests to the
// Vite dev server died inside 33.7 ms, the shell's module graph arrived half-loaded, Vue never
// mounted, and `ImportPanel.spec.ts` reported `import-lead` as "element(s) not found" on PR #1795,
// which touches a stylesheet and a unit test. The rerun of the same commit was green.
//
// Why it has to live here and not in the app or the browser:
//   · the APP cannot retry it — what failed to arrive is the bootstrap that would do the retrying,
//     so none of our code is running. This is why the retries hub#1526 put in the shell for
//     hub#1518 do not cover this case: they run inside an app that has already booted;
//   · CHROMIUM has no switch for it — checked against the binary Playwright ships
//     (`Google Chrome for Testing Framework`, 153.0.8010.12): no `network-change` or
//     `ignore-network` switch exists, while a known one like `disable-features` is present, so the
//     search was not looking in the wrong place;
//   · the DEV SERVER is what makes one event catastrophic: a page load is ~440 separate module
//     requests, i.e. 440 chances for a single instant to hit one the shell cannot boot without.
//
// ── What it deliberately does NOT do ─────────────────────────────────────────────────────────
// 🔴 It is not `retries: 1`, and it is not "reload when the screen is empty". Either of those is a
// blanket retry, and a blanket retry re-rolls the dice on real defects — the gate would go on
// lying, just more quietly. The reload fires only when the browser told us, in so many words, that
// a request for THE APP'S OWN CODE died with its connection. A blocked request, a request the page
// itself cancelled, a dev server that never came up, a 500 from the runtime, a screen that renders
// empty: all of those still fail, first time, every time.
//
// Guards: `tests/bench-boot.test.ts` (the decision table, and the check that every spec takes its
// `test` from here) and `tests/e2e/BenchBootRecovery.spec.ts` (the recovery, end to end).

import { readdirSync } from 'node:fs';

import { test as base, expect, request, type Request } from '@playwright/test';

// Re-exported so a spec needs ONE import line, not one for the bench and one for Playwright.
export { expect, request };
export type { Page, TestInfo } from '@playwright/test';

/**
 * Chromium errors that mean "the connection died under this request", as opposed to "the request
 * was answered with something bad" or "somebody stopped it on purpose".
 *
 * `ERR_NETWORK_CHANGED` is the one measured in hub#1806; the rest are the same accident seen from
 * a slightly different place (the socket was already open, the interface went away mid-flight, the
 * peer's address stopped being routable). The list is short and explicit on purpose: widening it
 * is how this turns into the blanket retry it exists to avoid, so it is pinned by a test.
 */
export const TRANSIENT_TRANSPORT_ERRORS: readonly string[] = [
  'net::ERR_NETWORK_CHANGED',
  'net::ERR_NETWORK_IO_SUSPENDED',
  'net::ERR_INTERNET_DISCONNECTED',
  'net::ERR_ADDRESS_UNREACHABLE',
  'net::ERR_CONNECTION_RESET',
  'net::ERR_CONNECTION_ABORTED',
  'net::ERR_CONNECTION_CLOSED',
  'net::ERR_SOCKET_NOT_CONNECTED',
  'net::ERR_EMPTY_RESPONSE',
];

/** How many times a single navigation may be re-fetched before the failure is the test's answer. */
export const BOOT_RELOAD_LIMIT = 2;

/**
 * The transport errors Chromium derives from the MACHINE's network changing, and from nothing else
 * (ERPlora/hub#2270).
 *
 * `ERR_NETWORK_CHANGED` is the network-change notifier cancelling every in-flight socket;
 * `ERR_INTERNET_DISCONNECTED` is the same notifier reporting "no network" for the instant between
 * two changes. No defect of ours, of the dev server or of the runtime can answer a request with
 * either, so a reload for them re-rolls nothing — and that is why they are paid from their own
 * time budget, not from `BOOT_RELOAD_LIMIT`. Every other transient code (a reset, an empty
 * response…) is something a crashing server can ALSO cause, and stays in the budget.
 */
export const NETWORK_CHANGE_ERRORS: readonly string[] = [
  'net::ERR_NETWORK_CHANGED',
  'net::ERR_INTERNET_DISCONNECTED',
];

/**
 * How long a navigation may keep being reloaded for network changes alone (ERPlora/hub#2270).
 *
 * The longest storm in the CI traces of 27/09 lasted 1.4 s (five bursts in the 390 px case). A
 * network that keeps changing for five seconds is an outage of the runner, and has to end as a
 * red test rather than as a bench that reloads forever.
 */
export const NETWORK_CHANGE_BUDGET_MS = 5_000;

/** What the bench does after a load of a navigation has settled. */
export type BootStep = 'hand-over' | 'reload' | 'reload-storm';

/**
 * The bench's decision after one load of a navigation, from the codes of the app's own requests
 * that died on the wire during it.
 *
 * Nothing died → the page is the spec's. Only network-change codes → reload without spending the
 * budget, while the storm is younger than `NETWORK_CHANGE_BUDGET_MS`. Anything else (alone or
 * mixed with a network change) → reload from the budget, which a crashing server can exhaust.
 */
export function nextBootStep(
  codes: readonly string[],
  countedReloads: number,
  elapsedMs: number,
): BootStep {
  if (codes.length === 0) return 'hand-over';
  if (codes.every((code) => NETWORK_CHANGE_ERRORS.includes(code))) {
    return elapsedMs < NETWORK_CHANGE_BUDGET_MS ? 'reload-storm' : 'hand-over';
  }
  return countedReloads < BOOT_RELOAD_LIMIT ? 'reload' : 'hand-over';
}

function originOf(url: string | undefined): string | undefined {
  if (url === undefined) return undefined;
  try {
    return new URL(url).origin;
  } catch {
    return undefined;
  }
}

/**
 * Did the browser fail to fetch the app's OWN code because the connection died under it?
 *
 * Both halves are load-bearing. The error has to be one of the transient transport failures above
 * — anything else is a fact about the product and belongs in the test result. And the request has
 * to be same-origin with the bench's own server — a third party dying is likewise a fact, and the
 * spec that cares about it has to be the one that says so.
 */
export function isBootTransportFailure(
  failedUrl: string,
  errorText: string | undefined,
  appOrigin: string | undefined,
): boolean {
  if (errorText === undefined) return false;
  if (!TRANSIENT_TRANSPORT_ERRORS.includes(errorText)) return false;
  const origin = originOf(appOrigin);
  return origin !== undefined && originOf(failedUrl) === origin;
}

/**
 * The endings Playwright's default `testMatch` collects, as a regex.
 *
 * The glob is `**\/*.@(spec|test).?(c|m)[jt]s?(x)` — `spec` OR `test`, an optional `c`/`m`, `j` or
 * `t`, and an optional `x`, which is 24 endings and not the one this guard used to look for. The
 * count is not a reading of the glob: it is what @playwright/test 1.62.1 collected from a
 * directory holding one file per ending (`Total: 24 tests in 24 files`). It stays a copy only
 * while `playwright.config.ts` declares no `testMatch` of its own, which `declaresTestMatch` below
 * is there to keep true.
 *
 * The case of that ending is not free either way. `collectFilesForProject`
 * (`playwright/lib/runner/index.js`) puts a file through TWO gates that disagree about it:
 * `new Set(['.js', '.ts', '.mjs', '.mts', ...]).has(path.extname(file))`, which is a Set lookup
 * and so wants the FINAL extension lowercase letter for letter, and then
 * `minimatch(filePath, testMatch, { nocase: true, dot: true })` (`util.js`, `createFileMatcher`),
 * which does NOT care how `spec` or `test` is spelled. Measured with 1.62.1: `Cased.Spec.ts` and
 * `Cased.tEsT.mts` are files Playwright runs; `Shouty.spec.TS` and `Shouty.Spec.Ts` are not.
 *
 * So the word is a case-blind class and the extension is literal. Taking the easy road — an `i`
 * on the whole pattern — buys the first half and loses the second: the guard would then fail the
 * build over a `Shouty.spec.TS` Playwright never runs, and a guard that cries wolf gets deleted.
 * `nocase` is minimatch's and not the filesystem's, so this is how CI's Linux behaves too.
 */
const PLAYWRIGHT_DEFAULT_TEST_MATCH = /\.(?:[sS][pP][eE][cC]|[tT][eE][sS][tT])\.[cm]?[jt]sx?$/;

/**
 * Every spec file Playwright would run under `dir`, as paths relative to it.
 *
 * It walks SUBDIRECTORIES because Playwright does: `playwright.config.ts` sets `testDir: './e2e'`
 * and leaves the default `testMatch`, which is recursive. The guard that uses this list is only
 * worth anything if it sees exactly what Playwright sees — with a flat `readdirSync` a spec one
 * folder down took `test` straight from Playwright, ran for real, and the guard stayed green
 * (ERPlora/hub#1820).
 *
 * And it matches every ENDING Playwright runs, not just `.spec.ts`, for the same reason one field
 * over: with `endsWith('.spec.ts')` a `ZZMutant.test.ts` dropped in here took `test` straight from
 * Playwright, was listed by `playwright --list` as a test it would run, and left this guard at
 * `41 passed` (ERPlora/hub#1824).
 */
export function listE2eSpecs(dir: string): string[] {
  return readdirSync(dir, { recursive: true })
    .map((entry) => String(entry))
    .filter((name) => PLAYWRIGHT_DEFAULT_TEST_MATCH.test(name))
    .sort();
}

/**
 * Source of `playwright.config.ts` minus its comments, with string literals left as they are.
 *
 * Comments have to go because this config EXPLAINS the default `testMatch` in prose, and a reader
 * that counts prose as a declaration cries wolf until someone deletes it. Strings have to stay
 * because `{ "testMatch": … }` is a legal key.
 *
 * Which is why this is a scanner and not a pair of `replace()` calls: the config is full of URLs,
 * and the `//` in `http://127.0.0.1:1` starts no comment. A stripper that does not know it is
 * inside a string would drop the rest of that line — and report "no `testMatch` here" about a
 * config that declares one, which is a miss shaped exactly like a pass.
 */
function stripComments(source: string): string {
  let out = '';
  let i = 0;

  while (i < source.length) {
    const pair = source.slice(i, i + 2);

    if (pair === '//') {
      while (i < source.length && source[i] !== '\n') i += 1;
      continue;
    }

    if (pair === '/*') {
      i += 2;
      while (i < source.length && source.slice(i, i + 2) !== '*/') i += 1;
      i += 2;
      continue;
    }

    const quote = source[i];
    if (quote === "'" || quote === '"' || quote === '`') {
      out += quote;
      i += 1;
      while (i < source.length && source[i] !== quote) {
        // An escaped quote does not close the literal, and skipping the pair is what keeps the
        // scanner from reading the rest of the file as if it were still inside a string.
        if (source[i] === '\\') {
          out += source[i];
          i += 1;
        }
        out += source[i] ?? '';
        i += 1;
      }
      out += quote;
      i += 1;
      continue;
    }

    out += source[i];
    i += 1;
  }

  return out;
}

/**
 * Does this Playwright config take a position on `testMatch`?
 *
 * `listE2eSpecs` COPIES Playwright's default, and a copy is true only while the original does not
 * move. Declaring a `testMatch` is a one-line change nobody would think to weigh against a guard
 * two files away, and the day it happens the list stops describing the set of files Playwright
 * runs — with no symptom, because the guard goes on passing. The decision table is in
 * `tests/bench-boot.test.ts` (ERPlora/hub#1824).
 */
export function declaresTestMatch(source: string): boolean {
  return /\btestMatch\b/.test(stripComments(source));
}

/**
 * The directory this Playwright config collects specs from, as written in it — or `null` when it
 * cannot be known without running the config.
 *
 * The e2e guard walks this directory instead of a copy of it (ERPlora/hub#1835): a copy is true only
 * while nobody moves the original, and a half-moved suite would be run by Playwright and read by
 * the guard in green. Not symmetric with {@link declaresTestMatch}: `testDir` is always declared, so
 * what matters is its VALUE. A plain string or a template with nothing to interpolate is read; a
 * computed path, an interpolating template or two declarations that disagree answer `null`, and the
 * guard says so out loud. No declaration is Playwright's default: the config's own directory (`.`).
 * The decision table is in `tests/bench-boot.test.ts`.
 */
export function declaredTestDir(source: string): string | null {
  const code = stripComments(source);
  const keys = [...code.matchAll(/["']?\btestDir["']?\s*:\s*/g)];
  if (keys.length === 0) return '.';

  const values = new Set<string>();
  for (const key of keys) {
    const rest = code.slice((key.index ?? 0) + key[0].length);
    const literal = /^(['"`])((?:(?!\1)[^\\\n]|\\.)*)\1/.exec(rest);
    if (!literal) return null;
    const [, quote, value] = literal;
    if (quote === '`' && value.includes('${')) return null;
    values.add(value);
  }
  return values.size === 1 ? [...values][0] : null;
}

/**
 * Does this spec's source take `test` from `@playwright/test` — and so opt out of the bench?
 *
 * Every way of reaching it counts: a named import in either quote style (nothing in this package
 * pins one), aliased or multi-line; Playwright's DEFAULT export, which IS `test`; and a namespace
 * import, from which `pw.test` is one dot away. Type-only imports are fine: a type cannot run a
 * test. Only a line that STARTS with `import` counts, so a comment quoting the forbidden line is
 * not a violation. The decision table lives in `tests/bench-boot.test.ts`.
 */
export function specTakesTestFromPlaywright(source: string): boolean {
  const imports = source.matchAll(/^\s*import\s+([^;]*?)\s*from\s*["']@playwright\/test["']/gm);
  for (const [, clause] of imports) {
    const spec = clause.trim();
    if (spec.startsWith('type ')) continue;
    if (spec.startsWith('*')) return true;
    const brace = spec.indexOf('{');
    const defaultImport = (brace === -1 ? spec : spec.slice(0, brace)).replace(/,\s*$/, '').trim();
    if (defaultImport.length > 0) return true;
    if (brace === -1) continue;
    const named = spec.slice(brace + 1, spec.lastIndexOf('}')).split(',');
    for (const specifier of named) {
      const name = specifier.trim().replace(/^type\s+/, '').split(/\s+as\s+/)[0].trim();
      if (name === 'test') return true;
    }
  }
  return false;
}

/** One reload the bench spent on a navigation, and the transport codes that made it spend it. */
export interface BootReload {
  url: string;
  codes: string[];
  /** Paid from the network-change time budget rather than from `BOOT_RELOAD_LIMIT` (hub#2270). */
  storm: boolean;
}

/**
 * The longest the bench waits for one load of a navigation to settle (ERPlora/hub#2270).
 *
 * A load settles when the app has mounted, or something of ours died, and the app's own requests
 * have stopped. This ceiling only matters for a page that never gets there — a bootstrap that
 * throws, say — and then the spec gets the page as it is, to fail on its own assertions.
 */
export const BOOT_SETTLE_MS = 10_000;

/** How long the app's own requests have to stay quiet before a load counts as settled. */
const BOOT_QUIET_MS = 150;

const BOOT_POLL_MS = 25;

/** Where the shell's own document stands: no `#app` at all, not yet mounted, or mounted. */
type ShellState = 'no-app' | 'booting' | 'mounted';

/** The resource types a load of the shell is made of; XHR and fetch are the spec's business. */
const BOOT_RESOURCE_TYPES = new Set(['document', 'script', 'stylesheet']);

const booksByPage = new WeakMap<object, BootReload[]>();

/**
 * The reloads the bench spent on this page, in order (ERPlora/hub#1839).
 *
 * A spec that injects a failure of OURS has to prove the bench did not reload for IT — not that the
 * bench did not reload at all, because a genuine accident of the runner inside the same navigation
 * makes it reload, correctly. The warning line says why, but it is printed by the bench's Node
 * process, where `page.on('console')` never sees it; these are the same facts, readable from the
 * spec. Reset on every `goto` and every `reload` the spec asks for, like the reloads themselves.
 */
export function bootReloadsOf(page: object): readonly BootReload[] {
  return booksByPage.get(page) ?? [];
}

/**
 * The bench's `test`. Same Playwright `test` as ever, with one difference: a navigation whose own
 * code died on the wire is fetched again instead of being handed to the spec as a blank page.
 *
 * Every e2e spec imports from here rather than from `@playwright/test`, and
 * `tests/bench-boot.test.ts` fails if one of them stops doing so — otherwise a spec written next
 * month would opt out of the recovery without anyone noticing, which is how hub#1518 came back as
 * this issue.
 */
export const test = base.extend({
  page: async ({ page, baseURL }, use) => {
    const appOrigin = originOf(baseURL);
    const isOwn = (url: string): boolean => appOrigin !== undefined && originOf(url) === appOrigin;
    const lost: string[] = [];
    // When the first request of ours died on the wire in the current navigation: the storm's age
    // is counted from here, not from the navigation's start (hub#2270).
    let firstLossAt: number | undefined;
    const inFlight = new Set<object>();
    let ownFailures = 0;
    let lastActivity = Date.now();
    // The main frame's document request that has not committed yet. Only the commit of THIS
    // request replaces the document: `framenavigated` also fires for a `pushState` of the router,
    // which replaces nothing.
    let pendingDocument: Request | undefined;

    page.on('request', (req) => {
      if (
        req.isNavigationRequest() &&
        req.serviceWorker() === null &&
        req.frame() === page.mainFrame()
      ) {
        pendingDocument = req;
      }
      if (!isOwn(req.url()) || !BOOT_RESOURCE_TYPES.has(req.resourceType())) return;
      inFlight.add(req);
      lastActivity = Date.now();
    });
    page.on('requestfinished', (req) => {
      if (inFlight.delete(req)) lastActivity = Date.now();
    });
    // hub#2315: a request the OLD document had in flight when the new one committed gets a
    // `request` event from Playwright and then nothing, ever — no `requestfinished`, no
    // `requestfailed`. Waiting for it spent the whole `BOOT_SETTLE_MS`, which aged the storm past
    // its budget and handed the spec a dead shell. The commit is the moment it stops being ours.
    page.on('framenavigated', (frame) => {
      // No document commits before its response is in: until then this is the router moving the
      // URL of the live one, which can happen while the next document is still on its way.
      if (frame !== page.mainFrame() || !pendingDocument?.existingResponse()) return;
      for (const req of inFlight) if (req !== pendingDocument) inFlight.delete(req);
      pendingDocument = undefined;
      lastActivity = Date.now();
    });
    page.on('requestfailed', (req) => {
      if (inFlight.delete(req)) lastActivity = Date.now();
      const errorText = req.failure()?.errorText;
      // A document request aborted after its response (a download) never commits; any other
      // failure of it still commits Chromium's error page, which is a new document all the same.
      if (req === pendingDocument && errorText === 'net::ERR_ABORTED') pendingDocument = undefined;
      if (isBootTransportFailure(req.url(), errorText, baseURL)) {
        firstLossAt ??= Date.now();
        lost.push(errorText as string);
      } else if (isOwn(req.url()) && errorText !== 'net::ERR_ABORTED') {
        // A failure of ours that is not the network's: the load is over, and it is the spec's red.
        ownFailures += 1;
      }
    });

    const shellState = async (): Promise<ShellState> => {
      try {
        return await page.evaluate(() => {
          const app = document.getElementById('app');
          if (app === null) return 'no-app';
          return app.hasAttribute('data-v-app') ? 'mounted' : 'booting';
        });
      } catch {
        // The document is being replaced under us (a reload of the app's own): still booting.
        return 'booting';
      }
    };

    // hub#2270, hole A: `load` is not the end of a load. The router fetches the screen after it,
    // and `main.ts` mounts only once that screen has arrived — the 1440 red died 60 ms after `goto`
    // resolved. So wait for the app's own verdict (mounted, or something of ours died), and for its
    // own requests to go quiet, before deciding anything.
    const settle = async (): Promise<void> => {
      const deadline = Date.now() + BOOT_SETTLE_MS;
      while (Date.now() < deadline) {
        const quiet = inFlight.size === 0 && Date.now() - lastActivity >= BOOT_QUIET_MS;
        if (quiet) {
          if (lost.length > 0 || ownFailures > 0) return;
          if ((await shellState()) !== 'booting' && inFlight.size === 0) return;
        }
        await new Promise((resolve) => setTimeout(resolve, BOOT_POLL_MS));
      }
    };

    const navigate = page.goto.bind(page);
    const reloadPage = page.reload.bind(page);

    // A load whose own document died of the network throws in Playwright. That throw is the same
    // accident as a dead module, so it is settled and decided like one; any other throw is the
    // spec's.
    const attempt = async (
      load: () => Promise<Awaited<ReturnType<typeof navigate>>>,
    ): Promise<Awaited<ReturnType<typeof navigate>>> => {
      try {
        return await load();
      } catch (error) {
        if (lost.length === 0) throw error;
        return null;
      }
    };

    type LoadOptions = Parameters<typeof reloadPage>[0];

    // One navigation, from its first load to the page the spec gets. `goto` and `reload` both come
    // through here: the spec's reload is a fresh load of the whole shell, as exposed to the runner's
    // network as the first one (hub#2274 died ~500 ms after `page.reload()`).
    const recover = async (
      url: string,
      first: () => Promise<Awaited<ReturnType<typeof navigate>>>,
      options: LoadOptions,
    ): Promise<Awaited<ReturnType<typeof navigate>>> => {
      lost.length = 0;
      ownFailures = 0;
      firstLossAt = undefined;
      const books: BootReload[] = [];
      booksByPage.set(page, books);
      let counted = 0;
      let response = await attempt(first);

      for (;;) {
        await settle();
        const codes = [...new Set(lost)];
        // The age of the storm, never of the navigation: a first load that was merely slow (Vite
        // transforming the shell cold, a loaded runner) must not spend the budget before anything
        // died.
        const stormAge = firstLossAt === undefined ? 0 : Date.now() - firstLossAt;
        const step = nextBootStep(codes, counted, stormAge);
        if (step === 'hand-over') {
          // Giving up with losses on the page hands the spec a shell that may never mount; the red
          // that follows has to point here, not at the screen the spec was looking for (hub#2315).
          if (codes.length > 0) {
            // eslint-disable-next-line no-console
            console.warn(
              `[bench] BENCH_GAVE_UP ${lost.length} request(s) for the app's own code died on the ` +
                `wire (${codes.join(', ')}) while loading ${url}, after ${books.length} reload(s) ` +
                `and a storm ${stormAge} ms old — handing the page over as it is. See hub#2315.`,
            );
          }
          break;
        }
        const storm = step === 'reload-storm';
        if (!storm) counted += 1;
        // Said out loud, never swallowed: a bench that heals itself in silence is a bench whose
        // flake rate nobody can measure, and hub#1806 exists because one went unmeasured for a
        // week. The line names the browser's own error so the next reader does not have to guess.
        // eslint-disable-next-line no-console
        console.warn(
          `[bench] ${lost.length} request(s) for the app's own code died on the wire ` +
            `(${codes.join(', ')}) while loading ${url} — reloading ` +
            (storm
              ? `(network change, outside the budget; see hub#2270).`
              : `(${counted}/${BOOT_RELOAD_LIMIT}). See hub#1806.`),
        );
        books.push({ url, codes, storm });
        lost.length = 0;
        ownFailures = 0;
        // A document that died leaves the page on Chromium's error page, where a reload would
        // reload the error; going back to the navigation's own URL is what fetches it again.
        response = await attempt(() =>
          page.url().startsWith('chrome-error://') ? navigate(url, options) : reloadPage(options),
        );
      }

      return response;
    };

    page.goto = async (url, options) => recover(url, () => navigate(url, options), options);
    page.reload = async (options) => {
      const url = page.url();
      return recover(url, () => reloadPage(options), options);
    };

    await use(page);
  },
});
