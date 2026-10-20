// Cash register → the sessions (WORKBOOK «Pantallas · Caja»; the old `erp-cashregister-dashboard`): the title
// «Cash register» and «Open session» (off while a session is open, saying why), the live
// `cash_register.session.list` newest first in a server-side DataTable — Session, Opened on, Status,
// Opening, Expected, Counted, Difference — with search, the filters behind the table's funnel, table or
// cards and 50 a page. «Detail»
// on every row (the row opens it too) and, on the open session, «Movement», «Count» and «Close», each by
// its permission. A closing count opens the close. The drawer charged with no session open is said, and
// so is a forgotten session past its cut-off. Nothing here refetches: it all re-runs by itself.
import { DataTable } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, errorFrame, flush, type MountOptions, mountCash, words } from '../__tests__/mount-cash-register';
import CashFigures from '../components/CashFigures.vue';
import CloseSessionModal from '../components/CloseSessionModal.vue';
import CountModal from '../components/CountModal.vue';
import MovementModal from '../components/MovementModal.vue';
import OpenSessionModal from '../components/OpenSessionModal.vue';
import UnassignedModal from '../components/UnassignedModal.vue';
import type { SessionRow } from '../operations';
import SessionsPage from './SessionsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const LIST = 'cash_register.session.list';
const CURRENT = 'cash_register.session.current';

const row = (id: string, over: Partial<SessionRow> = {}): SessionRow => ({
  id,
  number: `S-261014-000${id.slice(1)}`,
  business_day: '2026-10-14',
  status: 'closed',
  register_id: null,
  register_name: '',
  opened_at: '2026-10-14T08:00:00Z',
  opened_by: 'ana',
  opening_balance: 10000,
  closed_at: '2026-10-14T20:00:00Z',
  closed_by: 'ana',
  closing_balance: 9950,
  expected_balance: 10000,
  difference: -50,
  auto_closed: false,
  expected_hidden: false,
  auto_close_due: false,
  ...over,
});
const OPEN = row('s2', { status: 'open', closed_at: null, closed_by: '', closing_balance: null, difference: null, expected_balance: 10300 });
const CLOSED = row('s1');
const PAGE = { rows: [OPEN, CLOSED], total: 2, limit: 50, offset: 0 };
const NONE = { required: true, session: null, auto_close_at: null, unassigned_count: 0, unassigned_cash: 0 };

