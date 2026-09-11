// @erplora/module-types — contrato compartido (tipos TS).
// OBJETIVO: generar estos tipos desde ../../schemas/module.schema.json (fuente única).
// HOY: mínimos a mano para que el SDK/CLI tipen. ARQUITECTURA.md §7.2.

export interface NavigationItem {
  id: string;
  label: string;
  icon?: string;
  component: string; // custom element a montar
}

/**
 * A business role declared by a module (`roles[]`, paso 2b / hub#351). `extends` hangs it from a
 * base role of the hub, which is what keeps the frozen `admin`/`manager`/`employee` contract
 * intact. `admin` is NOT extendable: a manifest never grants administration of the hub (hub#347).
 */
export interface ModuleRole {
  /** Stable identifier (`waiter`); the key `role_permissions` grants against. */
  key: string;
  /** Human name, canonical ENGLISH; translated in `locales/<lang>.json` (ADR-0055). */
  label: string;
  /** Base role it hangs from. */
  extends: 'manager' | 'employee';
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
  /**
   * Business roles the module declares for its vertical (paso 2b, hub#351). Optional: the
   * published catalogue does not carry it. Declaring NAMES a role; `role_permissions` GRANTS.
   */
  roles?: ModuleRole[];
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
   * Chequeo de CONFIGURACIÓN del módulo (ADR-0063, extendido por hub#369). Declarativo y genérico:
   * el **runtime** lo evalúa para cada módulo instalado y activo y lo devuelve como un ítem de la
   * query core `hub.setup.status`, unido a los ítems del core (tus apps · datos del negocio · tu
   * equipo). El Hub no conoce módulos concretos: cada uno se autodeclara.
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
  /**
   * Route guards this module declares over ANOTHER module's surface (hub#775). The canonical case
   * is `cash_register`: while `enable_cash_register` is on and the route at `protected_pos_url`
   * (served by `sales`) is in play, the shell renders `component` (e.g. `erp-cashregister-open`)
   * instead of mounting the POS, until `guard_query` returns a row (a drawer is open). The runtime
   * enforces the same precondition AUTHORITATIVELY in the dispatcher; this is the shell half.
   */
  protects?: ModuleProtectsDef[];
  // queries/commands/events/ai_tools/network/scheduled_tasks → ver schemas/module.schema.json
}

/**
 * A route guard one module declares over another module's surface (hub#775). See
 * `ModuleManifest.protects`.
 */
export interface ModuleProtectsDef {
  /** Query of the declaring module that returns the SETTINGS row (system context, same hub_id). */
  settings_query: string;
  /** Boolean column in that row that arms the guard (`false`/absent → dormant). */
  enabled_setting: string;
  /** Column whose value is the protected ROUTE (`/m/sales`). */
  route_setting: string;
  /** Query of the declaring module whose rows decide whether the precondition is met. */
  guard_query: string;
  /** What `guard_query` must return for the precondition to be met. Today: `non_empty`. */
  expect: 'non_empty';
  /** Shell-side Web Component to render INSTEAD of the protected module while unmet. */
  component: string;
  /** Event the shell listens for to re-mount the protected module without a manual reload. */
  resume_on: string;
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
  /**
   * Acción de PRUEBA de ESTE ajuste (hub#1426): el tag del Web Component del módulo que sabe
   * ejecutarla. `"erp-kitchen-sound-preview"`.
   *
   * El shell pinta un botón «Probar» junto al campo y, al pulsarlo, llama al método
   * `preview({ key, value, settings })` de ese elemento con el valor que hay EN EL FORMULARIO,
   * todavía sin guardar. Existe porque un ajuste que solo se puede juzgar oyéndolo o viéndolo —el
   * volumen del KDS— se regula a ciegas: guardar, ir a la pantalla, esperar a que entre una
   * comanda y volver. El shell no sabe nada de sonido; quien ejecuta la prueba es el módulo.
   *
   * Va aquí, en el JSON Schema del propio módulo, y no en `module.json`: es una anotación DE LA
   * PROPIEDAD, y `x-` es la forma que JSON Schema tiene para eso (un validador ignora las palabras
   * clave que no conoce). El valor declarado y lo que se guarda no cambian: solo aparece un botón.
   */
  'x-erplora-preview'?: string;
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
  /**
   * De dónde saca el shell lo que este hub lleva CONSUMIDO de su cuota
   * (ERPlora/whatsapp_inbox#131). Sin este bloque la pestaña «Plan» solo dice lo que un plan
   * INCLUYE, que es la mitad del dato: el consumo es lo que avisa de que el módulo va a dejar de
   * responder. La query es del propio módulo y su permiso sigue decidiendo quién la lee; el
   * runtime no la ejecuta por su cuenta (`billing` es opaco para él).
   */
  usage?: ModuleUsageDef;
}

/** El bloque `billing.usage` de un manifest: de dónde sale el consumo de UNA métrica. */
export interface ModuleUsageDef {
  /** Query namespaced del módulo que devuelve el consumo (la gatea su propio permiso). */
  query: string;
  /** Qué clave de `billing.tiers[].quota` cuenta, para poder nombrarla y traducirla. */
  metric: string;
  /** Columna de la respuesta con lo consumido en el periodo en curso. */
  used: string;
  /** Columna con el límite que de verdad se aplica. Ausente → solo se pinta el consumo. */
  limit?: string;
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
 * Declaración de "¿está el módulo configurado?" (ADR-0063, extendido por hub#369). El **runtime**
 * ejecuta `query` (lectura declarativa del propio módulo, con los permisos de quien llama), toma la
 * **primera fila** y evalúa `configured_when`: si TODOS los checks pasan → configurado; si no hay
 * fila o algún check falla → NO configurado. El resultado sale como un ítem de la query core
 * `hub.setup.status`, que leen la checklist y el asistente.
 *
 * Ya no lo evalúa el navegador: era un bucle de N queries desde el cliente y el asistente recibía
 * prosa en vez del dato. Contrato completo en `architecture/hub/setup-status.md`.
 */
export interface ModuleSetupDef {
  /**
   * `true` (por defecto) = 🔴 funcional; `false` = 🟡 recomendado. **Nunca ⛔ bloqueante**: esa lista
   * la mantiene el core, para que un módulo de terceros no pueda autoproclamarse bloqueante.
   * Ojo: `required: false` ya NO se omite de la checklist — sale plegado tras "Ver todo".
   */
  required?: boolean;
  /** Query namespaced que devuelve el estado de configuración (1 fila). */
  query: string;
  /** Params estáticos para la query. */
  params?: Record<string, unknown>;
  /** Configurado ⇔ TODOS estos checks pasan sobre la primera fila. */
  configured_when: ModuleSetupCheck[];
  /** Título del ítem, **en inglés canónico** (ADR-0055); la traducción va en `locales/<lang>.json`. */
  title: string;
  /** Texto de ayuda corto, en inglés canónico. */
  description?: string;
  /** Icono ionicons para el ítem. */
  icon?: string;
  /** Ruta de la pantalla que completa el ítem (p. ej. `/m/verifactu/settings`). */
  route: string;
  /**
   * Permiso para CONFIGURARLO: solo se le ofrece el ítem a quien puede actuar. Deliberadamente más
   * estrecho que el permiso de LEER la query — quien solo mira no recibe una tarea que no puede
   * completar.
   */
  permission?: string;
  /**
   * Países (ISO-3166-1 alfa-2) donde aplica. Ausente/vacío = todos. Es lo que hace que VeriFactu no
   * salga fuera de España sin cablear el nombre del módulo en el core.
   */
  countries?: string[];
  /**
   * Puesto en la checklist. La escala es del core (apps=10, datos del negocio=40, equipo=80) y
   * asigna a cada módulo el suyo: usa el de la tabla de `architecture/hub/setup-status.md`, no uno
   * inventado. Ausente = 500, detrás de todo lo que el core colocó.
   */
  order?: number;
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
