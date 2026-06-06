// @erplora/module-types — contrato compartido (tipos TS).
// OBJETIVO: generar estos tipos desde ../../schemas/module.schema.json (fuente única).
// HOY: mínimos a mano para que el SDK/CLI tipen. ARQUITECTURA.md §7.2.

export interface NavigationItem {
  id: string;
  label: string;
  icon?: string;
  component: string; // custom element a montar
}

export interface ModuleManifest {
  id: string;
  name: string;
  version: string;
  depends_on?: string[];
  permissions?: string[];
  role_permissions?: Record<string, string[]>;
  navigation?: NavigationItem[];
  ui: { entry: string };
  // queries/commands/events/ai_tools/network/scheduled_tasks → ver schemas/module.schema.json
}

// Envelope de transporte (schemas/envelope.schema.json) — §7.6
export interface WireRequest { id: string; kind: 'query' | 'command'; name: string; params?: unknown; }
export interface WireResponse { id: string; ok: boolean; data?: unknown; error?: { code: string; message: string }; }
export interface WireEvent { name: string; payload?: unknown; }

// ── Queries de lista (paginadas) — contrato del motor de listas del runtime (§4, §8.2) ──────

/** Rango para un filtro `range` (números o fechas ISO). Campos vacíos = sin límite por ese lado. */
export interface RangeFilter { from?: unknown; to?: unknown; }

/** Parámetros que acepta una query de lista. El SDK los aplana a `f_<col>`/`f_<col>_from/_to`. */
export interface ListParams {
  /** Tamaño de página. Si se omite, el runtime usa el `page_size` declarado. */
  limit?: number;
  /** Desplazamiento (nº de filas a saltar). */
  offset?: number;
  /** Texto del buscador global (LIKE sobre las columnas `search` declaradas). */
  search?: string;
  /** Columna de orden (debe estar en la whitelist `sort`; si no, el runtime cae al default). */
  sort?: string;
  /** Dirección del orden. */
  dir?: 'asc' | 'desc';
  /** Filtros por columna: `col -> valor` (eq/like) o `col -> {from,to}` (range). Vacíos se omiten. */
  filters?: Record<string, unknown | RangeFilter>;
}

/** Forma de `data` que devuelve una query de lista: la página + el total filtrado (para el pager). */
export interface Page<T = unknown> {
  rows: T[];
  total: number;
  limit: number;
  offset: number;
}
