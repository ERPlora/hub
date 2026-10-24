// Sales & POS → Sales (SALE-F28–F31; the old `erp-sales-list`): the title «Sales», the period (Today to
// begin with, 7 days, 30 days, All) counted from the hub's business day, the six figures of the period
// (only for whoever may see the reports), and the live `sale.sale.list` in a server-side DataTable —
// Date, Number, Customer, Payment, Status («<amount> left to refund» under a sale partly refunded),
// Total —, search «Search number or customer…», the filters behind the table's funnel, table or cards, 50 a page. A row opens its
// document; «Document» and «Reprint» for everyone, «Void» and «Refund» too, only where they apply (whoever
// may not, with a manager's approval: the windows ask it). The list re-runs by itself on charges, voids and refunds: nothing here refetches.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage, toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { BYE, EMPLOYEE, errorFrame, flush, type MountOptions, mountSale } from '../__tests__/mount-sale';
import DocumentModal from '../components/document/DocumentModal.vue';
import ReprintJob from '../components/document/ReprintJob.vue';
import RefundModal from '../components/sales/RefundModal.vue';
import SalesKpis from '../components/sales/SalesKpis.vue';
import VoidSaleModal from '../components/sales/VoidSaleModal.vue';
import { formatDateTime } from '@erplora/ui/components';
import { plain } from '../lib/format';
import type { SaleRow } from '../operations';
import SalesWeek from '../components/sales/SalesWeek.vue';
import SalesPage from './SalesPage.vue';
import source from './SalesPage.vue?raw';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'sale.sale.list';

/** What a person reads in `el`: its texts in order, one space apart. */
function words(el: Element): string {
  const out: string[] = [];
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = plain(node.textContent ?? '').replace(/\s+/g, ' ').trim();
    if (text) out.push(text);
  }
  return out.join(' ');
}
const TODAY = { date_from: '2026-10-14', date_to: '2026-10-14' };

const row = (id: string, over: Partial<SaleRow> = {}): SaleRow => ({
  id,
  number: `20261014-000${id.slice(1)}`,
  business_day: '2026-10-14',
  created_at: '2026-10-14T10:05:00Z',
  status: 'completed',
  document_type: 'ticket',
  customer_id: null,
  customer_name: '',
  payment_method_name: 'Cash',
  staff_id: null,
  total: 1250,
  tax_total: 114,
  refunded_total: 0,
  refundable_total: 1250,
  sessions_to_return: 0,
  has_refunds: false,
  invoice_status: 'issued',
  documents_pending: false,
  ...over,
});

const ROWS = [
  row('s1', { customer_name: 'Lucía Pérez' }),
  row('s2', { status: 'voided', refundable_total: 0, payment_method_name: 'Card' }),
  row('s3', { status: 'refunded', refunded_total: 1250, refundable_total: 0, has_refunds: true }),
  row('s4', { refunded_total: 750, refundable_total: 500, has_refunds: true }),
  row('s5', { document_type: 'invoice' }),
];
const PAGE = { rows: ROWS, total: 5, limit: 50, offset: 0 };
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 14, 9, 0));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.mocked(toastError).mockClear();
  vi.mocked(toastSuccess).mockClear();
});

async function setup(options: MountOptions = {}) {
  const m = await mountSale(SalesPage, { path: '/sale/sales', ...options });
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="sales-table-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => words(c.element));
  /** A period chip's text, from its markup (happy-dom reads an upgraded Ionic element's text as empty). */
  const chip = (p: string) => m.find(`sales-range-${p}`).element.innerHTML.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  /** The list's params (one window but after «Load more»). */
  const list = () => m.params(OP);
  async function show(page: unknown) {
    await m.result(OP, page, { offset: 0 });
  }
  async function showOnNewStream(page: unknown) {
    await m.reopen();
    await show(page);
  }
  /** Picks a period, as `ion-segment` says it (`ionChange` with the value). */
  async function period(value: string) {
    m.find('sales-range').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
    await m.reopen();
  }
  /** What the table's funnel applies (`v-model:filters`): the filters by name, as typed. */
  async function filter(values: Record<string, string>) {
    table().vm.$emit('update:filters', values);
    await flush();
    await m.reopen();
  }
  async function action(id: string, actionId: string) {
    await m.find(`sales-table-row-${id}-${actionId}`).trigger('click');
    await flush();
  }
  const businessDayCalls = () => m.sent().filter((c) => c.path === '/api/sale/business_day');
  return { ...m, paramsOf: m.params, call, table, prop, rows, cells, chip, list, show, showOnNewStream, period, filter, action, businessDayCalls };
}

