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
import { CLIENT_INSTANCE } from './client-instance';
import type { PrintRequest, PrintResult } from './print';

type Listener = (payload: unknown, meta?: { clientInstance?: string }) => void;

/** The minimum client: the sale event, the queries it reads and the drawer's hardware. */
function fakeClient(over: {
  devices?: () => Promise<{ role: string | null; ip: string | null; port?: number }[]>;
  settings?: Record<string, unknown>;
  saleFails?: boolean;
} = {}) {
  const listeners: Record<string, Listener[]> = {};
  const openDrawer = vi.fn(async () => undefined);
  const client = {
    on: (event: string, cb: Listener) => {
      (listeners[event] ??= []).push(cb);
      return () => {};
    },
    // The SDK door that also says which shell tab caused the event (hub#1980).
    onEvent: (event: string, cb: Listener) => {
      (listeners[event] ??= []).push(cb);
      return () => {};
    },
    query: vi.fn(async (name: string) => {
      if (name === 'printing.settings.get') return [over.settings ?? { auto_print_on_sale: 1 }];
      // The raw rows as `sales` serves them (hub#1921): money in minor units, quantity in
      // millionths, the payment method as a code. Printing THEM is the bug.
      if (name === 'sales.get') {
        if (over.saleFails) throw new Error('sales.get failed');
        return [{ id: '42', sale_number: '20260919-0001', subtotal: 983, tax_amount: 207, total: 1190, payment_method: 'Card', amount_tendered: 1190 }];
      }
      if (name === 'sales.lines') return [{ product_name: 'Acondicionador 300 ml', quantity: 1_000_000, line_total: 1190 }];
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
    // By default the sale was charged HERE, in this very tab — the case every test below is about.
    // hub#1980's tests pass another tab's instance, or none.
    emit: async (payload: unknown, meta: { clientInstance?: string } = { clientInstance: CLIENT_INSTANCE }) => {
      for (const cb of listeners['sale.completed'] ?? []) cb(payload, meta);
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

/** The paper the ticket screen's print button prints for the sale (hub#1921), in euros and words. */
const PAPER = {
  business_name: 'Salon Lucia SL',
  vat_number: 'B12345674',
  receipt_id: '20260919-0001',
  items: [{ name: 'Acondicionador 300 ml', quantity: 1, total: 11.9 }],
  subtotal: 9.83,
  tax_amount: 2.07,
  total: 11.9,
  payment_method: 'Tarjeta',
  paid: 11.9,
};

/** Where the shell gets that paper from: the sales module's viewer, here a stand-in. `complete` is
 *  whether the viewer's just-charged wait ended with the fiscal number and QR (hub#1867). */
function paperSource(complete = true) {
  return vi.fn(async (_saleId: string): Promise<{ document: Record<string, unknown>; complete: boolean }> => ({
    document: PAPER,
    complete,
  }));
}

describe('the ticket on payment is the paper the ticket screen prints (hub#1921)', () => {
  it('prints the document the sales module composes, never the raw sale row', async () => {
    const gate = fakeGate();
    const saleDocument = paperSource();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print, saleDocument });

    await emit({ sale_id: '42' });

    expect(saleDocument).toHaveBeenCalledWith('42');
    expect(gate.calls).toHaveLength(1);
    // «1x … 11.90», «TOTAL 11.90», «Pago: Tarjeta» — not «1000000x … 1190.00» nor «Pago: Card».
    expect(gate.calls[0]!.data).toEqual(PAPER);
  });

  it('when the paper cannot be composed nothing is printed and the till hears it, with the code', async () => {
    const gate = fakeGate();
    const onFailure = vi.fn();
    const saleDocument = vi.fn(async () => {
      throw new Error('sale_document_timeout');
    });
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print, onFailure, saleDocument });

    await emit({ sale_id: '42' });

    // Better no paper and a warning (the ticket screen reprints it) than a paper with wrong amounts.
    expect(gate.print).not.toHaveBeenCalled();
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ saleId: '42', error: 'sale_document_timeout' });
    // And says WHICH failure it is: the paper was never made (reprint it from the ticket screen), not
    // a printer that did not deliver — the till shows a sentence for it, never the code.
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ notComposed: true });
  });

  it('the drawer opens even when the ticket cannot be composed', async () => {
    // The cash has to go in the drawer whatever happens to the paper: the drawer never waited on
    // the ticket's content, only on the sale being read — and that read is not the shell's any more.
    const { client, openDrawer, emit } = fakeClient({
      devices: async () => [{ role: 'receipt', ip: '10.0.0.5', port: 9100 }],
      settings: { auto_print_on_sale: 1, open_drawer_on_sale: 1 },
      saleFails: true,
    });
    const saleDocument = vi.fn(async () => {
      throw new Error('sale_document_unavailable');
    });
    bootPrintOnSale(client, { print: fakeGate().print, saleDocument });

    await emit({ sale_id: '42' });

    expect(openDrawer).toHaveBeenCalledWith('network:10.0.0.5:9100');
  });
});

