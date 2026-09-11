// hub#862 — «print the ticket on payment» was ON, the printer was ONLINE… and no paper came out, no
// warning appeared, and the hub's log did not have ONE line about the print queue.
//
// The cause: this file did not go through the global door (`erplora.print`). It resolved
// role→printer itself and called `peripherals.print` directly, so:
//   - a discovered printer with NO ROLE (the QA case) → `receiptPrinterId` undefined → both `if`s
//     false → **silent return**: no bridge, no queue, no browser, no warning;
//   - `getDevices()` throwing (the PWA in a browser) → `catch { return; }` → the same.
// And the hub's queue — which exists for exactly this — was never used along this path.
import { describe, it, expect, vi } from 'vitest';

import { bootPrintOnSale } from './print-on-sale';
import type { PrintRequest, PrintResult } from './print';

type Listener = (payload: unknown) => void;

/** The minimum client: the sale event, the queries it reads and the drawer's hardware. */
function fakeClient(over: {
  devices?: () => Promise<{ role: string | null; ip: string | null; port?: number }[]>;
  settings?: Record<string, unknown>;
} = {}) {
  const listeners: Record<string, Listener[]> = {};
  const openDrawer = vi.fn(async () => undefined);
  const client = {
    on: (event: string, cb: Listener) => {
      (listeners[event] ??= []).push(cb);
      return () => {};
    },
    query: vi.fn(async (name: string) => {
      if (name === 'printing.settings.get') return [over.settings ?? { auto_print_on_sale: 1 }];
      if (name === 'sales.get') return [{ id: '42', total: 1250, series: 'F', number: 7 }];
      if (name === 'sales.lines') return [{ product_name: 'Café', quantity: 1_000_000, unit_price: 1250 }];
      return [];
    }),
    peripherals: {
      getDevices: vi.fn(over.devices ?? (async () => [{ role: null, ip: '192.168.100.196', port: 9100 }])),
      print: vi.fn(async () => undefined),
      openDrawer,
    },
  };
  return {
    client: client as never,
    openDrawer,
    emit: async (payload: unknown) => {
      for (const cb of listeners['sale.completed'] ?? []) cb(payload);
      // The listener is synchronous and fires async work: give it a turn to finish.
      await new Promise((r) => setTimeout(r, 0));
    },
  };
}

/** The global door, spied on: what it was asked to print and what it answered. */
function fakeGate(result: PrintResult = { via: 'queue', role: 'receipt' }) {
  const calls: PrintRequest[] = [];
  return {
    calls,
    print: vi.fn(async (req: PrintRequest) => {
      calls.push(req);
      return result;
    }),
  };
}

describe('the ticket on payment (hub#862)', () => {
  it('with the printer holding NO ROLE the ticket leaves through the door, which queues it', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(gate.calls).toHaveLength(1);
    expect(gate.calls[0]!.role).toBe('receipt');
    expect(gate.calls[0]!.documentType).toBe('receipt');
    // Idempotency: the same ticket reprinted is ONE job, not two pieces of paper.
    expect(gate.calls[0]!.jobId).toBe('sale-42');
    // The document travels STRUCTURED (hub#501): what the ESC/POS renderer reads, never HTML.
    expect(gate.calls[0]!.data).toMatchObject({ items: expect.anything() });
  });

  it('is UNATTENDED printing: it never opens the browser dialog', async () => {
    // Nobody asked to print: the sale was paid. A browser dialog here would print the APP on a sheet
    // (this path carries no document `html`) and leave the till waiting for a click. With nowhere to
    // print, it warns — the same rule as the kitchen docket (`print-comanda`).
    const gate = fakeGate();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(gate.calls[0]!.fallbackToBrowser).toBe(false);
    expect(gate.calls[0]!.html).toBeUndefined();
  });

  it('with no hardware on this device (PWA) the ticket ALSO leaves through the door', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient({
      devices: async () => { throw new Error('hardware_unavailable'); },
    });
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(gate.print).toHaveBeenCalledTimes(1);
  });

  it('when the door does NOT deliver it is reported (a ticket that never came out cannot be silent)', async () => {
    const gate = fakeGate({ via: 'browser', role: 'receipt', error: 'no printer' });
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print, onFailure });

    await emit({ sale_id: '42' });

    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ saleId: '42' });
  });

  it('when the door delivers (queue or printer) it keeps quiet', async () => {
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'bridge', role: 'receipt' }).print, onFailure });

    await emit({ sale_id: '42' });

    expect(onFailure).not.toHaveBeenCalled();
  });

  // hub#1731 — the SILENT failure. `via:'queue'` was read as delivered, so a hub with NO printer
  // registered took the money, said nothing, and no paper ever came out. Queued and drained is
  // "late"; queued with nobody registered for the station is "never", and the till has to hear it.
  it('queued with NOBODY draining the station warns: the paper is not coming out', async () => {
    const gate = fakeGate({ via: 'queue', role: 'receipt', awaitingHost: true });
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print, onFailure });

    await emit({ sale_id: '42' });

    expect(onFailure).toHaveBeenCalledTimes(1);
    // The warning must say WHICH of the two it is: the ticket is safe in the queue and what is
    // missing is registering the printer — not the same thing as "it did not print".
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ saleId: '42', awaitingHost: true });
  });

  it('queued WITH somebody draining it keeps quiet (it comes out late, it is not lost)', async () => {
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'queue', role: 'receipt', awaitingHost: false }).print, onFailure });

    await emit({ sale_id: '42' });

    expect(onFailure).not.toHaveBeenCalled();
  });

  it('queued and the runtime did NOT answer coverage keeps quiet (unknown is not "nobody")', async () => {
    // A warning invented over a well-built hub would show on every ticket and stop being read.
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'queue', role: 'receipt' }).print, onFailure });

    await emit({ sale_id: '42' });

    expect(onFailure).not.toHaveBeenCalled();
  });

  it('with the setting off it prints nothing', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient({ settings: { auto_print_on_sale: 0 } });
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(gate.print).not.toHaveBeenCalled();
  });

  it('the drawer still opens through the printer holding the receipt role', async () => {
    const gate = fakeGate();
    const { client, openDrawer, emit } = fakeClient({
      devices: async () => [{ role: 'receipt', ip: '10.0.0.5', port: 9100 }],
      settings: { auto_print_on_sale: 1, open_drawer_on_sale: 1 },
    });
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(openDrawer).toHaveBeenCalledWith('network:10.0.0.5:9100');
  });

  it('with no receipt-role printer the drawer stays shut, but the ticket still prints', async () => {
    const gate = fakeGate();
    const { client, openDrawer, emit } = fakeClient({
      settings: { auto_print_on_sale: 1, open_drawer_on_sale: 1 },
    });
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(openDrawer).not.toHaveBeenCalled();
    expect(gate.print).toHaveBeenCalledTimes(1);
  });
});
