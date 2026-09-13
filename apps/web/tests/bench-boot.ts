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

import { test as base, expect, request } from '@playwright/test';

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
}

const booksByPage = new WeakMap<object, BootReload[]>();

/**
 * The reloads the bench spent on this page, in order (ERPlora/hub#1839).
 *
 * A spec that injects a failure of OURS has to prove the bench did not reload for IT — not that the
 * bench did not reload at all, because a genuine accident of the runner inside the same navigation
 * makes it reload, correctly. The warning line says why, but it is printed by the bench's Node
 * process, where `page.on('console')` never sees it; these are the same facts, readable from the
 * spec. Reset on every `goto`, like the reloads themselves.
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
    const lost: string[] = [];

    page.on('requestfailed', (req) => {
      const errorText = req.failure()?.errorText;
      if (isBootTransportFailure(req.url(), errorText, baseURL)) lost.push(errorText as string);
    });

    const navigate = page.goto.bind(page);

    page.goto = async (url, options) => {
      lost.length = 0;
      const books: BootReload[] = [];
      booksByPage.set(page, books);
      let response = await navigate(url, options);

      for (let reload = 1; lost.length > 0 && reload <= BOOT_RELOAD_LIMIT; reload += 1) {
        // Said out loud, never swallowed: a bench that heals itself in silence is a bench whose
        // flake rate nobody can measure, and this issue exists because one went unmeasured for a
        // week. The line names the browser's own error so the next reader does not have to guess.
        // eslint-disable-next-line no-console
        console.warn(
          `[bench] ${lost.length} request(s) for the app's own code died on the wire ` +
            `(${[...new Set(lost)].join(', ')}) while loading ${url} — reloading ` +
            `(${reload}/${BOOT_RELOAD_LIMIT}). See hub#1806.`,
        );
        books.push({ url, codes: [...new Set(lost)] });
        lost.length = 0;
        response = await page.reload(options);
      }

      return response;
    };

    await use(page);
  },
});