describe('the ticket on payment (hub#862)', () => {
  it('with the printer holding NO ROLE the ticket leaves through the door, which queues it', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

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
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(gate.calls[0]!.fallbackToBrowser).toBe(false);
    expect(gate.calls[0]!.html).toBeUndefined();
  });

  it('with no hardware on this device (PWA) the ticket ALSO leaves through the door', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient({
      devices: async () => { throw new Error('hardware_unavailable'); },
    });
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(gate.print).toHaveBeenCalledTimes(1);
  });

  it('when the door does NOT deliver it is reported (a ticket that never came out cannot be silent)', async () => {
    const gate = fakeGate({ via: 'browser', role: 'receipt', error: 'no printer' });
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print, onFailure, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ saleId: '42' });
    expect(onFailure.mock.calls[0]![0].notComposed).toBeUndefined();
  });

  it('when the door delivers (queue or printer) it keeps quiet', async () => {
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'bridge', role: 'receipt' }).print, onFailure, saleDocument: paperSource() });

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
    bootPrintOnSale(client, { print: gate.print, onFailure, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(onFailure).toHaveBeenCalledTimes(1);
    // The warning must say WHICH of the two it is: the ticket is safe in the queue and what is
    // missing is registering the printer — not the same thing as "it did not print".
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ saleId: '42', awaitingHost: true });
  });

  it('queued WITH somebody draining it keeps quiet (it comes out late, it is not lost)', async () => {
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'queue', role: 'receipt', awaitingHost: false }).print, onFailure, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(onFailure).not.toHaveBeenCalled();
  });

  it('queued and the runtime did NOT answer coverage keeps quiet (unknown is not "nobody")', async () => {
    // A warning invented over a well-built hub would show on every ticket and stop being read.
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'queue', role: 'receipt' }).print, onFailure, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(onFailure).not.toHaveBeenCalled();
  });

  it('with the setting off it prints nothing', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient({ settings: { auto_print_on_sale: 0 } });
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(gate.print).not.toHaveBeenCalled();
  });

  it('the drawer still opens through the printer holding the receipt role', async () => {
    const gate = fakeGate();
    const { client, openDrawer, emit } = fakeClient({
      devices: async () => [{ role: 'receipt', ip: '10.0.0.5', port: 9100 }],
      settings: { auto_print_on_sale: 1, open_drawer_on_sale: 1 },
    });
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(openDrawer).toHaveBeenCalledWith('network:10.0.0.5:9100');
  });

  it('with no receipt-role printer the drawer stays shut, but the ticket still prints', async () => {
    const gate = fakeGate();
    const { client, openDrawer, emit } = fakeClient({
      settings: { auto_print_on_sale: 1, open_drawer_on_sale: 1 },
    });
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(openDrawer).not.toHaveBeenCalled();
    expect(gate.print).toHaveBeenCalledTimes(1);
  });
});

