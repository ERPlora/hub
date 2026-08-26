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

// hub#1101: el runtime rechaza (409 `has_dependents`) desinstalar un módulo del que cuelgan otros,
// y nombra cuáles. La pantalla YA lo avisa antes de preguntar (hub#773), así que el `force` es
// exactamente la respuesta que el dueño acaba de dar — pero solo se manda cuando la ha dado.
describe('desinstalar · el gate de dependientes', () => {
  function fetchSpy(): ReturnType<typeof vi.fn> {
    const spy = vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
    vi.stubGlobal('fetch', spy);
    return spy;
  }

  it('por defecto NO fuerza: quien no ha visto la lista no puede saltarse el gate', async () => {
    const spy = fetchSpy();

    await uninstallModule('taxes');

    const init = spy.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeUndefined();
  });

  it('con la confirmación del dueño manda `force: true` en el cuerpo', async () => {
    const spy = fetchSpy();

    await uninstallModule('taxes', { force: true });

    const init = spy.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ force: true });
    expect((init.headers as Record<string, string>)['Content-Type']).toContain('application/json');
  });

  it('conserva la lista de dependientes que manda el runtime', async () => {
    respondWith(409, {
      ok: false,
      error: {
        code: 'has_dependents',
        message: '`taxes` cannot be uninstalled: 4 installed app(s) need it',
        dependents: ['sales', 'inventory', 'invoice', 'services'],
      },
    });

    const err = (await uninstallModule('taxes').catch((e: unknown) => e)) as ModuleActionError;
    expect(err.code).toBe('has_dependents');
    expect(err.dependents).toEqual(['sales', 'inventory', 'invoice', 'services']);
  });
});
