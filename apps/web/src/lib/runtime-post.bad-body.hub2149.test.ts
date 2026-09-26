// @vitest-environment happy-dom
//
// hub#2149 — a runtime door that answers 2xx without a JSON object is a broken response, not a
// success.
//
// `runtimePost` used to swallow the parse failure into `{}` and, with no `ok: false` in it, hand
// that `{}` back typed as the door's result. The courier then stored the literal string
// "undefined" as both tokens, wiped the local session and only blew up afterwards with a bare
// `TypeError` on `result.user.id`. These tests drive the REAL `runtimePost` through two of its
// doors (the courier and the PIN login) against a runtime that answers 200 with no usable body.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./device', () => ({
  getDeviceContext: vi.fn(async () => ({ id: 'device-1', clientType: 'hub-desktop' })),
  resolveDeviceId: vi.fn(async () => 'device-1'),
}));

import { RuntimeError, runtimePinLogin } from './cloud';
import { bootCourier, settleCourierBoot } from './courier';

const BROKEN_2XX_BODIES: Array<[string, () => Response]> = [
  ['an empty body', () => new Response('', { status: 200 })],
  ['an HTML page', () => new Response('<html><body>proxy</body></html>', { status: 200 })],
  ['a JSON null', () => new Response('null', { status: 200 })],
];

function runtimeAnswering(make: () => Response): void {
  vi.stubGlobal('fetch', vi.fn(async () => make()));
}

describe('runtimePost with a 2xx that carries no JSON object (hub#2149)', () => {
  beforeEach(() => {
    settleCourierBoot();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe.each(BROKEN_2XX_BODIES)('courier exchange answered with %s', (_label, make) => {
    it('rejects with an actionable RuntimeError and stores nothing on the device', async () => {
      runtimeAnswering(make);

      const outcome = await bootCourier('opaque-code').then(
        () => undefined,
        (error: unknown) => error,
      );

      expect(outcome).toBeInstanceOf(RuntimeError);
      expect((outcome as RuntimeError).code).toBe('runtime_bad_response');
      expect(localStorage.length).toBe(0);
    });
  });

  describe.each(BROKEN_2XX_BODIES)('PIN login answered with %s', (_label, make) => {
    it('rejects with runtime_bad_response instead of resolving to an empty session', async () => {
      runtimeAnswering(make);

      await expect(runtimePinLogin('Ana', '482913')).rejects.toMatchObject({
        name: 'RuntimeError',
        code: 'runtime_bad_response',
      });
    });
  });

  it('still reads a well-formed 2xx JSON answer as the door result', async () => {
    runtimeAnswering(
      () => new Response(JSON.stringify({ token: 'local-session', user: { id: 'u1' } }), { status: 200 }),
    );

    await expect(runtimePinLogin('Ana', '482913')).resolves.toMatchObject({ token: 'local-session' });
  });

  it('keeps the status-based error for a non-2xx answer without JSON', async () => {
    runtimeAnswering(() => new Response('', { status: 502 }));

    const outcome = await runtimePinLogin('Ana', '482913').then(
      () => undefined,
      (error: unknown) => error,
    );

    expect(outcome).toBeInstanceOf(RuntimeError);
    expect((outcome as RuntimeError).code).toBeUndefined();
  });
});