// hub#1867 — the paper now waits for the invoice number and the AEAT QR, like the till screen does,
// with the viewer's 10 s ceiling. When a slow AEAT runs that ceiling out, the paper still goes out —
// a till is never left without it — but the cashier hears that the customer's copy lacks the QR and
// where the complete one is: the print button on the receipt screen.
describe('a receipt that went out before its VeriFactu QR (hub#1867)', () => {
  it('is printed, and the till hears it lacks the QR', async () => {
    const gate = fakeGate({ via: 'bridge', role: 'receipt' });
    const onFailure = vi.fn();
    const onPrintedWithoutFiscal = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print, onFailure, onPrintedWithoutFiscal, saleDocument: paperSource(false) });

    await emit({ sale_id: '42' });

    expect(gate.calls[0]!.data).toEqual(PAPER);
    expect(onPrintedWithoutFiscal).toHaveBeenCalledTimes(1);
    expect(onPrintedWithoutFiscal).toHaveBeenCalledWith('42');
    expect(onFailure, 'it did print: not a failure').not.toHaveBeenCalled();
  });

  it('a complete receipt raises no such warning', async () => {
    const onPrintedWithoutFiscal = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'bridge', role: 'receipt' }).print, onPrintedWithoutFiscal, saleDocument: paperSource(true) });

    await emit({ sale_id: '42' });

    expect(onPrintedWithoutFiscal).not.toHaveBeenCalled();
  });

  it('when the incomplete receipt did not come out either, the till hears only that it did not print', async () => {
    const onFailure = vi.fn();
    const onPrintedWithoutFiscal = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, {
      print: fakeGate({ via: 'none', role: 'receipt', error: 'no printer' }).print,
      onFailure,
      onPrintedWithoutFiscal,
      saleDocument: paperSource(false),
    });

    await emit({ sale_id: '42' });

    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onPrintedWithoutFiscal, 'one warning, the one that matters').not.toHaveBeenCalled();
  });

  it('queued with nobody to print it, the till hears only that it is waiting for a printer', async () => {
    // Nothing came out yet: «it came out without the QR» would be false, and a second toast on top
    // of «set up a printer» buries the one thing the cashier has to do.
    const onFailure = vi.fn();
    const onPrintedWithoutFiscal = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, {
      print: fakeGate({ via: 'queue', role: 'receipt', awaitingHost: true }).print,
      onFailure,
      onPrintedWithoutFiscal,
      saleDocument: paperSource(false),
    });

    await emit({ sale_id: '42' });

    expect(onFailure.mock.calls[0]![0]).toMatchObject({ awaitingHost: true });
    expect(onPrintedWithoutFiscal).not.toHaveBeenCalled();
  });
});

// ERPlora/sales#283 — the «Print receipt» switch of the charge sheet. The till sends the cashier's
// choice with the sale (`print_receipt`) and it wins over `auto_print_on_sale` for THAT sale, in
// both directions (Square/Toast: the setting is the switch's default). Absent — every other
// producer of sales — the setting decides exactly as before.
describe('the charge sheet «Print receipt» switch (sales#283)', () => {
  it('switched OFF with auto-print ON: no receipt', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient({ settings: { auto_print_on_sale: 1 } });
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42', print_receipt: false });

    expect(gate.print).not.toHaveBeenCalled();
  });

  it('switched ON with auto-print OFF: the receipt is printed', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient({ settings: { auto_print_on_sale: 0 } });
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42', print_receipt: true });

    expect(gate.print).toHaveBeenCalledTimes(1);
    expect(gate.calls[0].data).toEqual(PAPER);
  });

  it('with no choice in the event the setting still decides', async () => {
    for (const [setting, printed] of [[1, 1], [0, 0]] as const) {
      const gate = fakeGate();
      const { client, emit } = fakeClient({ settings: { auto_print_on_sale: setting } });
      bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

      await emit({ sale_id: '42', print_receipt: 'yes' });
      await emit({ sale_id: '43' });

      expect(gate.print).toHaveBeenCalledTimes(printed * 2);
    }
  });

  it('the switch is about the paper: the drawer opens whatever it says', async () => {
    const gate = fakeGate();
    const { client, openDrawer, emit } = fakeClient({
      devices: async () => [{ role: 'receipt', ip: '10.0.0.5', port: 9100 }],
      settings: { auto_print_on_sale: 1, open_drawer_on_sale: 1 },
    });
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42', print_receipt: false });

    expect(gate.print).not.toHaveBeenCalled();
    expect(openDrawer).toHaveBeenCalledWith('network:10.0.0.5:9100');
  });
});

