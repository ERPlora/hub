import { describe, it, expect, vi } from 'vitest';
import {
  bootPrintComanda,
  buildComandaGroups,
  comandaRoute,
  KITCHEN_NOTICE_PATH,
  onKitchenOrderCreated,
} from './print-comanda';
import { isNoticeTarget } from './notice-tap';
import { CLIENT_INSTANCE } from './client-instance';
import type { PrintRequest, PrintResult } from './print';
import { createI18n } from 'vue-i18n';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

// The notice's words come from the catalogue (hub#2171): this stub echoes the key and its params,
// so a test pins WHICH sentence is asked for, not its prose (ADR-0055).
const t = (key: string, params?: Record<string, unknown>) => (params ? `${key}${JSON.stringify(params)}` : key);

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

  it('encolada y SIN NADIE que drene esa estación avisa: el plato no se empieza', async () => {
    // hub#1731 — el mismo mutismo que el tique, con peor consecuencia: la comanda que nadie saca
    // es comida que no se cocina. `via:'queue'` se leía como entregada, así que en un local sin
    // impresora dada de alta la cocina no se enteraba de nada.
    const print = vi.fn(async () => ({ via: 'queue' as const, role: 'kitchen', awaitingHost: true }));
    const onFailure = vi.fn();
    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, onFailure });
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ orderId: 'k-1', role: 'kitchen', awaitingHost: true });
  });

  it('encolada CON alguien que la drena no avisa: sale tarde, no se pierde', async () => {
    const print = vi.fn(async () => ({ via: 'queue' as const, role: 'kitchen', awaitingHost: false }));
    const onFailure = vi.fn();
    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, onFailure });
    expect(onFailure).not.toHaveBeenCalled();
  });

  it('encolada sin que el runtime conteste la cobertura no avisa: «no lo sé» no es «no hay nadie»', async () => {
    const print = vi.fn(async () => ({ via: 'queue' as const, role: 'kitchen' }));
    const onFailure = vi.fn();
    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, onFailure });
    expect(onFailure).not.toHaveBeenCalled();
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

    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, notify, t });

    expect(notify).toHaveBeenCalledTimes(1);
    const [titulo, cuerpo] = notify.mock.calls[0]!;
    expect(titulo).toContain('Mesa 4');
    expect(cuerpo).toContain('C-018');
  });

  // hub#2305: tapping «Kitchen order — Table 4» opens the kitchen (its first tab is the display),
  // not the screen the tablet had been left on.
  it('leads to the kitchen, on the device that prints it and on the one that does not', async () => {
    const print = vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' }));
    const notify = vi.fn<(t: string, b: string, path?: string) => Promise<void>>(async () => {});

    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, notify, t });
    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, notify, t }, 'elsewhere');

    expect(KITCHEN_NOTICE_PATH).toBe('/m/kitchen');
    expect(isNoticeTarget(KITCHEN_NOTICE_PATH)).toBe(true);
    expect(notify.mock.calls.map((c) => c[2])).toEqual([KITCHEN_NOTICE_PATH, KITCHEN_NOTICE_PATH]);
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

    await onKitchenOrderCreated(soloPantalla, { order_id: 'k-2' }, { print, notify, t });

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
      onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, notify, t }),
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

