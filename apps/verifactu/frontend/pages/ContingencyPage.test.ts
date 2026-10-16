// VeriFactu → Contingency (VERIFACTU-F20–F22; the old `erp-verifactu-contingency`): «Contingency queue» with «Process
// queue» (for whoever may send) and the live `verifactu.contingency.list` — Invoice, Environment, Attempts, Status,
// Next attempt, Last error — with «Retry» and «View» per row. The result of a pass is said under the button.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { click, EMPLOYEE, flush, type MountOptions, mountVerifactu } from '../__tests__/mount-verifactu';
import { plain } from '../lib/format';
import type { QueueRowOut } from '../operations';
import ContingencyPage from './ContingencyPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const OP = 'verifactu.contingency.list';
const ROW: QueueRowOut = {
  id: 'r1',
  invoice_number: 'TICKET-2026-000001',
  record_type: 'alta',
  environment: 'testing',
  attempts: 2,
  status: 'pending',
  next_attempt_at: '2026-10-14T10:05:00Z',
  last_error: 'the gateway or the AEAT could not be reached (down)',
  created_at: '2026-10-14T10:00:00Z',
};

async function setup(options: MountOptions = {}) {
  const m = await mountVerifactu(ContingencyPage, { path: '/verifactu/contingency', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  async function emit(name: string, ...args: unknown[]) {
    table().vm.$emit(name, ...args);
    await flush();
  }
  return { ...m, table, emit };
}

describe('ContingencyPage', () => {
  it('follows the queue in the order it goes out', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'next_attempt_at', dir: 'asc', limit: 50, offset: 0 }]);
    await s.result(OP, { rows: [ROW], total: 1, limit: 50, offset: 0 });
    expect(((s.table().props() as Record<string, unknown>).columns as Array<{ label: string }>).map((c) => c.label)).toEqual([
      'Invoice',
      'Environment',
      'Attempts',
      'Status',
      'Next attempt',
      'Last error',
    ]);
    const cells = s.wrapper.findAll('[data-testid="verifactu-queue-row"]')[0].findAll('[role="cell"]').map((c) => plain(c.text().trim()));
    expect(cells.slice(0, 4)).toEqual(['TICKET-2026-000001', 'Testing (AEAT test)', '2', 'Pending']);
  });

  it('a record the gateway refused promises no next attempt', async () => {
    const s = await setup();
    await s.result(OP, {
      rows: [{ ...ROW, next_attempt_at: null, last_error: "ERPlora's gateway could not present it (no_certificate)" }],
      total: 1,
      limit: 50,
      offset: 0,
    });
    const cells = s.wrapper.findAll('[data-testid="verifactu-queue-row"]')[0].findAll('[role="cell"]').map((c) => plain(c.text().trim()));
    expect(cells[4]).toBe('');
    expect(cells[5]).toContain('could not present it');
  });

  it('an empty queue says everything is in the AEAT', async () => {
    const s = await setup();
    await s.result(OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('Queue empty: everything is in the AEAT.');
  });

  it('«Process queue» runs the pass and says what came of it', async () => {
    const s = await setup();
    s.answer(200, { chains: 1, sent: 2, accepted: 2, accepted_with_errors: 0, rejected: 0, waiting: 0, reason: '', message: '' });
    await click(s.find('verifactu-queue-process').element);
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/verifactu/contingency/process', query: {}, body: {} }]);
    expect(s.find('verifactu-queue-result').text()).toBe('2 sent, 2 accepted, 0 rejected, 0 waiting.');
  });

  it('a pass that could not send says why', async () => {
    const s = await setup();
    s.answer(200, { chains: 0, sent: 0, accepted: 0, accepted_with_errors: 0, rejected: 0, waiting: 3, reason: 'gateway_unavailable', message: "ERPlora's sending gateway is not configured on this server" });
    await click(s.find('verifactu-queue-process').element);
    expect(s.find('verifactu-queue-result').text()).toBe("ERPlora's sending gateway is not configured on this server");
  });

  it('a pass the gateway refused is a warning, never a success', async () => {
    const s = await setup();
    s.answer(200, { chains: 0, sent: 0, accepted: 0, accepted_with_errors: 0, rejected: 0, waiting: 1, reason: 'refused', message: "ERPlora's gateway could not present it (nif_mismatch)" });
    await click(s.find('verifactu-queue-process').element);
    const result = s.find('verifactu-queue-result');
    expect(result.text()).toBe("ERPlora's gateway could not present it (nif_mismatch)");
    expect(result.html()).toContain('warning');
    expect(result.html()).not.toContain('success');
  });

  it('«Retry» puts the record out with the next pass', async () => {
    const s = await setup();
    await s.result(OP, { rows: [ROW], total: 1, limit: 50, offset: 0 });
    s.answer(200, { id: 'r1', invoice_number: 'TICKET-2026-000001' });
    await s.emit('action', { actionId: 'retry', row: ROW });
    expect(s.sent().at(-1)).toEqual({ method: 'POST', path: '/api/verifactu/contingency/retry', query: {}, body: { record_id: 'r1' } });
    expect(toastSuccess).toHaveBeenCalledWith('TICKET-2026-000001 goes out with the next pass.');
  });

  it('the employee looks but does not process nor retry', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.result(OP, { rows: [ROW], total: 1, limit: 50, offset: 0 });
    expect(s.find('verifactu-queue-process').exists()).toBe(false);
    expect(((s.table().props() as Record<string, unknown>).actions as Array<{ id: string }>).map((a) => a.id)).toEqual(['view']);
  });
});

describe('ContingencyPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
