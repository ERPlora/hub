// VeriFactu → Records (VERIFACTU-F16, F18; the old `erp-verifactu-records`): the live `verifactu.record.list` in a
// server-side DataTable — Seq, Invoice, Date, Type, F., Issuer, Total, Environment, Status —, the last sealed first,
// 50 a page, search «Search invoice, issuer or tax ID…» and the filters panel. A row opens its record; «Verify at
// the AEAT» opens the QR's link. Every state of the screen and the tabbar.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { errorFrame, flush, type MountOptions, mountVerifactu } from '../__tests__/mount-verifactu';
import { plain } from '../lib/format';
import type { RecordRowOut } from '../operations';
import RecordsPage from './RecordsPage.vue';

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
