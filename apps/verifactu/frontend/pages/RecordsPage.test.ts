// VeriFactu → Records (VERIFACTU-F16, F18; the old `erp-verifactu-records`): the live `verifactu.record.list` in a
// server-side DataTable — Seq, Invoice, Date, Type, F., Issuer, Total, Environment, Status —, the last sealed first,
// 50 a page, search «Search invoice, issuer or tax ID…» and the filters behind the table's funnel. A row opens its record; «Verify at
// the AEAT» opens the QR's link. Every state of the screen and the tabbar.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { errorFrame, flush, type MountOptions, mountVerifactu } from '../__tests__/mount-verifactu';
import { plain } from '../lib/format';
import type { RecordRowOut } from '../operations';
import RecordsPage from './RecordsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'verifactu.record.list';

const row = (number: string, over: Partial<RecordRowOut> = {}): RecordRowOut => ({
  id: number,
  sequence: 1,
  record_type: 'alta',
  invoice_id: `inv-${number}`,
  invoice_number: number,
  issue_date: '2026-10-14',
  invoice_type: 'F2',
  issuer_name: 'Peluquería Ana SL',
  issuer_nif: 'B12345674',
  total_amount: 1210,
  environment: 'testing',
  status: 'pending',
  correction: false,
  qr_url: `https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?numserie=${number}`,
  created_at: '2026-10-14T10:00:00Z',
  ...over,
});

const PAGE = {
  rows: [
    row('TICKET-2026-000002', { sequence: 2, status: 'accepted' }),
    row('TICKET-2026-000001', { sequence: 3, record_type: 'anulacion', invoice_type: '', total_amount: null, status: 'rejected' }),
  ],
  total: 2,
  limit: 50,
  offset: 0,
};
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };

async function setup(options: MountOptions = {}) {
  const m = await mountVerifactu(RecordsPage, options);
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="verifactu-records-row"]');
  async function emit(name: string, ...args: unknown[]) {
    table().vm.$emit(name, ...args);
    await flush();
  }
  return { ...m, table, prop, rows, emit, show: (page: unknown) => m.result(OP, page) };
}

describe('RecordsPage', () => {
  it('follows verifactu.record.list, the last sealed first, 50 from the first', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.prop('loading')).toBe(true);
    await s.show(PAGE);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'verifactu-records', pageSize: 50, total: 2, rowClickable: true });
    expect(s.prop('searchPlaceholder')).toBe('Search invoice, issuer or tax ID…');
  });

  it('sits under «VeriFactu» with the six tabs', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('VeriFactu records');
    expect((page.props('tabs') as Array<{ id: string }>).map((t) => t.id)).toEqual(['records', 'contingency', 'events', 'recovery', 'config', 'settings']);
  });

  it('paints Seq, Invoice, Date, Type, F., Issuer, Total, Environment and Status', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['sequence', 'Seq'],
      ['invoice_number', 'Invoice'],
      ['issue_date', 'Date'],
      ['record_type', 'Type'],
      ['invoice_type', 'F.'],
      ['issuer_name', 'Issuer'],
      ['total_amount', 'Total'],
      ['environment', 'Environment'],
      ['status', 'Status'],
    ]);
    const text = (i: number) => s.rows()[i].findAll('[role="cell"]').map((c) => plain(c.text().trim()));
    expect(text(0).slice(0, 9)).toEqual(['2', 'TICKET-2026-000002', '10/14/2026', 'Registration', 'F2', 'Peluquería Ana SL', '€12.10', 'Testing (AEAT test)', 'Accepted']);
    expect(text(1).slice(3, 9)).toEqual(['Cancellation', '—', 'Peluquería Ana SL', '—', 'Testing (AEAT test)', 'Rejected']);
  });

  it('searches, sorts and filters on the server', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.emit('update:search', 'B12345674');
    await s.emit('sort-change', { sort: 'sequence', dir: 'asc' });
    await s.reopen();
    expect(s.params(OP)).toEqual([{ search: 'B12345674', sort: 'sequence', dir: 'asc', limit: 50, offset: 0 }]);
  });

  it('a row opens its record; «Verify at the AEAT» opens the QR link in a new tab', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    const s = await setup();
    await s.show(PAGE);
    const push = vi.spyOn(s.router, 'push');
    await s.emit('row-click', PAGE.rows[0]);
    expect(push).toHaveBeenCalledWith('/verifactu/records/TICKET-2026-000002');
    await s.emit('action', { actionId: 'verify', row: PAGE.rows[0] });
    expect(open).toHaveBeenCalledWith(PAGE.rows[0].qr_url, '_blank', 'noopener');
    open.mockRestore();
  });

  it('says there are no records yet, or no results with a search', async () => {
    const s = await setup();
    await s.show(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No records yet. Every invoice you issue is sealed and listed here.');
    await s.emit('update:search', 'nope');
    await s.reopen();
    await s.show(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('says why it could not load, in the table', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    expect(s.prop('error')).toBe('msg boom');
  });

  it('replaces the screen when the app is off here', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'app_inactive'));
    await flush();
    expect(s.find('verifactu-records-inactive').exists()).toBe(true);
    expect(s.find('verifactu-records').exists()).toBe(false);
  });
});

