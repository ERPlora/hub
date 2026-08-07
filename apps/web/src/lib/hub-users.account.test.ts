// Alta de usuario de CUENTA: email + invitación vía SaaS (plan paso 2b, hub#356).
//
// La otra mitad del alta de hub#355. Aquí la identidad vive en el SaaS, así que el alta **crea una
// cuenta y una membresía**: el runtime revalida todo y responde 409/403 con un código estable, pero
// la UI tiene que (a) mandar el email —que sin la casilla es obligatorio—, (b) saber DECIR POR QUÉ
// cuando el runtime rechaza, y (c) adelantar lo que puede ver, para no pedirle al administrador que
// pulse «Crear» y espere a la red para enterarse de que `kitchen` no es un rol que el SaaS conceda.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({ 'X-Hub-Id': 'hub-1', 'X-Hub-Session': 'sess' }),
}));

import { accountUserIssue, createHubUser, hubUserErrorKey, type HubUser } from './hub-users';

const manager: HubUser = {
  id: 'u-ana',
  name: 'Ana Soto',
  email: 'ana@example.com',
  role: 'manager',
  cloud_user_id: null,
  is_active: true,
  has_pin: false,
  created_at: '2026-07-10T09:00:00Z',
};
/** Dado de baja: la puerta que el hub (o el SaaS) cerró — hub#348. */
const revoked: HubUser = { ...manager, id: 'u-ex', name: 'Luis Prat', email: 'luis@example.com', is_active: false };

function mockFetch(body: unknown, ok = true, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok, status, json: async () => body })),
  );
}

function calls(): [string, RequestInit][] {
  return (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls;
}

describe('alta de usuario de cuenta (hub#356)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('manda el alta con email y sin marcar local', async () => {
    mockFetch({ ok: true, data: { ...manager, id: 'u-new', name: 'Marta Ruiz' } });
    await createHubUser({
      name: 'Marta Ruiz',
      email: 'marta@example.com',
      role: 'employee',
      pin: '',
      local: false,
    });
    expect(JSON.parse(String(calls()[0][1].body))).toEqual({
      name: 'Marta Ruiz',
      email: 'marta@example.com',
      role: 'employee',
      pin: '',
      local: false,
    });
  });

  it('conserva el código del rechazo, venga en 409 o en 403', async () => {
    // `role_above_inviter` llega con 403 (es «tú no», no «esto no cabe»); el resto con 409. Los dos
    // son el mismo envelope y el shell los traduce igual — si la UI solo mirase el 409, el rechazo
    // más delicado sería el único que se enseñaría en inglés.
    mockFetch(
      {
        ok: false,
        error: { code: 'hub.users.role_above_inviter', message: 'only somebody who administers…' },
      },
      false,
      403,
    );
    const failure = await createHubUser({
      name: 'Marta Ruiz',
      email: 'marta@example.com',
      role: 'admin',
      pin: '',
    }).catch((error: unknown) => error);

    expect(hubUserErrorKey(failure)).toBe('role_above_inviter');
  });

  it('adelanta en la UI los motivos que el runtime va a rechazar', () => {
    const census = [manager, revoked];
    const ok = { name: 'Marta Ruiz', email: 'marta@example.com', role: 'employee', pin: '' };
    expect(accountUserIssue(ok, census)).toBe('');

    // Sin la casilla, el email ES la identidad: es por lo que el SaaS invita y por lo que el
    // primer login encuentra esta fila.
    expect(accountUserIssue({ ...ok, email: '  ' }, census)).toBe('account_needs_email');

    // Solo los tres roles que el SaaS sabe poner en una membresía. Los que declara un módulo son
    // del personal local, y `owner` no lo concede una invitación (ADR-0157).
    for (const role of ['kitchen', 'cashier', 'owner']) {
      expect(accountUserIssue({ ...ok, role }, census)).toBe('account_role_not_grantable');
    }
    for (const role of ['employee', 'manager', 'admin', 'Manager']) {
      expect(accountUserIssue({ ...ok, role }, census)).toBe('');
    }

    // Una persona = una fila, también por email: ni el de alguien activo ni el de alguien a quien
    // se le cerró la puerta — invitarlo otra vez sería resucitar una membresía revocada (hub#348).
    expect(accountUserIssue({ ...ok, email: 'ANA@example.com' }, census)).toBe('email_taken');
    expect(accountUserIssue({ ...ok, email: ' luis@example.com ' }, census)).toBe('email_taken');

    // El PIN es OPCIONAL aquí, pero si se teclea es la misma credencial que la del usuario local.
    expect(accountUserIssue({ ...ok, pin: '5390' }, census)).toBe('');
    expect(accountUserIssue({ ...ok, pin: '1234' }, census)).toBe('pin_too_simple');
    expect(accountUserIssue({ ...ok, pin: '12' }, census)).toBe('pin_length');
  });
});
