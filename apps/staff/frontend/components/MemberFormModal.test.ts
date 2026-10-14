// STAFF-F01, F02, F03, F21 — the record of a staff member, the old side panel as a dialog: «New» from
// «+», «Edit · {name}» from a row. Fields, in the old order: First name, Last name, Email, Phone,
// Employee ID, Role («No role»), Hub user («No Hub access», with the hint of why to link one), Status
// (only when editing), Bookable, Buffer between appointments, Hire date, Color, Specialties, Bio and,
// for whoever may see the pay, Hourly rate, Commission (%) and the HR notes. Role and Hub user are
// pickers with a server search (a business may have more than the 100 the server gives at once): the
// active roles (`staff.role.list`) and the accounts with access to this business
// (`staff.account.list`). Editing reads the full record and its pay when
// it opens, and saves only what changed. The server judges: a 422 goes under its field, a 409 (the
// Hub user already linked to someone else) on top, and the dialog stays open with what was typed.
import { describe, expect, it, vi } from 'vitest';

import type { MemberOut, RoleOut } from '../operations';
import { click, ionChecked, ionValue, MANAGER, EMPLOYEE, mountStaff, type MountOptions, page, settle } from '../__tests__/mount-staff';
import MemberFormModal from './MemberFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; errorText?: string; type?: string; disabled?: boolean };

const role = (id: string, name: string, is_active = true): RoleOut => ({ id, name, description: '', color: '', order: 0, is_active, member_count: 0 });
const ROLES = page([role('r1', 'Stylist'), role('r2', 'Receptionist')]);

const ROW: MemberOut = {
  id: 'm1',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
  email: 'ana@example.com',
  phone: '600',
  employee_number: 'E-7',
  role_id: 'r3',
  role_name: 'Barber',
  user_id: 4,
  status: 'active',
  is_bookable: true,
  hire_date: '2024-02-01',
  color: '#AA3300',
};
const DETAIL = { ...ROW, booking_buffer: 10, specialties: 'Colour', bio: 'Ten years.', created_at: '2026-01-01T10:00:00Z', updated_at: '2026-01-01T10:00:00Z' };
const PAY = { id: 'm1', user_id: 4, full_name: 'Ana López', role_id: 'r3', role_name: 'Barber', status: 'active', hourly_rate: 1250, commission_rate: '12.50', notes: 'Mornings.' };
const ACCOUNTS = page([
  { user_id: 4, name: 'Ana López' },
  { user_id: 9, name: 'Bea Ruiz' },
]);

const ROUTES = {
  '/api/staff/accounts': [200, ACCOUNTS],
  '/api/staff/roles': [200, ROLES],
  '/api/staff/members/detail': [200, DETAIL],
  '/api/staff/members/compensation': [200, page([PAY])],
  '/api/staff/members': [201, DETAIL],
  '/api/staff/members/update': [200, DETAIL],
} as Record<string, [number, unknown]>;

async function setup(member: MemberOut | null = null, options: MountOptions & { routes?: Record<string, [number, unknown]> } = {}) {
  const m = await mountStaff(MemberFormModal, { props: { open: false, member }, ...options });
  m.answerBy({ ...ROUTES, ...options.routes });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  await settle();
  const field = (name: string) => m.inDoc(`staff-member-form-${name}`) as Control;
  const options_ = (name: string) => [...field(name).querySelectorAll('ion-select-option')].map((o) => [(o as Control).value, o.textContent?.trim()]);
  const root = () => (m.wrapper.element.parentElement ?? m.wrapper.element) as Element;
  /** Opens a picker and gives its choices. */
  async function choices(name: string) {
    await click(field(name));
    await settle();
    return [...root().querySelectorAll(`[data-testid="staff-member-form-${name}-option"]`)].map((o) => [o.getAttribute('data-value'), o.textContent?.trim()]);
  }
  /** Opens a picker and picks the choice of `value`. */
  async function choose(name: string, value: string) {
    await click(field(name));
    await settle();
    await click(root().querySelector(`[data-testid="staff-member-form-${name}-option"][data-value="${value}"]`));
  }
  const save = () => m.inDoc('staff-member-form-submit') as Control;
  const posts = () => m.sent().filter((c) => c.method === 'POST');
  return { ...m, field, options: options_, choices, choose, save, posts };
}

