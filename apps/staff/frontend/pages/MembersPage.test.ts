// Staff → Staff (WORKBOOK «Pantallas · Personal»; STAFF-F01–F06, F08, F21): the live
// `staff.member.list` in a server-side DataTable — Name, Role, Email, Status and, only for whoever may
// see the pay, Rate/h; Phone exists but starts hidden —, «Search member…», sort by any column, the
// filters (first name, last name, email, phone, role, status, bookable, hire date, colour, Hub user),
// 50 a page. «+» opens «New» for whoever may add; a row (or «Edit») opens «Edit · {name}» for whoever may
// edit; «Deactivate» (confirmed) and «Terminate» (with its dialog) only for the owner and the admin.
// «My record» opens one's own record when it is linked. Every change comes back through the stream.
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { MemberMineOut, MemberOut } from '../operations';
import { click, EMPLOYEE, errorFrame, flush, MANAGER, type MountOptions, mountStaff, page, settle } from '../__tests__/mount-staff';
import FilterPanel from '../components/FilterPanel.vue';
import MemberFormModal from '../components/MemberFormModal.vue';
import MyRecordModal from '../components/MyRecordModal.vue';
import TerminateDialog from '../components/TerminateDialog.vue';
import MembersPage from './MembersPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'staff.member.list';

const member = (id: string, over: Partial<MemberOut> = {}): MemberOut => ({
  id,
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
  email: 'ana@example.com',
  phone: '600',
  employee_number: '',
  role_id: 'r1',
  role_name: 'Stylist',
  user_id: null,
  status: 'active',
  is_bookable: true,
  hire_date: null,
  color: '',
  ...over,
});
const ROWS = [
  member('m1'),
  member('m2', { first_name: 'Bea', last_name: 'Ruiz', full_name: 'Bea Ruiz', email: '', role_id: null, role_name: null, status: 'inactive' }),
];
const PAY = page([
  { id: 'm1', user_id: null, full_name: 'Ana López', role_id: 'r1', role_name: 'Stylist', status: 'active', hourly_rate: 1250, commission_rate: '10.00', notes: '' },
]);
const ACCOUNTS = page([{ user_id: 4, name: 'Ana López' }]);
const ROLES = page([{ id: 'r1', name: 'Stylist', description: '', color: '', order: 0, is_active: true, member_count: 1 }]);

