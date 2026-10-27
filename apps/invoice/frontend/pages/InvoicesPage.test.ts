// Invoicing → Invoices (INVOICE-F16, F19, F03, F08; the old `erp-invoice-list`): the live
// `invoice.invoice.list` in a server-side DataTable — Number, Customer, Total, Status, Date, Type —, the last
// issued first, 50 a page, search «Search invoices…» and the filters behind the table's funnel. A row opens its invoice; «Mark
// as paid» only where it applies and for whoever may issue; «Rectify» only where it applies and for
// whoever may rectify; «+» opens «New manual invoice». Every state of the screen and the tabbar.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { business, BYE, EMPLOYEE, errorFrame, flush, MANAGER, type MountOptions, mountInvoice, POLISH } from '../__tests__/mount-invoice';
import InvoiceCreateModal from '../components/InvoiceCreateModal.vue';
import RectifyModal from '../components/RectifyModal.vue';
import { plain } from '../lib/format';
import type { InvoiceRowOut } from '../operations';
import InvoicesPage from './InvoicesPage.vue';
import source from './InvoicesPage.vue?raw';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
beforeEach(() => mocks.confirm.mockReset());

const OP = 'invoice.invoice.list';

const row = (number: string, over: Partial<InvoiceRowOut> = {}): InvoiceRowOut => ({
  id: number,
  number,
  invoice_type: 'F1',
  series_code: 'FACT',
  year: 2026,
  issue_date: '2026-10-14',
  issued_at: '2026-10-14T10:00:00Z',
  customer_name: 'Talleres Pérez SL',
  customer_tax_id: 'B12345674',
  base_amount: 1000,
  tax_amount: 210,
  total_amount: 1210,
  currency: 'EUR',
  currency_decimals: 2,
  status: 'issued',
  source_type: 'manual',
  rectifies_id: null,
  rectifies_number: '',
  substituted: false,
  can_mark_paid: true,
  can_rectify: true,
  can_substitute: false,
  ...over,
});

const PAGE = {
  rows: [
    row('FACT-2026-000002'),
    row('TICKET-2026-000001', { invoice_type: 'F2', customer_name: '', status: 'paid', can_mark_paid: false, can_substitute: true, source_type: 'sale' }),
    row('RECT-2026-000001', { invoice_type: 'R1', total_amount: -1210, status: 'issued', can_mark_paid: false, can_rectify: false, rectifies_number: 'FACT-2026-000001' }),
  ],
  total: 3,
  limit: 50,
  offset: 0,
};
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };

async function setup(options: MountOptions = {}) {
  const m = await mountInvoice(InvoicesPage, options);
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="invoice-list-row"]');
  const params = () => m.params(OP);
  const show = (page: unknown) => m.result(OP, page);
  async function emit(name: string, ...args: unknown[]) {
    table().vm.$emit(name, ...args);
    await flush();
  }
  /** What the table's funnel applies (`v-model:filters`): the filters by name, as typed. */
  const filter = (values: Record<string, string>) => emit('update:filters', values);
  return { ...m, call, table, prop, rows, params, show, emit, filter };
}

