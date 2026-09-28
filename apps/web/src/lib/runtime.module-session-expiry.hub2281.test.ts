// hub#2281 — a module screen that meets a dead session leads to the login the shell already has.
//
// Kitchen › Stations, session running out: the module's `command` came back 401 and the screen
// showed a red «unknown error» — and nothing else happened. The shell's own calls go through the
// central reaction of hub#846 (probe, close the session once, explain, lead to the login); the
// module transport did not, because it fetched with the bare global `fetch`. So the one place the
// cashier was actually working was the one place a dead session went unnoticed.
//
// The contract: a 401 on the module transport feeds the SAME reaction — no second login flow —
// and the module still gets its refusal (code `unauthorized`), because a 401 means the command
// never ran: it must not turn into «we can't tell whether it completed» (hub#906).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ErploraError } from '@erplora/module-sdk';

import { getClient, setOnRuntimeSessionExpired } from './runtime';
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

/** Network-level stub: routes by URL substring, first match wins. Anything else never answers. */
function stubFetch(routes: Array<[match: string, route: Route]>) {
  const spy = vi.fn().mockImplementation((url: string) => {
    const hit = routes.find(([match]) => String(url).includes(match));
    if (!hit) return new Promise(() => {});
    const [, route] = hit;
    return Promise.resolve({
      ok: route.status >= 200 && route.status < 300,
      status: route.status,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve(route.body ?? {}),
    });
  });
  vi.stubGlobal('fetch', spy);
  return spy;
}

const probeCalls = (spy: ReturnType<typeof vi.fn>) =>
  spy.mock.calls.filter(([url]) => String(url).includes('/api/settings')).length;

/** What `/api/command` answers today for a dead session (`dispatch_api::unauthorized`). */
const DEAD_SESSION = { status: 401, body: { ok: false, error: 'no autenticado: sesión cerrada' } };

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

describe('a module command refused for a dead session (hub#2281)', () => {
  it('rejects with the session code and runs the shell reaction once: session closed, login ahead', async () => {
    const spy = stubFetch([
      ['/api/settings', { status: 401, body: { ok: false, error: 'sesión inválida o caducada' } }],
      ['/api/command', DEAD_SESSION],
    ]);

    const err = await getClient()
      .command('kitchen.station_create', { name: 'Barra' })
      .catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ErploraError);
    expect((err as ErploraError).code).toBe('unauthorized');
    // Not the «we can't tell whether it completed» verdict: a 401 means it never ran.
    expect((err as { outcomeUnknown?: boolean }).outcomeUnknown).toBeUndefined();
    await vi.waitFor(() => expect(expired).toHaveBeenCalledTimes(1));
    expect(getHubSession()).toBeNull();
    expect(user.value).toBeNull();
    expect(probeCalls(spy)).toBe(1);
  });

  it('a 401 that the probe does NOT confirm (a role refusal) leaves the session alone', async () => {
    stubFetch([
      ['/api/settings', { status: 200, body: { ok: true, data: {} } }],
      ['/api/command', DEAD_SESSION],
    ]);

    await getClient()
      .command('kitchen.station_create', { name: 'Barra' })
      .catch(() => undefined);
    // Let the probe settle before asserting nothing happened.
    await new Promise((r) => setTimeout(r, 0));

    expect(expired).not.toHaveBeenCalled();
    expect(getHubSession()).toBe('live-session-token');
  });

  it('a refusal that is not a 401 never probes the session', async () => {
    const spy = stubFetch([
      ['/api/settings', { status: 401, body: { ok: false } }],
      ['/api/command', { status: 403, body: { ok: false, error: { code: 'permission_denied', message: 'x' } } }],
    ]);

    await getClient()
      .command('kitchen.station_create', { name: 'Barra' })
      .catch(() => undefined);
    await new Promise((r) => setTimeout(r, 0));

    expect(probeCalls(spy)).toBe(0);
    expect(expired).not.toHaveBeenCalled();
  });
});
