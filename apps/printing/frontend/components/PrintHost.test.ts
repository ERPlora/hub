// Printing's piece beside the pane (PRINTING-F18, F13): inside the installed app, the device set up to print here keeps
// the hub's `/ws/print` open for the active printers of its registration («This device» of Printing → Devices), followed
// live — set up, changed or retired from any device —, and a drawer that does not open says so on screen (hub#2724). In
// a browser it reads nothing and opens nothing. A fake socket and a fake app bridge stand in; the e2e drives the real
// channel.
import { toastError } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, mountPrinting } from '../__tests__/mount-printing';
import type { DeviceOut } from '../operations';
import PrintHost from './PrintHost.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
}));

const OP = 'printing.device.list';

class FakeSocket {
  static made: FakeSocket[] = [];
  sent: Record<string, unknown>[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.made.push(this);
  }
  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close(): void {
    this.closed = true;
  }
  receive(frame: Record<string, unknown>): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

function device(more: Partial<DeviceOut> = {}): DeviceOut {
  return {
    id: '0192f0a4-0000-7000-8000-00000000d001',
    name: 'Counter till',
    printers: [
      { id: 'p-receipt', name: 'Till printer', usage: 'receipt', is_active: true },
      { id: 'p-off', name: 'Old printer', usage: 'kitchen', is_active: false },
    ],
    registered_at: '2026-10-30T10:00:00Z',
    registered_by: 'Ana',
    last_seen_at: null,
    this_device: true,
    ...more,
  };
}

const page = (...rows: DeviceOut[]) => ({ rows, total: rows.length, limit: 100, offset: 0 });

let invoke: ReturnType<typeof vi.fn>;

beforeEach(() => {
  FakeSocket.made = [];
  vi.stubGlobal('WebSocket', FakeSocket);
  vi.mocked(toastError).mockClear();
  invoke = vi.fn(async () => null);
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete (window as { __TAURI__?: unknown }).__TAURI__;
});

const inTheApp = () => ((window as { __TAURI__?: unknown }).__TAURI__ = { core: { invoke } });

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountPrinting(PrintHost, { locale });
  await m.live();
  return m;
}

describe('PrintHost', () => {
  it('in a browser reads nothing and opens nothing, and paints nothing', async () => {
    const s = await mountPrinting(PrintHost);
    await flush();
    expect(s.params(OP)).toEqual([]);
    expect(FakeSocket.made).toEqual([]);
    expect(s.find('printing-print-host').element.textContent).toBe('');
  });

  it('inside the app, a device not set up here opens nothing', async () => {
    inTheApp();
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 100 }]);
    await s.result(OP, page(device({ this_device: false })));
    expect(FakeSocket.made).toEqual([]);
  });

  it("a device set up says hello on the page's host with its own id and the active printers of its registration", async () => {
    inTheApp();
    const s = await setup();
    await s.result(OP, page(device({ this_device: false, id: 'other' }), device()));
    expect(FakeSocket.made.map((socket) => socket.url)).toEqual([`ws://${window.location.host}/ws/print`]);
    FakeSocket.made[0].onopen?.();
    expect(FakeSocket.made[0].sent).toEqual([{ type: 'hello', deviceId: s.client.deviceId, printers: ['p-receipt'] }]);
  });

  it('a device retired from another device stops printing at once, and set up again prints again', async () => {
    inTheApp();
    const s = await setup();
    await s.result(OP, page(device()));
    await s.result(OP, page(), {}, 2);
    expect(FakeSocket.made[0].closed).toBe(true);
    await s.result(OP, page(device()), {}, 3);
    expect(FakeSocket.made).toHaveLength(2);
    expect(FakeSocket.made[1].closed).toBe(false);
  });

  it('a device whose printers were all switched off prints for nothing: the channel closes', async () => {
    inTheApp();
    const s = await setup();
    await s.result(OP, page(device()));
    await s.result(OP, page(device({ printers: [{ id: 'p-receipt', name: 'Till printer', usage: 'receipt', is_active: false }] })), {}, 2);
    expect(FakeSocket.made[0].closed).toBe(true);
    expect(FakeSocket.made).toHaveLength(1);
  });

  it.each([
    ['en', 'The cash drawer did not open: check that “Till printer” is on and connected.'],
    ['es', 'El cajón no se ha abierto: comprueba que «Till printer» está encendida y conectada.'],
  ] as const)('a drawer that does not open says so on screen, naming its printer (%s)', async (locale, text) => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    invoke.mockImplementation(async (command: string) => {
      if (command === 'erplora_open_drawer') throw 'printer_unreachable';
      return null;
    });
    inTheApp();
    const s = await setup(locale);
    await s.result(OP, page(device()));
    const socket = FakeSocket.made[0];
    socket.onopen?.();
    socket.receive({ type: 'ready', deviceId: s.client.deviceId, roles: ['receipt'], heartbeatSeconds: 30 });
    socket.receive({
      type: 'job',
      jobId: 'job-1',
      role: 'receipt',
      kind: 'document',
      documentType: 'receipt',
      document: { total: '12.00' },
      format: 'receipt',
      copies: 1,
      openDrawer: true,
      printerId: 'p-receipt',
      target: 'network:192.168.1.50:9100',
    });
    await flush();
    expect(invoke.mock.calls.map(([command]) => command)).toEqual(['erplora_print', 'erplora_open_drawer']);
    expect(toastError).toHaveBeenCalledWith(text);
    // The paper came out: the hub hears it, so the ticket is not printed again.
    expect(socket.sent).toContainEqual({ type: 'done', jobId: 'job-1' });
    s.wrapper.unmount();
  });

  it('a drawer of a printer it does not name still says so', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    invoke.mockImplementation(async () => {
      throw 'printer_unreachable';
    });
    inTheApp();
    const s = await setup();
    await s.result(OP, page(device()));
    const socket = FakeSocket.made[0];
    socket.onopen?.();
    socket.receive({ type: 'ready', deviceId: s.client.deviceId, roles: ['receipt'], heartbeatSeconds: 30 });
    socket.receive({ type: 'job', jobId: 'job-2', role: 'receipt', kind: 'drawer', printerId: 'gone', target: 'network:10.0.0.1:9100' });
    await flush();
    expect(toastError).toHaveBeenCalledWith('The cash drawer did not open: check that its printer is on and connected.');
    s.wrapper.unmount();
  });

  it('unmounted (the person signs out), the channel closes', async () => {
    inTheApp();
    const s = await setup();
    await s.result(OP, page(device()));
    s.wrapper.unmount();
    expect(FakeSocket.made[0].closed).toBe(true);
  });
});
