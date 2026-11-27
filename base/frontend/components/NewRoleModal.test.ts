import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { click, flush, ionValue, mountBase, settle } from '../__tests__/mount-base';
import type { HubRoleRow } from '../operations/people';
import NewRoleModal from './NewRoleModal.vue';

const OWN = '0199aaaa-0000-7000-8000-000000000001';
const row = (key: string, label: string, origin: 'basic' | 'own' = 'basic'): HubRoleRow => ({
  key,
  label,
  description: '',
  origin,
  members: 0,
  to_review: false,
  mine: false,
  permissions: 10,
});
const ROLES = [row('hub_manager', 'Manager'), row('hub_employee', 'Employee'), row(OWN, 'Cajero', 'own')];

/** The window open over the roles, to start from `from`. */
async function open(from = 'hub_employee') {
  const m = await mountBase(NewRoleModal, { locale: 'es', props: { roles: ROLES, from, open: false } });
  await m.wrapper.setProps({ open: true });
  await settle();
  return m;
}

type Mounted = Awaited<ReturnType<typeof open>>;
const name = (m: Mounted) => m.inDoc('role-new-name');
const basedOn = (m: Mounted) => m.inDoc('role-new-based-on');
const submit = async (m: Mounted) => {
  await click(m.inDoc('role-new-submit'));
  await flush();
};

afterEach(() => {
  document.body.innerHTML = '';
});

describe('NewRoleModal', () => {
  it('offers every role to start from, each by its name, with the one asked for chosen', async () => {
    const m = await open();
    expect(m.inDoc('role-new')?.textContent).toContain('Nuevo rol');
    const options = [...(basedOn(m)?.querySelectorAll('ion-select-option') ?? [])].map((option) => option.textContent?.trim());
    expect(options).toEqual(['Encargado', 'Empleado', 'Cajero']);
    expect((basedOn(m) as unknown as { value: string }).value).toBe('hub_employee');
    expect((name(m) as unknown as { value: string }).value).toBe('');
  });

  it('is not sent without a name', async () => {
    const m = await open();
    await submit(m);
    expect(m.sent()).toEqual([]);
    await ionValue(name(m), '   ', 'ionInput');
    await submit(m);
    expect(m.sent()).toEqual([]);
  });

  it('makes the role with its name from the one chosen, says so and hands it over', async () => {
    const m = await open();
    m.answerBy({ '/api/roles': [200, row(OWN, 'Caja de tarde', 'own')] });
    await ionValue(name(m), ' Caja de tarde ', 'ionInput');
    await ionValue(basedOn(m), 'hub_manager');
    await submit(m);

    expect(m.sent().map((call) => [call.method, call.path, call.body])).toEqual([
      ['POST', '/api/roles', { name: 'Caja de tarde', based_on: 'hub_manager' }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Rol Caja de tarde creado');
    expect(m.wrapper.emitted('created')).toEqual([[OWN]]);
    expect(m.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a name that is taken is said under the name, and the window stays', async () => {
    const m = await open();
    const message = 'Ya hay un rol con ese nombre. Elige otro.';
    m.answerBy({ '/api/roles': [409, { error: { code: 'base.role_name_taken', message, fields: { name: message } } }] });
    await ionValue(name(m), 'Cajero', 'ionInput');
    await submit(m);

    expect((name(m) as unknown as { errorText: string }).errorText).toBe(message);
    expect(m.wrapper.emitted('created')).toBeUndefined();
    expect(m.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('a role that allows more than its maker may do is refused in the window', async () => {
    const m = await open();
    const message = 'Un rol no puede permitir más de lo que puedes hacer tú.';
    m.answerBy({ '/api/roles': [403, { error: { code: 'base.role_beyond_editor', message, fields: { states: message } } }] });
    await ionValue(name(m), 'Cajero', 'ionInput');
    await submit(m);

    expect(m.inDoc('role-new-error')?.textContent).toContain(message);
    expect(m.wrapper.emitted('created')).toBeUndefined();

    await m.wrapper.setProps({ open: false });
    await m.wrapper.setProps({ open: true });
    await settle();
    expect(m.inDoc('role-new-error')).toBeNull();
  });

  it('opens clean every time', async () => {
    const m = await open();
    await ionValue(name(m), 'A medias', 'ionInput');
    await m.wrapper.setProps({ open: false });
    await m.wrapper.setProps({ open: true, from: OWN });
    await settle();
    expect((name(m) as unknown as { value: string }).value).toBe('');
    expect((basedOn(m) as unknown as { value: string }).value).toBe(OWN);
  });
});
