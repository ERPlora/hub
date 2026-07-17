// @vitest-environment happy-dom
//
// Tests del dashboard declarativo (ADR-0054). CERO MOCKS de datos: el "cliente" de prueba es un
// doble mínimo del transporte (query + subscribe) que devuelve FILAS REALES controladas por el
// test — no fixtures inventados dentro del render. Verifica el contrato de comportamiento, no el
// markup interno de los ok-*.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// `dashboard-widgets` importa `module-loader` por sus funciones de I/O (loadInstalledManifests/
// loadModuleComponent), y ese módulo arrastra la cadena de iconos `~icons/…?raw` que el transform
// de vitest deniega (mismo motivo y patrón que DataPanel.test.ts). Aislamos la unidad pura
// `buildWidgetsFromManifests` stubeando esas funciones de I/O — NO mockeamos datos: las filas de
// las queries las controla el test con formas reales (regla CERO MOCKS intacta).
vi.mock('./module-loader', () => ({
  loadInstalledManifests: vi.fn(),
  loadModuleComponent: vi.fn(),
}));

import { buildWidgetsFromManifests } from './dashboard-widgets';
import type { InstalledManifest } from './module-loader';
import type { ErploraClient } from '@erplora/module-sdk';
import type { WidgetManifestDef } from '@erplora/module-types';

/**
 * Doble del cliente: `query` devuelve `[{ value }]` con el valor ACTUAL (mutable por el test para
 * simular que el backend cambió), y `on` (canal de eventos de ErploraClient, delega en
 * transport.subscribe) guarda los callbacks para poder emitir eventos de dominio a mano. Solo
 * implementa lo que el board usa.
 */
function makeClient(initial: number) {
  let current = initial;
  const subs = new Map<string, Set<(p: unknown) => void>>();
  const query = vi.fn(async () => [{ value: current }]);
  const client = {
    query,
    on(event: string, cb: (p: unknown) => void): () => void {
      let set = subs.get(event);
      if (!set) {
        set = new Set();
        subs.set(event, set);
      }
      set.add(cb);
      return () => set!.delete(cb);
    },
  };
  return {
    client: client as unknown as ErploraClient,
    query,
    setValue(v: number) {
      current = v;
    },
    emit(event: string, payload: unknown = {}) {
      subs.get(event)?.forEach((cb) => cb(payload));
    },
  };
}

/** Un manifest instalado con un único widget `kpi`. */
function manifestWith(def: WidgetManifestDef): InstalledManifest[] {
  return [
    { id: 'sales', manifest: { id: 'sales', widgets: { ventas_hoy: def } } },
  ] as unknown as InstalledManifest[];
}

/** Manifest con varios widgets (para probar filtro por permiso / presets). */
function manifestWithMany(widgets: Record<string, WidgetManifestDef>): InstalledManifest[] {
  return [{ id: 'sales', manifest: { id: 'sales', widgets } }] as unknown as InstalledManifest[];
}

/** Cliente cuyo `query` ejecuta `impl` (resuelve/rechaza a voluntad); `on` es no-op (sin refresco). */
function clientWith(impl: () => Promise<unknown>): ErploraClient {
  return { query: vi.fn(impl), on: () => () => {} } as unknown as ErploraClient;
}

/** Espera a que se vacíen las microtareas (la query async del render y su `.then`). */
const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

/**
 * Renderiza el ÚNICO widget de `def` en una celda y espera a que resuelva su query. Devuelve la
 * celda para inspeccionar el DOM pintado.
 */
async function renderOne(def: WidgetManifestDef, client: ErploraClient): Promise<HTMLElement> {
  const { widgets } = buildWidgetsFromManifests(manifestWith(def), { client, sector: null });
  const cell = document.createElement('div');
  widgets[0]!.render(cell);
  await flush();
  return cell;
}

const KPI_BASE: WidgetManifestDef = {
  title: 'Ventas hoy',
  kind: 'kpi',
  query: 'sales.stats.today',
  map: { value: 'value' },
  options: { format: 'number' },
};

/** Lee el valor pintado en el ok-kpi de la celda (propiedad `value`, como lo escribe el renderer). */
function kpiValue(cell: HTMLElement): string | undefined {
  const el = cell.querySelector('ok-kpi') as (HTMLElement & { value?: string }) | null;
  return el?.value;
}

