// #945: Google login from a Hub PWA must return to the Hub, not the SaaS.
// The Hub has no Google button / callback; the SaaS side (hub-bridge + the
// /api/v1/auth/session-exchange/ endpoint) is complete. This file tests the
// Hub-side client helper that redeems the one-time exchange code the SaaS
// mints in hub_oauth_bridge, producing the same LoginResult shape cloudLogin
// returns so the post-login bootstrap can be reused.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { beginRequest, endRequest } = vi.hoisted(() => ({
  beginRequest: vi.fn(),
  endRequest: vi.fn(),
}));
const { tauriMode } = vi.hoisted(() => ({ tauriMode: { value: false } }));

vi.mock('./shell', () => ({ beginRequest, endRequest }));
vi.mock('./device', () => ({
  isTauri: () => tauriMode.value,
  loginHeaders: vi.fn(async () => ({ 'X-Client-Type': 'hub' })),
}));

import { setTokens } from './cloud';
import { config } from './config';
import { sessionExchange } from './cloud';

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => { values.delete(key); },
    setItem: (key, value) => { values.set(key, String(value)); },
  };
}

const ME = {
  id: 'u-42',
  name: 'Ada Lovelace',
  email: 'ada@erplora.com',
};

function mockOk(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('sessionExchange (Google hub-bridge callback)', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', memoryStorage());
    vi.stubGlobal('fetch', vi.fn());
    beginRequest.mockClear();
    endRequest.mockClear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('POSTs the code to /api/v1/auth/session-exchange/ and returns a LoginResult', async () => {
    const fetchMock = vi.mocked(fetch);
    // First call = session-exchange, second = /me.
    fetchMock
      .mockResolvedValueOnce(
        mockOk({ access: 'access.jwt', refresh: 'refresh.jwt', hub_id: 'hub-1' }),
      )
      .mockResolvedValueOnce(mockOk(ME));

    const result = await sessionExchange('code-abc');

    expect(result.access).toBe('access.jwt');
    expect(result.refresh).toBe('refresh.jwt');
    expect(result.user.id).toBe('u-42');
    expect(result.user.email).toBe('ada@erplora.com');
    expect(result.hubId).toBe('hub-1');

    // The exchange hits the exact endpoint the SaaS exposes.
    const exchangeUrl = String(fetchMock.mock.calls[0][0]);
    expect(exchangeUrl).toBe(`${config.cloudApiUrl}/api/v1/auth/session-exchange/`);
    const exchangeInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(exchangeInit.method).toBe('POST');
    expect(JSON.parse(String(exchangeInit.body))).toEqual({ code: 'code-abc' });
  });

  it('does not persist tokens itself — the caller does (same contract as cloudLogin)', async () => {
    // cloudLogin/sessionExchange return a LoginResult; the LoginPage bootstrap
    // calls setTokens(). The helper must NOT touch storage so callers stay in
    // control of when a session is actually established.
    vi.mocked(fetch)
      .mockResolvedValueOnce(mockOk({ access: 'a', refresh: 'r' }))
      .mockResolvedValueOnce(mockOk(ME));

    const result = await sessionExchange('code-xyz');

    expect(result.access).toBe('a');
    expect(result.refresh).toBe('r');
    expect(localStorage.getItem('erplora.access')).toBeNull();
    expect(localStorage.getItem('erplora.refresh')).toBeNull();

    // …but the caller can persist with setTokens (sanity-check the round trip).
    setTokens(result.access, result.refresh);
    expect(localStorage.getItem('erplora.access')).toBe('a');
    expect(localStorage.getItem('erplora.refresh')).toBe('r');
  });

  it('rejects when the code is invalid (SaaS returns 400)', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'invalid' }), { status: 400 }),
    );
    await expect(sessionExchange('bogus')).rejects.toThrow();
  });

  it('rejects when the code has already been redeemed', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'invalid' }), { status: 400 }),
    );
    await expect(sessionExchange('used')).rejects.toThrow();
  });
});
