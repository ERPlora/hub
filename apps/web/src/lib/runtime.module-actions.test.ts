// hub#314 (ADR-0202 R2): el runtime RECHAZA desactivar/desinstalar un módulo que aún debe
// registros a la AEAT, con un código de dominio estable (`verifactu.unsent_records`) y un mensaje
// que dice cuántos quedan. Ese rechazo tiene que llegar entero al que pulsó el botón: si el
// cliente lo aplana a «no se pudo», la guarda vuelve a ser un no-op mudo.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ModuleActionError,
  activateModule,
  activeModuleIds,
  deactivateModule,
  publishActiveModuleIds,
  refreshActiveModuleIds,
  uninstallModule,
} from './runtime';
import { setHubSession } from './session';

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

// hub#1211 — `queryOptional`/`queryAllOptional` (module-sdk) short-circuit an ABSENT module by
// reading `activeModuleIds()` instead of asking the transport. A toggle that did not keep that set
// current would just move the 404 from "every call" to "every call until the next unrelated
// refresh" — still a defect, just a slower one.
describe('activeModuleIds · refreshed on every module action (hub#1211)', () => {
  /** The suite runs in `node` (vite.config.ts): the session store needs a `localStorage` to live in. */
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

  beforeEach(() => {
    // Every refresh below happens on a signed-in shell — toggling a module needs a session anyway.
    vi.stubGlobal('localStorage', memoryStorage());
    setHubSession('sess-live');
  });

  afterEach(() => {
    publishActiveModuleIds(undefined);
  });

  it('does not ask the runtime BEFORE there is a session: a 401 is not free (hub#1211)', async () => {
    // `getClient()` is built in `main.ts` on a cold boot, BEFORE anyone signs in. Seeding there
    // without this guard is a guaranteed `GET /api/modules → 401` on every login screen — console
    // noise of exactly the kind this fix removes — and it feeds the central dead-session probe
    // (hub#846). Same rule as `ensureMediaCookie`: nothing is asked until there is a session.
    setHubSession(null);
    const spy = vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({ ok: true, data: [] }) });
    vi.stubGlobal('fetch', spy);

    await refreshActiveModuleIds();

    expect(spy).not.toHaveBeenCalled();
    expect(activeModuleIds()).toBeUndefined();
  });

  /** Answers `/api/modules` (GET) and the action endpoint (POST) differently, by URL shape. */
  function scriptedFetch(modulesBody: unknown, actionBody: unknown = { ok: true }): ReturnType<typeof vi.fn> {
    const spy = vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(url.includes('/api/modules?') ? modulesBody : actionBody),
      }),
    );
    vi.stubGlobal('fetch', spy);
    return spy;
  }

  it('activateModule republishes the ACTIVE set after success', async () => {
    scriptedFetch({
      ok: true,
      data: [{ id: 'cash_register', name: 'Caja', status: 'active', version: '1.0.0' }],
    });

    await activateModule('cash_register');

    expect(activeModuleIds()).toEqual(new Set(['cash_register']));
  });

  it('leaves INACTIVE modules out: what short-circuits is "active", not "installed"', async () => {
    scriptedFetch({
      ok: true,
      data: [
        { id: 'cash_register', name: 'Caja', status: 'inactive', version: '1.0.0' },
        { id: 'sales', name: 'Ventas', status: 'active', version: '1.0.0' },
      ],
    });

    await deactivateModule('cash_register');

    expect(activeModuleIds()).toEqual(new Set(['sales']));
  });

  it('a failed refresh KEEPS the previous answer, never empties it', async () => {
    publishActiveModuleIds(new Set(['sales']));
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));

    await refreshActiveModuleIds();

    expect(activeModuleIds()).toEqual(new Set(['sales']));
  });

  it('with no refresh yet, the answer is "not known" (undefined), never an invented []', () => {
    expect(activeModuleIds()).toBeUndefined();
  });
});