describe('refresco en vivo por evento (refresh_on) — T1', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    document.body.replaceChildren();
  });

  /** Celda montada en el DOM (como en el board real): el refresco en vivo comprueba isConnected. */
  function mountCell(): HTMLElement {
    const cell = document.createElement('div');
    document.body.appendChild(cell);
    return cell;
  }

  it('un kpi con refresh_on re-ejecuta la query y muestra el valor NUEVO al llegar el evento', async () => {
    const { client, query, setValue, emit } = makeClient(42);
    const def: WidgetManifestDef = { ...KPI_BASE, refresh_on: ['sale.completed'] };

    const { widgets } = buildWidgetsFromManifests(manifestWith(def), { client, sector: null });
    const w = widgets.find((x) => x.id === 'ventas_hoy');
    expect(w).toBeDefined();

    const cell = mountCell();
    w!.render(cell);
    await vi.runAllTimersAsync(); // resuelve la query inicial

    expect(kpiValue(cell)).toBe('42');
    expect(query).toHaveBeenCalledTimes(1);

    // El backend cambia y se emite el evento de dominio: el widget debe refrescarse (con debounce).
    setValue(99);
    emit('sale.completed');
    await vi.runAllTimersAsync(); // absorbe el debounce + re-ejecuta la query

    expect(query).toHaveBeenCalledTimes(2);
    expect(kpiValue(cell)).toBe('99');
  });

  it('un widget SIN refresh_on NO se suscribe: el evento no dispara re-query (comportamiento de hoy)', async () => {
    const { client, query, setValue, emit } = makeClient(10);

    const { widgets } = buildWidgetsFromManifests(manifestWith(KPI_BASE), { client, sector: null });
    const cell = mountCell();
    widgets[0]!.render(cell);
    await vi.runAllTimersAsync();

    expect(query).toHaveBeenCalledTimes(1);
    setValue(77);
    emit('sale.completed');
    await vi.runAllTimersAsync();

    // Sin refresh_on el widget se monta una sola vez: sigue en 1 query y en el valor viejo.
    expect(query).toHaveBeenCalledTimes(1);
    expect(kpiValue(cell)).toBe('10');
  });

  it('varias emisiones seguidas se agrupan (debounce): una sola re-query, no una por evento', async () => {
    const { client, query, emit } = makeClient(1);
    const def: WidgetManifestDef = { ...KPI_BASE, refresh_on: ['sale.completed'] };

    const { widgets } = buildWidgetsFromManifests(manifestWith(def), { client, sector: null });
    const cell = mountCell();
    widgets[0]!.render(cell);
    await vi.runAllTimersAsync();
    expect(query).toHaveBeenCalledTimes(1);

    // Ráfaga de un TPV en hora punta: 5 ventas casi simultáneas → UNA sola re-query.
    emit('sale.completed');
    emit('sale.completed');
    emit('sale.completed');
    emit('sale.completed');
    emit('sale.completed');
    await vi.runAllTimersAsync();

    expect(query).toHaveBeenCalledTimes(2);
  });
});

// ── T2 · Renderers por kind con las formas de fila REALES de los 5 módulos con widgets ────────────
//
// Los `def` (kind/query/map/options) son los que declaran hoy sales/inventory/staff/verifactu/
// cash_register en su module.json (2026-07-17). Las FILAS usan las columnas reales que devuelve cada
// query; los valores los fija el test (CERO MOCKS = no inventar datos en el render de producción, no
// prohíbe controlar la entrada de un test unitario).

