// Tips → Tips (TIP-F03 to TIP-F06; WORKBOOK «Pantallas · Propinas»): the tips of the period — Today to begin with, 7 or
// 30 days, counted from the business day — live and newest first in a server-side DataTable: Date, Sale, For, Payment
// method, Amount and Status, «Search sale or person…», filters by person, payment and status, table or cards and 50 a
// page. «Record tip» opens its window; an active tip offers «Adjust» and «Void», a voided one nothing. Every state of
// the screen: loading, empty, no results, error, reconnecting and app inactive.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { offeredRowActions, pressRowAction } from '@erplora/ui/testing/data-table';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { errorFrame, flush, words } from '../../../../base/frontend/__tests__/mount-in-shell';
import { EMPLOYEE, MANAGER, mountTip, onTheTwentyFifth } from '../__tests__/mount-tip';
import TipAdjustModal from '../components/TipAdjustModal.vue';
import TipFormModal from '../components/TipFormModal.vue';
import TipVoidModal from '../components/TipVoidModal.vue';
import type { TipOut } from '../operations';
import TipsPage from './TipsPage.vue';

const OP = 'tip.tip.list';
const TODAY = { date_from: '2026-11-25', date_to: '2026-11-25' };

const tip = (id: string, fields: Partial<TipOut> = {}): TipOut =>
  ({
    id,
    sale_id: 's1',
    sale_number: '20261125-0007',
    pool: false,
    member_id: 'm-bea',
    member_name: 'Bea Gil',
    method_id: 'm-card',
    method_name: 'Card',
    method_type: 'card',
    amount: 250,
    status: 'active',
    created_at: '2026-11-25T12:30:00Z',
    ...fields,
  }) as TipOut;

const ROWS = [
  tip('t1'),
  tip('t2', { sale_id: null, sale_number: '', pool: true, member_id: null, member_name: '', method_name: 'Cash', method_type: 'cash', amount: 1200 }),
  tip('t3', { status: 'voided' }),
];
const PAGE = { rows: ROWS, total: 3, limit: 50, offset: 0 };
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };

onTheTwentyFifth();

async function setup(locale: 'en' | 'es' = 'en', session = MANAGER) {
  const m = await mountTip(TipsPage, { path: '/tip/tips', locale, session });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="tip-list-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((cell) => words(cell.element));
  const show = (page: unknown) => m.result(OP, page, { offset: 0 });
  async function changed() {
    await flush();
    await m.reopen();
  }
  async function emit(event: string, ...args: unknown[]) {
    table().vm.$emit(event, ...args);
    await changed();
  }
  async function period(value: string) {
    m.find('tip-list-period').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await changed();
  }
  return { ...m, table, prop, rows, cells, show, emit, period };
}

