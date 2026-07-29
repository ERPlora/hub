// ADR-0157 §8 — «Continuar con Google» en el Hub. El Hub NUNCA habla con Google: abre el OAuth del
// SaaS y, al volver, canjea un código de un solo uso por tokens (`session-exchange`). Aquí se prueba
// la pieza testable en cloud.ts: construir la URL del OAuth del SaaS y canjear el código.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { beginRequest, endRequest } = vi.hoisted(() => ({
  beginRequest: vi.fn(),
  endRequest: vi.fn(),
}));

vi.mock('./shell', () => ({ beginRequest, endRequest }));
vi.mock('./device', () => ({
  isTauri: () => false,
  loginHeaders: vi.fn(async () => ({ 'X-Client-Type': 'hub' })),
}));

import { exchangeGoogleCode, googleLoginUrl } from './cloud';
import { config } from './config';

const originalCloudApiUrl = config.cloudApiUrl;

describe('login con Google (ADR-0157 §8)', () => {
  beforeEach(() => {
    config.cloudApiUrl = 'https://cloud.test';
    beginRequest.mockClear();
    endRequest.mockClear();
  });

  afterEach(() => {
    config.cloudApiUrl = originalCloudApiUrl;
    vi.unstubAllGlobals();
  });

  it('construye la URL del OAuth del SaaS con next=/auth/hub-bridge/?callback=<hub>', () => {
    // El `next` NO es el callback del hub directo: allauth solo redirige a rutas del PROPIO SaaS
    // (un next cross-host se descarta → caía a /dashboard/) y el código de un solo uso lo emite
    // exclusivamente `/auth/hub-bridge/` (ADR-0157 §8). El callback del hub viaja dentro, doblemente
    // encodeado, y el bridge lo valida contra su allowlist antes de redirigir con `?code=`.
    expect(googleLoginUrl('https://hub.test/auth/google/callback')).toBe(
      'https://cloud.test/auth/google/login/?next=' +
        encodeURIComponent(
          '/auth/hub-bridge/?callback=' + encodeURIComponent('https://hub.test/auth/google/callback'),
        ),
    );
  });

  it('canjea el código de un solo uso por tokens y resuelve el usuario (session-exchange)', async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url === 'https://cloud.test/api/v1/auth/session-exchange/') {
        return new Response(
          JSON.stringify({ access: 'acc-1', refresh: 'ref-1', hub_id: 'hub-9' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url === 'https://cloud.test/api/v1/auth/me/') {
        return new Response(
          JSON.stringify({ id: 7, name: 'Ioan', email: 'ioan@bar.com' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await exchangeGoogleCode('CODE-123');

    // Canjeó el código en session-exchange (con el body {code}).
    const exchangeCall = fetchMock.mock.calls.find(
      ([u]) => u === 'https://cloud.test/api/v1/auth/session-exchange/',
    );
    expect(exchangeCall).toBeTruthy();
    expect(JSON.parse((exchangeCall![1] as RequestInit).body as string)).toEqual({ code: 'CODE-123' });

    // Devuelve LoginResult con la MISMA forma que cloudLogin (tokens + usuario + hubId).
    expect(result.access).toBe('acc-1');
    expect(result.refresh).toBe('ref-1');
    expect(result.hubId).toBe('hub-9');
    expect(result.user).toEqual({
      id: '7',
      name: 'Ioan',
      email: 'ioan@bar.com',
      avatarUrl: null,
    });
  });
});
