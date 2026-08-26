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

import {
  buildWidgetsFromManifests,
  MAX_DEFAULT_ACTIVE_WITHOUT_SECTOR,
} from './dashboard-widgets';
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
      options: { valueFormat: 'number', valueDivisor: 1_000_000, max: 10 },
    };
    const rows = [
      { name: 'Coca-Cola', stock: 3_000_000 },
      { name: 'Agua', stock: 5_000_000 },
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

  // Se comprueba sobre un `stat` a propósito: desde hub#1105 el `kpi` ya no pinta `options.label`
  // (era una segunda cabecera dentro del marco), así que el único kind que lo muestra —y por tanto
  // donde su traducción se puede observar— es `stat`. El contrato traducido es el mismo.
  it('traduce también el `label` (options.label) del widget desde el locale', async () => {
    const def: WidgetManifestDef = {
      title: 'Products in stock',
      kind: 'stat',
      query: 'inventory.products.stats',
      map: { value: 'value' },
      options: { format: 'number', label: 'Products with stock' },
    };
    const mods = [
      {
        id: 'inventory',
        manifest: { id: 'inventory', widgets: { 'inventory.in_stock': def } },
        locale: {
          widgets: { 'inventory.in_stock': { title: 'Con existencias', label: 'Productos con stock' } },
        },
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
    const stat = cell.querySelector('ok-stat') as (HTMLElement & { label?: string }) | null;
    expect(stat?.label).toBe('Productos con stock');
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

// ── hub#1100 · Qué arranca ACTIVO en el tablero (ADR-0054 §4) ──────────────────────────────────
//
// 🔴 El agujero: la recolección devolvía el CATÁLOGO (todos los widgets) y un preset "Recomendado"
// que sólo existía si el hub tenía sector. Sin sector el preset salía vacío y `ok-widget-board`
// caía a su último recurso documentado —«sin value y sin presets ⇒ activa TODOS»—, así que un hub
// con 25 módulos abría con los 20 widgets encendidos, los 9 marcados `default:false` incluidos.
// El paso que faltaba es decir explícitamente QUÉ está activo de salida (`defaultActive`), en vez
// de dejar que la librería lo adivine.
describe('hub#1100 — qué arranca ACTIVO (defaultActive), no el catálogo entero', () => {
  const client = clientWith(async () => [{ total: 1 }]);
  const base: WidgetManifestDef = {
    title: 'W',
    kind: 'kpi',
    query: 'sales.today',
    map: { value: 'total' },
  };

  /** Los 19 widgets reales de los 5 módulos con widgets (2026-08-25), con su default/sectors. */
  const REAL_WIDGETS: Record<string, WidgetManifestDef> = Object.fromEntries(
    (
      [
        ['cash_register.current_session', true, ['retail', 'hosteleria']],
        ['cash_register.recent_sessions', false, ['retail', 'hosteleria']],
        ['inventory.low_stock_count', true, ['retail', 'hosteleria']],
        ['inventory.value', true, ['retail', 'hosteleria']],
        ['inventory.in_stock', false, ['retail', 'hosteleria']],
        ['inventory.low_stock_products', true, ['retail', 'hosteleria']],
        ['sales.today', true, ['hosteleria', 'retail', 'belleza']],
        ['sales.tickets_today', true, ['hosteleria', 'retail', 'belleza']],
        ['sales.last_7_days', false, ['hosteleria', 'retail', 'belleza']],
        ['sales.recent_activity', false, ['hosteleria', 'retail', 'belleza']],
        ['staff.headcount', true, ['rrhh', 'hosteleria', 'retail', 'general', 'belleza']],
        ['staff.on_leave_today', true, ['rrhh', 'hosteleria', 'retail', 'general', 'belleza']],
        ['staff.pending_time_off', false, ['rrhh', 'hosteleria', 'retail', 'general', 'belleza']],
        ['staff.time_off_today', true, ['rrhh', 'hosteleria', 'retail', 'general', 'belleza']],
        ['staff.by_role', false, ['rrhh', 'hosteleria', 'retail', 'general', 'belleza']],
        ['verifactu.pending', true, ['hosteleria', 'retail', 'gestoria', 'general']],
        ['verifactu.contingency', false, ['hosteleria', 'retail', 'gestoria', 'general']],
        ['verifactu.by_status', false, ['hosteleria', 'retail', 'gestoria', 'general']],
        ['verifactu.events', false, ['hosteleria', 'retail', 'gestoria', 'general']],
      ] as Array<[string, boolean, string[]]>
    ).map(([id, def, sectors]) => [
      id,
      { ...base, default: def, sectors: sectors as WidgetManifestDef['sectors'] },
    ]),
  );

  const OPT_IN = Object.entries(REAL_WIDGETS)
    .filter(([, d]) => d.default !== true)
    .map(([id]) => id);

  it('🔴 SIN sector: un `default:false` NUNCA arranca activo (hoy arrancaban los 20)', () => {
    const { widgets, defaultActive } = buildWidgetsFromManifests(
      manifestWithMany(REAL_WIDGETS),
      { client, sector: null },
    );
    expect(widgets).toHaveLength(19); // el catálogo SIGUE completo: se ofrecen todos en el ⋮
    for (const id of OPT_IN) expect(defaultActive).not.toContain(id);
  });

  it('🔴 SIN sector: arranca con un puñado legible, no con el catálogo entero', () => {
    const { defaultActive } = buildWidgetsFromManifests(manifestWithMany(REAL_WIDGETS), {
      client,
      sector: null,
    });
    expect(defaultActive.length).toBeGreaterThan(0);
    expect(defaultActive.length).toBeLessThanOrEqual(MAX_DEFAULT_ACTIVE_WITHOUT_SECTOR);
  });

  it('SIN sector: el recorte reparte entre módulos — un `default:true` de CADA módulo antes que el segundo de ninguno', () => {
    // Revisión de la PR #1194: con `suggested.slice(0, 6)` el corte seguía el orden de instalación,
    // y en el banco real (inventory y staff antes que sales y cash_register) el Inicio arrancaba con
    // 3 de inventario + 3 de personal y SIN «Ventas hoy» ni «Caja» — los dos KPI que todo TPV pone
    // primero. Un puñado legible tiene que ser un puñado REPRESENTATIVO: round-robin por módulo.
    const moduleOf = (id: string): string => id.split('.')[0]!;
    // Cada módulo con SU manifest, en el orden en que los devolvió el hub del banco.
    const byModule = new Map<string, Record<string, WidgetManifestDef>>();
    for (const m of ['inventory', 'staff', 'sales', 'cash_register', 'verifactu']) byModule.set(m, {});
    for (const [id, def] of Object.entries(REAL_WIDGETS)) byModule.get(moduleOf(id))![id] = def;
    const mods = [...byModule].map(([id, widgets]) => ({
      moduleId: id,
      manifest: { id, widgets },
    })) as unknown as InstalledManifest[];
    const { defaultActive } = buildWidgetsFromManifests(mods, { client, sector: null });
    expect(defaultActive).toHaveLength(MAX_DEFAULT_ACTIVE_WITHOUT_SECTOR);
    // Los 5 módulos con widgets (todos tienen algún default:true) están representados…
    expect(new Set(defaultActive.map(moduleOf)).size).toBe(5);
    // …y el primero de cada módulo va antes que el segundo de cualquiera.
    const firstSeen = new Map<string, number>();
    defaultActive.forEach((id, i) => {
      if (!firstSeen.has(moduleOf(id))) firstSeen.set(moduleOf(id), i);
    });
    const lastFirst = Math.max(...firstSeen.values());
    const secondOfAny = defaultActive.findIndex((id, i) => firstSeen.get(moduleOf(id)) !== i);
    expect(secondOfAny === -1 || secondOfAny > lastFirst).toBe(true);
    expect(defaultActive).toContain('sales.today');
    expect(defaultActive).toContain('cash_register.current_session');
  });

  it('CON sector: exactamente los `default:true` cuyo `sectors` incluye ese sector', () => {
    const { defaultActive } = buildWidgetsFromManifests(manifestWithMany(REAL_WIDGETS), {
      client,
      sector: 'gestoria',
    });
    expect(defaultActive).toEqual(['verifactu.pending']);
  });

  it('CON sector: `default:true` sin `sectors` aplica a cualquier sector', () => {
    const widgets = {
      todos: { ...base, default: true },
      solo_retail: { ...base, default: true, sectors: ['retail'] as WidgetManifestDef['sectors'] },
    };
    const { defaultActive } = buildWidgetsFromManifests(manifestWithMany(widgets), {
      client,
      sector: 'hosteleria',
    });
    expect(defaultActive).toEqual(['todos']);
  });

  it('un widget filtrado por permiso tampoco arranca activo', () => {
    const widgets = {
      visible: { ...base, default: true },
      denegado: { ...base, default: true, permission: 'sales.read' },
    };
    const { defaultActive } = buildWidgetsFromManifests(manifestWithMany(widgets), {
      client,
      sector: 'retail',
      hasPermission: (p: string) => p !== 'sales.read',
    });
    expect(defaultActive).toEqual(['visible']);
  });
});

// ── hub#1105 · Una sola cabecera por tarjeta ───────────────────────────────────────────────────
//
// 🔴 El agujero: `createCard` ya pinta la cabecera del widget (título + icono) y el renderer de
// `kpi` volvía a pintar `options.label` + `options.icon` dentro del `ok-kpi`, cuya `.label` es
// otra cabecera (uppercase, bold, icono a la derecha). Dos cabeceras por tarjeta y, en 4 de los 6
// KPIs reales, el MISMO icono dos veces. El marco es el dueño de la cabecera: el kind sólo pinta
// el valor. `stat` ya se comportaba así (su `.label` es un subtítulo, no una cabecera) y no cambia.
describe('hub#1105 — el marco es el dueño de la cabecera: el kpi no la repite', () => {
  /** La cabecera de la card: el `<span>` del título y el `ion-icon` de su derecha (si lo hay). */
  function cardHeader(cell: HTMLElement): { title: string | null; icon: string | null } {
    const card = cell.querySelector('[role="group"]') as HTMLElement | null;
    const head = card?.firstElementChild as HTMLElement | undefined;
    return {
      title: head?.querySelector('span')?.textContent ?? null,
      icon: head?.querySelector('ion-icon')?.getAttribute('name') ?? null,
    };
  }

  it('🔴 kpi: el ok-kpi NO lleva label ni icono propios (la cabecera de la card ya los pinta)', async () => {
    // `sales.today` tal cual lo declara su module.json: título + icono en el marco, y OTRO
    // label + OTRO icono en options → dos cabeceras apiladas.
    const def: WidgetManifestDef = {
      title: "Today's sales",
      icon: 'trending-up-outline',
      kind: 'kpi',
      query: 'sales.metrics.today',
      map: { value: 'total' },
      options: { label: 'Today', icon: 'cash-outline', format: 'currency', currency: 'EUR' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ total: 12345 }]));
    const kpi = cell.querySelector('ok-kpi') as
      | (HTMLElement & { label?: string; icon?: string; value?: string })
      | null;
    expect(kpi?.value).toContain('123,45'); // el valor sigue ahí
    expect(kpi?.label ?? undefined).toBeUndefined();
    expect(kpi?.icon ?? undefined).toBeUndefined();
    expect(cardHeader(cell)).toEqual({ title: "Today's sales", icon: 'trending-up-outline' });
  });

  it('🔴 kpi: con el MISMO icono arriba y abajo, sólo queda el del marco', async () => {
    // `inventory.value`, `staff.headcount`, `sales.tickets_today` y `verifactu.pending`: el icono
    // del widget y el de options son literalmente el mismo.
    const def: WidgetManifestDef = {
      title: 'Inventory value',
      icon: 'cash-outline',
      kind: 'kpi',
      query: 'inventory.stats',
      map: { value: 'total' },
      options: { label: 'Stock value (at cost)', icon: 'cash-outline', format: 'number' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ total: 7 }]));
    const kpi = cell.querySelector('ok-kpi') as (HTMLElement & { icon?: string }) | null;
    expect(kpi?.icon ?? undefined).toBeUndefined(); // el de abajo se va…
    expect(cardHeader(cell).icon).toBe('cash-outline'); // …y queda el del marco
  });

  it('🔴 kpi: si el icono SÓLO viene en options, no se pierde — lo pinta el marco', async () => {
    const def: WidgetManifestDef = {
      title: 'Pending',
      kind: 'kpi',
      query: 'q',
      map: { value: 'total' },
      options: { icon: 'shield-checkmark-outline', format: 'number' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ total: 2 }]));
    expect(cardHeader(cell).icon).toBe('shield-checkmark-outline');
    const kpi = cell.querySelector('ok-kpi') as (HTMLElement & { icon?: string }) | null;
    expect(kpi?.icon ?? undefined).toBeUndefined();
  });

  it('🔴 sparkline: mismo contrato (también monta un ok-kpi dentro del marco)', async () => {
    const def: WidgetManifestDef = {
      title: 'Trend',
      icon: 'trending-up-outline',
      kind: 'sparkline',
      query: 'sales.spark',
      map: { series: 'amount', value: 'total' },
      options: { label: 'Sales', icon: 'trending-up-outline', sparkType: 'line' },
    };
    const cell = await renderOne(
      def,
      clientWith(async () => [
        { amount: 1, total: 10 },
        { amount: 3, total: 30 },
      ]),
    );
    const kpi = cell.querySelector('ok-kpi') as (HTMLElement & { label?: string; icon?: string }) | null;
    expect(kpi?.label ?? undefined).toBeUndefined();
    expect(kpi?.icon ?? undefined).toBeUndefined();
    expect(cardHeader(cell).icon).toBe('trending-up-outline');
  });

  it('REGRESIÓN: `stat` no cambia — su label sigue siendo el subtítulo que ya era', async () => {
    const def: WidgetManifestDef = {
      title: 'Contingency queue',
      icon: 'warning-outline',
      kind: 'stat',
      query: 'verifactu.stats',
      map: { value: 'queued' },
      options: { label: 'In contingency queue', format: 'number' },
    };
    const cell = await renderOne(def, clientWith(async () => [{ queued: 4 }]));
    const stat = cell.querySelector('ok-stat') as (HTMLElement & { label?: string }) | null;
    expect(stat?.label).toBe('In contingency queue');
  });
});
