import { describe, it, expect, vi } from 'vitest';
import { buildComandaGroups, onKitchenOrderCreated } from './print-comanda';
import type { PrintRequest, PrintResult } from './print';

// La comanda sale al DISPARAR el pedido (ADR-0144), no al cobrar. Cada estación dice por dónde
// sale la suya: la plancha imprime (nadie mira una pantalla con las manos ocupadas) y la barra
// solo se muestra (el camarero se sirve solo; imprimir sería tirar papel).
//
// Lo que NUNCA puede pasar: que un fallo de impresora pare al camarero. En un bar lleno, bloquear
// es peor que imprimir dos veces — la comanda ya está en la BD y el KDS es la fuente de verdad.

// Las filas de `kitchen.orders.items` traen la cantidad en PUNTO FIJO 10⁶ (ADR-0147, kitchen
// >= 2.3 con la migración 005): 2 raciones = 2000000. El papel habla lógico.
const CROQUETAS = {
  product_name: 'Croquetas',
  quantity: 2_000_000,
  notes: 'sin gluten',
  station_id: 's-cocina',
  station_name: 'Cocina caliente',
  destination: 'printer',
  printer_role: 'kitchen',
};
const CANAS = {
  product_name: 'Cañas',
  quantity: 2_000_000,
  notes: '',
  station_id: 's-barra',
  station_name: 'Barra',
  destination: 'display',
  printer_role: 'bar',
};
const FLAN = {
  product_name: 'Flan',
  quantity: 1_000_000,
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
      { product_name: 'Alcachofas', quantity: 1_000_000, station_id: null, destination: 'both', printer_role: 'kitchen' },
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

describe('la cantidad del papel habla lógico, el cable habla µ (ADR-0147)', () => {
  it('2000000 µ se imprimen como «2» y media ración (500000 µ) como «0.5»', () => {
    const groups = buildComandaGroups([
      { ...CROQUETAS },
      { ...CROQUETAS, product_name: 'Gambas', quantity: 500_000, notes: '' },
    ]);
    const kitchen = groups.find((g) => g.role === 'kitchen')!;
    expect(kitchen.items.map((i) => [i.name, i.quantity])).toEqual([
      ['Croquetas', 2],
      ['Gambas', 0.5],
    ]);
  });
});

// ── Aviso a cocina ──────────────────────────────────────────────────────────────────────────────
// El papel es una copia; la pantalla del KDS es la fuente de verdad. Pero una pantalla que nadie
// mira no avisa de nada: en cocina caliente la tablet está apoyada, en otra vista o bloqueada. La
// notificación del SISTEMA es lo único que atraviesa eso.
describe('aviso al entrar una comanda', () => {
  it('notifica con la etiqueta de sala y el número de comanda', async () => {
    const print = vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' }));
    const notify = vi.fn<(t: string, b: string) => Promise<void>>(async () => {});

    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, notify });

    expect(notify).toHaveBeenCalledTimes(1);
    const [titulo, cuerpo] = notify.mock.calls[0]!;
    expect(titulo).toContain('Mesa 4');
    expect(cuerpo).toContain('C-018');
  });

  it('AVISA aunque la comanda sea solo de pantalla — que es justo cuando más falta hace', async () => {
    // Sin papel de por medio, la notificación es el ÚNICO aviso que hay. `buildComandaGroups`
    // descarta lo que es `display`, así que este caso salía por la puerta de atrás sin avisar.
    const soloPantalla = fakeClient({
      query: vi.fn(async (name: string) => {
        if (name === 'kitchen.orders.items')
          return [{ product_name: 'Cañas', quantity: 2_000_000, destination: 'display', printer_role: 'bar' }];
        if (name === 'kitchen.orders.get') return [{ label: 'Barra', round_number: 1, order_number: 'C-019' }];
        return [];
      }),
    });
    const print = vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'bar' }));
    const notify = vi.fn<(t: string, b: string) => Promise<void>>(async () => {});

    await onKitchenOrderCreated(soloPantalla, { order_id: 'k-2' }, { print, notify });

    expect(print).not.toHaveBeenCalled();
    expect(notify).toHaveBeenCalledTimes(1);
  });

  it('si la notificación falla, la comanda se imprime igual', async () => {
    // Misma regla que el papel: nada de lo accesorio puede tumbar la comanda.
    const print = vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' }));
    const notify = vi.fn<(t: string, b: string) => Promise<void>>(async () => {
      throw new Error('permiso denegado');
    });

    await expect(
      onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, notify }),
    ).resolves.toBeUndefined();
    expect(print).toHaveBeenCalledTimes(1);
  });

  it('sin `notify` cableado sigue funcionando como antes', async () => {
    const print = vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' }));
    await expect(
      onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print }),
    ).resolves.toBeUndefined();
    expect(print).toHaveBeenCalledTimes(1);
  });
});

