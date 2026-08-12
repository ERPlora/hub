// hub#862 — «Imprimir ticket al cobrar» estaba ON, la impresora ONLINE… y no salía papel ni había
// aviso, y el log del hub no tenía UNA línea de la cola de impresión.
//
// La causa: este fichero NO pasaba por la puerta global (`erplora.print`). Resolvía él mismo
// rol→impresora y llamaba a `peripherals.print` directo, así que:
//   - impresora descubierta pero SIN ROL (el caso de QA) → `receiptPrinterId` undefined → los dos
//     `if` en falso → **return silencioso**: ni Bridge, ni cola, ni navegador, ni aviso;
//   - `getDevices()` que lanza (PWA en el navegador) → `catch { return; }` → lo mismo.
// Y la cola del hub —que existe justo para esto— no se usaba nunca por este camino.
import { describe, it, expect, vi } from 'vitest';

import { bootPrintOnSale } from './print-on-sale';
import type { PrintRequest, PrintResult } from './print';

type Listener = (payload: unknown) => void;

/** Cliente mínimo: el evento de venta, las queries que lee y el hardware del cajón. */
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
      // El listener es sincrónico y lanza el trabajo asíncrono: se le da un turno para acabar.
      await new Promise((r) => setTimeout(r, 0));
    },
  };
}

/** La puerta global, espiada: qué se le pidió imprimir y qué contestó. */
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

describe('tique al cobrar (hub#862)', () => {
  it('con la impresora SIN ROL el tique sale por la puerta global, que lo encola', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(gate.calls).toHaveLength(1);
    expect(gate.calls[0]!.role).toBe('receipt');
    expect(gate.calls[0]!.documentType).toBe('receipt');
    // Idempotencia: el mismo tique reimpreso es UN trabajo, no dos papeles.
    expect(gate.calls[0]!.jobId).toBe('sale-42');
    // El documento va ESTRUCTURADO (hub#501): lo que lee el renderizador ESC/POS, no HTML.
    expect(gate.calls[0]!.data).toMatchObject({ items: expect.anything() });
  });

  it('sin hardware en este equipo (PWA) el tique TAMBIÉN sale por la puerta', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient({
      devices: async () => { throw new Error('hardware_unavailable'); },
    });
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(gate.print).toHaveBeenCalledTimes(1);
  });

  it('si la puerta NO entrega, se avisa (un tique que no sale no puede ser silencioso)', async () => {
    const gate = fakeGate({ via: 'browser', role: 'receipt', error: 'sin impresora' });
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: gate.print, onFailure });

    await emit({ sale_id: '42' });

    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ saleId: '42' });
  });

  it('si la puerta entrega (cola o impresora) no molesta con avisos', async () => {
    const onFailure = vi.fn();
    const { client, emit } = fakeClient();
    bootPrintOnSale(client, { print: fakeGate({ via: 'bridge', role: 'receipt' }).print, onFailure });

    await emit({ sale_id: '42' });

    expect(onFailure).not.toHaveBeenCalled();
  });

  it('con el ajuste apagado no imprime nada', async () => {
    const gate = fakeGate();
    const { client, emit } = fakeClient({ settings: { auto_print_on_sale: 0 } });
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(gate.print).not.toHaveBeenCalled();
  });

  it('el cajón sigue abriéndose por la impresora del rol receipt', async () => {
    const gate = fakeGate();
    const { client, openDrawer, emit } = fakeClient({
      devices: async () => [{ role: 'receipt', ip: '10.0.0.5', port: 9100 }],
      settings: { auto_print_on_sale: 1, open_drawer_on_sale: 1 },
    });
    bootPrintOnSale(client, { print: gate.print });

    await emit({ sale_id: '42' });

    expect(openDrawer).toHaveBeenCalledWith('network:10.0.0.5:9100');
  });

  it('sin impresora con rol receipt el cajón no se abre, pero el tique se imprime igual', async () => {
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