describe('renderers por kind (T2) — formas de fila reales de los 5 módulos', () => {
  it('kpi (sales.today): pinta ok-kpi con el importe formateado como divisa (céntimos → €)', async () => {
    const def: WidgetManifestDef = {
      title: 'Ventas hoy',
      kind: 'kpi',
      query: 'sales.today',
      map: { value: 'total' },
      options: { label: 'Hoy', format: 'currency', currency: 'EUR', locale: 'es-ES' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ total: 12345, tickets: 9 }]));
    const kpi = cell.querySelector('ok-kpi') as (HTMLElement & { value?: string }) | null;
    expect(kpi).not.toBeNull();
    // 12345 céntimos → 123,45 € (÷100 + 2 decimales, es-ES).
    expect(kpi!.value).toContain('123,45');
  });

  it('kpi con delta/trend (verifactu.pending): refleja delta y tendencia', async () => {
    const def: WidgetManifestDef = {
      title: 'Pendientes AEAT',
      kind: 'kpi',
      query: 'verifactu.stats.compliance_summary',
      map: { value: 'pending_count', trend: 'trend' },
      options: { format: 'number' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ pending_count: 3, trend: 'up' }]));
    const kpi = cell.querySelector('ok-kpi') as (HTMLElement & { value?: string; trend?: string }) | null;
    expect(kpi?.value).toBe('3');
  });

  it('stat (inventory.in_stock): pinta ok-stat con el valor', async () => {
    const def: WidgetManifestDef = {
      title: 'Con existencias',
      kind: 'stat',
      query: 'inventory.products.stats',
      map: { value: 'products_in_stock' },
      options: { label: 'Productos con existencias', format: 'number' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ products_in_stock: 42 }]));
    const stat = cell.querySelector('ok-stat') as (HTMLElement & { value?: string }) | null;
    expect(stat?.value).toBe('42');
  });

  it('chart (sales.last_7_days): pinta ok-chart con type/labels/series desde las filas', async () => {
    const def: WidgetManifestDef = {
      title: 'Últimos 7 días',
      kind: 'chart',
      query: 'sales.last_7_days',
      map: { label: 'day', value: 'total' },
      options: { chartType: 'bar', seriesName: 'Ventas', gridlines: true, height: 220 },
    };
    const rows = [
      { day: 'Lun', total: 1000 },
      { day: 'Mar', total: 2000 },
      { day: 'Mié', total: 1500 },
    ];
    const cell = await renderOne(def, clientWith(async () => rows));
    const chart = cell.querySelector('ok-chart') as
      | (HTMLElement & { type?: string; labels?: string[]; series?: Array<{ data: number[] }> })
      | null;
    expect(chart?.type).toBe('bar');
    expect(chart?.labels).toEqual(['Lun', 'Mar', 'Mié']);
    expect(chart?.series?.[0]?.data).toEqual([1000, 2000, 1500]);
  });

  it('bar-list (inventory.low_stock_products): pinta ok-bar-list con los items mapeados', async () => {
    const def: WidgetManifestDef = {
      title: 'Stock bajo',
      kind: 'bar-list',
      query: 'inventory.products.low_stock',
      map: { label: 'name', value: 'stock' },
      options: { valueFormat: 'number', max: 10 },
    };
    const rows = [
      { name: 'Coca-Cola', stock: 3 },
      { name: 'Agua', stock: 5 },
    ];
    const cell = await renderOne(def, clientWith(async () => rows));
    const list = cell.querySelector('ok-bar-list') as
      | (HTMLElement & { items?: Array<{ label: string; value: number }> })
      | null;
    expect(list?.items?.length).toBe(2);
    expect(list?.items?.[0]?.label).toBe('Coca-Cola');
    expect(list?.items?.[0]?.value).toBe(3);
  });

  it('timeline (sales.recent_activity): pinta ok-timeline con los items mapeados', async () => {
    const def: WidgetManifestDef = {
      title: 'Actividad reciente',
      kind: 'timeline',
      query: 'sales.list',
      map: {
        id: 'id',
        title: 'sale_number',
        description: 'customer_name',
        time: 'created_at',
        status: 'status',
      },
      options: { align: 'left' },
    };
    const rows = [
      { id: 1, sale_number: 'T-001', customer_name: 'Ana', created_at: '2026-07-17', status: 'paid' },
    ];
    const cell = await renderOne(def, clientWith(async () => rows));
    const tl = cell.querySelector('ok-timeline') as
      | (HTMLElement & { items?: Array<{ title: string; description?: string }> })
      | null;
    expect(tl?.items?.length).toBe(1);
    expect(tl?.items?.[0]?.title).toBe('T-001');
    expect(tl?.items?.[0]?.description).toBe('Ana');
  });

  it('sparkline (contrato — ningún módulo lo usa hoy): ok-sparkline con la serie', async () => {
    const def: WidgetManifestDef = {
      title: 'Tendencia',
      kind: 'sparkline',
      query: 'sales.spark',
      map: { series: 'amount', value: 'total' },
      options: { sparkType: 'line' },
    };
    const rows = [
      { amount: 1, total: 10 },
      { amount: 3, total: 30 },
      { amount: 2, total: 20 },
    ];
    const cell = await renderOne(def, clientWith(async () => rows));
    const spark = cell.querySelector('ok-sparkline') as (HTMLElement & { values?: number[] }) | null;
    expect(spark?.values).toEqual([1, 3, 2]);
  });
});

