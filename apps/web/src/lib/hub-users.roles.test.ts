// hub#353 — el cliente de la **activación de roles** (`PUT /api/hub/roles/{key}`, hub#352).
//
// Lo que estos tests protegen es el MOTIVO. El runtime rechaza por dos razones distintas y
// accionables —«es un rol base, siempre está encendido» y «no lo declara ningún módulo
// instalado»— y cada una pide algo distinto del administrador. Si el cliente las aplana a un
// «no se pudo activar», la guarda del servidor se convierte en un no-op mudo: el usuario ve que
// el interruptor no obedece y no sabe por qué. Mismo contrato que `ModuleActionError` (hub#314).
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({}) }));

import { RoleActivationError, assignableRoles, setRoleActivation, type HubRole } from './hub-users';

/** Doble de `fetch` que responde una sola vez con `status` + `body`. */
function respondWith(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** El catálogo ya actualizado que devuelve el endpoint tras escribir. */
const CATALOGUE = [
  { name: 'admin', label: 'Administrator', extends: 'admin', source: { kind: 'core' }, active: true, permissions: 9, members: 1 },
  { name: 'kitchen', label: 'Kitchen', extends: 'employee', source: { kind: 'module', module_id: 'kitchen' }, active: true, permissions: 1, members: 0 },
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('setRoleActivation', () => {
  it('enciende un rol con un PUT a su clave y devuelve el catálogo ya actualizado', async () => {
    const fetchMock = respondWith(200, { ok: true, data: CATALOGUE });

    const roles = await setRoleActivation('kitchen', true);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/hub/roles/kitchen');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(String(init.body))).toEqual({ active: true });
    // La respuesta ES el catálogo nuevo: la pantalla no tiene que volver a pedirlo (ni adivinarlo).
    expect(roles.find((r) => r.name === 'kitchen')?.active).toBe(true);
  });

  it('apagar viaja igual, con `active:false`', async () => {
    const fetchMock = respondWith(200, { ok: true, data: CATALOGUE });

    await setRoleActivation('kitchen', false);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ active: false });
  });

  it('escapa la clave en la URL: un rol es texto libre del manifest, no una ruta', async () => {
    const fetchMock = respondWith(200, { ok: true, data: [] });

    await setRoleActivation('kitchen/head', true);

    expect(fetchMock.mock.calls[0][0]).toBe('/api/hub/roles/kitchen%2Fhead');
  });

  it('un rol BASE rechazado conserva el motivo del runtime, no un error genérico', async () => {
    respondWith(422, {
      ok: false,
      error: {
        // hub#1070/#1185: el catálogo responde `invalid_field` y el MOTIVO viaja como campo
        // (`reason`), que es lo que distingue los dos rechazos sin leer la frase.
        code: 'invalid_field',
        field: 'role_key',
        reason: 'immutable',
        message:
          'role `admin` is a base role of the hub: base roles are always active and cannot be switched off',
      },
    });

    const err = await setRoleActivation('admin', false).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(RoleActivationError);
    const failure = err as RoleActivationError;
    expect(failure.code).toBe('invalid_field');
    expect(failure.message).toContain('base role');
  });

  it('«no lo declara ningún módulo» es un motivo DISTINTO, no el mismo error', async () => {
    respondWith(422, {
      ok: false,
      error: {
        code: 'invalid_field',
        field: 'role_key',
        reason: 'unknown',
        message:
          'role `waiter` is not declared by any installed module: a hub activates the roles of its catalogue, it does not create new ones',
      },
    });

    const err = (await setRoleActivation('waiter', true).catch((e: unknown) => e)) as RoleActivationError;

    // Los dos rechazos comparten código HTTP (422); lo que los distingue —y lo que el admin
    // necesita para saber si instalar un módulo o dejarlo estar— es el CÓDIGO desde hub#1070. El
    // mensaje sigue llegando entero, pero ya no es lo único que los separa: por eso ahora se puede
    // traducir sin que nadie se quede sin poder distinguirlos.
    expect(err.code).toBe('invalid_field');
    expect(err.message).toContain('not declared by any installed module');
  });

  it('un 403 (sesión sin permiso) también llega con su motivo', async () => {
    respondWith(403, { ok: false, error: { code: 'permission_denied', message: 'admin session required' } });

    const err = (await setRoleActivation('kitchen', true).catch((e: unknown) => e)) as RoleActivationError;

    expect(err.code).toBe('permission_denied');
  });

  it('un fallo SIN motivo no se inventa uno: no hay nada que enseñarle al usuario', async () => {
    respondWith(500, {});

    const err = (await setRoleActivation('kitchen', true).catch((e: unknown) => e)) as RoleActivationError;

    expect(err).toBeInstanceOf(RoleActivationError);
    expect(err.code).toBeUndefined();
  });
});

// El otro extremo de la activación: a quién se le puede DAR el rol. El runtime
// (`roles::ensure_assignable`) rechaza asignar un rol declarado que el hub no ha encendido, así
// que ofrecerlo en el desplegable del alta es ofrecer algo que el servidor va a rechazar — y deja
// la pantalla de activación pareciendo que no sirve para nada.
describe('assignableRoles', () => {
  const role = (over: Partial<HubRole>): HubRole => ({
    name: 'x',
    label: 'X',
    extends: 'employee',
    source: { kind: 'module', module_id: 'kds' },
    active: false,
    permissions: 0,
    members: 0,
    ...over,
  });

  it('un rol declarado y APAGADO no se ofrece: el runtime rechazaría asignarlo', () => {
    const roles = [role({ name: 'kitchen', active: false })];

    expect(assignableRoles(roles)).toEqual([]);
  });

  it('el mismo rol, una vez encendido, sí se ofrece', () => {
    const roles = [role({ name: 'kitchen', active: true })];

    expect(assignableRoles(roles).map((r) => r.name)).toEqual(['kitchen']);
  });

  it('un rol BASE se ofrece siempre: es el contrato congelado del core', () => {
    const roles = [role({ name: 'admin', source: { kind: 'core' }, active: true })];

    expect(assignableRoles(roles).map((r) => r.name)).toEqual(['admin']);
  });

  it('un rol HUÉRFANO se sigue ofreciendo: hay hubs que ya lo llevan y hay que poder reasignarlo', () => {
    // `ensure_assignable` solo estrecha lo declarado; lo tecleado a mano antes del catálogo
    // (`cashier`, `waiter`) sigue siendo asignable como siempre. Quitarlo rompería hubs que funcionan.
    const roles = [role({ name: 'waiter', source: { kind: 'in_use' }, active: false })];

    expect(assignableRoles(roles).map((r) => r.name)).toEqual(['waiter']);
  });
});
