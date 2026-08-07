// hub#314 (ADR-0202 R2): el runtime RECHAZA desactivar/desinstalar un módulo que aún debe
// registros a la AEAT, con un código de dominio estable (`verifactu.unsent_records`) y un mensaje
// que dice cuántos quedan. Ese rechazo tiene que llegar entero al que pulsó el botón: si el
// cliente lo aplana a «no se pudo», la guarda vuelve a ser un no-op mudo.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ModuleActionError, deactivateModule, uninstallModule } from './runtime';

function respondWith(status: number, body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('acciones de módulo · el motivo del rechazo', () => {
  it('conserva el código de dominio y el mensaje cuando el runtime rechaza (409)', async () => {
    respondWith(409, {
      ok: false,
      error: {
        code: 'verifactu.unsent_records',
        message: '3 VeriFactu record(s) have not reached the AEAT yet',
      },
    });

    const err = await uninstallModule('verifactu').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ModuleActionError);
    const failure = err as ModuleActionError;
    expect(failure.code).toBe('verifactu.unsent_records');
    expect(failure.message).toContain('3');
  });

  it('también lo conserva al desactivar: la otra puerta al mismo agujero', async () => {
    respondWith(409, {
      ok: false,
      error: { code: 'verifactu.unsent_records', message: '1 record still unsent' },
    });

    const err = (await deactivateModule('verifactu').catch((e: unknown) => e)) as ModuleActionError;
    expect(err.code).toBe('verifactu.unsent_records');
  });

  it('un fallo SIN código no inventa un motivo: no hay nada que enseñarle al usuario', async () => {
    respondWith(500, {});

    const err = (await uninstallModule('taxes').catch((e: unknown) => e)) as ModuleActionError;
    expect(err).toBeInstanceOf(ModuleActionError);
    expect(err.code).toBeUndefined();
  });
});
