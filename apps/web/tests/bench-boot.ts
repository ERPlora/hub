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
 * Every spec file Playwright would run under `dir`, as paths relative to it.
 *
 * It walks SUBDIRECTORIES because Playwright does: `playwright.config.ts` sets `testDir: './e2e'`
 * and leaves the default `testMatch`, which is recursive. The guard that uses this list is only
 * worth anything if it sees exactly what Playwright sees — with a flat `readdirSync` a spec one
 * folder down took `test` straight from Playwright, ran for real, and the guard stayed green
 * (ERPlora/hub#1820).
 */
export function listE2eSpecs(dir: string): string[] {
  return readdirSync(dir, { recursive: true })
    .map((entry) => String(entry))
    .filter((name) => name.endsWith('.spec.ts'))
    .sort();
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
        lost.length = 0;
        response = await page.reload(options);
      }

      return response;
    };

    await use(page);
  },
});
