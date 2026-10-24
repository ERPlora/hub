// Employees › Roles (BASE-G143, G144; the old hub's RolesPanel): erplora.com's four roles, live, each with where it comes
// from («Basic»), «Always available», how many people have it and how many permissions it gives; they are given and
// changed on erplora.com. A catalogue that cannot be read says so.
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { HubRoleRow } from '../operations';
import RolesList from './RolesList.vue';

const MEMBERS_URL = 'http://localhost:8001/businesses/0199a1b2-0000-7000-8000-000000000001/members';

const ROLES: HubRoleRow[] = [
  { key: 'hub_owner', label: 'Owner', origin: 'basic', members: 1, permissions: 149 },
  { key: 'hub_admin', label: 'Admin', origin: 'basic', members: 0, permissions: 149 },
  { key: 'hub_manager', label: 'Manager', origin: 'basic', members: 2, permissions: 120 },
  { key: 'hub_employee', label: 'Employee', origin: 'basic', members: 5, permissions: 43 },
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
    expect(rows).toHaveLength(4);
    expect(rows[0].text()).toContain('Propietario');
    expect(rows[2].text()).toContain('Encargado');
    expect(rows[2].text()).toContain('Básico');
    expect(rows[2].text()).toContain('Siempre disponible');
    expect(rows[3].find('[data-testid="roles-members"]').text()).toBe('5');
    expect(rows[3].find('[data-testid="roles-permissions"]').text()).toBe('43');
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

  it('a catalogue that cannot be read says so', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.role.list'), 'server_error'));
    await flush();
    expect(m.wrapper.text()).toContain('The roles could not be loaded.');
  });
});
