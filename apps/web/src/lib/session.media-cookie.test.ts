// **Every way in has to end with the photos working** (hub#791).
//
// The media cookie carries the session token, so it has to be minted whenever a session starts — and
// there are five call sites that start one: the PIN pad, the cloud login, the invite/courier flow
// and the user switch. Wiring the mint at each of them means the sixth one, whenever it is written,
// ships a till whose product photos are blank and nothing points at why.
//
// So it hangs off `setHubSession`, the one function all five already go through. This file pins that
// choke point: a session appearing mints the cookie, and clearing one never does.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ensureMediaCookie = vi.fn().mockResolvedValue(true);
// `setHubSession` also re-seeds the active-module set (hub#1211, `session.active-modules.test.ts`);
// it is mocked here only so that chain resolves instead of tripping over a missing export.
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

/** The mint is fire-and-forget: let the dynamic import and its `.then` settle. */
const settle = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
  ensureMediaCookie.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the media cookie follows the session', () => {
  it('is minted when a session starts', async () => {
    setHubSession('sess-fresh');
    await settle();
    expect(ensureMediaCookie).toHaveBeenCalledTimes(1);
  });

  it('is not minted when the session is cleared', async () => {
    setHubSession(null);
    await settle();
    // Logging out has nothing to mint. The cookie already went inert with the session it carries:
    // the runtime revokes it server-side, so the token in the jar resolves to nobody.
    expect(ensureMediaCookie).not.toHaveBeenCalled();
  });

  it('never lets a failed mint escape into the login flow', async () => {
    // Signing in cannot fail because a photo credential could not be fetched. If this throw were
    // allowed to propagate, a hub with a slow or unreachable media door would refuse logins.
    ensureMediaCookie.mockRejectedValueOnce(new Error('offline'));
    expect(() => setHubSession('sess-fresh')).not.toThrow();
    await settle();
  });
});
