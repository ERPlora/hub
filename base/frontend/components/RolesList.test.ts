import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, installedApp, leaveInstalledApp, mountBase, subId, tap } from '../__tests__/mount-base';
import type { HubRoleRow } from '../operations/people';
import RolesList from './RolesList.vue';

const MEMBERS_URL = 'http://localhost:8001/businesses/0199a1b2-0000-7000-8000-000000000001/members';

function basic(key: string, label: string, members: number, permissions: number): HubRoleRow {
  return { key, label, description: '', origin: 'basic', members, to_review: false, permissions };
}

const ROLES: HubRoleRow[] = [
  basic('hub_owner', 'Owner', 1, 149),
  basic('hub_admin', 'Admin', 0, 149),
  basic('hub_manager', 'Manager', 2, 120),
  basic('hub_employee', 'Employee', 5, 43),
  basic('hub_accountant', 'Accountant', 1, 8),
];

function embed(block: object | null) {
  document.head.innerHTML = block ? `<script id="hub-home" type="application/json">${JSON.stringify(block)}</script>` : '';
}

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(RolesList, { path: '/employees#roles', routes: ['/employees'], ...options });
  const call = await m.live();
  return { ...m, call };
}

afterEach(() => {
  leaveInstalledApp();
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

describe('RolesList', () => {
  it('follows the roles live and explains them', async () => {
    const m = await open({ locale: 'es' });
    expect(m.client.stream.subscriptions('base.role.list').map((sub) => sub.params)).toEqual([{}]);
    expect(m.wrapper.text()).toContain('Estos son los roles de este negocio.');
  });

  it('a row per role, in the business’s language, with its people and permissions', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.role.list', { roles: ROLES });
    const rows = m.wrapper.findAll('[data-testid="roles-row"]');
    expect(rows).toHaveLength(5);
    expect(rows[0].text()).toContain('Propietario');
    expect(rows[2].text()).toContain('Encargado');
    expect(rows[2].text()).toContain('Básico');
    expect(rows[2].text()).toContain('Siempre disponible');
    expect(rows[3].find('[data-testid="roles-members"]').text()).toBe('5');
    expect(rows[3].find('[data-testid="roles-permissions"]').text()).toBe('43');
    expect(rows[4].text()).toContain('Gestoría');
  });

  it('a role the business made goes by its own name, as its own', async () => {
    const own: HubRoleRow = { ...basic('0199aaaa-0000-7000-8000-000000000001', 'Cajero', 3, 12), origin: 'own' };
    const m = await open({ locale: 'es', routes: ['/employees', '/employees/roles/:role'] });
    await m.result(m.call, 'base.role.list', { roles: [...ROLES, own] });
    const row = m.wrapper.findAll('[data-testid="roles-row"]')[5];
    expect(row.text()).toContain('Cajero');
    expect(row.text()).toContain('Propio');
    expect(row.text()).not.toContain('Básico');
    await row.trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe(`/employees/roles/${own.key}`);
  });

  it('who runs the business changes them on erplora.com; anyone else is only shown them', async () => {
    embed({ name: 'Bar', plan_url: '', members_url: MEMBERS_URL });
    const m = await open();
    await m.result(m.call, 'base.role.list', { roles: ROLES });
    expect(m.wrapper.get('a[data-testid="roles-change"]').attributes('href')).toBe(MEMBERS_URL);
    const other = await open({ session: EMPLOYEE });
    await other.result(other.call, 'base.role.list', { roles: ROLES });
    expect(other.wrapper.find('[data-testid="roles-change"]').exists()).toBe(false);
  });

  // The installed app opens nothing on a `_blank` link; the system browser does.
  it('in the installed app «Change roles on erplora.com» opens the system browser; the Google Play copy has none', async () => {
    embed({ name: 'Bar', plan_url: '', members_url: MEMBERS_URL });
    const invoke = installedApp('direct');
    const m = await open();
    await m.result(m.call, 'base.role.list', { roles: ROLES });
    await flush();
    const click = tap(m.wrapper.get('[data-testid="roles-change"]').element);
    await flush();
    expect(click.defaultPrevented).toBe(true);
    expect(invoke).toHaveBeenCalledWith('open_external_url', { url: MEMBERS_URL });
    m.wrapper.unmount();

    leaveInstalledApp();
    installedApp('play');
    const play = await open();
    await play.result(play.call, 'base.role.list', { roles: ROLES });
    await flush();
    expect(play.wrapper.find('[data-testid="roles-change"]').exists()).toBe(false);
  });

  it('anyone opens what a role allows from its row', async () => {
    const m = await open({ session: EMPLOYEE, routes: ['/employees', '/employees/roles/:role'] });
    await m.result(m.call, 'base.role.list', { roles: ROLES });
    await m.wrapper.findAll('[data-testid="roles-row"]')[3].trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/employees/roles/hub_employee');
  });

  it('a catalogue that cannot be read says so', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.role.list'), 'server_error'));
    await flush();
    expect(m.wrapper.text()).toContain('The roles could not be loaded.');
  });
});
