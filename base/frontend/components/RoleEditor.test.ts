import { afterEach, describe, expect, it } from 'vitest';

import { between } from '../__tests__/settings-form';
import { click, flush, ionChecked, ionValue, mountBase } from '../__tests__/mount-base';
import type { HubRoleRow, RoleDetail, RolePermission, RoleState } from '../operations/people';
import RoleEditor from './RoleEditor.vue';

const KEY = '0199aaaa-0000-7000-8000-000000000001';
const SAVE = '/api/roles/update';

const line = (permission: string, state: RoleState, fields: Partial<RolePermission> = {}): RolePermission => ({
  permission,
  phrase: permission,
  state,
  approvable: false,
  to_review: false,
  ...fields,
});

function cashier(fields: Partial<RoleDetail> = {}): RoleDetail {
  return {
    key: KEY,
    label: 'Cajero',
    description: 'La caja',
    origin: 'own',
    members: 2,
    to_review: false,
    apps: [
      { app: 'base', name: 'El negocio', permissions: [line('base.view_home', 'on')] },
      {
        app: 'sale',
        name: 'Ventas / TPV',
        permissions: [line('sale.take_payment', 'on'), line('sale.void_sale', 'approval', { approvable: true })],
      },
      { app: 'sensitive', name: 'Datos sensibles', permissions: [line('base.view_costs', 'off')] },
    ],
    ...fields,
  };
}

/** The same role with an app turned on after it was saved. */
const withNews = (): RoleDetail =>
  cashier({
    to_review: true,
    apps: [...cashier().apps, { app: 'table', name: 'Mesas', permissions: [line('table.view', 'on', { to_review: true })] }],
  });

/** What the Hub answers to the save: the role as the list shows it. */
const answerOf = (fields: Partial<HubRoleRow> = {}): HubRoleRow => ({
  key: KEY,
  label: 'Cajero',
  description: 'La caja',
  origin: 'own',
  members: 2,
  to_review: false,
  permissions: 12,
  ...fields,
});

async function open(role = cashier()) {
  return mountBase(RoleEditor, { locale: 'es', props: { role } });
}

type Mounted = Awaited<ReturnType<typeof open>>;
const el = (m: Mounted, testid: string) => m.wrapper.get(`[data-testid="${testid}"]`).element;
const save = async (m: Mounted) => {
  await click(el(m, 'role-save'));
  await flush();
};
const saveIsOff = (m: Mounted) => (el(m, 'role-save') as unknown as { disabled: boolean }).disabled;
const bodies = (m: Mounted) => m.sent().filter((call) => call.path === SAVE).map((call) => call.body);
const ALL: Record<string, RoleState> = {
  'base.view_home': 'on',
  'sale.take_payment': 'on',
  'sale.void_sale': 'approval',
  'base.view_costs': 'off',
};

afterEach(() => {
  document.body.innerHTML = '';
});

