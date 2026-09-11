// hub#1801 — **the second device threw you out and the hub said nothing**.
//
// hub#846 gave the shell one reaction to a confirmed-dead runtime session; what it could not do is
// say WHY, because the runtime answered the same `401` for a session that ran out of time and for
// one the plan displaced. From where the cashier stands those are not the same event at all: the
// first is «it's been a while», the second is «somebody opened the till on the other tablet and
// this plan covers one». Told neither, they read it as the hub going down, and they call support.
//
// Since hub#1801 the probe door (`GET /api/settings`, the any-role door the confirmation already
// used) carries a stable CODE next to the message, and that code is what this file pins: the
// reason reaches the hook as DATA (ADR-0055 — the sentence is the shell's, in `en` and `es`), and
// an ordinary expiry keeps arriving WITHOUT it. Only the pair is worth anything: if both looked
// alike here, the screen would be guessing again, just in the other direction.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_EVICTED_DEVICE_LIMIT } from './session-end-reason';
import { fetchStreamTicket, setOnRuntimeSessionExpired } from './runtime';
import { getHubSession, setHubSession, setUser, user } from './session';

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
  };
}

/** The probe door answers `401` with `body`; everything else answers a bare `401`. */
function stubProbe(body: unknown) {
  const spy = vi.fn().mockImplementation((url: string) =>
    Promise.resolve({
      ok: false,
      status: 401,
      json: () => Promise.resolve(String(url).includes('/api/settings') ? body : { ok: false }),
      text: () => Promise.resolve(JSON.stringify(body ?? {})),
    }),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

const expired = vi.fn();

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
  setHubSession('live-session-token');
  setUser({ id: 'u1', name: 'Cashier', email: 'cashier@shop.test', role: 'employee' });
  expired.mockClear();
  setOnRuntimeSessionExpired(expired);
});

afterEach(() => {
  setOnRuntimeSessionExpired(null);
  setUser(null);
  vi.unstubAllGlobals();
});

describe('a session the plan displaced (hub#1801)', () => {
  it('hands the reason to the shell, so the login screen can explain instead of staying quiet', async () => {
    stubProbe({ ok: false, error: 'no autenticado: sesión cerrada', code: SESSION_EVICTED_DEVICE_LIMIT });

    await fetchStreamTicket();

    expect(expired).toHaveBeenCalledTimes(1);
    expect(expired).toHaveBeenCalledWith(SESSION_EVICTED_DEVICE_LIMIT);
    // It is still a death: the local session goes, exactly as in hub#846.
    expect(getHubSession()).toBeNull();
    expect(user.value).toBeNull();
  });

  it('an ordinary expiry carries NO reason: sending that person to buy a bigger plan would be a lie', async () => {
    stubProbe({ ok: false, error: 'no autenticado: sesión inválida o caducada', code: 'unauthorized' });

    await fetchStreamTicket();

    expect(expired).toHaveBeenCalledTimes(1);
    expect(expired).toHaveBeenCalledWith(null);
  });

  it('a door that answers no code at all is an expiry too, never an eviction', async () => {
    // An older runtime than the shell (a hub mid-update) must degrade to hub#846 behaviour, not
    // invent a reason: absence of the code is absence of information.
    stubProbe({ ok: false, error: 'no autenticado: sesión inválida o caducada' });

    await fetchStreamTicket();

    expect(expired).toHaveBeenCalledWith(null);
  });

  it('a body that is not JSON at all still ends the session, silently as before', async () => {
    const spy = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: false,
        status: 401,
        json: () => Promise.reject(new SyntaxError('not json')),
        text: () => Promise.resolve('<html>proxy error</html>'),
      }),
    );
    vi.stubGlobal('fetch', spy);

    await fetchStreamTicket();

    expect(expired).toHaveBeenCalledWith(null);
    expect(getHubSession()).toBeNull();
  });
});
