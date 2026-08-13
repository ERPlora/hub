// hub#846 — a 401 from the RUNTIME must end the shell session, once, instead of every screen
// quietly emptying while the user still sees their name and navigation (the 401-every-10s loop
// of hub#902, and the "you have no apps" lie of hub#894 share this mechanism).
//
// The contract under test, in four lines:
//   1. A 401 while the shell holds a session is only a death sentence after CONFIRMING it against
//      an any-role door (`GET /api/settings`): several admin-gated handlers answer 401 to a live
//      cashier whose ROLE is short (crates/server/src/settings.rs maps every AuthError — including
//      `Forbidden` — to 401), and signing that cashier out would be a regression, not a fix.
//   2. A CONFIRMED death invalidates the local session exactly once (dozens of calls are in
//      flight when a screen loads) and raises `RuntimeSessionExpiredError` — never "no data".
//   3. A network failure never signs anyone out (contract of hub#770: retryable, last good data).
//   4. A 200 whose envelope says `ok:false` is a DOMAIN error: it surfaces, it does not empty the
//      screen, and it does not touch the session.
//
// Lesson of hub#770 applied: no collaborator is mocked here — every test drives the REAL exported
// functions with `fetch` stubbed at the network level, so a test can only pass through branches
// the production code actually has.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  RuntimeSessionExpiredError,
  fetchStreamTicket,
  listInstalledModules,
  listModuleUpdates,
  putModuleCapabilities,
  setOnRuntimeSessionExpired,
} from './runtime';
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

interface Route {
  status: number;
  body?: unknown;
}

/** Network-level stub: routes by URL substring, first match wins. Returns the spy for call counts. */
function stubFetch(routes: Array<[match: string, route: Route]>) {
  const spy = vi.fn().mockImplementation((url: string) => {
    const hit = routes.find(([match]) => String(url).includes(match));
    if (!hit) return Promise.reject(new Error(`unrouted fetch in test: ${url}`));
    const [, route] = hit;
    return Promise.resolve({
      ok: route.status >= 200 && route.status < 300,
      status: route.status,
      json: () => Promise.resolve(route.body ?? {}),
      text: () => Promise.resolve(JSON.stringify(route.body ?? {})),
    });
  });
  vi.stubGlobal('fetch', spy);
  return spy;
}

const probeCalls = (spy: ReturnType<typeof vi.fn>) =>
  spy.mock.calls.filter(([url]) => String(url).includes('/api/settings')).length;

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

describe('a runtime 401 with a confirmed-dead session (hub#846)', () => {
  it('ends the shell session, raises the reaction ONCE, and rejects — never resolves to "no data"', async () => {
    const spy = stubFetch([
      ['/api/settings', { status: 401, body: { ok: false, error: 'sesión inválida o caducada' } }],
      ['/api/modules/updates', { status: 401, body: { ok: false } }],
    ]);

    // A screen load fires many calls at once: every one must reject, the reaction must fire once.
    const results = await Promise.allSettled([listModuleUpdates(), listModuleUpdates()]);

    for (const r of results) {
      expect(r.status).toBe('rejected');
      expect((r as PromiseRejectedResult).reason).toBeInstanceOf(RuntimeSessionExpiredError);
    }
    expect(expired).toHaveBeenCalledTimes(1);
    expect(getHubSession()).toBeNull();
    expect(user.value).toBeNull();
    // Single-flight confirmation: one probe for the whole burst, not one per call in flight.
    expect(probeCalls(spy)).toBe(1);
  });

  it('the event-ticket loop (the 401-every-10s symptom of hub#902) reacts too, but keeps its never-throw contract', async () => {
    stubFetch([
      ['/api/settings', { status: 401, body: { ok: false } }],
      ['/api/events/ticket', { status: 401, body: { ok: false } }],
    ]);

    await expect(fetchStreamTicket()).resolves.toBeNull();

    expect(expired).toHaveBeenCalledTimes(1);
    expect(getHubSession()).toBeNull();
  });
});

describe('what must NOT sign anyone out', () => {
  it('a 401 that means "role not enough" (probe passes) leaves the session alone and surfaces the refusal', async () => {
    stubFetch([
      ['/api/settings', { status: 200, body: { currency: 'EUR' } }],
      ['/capabilities', { status: 401, body: { ok: false, error: 'se requiere rol owner/admin' } }],
    ]);

    await expect(putModuleCapabilities('sales', { manage_flows: true })).rejects.toThrow(
      'put-capabilities sales → 401',
    );

    expect(expired).not.toHaveBeenCalled();
    expect(getHubSession()).toBe('live-session-token');
  });

  it('a network failure stays a retryable error: no logout, no reaction', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    await expect(fetchStreamTicket()).resolves.toBeNull();

    expect(expired).not.toHaveBeenCalled();
    expect(getHubSession()).toBe('live-session-token');
  });

  it('a probe that cannot be read as a verdict (network failure) keeps the session: death is proven, never presumed', async () => {
    const spy = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes('/api/settings')) return Promise.reject(new Error('offline'));
      return Promise.resolve({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ ok: false }),
        text: () => Promise.resolve('{}'),
      });
    });
    vi.stubGlobal('fetch', spy);

    await expect(listModuleUpdates()).resolves.toEqual([]);

    expect(expired).not.toHaveBeenCalled();
    expect(getHubSession()).toBe('live-session-token');
  });

  it('a 401 with NO local session (login screen probing) reacts to nothing and does not probe', async () => {
    setUser(null);
    setHubSession(null);
    const spy = stubFetch([['', { status: 401, body: { ok: false } }]]);

    await expect(fetchStreamTicket()).resolves.toBeNull();

    expect(expired).not.toHaveBeenCalled();
    expect(spy).toHaveBeenCalledTimes(1); // the original call only — no confirmation probe
  });
});

describe('a 200 whose envelope says ok:false (the listInstalledModules flattening of hub#894)', () => {
  it('surfaces as a DOMAIN error instead of an empty hub, and never touches the session', async () => {
    stubFetch([
      ['/api/modules?', { status: 200, body: { ok: false, error: 'registry rebuilding' } }],
    ]);

    await expect(listInstalledModules()).rejects.toThrow('registry rebuilding');

    expect(expired).not.toHaveBeenCalled();
    expect(getHubSession()).toBe('live-session-token');
  });

  it('keeps returning the data on a healthy envelope', async () => {
    stubFetch([
      [
        '/api/modules?',
        {
          status: 200,
          body: { ok: true, data: [{ id: 'sales', name: 'Sales', status: 'active', version: '1' }] },
        },
      ],
    ]);

    await expect(listInstalledModules()).resolves.toHaveLength(1);
  });
});
