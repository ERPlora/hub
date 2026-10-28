// Printing → Devices (PRINTING-F18; WORKBOOK «Pantallas · Dispositivos»): the devices set up to print, live, by
// name — Name (this device marked), Printers, Last seen and Set up by —, and what the device the page runs on
// does. Whoever sets up the printers sets this device up («Print from this device»), edits any device and
// retires it after asking; everybody else reads.
import { DataTable, type DataTableAction, type DataTableColumn } from '@erplora/ui/components';
import { AppPage, toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, errorFrame, flush, MANAGER, type MountOptions, mountPrinting, words } from '../__tests__/mount-printing';
import DeviceModal from '../components/DeviceModal.vue';
import type { DeviceOut, PrinterOut } from '../operations';
import DevicesPage from './DevicesPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
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
afterEach(() => {
  mocks.confirm.mockReset();
  vi.useRealTimers();
});

const LIST = 'printing.device.list';
const PRINTERS = 'printing.printer.list';
const device = (id: string, more: Partial<DeviceOut> = {}): DeviceOut => ({
  id,
  name: 'Counter till',
  printers: [],
  registered_at: '2026-10-15T07:00:00Z',
  registered_by: 'Ana',
  last_seen_at: null,
  this_device: false,
  ...more,
});
const THIS = device('d1', {
  printers: [
    { id: 'p1', name: 'Till', usage: 'receipt', is_active: true },
    { id: 'p2', name: 'Kitchen', usage: 'kitchen', is_active: false },
  ],
  last_seen_at: '2026-10-15T07:57:00Z',
  this_device: true,
});
const OTHER = device('d2', { name: 'Kitchen tablet', printers: [{ id: 'p2', name: 'Kitchen', usage: 'kitchen', is_active: false }] });
const page = (rows: DeviceOut[]) => ({ rows, total: rows.length, limit: 100, offset: 0 });
const PRINTER_ROWS = [
  { id: 'p1', name: 'Till', usage: 'receipt', is_active: true },
  { id: 'p2', name: 'Kitchen', usage: 'kitchen', is_active: false },
] as PrinterOut[];

