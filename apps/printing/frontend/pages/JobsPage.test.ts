// Printing → Queue (PRINTING-F01, F14; WORKBOOK «Pantallas · Cola»): the live `printing.job.list`, newest
// first, in a server-side DataTable — Document, Role, Printer, Status, Attempts, Asked on, Detail — with the
// document's search, filters by status, role and printer, and 50 a page. Whoever manages the queue retries a
// failed (or unanswered) job and cancels a queued, failed or unanswered one; nobody else sees those buttons.
import { DataTable, type DataTableAction, type DataTableColumn } from '@erplora/ui/components';
import { AppPage, toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, flush, MANAGER, type MountOptions, mountPrinting, words } from '../__tests__/mount-printing';
import CancelJobModal from '../components/CancelJobModal.vue';
import type { JobOut } from '../operations';
import JobsPage from './JobsPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
});

const LIST = 'printing.job.list';
const PRINTERS = 'printing.printer.list';

const job = (id: string, more: Partial<JobOut> = {}): JobOut => ({
  id,
  job_key: `k-${id}`,
  kind: 'document',
  document_type: 'receipt',
  reference: 'T-000123',
  format: 'receipt',
  usage: 'receipt',
  printer_id: 'p1',
  printer_name: 'Till',
  copies: 1,
  open_drawer: false,
  status: 'pending',
  attempts: 0,
  leased_until: null,
  stale: false,
  retryable: false,
  cancellable: true,
  device: '',
  last_error: '',
  source_app: 'sale',
  created_at: '2026-10-14T21:05:00Z',
  created_by: 'Ana',
  sent_at: null,
  printed_at: null,
  failed_at: null,
  retried_at: null,
  retried_by: '',
  cancelled_at: null,
  cancelled_by: '',
  cancel_reason: '',
  ...more,
});
const QUEUED = job('j1', { retryable: true });
const FAILED = job('j2', { status: 'failed', attempts: 5, retryable: true, cancellable: true, last_error: 'out of paper', printer_id: null, printer_name: null, usage: 'label', document_type: 'barcode_label', reference: 'Shampoo' });
const DONE = job('j3', { status: 'done', cancellable: false });
const PAGE = { rows: [QUEUED, FAILED, DONE], total: 3, limit: 50, offset: 0 };

async function setup(options: MountOptions = {}) {
  const m = await mountPrinting(JobsPage, { path: '/printing/jobs', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T,>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const actions = (row: JobOut) =>
    prop<DataTableAction<JobOut>[]>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => a.id);
  return { ...m, table, prop, actions };
}

describe('JobsPage', () => {
  it('is Printing’s queue: newest first, 50 a page, on the server', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Printing');
    expect(s.find('printing-jobs-heading').text()).toBe('Print queue');
    expect(s.params(LIST)).toEqual([{ sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.params(PRINTERS)).toEqual([{ limit: 100 }]);
    expect(s.prop('serverSide')).toBe(true);
  });

  it('names each job, its role, its printer, why it is where it is', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    expect(s.prop('rows')).toEqual(PAGE.rows);
    const columns = s.prop<DataTableColumn<JobOut>[]>('columns');
    expect(columns.map((c) => c.key)).toEqual(['document', 'usage', 'printer_id', 'status', 'attempts', 'created_at', 'detail']);
    const cell = (key: string, row: JobOut) => columns.find((c) => c.key === key)!.format!(undefined, row);
    expect([cell('document', QUEUED), cell('usage', QUEUED), cell('printer_id', QUEUED)]).toEqual(['Receipt T-000123', 'Receipt', 'Till']);
    expect([cell('document', FAILED), cell('printer_id', FAILED), cell('detail', FAILED)]).toEqual([
      'Barcode label Shampoo',
      'No printer',
      'Last error: out of paper',
    ]);
    expect(words(s.find('printing-jobs-status-j2').element)).toBe('Failed');
  });

  it('filters by status, role and printer on the server', async () => {
    const s = await setup();
    await s.result(PRINTERS, { rows: [{ id: 'p1', name: 'Till' }], total: 1, limit: 100, offset: 0 });
    const columns = s.prop<DataTableColumn<JobOut>[]>('columns');
    expect(columns.find((c) => c.key === 'printer_id')!.filter).toEqual({ type: 'select', options: [{ value: 'p1', label: 'Till' }] });
    s.table().vm.$emit('update:filters', { status: 'failed', usage: 'label', printer_id: 'p1' });
    await flush();
    await s.reopen();
    expect(s.params(LIST)).toEqual([{ status: 'failed', usage: 'label', printer_id: 'p1', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
  });

  it('whoever manages the queue retries a failed job and cancels what can be; nobody else', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    expect([s.actions(QUEUED), s.actions(FAILED), s.actions(DONE)]).toEqual([['retry', 'cancel'], ['retry', 'cancel'], []]);
    for (const session of [MANAGER, EMPLOYEE]) {
      const other = await setup({ session });
      await other.result(LIST, PAGE);
      expect(other.prop<DataTableAction<JobOut>[]>('actions')).toEqual([]);
    }
  });

  it('«Try again» sends it back to the queue and says so; a refusal is said', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    s.answer(200, { ...FAILED, status: 'pending' });
    s.table().vm.$emit('action', { actionId: 'retry', row: FAILED });
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/printing/jobs/retry', query: {}, body: { job_id: 'j2' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Sent back to the queue: the next device to connect will print it.');
    const message = 'Only a queued or failed job, or a sent one with no answer, goes back to the queue; this one is sent.';
    s.answer(409, { error: { code: 'printing.job_not_retryable', message } });
    s.table().vm.$emit('action', { actionId: 'retry', row: FAILED });
    await flush();
    expect(toastError).toHaveBeenCalledWith(message);
  });

  it('«Cancel» opens the window with the job', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    s.table().vm.$emit('action', { actionId: 'cancel', row: FAILED });
    await flush();
    expect(s.wrapper.findComponent(CancelJobModal).props()).toMatchObject({ open: true, job: FAILED });
  });
});

describe('JobsPage by the clock', () => {
  afterEach(() => vi.useRealTimers());

  it('a sent job that does not answer within its lease can be retried and cancelled, by itself', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
    vi.setSystemTime(new Date('2026-10-15T08:00:00Z'));
    const SENT = job('j4', { status: 'sent', attempts: 1, leased_until: '2026-10-15T08:00:20Z', retryable: false, cancellable: false });
    const s = await setup();
    await s.result(LIST, { rows: [SENT], total: 1, limit: 50, offset: 0 });
    expect(s.actions(SENT)).toEqual([]);
    const detail = s.prop<DataTableColumn<JobOut>[]>('columns').find((c) => c.key === 'detail')!;
    expect(detail.format!(undefined, SENT)).toBe('');
    vi.advanceTimersByTime(30_000);
    await flush();
    expect(s.actions(SENT)).toEqual(['retry', 'cancel']);
    const later = s.prop<DataTableColumn<JobOut>[]>('columns').find((c) => c.key === 'detail')!;
    expect(later.format!(undefined, SENT)).toBe('No answer from the device');
  });
});
