// Staff → Time Off (WORKBOOK «Pantallas · Ausencias»; STAFF-F08, F17–F20, F24): the live
// `staff.time_off.list` — Member, Type, From, To (with the hours of a part day) and Status, never the
// reason —, «Search member…», sort by any column (newest first), filters (member, type, status, full
// day, dates), 50 a page. Row actions where they apply: «Approve» and «Reject» a pending request and
// «Cancel» (confirmed) a pending or approved one, for whoever manages time off; an employee cancels
// only their own pending request. «+» registers anyone's (managers) or asks for one's own (employee).
// Whoever has a linked record switches to «My time off» (`staff.time_off.mine`, with the reason).
import { ConfirmDialog, DataTable, EmptyState, StatusPill } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { TimeOffDetailOut, TimeOffOut } from '../operations';
import { EMPLOYEE, errorFrame, flush, type MountOptions, mountStaff, page, settle } from '../__tests__/mount-staff';
import TimeOffFormModal from '../components/TimeOffFormModal.vue';
import TimeOffPage from './TimeOffPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'staff.time_off.list';
const off = (id: string, over: Partial<TimeOffOut> = {}): TimeOffOut => ({
  id,
  member_id: 'm1',
  member_name: 'Ana López',
  leave_type: 'vacation',
  start_date: '2026-11-02',
  end_date: '2026-11-06',
  is_full_day: true,
  start_time: null,
  end_time: null,
  status: 'pending',
  approved_by_id: null,
  approved_at: null,
  ...over,
});
const ROWS = [
  off('t1'),
  off('t2', { member_id: 'm2', member_name: 'Bea Ruiz', leave_type: 'personal', start_date: '2026-11-10', end_date: '2026-11-10', is_full_day: false, start_time: '09:00:00', end_time: '13:00:00', status: 'approved' }),
  off('t3', { status: 'rejected' }),
];
const MINE = { member: { id: 'm2', full_name: 'Bea Ruiz' } };

async function setup(options: MountOptions = {}) {
  const m = await mountStaff(TimeOffPage, { path: '/staff/time-off', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="staff-time-off-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  type Action = { id: string; hidden?: (row: TimeOffOut) => boolean };
  /** The actions a row shows. */
  const shownActions = (row: TimeOffOut) => prop<Action[]>('actions').filter((a) => !a.hidden?.(row)).map((a) => a.id);
  async function action(id: string, actionId: string) {
    await m.find(`staff-time-off-row-${id}-${actionId}`).trigger('click');
    await settle();
  }
  return { ...m, table, prop, rows, cells, shownActions, action, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('TimeOffPage: the live list', () => {
  it('follows the requests, newest first, 50 from the first', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: '-start_date', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'staff-time-off', total: 3, sort: 'start_date', sortDir: 'desc' });
    expect(s.prop('searchPlaceholder')).toBe('Search member…');
  });

  it('paints Member, Type, From, To and Status; a part day with its hours; never the reason', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['member_name', 'Member'],
      ['leave_type', 'Type'],
      ['start_date', 'From'],
      ['end_date', 'To'],
      ['status', 'Status'],
    ]);
    expect(s.cells(0).slice(0, 5)).toEqual(['Ana López', 'Vacation', '11/02/2026', '11/06/2026', 'Pending']);
    expect(s.cells(1).slice(0, 5)).toEqual(['Bea Ruiz', 'Personal', '11/10/2026 09:00', '11/10/2026 13:00', 'Approved']);
    expect(s.wrapper.findAllComponents(StatusPill).map((p) => p.props('tone'))).toEqual(['warning', 'success', 'danger']);
  });

  it('an approval elsewhere repaints the row as it comes, without reloading', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    await s.result(OP, page([{ ...ROWS[0], status: 'approved' }, ...ROWS.slice(1)]), {}, 2);
    expect(s.cells(0)[4]).toBe('Approved');
  });

  it('searches and sorts on the server; no request at all says «No time-off requests.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No time-off requests.');
    s.table().vm.$emit('sortChange', { sort: 'member_name', dir: 'asc' });
    s.table().vm.$emit('update:search', 'bea');
    await flush();
    expect(s.list()).toEqual([{ search: 'bea', sort: 'member_name', limit: 50, offset: 0 }]);
  });

  it('filters behind the table funnel: member (searched), type and status on their columns, then full day as a yes/no and dates', async () => {
    // flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop('filterable')).toBe(true);
    type Filter = { type: string; key?: string; keys?: string[]; options?: Array<{ value: string }>; load?: (query: string) => Promise<unknown> };
    const columns = s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.label, c.filter?.key ?? c.key, c.filter?.type])).toEqual([
      ['Member', 'member_id', 'lookup'],
      ['Type', 'leave_type', 'select'],
      ['Status', 'status', 'select'],
    ]);
    expect(columns.find((c) => c.key === 'status')?.filter?.options?.map((o) => o.value)).toEqual(['pending', 'approved', 'rejected', 'cancelled']);
    const fields = s.prop<Array<Filter & { key: string; label: string }>>('filterFields');
    expect(fields.map((f) => [f.key, f.label, f.type, f.keys])).toEqual([
      ['is_full_day', 'Full day', 'boolean', undefined],
      ['dates', 'Dates', 'daterange', ['date_from', 'date_to']],
    ]);
    s.table().vm.$emit('update:filters', { status: 'pending', is_full_day: 'true', date_from: '2026-11-01', member_id: 'm1' });
    await flush();
    expect(s.list()).toEqual([{ status: 'pending', is_full_day: true, date_from: '2026-11-01', member_id: 'm1', sort: '-start_date', limit: 50, offset: 0 }]);
    expect(s.find('staff-time-off-filters-count').text()).toBe('4');
  });

  it('«My time off» has no filters: no funnel, no filter on any column', async () => {
    const s = await setup();
    await s.result('staff.member.mine', MINE);
    s.find('staff-time-off-whose').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'mine' } }));
    await flush();
    expect(s.prop<Array<{ filter?: unknown }>>('columns').some((c) => c.filter)).toBe(false);
    expect(s.prop('filterFields')).toEqual([]);
    expect(s.find('staff-time-off-filters-toggle').exists()).toBe(false);
  });
});