// ── The notice speaks the app's language (hub#2171) ─────────────────────────────────────────────
// It used to be composed from fixed Spanish words, so a bar running the app in English got
// «Nueva comanda · Mesa 4 — 3 líneas». The label and the order number are the business's own
// data and travel as they are; only the words around them are translated.
describe('the kitchen order notice speaks the app language (hub#2171)', () => {
  const print = () => vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' }));

  it('asks the catalogue for the title with the floor label and for the line count', async () => {
    const notify = vi.fn<(t: string, b: string) => Promise<void>>(async () => {});

    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print: print(), notify, t });

    const [title, body] = notify.mock.calls[0]!;
    expect(title).toBe('print.comandaNoticeFor{"label":"Mesa 4"}');
    expect(body).toBe('C-018 · print.comandaNoticeLines{"n":2}');
  });

  it('with no floor label the title is the plain sentence, never a hole', async () => {
    const noLabel = fakeClient({
      query: vi.fn(async (name: string) => {
        if (name === 'kitchen.orders.items') return [CROQUETAS];
        if (name === 'kitchen.orders.get') return [{ label: '', round_number: 1, order_number: 'C-020' }];
        return [];
      }),
    });
    const notify = vi.fn<(t: string, b: string) => Promise<void>>(async () => {});

    await onKitchenOrderCreated(noLabel, { order_id: 'k-3' }, { print: print(), notify, t });

    expect(notify.mock.calls[0]![0]).toBe('print.comandaNotice');
  });

  it('the catalogue has the sentences in English and in Spanish, with the line count pluralised', async () => {
    const said = async (locale: 'en' | 'es', lines: unknown[]) => {
      // The options go in untyped: vue-i18n's inference over the whole catalogue is too deep for tsc.
      const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, es } } as never) as unknown as {
        global: { t: (key: string, params: Record<string, unknown>) => string };
      };
      const translate = i18n.global.t;
      const client = fakeClient({
        query: vi.fn(async (name: string) => {
          if (name === 'kitchen.orders.items') return lines;
          if (name === 'kitchen.orders.get') return [{ label: 'Mesa 4', round_number: 1, order_number: 'C-018' }];
          return [];
        }),
      });
      const notify = vi.fn<(t: string, b: string) => Promise<void>>(async () => {});
      await onKitchenOrderCreated(client, { order_id: 'k-1' }, {
        print: print(),
        notify,
        t: (key, params) => translate(key, params ?? {}),
      });
      return notify.mock.calls[0]!;
    };

    const [enTitle, enOne] = await said('en', [CROQUETAS]);
    const [esTitle, esOne] = await said('es', [CROQUETAS]);
    const [, enTwo] = await said('en', [CROQUETAS, FLAN]);

    // A key missing from the catalogue comes back as the key itself.
    for (const s of [enTitle, enOne, esTitle, esOne, enTwo]) {
      expect(s).not.toMatch(/comandaNotice/);
      expect(s).not.toContain('{');
    }
    expect(enTitle).toContain('Mesa 4');
    expect(enOne).toContain('C-018');
    // The English app does not say it in Spanish.
    expect(enTitle).not.toBe(esTitle);
    expect(enOne).not.toBe(esOne);
    // One line and two lines are two different sentences.
    expect(enOne.replace('C-018 · ', '')).not.toBe(enTwo.replace('C-018 · ', '').replace('2', '1'));
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

