// hub#1697 — el cliente de la bandeja de mensajes no entregados no puede tirar el código.
//
// La puerta (`outbox_admin.rs`) contesta `{"ok":false,"error":{"code":"…","message":"…"}}`, y su
// `message` está escrito para quien depura —mezcla español e inglés («this dead-letter cannot be
// replayed: the authorisation that produced it was withdrawn…»)—. `unwrap` se quedaba sólo con el
// mensaje y lo tiraba dentro de la frase de la pantalla, así que el dueño del bar leía eso.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({ runtimeHeaders: () => ({}) }));

import { retryDeadLetter } from './dead-letter';

function refuses(body: unknown, status = 409): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
    ),
  );
}

beforeEach(() => vi.unstubAllGlobals());

describe('el rechazo de una dead-letter conserva su código', () => {
  it('lleva el `code` del sobre junto al mensaje', async () => {
    refuses({
      ok: false,
      error: {
        code: 'flow.release_revoked',
        message: 'this dead-letter cannot be replayed: the authorisation that produced it was withdrawn',
      },
    });

    const error = (await retryDeadLetter('evt_1').then(
      () => null,
      (e: unknown) => e,
    )) as { code?: string; message: string };

    expect(error.code).toBe('flow.release_revoked');
    expect(error.message).toContain('cannot be replayed');
  });

  it('no inventa código cuando el sobre no trae ninguno', async () => {
    refuses({ ok: false, error: { message: 'boom' } });

    const error = (await retryDeadLetter('evt_1').then(
      () => null,
      (e: unknown) => e,
    )) as { code?: string };

    expect(error.code).toBeUndefined();
  });
});