describe('SalesPage: the screen', () => {
  it('is «Sales» of Sales & POS, with its tabs', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Sales & POS');
    expect(page.props('tabsLabel')).toBe('Sales & POS sections');
    expect((page.props('tabs') as Array<{ id: string }>).map((tab) => tab.id)).toEqual(['pos', 'sales', 'quick_notes', 'departments', 'settings']);
    expect(s.find('sales-title').text()).toBe('Sales');
  });

  it('follows today’s sales, newest first, 50 from the first; and asks the hub its business day', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ ...TODAY, sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.businessDayCalls()).toHaveLength(1);
    expect(s.find('sales-table-loading').exists()).toBe(true);
    await s.show(PAGE);
    expect(s.table().props()).toMatchObject({
      serverSide: true,
      searchable: true,
      testid: 'sales-table',
      total: 5,
      pageSize: 50,
      pageSizeChooser: false,
      views: ['table', 'cards'],
      rowClickable: true,
      sort: 'created_at',
      sortDir: 'desc',
    });
    expect(s.prop('searchPlaceholder')).toBe('Search number or customer…');
    expect(s.prop('entityLabel')).toEqual({ one: 'sale', many: 'sales' });
  });

  it('paints Date, Number, Customer, Payment, Status and Total', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, c.sortable])).toEqual([
      ['created_at', 'Date', true],
      ['number', 'Number', true],
      ['customer_name', 'Customer', true],
      ['payment_method_name', 'Payment', true],
      ['status', 'Status', true],
      ['total', 'Total', true],
    ]);
    const when = plain(formatDateTime('2026-10-14T10:05:00Z', 'en'));
    expect(s.cells(0).slice(0, 6)).toEqual([when, '20261014-0001', 'Lucía Pérez', 'Cash', 'Completed', '€12.50']);
    expect(s.cells(1).slice(2, 5)).toEqual(['—', 'Card', 'Voided']);
    expect(s.cells(2)[4]).toBe('Refunded');
    expect(s.cells(3)[4]).toBe('Completed €5.00 left to refund');
  });

  it('a card is named by the sale’s number, with the receipt icon', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<(r: SaleRow) => string>('cardTitle')(ROWS[0])).toBe('20261014-0001');
    expect(s.prop<(r: SaleRow) => string>('cardIcon')(ROWS[0])).toBe('receipt-outline');
  });
});

describe('SalesPage: the period (SALE-F28 step 1)', () => {
  it('is Today, 7 days, 30 days or All, Today to begin with', async () => {
    const s = await setup();
    const segment = s.find('sales-range');
    expect([segment.attributes('aria-label'), (segment.element as HTMLElement & { value?: unknown }).value]).toEqual(['Period', 'today']);
    expect(['today', 'week', 'month', 'all'].map((p) => s.chip(p))).toEqual(['Today', '7 days', '30 days', 'All']);
  });

  it('counts back from the business day, for the rows and the figures, from the first page, asking the day again', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.find('sales-table-page-next').trigger('click');
    await flush();
    s.answer(200, { today: '2026-10-13' });
    await s.period('week');
    expect(s.businessDayCalls()).toHaveLength(2);
    expect(s.list()).toEqual([{ date_from: '2026-10-07', date_to: '2026-10-13', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.paramsOf('sale.sale.stats')).toEqual([{ date_from: '2026-10-07', date_to: '2026-10-13' }]);
    await s.period('all');
    expect(s.list()).toEqual([{ sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.paramsOf('sale.sale.stats')).toEqual([{}]);
  });

  it('«7 days» adds what was sold each of those days, under the figures (SALE-G01)', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.paramsOf('sale.sale.last_7_days')).toEqual([]);
    await s.period('week');
    expect(s.paramsOf('sale.sale.last_7_days')).toEqual([{}]);
    expect(s.wrapper.findComponent(SalesWeek).exists()).toBe(true);
    await s.period('month');
    expect(s.wrapper.findComponent(SalesWeek).exists()).toBe(false);
  });

  it('a business day it cannot read says the periods count from this device’s day', async () => {
    const s = await setup();
    s.answer(503, { error: { code: 'unavailable', message: 'Down' } });
    await s.period('month');
    expect(s.find('sales-business-day-error').text()).toContain("Could not read the business day: the periods count from this device's day.");
    expect(s.list()[0]).toMatchObject({ date_from: '2026-09-15', date_to: '2026-10-14' });
  });
});

describe('SalesPage: the figures (SALE-F28 step 2)', () => {
  it('whoever may see the reports gets the six figures of the period', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(SalesKpis).props('bounds')).toEqual(TODAY);
    expect(s.paramsOf('sale.sale.stats')).toEqual([TODAY]);
  });

  it('whoever may not sees the table without the figures (nothing asked)', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.wrapper.findComponent(SalesKpis).exists()).toBe(false);
    expect(s.paramsOf('sale.sale.stats')).toEqual([]);
    expect(s.list()).toHaveLength(1);
  });
});

