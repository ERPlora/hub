// hub#1172 — `GET /api/modules/updates` feeds the bell's «N apps have a new version», which keeps its
// last count when a check fails («I don't know» is not «all up to date»). That only works if a runtime
// that answered with an ERROR is told apart from one that answered «nothing to update»: resolving
// both to `[]` would wipe the notice every time the runtime hiccups.
//
// Driven through the REAL `listModuleUpdates` with `fetch` stubbed at the network level (lesson of
// hub#770), so only branches the production code actually has can pass.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { listModuleUpdates } from './runtime';
import { setHubSession, setUser } from './session';

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (i: number) => [...values.keys()][i] ?? null,
    removeItem: (key: string) => void values.delete(key),
    setItem: (key: string, value: string) => void values.set(key, String(value)),
  };
}

function answer(status: number, body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    }),
  );
}

const SALES = {
  module_id: 'sales',
  installed: '1.0.0',
  latest: '2.0.0',
  update_available: true,
  pinned: null,
  latest_min_erplora_version: null,
};

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
  setHubSession('live-session-token');
  setUser({ id: 'u1', name: 'Owner', email: 'owner@shop.test', role: 'admin' });
});

afterEach(() => {
  setUser(null);
  vi.unstubAllGlobals();
});

describe('listModuleUpdates tells «the runtime failed» from «nothing to update» (hub#1172)', () => {
  it('returns what the runtime answered', async () => {
    answer(200, { ok: true, data: [SALES] });
    await expect(listModuleUpdates()).resolves.toEqual([SALES]);
  });

  it('an answer with nothing to update is an empty list', async () => {
    answer(200, { ok: true, data: [] });
    await expect(listModuleUpdates()).resolves.toEqual([]);
  });

  it('🔴 a server error rejects instead of pretending every app is up to date', async () => {
    answer(500, { ok: false, error: 'db down' });
    await expect(listModuleUpdates()).rejects.toThrow();
  });

  it('🔴 an envelope that says ok:false rejects too', async () => {
    answer(200, { ok: false, error: 'boom' });
    await expect(listModuleUpdates()).rejects.toThrow();
  });

  it('🔴 a body that cannot be read rejects', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.reject(new SyntaxError('not json')),
        text: () => Promise.resolve('<html>'),
      }),
    );
    await expect(listModuleUpdates()).rejects.toThrow();
  });
});
