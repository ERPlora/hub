import { afterEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { RoleDetail } from '../operations/people';
import RolePage from './RolePage.vue';

function employee(fields: Partial<RoleDetail> = {}): RoleDetail {
  return {
    key: 'hub_employee',
    label: 'Empleado',
    origin: 'basic',
    members: 2,
    apps: [
      {
        app: 'base',
        name: 'El negocio',
        permissions: [{ permission: 'base.view_home', phrase: 'Ver el Inicio y sus paneles', state: 'yes' }],
      },
      {
        app: 'sale',
        name: 'Ventas / TPV',
        permissions: [
          { permission: 'sale.take_payment', phrase: 'Cobrar', state: 'yes' },
          { permission: 'sale.void_sale', phrase: 'Anular una venta', state: 'approval' },
          { permission: 'sale.view_all_sales', phrase: 'Ver las ventas de todos', state: 'no' },
        ],
      },
      {
        app: 'sensitive',
        name: 'Datos sensibles',
        permissions: [{ permission: 'base.view_costs', phrase: 'Ver costes', state: 'no' }],
      },
    ],
    ...fields,
  };
}

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(RolePage, { path: '/employees/roles/hub_employee', routes: ['/employees', '/employees/roles/:role'], ...options });
  const call = await m.live();
  return { ...m, call };
}

function line(m: Awaited<ReturnType<typeof open>>, permission: string) {
  return m.wrapper.get(`[data-testid="role-permission-${permission}"]`);
}

afterEach(() => {
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

describe('RolePage', () => {
  it('follows the role of the address live', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.role.detail').map((sub) => sub.params)).toEqual([{ role: 'hub_employee' }]);
  });

  it('says what it is loading until the role arrives', async () => {
    const m = await open({ locale: 'es' });
    expect(m.wrapper.get('[data-testid="role-loading"]').text()).toContain('Cargando lo que permite este rol…');
  });

  it('app by app, each phrase with what the role does with it, in the business’s language', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.role.detail', employee());

    expect(m.wrapper.findAll('[data-testid^="role-app-"]').map((app) => app.find('h2').text())).toEqual([
      'El negocio',
      'Ventas / TPV',
      'Datos sensibles',
    ]);
    expect(line(m, 'sale.void_sale').text()).toContain('Anular una venta');
    expect(line(m, 'sale.void_sale').text()).toContain('Con aprobación');
    expect(line(m, 'sale.take_payment').text()).toContain('Sí');
    expect(line(m, 'sale.view_all_sales').text()).toContain('No');
    expect(m.wrapper.text()).toContain('Lo que este rol deja hacer en este negocio, app por app.');
    expect(m.wrapper.get('[data-testid="role-members"]').text()).toBe('Personas con este rol: 2');
  });

  it('in English too', async () => {
    const m = await open();
    await m.result(m.call, 'base.role.detail', employee());
    expect(line(m, 'sale.void_sale').text()).toContain('With approval');
    expect(line(m, 'sale.take_payment').text()).toContain('Yes');
    expect(m.wrapper.get('[data-testid="role-members"]').text()).toBe('People with this role: 2');
  });

  it('each state has its own tone', async () => {
    const m = await open();
    await m.result(m.call, 'base.role.detail', employee());
    const tone = (permission: string) => line(m, permission).find('[data-testid="role-state"]').attributes('data-tone');
    expect([tone('sale.take_payment'), tone('sale.void_sale'), tone('sale.view_all_sales')]).toEqual(['success', 'warning', 'neutral']);
  });

  it('is read only: nothing to switch, save or change', async () => {
    const m = await open();
    await m.result(m.call, 'base.role.detail', employee());
    expect(m.wrapper.findAll('ion-toggle, ion-checkbox, ion-select, ion-input')).toHaveLength(0);
    // The only button is the bar's «Back»; the panels have none.
    expect(m.wrapper.findAll('[data-testid^="role-app-"] ion-button, [data-testid^="role-app-"] button')).toHaveLength(0);
  });

  it('a role that is not one of the five, or a page that cannot be read, says so', async () => {
    const m = await open({ locale: 'es' });
    m.call.push(errorFrame(subId(m.client, 'base.role.detail'), 'base.role_not_found'));
    await flush();
    expect(m.wrapper.get('[data-testid="role-not-found"]').text()).toContain('Este rol no existe en este negocio.');

    const other = await open({ locale: 'es' });
    other.call.push(errorFrame(subId(other.client, 'base.role.detail'), 'server_error'));
    await flush();
    expect(other.wrapper.get('[data-testid="role-error"]').text()).toContain('No se pudo cargar lo que permite este rol.');
    expect(other.wrapper.get('[data-testid="role-error"]').text()).toContain('Reintentar');
    const reconnect = vi.spyOn(other.client.stream, 'reconnect');
    await other.wrapper.get('[data-testid="role-error"] ion-button').trigger('click');
    expect(reconnect).toHaveBeenCalledTimes(1);
  });
});