// hub#1980 — two tills, each with its own receipt printer and «print on payment» on. Every open shell
// hears every `sale.completed` (one broadcast per hub), so the ticket came out at BOTH tills, and
// both papers were originals. The hub now stamps the frame with the shell tab that charged
// (`clientInstance`); the till prints — and opens its drawer — only for its own sales.
describe('only the till that charged prints the ticket and opens the drawer (hub#1980)', () => {
  const TILL_NEXT_DOOR = 'till-next-door-7c1e';

  function tillWithPrinterAndDrawer() {
    return fakeClient({
      devices: async () => [{ role: 'receipt', ip: '10.0.0.5', port: 9100 }],
      settings: { auto_print_on_sale: 1, open_drawer_on_sale: 1 },
    });
  }

  it('a sale charged at the till next door prints nothing here and leaves this drawer shut', async () => {
    const gate = fakeGate({ via: 'bridge', role: 'receipt' });
    const saleDocument = paperSource();
    const onFailure = vi.fn();
    const { client, openDrawer, emit } = tillWithPrinterAndDrawer();
    bootPrintOnSale(client, { print: gate.print, onFailure, saleDocument });

    await emit({ sale_id: '42' }, { clientInstance: TILL_NEXT_DOOR });

    expect(gate.print).not.toHaveBeenCalled();
    expect(saleDocument).not.toHaveBeenCalled();
    expect(openDrawer).not.toHaveBeenCalled();
    // Not this till's sale is not a failure: no warning either.
    expect(onFailure).not.toHaveBeenCalled();
  });

  it('the till that charged prints its one original and opens its drawer', async () => {
    const gate = fakeGate({ via: 'bridge', role: 'receipt' });
    const { client, openDrawer, emit } = tillWithPrinterAndDrawer();
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42' }, { clientInstance: CLIENT_INSTANCE });

    expect(gate.calls).toHaveLength(1);
    expect(gate.calls[0]!.jobId).toBe('sale-42');
    expect(openDrawer).toHaveBeenCalledWith(expect.any(String));
  });

  it('a sale no till charged (an API integration, a flow) prints at no till', async () => {
    const gate = fakeGate({ via: 'bridge', role: 'receipt' });
    const { client, openDrawer, emit } = tillWithPrinterAndDrawer();
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42' }, {});

    expect(gate.print).not.toHaveBeenCalled();
    expect(openDrawer).not.toHaveBeenCalled();
  });

  it('the cashier\'s «Print receipt» switch of the till next door does not make THIS till print', async () => {
    // sales#283's switch travels with the sale and wins over the setting — for the till that charged.
    const gate = fakeGate({ via: 'bridge', role: 'receipt' });
    const { client, emit } = fakeClient({ settings: { auto_print_on_sale: 0 } });
    bootPrintOnSale(client, { print: gate.print, saleDocument: paperSource() });

    await emit({ sale_id: '42', print_receipt: true }, { clientInstance: TILL_NEXT_DOOR });

    expect(gate.print).not.toHaveBeenCalled();
  });
});