// ── Lo que la fila SÍ trae y el papel perdía (hub#1156) ─────────────────────────────────────────
// `kitchen.orders.items` devuelve `modifiers`, `combo_ref` y `combo_name` desde kitchen 2.3.27,
// pero el shell copiaba a la línea sólo nombre/cantidad/notas. El KDS los pinta y la térmica no,
// que es justo al revés de lo que hace falta: en la plancha nadie mira una pantalla.
describe('lo que la línea arrastra al papel (hub#1156)', () => {
  it('un SUPLEMENTO llega a la hoja — «sin cebolla» es el plato que vuelve, no un adorno', () => {
    const groups = buildComandaGroups([{ ...CROQUETAS, modifiers: 'Sin cebolla', notes: '' }]);
    expect(groups[0].items[0]).toMatchObject({ name: 'Croquetas', modifiers: 'Sin cebolla' });
  });

  it('sin suplemento la línea NO gana un campo vacío (la hoja vieja se imprime igual)', () => {
    // El 99 % de las comandas no llevan suplemento: si les colásemos `modifiers: ''` cambiaríamos
    // la forma de `items` para todas, y `render_kitchen_order` pinta lo que es truthy.
    const groups = buildComandaGroups([{ ...CROQUETAS, notes: '' }]);
    expect(groups[0].items[0]).toEqual({ name: 'Croquetas', quantity: 2 });
    expect(groups[0].items[0]).not.toHaveProperty('modifiers');
  });

  it('los componentes de un MENÚ llevan su marca de menú a la hoja', () => {
    const groups = buildComandaGroups([
      { ...CROQUETAS, product_name: 'Gazpacho', quantity: 1_000_000, notes: '', combo_ref: 'c1', combo_name: 'Menú del día' },
      { ...CROQUETAS, product_name: 'Entrecot', quantity: 1_000_000, notes: '', combo_ref: 'c1', combo_name: 'Menú del día' },
    ]);
    expect(groups[0].items).toEqual([
      { name: 'Gazpacho', quantity: 1, combo_ref: 'c1', combo_name: 'Menú del día' },
      { name: 'Entrecot', quantity: 1, combo_ref: 'c1', combo_name: 'Menú del día' },
    ]);
  });

  it('una línea A LA CARTA no gana ningún campo de menú', () => {
    const groups = buildComandaGroups([{ ...CROQUETAS, notes: '', combo_ref: null, combo_name: '' }]);
    expect(groups[0].items[0]).toEqual({ name: 'Croquetas', quantity: 2 });
  });

  it('la marca del menú viaja a CADA hoja que recibe un componente (Simphony, opción 11)', () => {
    // El menú se reparte entre plancha y barra. Un cocinero que no lee «MENÚ» no sabe que su
    // entrecot va acoplado a un gazpacho, y lo saca cuando le viene bien.
    const groups = buildComandaGroups([
      { ...CROQUETAS, product_name: 'Entrecot', quantity: 1_000_000, notes: '', printer_role: 'kitchen', combo_ref: 'c1', combo_name: 'Menú del día' },
      { ...FLAN, product_name: 'Flan', notes: '', printer_role: 'bar', combo_ref: 'c1', combo_name: 'Menú del día' },
    ]);
    expect(groups).toHaveLength(2);
    for (const g of groups) {
      expect(g.items.every((i) => i.combo_ref === 'c1' && i.combo_name === 'Menú del día')).toBe(true);
    }
  });
});