describe('SalesPage: search, filters, sort and pages', () => {
  it('searches on the server; an empty answer says «No sale matches…», no sale at all «No sales yet.»', async () => {
    const s = await setup();
    await s.show(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No sales yet.');
    s.table().vm.$emit('update:search', ' 0007 ');
    await flush();
    expect(s.list()).toEqual([{ ...TODAY, search: '0007', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    await s.showOnNewStream(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No sale matches your search or filters.');
  });

  it('filters by status, payment and total (cents) on the server, from the first page', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.find('sales-table-page-next').trigger('click');
    await flush();
    await s.filter({ status: 'voided', payment_method_name: 'Cash', total_min: '10', total_max: '12,5' });
    expect(s.list()).toEqual([
      { status: 'voided', payment_method_name: 'Cash', total_min: 1000, total_max: 1250, ...TODAY, sort: 'created_at', dir: 'desc', limit: 50, offset: 0 },
    ]);
    // The figures are the period's: the filters narrow the rows only.
    expect(s.paramsOf('sale.sale.stats')).toEqual([TODAY]);
  });

  it('a date range replaces the period, for the rows and the figures; picking a period drops it', async () => {
    const s = await setup();
    await s.filter({ date_from: '2026-10-01', date_to: '2026-10-05' });
    expect(s.list()[0]).toMatchObject({ date_from: '2026-10-01', date_to: '2026-10-05' });
    expect(s.paramsOf('sale.sale.stats')).toEqual([{ date_from: '2026-10-01', date_to: '2026-10-05' }]);
    // No chip lit (Vue writes '' for an absent value: no button has it).
    expect((s.find('sales-range').element as HTMLElement & { value?: unknown }).value ?? '').toBe('');
    await s.period('today');
    expect(s.list()[0]).toMatchObject(TODAY);
    expect(s.prop('filters')).toEqual({});
  });

  it('picking a period drops only the date range: the other filters stay', async () => {
    const s = await setup();
    await s.filter({ status: 'voided', date_from: '2026-10-01' });
    await s.period('week');
    expect(s.prop('filters')).toEqual({ status: 'voided' });
    // 7 days back from this device's day (no business day answered here): the period rules again.
    expect(s.list()[0]).toMatchObject({ status: 'voided', date_from: '2026-10-08', date_to: '2026-10-14' });
  });

  // flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
  it('filters behind the table funnel, on their columns: date, payment (searched), status and total (as typed)', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop('filterable')).toBe(true);
    type Filter = { type: string; keys?: string[]; amount?: boolean; options?: Array<{ value: string; label: string }>; load?: (q: string) => Promise<unknown> };
    const columns = s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.label, c.filter?.type, c.filter?.keys, c.filter?.amount])).toEqual([
      ['Date', 'daterange', ['date_from', 'date_to'], undefined],
      ['Payment', 'lookup', undefined, undefined],
      ['Status', 'select', undefined, undefined],
      ['Total', 'range', ['total_min', 'total_max'], true],
    ]);
    expect(columns.find((c) => c.key === 'status')?.filter?.options).toEqual([
      { value: 'completed', label: 'Completed' },
      { value: 'voided', label: 'Voided' },
      { value: 'refunded', label: 'Refunded' },
    ]);
    // «Payment» asks the server for the business's methods (never a box of free text): the name read, the stored one sent.
    s.answer(200, { rows: [{ id: 'm1', name: 'Cash', display_name: 'Efectivo' }], total: 1, limit: 20, offset: 0 });
    const payment = columns.find((c) => c.key === 'payment_method_name')?.filter;
    expect(await payment?.load?.('efe')).toEqual([{ value: 'Cash', label: 'Efectivo' }]);
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/sale/payment_methods', query: { search: 'efe', limit: '20' } });
  });

  it('the funnel panel applies on «Apply» and counts the filtered columns', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.find('sales-table-filters-toggle').trigger('click');
    await flush();
    const panel = s.find('sales-table-filters-panel');
    const set = (name: string, event: string, value: string) =>
      panel.get(`[data-testid="sales-table-filter-${name}"]`).element.dispatchEvent(new CustomEvent(event, { detail: { value } }));
    set('status', 'ionChange', 'refunded');
    set('total_min', 'ionInput', '5');
    set('total_max', 'ionInput', '20,5');
    await flush();
    expect(s.list(), 'the panel edits a draft: nothing is asked before «Apply»').toEqual([{ ...TODAY, sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    await panel.get('[data-testid="sales-table-filters-apply"]').trigger('click');
    await flush();
    await s.reopen();
    expect(s.list()).toEqual([{ status: 'refunded', total_min: 500, total_max: 2050, ...TODAY, sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.find('sales-table-filters-count').text()).toBe('2');
  });

  it('an amount it cannot read, or a «to» day before its «from», is said under it, does not filter and leaves the period', async () => {
    const s = await setup();
    await s.show(EMPTY);
    expect(s.prop('filterErrors')).toEqual({});
    await s.filter({ total_max: 'doce', date_from: '2026-10-14', date_to: '2026-10-01' });
    expect(s.prop('filterErrors')).toEqual({ total_max: 'Type an amount, like 12.50', date_to: 'The end date cannot be before the start date.' });
    expect(s.list()).toEqual([{ ...TODAY, sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect((s.find('sales-range').element as HTMLElement & { value?: unknown }).value).toBe('today');
    await s.show(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No sales yet.');
  });

  it('a filter the server refused is said under it, and the rows stay', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.call.push(`event: error\ndata: ${JSON.stringify({ id: s.subId(OP), error: { code: 'invalid_field', message: 'Invalid', fields: { total_min: 'Too big.' } } })}\n\n`);
    await flush();
    expect(s.prop('filterErrors')).toEqual({ total_min: 'Too big.' });
    expect(s.prop('error')).toBeUndefined();
  });

  it('sorts on the server by any column, from the first page', async () => {
    const s = await setup();
    s.table().vm.$emit('sortChange', { sort: 'total', dir: 'asc' });
    await flush();
    expect(s.list()).toEqual([{ ...TODAY, sort: 'total', dir: 'asc', limit: 50, offset: 0 }]);
  });

  it('«Load more» never asks for more than 100 rows at once (windows of 100, each live)', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 400 });
    s.table().vm.$emit('loadMore');
    await flush();
    s.table().vm.$emit('loadMore');
    await flush();
    await s.reopen();
    expect(s.list().map((p) => [p.limit, p.offset])).toEqual([
      [100, 0],
      [50, 100],
    ]);
    expect(s.list().every((p) => (p.limit as number) <= 100)).toBe(true);
  });
});

describe('SalesPage: the row actions (SALE-F29–F31)', () => {
  it('a manager gets Document and Reprint everywhere, Void and Refund only where they apply', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ id: string; label: string; icon: string; color?: string }>>('actions').map((a) => [a.id, a.label, a.icon, a.color ?? null])).toEqual([
      ['document', 'Document', 'receipt-outline', null],
      ['reprint', 'Reprint', 'copy-outline', null],
      ['issue', 'Issue now', 'sync-outline', 'warning'],
      ['void', 'Void', 'ban-outline', 'danger'],
      ['refund', 'Refund', 'lucide:rotate-ccw', 'warning'],
    ]);
    const has = (id: string, action: string) => s.find(`sales-table-row-${id}-${action}`).exists();
    // A completed ticket without refunds: everything.
    expect(['document', 'reprint', 'void', 'refund'].map((a) => has('s1', a))).toEqual([true, true, true, true]);
    // Voided, or refunded in full: only the paper.
    expect(['void', 'refund'].map((a) => has('s2', a))).toEqual([false, false]);
    expect(['void', 'refund'].map((a) => has('s3', a))).toEqual([false, false]);
    // Partly refunded: refund what is left, no void.
    expect(['void', 'refund'].map((a) => has('s4', a))).toEqual([false, true]);
    // A full invoice is corrected with a credit note, never voided; it can be refunded.
    expect(['void', 'refund'].map((a) => has('s5', a))).toEqual([false, true]);
  });

  it('a sale paid whole with a voucher (0,00 €) can still be refunded while a session has not come back (SALE-F32)', async () => {
    const s = await setup();
    await s.show({
      ...PAGE,
      rows: [
        row('s6', { total: 0, refundable_total: 0, sessions_to_return: 1 }),
        row('s7', { total: 0, refundable_total: 0, sessions_to_return: 0 }),
        row('s8', { refunded_total: 1250, refundable_total: 0, sessions_to_return: 1, has_refunds: true }),
      ],
      total: 3,
    });
    const has = (id: string, action: string) => s.find(`sales-table-row-${id}-${action}`).exists();
    expect(['void', 'refund'].map((a) => has('s6', a))).toEqual([true, true]);
    expect(has('s7', 'refund')).toBe(false);
    expect(['void', 'refund'].map((a) => has('s8', a))).toEqual([false, true]);
  });

  it('a sale with a refund of no money (a voucher’s session came back) is refunded, never voided', async () => {
    // The server refuses voiding a sale with refunds (sale.sale_already_refunded), whatever the money.
    const s = await setup();
    await s.show({
      ...PAGE,
      rows: [row('s9', { refunded_total: 0, refundable_total: 1250, sessions_to_return: 1, has_refunds: true })],
      total: 1,
    });
    const has = (action: string) => s.find(`sales-table-row-s9-${action}`).exists();
    expect([has('void'), has('refund')]).toEqual([false, true]);
  });

  it('an employee gets Document, Reprint, «Issue now» (she charges), and Void and Refund, which a manager approves', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['document', 'reprint', 'issue', 'void', 'refund']);
    await s.action('s1', 'void');
    expect(s.wrapper.findComponent(VoidSaleModal).props()).toMatchObject({ open: true, sale: ROWS[0] });
    await s.action('s4', 'refund');
    expect(s.wrapper.findComponent(RefundModal).props()).toMatchObject({ open: true, sale: ROWS[3] });
  });

  it('a row, or «Document», opens its document (a duplicate when printed)', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.wrapper.findComponent(DocumentModal).props()).toMatchObject({ open: false });
    s.table().vm.$emit('rowClick', ROWS[0]);
    await flush();
    expect(s.wrapper.findComponent(DocumentModal).props()).toMatchObject({ open: true, saleId: 's1', duplicate: true });
    s.wrapper.findComponent(DocumentModal).vm.$emit('update:open', false);
    await flush();
    await s.action('s4', 'document');
    expect(s.wrapper.findComponent(DocumentModal).props()).toMatchObject({ open: true, saleId: 's4' });
  });

  it('«Reprint» prints the sale’s duplicate out of sight, with the row busy until it is done', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.action('s1', 'reprint');
    expect(s.wrapper.findComponent(ReprintJob).props('saleId')).toBe('s1');
    const busy = s.prop<Array<{ id: string; loading?: (r: SaleRow) => boolean }>>('actions').find((a) => a.id === 'reprint')!;
    expect([busy.loading?.(ROWS[0]), busy.loading?.(ROWS[1])]).toEqual([true, false]);
    s.wrapper.findComponent(ReprintJob).vm.$emit('done');
    await flush();
    expect(s.wrapper.findComponent(ReprintJob).exists()).toBe(false);
  });

  it('a sale whose fiscal documents wait says «Document pending» under its status, and only it offers «Issue now»', async () => {
    const s = await setup({ locale: 'es' });
    await s.show({ ...PAGE, rows: [row('s1'), row('s6', { invoice_status: 'pending', documents_pending: true })], total: 2 });
    expect(s.wrapper.findAll('[data-testid="sales-documents-pending"]').map((pill) => pill.text())).toEqual(['Documento pendiente']);
    expect(s.cells(1).join(' | ')).toContain('Documento pendiente');
    expect([s.find('sales-table-row-s1-issue').exists(), s.find('sales-table-row-s6-issue').exists()]).toEqual([false, true]);
  });

  it('«Issue now» asks the server for the sale’s waiting documents and says how it went', async () => {
    const s = await setup();
    await s.show({ ...PAGE, rows: [row('s6', { documents_pending: true })], total: 1 });
    s.answer(200, {});
    await s.action('s6', 'issue');
    expect(s.sent().filter((c) => c.method === 'POST')).toEqual([
      { method: 'POST', path: '/api/sale/sales/issue_documents', query: {}, body: { sale_id: 's6' } },
    ]);
    expect(toastSuccess).toHaveBeenCalledExactlyOnceWith('Fiscal documents issued.');
    s.net.onApi(() => Response.json({ error: { code: 'invoice.issuer_missing', message: 'Set up the issuer first.' } }, { status: 409 }));
    await s.action('s6', 'issue');
    expect(toastError).toHaveBeenCalledExactlyOnceWith('Set up the issuer first.');
  });

  it('«Void» opens «Void sale <number>» for that sale; «Refund» its refund window', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.action('s1', 'void');
    expect(s.wrapper.findComponent(VoidSaleModal).props()).toMatchObject({ open: true, sale: ROWS[0] });
    await s.action('s4', 'refund');
    expect(s.wrapper.findComponent(RefundModal).props()).toMatchObject({ open: true, sale: ROWS[3] });
  });
});