describe('InvoicesPage: the live list', () => {
  it('follows invoice.invoice.list, the last issued first, 50 from the first, until the first result loading', async () => {
    const s = await setup();
    expect(s.params()).toEqual([{ sort: 'issued_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.prop('loading')).toBe(true);
    await s.show(PAGE);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'invoice-list', pageSize: 50, total: 3, views: ['table', 'cards'], rowClickable: true });
    expect(s.prop('searchPlaceholder')).toBe('Search invoices…');
    expect(s.prop('entityLabel')).toEqual({ one: 'invoice', many: 'invoices' });
  });

  it('sits under «Invoicing» with the tabbar of its sections', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Invoicing');
    expect((page.props('tabs') as Array<{ id: string }>).map((t) => t.id)).toEqual(['invoices', 'series', 'issuer']);
  });

  it('paints Number, Customer, Total, Status, Date and Type, in that order', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.sortable])).toEqual([
      ['number', 'Number', true],
      ['customer_name', 'Customer', true],
      ['total_amount', 'Total', true],
      ['status', 'Status', true],
      ['issue_date', 'Date', true],
      ['invoice_type', 'Type', true],
    ]);
    const text = (i: number) => s.rows()[i].findAll('[role="cell"]').map((c) => plain(c.text().trim()));
    expect(text(0).slice(0, 6)).toEqual(['FACT-2026-000002', 'Talleres Pérez SL', '€12.10', 'Issued', '10/14/2026', 'Invoice']);
    expect(text(1).slice(0, 6)).toEqual(['TICKET-2026-000001', '—', '€12.10', 'Paid', '10/14/2026', 'Ticket']);
    expect(text(2).slice(2, 3)).toEqual(['-€12.10']);
  });

  it('sorts, searches and pages on the server; an empty answer says «No results»', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.emit('sortChange', { sort: 'total_amount', dir: 'asc' });
    expect(s.params()).toEqual([{ sort: 'total_amount', dir: 'asc', limit: 50, offset: 0 }]);
    await s.emit('update:search', '  pérez ');
    expect(s.params()).toEqual([{ search: 'pérez', sort: 'total_amount', dir: 'asc', limit: 50, offset: 0 }]);
    await s.reopen();
    await s.show(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('the filters travel with the query, from the first page', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.filter({ status: 'paid', total_amount_from: '10' });
    expect(s.params()).toEqual([{ status: 'paid', total_amount_from: 1000, sort: 'issued_at', dir: 'desc', limit: 50, offset: 0 }]);
  });

  it('a total typed with the business’s symbol travels in its cents (flow business-currency)', async () => {
    const s = await setup();
    await s.result('base.business.get', business(POLISH));
    await s.show(PAGE);
    await s.filter({ total_amount_from: '12,50 zł' });
    expect(s.params()).toEqual([{ total_amount_from: 1250, sort: 'issued_at', dir: 'desc', limit: 50, offset: 0 }]);
  });

  // flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
  it('filters behind the table funnel: total, status, date and type on their columns, then series and source', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop('filterable')).toBe(true);
    type Filter = { type: string; key?: string; keys?: string[]; amount?: boolean; maxlength?: number; label?: string; options?: Array<{ value: string; label: string }> };
    const columns = s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.label, c.filter?.type, c.filter?.keys, c.filter?.amount])).toEqual([
      ['Total', 'range', ['total_amount_from', 'total_amount_to'], true],
      ['Status', 'select', undefined, undefined],
      ['Date', 'daterange', ['issue_date_from', 'issue_date_to'], undefined],
      ['Type', 'select', undefined, undefined],
    ]);
    expect(columns.find((c) => c.key === 'status')?.filter?.options).toEqual([
      { value: 'issued', label: 'Issued' },
      { value: 'paid', label: 'Paid' },
      { value: 'cancelled', label: 'Cancelled' },
    ]);
    expect(columns.find((c) => c.key === 'invoice_type')?.filter?.options?.map((o) => [o.value, o.label])).toEqual([
      ['F1', 'Invoice (F1)'],
      ['F2', 'Ticket (F2)'],
      ['F3', 'Invoice replacing a ticket (F3)'],
      ['R1', 'Rectifying (R1)'],
      ['R2', 'Rectifying (R2)'],
      ['R3', 'Rectifying (R3)'],
      ['R4', 'Rectifying (R4)'],
      ['R5', 'Rectifying (R5)'],
    ]);
    const fields = s.prop<Filter[]>('filterFields');
    expect(fields.map((f) => [f.key, f.label, f.type, f.maxlength])).toEqual([
      ['series_code', 'Series', 'text', 20],
      ['source_type', 'Source', 'select', undefined],
    ]);
    expect(fields[1].options?.map((o) => o.value)).toEqual(['sale', 'manual', 'substitution', 'rectification', 'refund', 'void']);
  });

  it('every filter of the funnel reaches the server with its own parameter, from the first page', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.find('invoice-list-page-next').trigger('click');
    await flush();
    await s.filter({
      status: 'issued',
      invoice_type: 'F1',
      series_code: ' fact ',
      source_type: 'manual',
      issue_date_from: '2026-10-01',
      issue_date_to: '2026-10-14',
      total_amount_from: '12',
      total_amount_to: '100,5',
    });
    expect(s.params()).toEqual([
      {
        status: 'issued',
        invoice_type: 'F1',
        series_code: 'FACT',
        source_type: 'manual',
        issue_date_from: '2026-10-01',
        issue_date_to: '2026-10-14',
        total_amount_from: 1200,
        total_amount_to: 10050,
        sort: 'issued_at',
        dir: 'desc',
        limit: 50,
        offset: 0,
      },
    ]);
  });

  it('the funnel panel applies on «Apply» and counts the filtered columns', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.find('invoice-list-filters-toggle').trigger('click');
    await flush();
    const panel = s.find('invoice-list-filters-panel');
    const set = (name: string, event: string, value: string) =>
      panel.get(`[data-testid="invoice-list-filter-${name}"]`).element.dispatchEvent(new CustomEvent(event, { detail: { value } }));
    set('status', 'ionChange', 'paid');
    set('total_amount_to', 'ionInput', '50');
    set('series_code', 'ionInput', 'tick');
    await flush();
    expect(s.params(), 'the panel edits a draft: nothing is asked before «Apply»').toEqual([{ sort: 'issued_at', dir: 'desc', limit: 50, offset: 0 }]);
    await panel.get('[data-testid="invoice-list-filters-apply"]').trigger('click');
    await flush();
    expect(s.params()).toEqual([{ status: 'paid', series_code: 'TICK', total_amount_to: 5000, sort: 'issued_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.find('invoice-list-filters-count').text()).toBe('3');
  });

  it('an amount it cannot read, or a «to» day before its «from», is said under it and neither filters nor narrows', async () => {
    const s = await setup();
    await s.show(EMPTY);
    expect(s.prop('filterErrors')).toEqual({});
    await s.filter({ total_amount_from: 'doce', issue_date_from: '2026-10-14', issue_date_to: '2026-10-01' });
    expect(s.prop('filterErrors')).toEqual({
      total_amount_from: 'Type an amount, like 12.50',
      issue_date_to: 'The end date cannot be before the start date.',
    });
    expect(s.params()).toEqual([{ sort: 'issued_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No invoices yet.');
  });

  it('a filter the server refused (a 422 of the list) is said under it, and the rows stay', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.call.push(`event: error\ndata: ${JSON.stringify({ id: s.subId(OP), error: { code: 'invalid_field', message: 'Invalid', fields: { total_amount_to: 'Too big.' } } })}\n\n`);
    await flush();
    expect(s.prop('filterErrors')).toEqual({ total_amount_to: 'Too big.' });
    expect(s.prop('error')).toBeUndefined();
  });

  it('with no invoice at all says «No invoices yet.»', async () => {
    const s = await setup();
    await s.show(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No invoices yet.');
  });
});

describe('InvoicesPage: opening and acting on a row', () => {
  it('a row (or «View») opens its invoice', async () => {
    const s = await setup();
    await s.show(PAGE);
    const push = vi.spyOn(s.router, 'push');
    await s.emit('rowClick', PAGE.rows[0]);
    expect(push).toHaveBeenLastCalledWith('/invoice/invoices/FACT-2026-000002');
    await s.emit('action', { actionId: 'view', row: PAGE.rows[1] });
    expect(push).toHaveBeenLastCalledWith('/invoice/invoices/TICKET-2026-000001');
  });

  it('offers «Mark as paid» and «Rectify» only where they apply', async () => {
    const s = await setup();
    await s.show(PAGE);
    const actions = s.prop<Array<{ id: string; hidden?: (row: InvoiceRowOut) => boolean }>>('actions');
    expect(actions.map((a) => a.id)).toEqual(['view', 'paid', 'rectify']);
    const shown = (id: string) => PAGE.rows.filter((r) => !actions.find((a) => a.id === id)!.hidden?.(r)).map((r) => r.number);
    expect(shown('paid')).toEqual(['FACT-2026-000002']);
    expect(shown('rectify')).toEqual(['FACT-2026-000002', 'TICKET-2026-000001']);
  });

  it('«Mark as paid» asks and marks it; a refusal is said above the table', async () => {
    const s = await setup();
    await s.show(PAGE);
    mocks.confirm.mockResolvedValue(true);
    s.answer(409, { error: { code: 'invoice.cannot_mark_paid', message: 'This invoice cannot be marked as paid.' } });
    await s.emit('action', { actionId: 'paid', row: PAGE.rows[0] });
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/invoice/invoices/mark_paid', query: {}, body: { invoice_id: 'FACT-2026-000002' } }]);
    expect(s.find('invoice-action-error').text()).toContain('This invoice cannot be marked as paid.');
  });

  it('«Rectify» opens the window for that invoice', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.emit('action', { actionId: 'rectify', row: PAGE.rows[0] });
    const modal = s.wrapper.findComponent(RectifyModal);
    expect([modal.props('open'), modal.props('invoice')]).toEqual([true, PAGE.rows[0]]);
  });

  it('«+» opens «New manual invoice»', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.wrapper.findComponent(InvoiceCreateModal).props('open')).toBe(false);
    await s.find('invoice-list-add').trigger('click');
    await flush();
    expect(s.wrapper.findComponent(InvoiceCreateModal).props('open')).toBe(true);
  });
});

