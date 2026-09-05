// **How the person at the till proved who they are, kept next to the session it belongs to**
// (hub#1400, pm#196).
//
// The door to erplora.com is only offered to somebody who typed their e-mail and password, never to
// a PIN of the shift (ADR-0226). The runtime decides that — `hub_session.credential_kind` (hub#658)
// is the authority — but the shell has to know before it paints, so the login response carries it.
//
// It hangs off `setHubSession` and NOT off the user object on purpose. It is a property of the
// SESSION, not of the person: `applyProfile` rebuilds `SessionUser` from `GET /api/profile` every
// time the profile is read, and a field parked there would be silently wiped on the first refresh —
// the door would vanish moments after appearing. `setHubSession` is the one function all five ways
// in already go through, and `/api/profile` never touches it.
//
// The default is CLOSED: a session opened before this shipped, or one whose kind never arrived,
// says nothing — and "nothing" must not read as "a password".
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { watchEffect } from 'vue';

const ensureMediaCookie = vi.fn().mockResolvedValue(true);
const refreshActiveModuleIds = vi.fn().mockResolvedValue(undefined);
vi.mock('./runtime', () => ({ ensureMediaCookie, refreshActiveModuleIds }));

import { openedWithCloudLogin, setHubSession } from './session';

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

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
  setHubSession(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('how this session was opened', () => {
  it('is a password login when the runtime said so', () => {
    setHubSession('token-1', 'cloud');

    expect(openedWithCloudLogin.value).toBe(true);
  });

  it('is not a password login when the shift typed a PIN', () => {
    setHubSession('token-1', 'pin');

    expect(openedWithCloudLogin.value).toBe(false);
  });

  it('is not a password login when somebody passed a badge', () => {
    setHubSession('token-1', 'badge');

    expect(openedWithCloudLogin.value).toBe(false);
  });

  it('says no when the login never said — "not stated" is not "a password"', () => {
    // What a session opened before this shipped looks like: the token is there and the answer is
    // not. Reading that as a password would hand the door to exactly the PIN sessions it locks out.
    setHubSession('token-1');

    expect(openedWithCloudLogin.value).toBe(false);
  });

  it('forgets it when the session ends, so the next one starts closed', () => {
    setHubSession('token-1', 'cloud');

    setHubSession(null);

    expect(openedWithCloudLogin.value).toBe(false);
  });

  it('survives a reload: it is read back from where the session token lives', async () => {
    setHubSession('token-1', 'cloud');
    vi.resetModules();

    const reloaded = await import('./session');

    expect(reloaded.openedWithCloudLogin.value).toBe(true);
  });

  it('is reactive, so a login repaints the topbar without a reload', () => {
    // `canOpenManagement` is a computed over this. Reading `localStorage` directly would leave it
    // frozen at whatever was true when the module loaded — on a cold boot, before anybody signed in.
    const seen: boolean[] = [];
    const stop = watchEffect(() => seen.push(openedWithCloudLogin.value));

    setHubSession('token-1', 'cloud');

    stop();
    expect(seen[0]).toBe(false);
    expect(openedWithCloudLogin.value).toBe(true);
  });
});
