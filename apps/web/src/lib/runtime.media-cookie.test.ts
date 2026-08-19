// **The shell asking for the credential a photo can carry** (hub#791).
//
// Every request the app makes goes out with `X-Hub-Session` attached by hand. A photo is not one of
// those: `<img src="/api/media/raw?path=…">` is issued by the rendering engine, which attaches
// nothing, so every product picture in the till came back 401 and the grid of tiles was blank.
//
// The hub's answer is a read-only cookie scoped to that one door (`POST /api/media/session`), and
// this file pins the shell's half: that it is asked for at all, on the authenticated door, and that
// it never becomes a reason for the app to fail to start.
//
// It is deliberately paranoid about the failure modes, because the cost of getting them wrong is
// asymmetric: a missing cookie loses photos, but a throw here would happen on boot — before the
// router mounts — and lose the whole app.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ensureMediaCookie } from './runtime';
import { setHubSession } from './session';

/** The suite runs in `node` (vite.config.ts): the session store needs a `localStorage` to live in. */
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

function respondWith(status: number, calls?: Array<{ url: string; init?: RequestInit }>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      calls?.push({ url, init });
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve({ ok: status < 400, data: { cookie: status < 400 } }),
      });
    }),
  );
}

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the credential the browser attaches to a photo', () => {
  it('asks the runtime for it on the authenticated door', async () => {
    setHubSession('sess-live');
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    respondWith(200, calls);

    expect(await ensureMediaCookie()).toBe(true);
    expect(calls[0]?.url).toContain('/api/media/session');
    expect(calls[0]?.init?.method).toBe('POST');
    // The cookie is what the hub SETS on this response; the request itself still authenticates the
    // way everything else does.
    expect((calls[0]?.init?.headers as Record<string, string>)?.['X-Hub-Session']).toBe('sess-live');
  });

  it('does not knock on the door before there is a session', async () => {
    // On a cold boot the login screen renders first. Asking here would be a guaranteed 401, and a
    // 401 is not free: it feeds the central dead-session reaction (hub#846).
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    respondWith(200, calls);

    expect(await ensureMediaCookie()).toBe(false);
    expect(calls).toHaveLength(0);
  });

  it('answers false instead of throwing when the runtime refuses', async () => {
    setHubSession('sess-stale');
    respondWith(401);
    expect(await ensureMediaCookie()).toBe(false);
  });

  it('answers false instead of throwing when the runtime cannot be reached', async () => {
    // This runs on boot. A rejected promise here would take the app down before the router mounts,
    // trading "photos are missing" for "the till does not open" — on the offline path, of all of
    // them.
    setHubSession('sess-live');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    expect(await ensureMediaCookie()).toBe(false);
  });
});
