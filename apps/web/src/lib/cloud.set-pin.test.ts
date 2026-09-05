// hub#1430 — «Mi perfil» → cambiar mi PIN reutiliza `runtimeSetPin` (la misma puerta de
// autoservicio que la alta de PIN tras login cloud), y necesita distinguir POR QUÉ el runtime
// rechazó el cambio (PIN actual que no coincide, PIN ya usado por otra persona…). El runtime
// responde esos casos con `RuntimeError::Domain`/`InvalidField`, que `err_response` empaqueta como
// `{ok:false, error:{code, message}}` — un objeto ANIDADO. `runtimePost` tipaba `error` como un
// string plano y `code` en la raíz (el shape que sí usan `too_many_attempts`/`device_untrusted`),
// así que un rechazo anidado como este perdía su código: `RuntimeError.code` llegaba `undefined` y
// el mensaje se volvía «[object Object]» en vez del texto del runtime.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./shell', () => ({ beginRequest: vi.fn(), endRequest: vi.fn() }));

import { runtimeSetPin } from './cloud';

describe('runtimeSetPin — forma anidada del error del runtime (hub#1430)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('conserva el código estable cuando el runtime rechaza con {error:{code,message}}', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: false,
          error: { code: 'hub.users.pin_current_mismatch', message: 'the current PIN does not match' },
        }),
        { status: 409 },
      ),
    );

    await expect(runtimeSetPin('8246', 'sess-1', '0000')).rejects.toMatchObject({
      code: 'hub.users.pin_current_mismatch',
      message: 'the current PIN does not match',
    });
  });

  it('sigue leyendo la forma plana {error:"...", code:"..."} de las otras puertas de login', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({ ok: false, error: 'demasiados intentos fallidos: espera unos minutos', code: 'too_many_attempts' }),
        { status: 429 },
      ),
    );

    await expect(runtimeSetPin('8246', 'sess-1')).rejects.toMatchObject({
      code: 'too_many_attempts',
      message: 'demasiados intentos fallidos: espera unos minutos',
    });
  });

  it('manda `current_pin` solo cuando se pasa (la alta tras login cloud no tiene nada que confirmar)', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    await runtimeSetPin('8246', 'sess-1');

    const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string);
    expect(body).toEqual({ pin: '8246' });
  });

  it('manda `current_pin` cuando se pasa (rotar un PIN que ya existe, hub#1430)', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    await runtimeSetPin('8246', 'sess-1', '1379');

    const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string);
    expect(body).toEqual({ pin: '8246', current_pin: '1379' });
  });
});
