// VeriFactu → Recovery (VERIFACTU-F26–F29; the old `erp-verifactu-recovery`): «Chain recovery» with the «Issuer tax
// ID» (Invoicing's), «Chain integrity» with the last verdict, «Validate chain», «Query AEAT», «Recover chain from
// AEAT» (asks first), «Latest records at the AEAT» and «Continue chain manually (migration)» (a 64-hex fingerprint,
// asks first). Without a tax ID the buttons are off; each is shown to whoever may use it. «Latest records at the AEAT»
// is a server-side DataTable, as the old one: search «Search invoice, fingerprint or CSV…», sort on every column and
// the funnel's State and Date filters.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { click, flush, ionValue, MANAGER, type MountOptions, mountVerifactu } from '../__tests__/mount-verifactu';
import { plain } from '../lib/format';
import type { ChainStatusOut, ConfigOut } from '../operations';
import RecoveryPage from './RecoveryPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
beforeEach(() => mocks.confirm.mockReset());

const CONFIG = { environment: 'testing', issuer_nif: 'B12345674', issuer_name: 'Peluquería Ana SL' } as unknown as ConfigOut;
const CHAIN = (valid: boolean | null, first: number | null = null): ChainStatusOut => ({
  issuer_nif: 'B12345674',
  environment: 'testing',
  chains: [
    {
      issuer_nif: 'B12345674',
      environment: 'testing',
      sequence: 3,
      last_number: 'TICKET-2026-000003',
      last_issue_date: '2026-10-14',
      last_fingerprint: 'A'.repeat(64),
      anchored_at: null,
      anchor_source: '',
      validated_at: valid === null ? null : '2026-10-14T10:00:00Z',
      valid,
      total: 3,
      first_invalid_sequence: first,
    },
  ],
});
const AEAT = {
  rows: [
    {
      id: 'a1',
      issuer_nif: 'B12345674',
      environment: 'testing',
      invoice_number: 'TICKET-2026-000003',
      issue_date: '2026-10-14',
      fingerprint: 'A'.repeat(64),
      state: 'Correcto',
      csv: 'A-1',
      generated_on: '2026-10-14T10:00:00Z',
      queried_at: '2026-10-14T11:00:00Z',
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
};

const AEAT_OP = 'verifactu.aeat_record.list';

async function setup(chain: ChainStatusOut = CHAIN(null), options: MountOptions = {}) {
  const m = await mountVerifactu(RecoveryPage, { path: '/verifactu/recovery', ...options });
  await m.live();
  await m.result('verifactu.config.get', CONFIG);
  await m.reopen();
  await m.result('verifactu.chain.status', chain);
  await m.result(AEAT_OP, AEAT);
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  async function emit(name: string, ...args: unknown[]) {
    table().vm.$emit(name, ...args);
    await flush();
  }
  return { ...m, table, emit };
}

describe('RecoveryPage', () => {
  it('fills the issuer’s tax ID and says the chain was not validated yet', async () => {
    const s = await setup();
    expect((s.find('verifactu-recovery-nif').element as unknown as { value: string }).value).toBe('B12345674');
    expect(s.params('verifactu.chain.status')).toEqual([{ issuer_nif: 'B12345674' }]);
    expect(s.find('verifactu-recovery-integrity').text()).toContain('Not validated yet');
  });

  it('says whether the fingerprint chain is intact or broken', async () => {
    expect((await setup(CHAIN(true))).find('verifactu-recovery-integrity').text()).toContain('Fingerprint chain intact ✓');
    expect((await setup(CHAIN(false, 2))).find('verifactu-recovery-integrity').text()).toContain('BROKEN ✗ at sequence 2');
  });

  it('«Validate chain» validates the issuer’s chain', async () => {
    const s = await setup();
    s.answer(200, { issuer_nif: 'B12345674', environment: 'testing', valid: true, total: 3, first_invalid_sequence: null });
    await click(s.find('verifactu-recovery-validate').element);
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/chain/validate', query: {}, body: { issuer_nif: 'B12345674' } }]);
    expect(s.find('verifactu-recovery-result').text()).toBe('Operation completed.');
  });

  it('paints the latest records at the AEAT in a server-side table, the last generated first', async () => {
    const s = await setup();
    expect(s.params(AEAT_OP)).toEqual([{ sort: 'generated_on', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, filterable: true, testid: 'verifactu-recovery-aeat', pageSize: 50, total: 1 });
    expect(s.table().props('searchPlaceholder')).toBe('Search invoice, fingerprint or CSV…');
    expect(((s.table().props() as Record<string, unknown>).columns as Array<{ label: string }>).map((c) => c.label)).toEqual([
      'Invoice',
      'Date',
      'Fingerprint',
      'Status',
      'CSV',
      'Queried on',
    ]);
    const cells = s.wrapper.findAll('[data-testid="verifactu-recovery-aeat-row"]')[0].findAll('[role="cell"]').map((c) => plain(c.text().trim()));
    expect(cells.slice(0, 5)).toEqual(['TICKET-2026-000003', '10/14/2026', 'AAAAAAAAAA…AAAAAAAAAA', 'Registered', 'A-1']);
  });

  it('searches, sorts and filters the AEAT records on the server', async () => {
    const s = await setup();
    await s.emit('update:search', 'A-1');
    await s.emit('sort-change', { sort: 'issue_date', dir: 'asc' });
    await s.emit('update:filters', { state: 'Anulado', issue_date_from: '2026-10-01' });
    await s.reopen();
    expect(s.params(AEAT_OP)).toEqual([
      { search: 'A-1', state: 'Anulado', issue_date_from: '2026-10-01', sort: 'issue_date', dir: 'asc', limit: 50, offset: 0 },
    ]);
    const state = ((s.table().props() as Record<string, unknown>).columns as Array<{ key: string; filter?: { options?: { value: string; label: string }[] } }>).find(
      (c) => c.key === 'state',
    );
    expect(state?.filter?.options).toEqual([
      { value: 'Correcto', label: 'Registered' },
      { value: 'AceptadoConErrores', label: 'Accepted with errors' },
      { value: 'Anulado', label: 'Cancelled' },
    ]);
  });

  it('says there is no AEAT data yet, or no results with a search', async () => {
    const s = await setup();
    await s.result(AEAT_OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No AEAT data. Press «Query AEAT».');
    await s.emit('update:search', 'nope');
    await s.reopen();
    await s.result(AEAT_OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('«Recover chain from AEAT» asks first, and a refusal is said', async () => {
    const s = await setup();
    mocks.confirm.mockResolvedValue(true);
    s.answer(409, { error: { code: 'verifactu.gateway_unavailable', message: 'It cannot be sent now.' } });
    await click(s.find('verifactu-recovery-recover').element);
    expect(mocks.confirm.mock.calls[0][0].title).toBe('Recover the chain from the AEAT');
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/chain/recover_from_aeat', query: {}, body: { issuer_nif: 'B12345674' } }]);
    expect(s.find('verifactu-recovery-result').text()).toBe('It cannot be sent now.');
  });

  it('a manual anchor needs a 64-hex fingerprint, then asks and continues the chain', async () => {
    const s = await setup();
    await ionValue(s.find('verifactu-recovery-hash').element, 'xyz', 'ionInput');
    await ionValue(s.find('verifactu-recovery-invoice').element, 'OLD-1', 'ionInput');
    await ionValue(s.find('verifactu-recovery-date').element, '2026-10-01');
    await click(s.find('verifactu-recovery-manual').element);
    expect(s.find('verifactu-recovery-result').text()).toBe('The fingerprint must be 64 hexadecimal characters');
    expect(mocks.confirm).not.toHaveBeenCalled();
    await ionValue(s.find('verifactu-recovery-hash').element, 'ab'.repeat(32), 'ionInput');
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, { issuer_nif: 'B12345674', environment: 'testing', sequence: 0, invoice_number: 'OLD-1', fingerprint: 'AB'.repeat(32), found: 0 });
    await click(s.find('verifactu-recovery-manual').element);
    expect(s.sent().at(-1)).toEqual({
      method: 'POST',
      path: '/api/verifactu/chain/recover_manual',
      query: {},
      body: { issuer_nif: 'B12345674', fingerprint: 'ab'.repeat(32), invoice_number: 'OLD-1', issue_date: '2026-10-01' },
    });
  });

  it('the manager validates and queries but does not recover', async () => {
    const s = await setup(CHAIN(null), { session: MANAGER });
    expect(s.find('verifactu-recovery-validate').exists()).toBe(true);
    expect(s.find('verifactu-recovery-query').exists()).toBe(true);
    expect(s.find('verifactu-recovery-recover').exists()).toBe(false);
    expect(s.find('verifactu-recovery-manual').exists()).toBe(false);
  });
});
