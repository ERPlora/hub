// **Every way in has to end with the short-circuit armed** (hub#1211).
//
// `queryOptional`/`queryAllOptional` (module-sdk) skip the round trip for an ABSENT module by
// reading the shell's active-module set. That set is seeded when the SDK client is built — which
// `main.ts` does on a cold boot, BEFORE anyone signs in, so the seed cannot ask the runtime yet.
// Login is a route change, not a reload: without a re-seed on the way in, the set stays "not known"
// for the whole session, the SDK keeps falling back to the transport, and the 404-per-call this
// fix removes is still there for every real user (the e2e never saw it: it injects the session
// before boot). Same choke point and same reasoning as the media cookie (hub#791): five call sites
// open a session, and all of them already go through `setHubSession`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ensureMediaCookie = vi.fn().mockResolvedValue(true);
const refreshActiveModuleIds = vi.fn().mockResolvedValue(undefined);
vi.mock('./runtime', () => ({ ensureMediaCookie, refreshActiveModuleIds }));

import { setHubSession } from './session';

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, String(value));
    },
  } as Storage;
}

/** The re-seed is fire-and-forget: let the dynamic import and its `.then` settle. */
const settle = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
  ensureMediaCookie.mockClear();
  refreshActiveModuleIds.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the active-module set follows the session (hub#1211)', () => {
  it('is re-seeded when a session starts', async () => {
    setHubSession('sess-fresh');
    await settle();
    expect(refreshActiveModuleIds).toHaveBeenCalledTimes(1);
  });

  it('is not asked for when the session is cleared', async () => {
    setHubSession(null);
    await settle();
    expect(refreshActiveModuleIds).not.toHaveBeenCalled();
  });

  it('never lets a failed re-seed escape into the login flow', async () => {
    // Signing in cannot fail because the module list could not be fetched: the SDK simply keeps
    // asking the transport, as it did before the short-circuit existed.
    refreshActiveModuleIds.mockRejectedValueOnce(new Error('offline'));
    expect(() => setHubSession('sess-fresh')).not.toThrow();
    await settle();
  });

  it('does not stop the media cookie from being minted when it fails', async () => {
    // The two are independent chains on purpose: one refusing must not cost the other.
    refreshActiveModuleIds.mockRejectedValueOnce(new Error('offline'));
    setHubSession('sess-fresh');
    await settle();
    expect(ensureMediaCookie).toHaveBeenCalledTimes(1);
  });
});
