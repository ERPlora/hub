import { toastSuccess } from '@erplora/ui/shell';
import { offeredRowActions, pressRowAction } from '@erplora/ui/testing/data-table';
import { afterEach, describe, expect, it } from 'vitest';

import { click, EMPLOYEE, errorFrame, flush, installedApp, ionValue, leaveInstalledApp, mountBase, OWNER, settle, subId, tap } from '../__tests__/mount-base';
import type { HubRoleRow } from '../operations/people';
import RolesList from './RolesList.vue';

/** Who manages the roles: the owner and whoever runs the business. */
const MANAGES = { ...OWNER, permissions: [...OWNER.permissions, 'base.manage_roles'] };
const OWN = '0199aaaa-0000-7000-8000-000000000001';
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

const cashier = (fields: Partial<HubRoleRow> = {}): HubRoleRow => ({ ...basic(OWN, 'Cajero', 0, 12), origin: 'own', ...fields });

/** The list as who manages the roles opens it, with a role of the business's own. */
async function managed(own = cashier()) {
  const m = await open({ session: MANAGES, locale: 'es', routes: ['/employees', '/employees/roles/:role'] });
  await m.result(m.call, 'base.role.list', { roles: [...ROLES, own] });
  return m;
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
    expect(rows[3].find('[data-testid="roles-members"]').text()).toBe('5');
    expect(rows[3].find('[data-testid="roles-permissions"]').text()).toBe('43');
    expect(rows[4].text()).toContain('Gestoría');
  });

  it('a role the business made goes by its own name, as its own', async () => {
    const own = cashier({ members: 3 });
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

  it('marks the one left to review, and no other', async () => {
    const m = await managed(cashier({ to_review: true }));
    const marked = m.wrapper.findAll('[data-testid="roles-row"]').map((row) => row.find('[data-testid="roles-to-review"]').exists());
    expect(marked).toEqual([false, false, false, false, false, true]);
    expect(m.wrapper.get('[data-testid="roles-to-review"]').text()).toBe('Por revisar');
  });

  it('who manages the roles duplicates any, and edits or deletes the business’s own', async () => {
    const m = await managed();
    expect(offeredRowActions(m.wrapper, 'hub_employee')).toEqual(['duplicate']);
    expect(offeredRowActions(m.wrapper, OWN)).toEqual(['duplicate', 'edit', 'delete']);
    expect(m.wrapper.find('[data-testid="roles-add"]').text()).toContain('Nuevo rol');
  });

  it('whoever does not manage them is only shown them', async () => {
    const m = await open();
    await m.result(m.call, 'base.role.list', { roles: [...ROLES, cashier()] });
    expect(offeredRowActions(m.wrapper, 'hub_employee')).toEqual([]);
    expect(offeredRowActions(m.wrapper, OWN)).toEqual([]);
    expect(m.wrapper.find('[data-testid="roles-add"]').exists()).toBe(false);
  });

  it('«Duplicate» starts the new role from that one; «New role», from the employee’s', async () => {
    const m = await managed();
    const chosen = () => (m.inDoc('role-new-based-on') as unknown as { value: string }).value;
    await pressRowAction(m.wrapper, OWN, 'duplicate');
    await settle();
    expect(chosen()).toBe(OWN);
    await click(m.inDoc('role-new-cancel'));
    await m.wrapper.get('[data-testid="roles-add"]').trigger('click');
    await settle();
    expect(chosen()).toBe('hub_employee');
  });

  it('the role just made opens to adjust it', async () => {
    const m = await managed();
    const made = '0199aaaa-0000-7000-8000-000000000002';
    m.answerBy({ '/api/roles': [200, cashier({ key: made, label: 'Caja de tarde' })] });
    await pressRowAction(m.wrapper, 'hub_employee', 'duplicate');
    await settle();
    await ionValue(m.inDoc('role-new-name'), 'Caja de tarde', 'ionInput');
    await click(m.inDoc('role-new-submit'));
    await flush();
    expect(m.router.currentRoute.value.path).toBe(`/employees/roles/${made}`);
  });

  it('«Edit» opens the role, as its row does', async () => {
    const m = await managed();
    await pressRowAction(m.wrapper, OWN, 'edit');
    await flush();
    expect(m.router.currentRoute.value.path).toBe(`/employees/roles/${OWN}`);
  });

  it('«Delete» asks first, deletes it and says so', async () => {
    const m = await managed();
    m.answerBy({ '/api/roles/delete': [200, { key: OWN }] });
    await pressRowAction(m.wrapper, OWN, 'delete');
    await settle();
    expect(m.inDoc('role-delete')?.textContent).toContain('¿Borrar el rol Cajero? No se puede deshacer.');
    expect(m.sent()).toEqual([]);
    await click(m.inDoc('role-delete-submit'));
    await flush();

    expect(m.sent().map((call) => [call.path, call.body])).toEqual([['/api/roles/delete', { role: OWN }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Rol Cajero borrado');
    expect(m.inDoc('role-delete-submit')).toBeNull();
  });

  it('one somebody has is refused in the question, which stays; asked again, it is clean', async () => {
    const m = await managed(cashier({ members: 2 }));
    const message = '2 personas tienen este rol. Dales otro antes de borrarlo.';
    m.answerBy({ '/api/roles/delete': [409, { error: { code: 'base.role_in_use', message } }] });
    await pressRowAction(m.wrapper, OWN, 'delete');
    await settle();
    await click(m.inDoc('role-delete-submit'));
    await flush();
    expect(m.inDoc('role-delete')?.textContent).toContain(message);
    expect(toastSuccess).not.toHaveBeenCalled();

    await click(m.inDoc('role-delete-cancel'));
    await pressRowAction(m.wrapper, OWN, 'delete');
    await settle();
    expect(m.inDoc('role-delete')?.textContent).not.toContain(message);
  });

  it('a catalogue that cannot be read says so', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.role.list'), 'server_error'));
    await flush();
    expect(m.wrapper.text()).toContain('The roles could not be loaded.');
  });
});