describe('RoleEditor', () => {
  it('a panel per app with each permission as it is, the name and the description to change', async () => {
    const m = await open();
    expect(m.wrapper.findAll('[data-testid^="role-app-"] h2').map((title) => title.text())).toEqual([
      'El negocio',
      'Ventas / TPV',
      'Datos sensibles',
    ]);
    expect((el(m, 'role-switch-sale.take_payment') as unknown as { checked: boolean }).checked).toBe(true);
    expect((el(m, 'role-switch-base.view_costs') as unknown as { checked: boolean }).checked).toBe(false);
    expect((el(m, 'role-states-sale.void_sale') as unknown as { value: string }).value).toBe('approval');
    expect((el(m, 'role-name') as unknown as { value: string }).value).toBe('Cajero');
    expect((el(m, 'role-description') as unknown as { value: string }).value).toBe('La caja');
    expect(m.wrapper.get('[data-testid="role-members"]').text()).toBe('Personas con este rol: 2');
    expect(m.wrapper.find('[data-testid="role-review"]').exists()).toBe(false);
    expect(m.wrapper.find('form').attributes()).toHaveProperty('novalidate');
  });

  it('has nothing to save until something changes, and back as it was neither', async () => {
    const m = await open();
    expect(saveIsOff(m)).toBe(true);
    await ionChecked(el(m, 'role-switch-sale.take_payment'), false);
    expect(saveIsOff(m)).toBe(false);
    await ionChecked(el(m, 'role-switch-sale.take_payment'), true);
    expect(saveIsOff(m)).toBe(true);
  });

  it('saves everything it shows, so the role is left reviewed', async () => {
    const m = await open();
    m.answerBy({ [SAVE]: [200, answerOf()] });
    await ionChecked(el(m, 'role-switch-sale.take_payment'), false);
    await ionValue(el(m, 'role-states-sale.void_sale'), 'off');
    await save(m);

    expect(bodies(m)).toEqual([{ role: KEY, states: { ...ALL, 'sale.take_payment': 'off', 'sale.void_sale': 'off' } }]);
    expect(m.wrapper.get('[data-testid="role-saved"]').text()).toContain('Rol guardado.');
    // What was saved stays painted before the live answer comes.
    expect((el(m, 'role-switch-sale.take_payment') as unknown as { checked: boolean }).checked).toBe(false);
    expect(saveIsOff(m)).toBe(true);
  });

  it('a new name goes alone: what the role allows is not sent again', async () => {
    const m = await open();
    m.answerBy({ [SAVE]: [200, answerOf({ label: 'Caja de tarde' })] });
    await ionValue(el(m, 'role-name'), 'Caja de tarde', 'ionInput');
    await save(m);
    expect(bodies(m)).toEqual([{ role: KEY, name: 'Caja de tarde' }]);
    expect((el(m, 'role-name') as unknown as { value: string }).value).toBe('Caja de tarde');
  });

  it('an emptied description is sent empty', async () => {
    const m = await open();
    m.answerBy({ [SAVE]: [200, answerOf({ description: '' })] });
    await ionValue(el(m, 'role-description'), '', 'ionInput');
    await save(m);
    expect(bodies(m)).toEqual([{ role: KEY, description: '' }]);
  });

  it('with new permissions says so and may be saved as it is, which leaves them reviewed', async () => {
    const m = await open(withNews());
    const notice = m.wrapper.get('[data-testid="role-review"]');
    expect(notice.text()).toContain('Permisos nuevos por revisar');
    expect(m.wrapper.findAll('[data-testid="role-to-review"]')).toHaveLength(1);
    expect(saveIsOff(m)).toBe(false);

    m.answerBy({ [SAVE]: [200, answerOf()] });
    await save(m);

    expect(bodies(m)).toEqual([{ role: KEY, states: { ...ALL, 'table.view': 'on' } }]);
    expect(m.wrapper.find('[data-testid="role-saved"]').exists()).toBe(true);
    await m.wrapper.setProps({ role: cashier() });
    expect(m.wrapper.find('[data-testid="role-review"]').exists()).toBe(false);
    expect(saveIsOff(m)).toBe(true);
  });

  it('an app turned on meanwhile comes to review, with what was being changed still there', async () => {
    const m = await open();
    await ionChecked(el(m, 'role-switch-base.view_costs'), true);
    await m.wrapper.setProps({ role: withNews() });
    expect((el(m, 'role-switch-base.view_costs') as unknown as { checked: boolean }).checked).toBe(true);

    m.answerBy({ [SAVE]: [200, answerOf()] });
    await save(m);
    expect(bodies(m)).toEqual([{ role: KEY, states: { ...ALL, 'base.view_costs': 'on', 'table.view': 'on' } }]);
  });

  it('what another person saves meanwhile is painted, save what this one is changing', async () => {
    const m = await open();
    await ionChecked(el(m, 'role-switch-base.view_costs'), true);
    const apps = cashier().apps.map((app) => ({
      ...app,
      permissions: app.permissions.map((each) => (each.permission === 'sale.take_payment' ? { ...each, state: 'off' as const } : each)),
    }));
    await m.wrapper.setProps({ role: cashier({ apps }) });
    expect((el(m, 'role-switch-sale.take_payment') as unknown as { checked: boolean }).checked).toBe(false);
    expect((el(m, 'role-switch-base.view_costs') as unknown as { checked: boolean }).checked).toBe(true);
  });

  it('a role that would allow more than its editor may do is refused next to Save, with the change still there', async () => {
    const m = await open();
    const message = 'Un rol no puede permitir más de lo que puedes hacer tú.';
    m.answerBy({ [SAVE]: [403, { error: { code: 'base.role_beyond_editor', message, fields: { states: message } } }] });
    await ionChecked(el(m, 'role-switch-base.view_costs'), true);
    await save(m);

    const notice = m.wrapper.get('[data-testid="role-save-error"]');
    expect(notice.text()).toContain('No se pudo guardar el rol');
    expect(notice.text()).toContain(message);
    expect((el(m, 'role-switch-base.view_costs') as unknown as { checked: boolean }).checked).toBe(true);
    expect(m.wrapper.find('[data-testid="role-saved"]').exists()).toBe(false);
    expect(between(el(m, 'role-app-sensitive'), notice.element, el(m, 'role-save'))).toBe(true);

    await ionChecked(el(m, 'role-switch-base.view_costs'), false);
    expect(m.wrapper.find('[data-testid="role-save-error"]').exists()).toBe(false);
  });

  it('a name that is taken is said under the name', async () => {
    const m = await open();
    const message = 'Ya hay un rol con ese nombre. Elige otro.';
    m.answerBy({ [SAVE]: [409, { error: { code: 'base.role_name_taken', message, fields: { name: message } } }] });
    await ionValue(el(m, 'role-name'), 'Camarero', 'ionInput');
    await save(m);
    expect((el(m, 'role-name') as unknown as { errorText: string }).errorText).toBe(message);
  });
});