describe('RecordsPage: the filters behind the table funnel (FIX-DATATABLE-HUB-FILTERS-2B)', () => {
  // flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
  type Filter = { type: string; key?: string; keys?: string[]; amount?: boolean; label?: string; options?: Array<{ value: string; label: string }> };

  it('Date, Type, Total, Environment and Status filter on their columns, the invoice type after them', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop('filterable')).toBe(true);
    const columns = s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.label, c.filter?.key ?? c.key, c.filter?.type, c.filter?.keys, c.filter?.amount])).toEqual([
      ['Date', 'issue_date', 'daterange', ['issue_date_from', 'issue_date_to'], undefined],
      ['Type', 'record_type', 'select', undefined, undefined],
      ['Total', 'total_amount', 'range', ['total_amount_from', 'total_amount_to'], true],
      ['Environment', 'environment', 'select', undefined, undefined],
      ['Status', 'status', 'select', undefined, undefined],
    ]);
    const options = (key: string) => columns.find((c) => c.key === key)?.filter?.options;
    expect(options('record_type')).toEqual([
      { value: 'alta', label: 'Registration' },
      { value: 'anulacion', label: 'Cancellation' },
    ]);
    expect(options('environment')?.map((o) => o.value)).toEqual(['testing', 'production']);
    expect(options('status')?.map((o) => o.value)).toEqual(['pending', 'sent', 'accepted', 'accepted_with_errors', 'rejected']);
    const fields = s.prop<Filter[]>('filterFields');
    expect(fields.map((f) => [f.key, f.label, f.type])).toEqual([['invoice_type', 'Invoice type', 'select']]);
    expect(fields[0].options?.map((o) => [o.value, o.label])).toEqual(['F1', 'F2', 'F3', 'R1', 'R2', 'R3', 'R4', 'R5'].map((code) => [code, code]));
  });

  it('the funnel panel applies on «Apply»: every filter, the totals in cents, and counts them', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.find('verifactu-records-filters-toggle').trigger('click');
    await flush();
    const panel = s.find('verifactu-records-filters-panel');
    const set = (name: string, event: string, value: string) =>
      panel.get(`[data-testid="verifactu-records-filter-${name}"]`).element.dispatchEvent(new CustomEvent(event, { detail: { value } }));
    set('issue_date_from', 'ionChange', '2026-10-01');
    set('issue_date_to', 'ionChange', '2026-10-14');
    set('record_type', 'ionChange', 'alta');
    set('total_amount_from', 'ionInput', '12,50');
    set('total_amount_to', 'ionInput', '100');
    set('environment', 'ionChange', 'testing');
    set('status', 'ionChange', 'rejected');
    set('invoice_type', 'ionChange', 'F2');
    await flush();
    await s.reopen();
    expect(s.params(OP), 'the panel edits a draft: nothing is asked before «Apply»').toEqual([{ sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    await panel.get('[data-testid="verifactu-records-filters-apply"]').trigger('click');
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([
      {
        issue_date_from: '2026-10-01',
        issue_date_to: '2026-10-14',
        record_type: 'alta',
        total_amount_from: 1250,
        total_amount_to: 10000,
        environment: 'testing',
        status: 'rejected',
        invoice_type: 'F2',
        sort: 'created_at',
        dir: 'desc',
        limit: 50,
        offset: 0,
      },
    ]);
    expect(s.find('verifactu-records-filters-count').text()).toBe('6');
  });

  it('a total that is not an amount, or a day «until» before its «from», is said under it and does not filter', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop('filterErrors')).toEqual({});
    await s.emit('update:filters', { total_amount_from: '12x', issue_date_from: '2026-10-14', issue_date_to: '2026-10-01' });
    await s.reopen();
    expect(s.prop('filterErrors')).toEqual({
      total_amount_from: 'Write an amount in euros, such as 12,50.',
      issue_date_to: 'The end date cannot be before the start date.',
    });
    expect(s.params(OP)).toEqual([{ issue_date_from: '2026-10-14', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    const es = await setup({ locale: 'es' });
    await es.show(PAGE);
    await es.emit('update:filters', { issue_date_from: '2026-10-14', issue_date_to: '2026-10-01' });
    expect(es.prop('filterErrors')).toEqual({ issue_date_to: 'La fecha final no puede ser anterior a la inicial.' });
  });

  it('a filter the server refuses (422) goes under its filter; the rows stay and no error replaces them', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.emit('update:filters', { total_amount_to: '99999999999' });
    await s.reopen();
    await s.show(PAGE);
    const refused = { code: 'invalid_payload', message: 'Some fields are not valid.', fields: { total_amount_to: 'Input should be a valid integer.' } };
    s.net.lastStream().push(`event: error\ndata: ${JSON.stringify({ id: s.subId(OP), error: refused })}\n\n`);
    await flush();
    expect(s.prop('filterErrors')).toEqual({ total_amount_to: 'Input should be a valid integer.' });
    expect(s.prop('error')).toBeUndefined();
    expect(s.rows()).toHaveLength(2);
  });
});

describe('RecordsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
