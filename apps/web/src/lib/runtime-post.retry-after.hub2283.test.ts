// @vitest-environment happy-dom
//
// hub#2283 — the brute-force lock of the login doors answers `429 {code: "too_many_attempts",
// retry_after_secs}`. `runtimePost` kept the code and dropped the wait, so no screen could tell the
// person how long to wait. These tests drive the REAL `runtimePost` through the PIN door.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./device', () => ({
  getDeviceContext: vi.fn(async () => ({ id: 'device-1', clientType: 'hub-desktop' })),
  resolveDeviceId: vi.fn(async () => 'device-1'),
}));

import { RuntimeError, runtimePinLogin } from './cloud';

function runtimeAnswering(status: number, body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

async function refusalOf(): Promise<RuntimeError> {
  const outcome = await runtimePinLogin('Ana', '482913').then(
    () => undefined,
    (error: unknown) => error,
  );
  expect(outcome).toBeInstanceOf(RuntimeError);
  return outcome as RuntimeError;
}

describe('a locked login door (hub#2283)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps the wait the runtime names next to the code', async () => {
    runtimeAnswering(429, {
      ok: false,
      error: 'demasiados intentos fallidos: espera unos minutos',
      code: 'too_many_attempts',
      retry_after_secs: 240,
    });

    const err = await refusalOf();

    expect(err.code).toBe('too_many_attempts');
    expect(err.retryAfterSecs).toBe(240);
  });

  it.each<[string, unknown]>([
    ['missing', undefined],
    ['a string', '240'],
    ['negative', -5],
    ['not finite', null],
  ])('leaves the wait unknown when it is %s', async (_label, value) => {
    runtimeAnswering(429, { ok: false, code: 'too_many_attempts', retry_after_secs: value });

    const err = await refusalOf();

    expect(err.code).toBe('too_many_attempts');
    expect(err.retryAfterSecs).toBeUndefined();
  });

  it('carries no wait on an ordinary refusal', async () => {
    runtimeAnswering(401, { ok: false, error: 'PIN incorrecto' });

    const err = await refusalOf();

    expect(err.retryAfterSecs).toBeUndefined();
  });
});