describe('SalesPage: the states of the screen', () => {
  it('on an error the table says so with Retry', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'sale.boom'));
    await flush();
    expect(s.prop('error')).toBe('msg sale.boom');
    expect(s.wrapper.get('[data-role="load-error"]').text()).toContain('The sales could not be loaded');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.find('sales-table-retry').trigger('click');
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('when the app is not active, or the person may not look, says so instead of the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'app_inactive'));
    await flush();
    expect(s.find('sales-inactive').text()).toContain('This app is not active in this business.');
    expect(s.table().exists()).toBe(false);
    const f = await setup();
    f.call.push(errorFrame(f.subId(OP), 'permission_denied'));
    await flush();
    expect(f.find('sales-forbidden').text()).toContain('You do not have permission.');
  });

  it('while the stream reconnects keeps the rows and shows «Reconnecting…»', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.call.push(BYE);
    await flush();
    expect(s.find('sales-reconnecting').text()).toContain('Reconnecting…');
    expect(s.rows()).toHaveLength(5);
  });
});

describe('SalesPage: the rest', () => {
  it('has no OutfitKit tag', () => {
    expect(source).not.toMatch(/<ok[-]/);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(PAGE);
    expect(s.find('sales-title').text()).toBe('Ventas');
    expect(s.find('sales-range').attributes('aria-label')).toBe('Periodo');
    expect(['today', 'week', 'month', 'all'].map((p) => s.chip(p))).toEqual(['Hoy', '7 días', '30 días', 'Todo']);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Fecha', 'Número', 'Cliente', 'Pago', 'Estado', 'Total']);
    expect(s.cells(3).slice(4, 6)).toEqual(['Completada Por devolver 5,00 €', '12,50 €']);
    expect(s.prop<Array<{ label: string }>>('actions').map((a) => a.label)).toEqual(['Documento', 'Reimprimir', 'Emitir ahora', 'Anular', 'Devolver']);
    expect(s.prop('searchPlaceholder')).toBe('Buscar número o cliente…');
    expect(s.prop('labels')).toMatchObject({ loading: 'Cargando…', loadError: 'No se pudieron cargar las ventas', retry: 'Reintentar' });
    type Column = { key: string; filter?: { options?: Array<{ label: string }> } };
    expect(s.prop<Column[]>('columns').find((c) => c.key === 'status')?.filter?.options?.map((o) => o.label)).toEqual(['Completada', 'Anulada', 'Devuelta']);
    await s.filter({ total_min: 'mil', date_from: '2026-10-14', date_to: '2026-10-01' });
    expect(s.prop('filterErrors')).toEqual({ total_min: 'Escribe un importe, como 12,50', date_to: 'La fecha final no puede ser anterior a la inicial.' });
  });
});

describe('SalesPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