describe('TipsPage: the list', () => {
  it('sits under «Tips» with the tabs its menu opens', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect([page.props('title'), page.props('tabsLabel')]).toEqual(['Tips', 'Tips sections']);
    expect((page.props('tabs') as Array<{ to: string }>).map((tab) => tab.to)).toEqual(['/tip/tips', '/tip/report', '/tip/settings', '/tip/mine']);
  });

  it('follows today’s tips, 50 from the first, «Loading tips…» until the first result', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ ...TODAY, limit: 50, offset: 0 }]);
    expect(s.find('tip-list-loading').text()).toContain('Loading tips…');
    await s.show(PAGE);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'tip-list', pageSize: 50, total: 3, views: ['table', 'cards'] });
    expect([s.prop('searchPlaceholder'), s.prop('entityLabel')]).toEqual(['Search sale or person…', { one: 'tip', many: 'tips' }]);
  });

  it('paints Date, Sale, For, Payment method, Amount and Status; the pool and the unassigned say so', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ label: string }>>('columns').map((column) => column.label)).toEqual(['Date', 'Sale', 'For', 'Payment method', 'Amount', 'Status']);
    expect(s.cells(0).slice(1, 6)).toEqual(['20261125-0007', 'Bea Gil', 'Card', '€2.50', 'Active']);
    expect(s.cells(1).slice(1, 6)).toEqual(['To the pool', 'Unassigned', 'Cash', '€12.00', 'Active']);
    expect(s.cells(2)[5]).toBe('Voided');
    expect(s.prop<(row: TipOut) => string>('cardTitle')(ROWS[1])).toBe('To the pool');
  });

  it('counts the period back from today: 7 days, 30 days', async () => {
    const s = await setup();
    await s.period('week');
    expect(s.params(OP)).toEqual([{ date_from: '2026-11-19', date_to: '2026-11-25', limit: 50, offset: 0 }]);
    await s.period('month');
    expect(s.params(OP)).toEqual([{ date_from: '2026-10-27', date_to: '2026-11-25', limit: 50, offset: 0 }]);
  });

  it('searches and filters by person, payment and status on the server', async () => {
    const s = await setup();
    await s.emit('update:search', ' bea ');
    await s.emit('update:filters', { member_id: 'm-bea', method_type: 'cash', status: 'voided' });
    expect(s.params(OP)).toEqual([{ ...TODAY, search: 'bea', member_id: 'm-bea', method_type: 'cash', status: 'voided', limit: 50, offset: 0 }]);
  });

  it('says «There are no tips yet.» with nothing, and «No tips match» when searched or filtered', async () => {
    const s = await setup();
    await s.show(EMPTY);
    const heading = () => (s.wrapper.findComponent(EmptyState as unknown as Component).props() as Record<string, unknown>).heading;
    expect(heading()).toBe('There are no tips yet.');
    await s.emit('update:search', 'zz');
    await s.show(EMPTY);
    expect(heading()).toBe('No tips match');
  });

  it('a read that fails is the table’s error; reconnecting and an app turned off are said above it', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'tip.boom'));
    await flush();
    expect(s.prop('error')).toBe('msg tip.boom');
    expect(s.prop<{ loadError: string }>('labels').loadError).toBe('The tips could not be loaded.');
    s.net.lastStream().push(errorFrame(s.subId(OP), 'app_inactive'));
    await flush();
    expect(s.find('tip-list-inactive').exists()).toBe(true);
    expect(s.table().exists()).toBe(false);
  });
});

describe('TipsPage: what can be done', () => {
  it('an active tip offers «Adjust» and «Void»; a voided one, nothing', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(offeredRowActions(s.wrapper, 't1')).toEqual(['adjust', 'void']);
    expect(offeredRowActions(s.wrapper, 't3')).toEqual([]);
  });

  it('«Record tip», «Adjust» and «Void» open their windows on the tip of the row', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop('addable')).toBe(true);
    expect(s.prop<{ add: string }>('labels').add).toBe('Record tip');
    await s.emit('add');
    expect(s.wrapper.findComponent(TipFormModal).props('open')).toBe(true);
    await pressRowAction(s.wrapper, 't1', 'adjust');
    await flush();
    expect(s.wrapper.findComponent(TipAdjustModal).props()).toMatchObject({ open: true, tip: ROWS[0] });
    await pressRowAction(s.wrapper, 't2', 'void');
    await flush();
    expect(s.wrapper.findComponent(TipVoidModal).props()).toMatchObject({ open: true, tip: ROWS[1] });
  });

  it('whoever only records tips is offered neither «Adjust» nor «Void»; whoever only reads them, no «Record tip» either', async () => {
    const records = await setup('en', EMPLOYEE);
    await records.show(PAGE);
    expect(records.prop('addable')).toBe(true);
    expect(offeredRowActions(records.wrapper, 't1')).toEqual([]);
    const reads = await setup('en', { ...EMPLOYEE, permissions: EMPLOYEE.permissions.filter((held) => held !== 'tip.add_tip') });
    await reads.show(PAGE);
    expect(reads.prop('addable')).toBe(false);
    expect(offeredRowActions(reads.wrapper, 't1')).toEqual([]);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.show(PAGE);
    expect(s.prop<Array<{ label: string }>>('columns').map((column) => column.label)).toEqual(['Fecha', 'Venta', 'Para', 'Forma de pago', 'Importe', 'Estado']);
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Buscar venta o persona…', 'Anotar propina']);
    expect(s.cells(1)[1]).toBe('Al bote');
  });
});
