// ERPlora/saas#994 — login 2-pasos (2FA por OTP de email). El SaaS cambió
// `POST /api/v1/auth/login/` para responder `401 {two_factor_required, ticket, method,
// expires_in}`; el cliente completa con `POST /api/v1/auth/login/2fa/ {ticket, code}`. Un código
// erróneo devuelve 401 con un ticket NUEVO (single-use). Aquí se prueba la pieza testable de
// cloud.ts: detección del challenge, canje del código y reintento con el ticket renovado.
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

import { cloudLogin, cloudLogin2fa, TwoFactorRequiredError } from './cloud';
import { config } from './config';

const originalCloudApiUrl = config.cloudApiUrl;
const LOGIN = 'https://cloud.test/api/v1/auth/login/';
const TWOFA = 'https://cloud.test/api/v1/auth/login/2fa/';
const ME = 'https://cloud.test/api/v1/auth/me/';

const ME_USER = { id: 7, name: 'Ioan', email: 'ioan@bar.com' };

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** fetch mock que responde por URL. Devuelve la Response sin lanzar (para poder devolver 401). */
function fetchByRoute(routes: Record<string, (body: unknown) => Response>): ReturnType<typeof vi.fn> {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    const handler = routes[String(url)];
    if (!handler) throw new Error(`unexpected fetch: ${url}`);
    return handler(body);
  });
}