describe('InvoicesPage: who may do what', () => {
  it('a manager issues, pays and rectifies', async () => {
    const s = await setup({ session: MANAGER });
    await s.show(PAGE);
    expect(s.prop('addable')).toBe(true);
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['view', 'paid', 'rectify']);
  });

  it('an employee issues and pays but does not rectify', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect(s.prop('addable')).toBe(true);
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['view', 'paid']);
    expect(s.wrapper.findComponent(RectifyModal).exists()).toBe(false);
  });

  it('whoever only looks gets no «+» and no actions but «View»', async () => {
    const s = await setup({ session: { ...EMPLOYEE, permissions: ['invoice.view_invoice'] } });
    await s.show(PAGE);
    expect(s.prop('addable')).toBe(false);
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['view']);
    expect(s.wrapper.findComponent(InvoiceCreateModal).exists()).toBe(false);
  });
});

describe('InvoicesPage: the states of the screen', () => {
  it('says above the list that nothing can be invoiced while the issuer is not set up (INVOICE-F21)', async () => {
    const s = await setup();
    expect(s.subId('invoice.issuer.get')).toBeTruthy();
    await s.result('invoice.issuer.get', { configured: false });
    await s.show(PAGE);
    expect(s.find('invoice-issuer-notice').text()).toContain('You cannot invoice yet');
    expect(s.rows()).toHaveLength(3);
    await s.result('invoice.issuer.get', { configured: true }, {}, 2);
    expect(s.find('invoice-issuer-notice').exists()).toBe(false);
  });

  it('on an error the table says so with Retry', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'invoice.boom'));
    await flush();
    expect(s.prop('error')).toBe('msg invoice.boom');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.find('invoice-list-retry').trigger('click');
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('when the app is not active says so instead of the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'app_inactive'));
    await flush();
    expect(s.find('invoice-list-inactive').text()).toContain('This app is not active in this business');
    expect(s.table().exists()).toBe(false);
  });

  it('while the stream reconnects keeps the rows and shows «Reconnecting…»', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.call.push(BYE);
    await flush();
    expect(s.find('invoice-list-reconnecting').text()).toBe('Reconnecting…');
    expect(s.rows()).toHaveLength(3);
  });
});