async function setup(options: MountOptions = {}) {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
  vi.setSystemTime(new Date('2026-10-15T08:00:00Z'));
  const m = await mountPrinting(DevicesPage, { path: '/printing/devices', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T,>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const actions = (row: DeviceOut) =>
    prop<DataTableAction<DeviceOut>[]>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => a.id);
  return { ...m, table, prop, actions };
}

describe('DevicesPage', () => {
  it('is Printing’s page: its tabs, the intro and the devices that print', async () => {
    const s = await setup();
    const app = s.wrapper.findComponent(AppPage);
    expect(app.props('title')).toBe('Printing');
    expect((app.props('tabs') as Array<{ id: string }>).map((tab) => tab.id)).toEqual(['printers', 'devices', 'jobs', 'settings']);
    expect(s.find('printing-devices-heading').text()).toBe('Devices that print');
    expect(s.find('printing-devices-intro').text()).toBe(
      'Only the devices set up here print the queue, with anybody’s session: set up the one next to the printers from that device.',
    );
    expect(s.params(LIST)).toEqual([{ limit: 100 }]);
  });

  it('paints each device’s name, printers, last job asked and who set it up; this device is marked', async () => {
    const s = await setup();
    await s.result(LIST, page([THIS, OTHER]));
    expect(s.prop('rows')).toEqual([THIS, OTHER]);
    const columns = s.prop<DataTableColumn<DeviceOut>[]>('columns');
    expect(columns.map((c) => c.key)).toEqual(['name', 'printers', 'last_seen_at', 'registered_by']);
    const cell = (key: string, row: DeviceOut) => columns.find((c) => c.key === key)!.format!(row[key as keyof DeviceOut], row);
    expect([cell('printers', THIS), cell('last_seen_at', THIS), cell('last_seen_at', OTHER)]).toEqual([
      'Till, Kitchen (inactive)',
      '3\u00a0min ago',
      'Never',
    ]);
    expect(words(s.find('printing-devices-name-d1').element)).toBe('Counter till This device');
    expect(words(s.find('printing-devices-name-d2').element)).toBe('Kitchen tablet');
  });

  it('says what the device the page runs on prints, or that it prints nothing and who sets it up', async () => {
    const s = await setup();
    await s.result(LIST, page([THIS, OTHER]));
    expect(s.find('printing-devices-this').text()).toBe('This device prints for: Till, Kitchen (inactive).');
    const manager = await setup({ session: MANAGER });
    await manager.result(LIST, page([OTHER]));
    expect(manager.find('printing-devices-this').text()).toBe(
      'This device does not print yet: «Print from this device» sets it up with the printers it reaches.',
    );
    const employee = await setup({ session: EMPLOYEE });
    await employee.result(LIST, page([OTHER]));
    expect(employee.find('printing-devices-this').text()).toBe(
      'This device does not print here: someone who manages the printers sets it up from it.',
    );
  });

  it('whoever sets up printers sets this device up (once), edits and retires; the employee reads', async () => {
    const s = await setup({ session: MANAGER });
    await s.result(LIST, page([OTHER]));
    expect(s.prop('addable')).toBe(true);
    expect(s.prop<{ add: string }>('labels').add).toBe('Print from this device');
    expect(s.actions(OTHER)).toEqual(['edit', 'retire']);
    await s.result(LIST, page([THIS, OTHER]), {}, 2);
    expect(s.prop('addable')).toBe(false);
    const employee = await setup({ session: EMPLOYEE });
    await employee.result(LIST, page([THIS, OTHER]));
    expect(employee.prop('addable')).toBe(false);
    expect(employee.actions(THIS)).toEqual([]);
    expect(employee.wrapper.findComponent(DeviceModal).exists()).toBe(false);
  });

  it('sets up and edits through the device window, with the active printers of the business', async () => {
    const s = await setup();
    await s.result(LIST, page([OTHER]));
    expect(s.params(PRINTERS)).toEqual([{ limit: 100 }]);
    await s.result(PRINTERS, { rows: PRINTER_ROWS, total: 2, limit: 100, offset: 0 });
    s.table().vm.$emit('add');
    await flush();
    expect(s.wrapper.findComponent(DeviceModal).props()).toMatchObject({ open: true, device: null, printers: [PRINTER_ROWS[0]] });
    s.table().vm.$emit('action', { actionId: 'edit', row: OTHER });
    await flush();
    expect(s.wrapper.findComponent(DeviceModal).props()).toMatchObject({ open: true, device: OTHER });
  });

  it('retires a device after asking, and says so; «Back» leaves it', async () => {
    const s = await setup();
    await s.result(LIST, page([THIS, OTHER]));
    mocks.confirm.mockResolvedValueOnce(false);
    s.table().vm.$emit('action', { actionId: 'retire', row: OTHER });
    await flush();
    expect(s.sent()).toEqual([]);
    mocks.confirm.mockResolvedValueOnce(true);
    s.answer(200, OTHER);
    s.table().vm.$emit('action', { actionId: 'retire', row: OTHER });
    await flush();
    expect(mocks.confirm).toHaveBeenLastCalledWith({
      title: 'Retire Kitchen tablet?',
      message: 'It will print nothing more, and the jobs it has go back to the queue. To print from it again, set it up again from it.',
      confirmLabel: 'Yes, retire',
      cancelLabel: 'Back',
      tone: 'danger',
    });
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/printing/devices/retire', query: {}, body: { device_id: 'd2' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Device retired: it prints nothing more.');
    mocks.confirm.mockResolvedValueOnce(true);
    s.answer(404, { error: { code: 'printing.device_not_found', message: 'There is no device set up to print with that id.' } });
    s.table().vm.$emit('action', { actionId: 'retire', row: OTHER });
    await flush();
    expect(toastError).toHaveBeenCalledWith('There is no device set up to print with that id.');
  });

  it('shows loading, empty and error, and what blocks the page', async () => {
    const s = await setup();
    expect(s.prop('loading')).toBe(true);
    await s.result(LIST, page([]));
    expect(s.find('printing-devices-empty').exists()).toBe(true);
    expect(words(s.find('printing-devices-empty').element)).toBe(
      'No device prints yet. Set up the one next to the printers from that device.',
    );
    const failing = await setup();
    failing.net.lastStream().push(errorFrame(failing.subId(LIST), 'internal_error'));
    await flush();
    expect(failing.prop('error')).toBe('Could not load the devices.');
    const off = await setup();
    off.net.lastStream().push(errorFrame(off.subId(LIST), 'app_inactive'));
    await flush();
    expect(words(off.find('printing-devices-blocked').element)).toBe('Printing is not active in this business.');
    expect(off.find('printing-devices-this').exists()).toBe(false);
  });
});