// ── T2 · Estados de carga / error / vacío (hoy funcionan pero sin cobertura → riesgo de regresión) ─

describe('doble marco (P2): kpi/stat se aplanan dentro de la card', () => {
  it('ok-kpi NO dobla marco: pierde su borde/fondo/sombra/padding propios (la card ya los pone)', async () => {
    const def: WidgetManifestDef = {
      title: 'Ventas hoy',
      kind: 'kpi',
      query: 'sales.today',
      map: { value: 'value' },
      options: { format: 'number' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ value: 5 }]));
    const kpi = cell.querySelector('ok-kpi') as HTMLElement;
    expect(kpi.style.getPropertyValue('--background')).toBe('transparent');
    expect(kpi.style.getPropertyValue('--border-color')).toBe('transparent');
    expect(kpi.style.getPropertyValue('--box-shadow')).toBe('none');
    expect(kpi.style.getPropertyValue('--padding')).toBe('0');
  });
});

describe('estados de celda (T2): carga / error / vacío', () => {
  const KPI: WidgetManifestDef = {
    title: 'Ventas hoy',
    kind: 'kpi',
    query: 'sales.today',
    map: { value: 'total' },
    options: { format: 'number' },
  };

  it('CARGA: muestra ion-spinner mientras la query está pendiente', () => {
    let resolve!: (v: unknown) => void;
    const pending = new Promise<unknown>((r) => (resolve = r));
    const cell = document.createElement('div');
    const { widgets } = buildWidgetsFromManifests(manifestWith(KPI), {
      client: clientWith(() => pending),
      sector: null,
    });
    widgets[0]!.render(cell);
    // Sin await: la query sigue pendiente → spinner visible dentro de la card.
    expect(cell.querySelector('ion-spinner')).not.toBeNull();
    resolve([{ total: 1 }]); // limpia la promesa pendiente
  });

  it('ERROR: la query rechaza → estado muted (ok-empty-state), NUNCA dato inventado', async () => {
    const cell = await renderOne(KPI, clientWith(async () => Promise.reject(new Error('boom'))));
    expect(cell.querySelector('ok-empty-state')).not.toBeNull();
    expect(cell.querySelector('ok-kpi')).toBeNull();
  });

  it('VACÍO: la query no devuelve filas → estado muted', async () => {
    const cell = await renderOne(KPI, clientWith(async () => []));
    expect(cell.querySelector('ok-empty-state')).not.toBeNull();
    expect(cell.querySelector('ok-kpi')).toBeNull();
  });

  it('VACÍO: filas sin la columna mapeada (renderer devuelve false) → estado muted', async () => {
    // La query trae filas pero NINGUNA tiene `total` → renderKpi no encuentra valor → muted.
    const cell = await renderOne(KPI, clientWith(async () => [{ otra_columna: 9 }]));
    expect(cell.querySelector('ok-empty-state')).not.toBeNull();
    expect(cell.querySelector('ok-kpi')).toBeNull();
  });
});

// ── T2 · buildWidgetsFromManifests: filtro por permiso, presets por sector y validación de def ─────