async function setup(options: MountOptions = {}) {
  const m = await mountStaff(MembersPage, { path: '/staff/members', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="staff-members-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const list = () => m.params(OP);
  async function show(data: unknown) {
    await m.result(OP, data);
  }
  async function showOnNewStream(data: unknown) {
    await m.reopen();
    await m.result(OP, data);
  }
  async function filter(values: Record<string, string>) {
    m.wrapper.findComponent(FilterPanel).vm.$emit('update:modelValue', values);
    await flush();
  }
  async function action(id: string, actionId: string) {
    await m.find(`staff-members-row-${id}-${actionId}`).trigger('click');
    await settle();
  }
  return { ...m, table, prop, rows, cells, list, show, showOnNewStream, filter, action };
}

describe('MembersPage: the live directory', () => {
  it('follows the members sorted by name, 50 from the first, «Loading…» until they come', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
    expect(s.find('staff-members-loading').exists()).toBe(true);
    await s.show(page(ROWS));
    expect(s.find('staff-members-loading').exists()).toBe(false);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'staff-members', total: 2, views: ['table', 'cards'] });
    expect(s.prop('searchPlaceholder')).toBe('Search member…');
    expect(s.prop('entityLabel')).toEqual({ one: 'staff member', many: 'staff members' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Staff');
  });

  it('paints Name, Role, Email, Status and, for whoever may see the pay, Rate/h; Phone starts hidden', async () => {
    const s = await setup();
    await s.result('staff.member.compensation', PAY);
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string; hidden?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.hidden])).toEqual([
      ['name', 'Name', false],
      ['role_name', 'Role', false],
      ['email', 'Email', false],
      ['phone', 'Phone', true],
      ['status', 'Status', false],
      ['hourly_rate', 'Rate/h', false],
    ]);
    expect(s.cells(0).slice(0, 5)).toEqual(['Ana López', 'Stylist', 'ana@example.com', 'Active', '€12.50']);
    expect(s.cells(1).slice(0, 5)).toEqual(['Bea Ruiz', '—', '—', 'Inactive', '—']);
  });

  it('follows the pay of exactly the rows on screen (same query, sort and windows), only for whoever may see it', async () => {
    const s = await setup();
    expect(s.params('staff.member.compensation')).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
    s.table().vm.$emit('update:search', 'ana');
    s.wrapper.findComponent(FilterPanel).vm.$emit('update:modelValue', { status: 'active' });
    await flush();
    s.table().vm.$emit('loadMore');
    await flush();
    s.table().vm.$emit('loadMore');
    await flush();
    await s.reopen();
    const windows = [
      { status: 'active', search: 'ana', sort: 'name', limit: 100, offset: 0 },
      { status: 'active', search: 'ana', sort: 'name', limit: 50, offset: 100 },
    ];
    expect(s.list()).toEqual(windows);
    expect(s.params('staff.member.compensation')).toEqual(windows);
    const employee = await setup({ session: EMPLOYEE });
    expect(employee.params('staff.member.compensation')).toEqual([]);
    await employee.show(page(ROWS));
    expect(employee.prop<Array<{ key: string }>>('columns').map((c) => c.key)).not.toContain('hourly_rate');
  });

  it('sorts on the server by any column but the pay; a descending sort goes with a «-»', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; sortable?: boolean }>>('columns').filter((c) => c.sortable).map((c) => c.key)).toEqual([
      'name',
      'role_name',
      'email',
      'phone',
      'status',
    ]);
    s.table().vm.$emit('sortChange', { sort: 'email', dir: 'desc' });
    await flush();
    expect(s.list()).toEqual([{ sort: '-email', limit: 50, offset: 0 }]);
  });

  it('searches on the server; no member at all says «No staff members.», a search that finds none «No results»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No staff members.');
    s.table().vm.$emit('update:search', ' ana ');
    await flush();
    expect(s.list()).toEqual([{ search: 'ana', sort: 'name', limit: 50, offset: 0 }]);
    await s.showOnNewStream(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('filters by the old columns: text, role, status, bookable as a yes/no, hire date from–to and Hub user', async () => {
    const s = await setup();
    type Spec = { key: string; label: string; kind: string; options?: unknown[]; load?: (search: string) => Promise<unknown> };
    const specs = s.wrapper.findComponent(FilterPanel).props('filters') as unknown as Spec[];
    expect(specs.map((f) => [f.key, f.label, f.kind])).toEqual([
      ['first_name', 'First name', 'text'],
      ['last_name', 'Last name', 'text'],
      ['email', 'Email', 'text'],
      ['phone', 'Phone', 'text'],
      ['role_name', 'Role', 'search'],
      ['status', 'Status', 'select'],
      ['is_bookable', 'Bookable', 'select'],
      ['hire_date', 'Hire date', 'range'],
      ['color', 'Color (#RRGGBB)', 'text'],
      ['user_id', 'Hub user', 'search'],
    ]);
    expect(specs.find((f) => f.key === 'status')?.options).toEqual([
      { value: 'active', label: 'Active' },
      { value: 'on_leave', label: 'On leave' },
      { value: 'inactive', label: 'Inactive' },
    ]);
    // Role and Hub user search the server (more than 100 may exist): every role by name, and the accounts.
    s.answerBy({ '/api/staff/roles': [200, ROLES], '/api/staff/accounts': [200, ACCOUNTS] });
    expect(await specs.find((f) => f.key === 'role_name')?.load?.('sty')).toEqual([{ value: 'Stylist', label: 'Stylist' }]);
    expect(await specs.find((f) => f.key === 'user_id')?.load?.('')).toEqual([{ value: '4', label: 'Ana López' }]);
    expect(s.sent().map((c) => [c.path, c.query])).toEqual([
      ['/api/staff/roles', { search: 'sty', sort: 'name', limit: '100' }],
      ['/api/staff/accounts', { limit: '100' }],
    ]);
    await s.filter({ status: 'on_leave', is_bookable: 'false', hire_date_from: '2024-01-01', user_id: '4', role_name: 'Stylist' });
    expect(s.list()).toEqual([
      { status: 'on_leave', is_bookable: false, hire_date_from: '2024-01-01', user_id: 4, role_name: 'Stylist', sort: 'name', limit: 50, offset: 0 },
    ]);
  });

  it('an employee has no Hub user filter (only who adds or edits may read the accounts)', async () => {
    const s = await setup({ session: EMPLOYEE });
    const specs = s.wrapper.findComponent(FilterPanel).props('filters') as unknown as Array<{ key: string }>;
    expect(specs.map((f) => f.key)).not.toContain('user_id');
  });

  it('«Load more» on a phone never asks the server for more than 100 rows: past 100, a second window', async () => {
    const s = await setup();
    await s.show(page(ROWS, 300));
    s.table().vm.$emit('loadMore');
    await flush();
    s.table().vm.$emit('loadMore');
    await flush();
    await s.reopen();
    expect(s.list()).toEqual([
      { sort: 'name', limit: 100, offset: 0 },
      { sort: 'name', limit: 50, offset: 100 },
    ]);
  });

  it('the server’s «app not active» replaces the list; another failure is the table’s, with «Retry»', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'app_inactive'));
    await flush();
    expect(s.find('staff-members-inactive').exists()).toBe(true);
    expect(s.table().exists()).toBe(false);
  });
});