describe('a team member with no app login is named on the paper too (hub#2033 · kitchen#82)', () => {
  // Since sales#318/#320 the till can say a round is served by a staff record with no hub user:
  // `waiter_id` is then that record's id, which `hub.users.list` never lists. The KDS card names
  // it from the staff app (kitchen#82); the paper has to say the same thing as the screen.
  function clientWithTeam(team: unknown, users: unknown = [{ id: 'u-9', name: 'Marta' }]) {
    const query = vi.fn(async (name: string) => {
      if (name === 'kitchen.orders.items') return [CROQUETAS];
      if (name === 'kitchen.orders.get') {
        return [{ id: 'k-1', label: 'Mesa 4', round_number: 2, order_number: 'C-018', waiter_id: 'sm-7' }];
      }
      if (name === 'hub.users.list') return users;
      return [];
    });
    const queryAllOptional = vi.fn(async (name: string) => {
      if (name !== 'staff.members.list') return undefined;
      if (team instanceof Error) throw team;
      return team;
    });
    return { client: { query, queryAllOptional } as never, query, queryAllOptional };
  }

  const okPrint = () =>
    vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' }));

  it('names the staff record by its full name', async () => {
    const print = okPrint();
    const { client } = clientWithTeam([
      { id: 'sm-1', full_name: 'Luis Gil' },
      { id: 'sm-7', full_name: 'Carmen Ruiz', user_id: null },
    ]);
    await onKitchenOrderCreated(client, { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data?.waiter).toBe('Carmen Ruiz');
  });

  it('falls back to first + last name when the record has no full name', async () => {
    const print = okPrint();
    const { client } = clientWithTeam([{ id: 'sm-7', first_name: 'Carmen', last_name: 'Ruiz' }]);
    await onKitchenOrderCreated(client, { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data?.waiter).toBe('Carmen Ruiz');
  });

  it('still names a terminated or inactive member: who fired the round is a historical fact', async () => {
    const print = okPrint();
    const { client } = clientWithTeam([{ id: 'sm-7', full_name: 'Carmen Ruiz', status: 'terminated', is_active: false }]);
    await onKitchenOrderCreated(client, { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data?.waiter).toBe('Carmen Ruiz');
  });

  it('a hub user is resolved first and the staff app is not asked', async () => {
    const print = okPrint();
    const { client, queryAllOptional } = clientWithTeam([{ id: 'sm-7', full_name: 'Carmen Ruiz' }], [
      { id: 'sm-7', name: 'Carmen (user)' },
    ]);
    await onKitchenOrderCreated(client, { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data?.waiter).toBe('Carmen (user)');
    expect(queryAllOptional).not.toHaveBeenCalled();
  });

  it('without the staff app installed the paper prints as before — no name, no id', async () => {
    const print = okPrint();
    const { client } = clientWithTeam(undefined);
    await onKitchenOrderCreated(client, { order_id: 'k-1' }, { print });
    expect(print).toHaveBeenCalledTimes(1);
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('waiter');
  });

  it('if reading the team fails (no permission), the ticket still prints without a name', async () => {
    const print = okPrint();
    const { client } = clientWithTeam(new Error('permission_denied'));
    await onKitchenOrderCreated(client, { order_id: 'k-1' }, { print });
    expect(print).toHaveBeenCalledTimes(1);
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('waiter');
  });

  it('an id the team does not list either never reaches the paper', async () => {
    const print = okPrint();
    const { client } = clientWithTeam([{ id: 'sm-1', full_name: 'Luis Gil' }]);
    await onKitchenOrderCreated(client, { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('waiter');
  });
});

describe('la ronda `rush` manda el aviso `!! URGENTE !!` al pie (hub#1411)', () => {
  // El renderizador ESC/POS ya sabía pintar el aviso al pie del papel — pero solo reacciona a la
  // forma EXACTA `priority: "HIGH"` (`escpos.rs`, contrato de dispositivo que no se toca: lo lee
  // la `erplora-app` ya desplegada). `kitchen` habla su propio vocabulario, en minúsculas
  // (`normal`/`rush`/`vip`, `handler/src/lib.rs`), y no es su contrato de datos lo que cambia
  // (kitchen#39 ya filtró por él): el adaptador vive aquí, en el productor.
  function clientWithPriority(priority: string | undefined) {
    const query = vi.fn(async (name: string) => {
      if (name === 'kitchen.orders.items') return [CROQUETAS];
      if (name === 'kitchen.orders.get') {
        return [
          {
            id: 'k-1',
            label: 'Mesa 4',
            round_number: 1,
            order_number: 'C-018',
            ...(priority !== undefined ? { priority } : {}),
          },
        ];
      }
      return [];
    });
    return { query } as never;
  }

  const okPrint = () =>
    vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' }));

  it('una ronda `rush` manda `priority: "HIGH"` al renderizador', async () => {
    const print = okPrint();
    await onKitchenOrderCreated(clientWithPriority('rush'), { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data?.priority).toBe('HIGH');
  });

  it('una ronda `normal` no manda `priority` — el renderizador ya asume NORMAL sin el campo', async () => {
    const print = okPrint();
    await onKitchenOrderCreated(clientWithPriority('normal'), { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('priority');
  });

  it('sin `priority` en la cabecera (comanda vieja) tampoco manda el campo', async () => {
    const print = okPrint();
    await onKitchenOrderCreated(clientWithPriority(undefined), { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('priority');
  });

  it('`vip` NO dispara el aviso de cocina: es de sala, no de cocina', async () => {
    // Decisión explícita del alcance de hub#1411: `vip` queda fuera de este mapeo — si algún día
    // dispara algo, es una decisión de negocio propia (skill `market-decision`), no un efecto
    // colateral de este adaptador.
    const print = okPrint();
    await onKitchenOrderCreated(clientWithPriority('vip'), { order_id: 'k-1' }, { print });
    expect(print.mock.calls[0]![0].data).not.toHaveProperty('priority');
  });
});

// hub#2029 — two tills that both reach the kitchen printer. Every open shell hears every
// `kitchen.order.created` (one broadcast per hub), so the ticket came out once per open till and
// the pass cooked the dish twice. The hub stamps the frame with the shell tab that fired the order
// (`clientInstance`, hub#1980, carried across the relay by hub#2029): that till prints the ticket,
// the others only get the system notice. An order no till fired (API, flow, online ordering) goes to
// the hub's print queue, which keeps ONE job per `kitchen-<order>-<role>` — so it comes out once too.
describe('the kitchen ticket comes out once, at the printer it belongs to (hub#2029)', () => {
  const TILL_NEXT_DOOR = 'till-next-door-7c1e';

  function tillHearing() {
    const listeners: ((payload: unknown, meta: { clientInstance?: string }) => void)[] = [];
    const client = fakeClient({
      on: () => {
        throw new Error('the kitchen ticket must listen with onEvent: `on` cannot tell which till fired');
      },
      onEvent: (event: string, cb: (typeof listeners)[number]) => {
        if (event === 'kitchen.order.created') listeners.push(cb);
        return () => {};
      },
    });
    const emit = async (payload: unknown, meta: { clientInstance?: string }) => {
      for (const cb of listeners) cb(payload, meta);
      // The listener fires async work: let it finish its queries and its print.
      await new Promise((r) => setTimeout(r, 0));
    };
    return { client, emit };
  }

  function deps() {
    return {
      print: vi.fn<(req: PrintRequest) => Promise<PrintResult>>(async () => ({ via: 'bridge', role: 'kitchen' })),
      notify: vi.fn<(t: string, b: string) => Promise<void>>(async () => {}),
      t,
      onFailure: vi.fn(),
    };
  }

  it('an order fired at the till next door prints nothing here', async () => {
    const d = deps();
    const { client, emit } = tillHearing();
    bootPrintComanda(client, d);

    await emit({ order_id: 'k-1' }, { clientInstance: TILL_NEXT_DOOR });

    expect(d.print).not.toHaveBeenCalled();
    // Somebody else's ticket is not a failure: no warning either.
    expect(d.onFailure).not.toHaveBeenCalled();
  });

  it('…but the system notice still reaches this device: a KDS tablet with no printer lives on it', async () => {
    const d = deps();
    const { client, emit } = tillHearing();
    bootPrintComanda(client, d);

    await emit({ order_id: 'k-1' }, { clientInstance: TILL_NEXT_DOOR });

    expect(d.notify).toHaveBeenCalledTimes(1);
  });

  it('the till that fired the order prints its ticket, by its usual route', async () => {
    const d = deps();
    const { client, emit } = tillHearing();
    bootPrintComanda(client, d);

    await emit({ order_id: 'k-1' }, { clientInstance: CLIENT_INSTANCE });

    expect(d.print).toHaveBeenCalledTimes(1);
    const req = d.print.mock.calls[0]![0];
    expect(req.jobId).toBe('kitchen-k-1-kitchen');
    // Its own printer if it has one: nothing forces it through the queue.
    expect(req.queueOnly).toBeFalsy();
  });

  it('an order no till fired goes ONLY to the hub queue, where it is one job for every till', async () => {
    const d = deps();
    const { client, emit } = tillHearing();
    bootPrintComanda(client, d);

    await emit({ order_id: 'k-1' }, {});

    expect(d.print).toHaveBeenCalledTimes(1);
    const req = d.print.mock.calls[0]![0];
    expect(req.queueOnly).toBe(true);
    // The queue's key: the same order and station from every till is the same row.
    expect(req.jobId).toBe('kitchen-k-1-kitchen');
  });
});

describe('comandaRoute — who prints a kitchen ticket (hub#2029)', () => {
  it('this tab fired it → here; another tab → elsewhere; no tab → queue', () => {
    expect(comandaRoute({ clientInstance: CLIENT_INSTANCE })).toBe('here');
    expect(comandaRoute({ clientInstance: 'till-next-door-7c1e' })).toBe('elsewhere');
    expect(comandaRoute({})).toBe('queue');
  });
});

// hub#2257 — the floor used to read the door's reason as it came («el runtime rechazó el
// encolado», `sin papel`), or the literal «sin impresora» on a hub in English. The reason is for
// whoever diagnoses the printer, not for the waiter: it travels as a CODE and goes to the log; the
// sentence is the notice's (print-comanda-notice.ts). Same recipe as the receipt's (hub#2239).
describe('the reason a kitchen order did not print is for the log, not for the floor (hub#2257)', () => {
  it('a door that gives no reason still hands over a code, not a sentence in one language', async () => {
    const print = vi.fn(async () => ({ via: 'none' as const, role: 'kitchen' }));
    const onFailure = vi.fn();
    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, onFailure });
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0].error).toMatch(/^[a-z][a-z_]*$/);
  });

  it('so does a queue with nobody set up for that station', async () => {
    const print = vi.fn(async () => ({ via: 'queue' as const, role: 'kitchen', awaitingHost: true }));
    const onFailure = vi.fn();
    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, onFailure });
    expect(onFailure.mock.calls[0]![0].error).toMatch(/^[a-z][a-z_]*$/);
  });

  for (const [what, print] of [
    ['the door’s own reason', async () => ({ via: 'none' as const, role: 'kitchen', error: 'el runtime rechazó el encolado' })],
    [
      'the reason the door threw',
      async () => {
        throw new Error('el runtime rechazó el encolado');
      },
    ],
  ] as const) {
    it(`${what} is written to the log, with the order and the station`, async () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      try {
        await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print: vi.fn(print), onFailure: vi.fn() });
        const logged = warn.mock.calls.map((c) => c.map(String).join(' '));
        expect(
          logged.some((l) => l.includes('el runtime rechazó el encolado') && l.includes('k-1') && l.includes('kitchen')),
        ).toBe(true);
      } finally {
        warn.mockRestore();
      }
    });
  }
});

// hub#2494 — the station's printer on this device did not answer (switched off, out of paper).
// The floor is told, and Retry prints THAT station's docket again — not the whole order, so the
// station that did get its paper does not get a second one (Toast's «Reprint to this station»).
describe('a docket whose printer did not answer (hub#2494)', () => {
  const DEAD: PrintResult = { via: 'none', role: 'kitchen', error: 'unreachable', printerFailed: true };
  const kitchenAndBar = () =>
    fakeClient({
      query: vi.fn(async (name: string) => {
        if (name === 'kitchen.orders.items') return [CROQUETAS, FLAN];
        if (name === 'kitchen.orders.get') return [{ id: 'k-1', label: 'Mesa 4', round_number: 2, order_number: 'C-018' }];
        return [];
      }),
    });

  it('warns with a Retry that prints only that station again', async () => {
    const print = vi.fn(async (req: PrintRequest): Promise<PrintResult> =>
      req.role === 'kitchen' && print.mock.calls.length === 1 ? DEAD : { via: 'bridge', role: req.role ?? '' },
    );
    const onFailure = vi.fn();

    await onKitchenOrderCreated(kitchenAndBar(), { order_id: 'k-1' }, { print, onFailure });

    expect(onFailure).toHaveBeenCalledTimes(1);
    const failure = onFailure.mock.calls[0]![0];
    expect(failure).toMatchObject({ orderId: 'k-1', role: 'kitchen', label: 'Mesa 4', printerFailed: true });
    expect(print).toHaveBeenCalledTimes(2); // kitchen (dead) + bar (printed)

    await failure.retry();

    expect(print).toHaveBeenCalledTimes(3);
    const again = print.mock.calls[2]![0];
    expect(again.role).toBe('kitchen');
    expect(again.jobId).toBe('kitchen-k-1-kitchen');
    expect(again.data).toEqual(print.mock.calls[0]![0].data);
    expect(onFailure).toHaveBeenCalledTimes(1);
  });

  it('a Retry that fails again warns again', async () => {
    const print = vi.fn(async (req: PrintRequest): Promise<PrintResult> => ({ ...DEAD, role: req.role ?? '' }));
    const onFailure = vi.fn();

    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, onFailure });
    await onFailure.mock.calls[0]![0].retry();

    expect(onFailure).toHaveBeenCalledTimes(2);
    expect(typeof onFailure.mock.calls[1]![0].retry).toBe('function');
  });

  it('a station with no printer at all is not a printer failure: no Retry to offer', async () => {
    const print = vi.fn(async (): Promise<PrintResult> => ({ via: 'none', role: 'kitchen', error: 'no printer' }));
    const onFailure = vi.fn();

    await onKitchenOrderCreated(fakeClient(), { order_id: 'k-1' }, { print, onFailure });

    expect(onFailure.mock.calls[0]![0].retry).toBeUndefined();
  });
});
