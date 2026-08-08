// The bridge pairing credential has no client left, and the shell must stop asking for one
// (ADR-0196 §3, hub#340).
//
// hub#339 removed `WsBridgeTransport` from the SDK — the only thing that ever PRESENTED the bridge
// token. What it deliberately left behind was the other half: the shell kept calling
// `startBridgeTokenRefresh()` on boot, which minted a fresh machine credential every 12 minutes
// for a reader that no longer existed. A credential nobody reads is not dead weight, it is a
// secret with an expiry and no purpose.
//
// This is the "nobody calls it" test that a suppressive change needs: it is asserted over the
// WHOLE shell source, not over one module, because the point is a count — zero callers — and a
// per-module assertion could not tell the difference between "removed" and "moved next door".
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const SRC = new URL('..', import.meta.url).pathname;

/** Every `.ts`/`.vue` under `apps/web/src`, tests excluded (a test may name what it forbids). */
function shellSources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return shellSources(path);
    if (entry.name.endsWith('.test.ts')) return [];
    return /\.(ts|vue)$/.test(entry.name) ? [path] : [];
  });
}

/**
 * Source with comments removed — what the browser would actually run.
 *
 * The distinction matters here: the retirement leaves a tombstone comment that NAMES the retired
 * route on purpose, so the next reader learns why the file is a stump instead of re-adding it. A
 * scan that could not tell a mention from a call would force the tombstone out, which is the
 * opposite of what this test is for.
 */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

const sources = shellSources(SRC).map(
  (path) => [path, code(readFileSync(path, 'utf8'))] as const,
);

describe('the retired bridge pairing credential', () => {
  it('is asked for by nobody: no shell source calls the runtime proxy', () => {
    // `/api/bridge/token` is the runtime route that signed the call to the SaaS with the
    // `cloud_api_token` and handed the browser an `aud=erplora-bridge` JWT. The route is gone;
    // a caller left behind would be a silent 404 every 12 minutes.
    const callers = sources.filter(([, code]) => code.includes('/api/bridge/token'));
    expect(callers.map(([path]) => path)).toEqual([]);
  });

  it('is not stored, refreshed or presented anywhere in the shell', () => {
    // The pairing token used to live in `localStorage` under `erplora.bridge.token` and travel as
    // a `?token=` query param on the WS URL (a browser `WebSocket` cannot set headers). Both are
    // retired with the daemon that verified them.
    const forbidden = [
      'erplora.bridge.token',
      'startBridgeTokenRefresh',
      'refreshBridgeToken',
      'bridgeWsUrl',
      'getBridgeToken',
      'setBridgeToken',
    ];
    const survivors = sources.flatMap(([path, code]) =>
      forbidden.filter((symbol) => code.includes(symbol)).map((symbol) => `${path}: ${symbol}`),
    );
    expect(survivors).toEqual([]);
  });
});
