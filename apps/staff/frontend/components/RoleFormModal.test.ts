// STAFF-F04 «Crear, editar y retirar un rol»: «+» opens «New» (Role name, Description, Color — the old
// create panel); a row opens «Edit · {name}», which also has Order and Active (off = retired: it is
// no longer offered in the records, the ones holding it keep it). New sends `staff.role.create`; Edit
// sends only what changed with `staff.role.update`. A name already taken (409) is said on top; a 422
// goes under its field; the dialog keeps what was typed.
import { describe, expect, it, vi } from 'vitest';

import type { RoleOut } from '../operations';
import { click, ionChecked, ionValue, mountStaff, settle } from '../__tests__/mount-staff';
import RoleFormModal from './RoleFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; placeholder?: string; errorText?: string; disabled?: boolean };

const ROLE: RoleOut = { id: 'r1', name: 'Stylist', description: 'Cuts and colour', color: '#AA3300', order: 2, is_active: true, member_count: 3 };

async function setup(role: RoleOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountStaff(RoleFormModal, { props: { open: false, role }, locale, path: '/staff/roles' });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`staff-role-form-${name}`) as Control;
  const save = () => m.inDoc('staff-role-form-submit') as Control;
  return { ...m, field, save };
}

describe('RoleFormModal: New', () => {
  it('asks for the role name, a description and a colour, as the old panel', async () => {
    const s = await setup();
    expect(s.inDoc('staff-role-form')?.getAttribute('aria-label')).toBe('New');
    expect([s.field('name').label, s.field('description').label, s.field('color').label, s.field('color').placeholder]).toEqual([
      'Role name',
      'Description',
      'Color',
      'Color (#RRGGBB)',
    ]);
    expect(s.field('order')).toBeNull();
    expect(s.field('is_active')).toBeNull();
    expect(s.save().disabled).toBe(true);
  });

  it('sends staff.role.create with what was typed, trimmed, and closes', async () => {
    const s = await setup();
    s.answer(201, ROLE);
    await ionValue(s.field('name'), ' Stylist ', 'ionInput');
    await ionValue(s.field('color'), '#AA3300', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/roles', query: {}, body: { name: 'Stylist', description: '', color: '#AA3300' } }]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a name already taken (409) is said on top; a bad colour (422) under its field', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'staff.role_name_taken', message: 'A role with that name already exists.' } });
    await ionValue(s.field('name'), 'stylist', 'ionInput');
    await click(s.save());
    expect(s.inDoc('staff-role-form-error')?.textContent).toContain('A role with that name already exists.');
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { color: 'Enter a valid value.' } } });
    await click(s.save());
    expect(s.field('color').errorText).toBe('Enter a valid value.');
    expect(s.field('name').value).toBe('stylist');
  });
});

describe('RoleFormModal: Edit · {name}', () => {
  it('is named after the role and adds Order and Active, with what retiring means', async () => {
    const s = await setup(ROLE);
    expect(s.inDoc('staff-role-form')?.getAttribute('aria-label')).toBe('Edit · Stylist');
    expect([s.field('name').value, s.field('description').value, s.field('color').value, s.field('order').value, s.field('is_active').checked]).toEqual([
      'Stylist',
      'Cuts and colour',
      '#AA3300',
      '2',
      true,
    ]);
    expect(s.inDoc('staff-role-form-active-hint')?.textContent).toContain('no longer offered');
  });

  it('retires the role sending only what changed', async () => {
    const s = await setup(ROLE);
    s.answer(200, { ...ROLE, is_active: false });
    await ionChecked(s.field('is_active'), false);
    await ionValue(s.field('order'), '5', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/roles/update', query: {}, body: { id: 'r1', order: 5, is_active: false } }]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(ROLE, 'es');
    expect(s.inDoc('staff-role-form')?.getAttribute('aria-label')).toBe('Editar · Stylist');
    expect([s.field('name').label, s.field('order').label]).toEqual(['Nombre del rol', 'Orden']);
  });
});
