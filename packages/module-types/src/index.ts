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
  /**
   * Carpeta privada del módulo bajo `media/modules/` (ADR-0151) y qué puede hacer el USUARIO con
   * esos ficheros desde /files (ADR-0172). `user_actions` ausente o vacío = solo ver y descargar.
   * No limita al módulo, que sigue escribiendo por `ModuleStorage`.
   */
  static_files?: { folder: string; user_actions?: ('upload' | 'rename' | 'delete')[] };
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
  /**
   * Monetización del módulo (ADR-0006/0013). El manifest es la fuente del pricing + los tiers; la
   * clasificación de marketplace (sectores, business types, is_published) vive en el Cloud, NO aquí.
   * El shell lo usa para auto-inyectar una pestaña "Plan" en la navegación del módulo (compra =
   * usuario: JWT + X-Hub-Id, directo al Cloud). Ver `architecture/modules/`.
   */
  billing?: ModuleBilling;
  /**
   * Pantalla de ajustes declarativa del módulo (settings-as-widgets). El shell la renderiza con un
   * formulario GENÉRICO a partir del JSON Schema (`schema`), cargando los valores con `get` (query
   * singleton) y persistiendo el snapshot completo con `set` (command upsert). Si se declara
   * `component`, el shell pinta ESE Web Component en su lugar (escape-hatch). Sustituye al WC de la
   * pestaña `settings` del módulo cuando no hay `component`.
   */
  settings?: ModuleSettingsDef;
  // queries/commands/events/ai_tools/network/scheduled_tasks → ver schemas/module.schema.json
}

/** Bloque `settings` del manifest (settings declarativos estilo widgets). */
export interface ModuleSettingsDef {
  /** Título de la pantalla de ajustes. */
  title?: string;
  /** Icono ionicons para la pantalla/cabecera. */
  icon?: string;
  /** Ruta (relativa al paquete del módulo) del JSON Schema del formulario. */
  schema: string;
  /** Query namespaced que devuelve la fila singleton de ajustes del hub. */
  get: string;
  /** Command namespaced que persiste el snapshot COMPLETO de ajustes (upsert). */
  set: string;
  /** Escape-hatch: si está, el shell monta ESE custom element en vez del form genérico. */
  component?: string;
}

/** Una propiedad del JSON Schema de ajustes (subset que el form genérico entiende). */
export interface SettingsSchemaProperty {
  /** Tipo del campo → control: boolean=toggle, string=input (o select si `enum`), integer/number=number input. */
  type?: 'boolean' | 'string' | 'integer' | 'number' | string;
  /** Label del campo (si falta, el shell humaniza la clave). */
  title?: string;
  /** Texto de ayuda mostrado bajo el label. */
  description?: string;
  /** Opciones cerradas (string) → `ion-select`. */
  enum?: (string | number)[];
  /** Valor por defecto cuando la fila de ajustes no trae la clave. */
  default?: unknown;
  /** Longitud máxima (string) → `maxlength` del input. */
  maxLength?: number;
}

/** JSON Schema (subset) del formulario de ajustes de un módulo. */
export interface SettingsSchema {
  type?: string;
  properties?: Record<string, SettingsSchemaProperty>;
  required?: string[];
}

/** Un tier (plano) de un módulo dentro de `billing.tiers`. */
export interface BillingTierDef {
  /** Slug estable del tier (`basic`, `essential`, `premium`…). Se manda al Cloud como `tier_slug`. */
  slug: string;
  /** Nombre legible del tier. */
  name: string;
  /** Precio por intervalo (en la divisa del módulo/Cloud). 0 = gratis. */
  price: number;
  /** Periodo de facturación del precio. */
  interval?: 'month' | 'year' | 'one_time';
  /** Días de prueba gratis del tier. */
  trial_days?: number;
  /** Cuota incluida (p. ej. nº de operaciones/mes). Texto o número para mostrar. */
  quota?: number | string;
  /** Si el tier es medido por uso (pago por consumo). */
  metered?: boolean;
  /** Precio por unidad excedida sobre la cuota (cuando `metered`/`quota`). */
  overage_price?: number;
}

/** Bloque `billing` del manifest (ADR-0006/0013). */
export interface ModuleBilling {
  /** Tier por defecto del módulo (`basic`…). */
  tier?: string;
  /** Modelo de cobro del módulo. */
  type?: 'free' | 'one_time' | 'subscription' | string;
  /** Días de prueba gratis a nivel de módulo (si no se declaran por tier). */
  trial_days?: number;
  /** Lista de tiers/planos ofertados. El shell pinta uno por tarjeta. */
  tiers?: BillingTierDef[];
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
  /** Si true (por defecto) la config pendiente alerta en el DASHBOARD; si false es opcional y NO alerta. */
  required?: boolean;
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
  /**
   * Refresco en vivo (ADR-0054, T1): nombres de eventos de dominio cuya emisión debe re-ejecutar
   * la query de este widget. El board se suscribe al canal push existente (Outbox→broadcast, SDK
   * `subscribe`) y re-consulta con debounce. Ausente/vacío = el widget se monta UNA vez (como hoy).
   */
  refresh_on?: string[];

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