describe('quién mandó la ronda sale EN EL PAPEL (hub#1410 · recorte de kitchen#63)', () => {
  // La mitad de kitchen#63 se hizo en la tarjeta del KDS; la del papel se quedó fuera porque su
  // productor está aquí, no en el módulo. El renderizador ESC/POS ya sabía pintarlo
  // (`escpos.rs`, campo `waiter`) y nadie se lo mandaba nunca.
  //
  // Por qué importa en el pase: cuando un plato sale mal, va tarde o le falta algo, cocina
  // necesita a QUIÉN llamar sin buscar a nadie por la sala. Toast, Square for Restaurants y
  // Lightspeed imprimen el «server» en la cabecera del chit por exactamente eso.
  //
  // El `waiter_id` de la comanda es OPACO (kitchen no une con `hub_user`, ADR-0192): el nombre lo
  // resuelve el consumidor por `hub.users.list`, que es lo que ya hace la tarjeta del KDS.
  function clientWithWaiter(users: unknown, over: Record<string, unknown> = {}) {
    const query = vi.fn(async (name: string) => {
      if (name === 'kitchen.orders.items') return [CROQUETAS];
      if (name === 'kitchen.orders.get') {
        return [{ id: 'k-1', label: 'Mesa 4', round_number: 2, order_number: 'C-018', waiter_id: 'u-7' }];
      }
      if (name === 'hub.users.list') {
        if (users instanceof Error) throw users;
        return users;
      }
      return [];
    });
    return { query, ...over } as never;
  }

  const okPrint = () =>
    vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' }));

  it('el papel lleva el NOMBRE de quien disparó la ronda', async () => {
    const print = okPrint();
    await onKitchenOrderCreated(
      clientWithWaiter([{ id: 'u-9', name: 'Marta' }, { id: 'u-7', name: 'Ana' }]),
      { order_id: 'k-1' },
      { print },
    );
    expect(print.mock.calls[0]![0].data?.waiter).toBe('Ana');
  });

  it('un `waiter_id` que el hub ya no lista NO saca un UUID por la impresora', async () => {
    // Un id crudo es PEOR que un hueco: el cocinero lo lee a dos metros, no puede usarlo y deja
    // de fiarse de la cabecera. Misma política que la tarjeta del KDS.
    const print = okPrint();
    await onKitchenOrderCreated(clientWithWaiter([{ id: 'u-9', name: 'Marta' }]), { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('waiter');
  });

  it('si `hub.users.list` falla, la comanda SALE IGUAL — sin camarero', async () => {
    // El papel no puede depender de una consulta de presentación: la comida se cocina igual.
    const print = okPrint();
    await onKitchenOrderCreated(clientWithWaiter(new Error('403')), { order_id: 'k-1' }, { print });
    expect(print).toHaveBeenCalledTimes(1);
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('waiter');
  });

  it('una ronda SIN camarero no le pregunta al hub por sus personas', async () => {
    // Una comanda vieja, o disparada sin sesión, no tiene a quién nombrar: preguntar por la lista
    // de personas en cada disparo sería una consulta por comanda a cambio de nada.
    const query = vi.fn(async (name: string) => {
      if (name === 'kitchen.orders.items') return [CROQUETAS];
      if (name === 'kitchen.orders.get') return [{ id: 'k-1', label: 'Mesa 4', round_number: 1, order_number: 'C-018' }];
      return [];
    });
    const print = okPrint();
    await onKitchenOrderCreated({ query } as never, { order_id: 'k-1' }, { print });
    expect(query.mock.calls.map((c) => c[0])).not.toContain('hub.users.list');
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('waiter');
  });
});
