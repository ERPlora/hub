import { describe, it, expect, vi } from 'vitest';
import { buildComandaGroups, onKitchenOrderCreated } from './print-comanda';
import type { PrintRequest, PrintResult } from './print';

// La comanda sale al DISPARAR el pedido (ADR-0144), no al cobrar. Cada estación dice por dónde
// sale la suya: la plancha imprime (nadie mira una pantalla con las manos ocupadas) y la barra
// solo se muestra (el camarero se sirve solo; imprimir sería tirar papel).
//
// Lo que NUNCA puede pasar: que un fallo de impresora pare al camarero. En un bar lleno, bloquear
// es peor que imprimir dos veces — la comanda ya está en la BD y el KDS es la fuente de verdad.

const CROQUETAS = {
  product_name: 'Croquetas',
  quantity: 2,
  notes: 'sin gluten',
  station_id: 's-cocina',
  station_name: 'Cocina caliente',
  destination: 'printer',
  printer_role: 'kitchen',
};
const CANAS = {
  product_name: 'Cañas',
  quantity: 2,
  notes: '',
  station_id: 's-barra',
  station_name: 'Barra',
  destination: 'display',
  printer_role: 'bar',
};
const FLAN = {
  product_name: 'Flan',
  quantity: 1,
  notes: '',
  station_id: 's-postres',
  station_name: 'Postres',
  destination: 'both',
  printer_role: 'bar',
};

describe('qué se manda a papel y a qué impresora', () => {
  it('agrupa por ROL de impresora, no por estación', () => {
    // Dos estaciones distintas pueden compartir impresora (postres sale por la de barra): son
    // UNA hoja, no dos. Si no, el camarero recoge dos papeles del mismo rollo.
    const groups = buildComandaGroups([CROQUETAS, CANAS, FLAN]);
    expect(groups.map((g) => g.role).sort()).toEqual(['bar', 'kitchen']);
    expect(groups.find((g) => g.role === 'bar')?.items.map((i) => i.name)).toEqual(['Flan']);
    expect(groups.find((g) => g.role === 'kitchen')?.items.map((i) => i.name)).toEqual(['Croquetas']);
  });

  it('lo que es solo pantalla NO va a la impresora', () => {
    // Las cañas son de una estación `display`: aparecen en el KDS y ahí se quedan.
    const groups = buildComandaGroups([CANAS]);
    expect(groups).toEqual([]);
  });

  it('un producto sin enrutar se imprime igual (en la duda, papel)', () => {
    // Producto nuevo que nadie ha enrutado todavía: si lo descartáramos, la comida no se cocina y
    // nadie se entera. Sale por la impresora de cocina, que es donde alguien lo verá.
    const groups = buildComandaGroups([
      { product_name: 'Alcachofas', quantity: 1, station_id: null, destination: 'both', printer_role: 'kitchen' },
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].role).toBe('kitchen');
  });
});

function fakeClient(over: Record<string, unknown> = {}) {
  return {
    query: vi.fn(async (name: string) => {
      if (name === 'kitchen.orders.items') return [CROQUETAS, CANAS];
      if (name === 'kitchen.orders.get') return [{ id: 'k-1', label: 'Mesa 4', round_number: 2, order_number: 'C-018' }];
      return [];
    }),
    ...over,
  } as never;
}

describe('impresión de la comanda al dispararla', () => {
  it('imprime una hoja por rol, desatendida y con la etiqueta de sala', async () => {
    const print = vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({
      via: 'bridge',
      role: 'kitchen',
    }));
    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print });

    expect(print).toHaveBeenCalledTimes(1); // solo cocina: la barra es de pantalla
    const req = print.mock.calls[0]![0];
    expect(req.role).toBe('kitchen');
    expect(req.documentType).toBe('kitchen_order');
    // Nadie está delante de la cocina para darle a "Imprimir" en un diálogo del navegador.
    expect(req.fallbackToBrowser).toBe(false);
    // La etiqueta es lo único que cocina sabe de la sala, y se imprime TAL CUAL (ADR-0144).
    expect(req.data?.label).toBe('Mesa 4');
    expect(req.data?.round_number).toBe(2);
    expect(req.data?.items).toEqual([{ name: 'Croquetas', quantity: 2, notes: 'sin gluten' }]);
    // Mismo disparo reimpreso = mismo trabajo: el Bridge lo deduplica en vez de sacar dos hojas.
    expect(req.jobId).toBe('kitchen-k-1-kitchen');
  });

  it('si la impresora falla, la comanda NO se cae y se puede reimprimir', async () => {
    // En un bar lleno bloquear al camarero es peor que imprimir dos veces. La comanda ya está en
    // la BD; el papel es una copia. Se avisa y se deja reintentar, pero nadie se para.
    const print = vi.fn(async () => {
      throw new Error('sin papel');
    });
    const onFailure = vi.fn();

    await expect(
      onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, onFailure }),
    ).resolves.toBeUndefined();

    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ orderId: 'k-1', role: 'kitchen', label: 'Mesa 4' });
  });

  it('sin impresora para ese rol avisa, no imprime a ciegas por otra', async () => {
    // `via: none` = el Bridge no tiene ninguna impresora con ese rol. Sacar la comanda de cocina
    // por la impresora de tiquets dejaría al camarero con el papel y a la cocina sin comida.
    const print = vi.fn(async () => ({ via: 'none' as const, role: 'kitchen', error: 'sin impresora con rol "kitchen"' }));
    const onFailure = vi.fn();
    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, onFailure });
    expect(onFailure).toHaveBeenCalledTimes(1);
  });

  it('una comanda sin líneas no imprime una hoja en blanco', async () => {
    const print = vi.fn();
    const client = fakeClient({ query: vi.fn(async () => []) });
    await onKitchenOrderCreated(client, { order_id: 'k-1' }, { print });
    expect(print).not.toHaveBeenCalled();
  });

  it('un evento sin comanda no hace nada', async () => {
    const print = vi.fn();
    await onKitchenOrderCreated(fakeClient(), {}, { print });
    expect(print).not.toHaveBeenCalled();
  });
});
