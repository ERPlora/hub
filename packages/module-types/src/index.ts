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
  /**
   * Widgets de dashboard que ofrece el módulo (ADR-0054). Mapa
   * `<id.completo.namespaced> -> WidgetManifestDef`. El runtime solo lo transporta (dispatcher
   * genérico); el shell lo recolecta y renderiza. Ver `architecture/hub/dashboard/widgets.md`.
   */
  widgets?: Record<string, WidgetManifestDef>;
  /**
   * Chequeo de CONFIGURACIÓN del módulo (ADR-0063). Declarativo y genérico: el shell lo evalúa para
   * cada módulo instalado y, si NO está configurado, lo surfacea como alerta (campana + dashboard)
   * con un CTA a su pantalla de ajustes. El Hub no conoce módulos concretos: cada uno se autodeclara.
   * Ver `architecture/hub/setup-status.md`.
   */
  setup?: ModuleSetupDef;
  // queries/commands/events/ai_tools/network/scheduled_tasks → ver schemas/module.schema.json
}

/** Un chequeo sobre una fila del resultado de la query de `setup`. "Configurado" exige que TODOS
 *  pasen. EXACTAMENTE UNO de `truthy`/`equals` por entrada. */
export interface ModuleSetupCheck {
  /** Columna del resultado a evaluar. */
  field: string;
  /** Pasa si el campo es "verdadero" (true, número≠0, string no vacío). */
  truthy?: boolean;
  /** Pasa si el campo es igual a este valor (comparación laxa por string). */
  equals?: string | number | boolean;
}

/**
 * Declaración de "¿está el módulo configurado?" (ADR-0063). El shell ejecuta `query` (lectura
 * declarativa del módulo, revalida permiso en server), toma la **primera fila** y evalúa
 * `configured_when`: si TODOS los checks pasan → configurado; si no hay fila o algún check falla →
 * NO configurado → alerta con CTA a `route`.
 */
export interface ModuleSetupDef {
  /** Query namespaced que devuelve el estado de configuración (1 fila). */
  query: string;
  /** Params estáticos para la query. */
  params?: Record<string, unknown>;
  /** Configurado ⇔ TODOS estos checks pasan sobre la primera fila. */
  configured_when: ModuleSetupCheck[];
  /** Título de la alerta (p. ej. "Configura VeriFactu"). */
  title: string;
  /** Texto de ayuda corto. */
  description?: string;
  /** Icono ionicons para la alerta. */
  icon?: string;
  /** Ruta de la pantalla de configuración (p. ej. `/m/verifactu/settings`). */
  route: string;
  /** Permiso para configurarlo: solo se alerta a quien puede (la query revalida en server). */
  permission?: string;
}

/** Tamaño de celda de un widget en la rejilla de 12 columnas. sm=3, md=6, lg=8. */
export type WidgetSize = 'sm' | 'md' | 'lg';

/** Kind del render genérico de un widget de dashboard (vía declarativa). */
export type WidgetKind = 'kpi' | 'stat' | 'sparkline' | 'bar-list' | 'timeline' | 'chart';

/** Sector/tipo de negocio al que aplica un widget (preset "Recomendado"). */
export type WidgetSector = 'hosteleria' | 'retail' | 'gestoria' | 'rrhh' | 'general';

/**
 * Definición de un widget de dashboard en el `module.json` (campo `widgets`). EXACTAMENTE UNO de
 * `{ kind, component }`; si hay `kind`, `query` es obligatoria. Contrato ADR-0054.
 */
export interface WidgetManifestDef {
  /** Título mostrado en el board y el selector. OBLIGATORIO. */
  title: string;
  /** Nombre ionicons para el selector. */
  icon?: string;
  /** Grupo en el selector ("Ventas", "Inventario"…). */
  category?: string;
  /** Tamaño de celda (def "md"). */
  size?: WidgetSize;
  /** Permiso para mostrarlo en cliente (la query revalida en server). */
  permission?: string;
  /** Tipos de negocio aplicables. Ausente/vacío = todos. */
  sectors?: WidgetSector[];
  /** Sugerido ACTIVO en el preset "Recomendado" cuando el sector del hub coincide. */
  default?: boolean;

  // ── Vía declarativa (kind) ──
  /** Kind del render genérico (mutuamente excluyente con `component`). */
  kind?: WidgetKind;
  /** Query namespaced que alimenta el widget (OBLIGATORIA si hay `kind`). */
  query?: string;
  /** Params estáticos pasados a la query. */
  params?: Record<string, unknown>;
  /** Mapea columnas del resultado → props del widget. */
  map?: Record<string, string>;
  /** Props literales estáticas (label, icon, format, currency…). */
  options?: Record<string, unknown>;

  // ── Vía componente (escape hatch) ──
  /** Custom element del propio módulo a montar (mutuamente excluyente con `kind`). */
  component?: string;
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