describe('MemberFormModal: New (STAFF-F01)', () => {
  it('is «New», with the old fields in order and no Status (a new person is born Active)', async () => {
    const s = await setup();
    expect(s.inDoc('staff-member-form')?.getAttribute('aria-label')).toBe('New');
    const labels = [...(s.inDoc('staff-member-form-fields') as HTMLElement).querySelectorAll('[data-field]')].map((el) => (el as Control).label ?? el.textContent?.trim());
    expect(labels).toEqual([
      'First name',
      'Last name',
      'Email',
      'Phone',
      'Employee ID',
      'Role',
      'Hub user',
      'Bookable',
      'Buffer between appointments (min)',
      'Hire date',
      'Color',
      'Specialties',
      'Bio',
      'Hourly rate',
      'Commission (%)',
      'HR notes',
    ]);
    expect(s.field('status')).toBeNull();
    expect(s.field('is_bookable').checked).toBe(true);
    expect(s.field('hire_date').type).toBe('date');
    expect(s.field('first_name').getAttribute('mode')).toBe('md');
  });

  it('picks the role among the active ones and the Hub user among the accounts, searching the server', async () => {
    const s = await setup();
    expect([s.field('role_id').value, s.field('user_id').value]).toEqual(['No role', 'No Hub access']);
    expect(await s.choices('role_id')).toEqual([
      ['', 'No role'],
      ['r1', 'Stylist'],
      ['r2', 'Receptionist'],
    ]);
    expect(s.sent()).toContainEqual({ method: 'GET', path: '/api/staff/roles', query: { is_active: 'true', sort: 'name', limit: '100' }, body: undefined });
    expect(await s.choices('user_id')).toEqual([
      ['', 'No Hub access'],
      ['4', 'Ana López'],
      ['9', 'Bea Ruiz'],
    ]);
    expect(s.sent()).toContainEqual({ method: 'GET', path: '/api/staff/accounts', query: { limit: '100' }, body: undefined });
  });

  it('says why to link a Hub user while there is none, and stops saying it once one is chosen', async () => {
    const s = await setup();
    expect(s.inDoc('staff-member-form-hub-user-hint')?.textContent).toContain('counter sales go to whoever is signed in');
    await s.choose('user_id', '9');
    expect(s.field('user_id').value).toBe('Bea Ruiz');
    expect(s.inDoc('staff-member-form-hub-user-hint')).toBeNull();
  });

  it('keeps Save off until first and last name are typed, then sends staff.member.create and closes', async () => {
    const s = await setup();
    expect(s.save().disabled).toBe(true);
    await ionValue(s.field('first_name'), 'Bea', 'ionInput');
    await ionValue(s.field('last_name'), 'Ruiz', 'ionInput');
    await s.choose('user_id', '9');
    await s.choose('role_id', 'r1');
    await ionValue(s.field('hourly_rate'), '12,50', 'ionInput');
    await ionValue(s.field('commission_rate'), '10', 'ionInput');
    await ionChecked(s.field('is_bookable'), false);
    expect(s.save().disabled).toBe(false);
    await click(s.save());
    expect(s.posts()).toEqual([
      {
        method: 'POST',
        path: '/api/staff/members',
        query: {},
        body: {
          first_name: 'Bea',
          last_name: 'Ruiz',
          email: '',
          phone: '',
          employee_number: '',
          is_bookable: false,
          booking_buffer: 0,
          color: '',
          specialties: '',
          bio: '',
          role_id: 'r1',
          user_id: 9,
          hourly_rate: 1250,
          commission_rate: '10',
          notes: '',
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a 422 goes under its field, the dialog stays open with what was typed', async () => {
    const s = await setup(null, {
      routes: {
        '/api/staff/members': [422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { email: 'Enter a valid email address.' } } }],
      },
    });
    await ionValue(s.field('first_name'), 'Bea', 'ionInput');
    await ionValue(s.field('last_name'), 'Ruiz', 'ionInput');
    await ionValue(s.field('email'), 'bea@', 'ionInput');
    await click(s.save());
    expect(s.field('email').errorText).toBe('Enter a valid email address.');
    expect(s.field('email').classList.contains('ion-invalid')).toBe(true);
    expect(s.field('first_name').value).toBe('Bea');
    expect(s.wrapper.emitted('update:open')?.at(-1)).not.toEqual([false]);
  });

  it('a Hub user already linked (409) is said on top, naming who holds it', async () => {
    const message = 'That Hub user is already linked to Ana López. A Hub user can belong to one team member only.';
    const s = await setup(null, { routes: { '/api/staff/members': [409, { error: { code: 'staff.user_already_linked', message } }] } });
    await ionValue(s.field('first_name'), 'Bea', 'ionInput');
    await ionValue(s.field('last_name'), 'Ruiz', 'ionInput');
    await s.choose('user_id', '4');
    await click(s.save());
    expect(s.inDoc('staff-member-form-error')?.textContent).toContain(message);
  });

  it('without the pay permission there are no pay fields and no pay is sent', async () => {
    const s = await setup(null, { session: { ...MANAGER, permissions: MANAGER.permissions.filter((p) => p !== 'staff.view_compensation') } });
    for (const name of ['hourly_rate', 'commission_rate', 'notes']) expect(s.field(name), name).toBeNull();
    await ionValue(s.field('first_name'), 'Bea', 'ionInput');
    await ionValue(s.field('last_name'), 'Ruiz', 'ionInput');
    await click(s.save());
    expect(s.posts()[0].body).not.toHaveProperty('hourly_rate');
  });
});

describe('MemberFormModal: Edit · {name} (STAFF-F02, F03)', () => {
  it('is named after the person, reads the record and its pay, and fills the form with them', async () => {
    const s = await setup(ROW);
    expect(s.inDoc('staff-member-form')?.getAttribute('aria-label')).toBe('Edit · Ana López');
    expect(s.sent().filter((c) => c.method === 'GET').map((c) => [c.path, c.query])).toEqual([
      ['/api/staff/members/detail', { id: 'm1' }],
      ['/api/staff/members/compensation', { id: 'm1', limit: '1' }],
      ['/api/staff/accounts', { user_id: '4', limit: '1' }],
    ]);
    // The role and the Hub user the record holds, by name.
    expect([s.field('role_id').value, s.field('user_id').value]).toEqual(['Barber', 'Ana López']);
    expect([s.field('first_name').value, s.field('booking_buffer').value, s.field('bio').value, s.field('hourly_rate').value, s.field('commission_rate').value, s.field('notes').value]).toEqual([
      'Ana',
      '10',
      'Ten years.',
      '12.50',
      '12.5',
      'Mornings.',
    ]);
  });

  it('a linked account that no longer has access to this business says so, instead of an id', async () => {
    const s = await setup(ROW, { routes: { '/api/staff/accounts': [200, page([])] } });
    expect(s.field('user_id').value).toBe('No access to this business');
  });

  it('offers Active, On leave and Inactive as Status', async () => {
    const s = await setup(ROW);
    expect(s.options('status')).toEqual([
      ['active', 'Active'],
      ['on_leave', 'On leave'],
      ['inactive', 'Inactive'],
    ]);
  });

  it('saves only what changed with staff.member.update; «No Hub access» unlinks with null', async () => {
    const s = await setup(ROW);
    await ionValue(s.field('phone'), '611', 'ionInput');
    await s.choose('user_id', '');
    await ionValue(s.field('status'), 'on_leave');
    await click(s.save());
    expect(s.posts()).toEqual([
      { method: 'POST', path: '/api/staff/members/update', query: {}, body: { id: 'm1', phone: '611', user_id: null, status: 'on_leave' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('Enter on the Role picker opens it and never saves the record (it stays inside the field)', async () => {
    const s = await setup(ROW);
    await ionValue(s.field('phone'), '611', 'ionInput');
    // ion-input keeps its native input in the light DOM: that input is the target of the key.
    const field = s.field('role_id');
    const native = field.querySelector('input') ?? field.appendChild(document.createElement('input'));
    native.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await settle();
    expect(s.posts()).toEqual([]);
    expect(s.inDoc('staff-member-form-role_id-search')).not.toBeNull();
  });

  it('putting someone Inactive with live time off (409) is said on top', async () => {
    const message = 'That member has pending or approved time off that has not ended. Resolve it first.';
    const s = await setup(ROW, { routes: { '/api/staff/members/update': [409, { error: { code: 'staff.active_time_off', message } }] } });
    await ionValue(s.field('status'), 'inactive');
    await click(s.save());
    expect(s.inDoc('staff-member-form-error')?.textContent).toContain(message);
  });

  it('a record that cannot be read says so in the dialog and Save stays off', async () => {
    const s = await setup(ROW, { routes: { '/api/staff/members/detail': [404, { error: { code: 'not_found', message: 'That staff member does not exist in this business.' } }] } });
    expect(s.inDoc('staff-member-form-load-error')?.textContent).toContain('That staff member does not exist in this business.');
    expect(s.save().disabled).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup(ROW, { locale: 'es' });
    expect(s.inDoc('staff-member-form')?.getAttribute('aria-label')).toBe('Editar · Ana López');
    expect([s.field('employee_number').label, s.field('user_id').label, s.field('booking_buffer').label]).toEqual([
      'Nº de empleado',
      'Usuario del Hub',
      'Margen entre citas (min)',
    ]);
  });
});

describe('MemberFormModal: who may open it', () => {
  it('an employee never gets here (no «+», no row to open), and reads no account', async () => {
    const s = await setup(null, { session: EMPLOYEE });
    expect(s.sent().some((c) => c.path === '/api/staff/accounts')).toBe(false);
  });
});
