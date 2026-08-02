// Personal = core: el cliente REST de `/api/hub/users` + `/api/hub/roles`.
//
// La pantalla de Personal pintaba `staff.members.list` — una query del MÓDULO `staff`, que no está
// instalado en la mayoría de hubs: de ahí «No se pudo cargar el personal». Los usuarios reales del
// hub (incluido el owner/administrador, que entra por Cloud y NO tiene PIN) los sirve el runtime.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({ 'X-Hub-Id': 'hub-1', 'X-Hub-Session': 'sess' }),
}));

import {
  accessOf,
  canDeactivate,
  createHubUser,
  deactivateHubUser,
  listHubRoles,
  listHubUsers,
  updateHubUser,
  type HubUser,
} from './hub-users';

const owner: HubUser = {
  id: 'u-owner',
  name: 'Ioan Beilic',
  email: 'ioan@example.com',
  role: 'owner',
  cloud_user_id: 'cloud-1',
  is_active: true,
  has_pin: false,
  created_at: '2026-07-01T09:00:00Z',
};
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

function mockFetch(body: unknown, ok = true, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok, status, json: async () => body })),
  );
}

describe('hub-users: el personal sale del core', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('lista TODOS los usuarios del hub, incluido el owner sin PIN', async () => {
    mockFetch({ ok: true, data: [owner, cashier] });
    const users = await listHubUsers();
    expect(users.map((u) => u.id)).toEqual(['u-owner', 'u-caja']);
    expect(users[0].has_pin).toBe(false);
    expect(fetch).toHaveBeenCalledWith(
      '/api/hub/users',
      expect.objectContaining({ headers: expect.objectContaining({ 'X-Hub-Session': 'sess' }) }),
    );
  });

  it('propaga el mensaje del runtime cuando el alta se rechaza', async () => {
    mockFetch(
      { ok: false, error: { message: 'el PIN debe tener entre 4 y 8 dígitos' } },
      false,
      422,
    );
    await expect(
      createHubUser({ name: 'Ana', email: '', role: 'employee', pin: '12' }),
    ).rejects.toThrow('el PIN debe tener entre 4 y 8 dígitos');
  });

  it('edita por id con PUT y solo manda los campos tocados', async () => {
    mockFetch({ ok: true, data: { ...cashier, role: 'manager' } });
    const updated = await updateHubUser('u-caja', { role: 'manager' });
    expect(updated.role).toBe('manager');
    const [url, init] = (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock
      .calls[0];
    expect(url).toBe('/api/hub/users/u-caja');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(String(init.body))).toEqual({ role: 'manager' });
  });

  it('la baja es un DELETE que devuelve al usuario desactivado, no borrado', async () => {
    mockFetch({ ok: true, data: { ...cashier, is_active: false } });
    const row = await deactivateHubUser('u-caja');
    expect(row.is_active).toBe(false);
    expect(
      (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0][1].method,
    ).toBe('DELETE');
  });

  // Un usuario puede existir SIN ninguna vía de entrada: es el registro de una persona (p. ej. un
  // profesional que no toca el TPV). Decir «cuenta online» de quien no tiene cuenta es mentir.
  it('distingue las tres vías de acceso, incluida «ninguna»', () => {
    expect(accessOf(cashier)).toBe('pin');
    expect(accessOf(owner)).toBe('cloud');
    expect(accessOf({ ...owner, cloud_user_id: null, has_pin: false })).toBe('none');
    // El PIN manda: es la vía del día a día en el POS.
    expect(accessOf({ ...owner, has_pin: true })).toBe('pin');
  });

  // Espejo en UI del guard del servidor (`crates/server/src/hub_users.rs`): la acción se oculta
  // en vez de dejar que el usuario la pulse y coma un 400. El servidor sigue siendo la autoridad.
  it('no ofrece dar de baja ni a uno mismo ni al último administrador', () => {
    const census = [owner, cashier];
    expect(canDeactivate(census, 'u-owner', 'u-owner')).toBe(false);
    expect(canDeactivate(census, 'u-owner', 'u-caja')).toBe(true);
    // El owner es el único admin: tampoco puede darlo de baja otro admin… que aquí no existe.
    expect(canDeactivate(census, 'u-caja', 'u-owner')).toBe(false);
    // Con un segundo admin activo, sí.
    const withSecondAdmin = [...census, { ...owner, id: 'u-ana', role: 'admin' }];
    expect(canDeactivate(withSecondAdmin, 'u-ana', 'u-owner')).toBe(true);
    // Un admin INACTIVO no sirve de relevo.
    const withInactiveAdmin = [...census, { ...owner, id: 'u-ex', role: 'admin', is_active: false }];
    expect(canDeactivate(withInactiveAdmin, 'u-caja', 'u-owner')).toBe(false);
    // Un id desconocido no ofrece acción.
    expect(canDeactivate(census, 'u-owner', 'fantasma')).toBe(false);
  });

  it('los roles vienen del core con permisos y miembros', async () => {
    mockFetch({
      ok: true,
      data: [
        { name: 'owner', permissions: 12, members: 1 },
        { name: 'employee', permissions: 4, members: 0 },
      ],
    });
    const roles = await listHubRoles();
    expect(roles[0]).toEqual({ name: 'owner', permissions: 12, members: 1 });
    expect(fetch).toHaveBeenCalledWith('/api/hub/roles', expect.anything());
  });
});