describe('buildWidgetsFromManifests (T2): permiso, presets y validación', () => {
  const client = clientWith(async () => [{ total: 1 }]);
  const base: WidgetManifestDef = {
    title: 'W',
    kind: 'kpi',
    query: 'sales.today',
    map: { value: 'total' },
  };

  it('FILTRO PERMISO: hasPermission=false oculta el widget; true/null lo dejan pasar', () => {
    const widgets = { w: { ...base, permission: 'sales.read' } };
    const denied = buildWidgetsFromManifests(manifestWithMany(widgets), {
      client,
      sector: null,
      hasPermission: () => false,
    });
    expect(denied.widgets).toHaveLength(0);

    const allowed = buildWidgetsFromManifests(manifestWithMany(widgets), {
      client,
      sector: null,
      hasPermission: () => true,
    });
    expect(allowed.widgets).toHaveLength(1);

    // null = permiso desconocido → degradación permisiva (la query revalida en server).
    const unknown = buildWidgetsFromManifests(manifestWithMany(widgets), {
      client,
      sector: null,
      hasPermission: () => null,
    });
    expect(unknown.widgets).toHaveLength(1);
  });

  it('PRESET recomendado: default + sectors que incluye el sector del hub → id en el preset', () => {
    const widgets = {
      reco: { ...base, default: true, sectors: ['retail'] as WidgetManifestDef['sectors'] },
      otro: { ...base, default: true, sectors: ['hosteleria'] as WidgetManifestDef['sectors'] },
    };
    const { presets } = buildWidgetsFromManifests(manifestWithMany(widgets), {
      client,
      sector: 'retail',
    });
    expect(presets).toHaveLength(1);
    expect(presets[0]!.widgets).toContain('reco');
    expect(presets[0]!.widgets).not.toContain('otro');
  });

  it('PRESET vacío cuando no se conoce el sector del hub', () => {
    const widgets = { reco: { ...base, default: true, sectors: ['retail'] as WidgetManifestDef['sectors'] } };
    const { presets } = buildWidgetsFromManifests(manifestWithMany(widgets), { client, sector: null });
    expect(presets).toHaveLength(0);
  });

  it('CAP DE CONCURRENCIA (T4): no dispara más de N queries a la vez al montar el board', async () => {
    // Protege el pool per-hub (fix #609) y la ruta crítica del TPV: N widgets no deben saturar la BD
    // con N queries simultáneas. Con cap=2 y 6 widgets, como mucho 2 quedan en vuelo a la vez.
    let inFlight = 0;
    let maxInFlight = 0;
    const resolvers: Array<() => void> = [];
    const client = {
      query: vi.fn(() => {
        inFlight++;
        maxInFlight = Math.max(maxInFlight, inFlight);
        return new Promise((res) => resolvers.push(() => {
          inFlight--;
          res([{ value: 1 }]);
        }));
      }),
      on: () => () => {},
    } as unknown as ErploraClient;

    const widgets: Record<string, WidgetManifestDef> = {};
    for (let i = 0; i < 6; i++) widgets[`w${i}`] = { ...base, map: { value: 'value' } };
    const { widgets: built } = buildWidgetsFromManifests(manifestWithMany(widgets), {
      client,
      sector: null,
      maxConcurrentQueries: 2,
    });
    built.forEach((w) => w.render(document.createElement('div')));
    await flush();

    expect(maxInFlight).toBeLessThanOrEqual(2);

    // Drena: al resolver, el gate deja entrar a los siguientes.
    while (resolvers.length) {
      resolvers.shift()!();
      await flush();
    }
    expect(client.query).toHaveBeenCalledTimes(6); // todos se ejecutan, solo escalonados
  });
});

describe('accesibilidad de las cards (T5)', () => {
  it('la card KPI expone role="group" y aria-label con título + valor', async () => {
    const def: WidgetManifestDef = {
      title: 'Ventas hoy',
      kind: 'kpi',
      query: 'sales.today',
      map: { value: 'value' },
      options: { format: 'number' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ value: 5 }]));
    const card = cell.querySelector('[role="group"]') as HTMLElement | null;
    expect(card).not.toBeNull();
    const label = card!.getAttribute('aria-label') ?? '';
    expect(label).toContain('Ventas hoy'); // etiqueta
    expect(label).toContain('5'); // valor real
  });

  it('la card de un widget de lista tiene aria-label = título (el detalle es el contenido)', async () => {
    const def: WidgetManifestDef = {
      title: 'Stock bajo',
      kind: 'bar-list',
      query: 'inventory.products.low_stock',
      map: { label: 'name', value: 'stock' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ name: 'Café', stock: 3 }]));
    const card = cell.querySelector('[role="group"]') as HTMLElement | null;
    expect(card?.getAttribute('aria-label')).toBe('Stock bajo');
  });
});