describe('TimeOffPage: approve, reject and cancel (STAFF-F18, F19)', () => {
  it('a manager approves or rejects a pending request and cancels a pending or approved one', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(ROWS.map(s.shownActions)).toEqual([['approve', 'reject', 'cancel'], ['cancel'], []]);
  });

  it('«Approve» sends staff.time_off.approve; a refusal (an approved overlap) is said above the table', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, {});
    await s.action('t1', 'approve');
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/time_off/approve', query: {}, body: { id: 't1' } }]);
    const message = 'That member already has approved time off on those dates.';
    s.answer(409, { error: { code: 'staff.overlapping_time_off', message } });
    await s.action('t1', 'reject');
    expect(s.sent().at(-1)?.path).toBe('/api/staff/time_off/reject');
    expect(s.find('staff-time-off-error').text()).toContain(message);
  });

  it('«Cancel» asks first, naming the person and the dates, and sends staff.time_off.cancel', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, {});
    await s.action('t2', 'cancel');
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('open'), dialog.props('title'), dialog.props('message'), dialog.props('confirmLabel'), dialog.props('cancelLabel')]).toEqual([
      true,
      'Cancel time off',
      'Cancel the time off of Bea Ruiz from 11/10/2026 to 11/10/2026? It cannot be undone.',
      'Cancel time off',
      'Keep it',
    ]);
    dialog.vm.$emit('confirm');
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/time_off/cancel', query: {}, body: { id: 't2' } }]);
  });

  it('an employee only cancels their own pending request', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.result('staff.member.mine', MINE);
    const own = off('t9', { member_id: 'm2', member_name: 'Bea Ruiz' });
    await s.show(page([...ROWS, own]));
    expect([...ROWS, own].map(s.shownActions)).toEqual([[], [], [], ['cancel']]);
  });
});

describe('TimeOffPage: «+» and «My time off» (STAFF-F08, F17, F24)', () => {
  it('«+» registers anyone’s for a manager, and asks for one’s own for an employee', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('add');
    await flush();
    expect([s.wrapper.findComponent(TimeOffFormModal).props('open'), s.wrapper.findComponent(TimeOffFormModal).props('mode')]).toEqual([true, 'create']);
    const e = await setup({ session: EMPLOYEE });
    await e.show(page(ROWS));
    expect(e.prop('addable')).toBe(true);
    e.table().vm.$emit('add');
    await flush();
    expect(e.wrapper.findComponent(TimeOffFormModal).props('mode')).toBe('request');
  });

  it('whoever has a linked record switches to «My time off», with its reason', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.find('staff-time-off-whose').exists()).toBe(false);
    await s.result('staff.member.mine', MINE);
    expect(s.find('staff-time-off-whose').exists()).toBe(true);
    s.find('staff-time-off-whose').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'mine' } }));
    await flush();
    await s.reopen();
    expect(s.params('staff.time_off.mine')).toEqual([{ limit: 50, offset: 0 }]);
    const mine: TimeOffDetailOut = { ...off('t9', { member_id: 'm2', member_name: 'Bea Ruiz' }), reason: 'Wedding', notes: '', approved_by_name: null, created_at: '' };
    await s.result('staff.time_off.mine', page([mine]));
    expect(s.prop<Array<{ key: string }>>('columns').map((c) => c.key)).toEqual(['member_name', 'leave_type', 'start_date', 'end_date', 'status', 'reason']);
    expect(s.cells(0)[5]).toBe('Wedding');
    expect(s.prop('searchable')).toBe(false);
  });

  it('«My time off» does not sort (the server gives it in its own order), drops the search, and says when it is empty', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.result('staff.member.mine', MINE);
    s.table().vm.$emit('update:search', 'zzz');
    await flush();
    s.find('staff-time-off-whose').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'mine' } }));
    await flush();
    await s.reopen();
    await s.result('staff.time_off.mine', page([]));
    expect(s.prop<Array<{ sortable?: boolean }>>('columns').some((c) => c.sortable)).toBe(false);
    expect([s.prop('sort'), s.prop('search')]).toEqual([undefined, '']);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No time-off requests.');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.cells(0).slice(1, 5)).toEqual(['Vacaciones', '02/11/2026', '06/11/2026', 'Pendiente']);
  });
});

describe('TimeOffPage: today’s time off (STAFF-G05, STAFF-F20)', () => {
  it('lists who is away today above the list, also for an employee', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.params('staff.time_off.today')).toEqual([{ limit: 100 }]);
    const card = s.find('staff-away-today');
    expect(card.exists()).toBe(true);
    expect(card.element.compareDocumentPosition(s.table().element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('goes away with the list when the app is not active here', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'app_inactive'));
    await flush();
    expect(s.find('staff-away-today').exists()).toBe(false);
  });
});

describe('TimeOffPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
