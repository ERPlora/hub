// pm#196 / hub#1400 — `runtimeBrowserHandoff`, the call that trades the till session for the
// one-time address, and what it does when the user's JWT has gone STALE.
//
// The access token the SaaS mints lives ONE HOUR (`SIMPLE_JWT.ACCESS_TOKEN_LIFETIME`); the till
// session lives the whole day. The runtime verifies `exp` before it names the person, so from the
// second hour on it answers `handoff_user_token_invalid` — and `saasDoor` would degrade to the plain
// link, which lands on the login form: the very symptom the issue describes, only delayed until
// after lunch. Every other call in this file that carries the Bearer already refreshes ONCE on a 401
// and retries (`cloudFetch`, `runtimeGet`); this door has to do the same, or it works for an hour.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./shell', () => ({ beginRequest: vi.fn(), endRequest: vi.fn() }));
vi.mock('./config', () => ({
  config: { cloudApiUrl: 'https://erplora.com', hubId: 'hub-1' },
  cloudApiUrlReady: async () => {},
  isLocalHub: () => false,
}));
// The real `runtimeHeaders` reads the Bearer from the same store `setTokens` writes to; the mock
// mirrors exactly that, so a refreshed token is what the SECOND ask carries.
vi.mock('./runtime', () => ({
  runtimeHeaders: () => {
    const headers: Record<string, string> = { 'X-Hub-Session': 'sess-1', 'X-Hub-Id': 'hub-1' };
    const token = localStorage.getItem('erplora.access');
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  },
}));

import { runtimeBrowserHandoff, setTokens } from './cloud';

const ONE_TIME = 'https://erplora.com/auth/handoff/code-abc/?next=%2Fdashboard%2F';

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

type Call = { url: string; headers: Record<string, string>; body: unknown };
const calls: Call[] = [];

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status });
}

/** A runtime that refuses the STALE token and mints for any other, and a SaaS that rotates. */
function wire(options: { refreshAnswers?: Response } = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, headers, body });
      if (url.endsWith('/api/auth/handoff')) {
        if (headers.Authorization === 'Bearer stale-access') {
          return json({ ok: false, code: 'handoff_user_token_invalid' }, 401);
        }
        return json({ ok: true, url: ONE_TIME }, 200);
      }
      if (url.endsWith('/api/v1/auth/refresh/')) {
        return options.refreshAnswers ?? json({ access: 'fresh-access', refresh: 'refresh-2' }, 200);
      }
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
}

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal('localStorage', memoryStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('runtimeBrowserHandoff', () => {
  it('returns the one-time address the runtime mints for a live token', async () => {
    wire();
    setTokens('live-access', 'refresh-1');

    expect(await runtimeBrowserHandoff('/dashboard/')).toBe(ONE_TIME);

    expect(calls).toHaveLength(1);
    expect(calls[0].headers.Authorization).toBe('Bearer live-access');
    expect(calls[0].headers['X-Hub-Session']).toBe('sess-1');
    expect(calls[0].body).toEqual({ next: '/dashboard/' });
  });

  it('refreshes the user JWT once when the runtime says it is stale, and asks again with the fresh one', async () => {
    // The owner signed in at nine and presses «erplora.com» after lunch: the access token died at
    // ten. Without this, the door degrades to the plain link and she meets the login form — the
    // bug, four hours late.
    wire();
    setTokens('stale-access', 'refresh-1');

    expect(await runtimeBrowserHandoff('/dashboard/')).toBe(ONE_TIME);

    expect(calls.map((c) => c.url.replace(/^.*?(\/api\/)/, '/api/'))).toEqual([
      '/api/auth/handoff',
      '/api/v1/auth/refresh/',
      '/api/auth/handoff',
    ]);
    expect(calls[1].body).toEqual({ refresh: 'refresh-1' });
    expect(calls[2].headers.Authorization).toBe('Bearer fresh-access');
    expect(localStorage.getItem('erplora.refresh')).toBe('refresh-2');
  });

  it('does not refresh for a refusal that is not about the token', async () => {
    // A PIN session is refused on purpose (hub#1400); rotating the JWT would not change that, and
    // a refresh storm on every refusal is not what the lock is for.
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, headers: (init?.headers ?? {}) as Record<string, string>, body: undefined });
        return json({ ok: false, code: 'handoff_requires_cloud_login' }, 403);
      }),
    );
    setTokens('live-access', 'refresh-1');

    await expect(runtimeBrowserHandoff('/dashboard/')).rejects.toMatchObject({
      code: 'handoff_requires_cloud_login',
    });
    expect(calls).toHaveLength(1);
  });

  it("gives up with the runtime's own answer when the refresh fails, and does not ask twice", async () => {
    wire({ refreshAnswers: json({ detail: 'refresh expired' }, 401) });
    setTokens('stale-access', 'refresh-1');

    await expect(runtimeBrowserHandoff('/dashboard/')).rejects.toMatchObject({
      code: 'handoff_user_token_invalid',
    });
    expect(calls.map((c) => c.url.replace(/^.*?(\/api\/)/, '/api/'))).toEqual([
      '/api/auth/handoff',
      '/api/v1/auth/refresh/',
    ]);
  });
});
