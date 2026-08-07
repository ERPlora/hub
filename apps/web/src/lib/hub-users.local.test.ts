// Alta de usuario LOCAL: nombre + PIN, nada en el SaaS (plan paso 2b, hub#355).
//
// La casilla «Local user» crea a alguien que, en cuanto entra, puede operar la caja. El runtime es
// la autoridad —revalida todo y responde 409 con un código estable—, pero la UI tiene que
// (a) mandar el alta como local, (b) saber DECIR POR QUÉ cuando el runtime la rechaza, y
// (c) adelantar los motivos que puede ver desde aquí, para no pedirle al administrador que pulse
// «Crear» para enterarse de que `admin` no es un rol de un usuario local.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({ 'X-Hub-Id': 'hub-1', 'X-Hub-Session': 'sess' }),
}));

import { createHubUser, hubUserErrorKey, localUserIssue, type HubUser } from './hub-users';

const cashier: HubUser = {
  id: 'u-caja',
  name: 'Marta Ruiz',
  email: '',
  role: 'cashier',
  cloud_user_id: null,
  is_active: true,
  has_pin: true,
  created_at: '2026-07-10T09:00:00Z',
};
/** Dada de baja: la puerta que el hub (o el SaaS) cerró — hub#348. */
const dismissed: HubUser = { ...cashier, id: 'u-ex', name: 'Ana Soto', is_active: false };

function mockFetch(body: unknown, ok = true, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok, status, json: async () => body })),
  );
}

function calls(): [string, RequestInit][] {
  return (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls;
}

describe('alta de usuario local (hub#355)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('manda el alta marcada como local y sin email', async () => {
    mockFetch({ ok: true, data: { ...cashier, id: 'u-luis', name: 'Luis Prat' } });
    await createHubUser({ name: 'Luis Prat', email: '', role: 'employee', pin: '5390', local: true });
    expect(JSON.parse(String(calls()[0][1].body))).toEqual({
      name: 'Luis Prat',
      email: '',
      role: 'employee',
      pin: '5390',
      local: true,
    });
  });

  it('conserva el código estable del rechazo para poder traducirlo', async () => {
    // Sin el código, la UI solo puede repetir la frase inglesa del runtime a un usuario que ve el
    // Hub en español. Con él, el motivo se traduce como cualquier otra cadena visible.
    mockFetch(
      { ok: false, error: { code: 'hub.users.pin_in_use', message: 'another active user…' } },
      false,
      409,
    );
    const failure = await createHubUser({
      name: 'Luis Prat',
      email: '',
      role: 'employee',
      pin: '4821',
      local: true,
    }).catch((error: unknown) => error);

    expect(hubUserErrorKey(failure)).toBe('pin_in_use');
    expect((failure as Error).message).toContain('another active user');
    // Un error que no viene del runtime no inventa clave.
    expect(hubUserErrorKey(new Error('network down'))).toBeUndefined();
  });

  it('adelanta en la UI los motivos que el runtime va a rechazar', () => {
    const census = [cashier, dismissed];
    const ok = { name: 'Luis Prat', role: 'employee', pin: '5390' };
    expect(localUserIssue(ok, census)).toBe('');

    // Sin PIN un usuario local no puede entrar por ningún sitio.
    expect(localUserIssue({ ...ok, pin: '' }, census)).toBe('local_needs_pin');
    // Los dos PIN que se prueban primero: todo el mismo dígito y la cuesta.
    for (const weak of ['0000', '1111', '1234', '4321']) {
      expect(localUserIssue({ ...ok, pin: weak }, census)).toBe('pin_too_simple');
    }
    expect(localUserIssue({ ...ok, pin: '13579' }, census)).toBe('');
    // Administrar el hub sale de una cuenta, nunca de cuatro dígitos.
    for (const role of ['admin', 'owner', 'ADMIN']) {
      expect(localUserIssue({ ...ok, role }, census)).toBe('local_cannot_administer');
    }
    // Una persona = una fila: ni el nombre de alguien activo ni el de alguien dado de baja.
    expect(localUserIssue({ ...ok, name: 'Marta Ruiz' }, census)).toBe('name_taken');
    expect(localUserIssue({ ...ok, name: '  ana soto ' }, census)).toBe('name_taken');
  });
});