describe('login 2-pasos (2FA por email, ERPlora/saas#994)', () => {
  beforeEach(() => {
    config.cloudApiUrl = 'https://cloud.test';
    beginRequest.mockClear();
    endRequest.mockClear();
  });
  afterEach(() => {
    config.cloudApiUrl = originalCloudApiUrl;
    vi.unstubAllGlobals();
  });

  it('cloudLogin detecta el 401 two_factor_required y lanza TwoFactorRequiredError con el ticket', async () => {
    const fetchMock = fetchByRoute({
      [LOGIN]: () =>
        json(
          { two_factor_required: true, ticket: 'ticket-abc', method: 'email', expires_in: 300 },
          401,
        ),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(cloudLogin('ioan@bar.com', 'secret')).rejects.toBeInstanceOf(
      TwoFactorRequiredError,
    );

    const err = await cloudLogin('ioan@bar.com', 'secret').catch((e) => e);
    expect(err).toBeInstanceOf(TwoFactorRequiredError);
    expect(err.ticket).toBe('ticket-abc');
    expect(err.method).toBe('email');
    expect(err.expiresIn).toBe(300);

    // El login PEGA al endpoint correcto con {email, password} (paso 1).
    const loginCall = fetchMock.mock.calls.find(([u]) => u === LOGIN);
    expect(loginCall).toBeTruthy();
    expect(JSON.parse(String((loginCall![1] as RequestInit).body))).toEqual({
      email: 'ioan@bar.com',
      password: 'secret',
    });
    // No llega a pedir /me: el challenge aborta antes.
    expect(fetchMock.mock.calls.some(([u]) => u === ME)).toBe(false);
  });

  it('cloudLogin propaga un 401 sin 2FA como Error normal (no challenge)', async () => {
    vi.stubGlobal(
      'fetch',
      fetchByRoute({
        [LOGIN]: () => json({ detail: 'Invalid credentials.' }, 401),
      }),
    );

    await expect(cloudLogin('ioan@bar.com', 'wrong')).rejects.toThrow(
      'cloud /api/v1/auth/login/ → 401',
    );
  });

  it('cloudLogin2fa canjea {ticket, code} en /2fa/ y devuelve un LoginResult', async () => {
    const fetchMock = fetchByRoute({
      [TWOFA]: (body) => {
        expect(body).toEqual({ ticket: 'ticket-abc', code: '123456' });
        return json({ access: 'acc-1', refresh: 'ref-1', hub_id: 'hub-9' }, 200);
      },
      [ME]: () => json(ME_USER, 200),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await cloudLogin2fa('ticket-abc', '123456');

    expect(result.access).toBe('acc-1');
    expect(result.refresh).toBe('ref-1');
    expect(result.hubId).toBe('hub-9');
    expect(result.user).toEqual({
      id: '7',
      name: 'Ioan',
      email: 'ioan@bar.com',
      avatarUrl: null,
    });
    // El body del POST al /2fa/ lleva exactamente {ticket, code}.
    const twoFaCall = fetchMock.mock.calls.find(([u]) => u === TWOFA);
    expect(JSON.parse(String((twoFaCall![1] as RequestInit).body))).toEqual({
      ticket: 'ticket-abc',
      code: '123456',
    });
  });

  it('un código erróneo responde 401 con un ticket NUEVO → cloudLogin2fa lo expone para reintentar', async () => {
    const fetchMock = fetchByRoute({
      [TWOFA]: () =>
        json(
          { two_factor_required: true, ticket: 'ticket-NEW', method: 'email', expires_in: 300 },
          401,
        ),
    });
    vi.stubGlobal('fetch', fetchMock);

    // El ticket viejo ('ticket-old') YA está consumido; el Cloud devuelve 'ticket-NEW'.
    await expect(cloudLogin2fa('ticket-old', '000000')).rejects.toBeInstanceOf(
      TwoFactorRequiredError,
    );

    const err = await cloudLogin2fa('ticket-old', '000000').catch((e) => e);
    expect(err).toBeInstanceOf(TwoFactorRequiredError);
    expect(err.ticket).toBe('ticket-NEW');
    // El reintento DEBE usar el ticket nuevo, no el viejo: el body enviado lleva el ticket
    // que el llamador pasa, y tras un error el llamador adopta err.ticket.
    expect(err.ticket).not.toBe('ticket-old');
  });

  it('flujo completo: login → challenge → reintento con el ticket renovado → LoginResult', async () => {
    // 1) cloudLogin devuelve challenge con 't1'.
    // 2) primer cloudLogin2fa (código erróneo) → 401 con 't2' (ticket renovado).
    // 3) segundo cloudLogin2fa con 't2' y el código bueno → tokens + /me.
    const loginCalls: { body: unknown; status: number }[] = [];
    const twoFaHandler = vi.fn((body: { ticket: string; code: string }): Response => {
      loginCalls.push({ body, status: 0 });
      if (body.ticket === 't2' && body.code === '654321') {
        return json({ access: 'acc', refresh: 'ref', hub_id: 'hub-1' }, 200);
      }
      // Cualquier otro intento → 401 con ticket renovado 't2'.
      return json({ two_factor_required: true, ticket: 't2', method: 'email', expires_in: 300 }, 401);
    });

    vi.stubGlobal(
      'fetch',
      fetchByRoute({
        [LOGIN]: () => json({ two_factor_required: true, ticket: 't1', method: 'email', expires_in: 300 }, 401),
        [TWOFA]: (body) => twoFaHandler(body as { ticket: string; code: string }),
        [ME]: () => json(ME_USER, 200),
      }),
    );

    // Paso 1: el login exige 2FA y entrega 't1'.
    const e1 = await cloudLogin('ioan@bar.com', 'secret').catch((x) => x);
    expect(e1).toBeInstanceOf(TwoFactorRequiredError);
    let ticket = e1.ticket;

    // Paso 2: código erróneo → el Cloud renueva el ticket a 't2'. El cliente lo adopta.
    const e2 = await cloudLogin2fa(ticket, '000000').catch((x) => x);
    expect(e2).toBeInstanceOf(TwoFactorRequiredError);
    ticket = e2.ticket; // adopta el NUEVO ticket
    expect(ticket).toBe('t2');

    // Paso 3: reintento con el ticket nuevo y el código correcto → login completo.
    const result = await cloudLogin2fa(ticket, '654321');
    expect(result.access).toBe('acc');
    expect(result.user.id).toBe('7');

    // El cuerpo del último POST al /2fa/ lleva el ticket renovado (no el original 't1').
    const lastTwoFa = loginCalls[loginCalls.length - 1];
    expect(lastTwoFa.body).toEqual({ ticket: 't2', code: '654321' });
  });
});
