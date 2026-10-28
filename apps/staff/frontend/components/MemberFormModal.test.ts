// STAFF-F01, F02, F03, F21 — the record of a staff member, the old side panel as a dialog: «New» from
// «+», «Edit · {name}» from a row. Fields, in the old order: First name, Last name, Email, Phone,
// Employee ID, Role («No role»), Hub user («No Hub access», with the hint of why to link one), Status
// (only when editing), Bookable, Buffer between appointments, Hire date, Color, Specialties, Bio and,
// for whoever may see the pay, Hourly rate, Commission (%) and the HR notes. Role and Hub user are
// Combo fields that search the server (a business may have more than the 100 it gives at once): the
// active roles (`staff.role.list`) and the accounts with access to this business
// (`staff.account.list`), «No role» / «No Hub access» first. Editing reads the full record and its pay when
// it opens, and saves only what changed. The server judges: a 422 goes under its field, a 409 (the
// Hub user already linked to someone else) on top, and the dialog stays open with what was typed.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { MemberOut, RoleOut } from '../operations';
import {
  BUSINESS,
  business,
  click,
  EMPLOYEE,
  ionChecked,
  ionValue,
  JAPANESE,
  MANAGER,
  mountStaff,
  type MountOptions,
  page,
  POLISH,
  settle,
} from '../__tests__/mount-staff';
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
  /** The Combo of a field (`role_id`, `user_id`). */
  const combo = (name: string) => m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === `staff-member-form-${name}`);
  /** What a Combo offers for `query` (`''`: on opening), as [id, label]. */
  async function choices(name: string, query = '') {
    const search = combo(name)?.props('search') as ((q: string) => Promise<ComboOption[]>) | undefined;
    if (!search) throw new Error(`${name} is not a Combo with a server search`);
    const found = await search(query);
    await settle();
    return found.map((o) => [o.id, o.label]);
  }
  /** Picks, in a Combo, the option of `id` it offers on opening. */
  async function choose(name: string, id: string) {
    const search = combo(name)?.props('search') as ((q: string) => Promise<ComboOption[]>) | undefined;
    if (!search) throw new Error(`${name} is not a Combo with a server search`);
    const option = (await search('')).find((o) => o.id === id);
    if (!option) throw new Error(`${name} offers no ${id}`);
    combo(name)!.vm.$emit('update:modelValue', option);
    await settle();
  }
  const save = () => m.inDoc('staff-member-form-submit') as Control;
  const posts = () => m.sent().filter((c) => c.method === 'POST');
  return { ...m, field, options: options_, combo, choices, choose, save, posts };
}