describe('MembersPage: who may do what', () => {
  it('the owner adds, opens a row, and gets Edit, Deactivate and Terminate', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.prop('rowClickable')]).toEqual([true, true]);
    expect(s.prop<Array<{ id: string; icon: string }>>('actions').map((a) => [a.id, a.icon])).toEqual([
      ['edit', 'create-outline'],
      ['deactivate', 'ban-outline'],
      ['terminate', 'person-remove-outline'],
    ]);
    expect((s.wrapper.findComponent(AppPage).props('tabs') ?? []).map((t: { id: string }) => t.id)).toEqual(['staff', 'roles', 'time_off', 'schedules', 'settings']);
  });

  it('a manager adds and edits, but neither deactivates nor terminates', async () => {
    const s = await setup({ session: MANAGER });
    await s.show(page(ROWS));
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['edit']);
  });

  it('an employee only reads: no «+», no row to open, no action, no Settings tab', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.prop('rowClickable'), s.prop('actions')]).toEqual([false, false, []]);
    expect((s.wrapper.findComponent(AppPage).props('tabs') ?? []).map((t: { id: string }) => t.id)).toEqual(['staff', 'roles', 'time_off', 'schedules']);
  });
});

describe('MembersPage: the record and its lifecycle', () => {
  it('«+» opens «New»; a row opens «Edit · {name}» with that row', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const modal = () => s.wrapper.findComponent(MemberFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('member')]).toEqual([true, null]);
    modal().vm.$emit('update:open', false);
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect([modal().props('open'), modal().props('member')]).toEqual([true, ROWS[1]]);
  });

  it('«Deactivate» asks «Take {name} off the floor?…» and sends staff.member.deactivate', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answerBy({ '/api/staff/members/deactivate': [200, { ...ROWS[0], status: 'inactive' }] });
    await s.action('m1', 'deactivate');
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('open'), dialog.props('title'), dialog.props('message'), dialog.props('confirmLabel')]).toEqual([
      true,
      'Deactivate member',
      'Take Ana López off the floor? They stop being bookable; nothing is deleted.',
      'Deactivate',
    ]);
    dialog.vm.$emit('confirm');
    await settle();
    expect(s.sent().filter((c) => c.method === 'POST')).toEqual([{ method: 'POST', path: '/api/staff/members/deactivate', query: {}, body: { id: 'm1' } }]);
    expect(dialog.props('open')).toBe(false);
  });

  it('«Deactivate» is off for someone already inactive', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const deactivate = s.prop<Array<{ id: string; disabled?: (row: MemberOut) => boolean }>>('actions').find((a) => a.id === 'deactivate')!;
    expect(ROWS.map((row) => deactivate.disabled?.(row))).toEqual([false, true]);
  });

  it('a refused row action (live time off, 409) is said above the table', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const message = 'That member has pending or approved time off that has not ended. Resolve it first.';
    s.answer(409, { error: { code: 'staff.active_time_off', message } });
    await s.action('m1', 'deactivate');
    s.wrapper.findComponent(ConfirmDialog).vm.$emit('confirm');
    await settle();
    expect(s.find('staff-members-error').text()).toContain(message);
  });

  it('«Terminate» opens its dialog for that person', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    await s.action('m2', 'terminate');
    const dialog = s.wrapper.findComponent(TerminateDialog);
    expect([dialog.props('open'), dialog.props('member')]).toEqual([true, ROWS[1]]);
  });
});

describe('MembersPage: my record (STAFF-F08)', () => {
  const MINE = { member: { ...ROWS[0], booking_buffer: 0, specialties: '', bio: '', created_at: '', updated_at: '', hourly_rate: 900, commission_rate: '5.00' } as MemberMineOut };

  it('offers «My record» to whoever has a linked record, and opens it', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.params('staff.member.mine')).toEqual([{}]);
    expect(s.find('staff-members-mine').exists()).toBe(false);
    await s.result('staff.member.mine', MINE);
    await s.show(page(ROWS));
    await click(s.find('staff-members-mine').element);
    const modal = s.wrapper.findComponent(MyRecordModal);
    expect([modal.props('open'), modal.props('record')]).toEqual([true, MINE.member]);
  });

  it('without a linked record there is no «My record»', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.result('staff.member.mine', { member: null });
    await s.show(page(ROWS));
    expect(s.find('staff-members-mine').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Personal');
    expect(s.prop('searchPlaceholder')).toBe('Buscar miembro…');
    expect(s.cells(0)[3]).toBe('Activo');
  });
});

describe('MembersPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
