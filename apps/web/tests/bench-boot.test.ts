// Guards for the bench's boot recovery (ERPlora/hub#1806).
//
// These live in `tests/` and NOT in `tests/e2e/` on purpose: Playwright's default `testMatch`
// picks up `*.test.ts` as well as `*.spec.ts`, so a vitest file inside `testDir` would be handed
// to Playwright and fail there. `bench-ports.test.ts` sits here for the same reason.

import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { isBootTransportFailure, TRANSIENT_TRANSPORT_ERRORS } from './bench-boot';

const APP_ORIGIN = 'http://localhost:8915';
const MODULE_URL = `${APP_ORIGIN}/src/lib/money.ts`;

describe('isBootTransportFailure', () => {
  // THE measured case (hub#1806, run 34532770133): one network-configuration change on the runner
  // cancelled 79 in-flight requests to the dev server inside 33.7 ms, so the app's module graph
  // arrived half-loaded and Vue never mounted. The page was blank and `import-lead` was never in
  // the DOM. Nothing about the PR under test was involved.
  it('is true for a network change that killed a request for the app own code', () => {
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_NETWORK_CHANGED', APP_ORIGIN)).toBe(true);
  });

  // What the e2e reproduction (`BenchBootRecovery.spec.ts`) injects, because `route.abort()` has
  // no code for a network change. Same class, same code path.
  it('is true for a connection reset', () => {
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_CONNECTION_RESET', APP_ORIGIN)).toBe(true);
  });

  // 🔴 The exclusions are the point of this list. A reload that fires on ANY failed request is a
  // blanket retry, and a blanket retry is exactly the gate-that-lies this issue exists to remove:
  // it would turn a real defect into an intermittent green.
  it('is false when the page itself cancelled the request', () => {
    // Routine: a navigation away, an AbortController, an <img> removed mid-flight.
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_ABORTED', APP_ORIGIN)).toBe(false);
  });

  it('is false when the browser blocked the request', () => {
    // A CSP violation is a defect of ours (root CLAUDE.md), never something to retry away.
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_BLOCKED_BY_CSP', APP_ORIGIN)).toBe(false);
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_BLOCKED_BY_CLIENT', APP_ORIGIN)).toBe(false);
  });

  it('is false when nothing is listening on the dev server', () => {
    // The bench failed to come up. Retrying only delays a failure that has to be loud and fast.
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_CONNECTION_REFUSED', APP_ORIGIN)).toBe(false);
  });

  it('is false for a request that is not the app own code', () => {
    // Only the app's own origin counts: a third party dying is a fact about the product, and the
    // spec that cares must assert on it.
    expect(
      isBootTransportFailure('https://erplora.com/api/x', 'net::ERR_NETWORK_CHANGED', APP_ORIGIN),
    ).toBe(false);
  });

  it('is false when the browser reported no error text', () => {
    expect(isBootTransportFailure(MODULE_URL, undefined, APP_ORIGIN)).toBe(false);
  });

  it('is false when the bench has no origin to compare against', () => {
    expect(isBootTransportFailure(MODULE_URL, 'net::ERR_NETWORK_CHANGED', undefined)).toBe(false);
  });

  it('keeps the excused codes to transport failures that lose the connection', () => {
    // Pinned so that widening the list is a deliberate edit with a reason, not a drive-by.
    expect([...TRANSIENT_TRANSPORT_ERRORS].sort()).toEqual([
      'net::ERR_ADDRESS_UNREACHABLE',
      'net::ERR_CONNECTION_ABORTED',
      'net::ERR_CONNECTION_CLOSED',
      'net::ERR_CONNECTION_RESET',
      'net::ERR_EMPTY_RESPONSE',
      'net::ERR_INTERNET_DISCONNECTED',
      'net::ERR_NETWORK_CHANGED',
      'net::ERR_NETWORK_IO_SUSPENDED',
      'net::ERR_SOCKET_NOT_CONNECTED',
    ]);
  });
});

// The mechanical half of the guard (root CLAUDE.md: when the incident is a PATTERN, the fix
// includes the rule that stops it reappearing in ANY new file). The recovery only reaches a spec
// that takes `test` from the bench, so a spec that imports it straight from Playwright opts out of
// it in silence — which is how this would come back a third time in a spec nobody has written yet.
describe('every e2e spec takes its `test` from the bench', () => {
  const E2E_DIR = fileURLToPath(new URL('./e2e', import.meta.url));

  const specs = readdirSync(E2E_DIR).filter((name) => name.endsWith('.spec.ts'));

  it('finds the specs to check', () => {
    // Without this the loop below is vacuously green if the directory ever moves.
    expect(specs.length).toBeGreaterThanOrEqual(11);
  });

  it.each(specs)('%s does not import `test` from @playwright/test', (name) => {
    const source = readFileSync(join(E2E_DIR, name), 'utf8');
    const playwrightImports = source.matchAll(/import\s*\{([^}]*)\}\s*from\s*'@playwright\/test'/g);
    for (const [, clause] of playwrightImports) {
      const named = clause.split(',').map((part) => part.trim().split(/\s+as\s+/)[0].trim());
      expect(named, `${name} must take \`test\` from '../bench-boot'`).not.toContain('test');
    }
  });
});