async function setup(options: MountOptions = {}) {
  const m = await mountCash(SessionsPage, { path: '/cash_register/sessions', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const rows = () => m.wrapper.findAll('[data-testid="cash-register-sessions-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => words(c.element));
  const action = async (id: string, actionId: string) => {
    await m.find(`cash-register-sessions-row-${id}-${actionId}`).trigger('click');
    await flush();
  };
  /** The table's subscriptions to the list (the figures above it read the closed ones apart: no offset). */
  const tableParams = () => m.params(LIST).filter((params) => 'offset' in params);
  const ready = async (current: unknown = { ...NONE, session: OPEN }, page: unknown = PAGE) => {
    await m.result(CURRENT, current);
    await m.result(LIST, page, { offset: 0 });
  };
  return { ...m, table, rows, cells, action, ready, tableParams };
}

describe('SessionsPage: the screen', () => {
  it('shows the drawer\'s figures above the sessions (CASH_REGISTER-F12)', async () => {
    const s = await setup();
    await s.ready();
    const figures = s.wrapper.findComponent(CashFigures);
    expect(figures.exists()).toBe(true);
    const table = s.table().element;
    expect(figures.element.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('is «Cash register», with its tabs and «Open session»', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Cash register');
    expect((page.props('tabs') as Array<{ id: string }>).map((tab) => tab.id)).toEqual(['sessions', 'settings']);
    expect(s.find('cash-register-sessions-title').text()).toBe('Cash register');
    expect(s.find('cash-register-new-session').text()).toBe('Open session');
  });

  it('follows the sessions newest first, 50 from the first, and the open one', async () => {
    const s = await setup();
    expect(s.tableParams()).toEqual([{ sort: 'opened_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.params(CURRENT)).toEqual([{}]);
    await s.ready();
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, total: 2, pageSize: 50, rowClickable: true });
    expect([s.cells(0)[0], ...s.cells(0).slice(2, 7)]).toEqual(['S-261014-0002', 'Open', '€100.00', '€103.00', '—', '—']);
    expect(s.cells(1).slice(2, 7)).toEqual(['Closed', '€100.00', '€100.00', '€99.50', '-€0.50']);
  });

  it('a blind count leaves the open session’s expected empty', async () => {
    const s = await setup();
    await s.ready({ ...NONE, session: OPEN }, { ...PAGE, rows: [{ ...OPEN, expected_balance: null, expected_hidden: true }] });
    expect(s.cells(0)[4]).toBe('—');
  });

  it('«Open session» is off while a session is open, saying why; on with the drawer closed', async () => {
    const s = await setup();
    await s.ready();
    const disabled = () => (s.find('cash-register-new-session').element as HTMLElement & { disabled?: boolean }).disabled;
    expect(disabled()).toBe(true);
    expect(s.find('cash-register-new-session').attributes('title')).toBe('There is already an open cash session. Close it before opening another one.');
    await s.result(CURRENT, NONE);
    expect(disabled()).toBe(false);
    await s.find('cash-register-new-session').trigger('click');
    await flush();
    expect(s.wrapper.findComponent(OpenSessionModal).props('open')).toBe(true);
  });

  it('a forgotten session past its cut-off is said, and «Open session» closes it by opening the next', async () => {
    const s = await setup();
    await s.ready({ ...NONE, session: { ...OPEN, auto_close_due: true }, auto_close_at: '2026-10-14T02:00:00Z' });
    expect(s.find('cash-register-auto-close-due').text()).toContain('Session S-261014-0002 was due to close by itself');
    expect((s.find('cash-register-new-session').element as HTMLElement & { disabled?: boolean }).disabled).toBe(false);
  });

  it('says what was charged with the drawer closed and lists it', async () => {
    const s = await setup();
    await s.ready({ ...NONE, unassigned_count: 2, unassigned_cash: 300 });
    expect(words(s.find('cash-register-unassigned').element)).toContain('Sale lines in no shift 2 sale lines fell in no session · €3.00 in cash.');
    await s.find('cash-register-unassigned-view').trigger('click');
    await flush();
    expect(s.wrapper.findComponent(UnassignedModal).props('open')).toBe(true);
    expect(s.wrapper.findComponent(OpenSessionModal).props('unassignedCash')).toBe(300);
  });
});

describe('SessionsPage: the filters behind the table funnel (FIX-DATATABLE-HUB-FILTERS-2B)', () => {
  // flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
  type Filter = { type: string; key?: string; keys?: string[]; amount?: boolean; maxlength?: number; options?: Array<{ value: string; label: string }> };
  const prop = <T,>(s: Awaited<ReturnType<typeof setup>>, name: string) => (s.table().props() as Record<string, unknown>)[name] as T;

  it('Session, Status and the four amounts filter on their own columns, the amounts typed in euros', async () => {
    const s = await setup();
    await s.ready();
    expect(prop(s, 'filterable')).toBe(true);
    const columns = prop<Array<{ key: string; label: string; filter?: Filter }>>(s, 'columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.label, c.filter?.key ?? c.key, c.filter?.type, c.filter?.keys, c.filter?.amount, c.filter?.maxlength])).toEqual([
      ['Session', 'number', 'text', undefined, undefined, 24],
      ['Status', 'status', 'select', undefined, undefined, undefined],
      ['Opening', 'opening_balance', 'range', ['opening_min', 'opening_max'], true, undefined],
      ['Expected', 'expected_balance', 'range', ['expected_min', 'expected_max'], true, undefined],
      ['Counted', 'closing_balance', 'range', ['counted_min', 'counted_max'], true, undefined],
      ['Difference', 'difference', 'range', ['difference_min', 'difference_max'], true, undefined],
    ]);
    expect(columns.find((c) => c.key === 'status')?.filter?.options).toEqual([
      { value: 'open', label: 'Open' },
      { value: 'closed', label: 'Closed' },
    ]);
    expect(prop(s, 'filterFields') ?? []).toEqual([]);
  });

  it('the funnel panel applies on «Apply»: every filter, euros into cents, a short difference, and counts them', async () => {
    const s = await setup();
    await s.ready();
    await s.find('cash-register-sessions-filters-toggle').trigger('click');
    await flush();
    const panel = s.find('cash-register-sessions-filters-panel');
    const set = (name: string, event: string, value: string) =>
      panel.get(`[data-testid="cash-register-sessions-filter-${name}"]`).element.dispatchEvent(new CustomEvent(event, { detail: { value } }));
    set('number', 'ionInput', 'S-261014-0001');
    set('status', 'ionChange', 'closed');
    set('opening_min', 'ionInput', '100');
    set('opening_max', 'ionInput', '200');
    set('expected_min', 'ionInput', '50');
    set('expected_max', 'ionInput', '1.250,50');
    set('counted_min', 'ionInput', '0,5');
    set('counted_max', 'ionInput', '300');
    set('difference_min', 'ionInput', '-5');
    set('difference_max', 'ionInput', '-0,01');
    await flush();
    await s.reopen();
    expect(s.tableParams(), 'the panel edits a draft: nothing is asked before «Apply»').toEqual([{ sort: 'opened_at', dir: 'desc', limit: 50, offset: 0 }]);
    await panel.get('[data-testid="cash-register-sessions-filters-apply"]').trigger('click');
    await flush();
    await s.reopen();
    expect(s.tableParams()).toEqual([
      {
        number: 'S-261014-0001',
        status: 'closed',
        opening_min: 10000,
        opening_max: 20000,
        expected_min: 5000,
        expected_max: 125050,
        counted_min: 50,
        counted_max: 30000,
        difference_min: -500,
        difference_max: -1,
        sort: 'opened_at',
        dir: 'desc',
        limit: 50,
        offset: 0,
      },
    ]);
    expect(s.find('cash-register-sessions-filters-count').text()).toBe('6');
  });

  it('an amount it cannot read is said under its field, in both languages, and neither filters nor narrows the list', async () => {
    const s = await setup();
    await s.ready();
    expect(prop(s, 'filterErrors')).toEqual({});
    s.table().vm.$emit('update:filters', { status: 'open', counted_min: 'abc' });
    await flush();
    await s.reopen();
    expect(prop(s, 'filterErrors')).toEqual({ counted_min: 'This is not an amount.' });
    expect(s.tableParams()).toEqual([{ status: 'open', sort: 'opened_at', dir: 'desc', limit: 50, offset: 0 }]);
    s.table().vm.$emit('update:filters', { counted_min: 'abc' });
    await flush();
    await s.reopen();
    await s.result(LIST, { rows: [], total: 0, limit: 50, offset: 0 }, { offset: 0 });
    expect(s.find('cash-register-sessions-empty').text()).toContain('No cash sessions.');
    const es = await setup({ locale: 'es' });
    await es.ready();
    es.table().vm.$emit('update:filters', { difference_max: 'x' });
    await flush();
    expect(prop(es, 'filterErrors')).toEqual({ difference_max: 'Esto no es un importe.' });
  });

  it('a filter the server refuses (422) goes under its filter; the rows stay and no error replaces them', async () => {
    const s = await setup();
    await s.ready();
    s.table().vm.$emit('update:filters', { opening_max: '99999999' });
    await flush();
    await s.reopen();
    await s.result(LIST, PAGE, { opening_max: 9999999900 });
    const refused = { code: 'invalid_payload', message: 'Some fields are not valid.', fields: { opening_max: 'Ensure this value is less than or equal to 9999999999.' } };
    s.net.lastStream().push(`event: error\ndata: ${JSON.stringify({ id: s.subId(LIST, { opening_max: 9999999900 }), error: refused })}\n\n`);
    await flush();
    expect(prop(s, 'filterErrors')).toEqual({ opening_max: 'Ensure this value is less than or equal to 9999999999.' });
    expect(prop(s, 'error')).toBeUndefined();
    expect(s.rows()).toHaveLength(2);
  });
});

describe('SessionsPage: the actions', () => {
  it('«Detail» on every row; «Movement», «Count» and «Close» only on the open one', async () => {
    const s = await setup();
    await s.ready();
    for (const id of ['detail', 'movement', 'count', 'close']) expect(s.find(`cash-register-sessions-row-s2-${id}`).exists(), id).toBe(true);
    expect(s.find('cash-register-sessions-row-s1-detail').exists()).toBe(true);
    for (const id of ['movement', 'count', 'close']) expect(s.find(`cash-register-sessions-row-s1-${id}`).exists(), id).toBe(false);
  });

  it('a session past its cut-off takes nothing more: only «Detail»', async () => {
    const s = await setup();
    const due = { ...OPEN, auto_close_due: true };
    await s.ready({ ...NONE, session: due, auto_close_at: '2026-10-14T02:00:00Z' }, { ...PAGE, rows: [due, CLOSED] });
    expect(s.find('cash-register-sessions-row-s2-detail').exists()).toBe(true);
    for (const id of ['movement', 'count', 'close']) expect(s.find(`cash-register-sessions-row-s2-${id}`).exists(), id).toBe(false);
  });

  it('opens the movement, the count and the close of the open session', async () => {
    const s = await setup();
    await s.ready();
    await s.action('s2', 'movement');
    expect(s.wrapper.findComponent(MovementModal).props()).toMatchObject({ open: true, session: OPEN });
    await s.action('s2', 'count');
    expect(s.wrapper.findComponent(CountModal).props()).toMatchObject({ open: true, session: OPEN });
    await s.action('s2', 'close');
    expect(s.wrapper.findComponent(CloseSessionModal).props()).toMatchObject({ open: true, session: OPEN });
  });

  it('a closing count opens the close of its session; an opening one does not', async () => {
    const s = await setup();
    await s.ready();
    await s.action('s2', 'count');
    s.wrapper.findComponent(CountModal).vm.$emit('counted', { type: 'opening', total: 100 });
    await flush();
    expect(s.wrapper.findComponent(CloseSessionModal).props('open')).toBe(false);
    s.wrapper.findComponent(CountModal).vm.$emit('counted', { type: 'closing', total: 100 });
    await flush();
    expect(s.wrapper.findComponent(CloseSessionModal).props()).toMatchObject({ open: true, session: OPEN });
  });

  it('«Detail» and a tap on the row open the session’s detail', async () => {
    const s = await setup();
    await s.ready();
    await s.action('s1', 'detail');
    expect(s.router.currentRoute.value.path).toBe('/cash_register/sessions/s1');
    s.table().vm.$emit('rowClick', OPEN);
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/cash_register/sessions/s2');
  });

  it('whoever may not open sees no «Open session»', async () => {
    const s = await setup({ session: { ...EMPLOYEE, permissions: EMPLOYEE.permissions.filter((p) => p !== 'cash_register.add_session') } });
    await s.ready();
    expect(s.find('cash-register-new-session').exists()).toBe(false);
  });
});

describe('SessionsPage: states', () => {
  it('empty says «No cash sessions.»', async () => {
    const s = await setup();
    await s.ready(NONE, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.find('cash-register-sessions-empty').text()).toContain('No cash sessions.');
  });

  it('the app off here replaces the list with a notice', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(LIST, { offset: 0 }), 'app_inactive'));
    await flush();
    expect(s.find('cash-register-sessions-inactive').text()).toContain('Cash register is not active in this business.');
    expect(s.table().exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.ready();
    expect(s.find('cash-register-new-session').text()).toBe('Abrir sesión');
    expect(s.cells(1)[2]).toBe('Cerrada');
  });
});

describe('SessionsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