describe('MemberFormModal: New (STAFF-F01)', () => {
  it('is «New», with the old fields in order and no Status (a new person is born Active)', async () => {
    const s = await setup();
    expect(s.inDoc('staff-member-form')?.getAttribute('aria-label')).toBe('New');
    // A Combo carries `data-field` on its wrapper, around its ion-input.
    const label = (el: Element) => (el as Control).label ?? (el.querySelector('ion-input') as Control | null)?.label ?? el.textContent?.trim();
    const labels = [...(s.inDoc('staff-member-form-fields') as HTMLElement).querySelectorAll('[data-field]')].map(label);
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

  it('asks the server again as the person types, without the «none» choice', async () => {
    const s = await setup();
    expect(await s.choices('role_id', 'sty')).toEqual([
      ['r1', 'Stylist'],
      ['r2', 'Receptionist'],
    ]);
    expect(s.sent()).toContainEqual({ method: 'GET', path: '/api/staff/roles', query: { is_active: 'true', sort: 'name', limit: '100', search: 'sty' }, body: undefined });
    expect((await s.choices('user_id', 'bea')).map(([id]) => id)).toEqual(['4', '9']);
  });

  it('Role and Hub user empty with their «none» choice (no Clear button), and say «No results»', async () => {
    const s = await setup();
    for (const name of ['role_id', 'user_id']) {
      expect([s.combo(name)?.props('label'), s.combo(name)?.props('clearable'), s.combo(name)?.props('emptyLabel')], name).toEqual([
        name === 'role_id' ? 'Role' : 'Hub user',
        false,
        'No results',
      ]);
    }
    await s.choose('role_id', 'r1');
    expect(s.field('role_id').value).toBe('Stylist');
    await s.choose('role_id', '');
    expect(s.field('role_id').value).toBe('No role');
  });

  it('a 422 on the role goes under its field', async () => {
    const s = await setup(null, {
      routes: { '/api/staff/members': [422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { role_id: 'That role is not active.' } } }] },
    });
    await ionValue(s.field('first_name'), 'Bea', 'ionInput');
    await ionValue(s.field('last_name'), 'Ruiz', 'ionInput');
    await s.choose('role_id', 'r1');
    await click(s.save());
    expect(s.combo('role_id')?.props('errorText')).toBe('That role is not active.');
    expect(s.field('role_id').classList.contains('ion-invalid')).toBe(true);
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

  // gh:staff#70: closing the panel while the record loads drops that read: a late answer never fills the
  // form opened next.
  it('a record that answers after the panel closed never fills the next form', async () => {
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    const m = await mountStaff(MemberFormModal, { props: { open: false, member: ROW } });
    m.net.onApi(async ({ url }) => {
      const path = new URL(url, 'http://a.localhost').pathname;
      if (path === '/api/staff/members/detail') await held;
      const [status, body] = ROUTES[path] ?? [404, { error: { code: 'not_found', message: 'Not found' } }];
      return Response.json(body, { status });
    });
    await m.wrapper.setProps({ open: true });
    await settle();
    expect(m.inDoc('staff-member-form-loading')).not.toBeNull();
    await m.wrapper.setProps({ open: false });
    await settle();
    await m.wrapper.setProps({ member: null, open: true });
    await settle();
    release();
    await settle();
    await settle();
    const field = (name: string) => m.inDoc(`staff-member-form-${name}`) as Control;
    expect(m.inDoc('staff-member-form')?.getAttribute('aria-label')).toBe('New');
    expect([field('first_name').value, field('email').value, field('bio').value]).toEqual(['', '', '']);
    expect(m.inDoc('staff-member-form-loading')).toBeNull();
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

  it('a new record speaks Spanish in its pickers too', async () => {
    const s = await setup(null, { locale: 'es' });
    expect([s.field('role_id').value, s.field('user_id').value]).toEqual(['Sin rol', 'Sin acceso al Hub']);
    expect((await s.choices('role_id'))[0]).toEqual(['', 'Sin rol']);
    expect(s.combo('role_id')?.props('emptyLabel')).toBe('Sin resultados');
  });
});

describe('MemberFormModal: the business\'s currency (staff-business-currency)', () => {
  const YEN_PAY = { '/api/staff/members/compensation': [200, page([{ ...PAY, hourly_rate: 1500 }])] } as Record<string, [number, unknown]>;
  /** What the end of the Hourly rate field says (the currency's symbol), `null` when it says nothing. */
  const symbol = (s: Awaited<ReturnType<typeof setup>>) => s.inDoc('staff-member-form-hourly_rate-currency')?.textContent?.trim() ?? null;
  async function answer(s: Awaited<ReturnType<typeof setup>>, fields: Parameters<typeof business>[0]) {
    await s.live();
    await s.result(BUSINESS, business(fields));
    await settle();
  }

  it('a business in Poland types the rate in złoty: «zł» at the end of the field, never «€»', async () => {
    const s = await setup(ROW, { locale: 'es' });
    await answer(s, POLISH);
    expect(symbol(s)).toBe('zł');
    expect(s.field('hourly_rate').value).toBe('12,50');
    await ionValue(s.field('hourly_rate'), '13,75', 'ionInput');
    await click(s.save());
    expect(s.posts().map((c) => c.body)).toEqual([{ id: 'm1', hourly_rate: 1375 }]);
  });

  it('a business in Spain still types it in euros', async () => {
    const s = await setup(null);
    await answer(s, {});
    expect(symbol(s)).toBe('€');
  });

  it('until the business answers, the field shows no symbol, never «€»', async () => {
    const s = await setup(null);
    expect(symbol(s)).toBeNull();
  });

  // gh:staff#64: in yen what is typed is yen: «1500» is 1500, not 150000.
  it('a business in Japan types whole yen: «1500» goes as 1500', async () => {
    const s = await setup(null);
    await answer(s, JAPANESE);
    expect(symbol(s)).toBe('¥');
    await ionValue(s.field('first_name'), 'Bea', 'ionInput');
    await ionValue(s.field('last_name'), 'Ruiz', 'ionInput');
    await ionValue(s.field('hourly_rate'), '1500', 'ionInput');
    await click(s.save());
    expect(s.posts()[0].body).toMatchObject({ hourly_rate: 1500 });
  });

  it('a rate read before the business answers is rewritten in its decimals when it does, and saving it unchanged sends nothing', async () => {
    const s = await setup(ROW, { routes: YEN_PAY });
    expect(s.field('hourly_rate').value).toBe('15.00');
    await answer(s, JAPANESE);
    expect(s.field('hourly_rate').value).toBe('1500');
    await click(s.save());
    expect(s.posts().map((c) => c.body)).toEqual([{ id: 'm1' }]);
  });

  it('a rate typed before the business answers stays as typed and is read in its currency when saving', async () => {
    const s = await setup(ROW, { routes: YEN_PAY });
    await ionValue(s.field('hourly_rate'), '1600', 'ionInput');
    await answer(s, JAPANESE);
    expect(s.field('hourly_rate').value).toBe('1600');
    await click(s.save());
    expect(s.posts().map((c) => c.body)).toEqual([{ id: 'm1', hourly_rate: 1600 }]);
  });
});

describe('MemberFormModal: who may open it', () => {
  it('an employee never gets here (no «+», no row to open), and reads no account', async () => {
    const s = await setup(null, { session: EMPLOYEE });
    expect(s.sent().some((c) => c.path === '/api/staff/accounts')).toBe(false);
  });
});
