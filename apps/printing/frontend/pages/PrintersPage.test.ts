// Printing → Printers (PRINTING-F01, F03–F05, F19; WORKBOOK «Pantallas · Impresoras»): the intro, the print
// queue's summary, and the business's printers, live, by name — Name, Role, Connection, Address, Paper,
// Status (with the last error) and Active —, with «Add printer», «Edit», «Test» and «Deactivate»/«Activate»
// by permission. «Test» queues the test page and says so; a refusal is said in the server's words.
import { DataTable, type DataTableAction, type DataTableColumn } from '@erplora/ui/components';
import { AppPage, toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, flush, MANAGER, type MountOptions, mountPrinting, words } from '../__tests__/mount-printing';
import PrinterModal from '../components/PrinterModal.vue';
import QueueSummary from '../components/QueueSummary.vue';
import type { PrinterOut } from '../operations';
import PrintersPage from './PrintersPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

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

const LIST = 'printing.printer.list';
const printer = (id: string, more: Partial<PrinterOut> = {}): PrinterOut => ({
  id,
  name: 'Till',
  kind: 'network',
  address: '192.168.1.50',
  port: 9100,
  paper_width: 80,
  usage: 'receipt',
  is_active: true,
  target: 'network:192.168.1.50:9100',
  oldest_pending_at: null,
  state: 'ready',
  pending: 0,
  last_printed_at: null,
  last_failed_at: null,
  last_error: '',
  created_at: '2026-10-14T08:00:00Z',
  ...more,
});
const TILL = printer('p1');
const KITCHEN = printer('p2', { name: 'Kitchen', usage: 'kitchen', kind: 'bluetooth', address: 'AA:BB:CC:DD:EE:FF', port: null, paper_width: 58, state: 'failing', last_failed_at: '2026-10-14T09:00:00Z', last_error: 'out of paper' });
const OFFICE = printer('p3', { name: 'Office', kind: 'system', address: '', port: null, is_active: false, state: 'inactive' });
const PAGE = { rows: [KITCHEN, OFFICE, TILL], total: 3, limit: 100, offset: 0 };

async function setup(options: MountOptions = {}) {
  const m = await mountPrinting(PrintersPage, { path: '/printing/printers', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T,>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const actions = (row: PrinterOut) =>
    prop<DataTableAction<PrinterOut>[]>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => a.id);
  return { ...m, table, prop, actions };
}

describe('PrintersPage', () => {
  it('is Printing’s page: its tabs, the intro, the queue’s summary and the printers', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Printing');
    expect((page.props('tabs') as Array<{ id: string }>).map((tab) => tab.id)).toEqual(['printers', 'jobs', 'settings']);
    expect(s.find('printing-printers-intro').text()).toBe("Add the business's printers, say what each one prints and check that paper comes out.");
    expect(s.wrapper.findComponent(QueueSummary).exists()).toBe(true);
    expect(s.find('printing-printers-heading').text()).toBe('Printers');
    expect(s.find('printing-printers-app-note').exists()).toBe(true);
    expect(s.params(LIST)).toEqual([{ limit: 100 }]);
  });

  it('paints each printer’s role, connection, address, paper, status and last error', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    expect(s.prop('rows')).toEqual(PAGE.rows);
    const columns = s.prop<DataTableColumn<PrinterOut>[]>('columns');
    expect(columns.map((c) => c.key)).toEqual(['name', 'usage', 'kind', 'address', 'paper_width', 'state', 'is_active']);
    const cell = (key: string, row: PrinterOut) => columns.find((c) => c.key === key)!.format!(row[key as keyof PrinterOut], row);
    expect([cell('usage', KITCHEN), cell('kind', KITCHEN), cell('address', KITCHEN), cell('paper_width', KITCHEN)]).toEqual([
      'Kitchen',
      'Bluetooth',
      'AA:BB:CC:DD:EE:FF',
      '58 mm',
    ]);
    expect([cell('address', TILL), cell('paper_width', OFFICE), cell('is_active', OFFICE)]).toEqual(['192.168.1.50:9100', 'A4', 'No']);
    expect(words(s.find('printing-printers-state-p2').element)).toBe('With errors Last error: out of paper');
    expect(words(s.find('printing-printers-state-p1').element)).toBe('Ready');
  });

  it('the owner and the manager add, edit, test and deactivate; the employee only tests', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    expect(s.prop('addable')).toBe(true);
    expect(s.actions(TILL)).toEqual(['edit', 'test', 'toggle']);
    expect(s.actions(OFFICE)).toEqual(['edit', 'toggle']);
    const manager = await setup({ session: MANAGER });
    await manager.result(LIST, PAGE);
    expect(manager.actions(TILL)).toEqual(['edit', 'test', 'toggle']);
    const employee = await setup({ session: EMPLOYEE });
    await employee.result(LIST, PAGE);
    expect(employee.prop('addable')).toBe(false);
    expect(employee.actions(TILL)).toEqual(['test']);
  });

  it('«Test» queues the test page and says so; a refusal is said', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    s.answer(201, { id: 'j1', kind: 'test_page' });
    s.table().vm.$emit('action', { actionId: 'test', row: TILL });
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/printing/printers/test', query: {}, body: { printer_id: 'p1' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Test page sent to the queue of Till.');
    s.answer(409, { error: { code: 'printing.printer_inactive', message: 'That printer is inactive: activate it to test it.' } });
    s.table().vm.$emit('action', { actionId: 'test', row: TILL });
    await flush();
    expect(toastError).toHaveBeenCalledWith('That printer is inactive: activate it to test it.');
  });

  it('deactivates and activates a printer and says so', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    s.answer(200, { ...TILL, is_active: false });
    s.table().vm.$emit('action', { actionId: 'toggle', row: TILL });
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/printing/printers/update', query: {}, body: { printer_id: 'p1', is_active: false } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Printer deactivated');
  });

  it('adds and edits through the printer window', async () => {
    const s = await setup();
    await s.result(LIST, PAGE);
    s.table().vm.$emit('add');
    await flush();
    expect(s.wrapper.findComponent(PrinterModal).props()).toMatchObject({ open: true, printer: null });
    s.table().vm.$emit('action', { actionId: 'edit', row: KITCHEN });
    await flush();
    expect(s.wrapper.findComponent(PrinterModal).props()).toMatchObject({ open: true, printer: KITCHEN });
  });
});

describe('PrintersPage by the clock', () => {
  afterEach(() => vi.useRealTimers());

  it('a printer whose oldest job has waited over a minute turns «Waiting» by itself', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
    vi.setSystemTime(new Date('2026-10-15T08:00:00Z'));
    const s = await setup();
    await s.result(LIST, { rows: [{ ...TILL, pending: 1, oldest_pending_at: '2026-10-15T07:59:30Z' }], total: 1, limit: 100, offset: 0 });
    expect(words(s.find('printing-printers-state-p1').element)).toBe('Ready');
    vi.advanceTimersByTime(60_000);
    await flush();
    expect(words(s.find('printing-printers-state-p1').element)).toBe('Waiting');
  });
});

describe('PrintersPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