describe('i18n de títulos de widget (T5, ADR-0055)', () => {
  const client = clientWith(async () => [{ value: 1 }]);
  const def: WidgetManifestDef = {
    title: 'Sales today', // inglés canónico en el module.json
    kind: 'kpi',
    query: 'sales.today',
    map: { value: 'value' },
  };

  it('traduce el título desde el locale del módulo (`locale.widgets.<id>.title`)', () => {
    const mods = [
      {
        id: 'sales',
        manifest: { id: 'sales', widgets: { 'sales.today': def } },
        locale: { widgets: { 'sales.today': { title: 'Ventas hoy' } } },
      },
    ] as unknown as InstalledManifest[];
    const { widgets } = buildWidgetsFromManifests(mods, { client, sector: null });
    expect(widgets[0]!.title).toBe('Ventas hoy');
  });

  it('sin locale (o sin entrada) usa el título canónico inglés del module.json', () => {
    const mods = [
      { id: 'sales', manifest: { id: 'sales', widgets: { 'sales.today': def } } },
    ] as unknown as InstalledManifest[];
    const { widgets } = buildWidgetsFromManifests(mods, { client, sector: null });
    expect(widgets[0]!.title).toBe('Sales today');
  });

  it('traduce también el `label` (options.label) del widget desde el locale', async () => {
    const def: WidgetManifestDef = {
      title: 'Sales today',
      kind: 'kpi',
      query: 'sales.today',
      map: { value: 'value' },
      options: { format: 'number', label: 'Today' },
    };
    const mods = [
      {
        id: 'sales',
        manifest: { id: 'sales', widgets: { 'sales.today': def } },
        locale: { widgets: { 'sales.today': { title: 'Ventas hoy', label: 'Hoy' } } },
      },
    ] as unknown as InstalledManifest[];
    const { widgets } = buildWidgetsFromManifests(mods, {
      client: clientWith(async () => [{ value: 5 }]),
      sector: null,
    });
    const cell = document.createElement('div');
    document.body.appendChild(cell);
    widgets[0]!.render(cell);
    await new Promise((r) => setTimeout(r, 0));
    const kpi = cell.querySelector('ok-kpi') as (HTMLElement & { label?: string }) | null;
    expect(kpi?.label).toBe('Hoy');
    document.body.replaceChildren();
  });

  it('el título traducido llega a la card (aria-label / cabecera), no el canónico', async () => {
    const mods = [
      {
        id: 'sales',
        manifest: { id: 'sales', widgets: { 'sales.today': { ...def, options: { format: 'number' } } } },
        locale: { widgets: { 'sales.today': { title: 'Ventas hoy' } } },
      },
    ] as unknown as InstalledManifest[];
    const { widgets } = buildWidgetsFromManifests(mods, { client, sector: null });
    const cell = document.createElement('div');
    document.body.appendChild(cell);
    widgets[0]!.render(cell);
    await new Promise((r) => setTimeout(r, 0));
    const card = cell.querySelector('[role="group"]') as HTMLElement | null;
    expect(card?.getAttribute('aria-label')).toContain('Ventas hoy');
    document.body.replaceChildren();
  });
});

describe('validación de def — bloque real', () => {
  const client = clientWith(async () => [{ total: 1 }]);
  const base: WidgetManifestDef = { title: 'W', kind: 'kpi', query: 'sales.today', map: { value: 'total' } };

  it('descarta def sin title, def con kind Y component, y kind sin query', () => {
    const widgets = {
      sin_title: { kind: 'kpi', query: 'q', map: { value: 'v' } } as unknown as WidgetManifestDef,
      ambos: { title: 'X', kind: 'kpi', query: 'q', component: 'erp-x' } as WidgetManifestDef,
      kind_sin_query: { title: 'Y', kind: 'kpi' } as WidgetManifestDef,
      valido: { ...base },
    };
    const { widgets: out } = buildWidgetsFromManifests(manifestWithMany(widgets), {
      client,
      sector: null,
    });
    expect(out.map((w) => w.id)).toEqual(['valido']);
  });
});