describe('InvoicesPage: the rest', () => {
  it('names its cards by number and formats nothing by hand', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(PAGE.rows.map(s.prop<(row: InvoiceRowOut) => string>('cardTitle'))).toEqual(PAGE.rows.map((r) => r.number));
    expect(source).not.toMatch(/<ok[-]/);
    expect(source).not.toMatch(/Intl\.|toLocale|new Date\(/);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Facturación');
    await s.show(PAGE);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Número', 'Cliente', 'Total', 'Estado', 'Fecha', 'Tipo']);
    expect(s.rows()[0].findAll('[role="cell"]').slice(2, 5).map((c) => plain(c.text().trim()))).toEqual(['12,10 €', 'Emitida', '14/10/2026']);
    expect(s.prop('searchPlaceholder')).toBe('Buscar facturas…');
    expect(s.prop<Array<{ label: string }>>('filterFields').map((f) => f.label)).toEqual(['Serie', 'Origen']);
    await s.filter({ total_amount_to: 'mil', issue_date_from: '2026-10-14', issue_date_to: '2026-10-01' });
    expect(s.prop('filterErrors')).toEqual({ total_amount_to: 'Escribe un importe, como 12,50', issue_date_to: 'La fecha final no puede ser anterior a la inicial.' });
  });
});

describe('InvoicesPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
