// hub#1801 — the WIRE, which is the only part of the chain that lives in the boot.
//
// The runtime names the reason and `LoginPage.vue` knows how to paint it; between the two there is
// one line in `main.ts` that has to carry the reason from the hook into the query. `main.ts` cannot
// be mounted in a unit test — it opens sockets, registers the service worker and mounts the app —
// so this reads the SOURCE, the same way `main-asks-for-notices.hub1732.test.ts` does.
//
// A weak assertion on purpose: it proves the wire is there, not that it behaves. The behaviour is
// pinned by `lib/runtime.session-eviction.hub1801.test.ts` (the reason reaches the hook) and by
// `views/login-session-taken-over.hub1801.test.ts` (the screen explains it). What THIS catches is
// somebody deleting the wire between them while both of those stay green — which is exactly the
// shape of the original defect: every piece in place, nothing joined.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { SESSION_EVICTED_DEVICE_LIMIT } from './lib/session-end-reason';

const MAIN = readFileSync(fileURLToPath(new URL('./main.ts', import.meta.url)), 'utf8');

/**
 * The `setOnRuntimeSessionExpired(...)` call ALONE.
 *
 * Scoping is the whole point: asserted against the file, every one of these passes on the IMPORT
 * line or on the Cloud plane's twin hook, and the mutant that matters — reverting this hook to the
 * single hedged sentence of hub#846 — stays green.
 */
function runtimeHook(source: string): string {
  const start = source.indexOf('setOnRuntimeSessionExpired(');
  expect(start).toBeGreaterThan(-1);
  const end = source.indexOf('\n});', start);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe('the shell carries the eviction reason to the login screen', () => {
  it('takes the reason the hook now hands it and puts it in the query', () => {
    const hook = runtimeHook(MAIN);
    expect(hook).toContain('reason');
    expect(hook).toContain('SESSION_EVICTED_DEVICE_LIMIT');
  });

  it('names the reason through the shared constant, never a literal of its own', () => {
    // Two spellings of the same code is how one of them ends up being the stale one.
    expect(MAIN).toContain("from './lib/session-end-reason'");
    expect(runtimeHook(MAIN)).not.toContain(SESSION_EVICTED_DEVICE_LIMIT);
  });

  it('says it through i18n, never a hardcoded sentence (ADR-0055/0199)', () => {
    expect(runtimeHook(MAIN)).toContain('i18n.global.t(');
    expect(MAIN).not.toMatch(/Session opened on another|Sesión abierta en otro/);
  });

  it('and the region that is asserted really is only that hook', () => {
    // The positive control of the scoping above, placed AFTER the region: a slice that ran to the
    // end of the file would swallow this and quietly turn every assertion into a file-wide one.
    expect(MAIN).toContain('setOnHubGone');
    expect(runtimeHook(MAIN)).not.toContain('setOnHubGone');
  });
});