// hub#2239 — the till used to paint the door's reason as it came («el runtime rechazó el encolado»,
// or the literal «sin impresora» on a hub in English). The reason is for whoever diagnoses the till,
// not for the cashier: it travels as a CODE and is written to the log; the sentence is the notice's.
describe('the reason a receipt did not print is for the log, not for the till (hub#2239)', () => {
  it('a door that gives no reason still hands over a code, not a sentence in one language', async () => {
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'none', role: 'receipt' }).print, onFailure, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0].error).toMatch(/^[a-z][a-z_]*$/);
  });

  it('the door’s own reason is written to the log, with the sale', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    try {
      const { client, emit } = fakeClient();
      const gate = fakeGate({ via: 'none', role: 'receipt', error: 'el runtime rechazó el encolado' });
      bootPrintOnSale(client, { print: gate.print, onFailure: vi.fn(), saleDocument: paperSource() });

      await emit({ sale_id: '42' });

      const logged = warn.mock.calls.map((c) => c.map(String).join(' '));
      expect(logged.some((l) => l.includes('el runtime rechazó el encolado') && l.includes('42'))).toBe(true);
    } finally {
      warn.mockRestore();
    }
  });

  it('so is the reason the paper could not be composed', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    try {
      const { client, emit } = fakeClient();
      const saleDocument = vi.fn(async () => {
        throw new Error('sale_document_timeout');
      });
      bootPrintOnSale(client, { print: fakeGate().print, onFailure: vi.fn(), saleDocument });

      await emit({ sale_id: '42' });

      const logged = warn.mock.calls.map((c) => c.map(String).join(' '));
      expect(logged.some((l) => l.includes('sale_document_timeout') && l.includes('42'))).toBe(true);
    } finally {
      warn.mockRestore();
    }
  });
});

// hub#2494 — the till's own printer is switched off or out of paper: the door now says so
// (`printerFailed`) instead of «done». The till hears it and gets a way to print it again right
// there (Square, Toast, Lightspeed), not «go and find the sale».
describe('a receipt whose printer did not answer (hub#2494)', () => {
  const DEAD: PrintResult = { via: 'none', role: 'receipt', error: 'unreachable: connection refused', printerFailed: true };

  it('is reported as a printer failure, with a Retry that prints the same receipt again', async () => {
    const answers: PrintResult[] = [DEAD, { via: 'bridge', role: 'receipt' }];
    const print = vi.fn(async (_req: PrintRequest) => answers.shift()!);
    const onFailure = vi.fn();
    const { client, emit, openDrawer } = fakeClient({ settings: { auto_print_on_sale: 1, open_drawer_on_sale: 1 }, devices: async () => [{ role: 'receipt', ip: '10.0.0.5', port: 9100 }] });
    bootPrintOnSale(client, { print, onFailure, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(onFailure).toHaveBeenCalledTimes(1);
    const failure = onFailure.mock.calls[0]![0];
    expect(failure).toMatchObject({ saleId: '42', printerFailed: true });
    expect(typeof failure.retry).toBe('function');

    await failure.retry();

    expect(print).toHaveBeenCalledTimes(2);
    expect(print.mock.calls[1]![0]).toMatchObject({ role: 'receipt', jobId: 'sale-42', data: PAPER });
    // Printed this time: no second warning, and Retry is about the paper — the drawer stays as it was.
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(openDrawer).toHaveBeenCalledTimes(1);
  });

  it('a Retry that fails again warns again, with its own Retry', async () => {
    const print = vi.fn(async (_req: PrintRequest) => DEAD);
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print, onFailure, saleDocument: paperSource() });

    await emit({ sale_id: '42' });
    await onFailure.mock.calls[0]![0].retry();

    expect(onFailure).toHaveBeenCalledTimes(2);
    expect(onFailure.mock.calls[1]![0]).toMatchObject({ saleId: '42', printerFailed: true });
    expect(typeof onFailure.mock.calls[1]![0].retry).toBe('function');
  });

  it('a receipt with no printer and no queue at all is not a printer failure: no Retry to offer', async () => {
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'none', role: 'receipt', error: 'no printer' }).print, onFailure, saleDocument: paperSource() });

    await emit({ sale_id: '42' });

    expect(onFailure.mock.calls[0]![0].printerFailed).toBeUndefined();
    expect(onFailure.mock.calls[0]![0].retry).toBeUndefined();
  });
});
