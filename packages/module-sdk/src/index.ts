// @erplora/module-sdk — puente que usan los Web Components (Stencil). ARQUITECTURA.md §7.1, §7.5–7.6.
//
// Transporte de DATOS (ADR-0050): HTTP (RPC) + WebSocket (eventos) en AMBOS productos, contra el
// runtime Axum (embebido en loopback 127.0.0.1:8787 en Hub Local, ECS en Hub Cloud). NO hay
// `invoke`/IPC para datos — se eliminó `IpcTransport`. El módulo solo ve la interfaz
// `ErploraTransport`; nada de su código depende del transporte.
//   - HttpWsTransport  → HTTP POST query/command + WS eventos    (def., ambos productos)
//   - WsTransport      → todo por un solo WS                      (alternativa)
//
// Principio (decisión 2026-05-31): el 90% de la lógica vive en **Rust** (el runtime es la
// autoridad: valida permiso, hub_id, payload y ejecuta). El WC es una mini-app que llama a
// `query`/`command`/`on`; nunca toca la BD ni confía en su propio `hasPermission` para seguridad.

// Contrato público de cantidades (ADR-0147). Vive en un fichero sin dependencias para que los
// módulos puedan importarlo también de forma tree-shakeable desde `@erplora/module-sdk`.
export {
  QUANTITY_SCALE,
  toMicro,
  fromMicro,
  parseQuantity,
  formatQuantity,
  onGrid,
  // Con extensión a propósito: los tests del SDK corren con el runner de
  // `node:test` sobre ESM (`--experimental-transform-types`), que EXIGE el
  // especificador completo. Sin el `.ts` este barrel no resuelve y tumbaba
  // `index.test.ts` entero — que es como se coló, porque `quantity.test.ts`
  // importa el módulo directamente y por sí solo pasaba en verde.
} from './quantity.ts';
import { toMicro } from './quantity.ts';

/**
 * What the hub says about a live event beyond its payload (hub#1980).
 *
 * `clientInstance` is the shell tab whose request produced the event — the `X-Client-Instance` it
 * sent, stamped on the frame by the hub, never by the emitting module. Absent when no shell caused
 * it (an API integration, a flow, a scheduled task). Every till hears every `sale.completed`; this
 * is how the till that charged tells its own sale from the one next to it.
 */
export interface EventMeta {
  clientInstance?: string;
}

export interface ErploraTransport {
  query(name: string, params?: Record<string, unknown>): Promise<unknown>;
  command(name: string, payload?: Record<string, unknown>): Promise<unknown>;
  subscribe(event: string, cb: (payload: unknown) => void): () => void;
  /**
   * `subscribe` with the frame's [`EventMeta`] (hub#1980). Optional so a transport without frames
   * keeps working: the client then delivers an empty meta.
   */
  subscribeWithMeta?(event: string, cb: (payload: unknown, meta: EventMeta) => void): () => void;
  /**
   * Descarga autenticada de un fichero de `media/`. Es opcional para que transportes sin HTTP
   * (y shells anteriores) sigan siendo compatibles; el cliente degrada a `null`.
   */
  fetchMediaBlob?(ref: string, opts?: MediaFetchOptions): Promise<Blob | null>;
}

export interface MediaFetchOptions {
  signal?: AbortSignal;
}

/**
 * Per-call options of {@link ErploraClient.command} and {@link ErploraClient.commandOptional}.
 */
export interface CommandOptions {
  /**
   * The calling screen resolves an unknown outcome ITSELF (hub#2375) — it probes the hub once it is
   * back (an idempotency key, a status read) and tells the person what happened. Then the shell's
   * default net (the red «we can't tell — check before trying again» toast of hub#906) would say
   * the opposite of the screen at the same time, so it is skipped for THIS call. The caller still
   * gets the same {@link UnknownOutcomeError}: it is what tells the screen to probe. Default
   * `false`: a module that says nothing keeps the net.
   */
  resolvesOutcome?: boolean;
}

/**
 * Convierte la referencia portable guardada en BD/blueprint en la única ruta REST que un módulo
 * puede pedir. No es un proxy: rechaza orígenes, endpoints distintos, parámetros extra y
 * traversal antes de que `fetch` vea la cadena.
 */
function mediaPath(ref: string): string | null {
  if (typeof ref !== 'string' || !ref.trim()) return null;
  let path = ref.trim();
  if (path.startsWith('/')) {
    let parsed: URL;
    try {
      parsed = new URL(path, 'http://erplora.invalid');
    } catch {
      return null;
    }
    const keys = [...parsed.searchParams.keys()];
    if (
      parsed.origin !== 'http://erplora.invalid'
      || parsed.pathname !== '/api/media/raw'
      || parsed.hash
      || keys.length !== 1
      || keys[0] !== 'path'
    ) return null;
    path = parsed.searchParams.get('path') ?? '';
  }
  if (
    !path
    || path.startsWith('/')
    || path.includes('\\')
    || path.includes('?')
    || path.includes('#')
    || /^[a-z][a-z0-9+.-]*:/i.test(path)
    || path.split('/').some((part) => !part || part === '.' || part === '..')
  ) return null;
  return path;
}

export interface Notification {
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
}

/**
 * How much identity friction THIS device asks for (hub#357/#358): `shared` is the till at the
 * counter that several people take turns at; `personal` is somebody's own phone or laptop. The pair
 * is CLOSED — the same two spellings as `DeviceMode::parse` in the runtime. Read it through
 * `erplora.deviceMode`.
 */
export type DeviceMode = 'shared' | 'personal';

/** Opciones de formateo de dinero (ADR-0059). Mismo shape que `apps/web/src/lib/money.ts`. */
export interface FormatMoneyOptions {
  /** ISO-4217. Por defecto, la moneda del hub (`erplora.currency`). */
  currency?: string;
  /** Locale BCP-47 para los separadores. Por defecto, el locale activo (`erplora.locale`). */
  locale?: string;
  /** Dígitos decimales (por defecto, los de la divisa: 2 para EUR/USD). */
  maximumFractionDigits?: number;
}

// ── i18n del chrome compartido de tablas ──────────────────────────────────────────────────

/** Etiquetas que los módulos pasan a `<ok-data-table .labels=...>`.
 *
 * OutfitKit conserva inglés como fallback para compatibilidad. El módulo, que sí conoce el
 * idioma activo del shell, debe pasar este objeto para que buscador, columnas, paginación y
 * acciones cambien a la vez que su contenido. Se mantiene aquí para que cada módulo instalable
 * no copie y desincronice el mismo diccionario.
 */
const DATA_TABLE_LABELS_ES = {
  search: 'Buscar…', empty: 'Sin resultados', filters: 'Filtros', clear: 'Limpiar',
  apply: 'Aplicar', selected: '{n} seleccionados', importCsv: 'Importar CSV',
  exportCsv: 'Exportar CSV', add: 'Añadir', moreActions: 'Más acciones',
  rowsPerPage: 'Filas por página', perPageShort: '{n} / pág.', viewList: 'Vista lista',
  viewCards: 'Vista tarjetas', columnsVisible: 'Columnas visibles', columns: 'Columnas',
  actions: 'Acciones', close: 'Cerrar', newRecord: 'Nuevo', form: 'Formulario',
  filterPlaceholder: 'Filtrar…', from: 'Desde', to: 'Hasta',
  fromOf: '{label} desde', toOf: '{label} hasta', gte: '≥', lte: '≤',
  noValues: 'Sin valores', selectAll: 'Seleccionar todo', selectRow: 'Seleccionar fila',
  select: 'Seleccionar', showing: 'Mostrando {from}–{to} de',
  recordSingular: 'registro', recordPlural: 'registros',
  loadError: 'No se han podido cargar los datos', retry: 'Reintentar',
} as const;

const DATA_TABLE_LABELS_EN = {
  search: 'Search…', empty: 'No results', filters: 'Filters', clear: 'Clear',
  apply: 'Apply', selected: '{n} selected', importCsv: 'Import CSV',
  exportCsv: 'Export CSV', add: 'Add', moreActions: 'More actions',
  rowsPerPage: 'Rows per page', perPageShort: '{n} / page', viewList: 'List view',
  viewCards: 'Card view', columnsVisible: 'Visible columns', columns: 'Columns',
  actions: 'Actions', close: 'Close', newRecord: 'New', form: 'Form',
  filterPlaceholder: 'Filter…', from: 'From', to: 'To',
  fromOf: '{label} from', toOf: '{label} to', gte: '≥', lte: '≤',
  noValues: 'No values', selectAll: 'Select all', selectRow: 'Select row',
  select: 'Select', showing: 'Showing {from}–{to} of',
  recordSingular: 'record', recordPlural: 'records',
  loadError: "Couldn't load the data", retry: 'Retry',
} as const;

export function dataTableLabels(locale = 'es'): Record<string, string> {
  return locale.toLowerCase().startsWith('en') ? DATA_TABLE_LABELS_EN : DATA_TABLE_LABELS_ES;
}

/**
 * Whether the shell's `<ok-data-table>` paints a failed load itself (`error` + Retry, OutfitKit ≥
 * 0.1.113, pm#530). A module paints with the SHELL's OutfitKit (ADR-0451), and a hub on an older
 * image has a table without that state: there the module keeps its own banner, or the reason of
 * the failure would be shown nowhere. Where the table does paint it, the banner is a duplicate.
 */
export function dataTableShowsLoadError(): boolean {
  const registry = (globalThis as { customElements?: { get(tag: string): { prototype: object } | undefined } })
    .customElements;
  const table = registry?.get('ok-data-table');
  return !!table && 'error' in table.prototype;
}

// ── Queries de lista (paginadas) — contrato del motor de listas del runtime (§4, §8.2) ──────

/** Rango para un filtro `range` (números o fechas ISO). Campos vacíos = sin límite por ese lado. */
export interface RangeFilter {
  from?: unknown;
  to?: unknown;
}

/** Parámetros de una query de lista. `queryPage` los aplana a `f_<col>` / `f_<col>_from/_to`. */
export interface ListParams {
  limit?: number;
  offset?: number;
  search?: string;
  sort?: string;
  dir?: 'asc' | 'desc';
  /** `col -> valor` (eq/like) o `col -> {from,to}` (range). Valores vacíos/null se omiten.
   *
   *  ⚠️ **La columna tiene que estar declarada** en el bloque `list` de la query. Esto se aplana a
   *  `f_<col>` diga lo que diga el manifest, así que una columna que la query no declara llega
   *  bien prefijada y el motor la **descarta en silencio**: `200 ok` con la lista ENTERA y quien
   *  llamó creyéndose filtrado (hub#1173; el namespace `f_` se cierra en hub#1182). Si la lista no
   *  tiene el filtro que necesitas, **añádelo a su `list.filters`** — no lo mandes esperando que
   *  cuele, porque no falla: miente. */
  filters?: Record<string, unknown>;
  /** Params de **contexto obligatorios** que la query base referencia con su nombre crudo
   *  (p.ej. una sub-lista de hijos: `{ params: { bom_id } }` → bindea `:bom_id`). Se pasan
   *  verbatim al wire, sin prefijo `f_`.
   *
   *  ⚠️ **Solo lo que el SQL base referencia de verdad** (hub#1173): un nombre que su SQL no
   *  bindea no es contexto, es un parámetro inventado, y el runtime lo rechaza con
   *  `unknown_filter` (422) en vez de ignorarlo. */
  params?: Record<string, unknown>;
}

/** Forma de `data` de una query de lista: la página + el total filtrado (para el pager). */
export interface Page<T = unknown> {
  rows: T[];
  total: number;
  limit: number;
  offset: number;
}

/** ¿Es un valor "vacío" que debe omitirse como filtro? (null/undefined/''). */
function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === '';
}

/** Aplana `ListParams` a los params del wire que entiende el runtime (`f_col`, `f_col_from`…). */
export function buildListParams(p: ListParams): Record<string, unknown> {
  // Params de contexto verbatim (p.ej. :bom_id de una sub-lista); el resto se aplana encima.
  const out: Record<string, unknown> = { ...(p.params ?? {}) };
  if (p.limit != null) out.limit = p.limit;
  if (p.offset != null) out.offset = p.offset;
  if (!isEmpty(p.search)) out.search = p.search;
  if (p.sort) out.sort = p.sort;
  if (p.dir) out.dir = p.dir;
  for (const [col, val] of Object.entries(p.filters ?? {})) {
    if (val !== null && typeof val === 'object' && ('from' in val || 'to' in val)) {
      const r = val as RangeFilter;
      if (!isEmpty(r.from)) out[`f_${col}_from`] = r.from;
      if (!isEmpty(r.to)) out[`f_${col}_to`] = r.to;
    } else if (!isEmpty(val)) {
      out[`f_${col}`] = val;
    }
  }
  return out;
}

// ── Controlador de listas (estado + re-consulta al runtime) ─────────────────────────────────
// (movido desde modules/_shared/ui/list-controller.ts) Agnóstico de framework: lo usan TODOS los
// CRUD para alimentar `<data-table serverSide>` sin reimplementar el estado en cada vista. La vista
// pasa un `onChange` que fuerza repintado (en Stencil: incrementar un @State) y lee
// `rows/total/loading/error/state` en render. Solo usa `queryPage` del cliente, que aplana los
// filtros a `f_<col>` y devuelve `{rows,total,limit,offset}`.

/** Forma de una página de lista. Alias de `Page`, para los consumidores del controlador. */
export type ListPage<T = unknown> = Page<T>;

/** The slice of the SDK client the controller needs (injectable in tests). */
export interface ListClient {
  queryPage<R = unknown>(name: string, params: ListParams): Promise<Page<R>>;
  /**
   * Decimals of the hub currency (`erplora().currencyDecimals`). Required only when the
   * controller declares `moneyFilters`: it is the scale of what the person types.
   */
  readonly currencyDecimals?: number;
}

export interface ListControllerOptions {
  /** Filas por página (default 50). */
  pageSize?: number;
  /** Orden inicial. */
  sort?: string;
  dir?: 'asc' | 'desc';
  /** Filtros iniciales (`col -> valor` o `col -> {from,to}`). */
  filters?: Record<string, unknown>;
  /** Params de contexto obligatorios iniciales (sub-listas: `{ bom_id }`). */
  context?: Record<string, unknown>;
  /**
   * Columns whose filter is MONEY stored in minor units (hub#2271). The person types the major
   * unit («12» for twelve euros); each edge travels as `majorToMinor(edge, client.currencyDecimals)`
   * so «from 12» does not match 0,12 €. The controller state keeps what was typed.
   */
  moneyFilters?: readonly string[];
  /** Columns whose filter is a QUANTITY stored in the 10⁶ scale (ADR-0147): «1,5» → 1 500 000. */
  quantityFilters?: readonly string[];
}

export interface ListControllerState {
  page: number; // 0-based
  pageSize: number;
  search: string;
  sort?: string;
  dir: 'asc' | 'desc';
  filters: Record<string, unknown>;
  /** Params de contexto obligatorios (sub-lista de hijos de un padre seleccionado). */
  context: Record<string, unknown>;
}

export class ListController<T = Record<string, unknown>> {
  rows: T[] = [];
  total = 0;
  loading = false;
  error = '';
  readonly state: ListControllerState;
  /** Descarta respuestas obsoletas si llegan fuera de orden (race de cargas concurrentes). */
  private seq = 0;
  private readonly moneyFilters: ReadonlySet<string>;
  private readonly quantityFilters: ReadonlySet<string>;

  constructor(
    private readonly client: ListClient,
    private readonly queryName: string,
    private readonly onChange: () => void = () => {},
    opts: ListControllerOptions = {},
  ) {
    this.state = {
      page: 0,
      pageSize: opts.pageSize ?? 50,
      search: '',
      sort: opts.sort,
      dir: opts.dir ?? 'asc',
      filters: { ...(opts.filters ?? {}) },
      context: { ...(opts.context ?? {}) },
    };
    this.moneyFilters = new Set(opts.moneyFilters ?? []);
    this.quantityFilters = new Set(opts.quantityFilters ?? []);
    if (this.moneyFilters.size > 0 && typeof client.currencyDecimals !== 'number') {
      // Guessing 2 would filter 100 times off in a yen hub: refuse where the screen is wired.
      throw new ErploraError(
        'list_money_filters_need_currency_decimals',
        'moneyFilters needs a list client that exposes currencyDecimals',
      );
    }
  }

  /**
   * The filters as the runtime compares them: money and quantity columns scaled from what the
   * person typed to the stored integer. `state.filters` stays as typed, so a table that echoes it
   * back keeps showing «12», not «1200».
   */
  private wireFilters(): Record<string, unknown> {
    if (this.moneyFilters.size === 0 && this.quantityFilters.size === 0) return this.state.filters;
    const decimals = this.client.currencyDecimals ?? 0;
    const out: Record<string, unknown> = {};
    for (const [col, value] of Object.entries(this.state.filters)) {
      const scale = this.moneyFilters.has(col)
        ? (n: number) => majorToMinor(n, decimals)
        : this.quantityFilters.has(col)
          ? toMicro
          : null;
      out[col] = scale ? scaleFilterValue(value, scale) : value;
    }
    return out;
  }

  /** Nº de páginas según el total del servidor (mínimo 1). */
  get pageCount(): number {
    return Math.max(1, Math.ceil(this.total / this.state.pageSize));
  }

  /**
   * (Re)loads the current page from the server. On a phone, after «Load more» (hub#2365), the
   * current page is everything shown so far: a refresh brings back pages 0..page in one request.
   */
  async load(): Promise<void> {
    const s = this.state;
    const mySeq = ++this.seq;
    const paging = mobilePagingOf(this);
    const window = nextListWindow(paging, s);
    this.loading = true;
    this.error = '';
    this.onChange();
    try {
      const page = await this.client.queryPage<T>(this.queryName, {
        limit: window.limit,
        offset: window.offset,
        search: s.search,
        sort: s.sort,
        dir: s.dir,
        filters: this.wireFilters(),
        params: s.context,
      });
      if (mySeq !== this.seq) return; // llegó una carga más reciente
      const rows = page.rows ?? [];
      this.rows = window.append ? [...this.rows, ...rows] : rows;
      this.total = page.total ?? this.rows.length;
      if (window.growsTo !== undefined) {
        s.page = window.growsTo;
        keepAccumulating(paging, () => void this.load());
      }
    } catch (e) {
      if (mySeq !== this.seq) return;
      this.rows = [];
      this.total = 0;
      // Never blank: a blank `error` is «no error» for the table, which would go back to
      // «No customers» + «0 records» over a hub that did not answer (pm#530).
      const reason = e instanceof Error ? e.message.trim() : '';
      this.error = tableReadReason(e, activeLocale()) || reason || listLoadFailedMessage(activeLocale());
    } finally {
      if (mySeq === this.seq) {
        this.loading = false;
        this.onChange();
      }
    }
  }

  /**
   * Goes to `page`. On a phone `<ok-data-table>` has no pager, only «Load more», which asks for
   * `page + 1`: that one is ADDED under the rows already shown (hub#2365). Any other jump replaces.
   */
  setPage(page: number): void {
    const next = Math.max(0, page);
    const paging = mobilePagingOf(this);
    if (next === this.state.page + 1 && phoneViewport()?.matches) {
      paging.growNext = true;
    } else {
      stopAccumulating(paging);
      this.state.page = next;
    }
    void this.load();
  }

  setSort(sort: string, dir: 'asc' | 'desc'): void {
    this.state.sort = sort;
    this.state.dir = dir;
    this.state.page = 0;
    void this.load();
  }

  setSearch(search: string): void {
    this.state.search = search;
    this.state.page = 0;
    void this.load();
  }

  /** Cambia el nº de filas por página y recarga desde la página 0. */
  setPageSize(pageSize: number): void {
    this.state.pageSize = Math.max(1, pageSize);
    this.state.page = 0;
    void this.load();
  }

  /** Aplica/quita un filtro de columna; valores vacíos lo eliminan. Vuelve a la página 0. */
  setFilter(col: string, value: unknown): void {
    if (isEmpty(value)) {
      delete this.state.filters[col];
    } else if (typeof value === 'object' && value !== null) {
      // Rango parcial {from}/{to}: fusiona con lo existente para no perder el otro extremo.
      const prev = (this.state.filters[col] as Record<string, unknown>) ?? {};
      const merged = { ...prev, ...(value as Record<string, unknown>) };
      const cleaned = Object.fromEntries(Object.entries(merged).filter(([, v]) => !isEmpty(v)));
      if (Object.keys(cleaned).length === 0) delete this.state.filters[col];
      else this.state.filters[col] = cleaned;
    } else {
      this.state.filters[col] = value;
    }
    this.state.page = 0;
    void this.load();
  }

  /** Fija/actualiza los params de contexto obligatorios (p.ej. al seleccionar el padre).
   *  Vuelve a la página 0 y recarga. Pasa `{}` o keys con valor vacío para limpiar. */
  setContext(context: Record<string, unknown>): void {
    this.state.context = { ...context };
    this.state.page = 0;
    void this.load();
  }

  reset(): void {
    this.state.page = 0;
    this.state.search = '';
    this.state.filters = {};
    void this.load();
  }
}

// ── «Load more» on a phone (hub#2365) ────────────────────────────────────────────────────────
// Kept outside the class on purpose: it is private state, and a private field would still land in
// the frozen kernel surface (`contracts/kernel/sdk.d.ts`) that the declarations are checked against.

/** `<ok-data-table>`'s phone edge (OutfitKit `MOBILE_BREAKPOINT`): no pager there, only «Load more». */
const PHONE_MEDIA = '(max-width: 640px)';

interface ViewportQuery {
  readonly matches: boolean;
  addEventListener?(type: 'change', listener: (e: { matches: boolean }) => void): void;
  removeEventListener?(type: 'change', listener: (e: { matches: boolean }) => void): void;
}

/** The phone media query, or `null` where there is no window (tests, workers). */
function phoneViewport(): ViewportQuery | null {
  const matchMedia = (globalThis as { matchMedia?: (query: string) => ViewportQuery }).matchMedia;
  return typeof matchMedia === 'function' ? matchMedia(PHONE_MEDIA) : null;
}

interface MobilePaging {
  /** `rows` hold pages 0..state.page (a phone asked for more at least once). */
  accumulated: boolean;
  /** The next `load()` grows the list by one page instead of reloading (set by `setPage`). */
  growNext: boolean;
  /** Stops watching the phone edge (watched only while `accumulated`). */
  unwatch?: () => void;
}

const mobilePaging = new WeakMap<object, MobilePaging>();

function mobilePagingOf(ctrl: object): MobilePaging {
  let paging = mobilePaging.get(ctrl);
  if (!paging) {
    paging = { accumulated: false, growNext: false };
    mobilePaging.set(ctrl, paging);
  }
  return paging;
}

interface ListWindow {
  offset: number;
  limit: number;
  /** Glue the answer under the current rows instead of replacing them. */
  append: boolean;
  /** The page the list reaches when the answer lands (only when growing). */
  growsTo?: number;
}

/** What the next `load()` asks for. Consumes a pending «Load more». */
function nextListWindow(paging: MobilePaging, s: ListControllerState): ListWindow {
  const size = s.pageSize;
  const grow = paging.growNext;
  paging.growNext = false;
  if (grow) {
    const target = s.page + 1;
    // The rows cover 0..page (page 0, or already accumulated): only the next page is missing.
    if (paging.accumulated || s.page === 0) {
      return { offset: target * size, limit: size, append: true, growsTo: target };
    }
    // A page reached with a desktop pager (then turned into a phone): fill everything up to target.
    return { offset: 0, limit: (target + 1) * size, append: false, growsTo: target };
  }
  if (s.page === 0) stopAccumulating(paging); // a new result set (search, filter, sort…) starts over
  if (paging.accumulated) return { offset: 0, limit: (s.page + 1) * size, append: false };
  return { offset: s.page * size, limit: size, append: false };
}

/** Marks the rows as accumulated and, once, watches for the phone turning into a desktop pager. */
function keepAccumulating(paging: MobilePaging, reload: () => void): void {
  paging.accumulated = true;
  if (paging.unwatch) return;
  const viewport = phoneViewport();
  if (!viewport?.addEventListener) return;
  const onChange = (e: { matches: boolean }): void => {
    if (e.matches) return;
    // The pager is back and says «page N»: show page N on its own, not everything up to it.
    stopAccumulating(paging);
    reload();
  };
  viewport.addEventListener('change', onChange);
  paging.unwatch = () => viewport.removeEventListener?.('change', onChange);
}

function stopAccumulating(paging: MobilePaging): void {
  paging.accumulated = false;
  paging.unwatch?.();
  paging.unwatch = undefined;
}

/**
 * One typed edge (major units) → the stored integer. The table emits a Number from the panel and
 * text from the inline control («12,5» included). Empty or not a number → `''`, which
 * `buildListParams` drops: a stray keystroke never becomes «from 0».
 */
function scaleFilterEdge(edge: unknown, scale: (n: number) => number): unknown {
  const text = typeof edge === 'string' ? edge.trim().replace(',', '.') : edge;
  if (text === '' || text === null || text === undefined) return '';
  const n = Number(text);
  return Number.isFinite(n) ? scale(n) : '';
}

/** A `{ from?, to? }` range scaled edge by edge; a plain value is one edge. */
function scaleFilterValue(value: unknown, scale: (n: number) => number): unknown {
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([edge, v]) => [edge, scaleFilterEdge(v, scale)]),
    );
  }
  return scaleFilterEdge(value, scale);
}

const LIST_LOAD_FAILED_EN = 'The hub did not return the data.';
const LIST_LOAD_FAILED_ES = 'El hub no ha devuelto los datos.';

/** The reason of a failed load that came without one (same locale rule as {@link dataTableLabels}). */
function listLoadFailedMessage(locale: string): string {
  return locale.toLowerCase().startsWith('en') ? LIST_LOAD_FAILED_EN : LIST_LOAD_FAILED_ES;
}

/** Fábrica del controlador de lista (azúcar sobre `new ListController`). */
export function createListController<T = Record<string, unknown>>(
  client: ListClient,
  queryName: string,
  onChange: () => void = () => {},
  opts: ListControllerOptions = {},
): ListController<T> {
  return new ListController<T>(client, queryName, onChange, opts);
}

/** Error de una llamada al runtime, con el `code` que devuelve el server. */
export class ErploraError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    /**
     * The missing permission, present only on `requires_elevation` (hub#360): the refusal the
     * dispatcher reports when a **manager** could approve the action. It is what the approval
     * dialog names and what the runtime re-checks — read the field, never parse the message.
     * A flat `permission_denied` leaves it `undefined` on purpose: it is not an offer to elevate.
     */
    public readonly permission?: string,
    /**
     * The fields the payload schema refused, present only on `invalid_payload` (hub#1094): the
     * runtime splits them off the detail (`registry::invalid_payload_fields`) so the screen can
     * MARK those controls. Read the field, never parse the message — the message is prose and
     * translatable, the list is not. `undefined` on every refusal that names no field. A typed
     * `invalid_field` refusal of the core (one `field` + a stable `reason`, hub#1070) lands here
     * too, as a one-element list.
     */
    public readonly fields?: readonly string[],
    /**
     * How many seconds a lock has left, present only when the refusal names a usable wait — today
     * `too_many_attempts` at the manager's approval, `error.retry_after_secs` (hub#2290). The shell
     * says «Wait N minutes» from it instead of a vague «a few». `undefined` when the runtime named
     * none or something that is not a non-negative number — never a made-up wait.
     */
    public readonly retryAfterSecs?: number,
  ) {
    super(message);
    this.name = 'ErploraError';
  }
}

// ── Step-up approval: the wire half of the manager's PIN (hub#363, ADR-0238/0246) ────────────
//
// **Published contract of the runtime. None of these three names is ours to rename** — the code,
// the path and the header are what `crates/server` answers, routes and reads (hub#361).

/** The stable code the dispatcher answers when a **manager** could approve the action (hub#360). */
export const REQUIRES_ELEVATION = 'requires_elevation';
/** Where a PIN is verified. The runtime is the authority; the client never checks digits. */
export const ELEVATION_APPROVE_PATH = '/api/elevation/approve';
/** The header that presents a minted approval on the ONE retry it buys. */
export const ELEVATION_TOKEN_HEADER = 'X-Elevation-Token';

/** A minted approval, as `POST /api/elevation/approve` returns it. */
export interface ElevationApproval {
  /** Opaque, single-use, bound to this exact action. Meaningless outside the hub's runtime. */
  token: string;
  /** The permission that was stepped up to — the same one the refusal named. */
  permission: string;
  /** `hub_user.id` of the manager. The runtime stamps it as `approved_by`; nothing here does. */
  approvedBy: string;
  /** Their name, for the confirmation the cashier sees («approved by Sofía»). */
  approverName: string;
  /** How long an UNUSED approval stays spendable. A ceiling, never a window to work inside. */
  expiresInSeconds: number;
}

/**
 * What the shell's dialog is being asked to get approved.
 *
 * `approve` is a **function**, not a pair of fields, because a refused PIN must not tear the flow
 * down: the manager mistyped, they retype, and the dialog stays open. It throws {@link
 * ErploraError} with the runtime's stable `hub.elevation.*` code so the screen can say something
 * useful — and so no screen has to know the endpoint.
 */
export interface ElevationAsk {
  /** The command that was refused. */
  command: string;
  /** Its payload, **exactly as sent**: the grant is fingerprinted on it. */
  payload: Record<string, unknown>;
  /** The permission the refusal named as a field (hub#360) — never parsed out of the message. */
  permission: string;
  approve(approver: string, pin: string): Promise<ElevationApproval>;
  /**
   * The same approval, presented as a **badge** (hub#658).
   *
   * A separate door and not an overload of `approve` because a badge resolves the whole person: it
   * replaces the (name, PIN) **pair**, so there is no name to pass. What it does NOT change is who
   * may approve — the runtime asks exactly the same questions of both and answers with the same
   * `hub.elevation.*` codes.
   */
  approveWithBadge(badge: string): Promise<ElevationApproval>;
}

/**
 * The shell's approval dialog. Resolves with the **token** to retry with, or `null` when nobody
 * approved (the cashier closed the dialog) — in which case the caller sees the refusal it already
 * had, unchanged.
 */
export type ElevationApprover = (ask: ElevationAsk) => Promise<string | null>;

/**
 * The hub (or the proxy in front of it) did NOT answer with the JSON envelope the runtime always
 * returns — the transport is down (hub#782).
 *
 * Surfaces from `post()` in three shapes that used to escape as raw, code-less errors:
 *   - a `5xx text/html` error page from the proxy (the hub container died, OOM exit 137 / hub#759;
 *     any deploy or restart window) — `res.json()` blew up with `SyntaxError: Unexpected token '<'`;
 *   - a response whose body is not valid JSON regardless of its `Content-Type`;
 *   - a network-level failure of `fetch` itself (`TypeError: Failed to fetch`, DNS, CORS, abort).
 *
 * They collapse to ONE code on purpose: from a module's point of view all three mean «the hub did
 * not reply with something usable», and the UI shows one message and (maybe) retries — splitting
 * them would only force every one of the 24 modules to repeat the same `||`. A domain refusal
 * (`PermissionDenied` → 403 + JSON envelope) is NOT this: it carries its own `code`
 * (`permission_denied`, `requires_elevation`, …) and flows through `unwrap` untouched.
 */
export const SERVER_UNAVAILABLE = 'server_unavailable';

// ── hub#906: the honest verdict of a command the hub never answered ──────────────────────────
//
// A QUERY that failed did nothing. A COMMAND that failed may have COMMITTED: in the incident that
// motivates this (saas#1460), the runtime accepted `complete_sale` (200 in its own log) and was
// OOM-killed before the client could read the response — the cashier saw a raw WebKit exception,
// concluded «it did not charge», and charged again: double charge, duplicated fiscal document.
// The client cannot know which side of the commit the failure fell on, and pretending either way
// is the bug. So the command path presents the only honest verdict: «we can't tell — check before
// trying again». No automatic retry is ever added here: retrying a charge is how a fiscal
// document gets duplicated.

/**
 * The honest sentence, per locale (en is the source, es the translation — ADR-0055). Localized
 * HERE, like `dataTableLabels`, because this error's `message` is what modules and the shell's
 * toast show verbatim; a technical English line in front of a cashier is the failure being fixed.
 *
 * It says only what holds for ANY command (hub#2342): the same sentence answers saving a flow, a
 * template or the certificate, so a tail about charges and Sales would mislead there. The charge
 * guidance lives in the charge flow itself — the POS of `sales` renders its own «we can't tell
 * whether it charged» panel with a link to Sales (sales#91).
 */
const COMMAND_VERDICT_EN = "We can't tell whether the operation completed. Check the result before trying again.";
const COMMAND_VERDICT_ES = 'No sabemos si la operación se completó. Comprueba el resultado antes de reintentar.';

/** The unknown-outcome sentence for `locale` (same resolution rule as {@link dataTableLabels}). */
export function commandVerdictMessage(locale = 'es'): string {
  return locale.toLowerCase().startsWith('en') ? COMMAND_VERDICT_EN : COMMAND_VERDICT_ES;
}

// ── hub#2288: a READ the hub never answered ──────────────────────────────────────────────────
//
// A query that failed did nothing, so there is no verdict to give — only what happened and what
// to do: the screen could not load its data, and trying again is safe. Localized here for the same
// reason as the command verdict: modules and the list controller paint `message` verbatim.
const READ_UNREACHABLE_EN =
  'The data could not be loaded because the hub is not responding. Check the connection and try again.';
const READ_UNREACHABLE_ES =
  'No se han podido cargar los datos porque el hub no responde. Comprueba la conexión e inténtalo de nuevo.';

// hub#2404: the shell's table already paints «Couldn't load the data» as the heading of its error
// state, so under it the reason gives only the why and what to do. The full sentence above stays
// for every place that shows the reason alone: toasts, banners, and an older table without that state.
const READ_UNREACHABLE_UNDER_HEADING_EN = 'The hub is not responding. Check the connection and try again.';
const READ_UNREACHABLE_UNDER_HEADING_ES = 'El hub no responde. Comprueba la conexión e inténtalo de nuevo.';

/**
 * The list reason for a read the hub never answered, when the table paints it under its heading.
 * By `code`, not `instanceof`: the list controller is baked into each module's bundle, while the
 * error comes from the shell's client, whose ErploraError is another bundle's class.
 */
function tableReadReason(e: unknown, locale: string): string {
  if ((e as { code?: unknown } | null)?.code !== SERVER_UNAVAILABLE || !dataTableShowsLoadError()) return '';
  return locale.toLowerCase().startsWith('en') ? READ_UNREACHABLE_UNDER_HEADING_EN : READ_UNREACHABLE_UNDER_HEADING_ES;
}

/**
 * The error a read gets when its transport failed: {@link SERVER_UNAVAILABLE} as before (hub#782),
 * the sentence a person may read as `message`, and the transport's technical line on `cause`.
 * Anything else — a domain refusal, `module_not_installed` — passes through untouched.
 */
function unreachableRead(e: unknown, locale: string): unknown {
  if (!(e instanceof ErploraError) || e.code !== SERVER_UNAVAILABLE) return e;
  const sentence = locale.toLowerCase().startsWith('en') ? READ_UNREACHABLE_EN : READ_UNREACHABLE_ES;
  const read = new ErploraError(SERVER_UNAVAILABLE, sentence);
  read.cause = e;
  return read;
}

/**
 * The error a command gets when its transport failed (hub#906): the unknown-outcome verdict, with
 * the transport's technical line on `cause`, and the shell's notifier told once as the default net.
 * Anything else — a domain refusal, `module_not_installed` — passes through untouched.
 */
function unknownOutcome(e: unknown, locale: string, notifier?: (n: Notification) => void): unknown {
  if (!(e instanceof ErploraError) || e.code !== SERVER_UNAVAILABLE) return e;
  const verdict = new UnknownOutcomeError(commandVerdictMessage(locale), e);
  notifier?.({ type: 'error', message: verdict.message });
  return verdict;
}

/**
 * A call on the core's REST surface the hub never answered. A `GET` is a read like any query — the
 * flow gallery and the templates tab load through it — so it gets the read sentence (hub#2288). A
 * write (saving a flow, registering a template, uploading the certificate, retrying a print job)
 * may have committed before the answer was lost, exactly like a command, so it gets the command
 * verdict (hub#2320): «could not be loaded» would be a lie there.
 */
function coreCall<R>(
  request: Promise<R>,
  method: string,
  locale: string,
  notifier?: (n: Notification) => void,
): Promise<R> {
  return request.catch((e: unknown) => {
    throw method === 'GET' ? unreachableRead(e, locale) : unknownOutcome(e, locale, notifier);
  });
}

/**
 * A command the hub never answered (hub#906). `code` stays {@link SERVER_UNAVAILABLE} — the
 * contract modules already key on since hub#782 — and the verdict travels as the **data field**
 * `outcomeUnknown`, never as an `instanceof`: module bundles may carry their own copy of this
 * class, and a plain field survives that where the prototype chain does not. The technical
 * transport line is kept on `cause` for logs; `message` is the sentence a person may read.
 */
export class UnknownOutcomeError extends ErploraError {
  readonly outcomeUnknown = true;

  constructor(message: string, cause: unknown) {
    super(SERVER_UNAVAILABLE, message);
    this.name = 'UnknownOutcomeError';
    this.cause = cause;
  }
}

/** Sobre de respuesta estándar del server Axum (`crates/server`). */
interface Envelope {
  ok: boolean;
  data?: unknown;
  error?: PlatformFailure & {
    message: string;
    permission?: string;
    fields?: string[];
    field?: string;
    retry_after_secs?: unknown;
  };
}

// ── hub#1102: a PLATFORM failure is not a sentence a module wrote ────────────────────────────
//
// With `taxes` uninstalled, the pay dialog of the till showed «required read `taxes.rules.list` is
// unavailable — the command was aborted (hub#701)»: English, backticks, an internal query name and
// a GitHub issue number, in front of a customer. `erp-pos-touch` was doing the ordinary thing —
// `this.error = e.message` — and so does every one of the 25 modules, which is why this belongs
// here and not in `sales`: fixing it there fixes it once and misses the other 24.
//
// The runtime half is hub#1074: the plumbing stopped travelling as prose and what reaches the wire
// is a stable `code` plus the app as a FIELD. This is the other half. Two rules hold it honest:
//
//  1. only PLATFORM codes are rewritten. A module's domain refusal (`inventory.insufficient_stock`,
//     ADR-0205/hub#139) is the module saying something true about the request, and overwriting it
//     would silence exactly the channel that works;
//  2. an unrecognised code keeps whatever the runtime sent. A sentence we invented for a code we do
//     not know says strictly less than the one that arrived.

/** The fields of an error envelope this SDK reads. Everything is optional: older runtimes. */
export interface PlatformFailure {
  code?: string;
  /** The app a refusal is ABOUT (`module_not_installed`, `module_inactive`, `missing_dependency`). */
  module?: string;
  /** The `required` read that could not be resolved (`read_unavailable`). */
  query?: string;
  /** The refused field of an `invalid_field` (hub#1070/#1185): `name`, `role_key`, `language`… */
  field?: string;
  /** WHY it was refused: `required` · `too_long` · `format` · `length` · `unknown` · `immutable`
   *  · `inactive` on an `invalid_field`; on a `read_unavailable` (hub#2410),
   *  `module_not_installed` · `module_inactive` · `query_failed`. A small closed set, so a screen
   *  branches on it instead of reading the prose. */
  reason?: string;
}

/** A localized sentence, `en` source + `es` translation (ADR-0055). */
type Bilingual = { en: string; es: string };

/**
 * The app id a sentence should send the user after, or `''` when the runtime named none.
 *
 * The RAW id on purpose, exactly like `appLabel` in the shell: the human name lives in the
 * marketplace catalogue, which this SDK cannot reach, and prettifying `cash_register` into
 * «Cash Register» would invent a name the owner will not find in Apps either.
 */
function appOf(failure: PlatformFailure): string {
  if (failure.module) return failure.module;
  // `read_unavailable` names the query (`taxes.rules.list`); its owner is the first segment.
  return failure.query?.split('.')[0] ?? '';
}

/** «The operation did not happen and there is nothing you can do about it here.» */
const PLUMBING: Bilingual = {
  en: 'The operation could not be completed. Try again, and tell an administrator if it keeps happening.',
  es: 'No se pudo completar la operación. Inténtalo de nuevo y avisa a un administrador si sigue pasando.',
};

/**
 * The stable code the runtime gives a refusal that means «sign in again» (`AuthError::code`,
 * `crates/server/src/auth.rs`, hub#1241). The two busiest doors, `/api/query` and `/api/command`,
 * answer a dead session with a bare-string error and no code at all (`dispatch_api::unauthorized`),
 * so {@link unwrap} names it for them from the 401 (hub#2281).
 */
const SESSION_REFUSED = 'unauthorized';

/**
 * «Your session is over: sign in again.» The same sentence the shell toasts when it closes the
 * session (`auth.sessionEnded`), so the banner of a module and the toast above it agree.
 */
const SESSION_ENDED: Bilingual = {
  en: 'Your session has ended: it expired or was opened on another device. Please sign in again.',
  es: 'Tu sesión ha terminado: caducó o se abrió en otro dispositivo. Vuelve a entrar.',
};

/**
 * The codes a person can meet at a counter, and what to tell them.
 *
 * The plumbing family is every code whose message hub#1074 now redacts to a fixed English line
 * written for the log: it is the same event to whoever is standing there, so it is one sentence.
 * The missing/inactive app family is NOT folded into it — «install it» and «switch it back on» are
 * different actions, and a screen that cannot tell them apart sends the owner to the wrong place.
 */
const PLATFORM_FAILURES: Record<
  string,
  // hub#1337: `null` = «there is nothing better to say than what already arrived». Only `other`
  // answers it today, and only when the runtime let an authored sentence through.
  (app: string, failure: PlatformFailure) => Bilingual | null
> = {
  // hub#2410: the kernel says WHY the read did not resolve, and only one of the three causes is
  // fixed from Apps. A runtime that sends no `reason` (or one this SDK does not know) keeps the
  // sentence every screen showed before it.
  read_unavailable: (app, failure) =>
    failure.reason === 'query_failed'
      ? READ_FAILED
      : failure.reason === 'module_inactive'
        ? switchedOffApp(app)
        : missingApp(app),
  module_not_installed: (app) => missingApp(app),
  missing_dependency: (app) => missingApp(app),
  module_inactive: (app) => switchedOffApp(app),
  // hub#2434: not plumbing and not the request — the business has not filled in what an invoice
  // needs. The runtime lists it in `missing`; the sentence names it and says where it is done.
  fiscal_precondition_failed: (_app, failure) => fiscalSetupMissing(missingOf(failure)),
  // hub#2383: a query asked without a value its SQL needs. It used to answer «there is nothing»;
  // now it refuses, naming the query and the bind as fields for whoever fixes the call. The person
  // reading did nothing wrong and cannot fix it here, but «nothing was found» would be a lie.
  missing_required_param: () => ASKED_WITHOUT_A_VALUE,
  db: () => PLUMBING,
  io: () => PLUMBING,
  wasm: () => PLUMBING,
  // hub#2428: redacted like `wasm`, but it is not a crash — the action was too big for the hub's
  // instruction budget and was rolled back whole. «Try again» would repeat the same click.
  wasm_budget_exceeded: () => TOO_BIG_AT_ONCE,
  // hub#2431: the same for a handler the hub's clock interrupted — rolled back whole, not a crash.
  wasm_timeout: () => TOO_LONG_AT_ONCE,
  native: () => PLUMBING,
  schema: () => PLUMBING,
  // hub#1315: a module.json the installer refuses at install time (`RuntimeError::Manifest`) is
  // redacted by `may_reach_the_client` exactly like its five siblings above — this table just
  // never had to answer it before the shell's own copy (`apps/web/src/lib/platform-failure.ts`,
  // hub#1258) started covering `manifest` over vue-i18n keys instead of here.
  manifest: () => PLUMBING,
  // hub#1337: `other` is NOT one of them. `may_reach_the_client` puts `E::Other(_)` on the SPEAKING
  // side of the door — beside `Domain`, `PermissionDenied`, `InvalidField` — with
  // `carries_driver_text` as the net underneath, exactly so the readable half of the ~50
  // `Other(...)` sites («usuario no encontrado», `crates/runtime/src/hub_users.rs`) reaches whoever
  // is reading and the half that wraps a `DbError` does not. Answering PLUMBING here threw that
  // decision away and showed the generic line for all of them. So: step aside when the runtime let
  // a sentence through, and speak only when it redacted one (or when there is none to keep).
  other: (_app, failure) => (authoredSentenceOf(failure) ? null : PLUMBING),
  // The bucket every unmapped runtime error fell into before hub#1074, and what an older hub still
  // answers. Its message is plumbing by definition — that is what put driver text on a till.
  //
  // hub#1337: this is why it does NOT follow `other` above. One commit separates them — hub#1074
  // (`594eb485`) replaced the door's flat `_ => "error"` bucket with `error_code_of`, where `other`
  // comes from, in the SAME change that added `may_reach_the_client`. A hub that answers `other` is
  // therefore a hub that already redacts, and its sentence is safe to keep; a hub that answers
  // `error` is one from before that gate, whose bucket carried the driver's own words unfiltered.
  error: () => PLUMBING,
};

/**
 * The line `error_payload` (`crates/server/src/lib.rs`, `REDACTED_MESSAGE`) sends INSTEAD of a
 * sentence, when the one it had was plumbing (hub#1074).
 *
 * Mirrored rather than imported — it crosses a language boundary — and kept honest by a guard in
 * `platform-failure.test.ts` that reads the constant straight out of the Rust and compares.
 */
const RUNTIME_REDACTED_LINE = 'the request could not be completed — the hub recorded the details';

/**
 * The sentence the runtime WROTE for whoever is reading, or `undefined` when it wrote none.
 *
 * `undefined` covers the two ways there is nothing to keep: the runtime redacted what it had
 * (the fixed English line above, aimed at the log), or no message travelled at all — an older
 * runtime, or a caller that only carries the code.
 *
 * Read off the envelope's `error` object, which always carries it ({@link Envelope}), but
 * deliberately NOT declared on the public {@link PlatformFailure}: it is not something a CALLER has
 * to supply to get a sentence, and every field of that interface is part of the frozen kernel
 * surface (`contracts/kernel/sdk.d.ts`, ADR «El Hub se CIERRA como KERNEL»).
 */
function authoredSentenceOf(failure: PlatformFailure): string | undefined {
  const sentence = (failure as { message?: unknown }).message;
  if (typeof sentence !== 'string') return undefined;
  const trimmed = sentence.trim();
  if (!trimmed || trimmed === RUNTIME_REDACTED_LINE) return undefined;
  return trimmed;
}

// 🔴 `invalid_field` (hub#1070/#1185) is deliberately NOT in the table above.
//
// It is produced only by the CORE's own doors — staff, the role catalogue, one's own profile —
// which are screens of the shell (`apps/web`), not surfaces a module's Web Component ever calls.
// And a sentence this SDK could build out of `field` + `reason` («the field “role_key” is not
// valid») says strictly LESS than the `detail` the runtime already sends, which names the role,
// the length or the accepted values. Rule 2 above applies to it like to any other unknown code:
// the sentence that arrived wins.
//
// What this SDK does do is carry `field` and `reason` on {@link PlatformFailure}, so a screen that
// wants to translate them branches on data instead of parsing prose. Translating them into the
// user's language belongs to the shell that owns those forms — see hub#1190.

/**
 * «Too big to do in one go, and nothing changed» (hub#2428): a module handler ran out of the hub's
 * instruction budget and the whole command was rolled back. The remedy is asking for less at once,
 * not trying again.
 */
const TOO_BIG_AT_ONCE: Bilingual = {
  en: 'This action is too big to do in one go. Nothing was changed: try with fewer items or a shorter range.',
  es: 'Esta acción es demasiado grande para hacerla de una vez. No se ha cambiado nada: prueba con menos elementos o un rango más corto.',
};

/**
 * «It took too long, and nothing changed» (hub#2431): a module handler ran past the hub's time limit
 * and the whole command was rolled back. The remedy is asking for less at once, not trying again.
 */
const TOO_LONG_AT_ONCE: Bilingual = {
  en: 'This action took too long to finish. Nothing was changed: try with fewer items or a shorter range.',
  es: 'Esta acción ha tardado demasiado en terminar. No se ha cambiado nada: prueba con menos elementos o un rango más corto.',
};

/**
 * «The app is there, but a piece of what this needs could not be read» (hub#2410): a `required`
 * read of an installed, active app failed — a passing fault, not something Apps can fix. The app is
 * deliberately NOT named: naming it is what sent the owner to Apps to look for it.
 */
/**
 * «The screen asked without a value it needs, so nothing was looked up» (hub#2383): NOT «there is
 * nothing», which is what the empty answer used to say.
 */
const ASKED_WITHOUT_A_VALUE: Bilingual = {
  en: 'This screen asked for information without a value it needs, so nothing was looked up. Try again, and tell an administrator if it keeps happening.',
  es: 'Esta pantalla pidió información sin un dato que necesita, así que no se ha buscado nada. Inténtalo de nuevo y avisa a un administrador si sigue pasando.',
};

const READ_FAILED: Bilingual = {
  en: 'Some information this action needs could not be read, so nothing was done. Try again, and tell an administrator if it keeps happening.',
  es: 'No se pudo leer un dato que esta acción necesita, así que no se ha hecho nada. Inténtalo de nuevo y avisa a un administrador si sigue pasando.',
};

function switchedOffApp(app: string): Bilingual {
  return {
    en: app
      ? `The app “${app}” is switched off and this action needs it. Ask an administrator to switch it back on from Apps.`
      : 'An app this action needs is switched off. Ask an administrator to switch it back on from Apps.',
    es: app
      ? `La app «${app}» está desactivada y esta acción la necesita. Pide a un administrador que vuelva a activarla desde Apps.`
      : 'Una app que esta acción necesita está desactivada. Pide a un administrador que vuelva a activarla desde Apps.',
  };
}

function missingApp(app: string): Bilingual {
  return {
    en: app
      ? `The app “${app}” is missing and this action needs it. Ask an administrator to install it from Apps.`
      : 'An app this action needs is not installed. Ask an administrator to install it from Apps.',
    es: app
      ? `Falta la app «${app}» y esta acción la necesita. Pide a un administrador que la instale desde Apps.`
      : 'Falta una app que esta acción necesita. Pide a un administrador que la instale desde Apps.',
  };
}

/**
 * What the fiscal precondition is missing, as the runtime sent it (hub#2434), or `[]`.
 *
 * Read off the envelope like {@link authoredSentenceOf} reads `message`, and NOT declared on the
 * public {@link PlatformFailure} for the same reason: that interface is frozen kernel surface.
 */
function missingOf(failure: PlatformFailure): string[] {
  const missing = (failure as { missing?: unknown }).missing;
  return Array.isArray(missing) ? missing.filter((m): m is string => typeof m === 'string') : [];
}

/**
 * The half of the business identity the Settings form holds (`Ajustes › Negocio`), in the words of
 * that form, with the article Spanish needs in front of each. The keys are the setting names
 * `enforce_fiscal_precondition` pushes into `missing` (`crates/runtime/src/commands.rs`).
 */
const FISCAL_IDENTITY_NAMES: Record<string, Bilingual> = {
  business_legal_name: { en: 'legal name', es: 'la razón social' },
  business_tax_id: { en: 'tax ID', es: 'el NIF' },
};

/** «… (an administrator can do it)» — the till user usually cannot open Settings. */
const WHO_CAN: Bilingual = {
  en: 'an administrator can do it',
  es: 'lo puede hacer un administrador',
};

/**
 * «To issue invoices, first complete …» (hub#2434): what the fiscal precondition (ADR-0203) is
 * missing, named in business words, and where each piece is filled in — the legal name and the tax
 * ID in Settings › Business, the digital certificate from the setup checklist on Home, where the
 * app that files with the tax agency asks for it. A requirement this SDK does not know (a newer
 * runtime) is left out rather than shown raw; with nothing known, the sentence points at the
 * checklist, which lists every piece.
 */
function fiscalSetupMissing(missing: string[]): Bilingual {
  const identity = missing.filter((m) => m in FISCAL_IDENTITY_NAMES).map((m) => FISCAL_IDENTITY_NAMES[m]!);
  const certificate = missing.includes('certificate');
  const identityEn = identity.map((n) => n.en).join(' and ');
  const identityEs = identity.map((n) => n.es).join(' y ');
  if (identity.length && certificate) {
    return {
      en: `To issue invoices, first complete the business's ${identityEn} in Settings › Business, and upload its digital certificate from «Finish setting up your business» on Home (${WHO_CAN.en}).`,
      es: `Para emitir facturas, completa primero ${identityEs} del negocio en Ajustes › Negocio, y sube su certificado digital desde «Termina de configurar tu negocio», en Inicio (${WHO_CAN.es}).`,
    };
  }
  if (identity.length) {
    return {
      en: `To issue invoices, first complete the business's ${identityEn} in Settings › Business (${WHO_CAN.en}).`,
      es: `Para emitir facturas, completa primero ${identityEs} del negocio en Ajustes › Negocio (${WHO_CAN.es}).`,
    };
  }
  if (certificate) {
    return {
      en: `To issue invoices, the business needs its digital certificate. Upload it from «Finish setting up your business» on Home (${WHO_CAN.en}).`,
      es: `Para emitir facturas, el negocio necesita su certificado digital. Súbelo desde «Termina de configurar tu negocio», en Inicio (${WHO_CAN.es}).`,
    };
  }
  return {
    en: `To issue invoices, first complete the business's fiscal details: you will find them in «Finish setting up your business» on Home (${WHO_CAN.en}).`,
    es: `Para emitir facturas, completa primero los datos fiscales del negocio: los tienes en «Termina de configurar tu negocio», en Inicio (${WHO_CAN.es}).`,
  };
}

/**
 * What to tell a person about a PLATFORM failure, or `null` when this is not one (hub#1102).
 *
 * `null` is the answer for a module's own domain code and for anything unrecognised — the caller
 * then keeps the sentence the runtime sent, which is the honest default. hub#1337: it is also the
 * answer for an `other` that arrived WITH such a sentence, because the runtime's own door
 * (`may_reach_the_client`) already decided that one may be read.
 */
export function platformFailureMessage(
  failure: PlatformFailure,
  locale = 'es',
): string | null {
  const entry = failure.code ? PLATFORM_FAILURES[failure.code] : undefined;
  if (!entry) return null;
  // hub#1337: an entry may also decide there is nothing better to say than what already arrived —
  // `other` does, when the runtime let an authored sentence through. Same answer as an unknown
  // code, and for the same reason: the sentence that arrived wins.
  const sentence = entry(appOf(failure), failure);
  if (!sentence) return null;
  return locale.toLowerCase().startsWith('en') ? sentence.en : sentence.es;
}

/**
 * The language the shell is running in, read the same way {@link ErploraClient.locale} reads it.
 *
 * Module-level and not a client method because {@link unwrap} runs in the TRANSPORT, below any
 * client: a refusal has to be readable on every path — `query`, `command`, and a module holding a
 * transport directly — and threading a locale through all of them to reach one string is how half
 * the paths end up in English.
 */
function activeLocale(): string {
  try {
    return localStorage.getItem('erplora.locale') || 'es';
  } catch {
    return 'es';
  }
}

// ── hub#1570: a module's DOMAIN refusal, in the module's own words ───────────────────────────
//
// ADR-0398 split the two halves of a domain code (ADR-0205, `<module>.<snake_case>`): the manifest
// declares that the code EXISTS and whether it is deprecated, and `locales/<lang>.json → errors`
// says what it SAYS — English the source, `es` the translation (ADR-0055), both forced by
// `erplora validate`. The runtime deliberately never reads that block (`manifest::ModuleLocale`
// keeps `name`/`navigation`/`setup` and nothing else), so the sentence only ever exists inside the
// module's own Web Component bundle.
//
// Which is why the SDK never read it: 21 modules ship 197 translated refusals (2026-09-05) and the
// SDK had no consumer — ten modules had each grown a by-code lookup of their own instead
// (`services`, `staff`, `tables`, `sales`, `pricing`, `appointments`, `invoice`, `kitchen`,
// `reservations`, `schedules`): the same fix, written ten times. Every other screen does the
// ordinary `this.error = e.message`, and `message` is whatever the handler or `expect_rows.error`
// wrote — English, on a Spanish till. Fixing it in a screen fixes it once and misses the rest (the
// same reasoning that put the PLATFORM half here, hub#1102).
//
// Five modules (`customers`, `online_booking`, `tasks`, `tickets`, `whatsapp_inbox`) still keep the
// pre-ADR-0398 NESTED shape, `errors.<module>.<name>`. That is not the contract and it is not read
// here: they stay on the server sentence until they migrate (their issues say so).
//
// The catalogue reaches us through the door every module already uses: `erplora.t(CATALOG, …)`,
// which each Web Component calls to render its own labels. Nothing to add in the 27 module repos —
// a module that translated its refusals gets them spoken by having been rendered.
const REFUSAL_TEXTS = new Map<string, Record<string, string>>();

/** Catalogues already indexed, by identity: `t()` runs on every render, this must not. */
const INDEXED_CATALOGS = new WeakSet<object>();

/**
 * A DOMAIN code and nothing else (ADR-0205): `<module>.<snake_case>`, exactly two segments.
 *
 * The guard is on the way IN, not on the way out: it keeps a catalogue with a stray key from ever
 * being able to answer for a core refusal (`not_found`, `permission_denied`) or for the core's
 * three-segment namespaces (`hub.fiscal.*`, `hub.elevation.*`) — a module does not get to rewrite
 * those. The core ALSO refuses in two-segment namespaces, which this shape cannot tell from a
 * module's: those are refused by name, {@link CORE_NAMESPACES}.
 */
const DOMAIN_CODE = /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/;

/**
 * Namespaces the CORE emits refusals in with the very shape of a module code: `flow.grant_denied`
 * (`crates/runtime/src/flows`), `hub.migration_lock_timeout` (`dispatch.rs`), `fiscal.hub_closed`
 * (`fiscal_profile.rs`), `print.not_ready` (`print_ws.rs`). No module is called any of these, and
 * none gets to speak for the core (interop-contract §8.5) — so a catalogue key in one of them is a
 * stray, and is never indexed.
 */
const CORE_NAMESPACES: ReadonlySet<string> = new Set(['hub', 'flow', 'fiscal', 'print']);

/** Is `code` a code some MODULE owns — the only kind a module catalogue may put words to? */
function isModuleCode(code: string): boolean {
  return DOMAIN_CODE.test(code) && !CORE_NAMESPACES.has(code.slice(0, code.indexOf('.')));
}

/**
 * Index the `errors` block of a module locale catalogue, in every language it carries — not only
 * the active one, so switching the hub's language later resolves without re-rendering.
 */
function rememberRefusalTexts(catalog: Record<string, unknown>): void {
  if (!catalog || typeof catalog !== 'object' || INDEXED_CATALOGS.has(catalog)) return;
  INDEXED_CATALOGS.add(catalog);
  for (const [lang, dict] of Object.entries(catalog)) {
    const errors = (dict as { errors?: unknown } | null)?.errors;
    if (!errors || typeof errors !== 'object') continue;
    for (const [code, text] of Object.entries(errors as Record<string, unknown>)) {
      if (typeof text !== 'string' || !text || !isModuleCode(code)) continue;
      const byLang = REFUSAL_TEXTS.get(code) ?? {};
      byLang[lang] = text;
      REFUSAL_TEXTS.set(code, byLang);
    }
  }
}

/**
 * What the module that owns `code` says about this refusal, in `locale`, or `null` when it never
 * said anything — in which case the sentence that arrived wins, exactly as for an unknown platform
 * code (hub#1102 rule 2): a sentence we invented says strictly less than the one the hub sent.
 *
 * Resolution is `locale → en → nothing`, the chain `ErploraClient.t` already uses. A text may
 * splice the server's own detail with `{message}` — `combos.combo_in_use` is written that way in
 * both languages, because the module wants its sentence AND the list the handler computed.
 */
function refusalText(code: string, locale: string, serverMessage: string): string | null {
  const byLang = REFUSAL_TEXTS.get(code);
  if (!byLang) return null;
  const text = byLang[locale] ?? byLang.en;
  if (!text) return null;
  return text.includes('{message}') ? text.replaceAll('{message}', serverMessage) : text;
}

/**
 * The envelope's `error` as the object this SDK reads, or `undefined` when it carries none.
 *
 * hub#2281: some doors still send `error` as a bare STRING of log prose — `/api/query` and
 * `/api/command` among them, for a dead session (`dispatch_api::unauthorized`). A string has no
 * code to branch on and nothing a person should read, so it counts as an empty refusal. A 401 that
 * names no code of its own is the session being refused, and gets the runtime's code for it; a 401
 * WITH a code (`hub_not_enrolled`: this hub has no machine credential) is about something else, and
 * signing in again would not fix it.
 */
function refusalOf(error: unknown, status?: number): Envelope['error'] | undefined {
  const e = error !== null && typeof error === 'object' ? (error as NonNullable<Envelope['error']>) : undefined;
  if (status === 401 && !e?.code) return { ...e, code: SESSION_REFUSED, message: e?.message ?? '' };
  return e;
}

function unwrap(env: Envelope, status?: number): unknown {
  if (!env.ok) {
    const e = refusalOf(env.error, status);
    // hub#1102: a platform failure is told in the user's language and in business words; a module's
    // own refusal (and any code we do not know) keeps the sentence it arrived with.
    //
    // hub#1570: below the platform half, a module's OWN refusal is spoken with the module's own
    // translated sentence when it published one (`locales/<lang>.json → errors`, ADR-0398). The
    // order is load-bearing: a platform code is never a module's to rewrite, and a code nobody
    // translated still keeps what arrived.
    const locale = activeLocale();
    // hub#2281: a refusal of the SESSION is said here, in the transport, and NOT in the public
    // platform table: the shell's own screens (Settings › Roles, hub#1705) run that table over their
    // refusals and answer `unauthorized` from their own catalogue when it stays silent.
    const sessionEnded = e?.code === SESSION_REFUSED;
    const spoken = e
      ? sessionEnded
        ? (locale.toLowerCase().startsWith('en') ? SESSION_ENDED.en : SESSION_ENDED.es)
        : (platformFailureMessage(e, locale) ??
          (e.code ? refusalText(e.code, locale, e.message ?? '') : null))
      : null;
    // hub#2281: the last resort is a sentence a person can act on, in their language — never
    // «unknown error». It is the plumbing one: from the counter, a refusal nobody explained is the
    // same event as a failure the runtime redacted.
    const lastResort = locale.toLowerCase().startsWith('en') ? PLUMBING.en : PLUMBING.es;
    throw new ErploraError(
      e?.code ?? 'error',
      spoken ?? (e?.message?.trim() || lastResort),
      e?.permission,
      // hub#1094: absent stays absent. An empty array would read as «the runtime looked and found
      // no bad field», which is a different statement from «this refusal is not about fields».
      // The core's typed refusals (`invalid_field`, hub#1070/#1185) name ONE field in the singular:
      // it folds in here so there is a single reader for «which fields were refused».
      e?.fields?.length ? e.fields : e?.field ? [e.field] : undefined,
      retryAfterOf(e?.retry_after_secs),
    );
  }
  return env.data;
}

/** `retry_after_secs` of a refusal, only when it is a usable wait (a non-negative number). */
function retryAfterOf(value: unknown): number | undefined {
  return typeof value === 'number' && value >= 0 ? value : undefined;
}

/**
 * Compat de queries de lista: si `data` es una página `{rows:[…],total:number}`, devuelve solo
 * `rows`. Así una vista antigua que use `query()` sigue recibiendo el array aunque a su query se
 * le añada un bloque `list`. `queryPage()` NO pasa por aquí (necesita el total).
 */
function unwrapPage(data: unknown): unknown {
  if (
    data !== null &&
    typeof data === 'object' &&
    Array.isArray((data as { rows?: unknown }).rows) &&
    typeof (data as { total?: unknown }).total === 'number'
  ) {
    return (data as { rows: unknown[] }).rows;
  }
  return data;
}

// ─────────────────────────────────────────────────────────────────────────────
// Transporte cloud: HTTP (RPC) + WebSocket (solo push de eventos).
// HTTP para query/command (si cae el socket, las ventas siguen yendo por HTTP);
// WS solo para recibir eventos de dominio. ARQUITECTURA.md §7.6.
// ─────────────────────────────────────────────────────────────────────────────

/** Reconnect wait when the socket drops (the cadence the channel has always had). */
const PUSH_RETRY_MIN_MS = 1_000;
/** Ceiling for the wait while there is no credential to present (a logged-out till). */
const PUSH_RETRY_MAX_MS = 30_000;

/**
 * A short, safe label for an unknown error, for {@link ErploraError} messages that must not leak the
 * raw text of a `SyntaxError`/`TypeError` (hub#782). It keeps the error's `name`/`message` when they
 * are harmless and degrades to a fixed phrase otherwise — never `undefined`.
 */
function safeErr(e: unknown): string {
  if (e instanceof Error && e.message) {
    // The exact byte sequence of the proxy's HTML would otherwise reach the cashier. Truncate hard.
    const m = e.message.trim();
    return m.length > 120 ? `${m.slice(0, 120)}…` : m;
  }
  return 'network error';
}

/** Control frame of the event channel: the hub accepted the credential (hub#504). */
export const STREAM_READY = 'stream.ready';
/** Control frame of the event channel: the hub refused it, with a stable code. */
export const STREAM_ERROR = 'stream.error';

export interface HttpWsOptions {
  /** Base URL del server del hub (p.ej. "" para mismo origen, o "http://localhost:8787"). */
  baseUrl?: string;
  /**
   * Canal push servidor→cliente (hub#19). `'ws'` (por defecto) = WebSocket `/ws`; `'sse'` =
   * Server-Sent Events `/api/events` (reconexión automática del navegador + keep-alive gratis).
   * La interfaz `ErploraTransport` no cambia: los módulos no se enteran del canal usado.
   */
  push?: 'ws' | 'sse';
  /** URL del WebSocket de eventos. Por defecto deriva de baseUrl. */
  wsUrl?: string;
  /** URL del endpoint SSE de eventos. Por defecto deriva de baseUrl (`…/api/events`). */
  sseUrl?: string;
  /** Cabeceras de auth (X-Hub-Id, Authorization, …) calculadas por el shell. */
  headers?: () => Record<string, string>;
  /** Inyectable para tests (por defecto el fetch global). */
  fetchImpl?: typeof fetch;
  /** Inyectable para tests (por defecto el WebSocket global). */
  WebSocketImpl?: typeof WebSocket;
  /** Inyectable para tests (por defecto el EventSource global). */
  EventSourceImpl?: typeof EventSource;
  /**
   * **Credential for the event channel** (hub#504). The hub does not push a single event to a
   * connection that has not presented an API key of that hub with read access.
   *
   * Called on **every** (re)connect, never cached: the shell answers with a single-use ticket
   * (`POST /api/events/ticket`), and a replayed ticket is not a credential. Returning `null` —
   * nobody is logged in yet, the hub is unreachable — closes the socket rather than leaving it
   * open and mute; the reconnect loop tries again.
   *
   * Without it the transport connects anonymously, which the hub refuses. That is deliberate: a
   * shell that forgets to configure this goes visibly deaf instead of quietly reading everything.
   */
  streamCredential?: () => Promise<string | null>;
  /**
   * Told when the hub refuses the channel (`unauthenticated`, `events.read_required`). Without a
   * hook this is exactly the failure nobody notices: the dashboard simply stops refreshing.
   */
  onStreamRefused?: (code: string, message: string) => void;
  /**
   * **The approval dialog** (hub#363). Called when a command comes back
   * {@link REQUIRES_ELEVATION} — a refusal a manager could approve — and only then.
   *
   * It lives HERE, once, and not in every screen. A module that forgot to handle the code would
   * leave the cashier staring at a raw error instead of a dialog, and there would be no way to
   * tell which of the 24 modules forgot: the failure is silent by construction. Same shape as the
   * receipt of hub#362 — the seam every action already crosses is the only place a contract
   * cannot be lost by omission.
   *
   * Without it, `requires_elevation` propagates to the caller exactly as it did before this
   * feature existed: a headless host never hangs on a dialog it does not have.
   */
  elevationApprover?: ElevationApprover;
}

export class HttpWsTransport implements ErploraTransport {
  private readonly baseUrl: string;
  private readonly push: 'ws' | 'sse';
  private readonly wsUrl: string;
  private readonly sseUrl: string;
  private readonly headers: () => Record<string, string>;
  private readonly fetchImpl: typeof fetch;
  private readonly WebSocketImpl?: typeof WebSocket;
  private readonly EventSourceImpl?: typeof EventSource;
  private readonly streamCredential?: () => Promise<string | null>;
  private pushRetryMs = PUSH_RETRY_MIN_MS;
  private readonly onStreamRefused?: (code: string, message: string) => void;
  private readonly elevationApprover?: ElevationApprover;
  /**
   * The approval flows in progress, keyed by the ACTION (hub#363).
   *
   * A cashier double-taps «void» and two identical commands are refused. Without this the manager
   * is asked twice for the same thing, taps twice, and the second approval is either spent on a
   * duplicate void or left minted — a spendable credential lying around for the rest of the
   * window. Both callers join one dialog and receive the one result instead.
   *
   * Keyed on `command` + a plain `JSON.stringify` of the payload, which is NOT the runtime's
   * canonical fingerprint and does not need to be: a key that misses (the same payload written in
   * another key order) merely costs a second dialog, while a key that over-matched would collapse
   * two different actions into one. It errs the safe way on purpose.
   */
  private readonly elevating = new Map<string, Promise<unknown>>();

  private ws?: WebSocket;
  private es?: EventSource;
  private readonly listeners = new Map<string, Set<(p: unknown, meta: EventMeta) => void>>();
  private pushStarted = false;

  constructor(opts: HttpWsOptions = {}) {
    this.baseUrl = opts.baseUrl ?? '';
    this.push = opts.push ?? 'ws';
    this.wsUrl = opts.wsUrl ?? deriveWsUrl(this.baseUrl);
    this.sseUrl = opts.sseUrl ?? deriveSseUrl(this.baseUrl);
    this.headers = opts.headers ?? (() => ({}));
    this.fetchImpl = opts.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.WebSocketImpl = opts.WebSocketImpl ?? (globalThis as { WebSocket?: typeof WebSocket }).WebSocket;
    this.EventSourceImpl =
      opts.EventSourceImpl ?? (globalThis as { EventSource?: typeof EventSource }).EventSource;
    this.streamCredential = opts.streamCredential;
    this.onStreamRefused = opts.onStreamRefused;
    this.elevationApprover = opts.elevationApprover;
  }

  private async post(
    path: string,
    body: unknown,
    extraHeaders: Record<string, string> = {},
  ): Promise<unknown> {
    return this.send('POST', path, body, extraHeaders);
  }

  /**
   * **The hub's own REST surface** (hub#714) — `/api/hub/flows*` today. Same envelope discipline as
   * every other call, a different verb and a path the CALLER's surface built from a fixed table.
   *
   * This method takes a path and is therefore exactly the shape of a generic proxy, which is why it
   * is not reachable from module code: `ErploraClient` never exposes the transport, and the only
   * thing on the client that can call it is {@link FlowsApi}, whose method list is pinned by a test.
   */
  coreRequest(req: CoreRequest, extraHeaders: Record<string, string> = {}): Promise<unknown> {
    return this.send(req.method, req.path, req.body, extraHeaders, req.envelope === true);
  }

  /**
   * Bytes de media para módulos, autenticados por el shell sin revelarles la sesión.
   *
   * A diferencia de `coreRequest`, esta puerta no acepta verbo ni URL arbitrarios: una referencia
   * de blueprint sólo puede acabar en `GET /api/media/raw?path=…` del mismo Hub. El `Blob` permite
   * que el consumidor cree un object URL local; ninguna credencial termina en el DOM.
   */
  async fetchMediaBlob(ref: string, opts: MediaFetchOptions = {}): Promise<Blob | null> {
    const path = mediaPath(ref);
    if (!path) return null;
    try {
      const res = await this.fetchImpl(
        `${this.baseUrl}/api/media/raw?path=${encodeURIComponent(path)}`,
        // Nunca seguir un 30x: `fetch` puede reenviar cabeceras a otro origen y la sesión del Hub
        // no sale de este proceso ni aunque un proxy esté mal configurado.
        { method: 'GET', headers: this.headers(), signal: opts.signal, redirect: 'error' },
      );
      if (!res.ok) return null;
      const contentType = res.headers.get('content-type')?.toLowerCase() ?? '';
      if (!contentType.startsWith('image/')) return null;
      return await res.blob();
    } catch {
      return null;
    }
  }

  /**
   * **Bytes from the hub's own REST surface** (hub#2114) — the `GET` twin of {@link coreRequest}
   * for the one kind of door that answers a FILE instead of an envelope: a WhatsApp attachment the
   * runtime streams from the SaaS. Same seal as `coreRequest`: module code cannot reach it — only
   * {@link WhatsappMediaApi} calls it, with a path it built from a fixed prefix.
   *
   * A `2xx` is the file, handed back as a `Blob` so the module makes a local object URL and no
   * credential ever lands in the DOM. A refusal is still the runtime's envelope and is read like
   * every other one (`unwrap`), so the module gets the SaaS's own `code` (`media_not_found`,
   * `media_unavailable`…). Anything that is neither — the proxy's HTML page, a dead network — is
   * {@link SERVER_UNAVAILABLE}, with none of its text.
   */
  async coreBlobRequest(path: string, extraHeaders: Record<string, string> = {}): Promise<Blob> {
    let res: Response;
    try {
      res = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: 'GET',
        headers: { ...this.headers(), ...extraHeaders },
        // Never follow a 30x: `fetch` could carry the hub session to another origin.
        redirect: 'error',
      });
    } catch {
      // A fixed phrase: the browser's own message is nothing the cashier can act on.
      throw new ErploraError(SERVER_UNAVAILABLE, `request to ${path} failed`);
    }
    if (res.status >= 200 && res.status < 300) return await res.blob();
    const ct = res.headers?.get?.('content-type');
    if (!ct || !ct.toLowerCase().includes('application/json')) {
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        `unexpected response from ${path}: HTTP ${res.status}`,
      );
    }
    let env: Envelope;
    try {
      env = (await res.json()) as Envelope;
    } catch {
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        `request to ${path} returned an invalid JSON body`,
      );
    }
    // A refusal throws here with its own code; an `ok` envelope on a non-2xx status is nothing
    // the runtime writes, so it is not taken for a file.
    if (!env.ok) unwrap(env, res.status);
    throw new ErploraError(SERVER_UNAVAILABLE, `unexpected response from ${path}: HTTP ${res.status}`);
  }

  private async send(
    method: string,
    path: string,
    body: unknown,
    extraHeaders: Record<string, string> = {},
    envelope = false,
  ): Promise<unknown> {
    // hub#782: the proxy's `5xx text/html` page (the hub container died — OOM exit 137 / hub#759;
    // any deploy window) used to reach `res.json()` and blow up as a raw `SyntaxError`, which is
    // NOT an `ErploraError`, carries no `code`, and so no module can orient by it. The runtime
    // ALWAYS answers `application/json` — even its 4xx domain refusal travels in an envelope with a
    // `code` — so JSON is the signature of «the hub answered», and anything else is the proxy (or
    // the network). That is why we key on the CONTENT-TYPE and not on `res.ok`: a 403 envelope with
    // `permission_denied` is a domain refusal with its own code, not a transport failure.
    let res: Response;
    // A `GET`/`DELETE` carries no body and must not announce one: some proxies reject the pair.
    // A form (hub#2232) goes as it is and WITHOUT a `Content-Type` of ours: `fetch` writes the
    // multipart one with its boundary, and any value set here would drop it.
    const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
    const framing: Record<string, string> =
      body === undefined || isForm ? {} : { 'Content-Type': 'application/json' };
    try {
      res = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method,
        headers: { ...framing, ...this.headers(), ...extraHeaders },
        ...(body === undefined
          ? {}
          : { body: isForm ? (body as FormData) : JSON.stringify(body) }),
      });
    } catch (e) {
      // A network-level failure (DNS, CORS, abort, `TypeError: Failed to fetch`): same meaning for
      // the caller — «the hub did not answer» — collapsed to one code. The raw message is dropped so
      // nothing of the browser's internals reaches the cashier.
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        `request to ${path} failed: ${safeErr(e)}`,
      );
    }
    // hub#1682: a `204 No Content` is a SUCCESS with nothing to say — no body, and no
    // `content-type` either. It reaches here because the runtime hands the SaaS's answer back
    // untouched (`cloud_body_passthrough`) and the SaaS answers a delete that way. Without this,
    // the empty body fell through to `res.json()`, blew up, and was reported as
    // `server_unavailable: invalid JSON body` — the caller was told the hub had not answered
    // while the template had already been dropped from Meta. There is nothing to unwrap: 204
    // means «done», by definition of the status and not by convention of any one route.
    if (res.status === 204) return undefined;
    const ct = res.headers?.get?.('content-type');
    // hub#782: the runtime ALWAYS answers `application/json`, even on a 4xx domain refusal. The
    // proxy answers `text/html`. So a content-type that is PRESENT and is NOT JSON is the signature
    // of the proxy — we refuse it. We do NOT require the header: a fetch mock (and some minimal
    // HTTP/1.0 responders) omit it, and an envelope that parses is still a valid runtime answer.
    if (ct !== null && ct !== undefined && !ct.toLowerCase().includes('application/json')) {
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        `unexpected response from ${path}: HTTP ${res.status} ${ct}`,
      );
    }
    let env: Envelope;
    try {
      env = (await res.json()) as Envelope;
    } catch {
      // Defense in depth: a proxy can label an HTML page `application/json`, and the JSON parser's
      // own message echoes that HTML back («Unexpected token '<', "<!DOCTYPE "…»). A fixed phrase
      // keeps the proxy's internals out of the message the cashier reads.
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        `request to ${path} returned an invalid JSON body`,
      );
    }
    const data = unwrap(env, res.status);
    return envelope ? env : data;
  }

  /**
   * A **query is never elevated** — and that is the runtime's rule, mirrored here rather than
   * invented: `permissions::check_command` is the command gate and only that, because an approval
   * exists to attribute an ACTION to the manager who allowed it, and a PIN that unlocked a report
   * would leave no such trace. So this path has no capture at all.
   */
  query(name: string, params: Record<string, unknown> = {}): Promise<unknown> {
    return this.post('/api/query', { name, params });
  }

  command(name: string, payload: Record<string, unknown> = {}): Promise<unknown> {
    if (!this.elevationApprover) return this.sendCommand(name, payload);
    return this.sendCommand(name, payload).catch((e: unknown) => {
      // ONE guard, on the code the dispatcher answers only for a refusal a manager could approve.
      // A flat `permission_denied` — what an API key gets (hub#361), and what any other missing
      // permission gets — is not an offer to elevate and must never open a dialog: nobody is
      // standing at an integration to type four digits.
      if (!(e instanceof ErploraError) || e.code !== REQUIRES_ELEVATION) throw e;
      return this.elevate(name, payload, e);
    });
  }

  /** One POST to `/api/command`, with an approval attached if there is one. Never retried. */
  private sendCommand(
    name: string,
    payload: Record<string, unknown>,
    token?: string,
  ): Promise<unknown> {
    return this.post(
      '/api/command',
      { name, payload },
      token ? { [ELEVATION_TOKEN_HEADER]: token } : {},
    );
  }

  /**
   * Ask the shell for an approval and spend it — **once**.
   *
   * The runtime spends the grant at the gate, BEFORE the command runs, so after the elevated
   * attempt leaves this process the approval is gone whatever happens next. That rules out every
   * kind of resend: an answer that never arrived may well be an action that already happened, and
   * sending it again would either duplicate it or tell the cashier to fetch the manager for
   * something that is already done. So the elevated attempt goes through {@link sendCommand},
   * which does not re-enter this capture — a second `requires_elevation` (a token that expired
   * between the tap and the send) is reported, not turned into another dialog.
   */
  private elevate(
    name: string,
    payload: Record<string, unknown>,
    refusal: ErploraError,
  ): Promise<unknown> {
    const key = `${name} ${JSON.stringify(payload)}`;
    const joined = this.elevating.get(key);
    if (joined) return joined;
    const flow = (async () => {
      const ask: ElevationAsk = {
        command: name,
        payload,
        permission: refusal.permission ?? '',
        approve: (approver, pin) =>
          this.approveElevation(name, payload, { approver, pin }),
        approveWithBadge: (badge) => this.approveElevation(name, payload, { badge }),
      };
      const token = await this.elevationApprover!(ask);
      // Nobody approved: hand back the refusal the caller already had, untouched. A module written
      // before hub#363 keeps behaving exactly as it did.
      if (!token) throw refusal;
      return this.sendCommand(name, payload, token);
    })();
    // Single-flight, not a cache: the entry goes the moment the flow settles, so a cashier who
    // cancels and taps again gets a new dialog rather than the stale refusal of the one they shut.
    this.elevating.set(key, flow);
    void flow.catch(() => {}).then(() => this.elevating.delete(key));
    return flow;
  }

  /**
   * `POST /api/elevation/approve` — the credential is verified by the runtime, never here
   * (hub#361, and hub#658 for the badge half).
   */
  private approveElevation(
    command: string,
    payload: Record<string, unknown>,
    credential: { approver: string; pin: string } | { badge: string },
  ): Promise<ElevationApproval> {
    return this.post(ELEVATION_APPROVE_PATH, { ...credential, command, payload }).then((data) => {
      const d = (data ?? {}) as Record<string, unknown>;
      return {
        token: String(d.token ?? ''),
        permission: String(d.permission ?? ''),
        approvedBy: String(d.approved_by ?? ''),
        approverName: String(d.approver_name ?? ''),
        expiresInSeconds: Number(d.expires_in_seconds ?? 0),
      };
    });
  }

  subscribe(event: string, cb: (payload: unknown) => void): () => void {
    return this.subscribeWithMeta(event, (payload) => cb(payload));
  }

  subscribeWithMeta(event: string, cb: (payload: unknown, meta: EventMeta) => void): () => void {
    let set = this.listeners.get(event);
    if (!set) {
      set = new Set();
      this.listeners.set(event, set);
    }
    set.add(cb);
    this.ensurePush();
    return () => {
      set!.delete(cb);
      if (set!.size === 0) this.listeners.delete(event);
    };
  }

  /** Reparte un frame del wire (texto JSON) a los suscriptores. Común a WS y SSE. */
  private handleFrame(raw: unknown): void {
    let msg: { event?: string; name?: string; type?: string; payload?: unknown; client_instance?: unknown };
    try {
      msg = JSON.parse(typeof raw === 'string' ? raw : '');
    } catch {
      return;
    }
    // Formas reales del frame en el wire del runtime (crates/server/src/state.rs):
    //   - eventos de dominio (outbox→broadcast): {"name":"sale.completed","payload":{…}}
    //   - flujo de instalación:                  {"type":"module.installed","module_id":"…"}
    // Se acepta también {"event":…} por compat. Sin `payload`, se entrega el frame entero
    // (p.ej. module.installed lleva module_id en la raíz).
    const name = msg.event ?? msg.name ?? msg.type;
    if (!name) return;
    // hub#504: control frames of the channel itself. They are protocol, not business, so they are
    // never delivered as domain events — and a refusal is REPORTED, because a channel that goes
    // quiet without saying why is the failure nobody debugs.
    if (name === STREAM_READY) return;
    if (name === STREAM_ERROR) {
      const frame = msg as { code?: string; message?: string };
      this.onStreamRefused?.(frame.code ?? 'unknown', frame.message ?? '');
      return;
    }
    const set = this.listeners.get(name);
    if (!set) return;
    // hub#1980: the tab that caused it, as the hub stamped it next to `module`. Only a string counts.
    const meta: EventMeta = typeof msg.client_instance === 'string' ? { clientInstance: msg.client_instance } : {};
    for (const cb of set) cb(msg.payload ?? msg, meta);
  }

  /** Abre el canal push (lazy) la primera vez que alguien se suscribe, según `push`. */
  private ensurePush(): void {
    if (this.pushStarted) return;
    if (this.push === 'sse') this.ensureSse();
    else this.ensureWs();
  }

  private ensureWs(): void {
    if (!this.WebSocketImpl) return;
    this.pushStarted = true;
    const socket = new this.WebSocketImpl(this.wsUrl);
    this.ws = socket;
    socket.onmessage = (ev: MessageEvent) => this.handleFrame(ev.data);
    // hub#504: the credential goes in the FIRST FRAME, never in the URL — the query string ends up
    // in every access log and proxy trace on the way. Asked for on each open, because a ticket is
    // single use.
    socket.onopen = () => {
      if (!this.streamCredential) return;
      void this.streamCredential()
        .catch(() => null)
        .then((token) => {
          if (token) {
            socket.send(JSON.stringify({ type: 'auth', token }));
            this.pushRetryMs = PUSH_RETRY_MIN_MS;
            return;
          }
          // No credential (nobody logged in yet, hub unreachable): close rather than hold a socket
          // the hub will never speak on, and **back off**. The shell wires its listeners at boot,
          // so "no session yet" is the ordinary state of the login screen — retrying every second
          // there would be a request a second for as long as the till sits idle.
          this.pushRetryMs = Math.min(this.pushRetryMs * 2, PUSH_RETRY_MAX_MS);
          socket.close();
        });
    };
    socket.onclose = () => {
      this.pushStarted = false;
      this.ws = undefined;
      // Reabre si aún hay suscriptores (degradación elegante: query/command siguen por HTTP).
      if (this.listeners.size > 0) setTimeout(() => this.ensurePush(), this.pushRetryMs);
    };
  }

  /** SSE: el navegador reconecta solo (con `Last-Event-ID`), no necesitamos reabrir a mano. */
  private ensureSse(): void {
    if (!this.EventSourceImpl) return;
    this.pushStarted = true;
    // SSE has no first frame and `EventSource` sets no headers, so the ticket travels in the
    // query — which is only acceptable because it is single use and dies in a minute.
    if (!this.streamCredential) {
      this.openSse(this.sseUrl);
      return;
    }
    void this.streamCredential()
      .catch(() => null)
      .then((ticket) => {
        if (!ticket) {
          this.pushStarted = false;
          return;
        }
        const sep = this.sseUrl.includes('?') ? '&' : '?';
        this.openSse(`${this.sseUrl}${sep}ticket=${encodeURIComponent(ticket)}`);
      });
  }

  private openSse(url: string): void {
    if (!this.EventSourceImpl) return;
    this.es = new this.EventSourceImpl(url);
    this.es.onmessage = (ev: MessageEvent) => this.handleFrame(ev.data);
  }

  /** Cierra el canal push (p.ej. al desmontar el shell). */
  close(): void {
    this.ws?.close();
    this.es?.close();
  }
}

function deriveSseUrl(baseUrl: string): string {
  if (!baseUrl) {
    const loc = (globalThis as { location?: Location }).location;
    return loc ? `${loc.protocol}//${loc.host}/api/events` : 'http://localhost:8787/api/events';
  }
  return baseUrl.replace(/\/$/, '') + '/api/events';
}

function deriveWsUrl(baseUrl: string): string {
  if (!baseUrl) {
    // Mismo origen: ws(s)://host/ws.
    const loc = (globalThis as { location?: Location }).location;
    if (loc) {
      const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${proto}//${loc.host}/ws`;
    }
    return 'ws://localhost:8787/ws';
  }
  return baseUrl.replace(/^http/, 'ws') + '/ws';
}

// ─────────────────────────────────────────────────────────────────────────────
// Bridge nativo de Tauri (`invoke` + `listen`). ADR-0050: NO se usa para DATOS (eso va por
// HttpWsTransport, mismo origen). Queda para lo genuinamente nativo sin equivalente HTTP — hoy el
// HARDWARE (`IpcBridgeTransport`, más abajo: la app instalada ES el acceso al hardware, §2.7) y
// caprichos nativos (keychain, device_id). El transporte de datos `IpcTransport` se ELIMINÓ.
// ─────────────────────────────────────────────────────────────────────────────

/** Subconjunto de la API de Tauri que necesita el bridge nativo (inyectable para tests). */
export interface TauriBridge {
  invoke(cmd: string, args: Record<string, unknown>): Promise<unknown>;
  listen(event: string, cb: (e: { payload: unknown }) => void): Promise<() => void>;
}

// ─────────────────────────────────────────────────────────────────────────────
// The automation kernel, as a MODULE may reach it (hub#714, ADR-0283 §9).
//
// The visual flow editor is a module (pm#110) and had no declared way in: `query`/`command` speak
// to the dispatcher, and flows are core REST on purpose — the ADR froze that and «commands
// `hub.flows.*`» is exactly the surface it froze shut. What a module COULD do was read the session
// token out of `localStorage` and `fetch('/api/hub/flows')` itself: same document as the shell,
// same origin, no sandbox. It would work — while the user is an admin — and it would break the day
// the shell moves the session into an httpOnly cookie. A contract that leans on that is not one.
//
// So the way in is explicit, typed and module-scoped. What it is NOT is a proxy: there is no
// method that takes a path, every path is built here from the frozen §9 table, and every id is
// checked before it can be pasted into one. `flows.test.ts` pins both — the method list and the
// URLs — so an escape hatch cannot be added quietly.
//
// The gate stays in Rust and does not move: `require_admin_session` first (a cashier still gets
// 403, an API key is still refused), and then the `manage_flows` capability of the calling module.
// ─────────────────────────────────────────────────────────────────────────────

/** Where the kernel's REST surface lives. **Every** path this surface can build starts here. */
export const FLOWS_BASE_PATH = '/api/hub/flows';

/** Where the photo, video or PDF a WhatsApp template step sends in its header goes up — the one
 *  path {@link FlowsApi.uploadWhatsappHeaderImage} and {@link FlowsApi.uploadWhatsappHeaderMedia}
 *  post to (`crates/server/src/flows_header_media.rs`, hub#2335 and hub#2347). */
export const FLOWS_WHATSAPP_HEADER_IMAGES_PATH = '/api/hub/flows/whatsapp-header-images';

/**
 * What {@link FlowsApi.uploadWhatsappHeaderImage} answers. `ref` is what the step stores in
 * `vars.header_image`; the hub signs a fresh link to it on every send. `mime_type` is decided by
 * the photo's BYTES, never by its name.
 */
export interface WhatsappHeaderImage {
  ref: string;
  mime_type: 'image/jpeg' | 'image/png';
  size: number;
}

/** The header a file is uploaded for: the media kinds of a WhatsApp template header (hub#2347). */
export type WhatsappHeaderMediaKind = 'image' | 'video' | 'document';

/**
 * What {@link FlowsApi.uploadWhatsappHeaderMedia} answers. `ref` is what the step stores in
 * `vars.header_image`, `vars.header_video` or `vars.header_document`; the hub signs a fresh link to
 * it on every send, and only for the header of its own kind. `mime_type` is decided by the file's
 * BYTES, never by its name.
 */
export interface WhatsappHeaderMedia {
  ref: string;
  mime_type: 'image/jpeg' | 'image/png' | 'video/mp4' | 'application/pdf';
  size: number;
}

/** Where the hub's event catalogue lives. Every path {@link EventsApi} can build starts here. */
export const EVENTS_BASE_PATH = '/api/hub/events';

/**
 * `_event_outbox.failure_kind` for the one dead-letter a retry can never fix (hub#827): the owner
 * withdrew the flow's authorisation while the message was still queued, so the recipient is no
 * longer in the row. It arrives as `failure_kind` on a {@link DeadEvent} and as the `code` of the
 * `409` {@link EventsApi.retry} refuses with — the same word in both places, so a screen can say
 * what WOULD help (grant the permission again and run the flow) instead of drawing a dead end.
 *
 * Exported so a module matches the runtime's constant instead of retyping the string.
 */
export const RELEASE_REVOKED = 'flow.release_revoked';

/** How a call names the module it acts for. Read by `crates/server/src/flows_api.rs`, nowhere else. */
export const MODULE_HEADER = 'X-Erplora-Module';

/** Asking for a module-scoped surface through a client that is not scoped to any module. */
export const MODULE_SCOPE_REQUIRED = 'module_scope_required';

/** A value this SDK refuses to put in a URL. It never becomes a request. */
export const INVALID_ARGUMENT = 'invalid_argument';

/** Verbs the kernel's REST surface answers. There is no `PATCH` and no `HEAD`: §9 has neither. */
export type CoreMethod = 'GET' | 'POST' | 'PUT' | 'DELETE';

/** One call to the hub's own REST surface. `path` is always built by the surface, never received. */
export interface CoreRequest {
  method: CoreMethod;
  path: string;
  body?: unknown;
  /**
   * Hand back the whole `ok` envelope instead of its `data` (hub#2123): for a route whose answer
   * carries a sibling of `data` — `discarded` on `GET /flows/templates`. A refusal throws the same.
   */
  envelope?: boolean;
}

/** A transport that can reach the core's REST surface (as opposed to the dispatcher). */
export interface CoreApiTransport {
  coreRequest(req: CoreRequest, headers?: Record<string, string>): Promise<unknown>;
}

/**
 * An id that may be pasted into a path segment. Flow, run and approval ids are UUIDv4 in the
 * runtime (`registry::new_id`), so this is generous — and it is not the point.
 *
 * The point is that `fetch` NORMALISES a URL: `/api/hub/flows/../../settings` leaves the process as
 * `/api/settings`. An id concatenated into a path is therefore the generic proxy arriving by the
 * back door, whatever the surface's method list says. Hence: no `/`, no `.`, no `%`, no `?`, no
 * `#`, and a length cap.
 */
const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;

/**
 * A secret name, as `flows/secrets.rs` defines it: UPPER_SNAKE_CASE, starting with a letter, ≤ 64.
 * Checked here too because it also travels in a path — and because the name is read back as
 * `{{secret.NAME}}`, so one with a dot or a brace in it is a different thing entirely.
 */
const SECRET_NAME_PATTERN = /^[A-Z][A-Z0-9_]{0,63}$/;

/**
 * An event name: `sale.completed`, `hub.whatsapp.message_received`. Dots are allowed here and not
 * in {@link ID_PATTERN} because a name travels in a QUERY STRING, where `URLSearchParams` encodes
 * it — the reason it is still checked is that a surface which accepts anything is one
 * path-building change away from being the proxy this SDK refuses to be.
 */
const EVENT_NAME_PATTERN = /^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$/;

function checkedSegment(kind: string, value: string, pattern: RegExp): string {
  if (typeof value === 'string' && pattern.test(value)) return value;
  throw new ErploraError(
    INVALID_ARGUMENT,
    `\`${String(value)}\` is not a valid ${kind}: it would have to be pasted into a URL`,
  );
}

/** `?a=1&b=2`, or `''` when nothing was asked for (a bare `?` is noise the hub has to parse). */
function queryString(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : '';
}

/** A flow as the kernel stores it. `definition` travels as JSON, never as an escaped string. */
export interface Flow {
  id: string;
  name: string;
  enabled: boolean;
  definition: Record<string, unknown>;
  created_by?: string;
  updated_by?: string;
  [k: string]: unknown;
}

/** What `POST`/`PUT /api/hub/flows[/{id}]` accept. `enabled` defaults to true in the runtime. */
export interface FlowInput {
  name: string;
  definition: Record<string, unknown>;
  enabled?: boolean;
}

/**
 * What `GET /api/hub/flows/schema` answers (hub#716): the JSON Schema the hub judges a flow
 * document with, and which core is doing the judging.
 */
export interface FlowSchema {
  /** The document version this core enforces (`1` today). A flow declaring another is refused. */
  schema_version: number;
  /** The hub's own version, e.g. `1.2.3` — the reason this is asked instead of bundled. */
  core_version: string;
  /** The JSON Schema itself, verbatim from `schemas/flow.schema.json` as that core ships it. */
  schema: Record<string, unknown>;
}

/** One page of run history. `next_cursor` comes only when the page was FULL (`§9`). */
export interface RunPage<T = unknown> {
  data: T[];
  next_cursor?: string;
}

/**
 * **The frozen §9 flows contract, and nothing else.** One method per route, no method that takes a
 * path, no method that takes a URL. Adding one turns `flows.test.ts` red on purpose.
 */
export class FlowsApi {
  constructor(
    private readonly send: (req: CoreRequest) => Promise<unknown>,
    /**
     * The id of the module this surface belongs to (hub#1677). It is the `{module}` segment of the
     * template routes, and it comes from `forModule(<id>)` rather than from an argument on purpose:
     * ADR-0470 §1 says a module turns on **its own** recipes, and a parameter would be an invitation
     * to name somebody else's — which the hub refuses with `403 flow.template_not_yours`, but only
     * after the call has been written.
     */
    private readonly moduleId: string = '',
  ) {}

  /** `GET /api/hub/flows` */
  async list(): Promise<Flow[]> {
    return this.send({ method: 'GET', path: FLOWS_BASE_PATH }) as Promise<Flow[]>;
  }

  /** `POST /api/hub/flows` */
  async create(flow: FlowInput): Promise<Flow> {
    return this.send({ method: 'POST', path: FLOWS_BASE_PATH, body: flow }) as Promise<Flow>;
  }

  /** `GET /api/hub/flows/{id}` */
  async get(id: string): Promise<Flow> {
    const flow = checkedSegment('flow id', id, ID_PATTERN);
    return this.send({ method: 'GET', path: `${FLOWS_BASE_PATH}/${flow}` }) as Promise<Flow>;
  }

  /** `PUT /api/hub/flows/{id}` — revalidates the document and re-seeds the triggers. */
  async update(id: string, flow: FlowInput): Promise<Flow> {
    const target = checkedSegment('flow id', id, ID_PATTERN);
    return this.send({
      method: 'PUT',
      path: `${FLOWS_BASE_PATH}/${target}`,
      body: flow,
    }) as Promise<Flow>;
  }

  /** `DELETE /api/hub/flows/{id}` — soft-delete: the row survives as the record it existed. */
  async remove(id: string): Promise<unknown> {
    const flow = checkedSegment('flow id', id, ID_PATTERN);
    return this.send({ method: 'DELETE', path: `${FLOWS_BASE_PATH}/${flow}` });
  }

  /** `GET /api/hub/flows/{id}/grants` — what this flow is allowed to do unattended. */
  async grants(id: string): Promise<unknown[]> {
    const flow = checkedSegment('flow id', id, ID_PATTERN);
    return this.send({
      method: 'GET',
      path: `${FLOWS_BASE_PATH}/${flow}/grants`,
    }) as Promise<unknown[]>;
  }

  /** `PUT /api/hub/flows/{id}/grants` — a COMPLETE replace; `granted_by` comes from the session. */
  async replaceGrants(id: string, grants: unknown[]): Promise<unknown[]> {
    const flow = checkedSegment('flow id', id, ID_PATTERN);
    return this.send({
      method: 'PUT',
      path: `${FLOWS_BASE_PATH}/${flow}/grants`,
      body: { grants },
    }) as Promise<unknown[]>;
  }

  /** `POST /api/hub/flows/{id}/run` — the manual trigger. */
  async run(id: string, input?: Record<string, unknown>): Promise<unknown> {
    const flow = checkedSegment('flow id', id, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${FLOWS_BASE_PATH}/${flow}/run`,
      ...(input === undefined ? {} : { body: input }),
    });
  }

  /** `GET /api/hub/flows/{id}/runs` — history, paged by CURSOR (a short page IS the end). */
  async runs(id: string, page: { limit?: number; before?: string } = {}): Promise<RunPage> {
    const flow = checkedSegment('flow id', id, ID_PATTERN);
    const search = queryString({ limit: page.limit, before: page.before });
    return this.send({
      method: 'GET',
      path: `${FLOWS_BASE_PATH}/${flow}/runs${search}`,
    }) as Promise<RunPage>;
  }

  /** `GET /api/hub/flows/runs/{run_id}` — the run with its steps and the events it emitted. */
  async getRun(runId: string): Promise<unknown> {
    const run = checkedSegment('run id', runId, ID_PATTERN);
    return this.send({ method: 'GET', path: `${FLOWS_BASE_PATH}/runs/${run}` });
  }

  /** `GET /api/hub/flows/approvals[?status=]` — the tray. `status` is an enum in the kernel
   *  (`pending`/`approved`/`rejected`), so it is checked like a segment even though it travels as a
   *  query param that `URLSearchParams` already encodes: nothing on this surface is free text. */
  async approvals(status?: string): Promise<unknown[]> {
    const filter = status === undefined ? '' : checkedSegment('status', status, ID_PATTERN);
    return this.send({
      method: 'GET',
      path: `${FLOWS_BASE_PATH}/approvals${queryString({ status: filter })}`,
    }) as Promise<unknown[]>;
  }

  /** `POST /api/hub/flows/approvals/{id}/approve` — `decided_by` is the session, never the body. */
  async approve(approvalId: string, body?: Record<string, unknown>): Promise<unknown> {
    const approval = checkedSegment('approval id', approvalId, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${FLOWS_BASE_PATH}/approvals/${approval}/approve`,
      ...(body === undefined ? {} : { body }),
    });
  }

  /** `POST /api/hub/flows/approvals/{id}/reject` */
  async reject(approvalId: string, body?: Record<string, unknown>): Promise<unknown> {
    const approval = checkedSegment('approval id', approvalId, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${FLOWS_BASE_PATH}/approvals/${approval}/reject`,
      ...(body === undefined ? {} : { body }),
    });
  }

  /** `GET /api/hub/flows/secrets` — the NAMES. There is no endpoint that returns a value, and
   *  that absence is the design (ADR-0283 §4). */
  async secrets(): Promise<unknown> {
    return this.send({ method: 'GET', path: `${FLOWS_BASE_PATH}/secrets` });
  }

  /** `PUT /api/hub/flows/secrets/{name}` — write-only. */
  async putSecret(name: string, value: string): Promise<unknown> {
    const secret = checkedSegment('secret name', name, SECRET_NAME_PATTERN);
    return this.send({
      method: 'PUT',
      path: `${FLOWS_BASE_PATH}/secrets/${secret}`,
      body: { value },
    });
  }

  /** `DELETE /api/hub/flows/secrets/{name}` */
  async deleteSecret(name: string): Promise<unknown> {
    const secret = checkedSegment('secret name', name, SECRET_NAME_PATTERN);
    return this.send({ method: 'DELETE', path: `${FLOWS_BASE_PATH}/secrets/${secret}` });
  }

  /**
   * `GET /api/hub/flows/schema` — **the flow contract THIS hub enforces** (hub#716).
   *
   * Ask it once, when the editor opens, and build the palette from the answer. The alternative —
   * bundling `flow.schema.json` — is a photo of whichever core the module was built against, and
   * a module updates on its own clock (hub#516): ahead of its hub it offers a step the hub
   * refuses to save, behind it it hides one that works. `core_version` is there so the editor can
   * say which of the two is happening instead of showing a validation error nobody can act on.
   */
  async schema(): Promise<FlowSchema> {
    return this.send({ method: 'GET', path: `${FLOWS_BASE_PATH}/schema` }) as Promise<FlowSchema>;
  }

  /**
   * `POST /api/hub/flows/whatsapp-header-images` — **the photo a WhatsApp template step sends in
   * its header** (hub#2335).
   *
   * A template approved with a photo header sends a photo on every message, and Meta downloads it
   * from a link; the owner has the file, not a public link. The hub keeps it in its own files and
   * answers a `ref` for the step's `vars.header_image`; every send signs a fresh link to it, so the
   * file never has to be public and the link never expires in the queue. The same photo twice is
   * the same `ref`.
   *
   * Only a JPEG or a PNG of up to 5 MB (Meta's cap), told by its bytes. A refusal arrives as an
   * {@link ErploraError} with its code: `whatsapp.header_image_unsupported`,
   * `whatsapp.header_image_too_large`, `whatsapp.header_image_missing`,
   * `whatsapp.invalid_header_image_upload`, `whatsapp.header_image_not_saved`.
   *
   * A hub older than this route leaves the method **absent** rather than broken, like
   * {@link templates}: `typeof flows.uploadWhatsappHeaderImage` is the probe.
   */
  async uploadWhatsappHeaderImage(file: Blob): Promise<WhatsappHeaderImage> {
    const form = new FormData();
    form.append('file', file);
    return this.send({
      method: 'POST',
      path: FLOWS_WHATSAPP_HEADER_IMAGES_PATH,
      body: form,
    }) as Promise<WhatsappHeaderImage>;
  }

  /**
   * `POST /api/hub/flows/whatsapp-header-images` with a `kind` — **the photo, the VIDEO or the PDF
   * a WhatsApp template step sends in its header** (hub#2347).
   *
   * The same door as {@link uploadWhatsappHeaderImage}, for the header the approved template
   * has: `image` (a JPEG or a PNG of up to 5 MB), `video` (an MP4 of up to 16 MB) or `document` (a
   * PDF of up to 100 MB) — Meta's caps, the file told by its bytes and refused when it is not the
   * kind asked for. The answer's `ref` goes in `vars.header_<kind>`.
   *
   * A refusal arrives as an {@link ErploraError} with the code of the kind asked for:
   * `whatsapp.header_<kind>_unsupported`, `whatsapp.header_<kind>_too_large`,
   * `whatsapp.header_<kind>_missing`, `whatsapp.header_<kind>_not_saved`, and
   * `whatsapp.header_media_kind_unknown` or `whatsapp.invalid_header_image_upload`.
   *
   * A hub older than hub#2347 leaves the method **absent** (its door takes photos only):
   * `typeof flows.uploadWhatsappHeaderMedia` is the probe.
   */
  async uploadWhatsappHeaderMedia(
    file: Blob,
    kind: WhatsappHeaderMediaKind,
  ): Promise<WhatsappHeaderMedia> {
    const form = new FormData();
    // The kind first: the runtime refuses a file of another kind before reading the rest of it.
    form.append('kind', kind);
    form.append('file', file);
    return this.send({
      method: 'POST',
      path: FLOWS_WHATSAPP_HEADER_IMAGES_PATH,
      body: form,
    }) as Promise<WhatsappHeaderMedia>;
  }

  /**
   * `GET /api/hub/flows/templates` — **the automations the installed modules ship** (hub#1611).
   *
   * The gallery used to offer only the templates written inside the `flows` module itself, so a
   * business that installed the WhatsApp module could not find the automation that module brings
   * with it: it had to be built by hand, step by step. The modules already publish them — the
   * `flows/` folder travels in the zip since `module-toolkit#209` — and the runtime registers them
   * on install; this is what puts them on the screen.
   *
   * Merge them with the module's own: `module` says where each one comes from, and `requires` is
   * the **per-template** version floor, deliberately not the module's `depends_on` (a template is
   * optional and its module works without it).
   *
   * The `grants` are what the template **will ask for**, never what it has. A template is created
   * paused and with no permissions, and a person grants them — the same door as any other flow.
   *
   * A hub older than this route leaves the method **absent** rather than broken, like
   * `events.list` (hub#823): the SDK travels with the hub, so `typeof flows.templates` is the
   * probe, and the screen can say «this hub does not serve module templates yet» instead of
   * showing an empty gallery that reads as «this module ships none».
   */
  async templates(): Promise<ModuleFlowTemplate[]> {
    return this.send({ method: 'GET', path: `${FLOWS_BASE_PATH}/templates` }) as Promise<
      ModuleFlowTemplate[]
    >;
  }

  /**
   * `GET /api/hub/flows/templates`, read for its other half (hub#2123): **the automations of this
   * module that the hub is NOT offering, and why**.
   *
   * The hub computes it since hub#1649 and answers it next to `data`, but {@link templates} returns
   * `data` alone, so no module could tell «I ship none» from «the hub left mine out». Read the
   * `code`; `detail` is prose for a person and is never compared (ADR-0055). On the floor codes
   * (`template_floor_*`) `requires` names the neighbour as data — which module, the floor, and the
   * version installed here (`null` = not installed) — so the card can say «Needs Staff, which is
   * paused» in the user's language.
   *
   * Same request and scope as {@link templates}: only this module's own. A separate method so the
   * array `templates()` returns keeps its shape. A hub older than this method leaves it
   * **absent**: `typeof flows.templateDiscards` is the probe.
   */
  async templateDiscards(): Promise<FlowTemplateDiscard[]> {
    const path = `${FLOWS_BASE_PATH}/templates`;
    const env = (await this.send({ method: 'GET', path, envelope: true })) as {
      discarded?: unknown;
    };
    // «Nothing was left out» is a claim; an answer that does not carry the list cannot make it.
    if (!Array.isArray(env?.discarded)) {
      throw new ErploraError(SERVER_UNAVAILABLE, `unexpected response from ${path}: no discarded list`);
    }
    return env.discarded as FlowTemplateDiscard[];
  }

  /**
   * `POST /api/hub/flows/templates/{thisModule}/{family}/activate` — **the one tap** (hub#1677,
   * ADR-0470).
   *
   * Builds this module's own factory recipe (or finds the one already built), gives it exactly the
   * permissions the family's sidecar declared — the pins included — and leaves it RUNNING. That is
   * the amendment to ADR-0463 §5 («grants are shown, not granted») and it is limited to this path:
   * what is granted is what the module's publisher declared and signed, `erplora validate` checked
   * before publication, and the owner consented to in the one sentence this module paints.
   *
   * Pressing it twice lands on the SAME automation. The refusals worth handling by name:
   * `flow.template_not_found` (nobody ships that family) and the discard codes the listing already
   * serves — `template_floor_module_too_old` and friends — which arrive as `409` and are the reason
   * to show instead of a mute failure.
   *
   * A hub older than this route leaves the method **absent** rather than broken, like
   * {@link templates}: `typeof flows.activateTemplate` is the probe.
   */
  async activateTemplate(family: string): Promise<Flow> {
    const own = checkedSegment('module id', this.moduleId, ID_PATTERN);
    const target = checkedSegment('template family', family, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${FLOWS_BASE_PATH}/templates/${own}/${target}/activate`,
    }) as Promise<Flow>;
  }

  /**
   * `POST /api/hub/flows/templates/{thisModule}/{family}/deactivate` — a **pause**, never a delete.
   *
   * The permissions stay and so does the run history: what that automation did needs an owner that
   * still exists, and turning it back on must not ask the person to authorise again what they
   * already authorised. A family that was never activated answers `flow.not_found`.
   */
  async deactivateTemplate(family: string): Promise<Flow> {
    const own = checkedSegment('module id', this.moduleId, ID_PATTERN);
    const target = checkedSegment('template family', family, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${FLOWS_BASE_PATH}/templates/${own}/${target}/deactivate`,
    }) as Promise<Flow>;
  }

  /**
   * `POST /api/hub/flows/templates/{thisModule}/{family}/restore` — the explicit **«restore the
   * factory recipe»** gesture (hub#2059).
   *
   * Same flow (id and run history kept), rebuilt from the module's CURRENT document and given
   * exactly the permissions it declares today — pins included. The owner's own edits to the flow
   * are lost; that is the whole point of the button, never a side effect of something softer.
   * Paused stays paused, running stays running: this is not {@link activateTemplate}.
   *
   * A family that was never activated answers `flow.not_found` — there is no factory recipe here
   * to restore. A module may only restore its OWN recipes through this method, exactly like
   * {@link activateTemplate}; the gallery that holds `manage_flows` may restore any module's, but
   * that is a different door, not this one: {@link restoreModuleTemplate}.
   *
   * A hub older than this route leaves the method **absent** rather than broken, like
   * {@link activateTemplate}: `typeof flows.restoreTemplate` is the probe.
   */
  async restoreTemplate(family: string): Promise<Flow> {
    const own = checkedSegment('module id', this.moduleId, ID_PATTERN);
    const target = checkedSegment('template family', family, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${FLOWS_BASE_PATH}/templates/${own}/${target}/restore`,
    }) as Promise<Flow>;
  }

  /**
   * `POST /api/hub/flows/templates/{module}/{family}/restore` — the Automations gallery's door
   * (flows#136), for the `flows` module to restore a recipe that belongs to ANOTHER module, not
   * its own.
   *
   * Unlike {@link restoreTemplate}, `module` is an argument here, so it is checked exactly like
   * `family`. The path names the target module; the `X-Erplora-Module` header still names the
   * calling module (`send` sets it, nothing to do here), and the hub judges that caller, not the
   * path, in `refuse_unless_own_or_editor` (hub#2059, `crates/server/src/flows_api.rs`): it lets
   * the call through only when the caller holds `manage_flows`, or the caller names itself — every
   * other caller gets `403 flow.template_not_yours`.
   *
   * Same effect as {@link restoreTemplate} otherwise: same flow id and run history, its document
   * and grants rebuilt from the target module's CURRENT recipe, enabled state unchanged. A family
   * that was never activated answers `flow.not_found`, same as the other door.
   *
   * A hub older than this method leaves it **absent** rather than broken, like
   * {@link restoreTemplate}: `typeof flows.restoreModuleTemplate` is the probe.
   */
  async restoreModuleTemplate(module: string, family: string): Promise<Flow> {
    const targetModule = checkedSegment('module id', module, ID_PATTERN);
    const targetFamily = checkedSegment('template family', family, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${FLOWS_BASE_PATH}/templates/${targetModule}/${targetFamily}/restore`,
    }) as Promise<Flow>;
  }
}

/**
 * A factory automation of this module that the hub is NOT offering, and why (hub#1649, hub#2123).
 */
export interface FlowTemplateDiscard {
  /** The module that ships it — always the caller itself. */
  module: string;
  /** The family left out, or the file name when it did not even name one. */
  family: string;
  /** Stable reason code (`template_floor_module_paused`, `template_owner_paused`…). Read this. */
  code: string;
  /** A sentence for a person. Never compared (ADR-0055). */
  detail: string;
  /**
   * Only on the floor codes (`template_floor_*`): the neighbour the floor names. `installed` is the
   * version this hub has, or `null` when it is not installed.
   */
  requires?: { module: string; floor: string; installed: string | null };
}

/**
 * A factory automation shipped by an installed module (hub#1611).
 *
 * The document travels **per language** and uncollated: `erplora validate` already guarantees every
 * language declares the same steps, in the same order, with the same machinery — only the prose
 * differs — so serving the hub's language or falling back to `en` is serving the SAME automation in
 * other words.
 */
export interface ModuleFlowTemplate {
  /** The module that ships it, so the gallery can say where an entry comes from. */
  module: string;
  /** The shared prefix of the family's files (`appointment-from-whatsapp`). */
  family: string;
  /** `lang -> flow document`. Always carries `en`, the source language (ADR-0055/0199). */
  documents: Record<string, unknown>;
  /**
   * What the template will ASK the owner for. Never what it already holds.
   *
   * `payload` is the part of the call this permission **FIXES** (hub#1623, hub#1654): absent or
   * empty fixes nothing, and `{ "channel": "customer" }` on `appointments.appointments.cancel`
   * turns «may cancel appointments» into «may cancel appointments AS THE CUSTOMER». Paint it and
   * hand it back on `PUT …/flows/<id>/grants` unchanged — a pin dropped between this list and the
   * permission screen is a wide permission granted by an owner who believed they narrowed it.
   *
   * `reason` is the sentence that explains the permission, `lang -> text` (hub#2069, flows#114):
   * the module writes it in its `<family>.grants.json` and the hub serves it verbatim. Optional —
   * absent means the module gave none, and the screen falls back to the bare command name.
   */
  grants: Array<{
    kind: string;
    value: string;
    payload?: Record<string, unknown>;
    reason?: Record<string, string>;
  }>;
  /** Per-template version floor (`module -> SemVer`). Unmet -> do not offer it. */
  requires: Record<string, string>;
  /**
   * The flow this hub has already built from it, or `null` when it has not (hub#1677, ADR-0470 §5).
   *
   * `null` and not absent, so the card can tell «not installed» from «this hub is too old to know»:
   * a hub before this field leaves the key out entirely, and `undefined` is the honest answer there.
   * `enabled: false` is a recipe that IS installed and paused — «paused», not «activate me».
   *
   * It replaces the heuristic of wi#79 (guess by trigger event + command), which could not tell two
   * families of the same module apart: with two appointment recipes and one of them on, both read
   * as «you already have this one».
   */
  installed?: {
    flow_id: string;
    enabled: boolean;
    /**
     * Whether the installed flow was built from an OLDER version of the recipe this module ships
     * today (hub#2059).
     *
     * `true` — the module now ships a different recipe than the one this flow was built from:
     * offer «Restore the factory one» ({@link FlowsApi.restoreTemplate}), never overwrite it on its
     * own. `false` — the flow already matches what the module ships. `null` — this hub cannot tell
     * (the flow was built before the hub started remembering the recipe's version). Absent — a hub
     * older than hub#2059, which never computed this at all.
     */
    outdated?: boolean | null;
  } | null;
}

/**
 * One field of an event payload (hub#715): a path the flow mapping language can resolve, its type
 * and — when the value could not be about a person — one real example from this hub.
 */
export interface EventFieldShape {
  /** `total`, `customer.id`. Paste it as `event.<path>` into a mapping and it resolves. */
  path: string;
  /** `string` · `number` · `boolean` · `object` · `array` · `null`. */
  type: string;
  /** A real value from a real event. Absent when redacted, and for objects and arrays. */
  sample?: unknown;
  /**
   * The example was withheld because the value could be about a person. **The field still
   * exists** — offer it in the picker, just without an example beside it.
   */
  redacted: boolean;
  /** The example was cut short. */
  truncated: boolean;
  /** Items in the newest sample, for an array. Nothing is offered from INSIDE one: the mapping
   *  language has no array indexing. */
  items?: number;
  /** In how many of the sampled events the path was present. Below `samples` = **optional**. */
  seen_in: number;
}

/** What `GET /api/hub/events/shape` answers. */
export interface EventShape {
  event_name: string;
  /** Installed modules that declare they emit it. */
  declared_by: string[];
  /**
   * How many real events the shape came from. **`0` means «no examples yet», not «no such
   * event»**: an infrequent event whose last occurrence aged out of the ninety-day retention
   * window lands here, and the picker should say so instead of hiding the trigger.
   */
  samples: number;
  last_seen_at?: string;
  fields: EventFieldShape[];
}

/**
 * One line of `GET /api/hub/events` (hub#823): an event this hub can produce, and **only its
 * name** — what it carries stays behind {@link EventsApi.shape} with the redaction of ADR-0312.
 *
 * The union of two sources, and the difference between them is information the picker needs:
 * `declared_by` empty means the name was seen in the outbox but no installed module claims it any
 * more (the module was uninstalled), and a missing `last_seen_at` means it is declared but has
 * never happened here yet. Neither disqualifies it as a trigger — a shop that has not sold
 * anything still gets to automate its first sale.
 */
export interface EventCatalogEntry {
  /** The event name exactly as it is emitted: `sale.completed`. */
  name: string;
  /** Installed modules declaring they emit it. Empty = only the outbox remembers it. */
  declared_by: string[];
  /** When this hub last emitted it. Absent = never (within the retention window). */
  last_seen_at?: string;
}

/**
 * **One dead-letter**: a business event that never happened — the note that was not written, the
 * warning that never went out — left in `_event_outbox` after the relay gave up (hub#660).
 *
 * The whole payload travels, deliberately: an operator deciding between «replay this» and «close it
 * for good» is deciding ABOUT the payload. It is also why this read sits behind `manage_flows` and
 * not behind «an admin is logged in» — it is the widest of the three outbox reads.
 */
export interface DeadEvent {
  id: string;
  event_name: string;
  /** The **emitting** module (attribution): who produced the event, not who refused it. */
  module_id: string;
  /** The user whose context the emitter ran with — the cashier behind a structural dead-letter. */
  user_id: string;
  payload: unknown;
  last_error: string;
  attempts: number;
  depth: number;
  created_at: string;
  /**
   * Why the row is terminal, when the answer is not «it burnt its eight attempts» (hub#827). `''`
   * for an ordinary dead-letter; {@link RELEASE_REVOKED} when the owner withdrew a flow's
   * authorisation while the message was still queued.
   */
  failure_kind: string;
  /**
   * Whether {@link EventsApi.retry} can do anything with this row. **A screen must not offer a
   * button that cannot work**: retrying a revoked release used to answer `200`, reset the attempts
   * and die again for the same reason — a loop with no exit, drawn as the remedy. When this is
   * `false`, show what WOULD help instead.
   */
  retryable: boolean;
}

/** What `GET /api/hub/events/dead/count` answers — the number a badge renders. */
export interface DeadCount {
  count: number;
}

/** What `POST /api/hub/events/retry-all` answers: how many rows of THIS hub went back to the relay. */
export interface RetryAllResult {
  retried: number;
}

/** What `POST /api/hub/events/{id}/discard` answers: the closed row's stamp (hub#955). */
export interface DiscardResult {
  id: string;
  status: string;
  /** `hub_user:<id>` — the resolved session, never anything the caller sent. */
  discarded_by: string;
  /**
   * Why it was closed, **as stored**: trimmed and capped by the runtime, `''` when no reason was
   * given. A hub older than hub#955 leaves the field out entirely, so a tray that renders it must
   * treat it as possibly absent.
   */
  discard_reason?: string;
}

/**
 * **One dead-letter somebody CLOSED**, with the whole stamp the close left behind (hub#1117).
 *
 * The sibling of {@link DeadEvent}, and deliberately not the same shape. A dead-letter is a
 * decision waiting to be made, so it travels with its payload — that is what tells a lost invoice
 * from noise. A closed row is a decision already made, and what is asked of it afterwards is «who
 * closed this, when and why», never «what did it carry»: **no payload travels here**.
 *
 * The three parts of the stamp arrive together because an audit record is the three together.
 * «Somebody closed this» was already stored before hub#955 and it is the half that needed no
 * storing; the reason is the half only the person closing the row knew.
 */
export interface DiscardedEvent {
  id: string;
  event_name: string;
  /** The **emitting** module (attribution), as in {@link DeadEvent}. */
  module_id: string;
  /** Why it died in the first place — the half of the story the hub knows on its own. */
  last_error: string;
  created_at: string;
  /** When it was closed. Also the row's retention clock: ninety days from here it is pruned. */
  discarded_at: string;
  /** `hub_user:<id>` — the resolved session, never anything the caller sent. */
  discarded_by: string;
  /** Why a person closed it, **as stored** (trimmed and capped). `''` when none was given. */
  discard_reason: string;
}

/** One link of a correlation chain (hub#666). No payload: the chain is for walking, not inspecting. */
export interface CorrelatedEvent {
  id: string;
  event_name: string;
  module_id: string;
  status: string;
  /** The flow run that emitted it (`''` when a person's command did). */
  run_id: string;
  /** The event whose delivery caused it (`''` when it is the root of its chain). */
  parent_event_id: string;
  depth: number;
  created_at: string;
}

/**
 * What `GET /api/hub/events/{id}/trace` answers (hub#666): **what this event set off** — the flow
 * runs it started and the events its delivery caused. One level only; the caller follows the link
 * it cares about, one hop at a time.
 */
export interface EventTrace {
  event: CorrelatedEvent;
  /**
   * The runs this event started. Left `unknown` for the same reason {@link FlowsApi.getRun} is:
   * the run shape belongs to the kernel and a second copy here is one that can drift.
   */
  runs: unknown[];
  caused: CorrelatedEvent[];
}

/**
 * **The hub's event catalogue and its dead-letter queue** (hub#715, hub#823, hub#953) — which
 * events this hub can produce, what each of them carries, and which of them never made it.
 *
 * Not the live event bus: to react to events, use `subscribe`. This is the read the flow editor is
 * built from — {@link list} fills its «when this happens» dropdown, {@link shape} its data picker,
 * so the owner chooses «Total de la venta — 42,50 €» and not `sale.total` — plus the seven gestures
 * that make a failure recoverable ({@link dead}, {@link deadCount}, {@link retry}, {@link discard},
 * {@link discarded}, {@link retryAll}, {@link trace}), which is the tray `ERPlora/flows#20` draws.
 *
 * **All nine sit behind the same two gates** (ADR-0312, hub#953): a human owner/admin session the
 * runtime checks, plus `manage_flows` declared in the calling module's `module.json` and granted by
 * the owner. The gate matters MORE for the dead-letter half than for the catalogue: a dead-letter
 * carries the whole payload, and {@link retry} re-runs another module's command with THAT module's
 * authority (hub#686). Without it, one installed module could drive another's automations.
 *
 * Nine methods, nine routes, no method that takes a path — the same discipline as
 * {@link FlowsApi}, pinned by the same test file.
 */
export class EventsApi {
  constructor(private readonly send: (req: CoreRequest) => Promise<unknown>) {}

  /**
   * `GET /api/hub/events` — **the events this hub can produce**, names only.
   *
   * The union of what the installed modules declare and what the outbox has really seen, so the
   * trigger picker offers this business's own events instead of a list typed into a module that
   * ages on its own and can never name an event nobody thought to add (flows#8).
   *
   * Names only, deliberately: what an event CARRIES is a separate read behind {@link shape}, with
   * the redaction ADR-0312 put there. Listing the names of a hub's events is not the same
   * disclosure as listing its customers' email addresses, and only the second needs the sampling
   * machinery — but both sit behind the same `manage_flows` gate, because the set of events a
   * business emits is still the shape of that business.
   */
  async list(): Promise<EventCatalogEntry[]> {
    return this.send({ method: 'GET', path: EVENTS_BASE_PATH }) as Promise<EventCatalogEntry[]>;
  }

  /**
   * `GET /api/hub/events/shape?name=…` — the fields of an event, with an example each.
   *
   * The hub answers the SHAPE, never a stored payload: a value that could be about a person
   * arrives with `redacted: true` and no `sample`, and the field is still there to be mapped. A
   * `not_found` refusal means this hub has never heard of the event at all — one that simply has
   * no surviving examples answers with `samples: 0`.
   */
  async shape(name: string, opts: { limit?: number } = {}): Promise<EventShape> {
    const event = checkedSegment('event name', name, EVENT_NAME_PATTERN);
    return this.send({
      method: 'GET',
      path: `${EVENTS_BASE_PATH}/shape${queryString({ name: event, limit: opts.limit })}`,
    }) as Promise<EventShape>;
  }

  // ── The dead-letter queue (hub#660, exposed by hub#953) ─────────────────────────────────────
  //
  // Four gestures and two reads, and between them they are the difference between «the engine is
  // built» and «somebody can use it». A dead event is business that did not happen, and until this
  // surface existed it was visible only to whoever knew how to `curl` — never to the owner of the
  // salon whose reminder never went out.

  /**
   * `GET /api/hub/events/dead` — **what died**, newest first, with the payload it was carrying.
   *
   * The payload is the point: it is what lets an operator tell a lost invoice from noise. Rows come
   * with {@link DeadEvent.retryable} already decided by the runtime, so a screen knows which ones
   * it may offer «Retry» for **before** anyone presses anything.
   */
  async dead(): Promise<DeadEvent[]> {
    return this.send({
      method: 'GET',
      path: `${EVENTS_BASE_PATH}/dead`,
    }) as Promise<DeadEvent[]>;
  }

  /**
   * `GET /api/hub/events/dead/count` — the cheap number (no payloads), for a badge.
   *
   * Counts only `dead`: `delivered`/`pending` are not failures, and `discarded` are failures a
   * person already decided to keep closed. Neither is «something that needs you».
   */
  async deadCount(): Promise<DeadCount> {
    return this.send({
      method: 'GET',
      path: `${EVENTS_BASE_PATH}/dead/count`,
    }) as Promise<DeadCount>;
  }

  /**
   * `POST /api/hub/events/{id}/retry` — put one dead-letter back in front of the relay.
   *
   * The delivery happens on the relay's next cycle, not here: at-least-once plus the idempotency of
   * `_event_delivery` still hold, so listeners that already succeeded on an earlier attempt are not
   * re-run.
   *
   * **Rejects when the retry can never work.** A row whose flow authorisation was withdrawn answers
   * `409` with {@link RELEASE_REVOKED}, and it arrives here as a thrown {@link ErploraError}
   * carrying that code — never as a resolved promise. Reporting «re-sent» for a message that did
   * not move is the one outcome a recovery tray must not produce.
   */
  async retry(id: string): Promise<{ id: string; status: string }> {
    const event = checkedSegment('event id', id, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${EVENTS_BASE_PATH}/${event}/retry`,
    }) as Promise<{ id: string; status: string }>;
  }

  /**
   * `POST /api/hub/events/{id}/discard` — close a dead-letter for good, optionally saying WHY.
   *
   * **Never a delete**: the row survives as the only proof the event existed, stamped with
   * `discarded_at` and a `discarded_by` the runtime takes from the resolved session — never from
   * anything a caller sends. The relay does not pick it up again.
   *
   * `reason` is the one part of the stamp the hub cannot know (hub#955), so it is the one thing
   * this body carries. It is stored trimmed and capped, and it comes back in the answer as
   * {@link DiscardResult.discard_reason} — the stored value, not the string that was sent. Leaving
   * it out sends no body at all: discarding without an explanation stays a legitimate gesture,
   * because a queue that demands an essay to close a row is a queue nobody drains.
   */
  async discard(id: string, reason?: string): Promise<DiscardResult> {
    const event = checkedSegment('event id', id, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${EVENTS_BASE_PATH}/${event}/discard`,
      ...(reason === undefined ? {} : { body: { reason } }),
    }) as Promise<DiscardResult>;
  }

  /**
   * `GET /api/hub/events/discarded` — **what was closed by hand**, newest closure first, with the
   * whole stamp: who, when and WHY (hub#1117).
   *
   * The read half of {@link discard}. All three parts had been stored since hub#955 and nothing
   * projected any of them: {@link dead} filters `dead`, so closing a row took it out of the only
   * listing there was, and {@link trace} returns the status without the stamp. A tray could show
   * «cerrado porque…» only for as long as the component that closed it stayed mounted — the
   * promise «durante noventa días» was checkable with `psql` and nowhere else.
   *
   * The ninety days need no argument here: retention is a hard delete, so a row past the window is
   * simply not in the answer. No id and no filter, like {@link retryAll} — the hub answers about
   * ITS OWN closed rows, and no argument exists that could name another tenant's.
   *
   * **No payload**, unlike {@link dead}: this is an audit read of a decision already made. The
   * tray `ERPlora/flows#47` draws is built on it.
   */
  async discarded(): Promise<DiscardedEvent[]> {
    return this.send({
      method: 'GET',
      path: `${EVENTS_BASE_PATH}/discarded`,
    }) as Promise<DiscardedEvent[]>;
  }

  /**
   * `POST /api/hub/events/retry-all` — every dead-letter of **THIS hub**, back to the relay at once.
   *
   * For the real case the one-by-one gesture does not cover: a transient outage (the database went
   * down, a module was deactivated mid-flight) killed several events at the same time and the cause
   * is now fixed. There is no id and no filter, exactly like the endpoint — no argument exists that
   * could name another tenant's rows. Rows that can never be replayed are skipped, not swept along.
   */
  async retryAll(): Promise<RetryAllResult> {
    return this.send({
      method: 'POST',
      path: `${EVENTS_BASE_PATH}/retry-all`,
    }) as Promise<RetryAllResult>;
  }

  /**
   * `GET /api/hub/events/{id}/trace` — **what this event set off** (hub#666): the flow runs it
   * started and the events its delivery caused, one level deep.
   *
   * The forward reading of the correlation columns — the door that answers «this sale fired these
   * five steps» from the sale end, which is the end a person actually has.
   */
  async trace(id: string): Promise<EventTrace> {
    const event = checkedSegment('event id', id, ID_PATTERN);
    return this.send({
      method: 'GET',
      path: `${EVENTS_BASE_PATH}/${event}/trace`,
    }) as Promise<EventTrace>;
  }
}

/** Where the business's WhatsApp templates live. Every path {@link WhatsappTemplatesApi} can build
 *  starts here — `crates/server/src/whatsapp_templates.rs` (hub#1610). */
export const WHATSAPP_TEMPLATES_BASE_PATH = '/api/hub/whatsapp/templates';

/** Where the sample of a template's photo, video or PDF header goes up — the one path
 *  {@link WhatsappTemplatesApi.uploadHeaderSample} posts to (`crates/server/src/
 *  whatsapp_header_samples.rs`, hub#2232). */
export const WHATSAPP_TEMPLATE_HEADER_SAMPLES_PATH = '/api/hub/whatsapp/template-header-samples';

/**
 * A Meta template name, exactly as the runtime defines it
 * (`whatsapp_templates.rs::template_name_is_safe`, itself the SaaS's `NAME_RE`): lowercase letters,
 * digits and underscores, up to 512. Checked here for ONE reason — the name is pasted into a path
 * by {@link WhatsappTemplatesApi.remove}, and `fetch` normalises `..` out of a URL, so a name is
 * the one value in this surface an attacker could steer a request with. The runtime refuses the
 * same names and stays the door that counts; this is the half that never builds the URL at all.
 */
const TEMPLATE_NAME_PATTERN = /^[a-z0-9_]{1,512}$/;

/**
 * One template of the business, with the verdict Meta gave it.
 *
 * The field names are **the SaaS's**, not this SDK's: the runtime is a passthrough (status and body
 * come back untouched) and re-shaping them here would be a second place to keep in step with Meta.
 * `status` and `rejected_reason` travel as CODES for the same reason — the module turns them into a
 * sentence with its own `en` + `es` strings (ADR-0055), so a `status` translated to prose here is a
 * status the tab could no longer act on.
 */
export interface WhatsappTemplate {
  name: string;
  language: string;
  category?: string;
  /** Meta's verdict as Meta words it: `PENDING`, `APPROVED`, `REJECTED`, `PAUSED`… */
  status: string;
  /** Why Meta rejected it, as a code (`INVALID_FORMAT`). Absent unless `status` is a rejection. */
  rejected_reason?: string;
  meta_id?: string;
  [field: string]: unknown;
}

/** What `GET /api/hub/whatsapp/templates` answers. */
export interface WhatsappTemplateList {
  templates: WhatsappTemplate[];
  /**
   * `true` when the SaaS could not reach Meta and is answering with what it had stored, so the tab
   * can say the verdicts may have moved instead of presenting stale ones as current.
   */
  stale: boolean;
}

/**
 * The template the business wrote, on its way to Meta.
 *
 * Deliberately open: every rule about what Meta accepts — the name, the category, the numbered
 * placeholders, one example per placeholder — lives in the SaaS, which is the half that knows.
 * The runtime does not copy them either (it checks only that the body is an object), and a type
 * that copied them here would refuse templates Meta would have taken and would need updating every
 * time Meta moves.
 */
export interface WhatsappTemplateInput {
  name: string;
  language: string;
  category?: string;
  /**
   * A header that is a file (hub#2232, saas#2377): `IMAGE`, `VIDEO` or `DOCUMENT`, with no header
   * text. Absent or `TEXT` is a text header, exactly as before.
   */
  header_format?: 'TEXT' | WhatsappHeaderSampleFormat;
  /**
   * With a file header: the {@link WhatsappTemplateHeaderSample.header_handle} that
   * {@link WhatsappTemplatesApi.uploadHeaderSample} returned. Asked on EVERY save — Meta holds the
   * sample, not a handle it would take back.
   */
  header_handle?: string;
  [field: string]: unknown;
}

/** The kinds of file a template header can be, as Meta names them. */
export type WhatsappHeaderSampleFormat = 'IMAGE' | 'VIDEO' | 'DOCUMENT';

/**
 * What {@link WhatsappTemplatesApi.uploadHeaderSample} answers (saas#2377). `format` is decided by
 * the file's BYTES, not by the type the browser declared: register the header with this one.
 */
export interface WhatsappTemplateHeaderSample {
  header_handle: string;
  format: WhatsappHeaderSampleFormat;
  mime_type: string;
  size: number;
}

/**
 * **The templates the business promises Meta** (hub#1682) — the only way a module reaches them.
 *
 * Four methods and no more. It is not a proxy and must not become one: the paths are two fixed
 * constants ({@link WHATSAPP_TEMPLATES_BASE_PATH} and, for a header's sample,
 * {@link WHATSAPP_TEMPLATE_HEADER_SAMPLES_PATH}), the only value that ever reaches a path is a
 * template name checked against {@link TEMPLATE_NAME_PATTERN} first, and the method list is pinned
 * by `whatsapp-templates.test.ts`.
 *
 * The credential is never here. The shell puts `X-Hub-Session` on the transport and the runtime
 * swaps it for the hub's machine credential on its way to the SaaS (ADR-0003), which is what keeps
 * the Meta token out of the browser (ADR-0012).
 */
export class WhatsappTemplatesApi {
  constructor(private readonly send: (req: CoreRequest) => Promise<unknown>) {}

  /**
   * `GET /api/hub/whatsapp/templates` — every template of this business with the verdict Meta gave
   * it, plus {@link WhatsappTemplateList.stale} when the SaaS answered from store because Meta was
   * unreachable.
   *
   * Read when the tab OPENS, never on a timer: the SaaS refreshes against Meta on every call and
   * that path carries no throttle of its own (hub#1610).
   */
  async list(): Promise<WhatsappTemplateList> {
    return this.send({
      method: 'GET',
      path: WHATSAPP_TEMPLATES_BASE_PATH,
    }) as Promise<WhatsappTemplateList>;
  }

  /**
   * `POST /api/hub/whatsapp/templates` — register the template with Meta. `201` when it is new,
   * `200` when it replaced one in place; **both come back `PENDING`**, because any edit sends a
   * template back through Meta's review.
   *
   * The body travels **verbatim**. A refusal comes back with its status and a `code`
   * (`invalid_name`, `missing_example`, `meta_rate_limited`…) inside an {@link ErploraError}, and
   * the module is the one that turns that code into a sentence (ADR-0055).
   *
   * The name is NOT checked here, unlike in {@link remove}: it travels in the body, never in a
   * path, so it cannot steer a request — and the SaaS is the half that knows which names Meta
   * takes. Checking it here would refuse templates Meta would have accepted.
   */
  async register(template: WhatsappTemplateInput): Promise<WhatsappTemplate> {
    return this.send({
      method: 'POST',
      path: WHATSAPP_TEMPLATES_BASE_PATH,
      body: template,
    }) as Promise<WhatsappTemplate>;
  }

  /**
   * `POST /api/hub/whatsapp/template-header-samples` — upload the sample of a photo, video or PDF
   * header to Meta and get back the `header_handle` the template is registered with (hub#2232).
   *
   * The file goes as the multipart field `file`, relayed by the runtime in streaming to the SaaS,
   * which holds the Meta token. What kind it is and how big it may be is decided THERE, from its
   * bytes (JPEG/PNG up to 5 MB, MP4 up to 16 MB, PDF up to 100 MB): a refusal arrives as an
   * {@link ErploraError} with its code — `unsupported_header_sample`, `header_sample_too_large`,
   * `missing_file`, `no_whatsapp_number`, `whatsapp_not_configured`, `meta_*`.
   *
   * A `File` keeps its name; a bare `Blob` goes up as `blob` (what `FormData` names it), still a
   * file part — a multipart part without a filename is not a file to the SaaS.
   */
  async uploadHeaderSample(file: Blob): Promise<WhatsappTemplateHeaderSample> {
    const form = new FormData();
    form.append('file', file);
    return this.send({
      method: 'POST',
      path: WHATSAPP_TEMPLATE_HEADER_SAMPLES_PATH,
      body: form,
    }) as Promise<WhatsappTemplateHeaderSample>;
  }

  /**
   * `DELETE /api/hub/whatsapp/templates/{name}` — drop it from Meta and from the SaaS, every
   * language of it.
   *
   * Answers `204`, so this resolves with `undefined`: there is no template left to describe.
   * **Not reversible in any useful sense** — a template deleted has to be written and approved
   * again, and Meta's review takes days.
   */
  async remove(name: string): Promise<void> {
    const template = checkedSegment('template name', name, TEMPLATE_NAME_PATTERN);
    await this.send({
      method: 'DELETE',
      path: `${WHATSAPP_TEMPLATES_BASE_PATH}/${template}`,
    });
  }
}

/** Where a WhatsApp attachment is downloaded from. Every path {@link WhatsappMediaApi} can build
 *  starts here — `crates/server/src/whatsapp_media.rs` (hub#2114). */
export const WHATSAPP_MEDIA_BASE_PATH = '/api/hub/whatsapp/media';

/**
 * A Meta media id, exactly as the runtime and the SaaS define it (`whatsapp_media.rs::
 * media_id_is_safe`, saas#2289): digits, 1 to 32. It is pasted into a path, and `fetch` normalises
 * `..` out of a URL, so anything else is refused before a request exists.
 */
const MEDIA_ID_PATTERN = /^\d{1,32}$/;

/** A transport that can fetch bytes from the core's REST surface (hub#2114). */
export interface CoreBlobTransport {
  coreBlobRequest(path: string, headers?: Record<string, string>): Promise<Blob>;
}

/**
 * **A WhatsApp attachment** (hub#2114) — the photo, voice note, video or document a customer sent.
 *
 * Meta hands the business an asset id (`payload.image.id`, `payload.audio.id`…), never the file;
 * the SaaS swaps it for the bytes and the runtime streams them with the hub's machine credential,
 * which never reaches the browser (ADR-0003). One method and no more: the path is one fixed prefix
 * plus an id checked against {@link MEDIA_ID_PATTERN}, and the method list is pinned by
 * `whatsapp-media.test.ts`.
 */
export class WhatsappMediaApi {
  constructor(private readonly fetchBlob: (path: string) => Promise<Blob>) {}

  /**
   * `GET /api/hub/whatsapp/media/{mediaId}` — the file, as a `Blob` whose `type` is Meta's MIME
   * (`image/jpeg`, `audio/ogg; codecs=opus`…). Make an object URL of it and revoke it when the
   * bubble goes away.
   *
   * A refusal arrives as an {@link ErploraError} with the code to act on: `media_not_found` (Meta
   * no longer keeps it — do not retry), `media_unavailable` (Meta did not answer — offer «Retry»),
   * `meta_permission_denied` (reconnect WhatsApp), `no_whatsapp_number`, `capability_denied`
   * (`notify` on `whatsapp` not granted), `permission_denied` (this person cannot read the inbox).
   */
  async get(mediaId: string): Promise<Blob> {
    const id = checkedSegment('WhatsApp media id', mediaId, MEDIA_ID_PATTERN);
    return this.fetchBlob(`${WHATSAPP_MEDIA_BASE_PATH}/${id}`);
  }
}

/** Where the business certificate lives. Every path {@link CertificateApi} can build is this one. */
export const CERTIFICATE_BASE_PATH = '/api/business/certificate';

/** One certificate slot, as the runtime publishes it: presence and who put it there, never bytes. */
export interface CertificateSlot {
  present: boolean;
  uploaded_at?: string | null;
  /** `hub_user:<id>` of the admin who uploaded it. */
  uploaded_by?: string | null;
}

/**
 * What the three certificate doors answer: the state the certificate is in (or was left in).
 *
 * The root fields describe the business's OWN certificate. `active` is the slot that signs (`null`
 * when there is none) and `transmission_route` is how records reach the tax authority right now
 * (`own` with an own certificate, `delegated` through ERPlora's cell without one).
 */
export interface CertificateStatus extends CertificateSlot {
  slots: Record<string, CertificateSlot>;
  active: string | null;
  transmission_route: string;
  [field: string]: unknown;
}

/** An upload: the `.p12` / `.pfx` file as base64 and the password that opens it. */
export interface CertificateUpload {
  pkcs12Base64: string;
  password: string;
}

/**
 * **The business certificate** (hub#1844) — read its state, upload or replace it, remove it.
 *
 * Three methods and one path, pinned by `certificate.test.ts`. The custody does not move: the bytes
 * and the password go to the core, which encrypts them at rest, and nothing that comes back carries
 * either — only presence, who uploaded it and which road the records take.
 *
 * The session is never here. The shell puts `X-Hub-Session` on the transport, so a compliance
 * module's screen stops reading the token out of `localStorage` to reach this door.
 */
export class CertificateApi {
  constructor(private readonly send: (req: CoreRequest) => Promise<unknown>) {}

  /** `GET /api/business/certificate` — the state of the certificate. Never its bytes. */
  async get(): Promise<CertificateStatus> {
    return this.send({ method: 'GET', path: CERTIFICATE_BASE_PATH }) as Promise<CertificateStatus>;
  }

  /**
   * `PUT /api/business/certificate` — upload or replace the business's own certificate. Needs an
   * owner/admin session. A file the runtime cannot open comes back as an {@link ErploraError} with
   * its code, so the screen can say whether it was the file or the password.
   */
  async put(upload: CertificateUpload): Promise<CertificateStatus> {
    return this.send({
      method: 'PUT',
      path: CERTIFICATE_BASE_PATH,
      body: { pkcs12_b64: upload.pkcs12Base64, password: upload.password },
    }) as Promise<CertificateStatus>;
  }

  /**
   * `DELETE /api/business/certificate` — remove the business's own certificate. The hub goes back
   * to the delegated road; it does not stop invoicing. Answers the state it leaves.
   */
  async remove(): Promise<CertificateStatus> {
    return this.send({
      method: 'DELETE',
      path: CERTIFICATE_BASE_PATH,
    }) as Promise<CertificateStatus>;
  }
}

/** Where the hub's print queue lives. Every path {@link PrintApi} can build starts here. */
export const PRINT_JOBS_BASE_PATH = '/api/print/jobs';

/** What `POST /api/print/jobs/{jobId}/retry` answers: the job, back in the queue. */
export interface PrintRetryResult {
  jobId: string;
  /** Always `"pending"` on success — the job is waiting for a print host again. */
  status: string;
}

/** What `POST /api/print/jobs/{jobId}/discard` answers: the stamp the row now carries (hub#1108). */
export interface PrintDiscardResult {
  jobId: string;
  discardedAt: string;
  /** `hub_user:<id>`, resolved by the runtime from the session — never sent by the caller. */
  discardedBy: string;
  /** The STORED reason: trimmed and capped, not the string that was sent. */
  discardReason: string;
}

/**
 * **Getting a stuck print job unstuck** (hub#1108) — put it back, or close it for good.
 *
 * Not the queue itself: READING it is `hub.print.coverage` / `hub.print.jobs` (hub#1107), core
 * queries that travel through the dispatcher like any other, so `erplora().query(…)` is all a screen
 * needs to draw the ticket that is not coming out. This is the other half — the two gestures that
 * make the failure recoverable — and they are core REST for the same reason flows are (ADR-0283 §9).
 *
 * **Both sit behind two gates** and neither replaces the other: an owner/admin session the runtime
 * checks, plus the **`printer`** capability declared in the calling module's `module.json` and
 * granted by the owner. Reading the queue is any local session on purpose (hub#987: whoever is
 * standing next to the printer is who can turn the till on); binning a ticket or re-firing one is
 * the owner's gesture. Without the capability, "an admin is logged in" would mean every installed
 * module can bin every other one's tickets. A refusal arrives as `capability_denied`, so a screen
 * can ask for the grant instead of showing «error».
 *
 * Two methods, two routes, no method that takes a path — the same discipline as {@link FlowsApi} and
 * {@link EventsApi}, pinned by the same kind of test file.
 */
export class PrintApi {
  constructor(private readonly send: (req: CoreRequest) => Promise<unknown>) {}

  /**
   * `POST /api/print/jobs/{jobId}/retry` — put a **dead** job back in front of the print hosts, with
   * its hand-outs reset.
   *
   * It cannot be "queue it again": the queue is keyed by `(hub_id, jobId)` with
   * `ON CONFLICT DO NOTHING`, so re-enqueueing the same id is a no-op by construction — and a new id
   * is not an option either, because the document does not travel in the status view. Resetting the
   * attempts is the substance: the attempt ceiling is what sent the job to `dead`, so a retry that
   * kept the count would die on its first hand-out.
   *
   * **Rejects when the job is not `dead`**, with `print.job_not_requeueable` and the state it IS in,
   * so a screen can explain instead of reporting a move that never happened.
   */
  async retry(jobId: string): Promise<PrintRetryResult> {
    const job = checkedSegment('job id', jobId, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${PRINT_JOBS_BASE_PATH}/${job}/retry`,
    }) as Promise<PrintRetryResult>;
  }

  /**
   * `POST /api/print/jobs/{jobId}/discard` — retire a job nobody is ever going to print, optionally
   * saying WHY.
   *
   * **Never a delete**: the row survives as the only proof the ticket existed, stamped with
   * `discardedAt` and a `discardedBy` the runtime takes from the resolved session. No print host is
   * handed it again, and it stops holding its station hostage — deleting a station answers `409`
   * while anything is still queued for it.
   *
   * `reason` is the one part of the stamp the hub cannot know, so it is the one thing this body
   * carries. It is stored trimmed and capped and comes back as
   * {@link PrintDiscardResult.discardReason} — the stored value, not the string that was sent.
   * Leaving it out sends no body at all: a queue that demands an essay to close a row is a queue
   * nobody drains.
   *
   * **Rejects a job a host is printing** (`print.job_not_discardable`): the lease already covers the
   * host that died, and binning a ticket a live host is rendering would be the silent loss the queue
   * exists to prevent.
   */
  async discard(jobId: string, reason?: string): Promise<PrintDiscardResult> {
    const job = checkedSegment('job id', jobId, ID_PATTERN);
    return this.send({
      method: 'POST',
      path: `${PRINT_JOBS_BASE_PATH}/${job}/discard`,
      ...(reason === undefined ? {} : { body: { reason } }),
    }) as Promise<PrintDiscardResult>;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Cliente que usan los Web Components.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The runtime's RESERVED namespace owner (ADR-0192, `crates/runtime/src/hub_users.rs::CORE_NAMESPACE`):
 * `hub.*` is served by the core itself, before the module registry, and is never an installed
 * module — so it is never in `installedModules` and can never be proven absent. Without this
 * exemption the `queryOptional` short-circuit (hub#1211) would answer `undefined` for every
 * `queryOptional('hub.…')`, the exact false absence it exists to avoid (the runtime itself never
 * says `module_not_installed` for the core: a bad `hub.*` name is `not_found`, a broken contract,
 * and must still explode). Module-private on purpose: not part of the frozen public surface.
 */
const CORE_NAMESPACE_OWNER = 'hub';

export class ErploraClient {
  private bridge?: BridgeTransport;
  /** The module this client acts FOR, set only by {@link ErploraClient.forModule}. */
  private moduleId?: string;
  private flowsApi?: FlowsApi;
  private eventsApi?: EventsApi;
  private printApi?: PrintApi;
  private whatsappTemplatesApi?: WhatsappTemplatesApi;
  private whatsappMediaApi?: WhatsappMediaApi;
  private certificateApi?: CertificateApi;

  constructor(
    private readonly transport: ErploraTransport,
    private readonly opts: {
      permissions?: () => ReadonlySet<string>;
      notifier?: (n: Notification) => void;
      /**
       * Moneda ISO-4217 del hub (ADR-0059), inyectada por el shell (fuente: `/api/hub/context` →
       * `lib/money.ts → hubCurrency()`). El módulo NUNCA la hardcodea: lee `erplora.currency` o
       * formatea con `erplora.formatMoney` / `erplora.formatAmount`. Si el shell no la inyecta, el
       * cliente degrada a la moneda publicada en `globalThis.__erploraCurrency` o, en último término,
       * a `'EUR'` (igual que `locale` degrada a `'es'`). Inyectable para tests.
       */
      currency?: () => string;
      /** Los DECIMALES de la moneda del hub (ADR-0123 §7): EUR 2, JPY 0, KWD 3. Lo inyecta el shell
       *  desde `/api/hub/context` (`currency_decimals`). Sin esto, se resuelven del código ISO. */
      currencyDecimals?: () => number;
      /**
       * La zona horaria IANA del NEGOCIO, ya RESUELTA (hub#731, hub#1022): la declarada en settings
       * o la deducida del país del hub. La inyecta el shell desde `/api/hub/context` (misma fuente
       * que `currency`). Si no se inyecta, lee la que el shell publica en
       * `globalThis.__erploraTimezone` (mirror de `__erploraCurrency`) y, en último término,
       * degrada a `'UTC'`. La leen los módulos que agendan — «mañana a las 09:00» son las 09:00 de
       * la TIENDA: igual que el runtime entrega `context.timezone` a los handlers, el shell entrega
       * esto al Web Component. Inyectable para tests.
       */
      timezone?: () => string;
      /**
       * The live set of ACTIVE module ids (hub#1211) — the shell's `listInstalledModules()`
       * filtered to `status === 'active'`, refreshed on install/uninstall/activate/deactivate.
       * Lets `queryOptional`/`queryAllOptional` learn a module is absent WITHOUT a round trip:
       * before this existed, the only way to find that out was asking the transport and catching
       * `module_not_installed` after the request had already happened, so every optional
       * integration a hub does not have left a failed `POST /api/query` in the console per call.
       *
       * `undefined` means "I do not know yet" (e.g. before the shell's first `GET /api/modules`
       * resolves), and is treated as "cannot rule it out" — the SDK falls back to asking the
       * transport, exactly like before this option existed. Guessing "absent" while unknown would
       * be the SYMMETRIC regression: a real query silently skipped. Injectable for tests.
       */
      installedModules?: () => ReadonlySet<string> | undefined;
      /**
       * The mode of THIS device as the hub last answered (`GET /api/device/mode`, hub#358),
       * injected by the shell from its reactive `deviceMode`. A module cannot ask the hub itself:
       * the device id is native in the installable app and the runtime URL is not the page origin.
       * Re-read on every access, so a revoked `personal` is seen at once. Injectable for tests.
       */
      deviceMode?: () => DeviceMode;
    } = {},
    bridge?: BridgeTransport,
  ) {
    this.bridge = bridge;
  }

  /**
   * The module id a namespaced query/command NAME belongs to (ADR-0127: every name is namespaced
   * `modulo.entidad.accion`) — `"verifactu.records.by_invoice"` → `"verifactu"`. `undefined` for a
   * name with no dot: that is not a shape this SDK's naming convention produces, and refusing to
   * guess an owner keeps the short-circuit from ever misfiring on it (it just travels, as before).
   */
  private static ownerModuleOf(name: string): string | undefined {
    const dot = name.indexOf('.');
    return dot > 0 ? name.slice(0, dot) : undefined;
  }

  /**
   * `true` only when the caller can PROVE the owning module is absent — `installedModules()`
   * answered a concrete set and the module is not in it. Any doubt (no option wired, the set is
   * not known yet, or the name carries no recognisable owner) resolves to `false`, which keeps the
   * existing "ask the transport, catch the absence" path as the fallback. The core namespace is
   * never absent by construction (see {@link CORE_NAMESPACE_OWNER}).
   */
  private isKnownAbsent(name: string): boolean {
    const owner = ErploraClient.ownerModuleOf(name);
    if (!owner || owner === CORE_NAMESPACE_OWNER) return false;
    const installed = this.opts.installedModules?.();
    if (!installed) return false;
    return !installed.has(owner);
  }

  /**
   * Hardware local (impresoras de red / cajón) — el módulo llama AQUÍ, nunca al hardware directo.
   * El transporte lo elige el shell y lo inyecta; el módulo ni se entera. Igual que el WC nunca
   * toca la BD, tampoco toca el hardware por su cuenta (ARQUITECTURA.md §2.7).
   *
   * Sin transporte inyectado NO se inventa uno: se degrada a «aquí no hay hardware»
   * ({@link UnavailableBridgeTransport}). Antes el defecto era el cliente WS a `localhost:12321`,
   * de modo que un navegador cualquiera sondeaba un puerto local aunque el shell hubiera decidido
   * que no había hardware — justo lo que retira ADR-0196 §3.
   */
  get peripherals(): BridgeTransport {
    return (this.bridge ??= new UnavailableBridgeTransport());
  }

  /**
   * Descarga una referencia portable de `media/` sin exponer al módulo la sesión del Hub.
   * `null` cubre referencia inválida, fichero ausente, aborto y shells/transportes anteriores.
   */
  fetchMediaBlob(ref: string, opts: MediaFetchOptions = {}): Promise<Blob | null> {
    const fetcher = this.transport.fetchMediaBlob;
    return typeof fetcher === 'function'
      ? fetcher.call(this.transport, ref, opts)
      : Promise.resolve(null);
  }

  /**
   * **This client, acting for a named module** (hub#714). The only way to reach {@link flows}.
   *
   * The shell calls it when it MOUNTS a module's Web Component (`ModuleView.vue`), which is the one
   * place that genuinely knows which module is being loaded — so for every component the shell
   * mounts, the id comes from the loader and not from something the module wrote about itself.
   * A module that instead grabs `globalThis.erplora` gets the unscoped client, which has no `flows`
   * at all: it would have to call this and name itself, and that naming is visible in its source.
   *
   * It is a **view, not a copy**: the scope delegates to this very instance through the prototype
   * chain. That is deliberate and load-bearing — `apps/web/src/main.ts` bolts `print` and
   * `loadSlot` onto the one client object AFTER constructing it, and a scope built with
   * `new ErploraClient(…)` would silently lose both. The symptom would be «this module cannot
   * print» in a shop, a long way from here.
   */
  forModule(moduleId: string): ErploraClient {
    const id = typeof moduleId === 'string' ? moduleId.trim() : '';
    if (!id) {
      throw new ErploraError(INVALID_ARGUMENT, 'forModule() needs the id of the calling module');
    }
    const scoped = Object.create(this) as ErploraClient;
    scoped.moduleId = id;
    // Not inherited: the parent's memoised surfaces belong to the parent's scope (or to none).
    //
    // hub#1530 — this is a SECURITY line, not housekeeping. Each surface captured the module
    // header at the moment it was built, and the hub resolves the owner's grant from that header on
    // every request (`flows_api.rs::calling_module` → `require_module_capability`). Inheriting one
    // through the prototype chain would let this scope act under the PREVIOUS module's grant, and
    // make the `403` blame that module instead of the one that asked. Every field declared next to
    // `flowsApi` belongs here: `print.test.ts` discovers the module-scoped surfaces and fails if
    // any of them survives a re-scope, so a fourth one is covered the day it is written.
    scoped.flowsApi = undefined;
    scoped.eventsApi = undefined;
    scoped.printApi = undefined;
    scoped.whatsappTemplatesApi = undefined;
    scoped.whatsappMediaApi = undefined;
    scoped.certificateApi = undefined;
    return scoped;
  }

  /**
   * **The hub's automation kernel** (`/api/hub/flows*`, ADR-0283 §9) — flows, their grants, their
   * secrets and the approval tray. The typed way in for the flow editor module (pm#110).
   *
   * Reaching it needs THREE things, and this getter is only the first: the client must be scoped to
   * a module ({@link forModule}); the user must hold a local owner/admin session, which the runtime
   * checks and this SDK never second-guesses; and the module must have `manage_flows` declared in
   * its `module.json` and granted by the owner in Settings → Permissions. A refusal arrives as
   * `capability_denied`, so the editor can ask for the grant instead of showing «error».
   *
   * 🔴 **Three methods are the exception, and on purpose** (hub#1677, ADR-0470): {@link templates},
   * {@link activateTemplate} and {@link deactivateTemplate} need **no capability at all**. A module
   * that publishes a recipe does not compose flows or grants — it picks which of its own published
   * recipes is on — so asking it for `manage_flows`, the widest capability there is, in order to
   * press one switch would send the owner to the very Settings → Permissions trip this removes.
   * `templates` answers such a module with **its own** recipes and its own discards, nothing else;
   * a module that does hold `manage_flows` still gets the whole gallery.
   */
  get flows(): FlowsApi {
    const moduleId = this.moduleId;
    if (!moduleId) {
      throw new ErploraError(
        MODULE_SCOPE_REQUIRED,
        'the flows surface is module-scoped: use `erplora.forModule("<your module id>").flows`',
      );
    }
    const transport = this.transport as Partial<CoreApiTransport>;
    if (typeof transport.coreRequest !== 'function') {
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        'this transport cannot reach the core REST surface',
      );
    }
    return (this.flowsApi ??= new FlowsApi(
      (req) => coreCall(transport.coreRequest!(req, { [MODULE_HEADER]: moduleId }), req.method, this.locale, this.opts.notifier),
      moduleId,
    ));
  }

  /**
   * **What the hub's events carry** (hub#715) — the catalogue the flow editor's data picker is
   * built from, so the owner picks «Total de la venta — 42,50 €» and not `sale.total`.
   *
   * Module-scoped and gated exactly like {@link flows}: an owner/admin session the runtime checks,
   * plus `manage_flows` declared in the module's `module.json` and granted by the owner. What the
   * events of a business carry is the shape of that business, and it is not something every
   * installed module gets to read.
   *
   * This is **not** the live event bus — `subscribe` is.
   */
  get events(): EventsApi {
    const moduleId = this.moduleId;
    if (!moduleId) {
      throw new ErploraError(
        MODULE_SCOPE_REQUIRED,
        'the event catalogue is module-scoped: use `erplora.forModule("<your module id>").events`',
      );
    }
    const transport = this.transport as Partial<CoreApiTransport>;
    if (typeof transport.coreRequest !== 'function') {
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        'this transport cannot reach the core REST surface',
      );
    }
    return (this.eventsApi ??= new EventsApi((req) =>
      coreCall(transport.coreRequest!(req, { [MODULE_HEADER]: moduleId }), req.method, this.locale, this.opts.notifier),
    ));
  }

  /**
   * **The print queue's recovery gestures** (hub#1108) — put a dead ticket back, or retire one that
   * is never coming out.
   *
   * Reading the queue does not come through here: `hub.print.coverage` and `hub.print.jobs` are core
   * queries (hub#1107), so a screen draws the stuck ticket with `erplora.query(…)` like any other
   * data. This getter is the WRITE half, and it is module-scoped and gated: an owner/admin session
   * the runtime checks, plus `printer` declared in the module's `module.json` and granted by the
   * owner in Settings → Permissions.
   */
  /**
   * **The templates the business promises Meta** (hub#1682) — list them, register one, drop one.
   *
   * A template approved by Meta is the ONLY thing that lets the business write to a customer
   * outside the 24 h since that customer last wrote: without one there is no appointment reminder,
   * no «your order is ready» and no confirmation. Until this surface existed the WhatsApp module
   * could save a template and nothing more — Meta never saw it — and the owner had to leave ERPlora
   * and write it again in Meta's WhatsApp Manager.
   *
   * Module-scoped and gated twice, like every other surface here: an owner/admin session the
   * runtime checks, plus **`notify`** — «Notificaciones · enviar notificaciones por email, SMS o
   * WhatsApp» — declared in the module's `module.json` and granted by the owner in
   * Settings → Permissions. `notify` and not a new capability (ADR-0470): a template approved by
   * Meta is what makes a WhatsApp notification legal outside those 24 h, so it is the same risk the
   * owner already weighed. A refusal arrives as `capability_denied`, so the tab can ask for the
   * grant instead of showing «error».
   */
  get whatsappTemplates(): WhatsappTemplatesApi {
    const moduleId = this.moduleId;
    if (!moduleId) {
      throw new ErploraError(
        MODULE_SCOPE_REQUIRED,
        'the WhatsApp templates are module-scoped: use `erplora.forModule("<your module id>").whatsappTemplates`',
      );
    }
    const transport = this.transport as Partial<CoreApiTransport>;
    if (typeof transport.coreRequest !== 'function') {
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        'this transport cannot reach the core REST surface',
      );
    }
    return (this.whatsappTemplatesApi ??= new WhatsappTemplatesApi((req) =>
      coreCall(transport.coreRequest!(req, { [MODULE_HEADER]: moduleId }), req.method, this.locale, this.opts.notifier),
    ));
  }

  /**
   * **A WhatsApp attachment** (hub#2114) — `get(mediaId)` → the `Blob` of the photo, voice note,
   * video or document a customer sent.
   *
   * Module-scoped and gated twice by the runtime: a person with a session who may read the inbox
   * (`whatsapp_inbox.view_conversation`), plus **`notify`** on the `whatsapp` channel declared in the
   * module's `module.json` and granted by the owner — the criterion of {@link whatsappTemplates}.
   *
   * Reading this getter on a scoped client NEVER throws: the inbox reads it on every render of a
   * thread, and a throw there would take the whole conversation down instead of one attachment. A
   * transport that cannot fetch bytes (a shell older than this surface) makes `get` reject with
   * {@link SERVER_UNAVAILABLE} instead.
   */
  get whatsappMedia(): WhatsappMediaApi {
    const moduleId = this.moduleId;
    if (!moduleId) {
      throw new ErploraError(
        MODULE_SCOPE_REQUIRED,
        'WhatsApp attachments are module-scoped: use `erplora.forModule("<your module id>").whatsappMedia`',
      );
    }
    const transport = this.transport as Partial<CoreBlobTransport>;
    return (this.whatsappMediaApi ??= new WhatsappMediaApi((path) =>
      typeof transport.coreBlobRequest === 'function'
        ? coreCall(transport.coreBlobRequest(path, { [MODULE_HEADER]: moduleId }), 'GET', this.locale)
        : Promise.reject(
            new ErploraError(SERVER_UNAVAILABLE, 'this transport cannot fetch bytes from the hub'),
          ),
    ));
  }

  /**
   * **The business certificate** (hub#1844) — read its state, upload or replace it, remove it.
   *
   * The certificate belongs to the business, but the screen that manages it belongs to a compliance
   * module (the hub is country-agnostic, ADR-0424). Module-scoped and gated twice: an owner/admin
   * session the runtime checks (a user session is enough to read), plus **`certificate`** declared
   * in the module's `module.json` and granted by the owner — the same grant the module already needs
   * to sign with that key. A refusal arrives as `capability_denied`, so the screen can ask for the
   * grant instead of showing «error».
   */
  get certificate(): CertificateApi {
    const moduleId = this.moduleId;
    if (!moduleId) {
      throw new ErploraError(
        MODULE_SCOPE_REQUIRED,
        'the business certificate is module-scoped: use `erplora.forModule("<your module id>").certificate`',
      );
    }
    const transport = this.transport as Partial<CoreApiTransport>;
    if (typeof transport.coreRequest !== 'function') {
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        'this transport cannot reach the core REST surface',
      );
    }
    return (this.certificateApi ??= new CertificateApi((req) =>
      coreCall(transport.coreRequest!(req, { [MODULE_HEADER]: moduleId }), req.method, this.locale, this.opts.notifier),
    ));
  }

  /**
   * ⚠️ **Not `print`.** `erplora.print(req)` is a PUBLISHED contract — the shell bolts the print
   * service onto this very instance in `apps/web/src/main.ts` and every module calls it to QUEUE a
   * document. Taking that name for a getter would silently break printing in every installed
   * module, so the queue's recovery gestures live one word away.
   */
  get printQueue(): PrintApi {
    const moduleId = this.moduleId;
    if (!moduleId) {
      throw new ErploraError(
        MODULE_SCOPE_REQUIRED,
        'the print recovery gestures are module-scoped: use `erplora.forModule("<your module id>").printQueue`',
      );
    }
    const transport = this.transport as Partial<CoreApiTransport>;
    if (typeof transport.coreRequest !== 'function') {
      throw new ErploraError(
        SERVER_UNAVAILABLE,
        'this transport cannot reach the core REST surface',
      );
    }
    return (this.printApi ??= new PrintApi((req) =>
      coreCall(transport.coreRequest!(req, { [MODULE_HEADER]: moduleId }), req.method, this.locale, this.opts.notifier),
    ));
  }

  /**
   * Query genérica. Compat: si la query es de **lista** (`{rows,total,…}`), desenvuelve y entrega
   * solo `rows`, para que una vista antigua que aún use `query()` no se rompa al añadir un bloque
   * `list` a su query. Para paginar de verdad (total/página) usa `queryPage`.
   */
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T> {
    return this.transport.query(name, params).then(unwrapPage, (e: unknown) => {
      // hub#2288: a read the hub never answered is told in the user's language, not the
      // transport's technical line.
      throw unreachableRead(e, this.locale);
    }) as Promise<T>;
  }
  /**
   * Query a una integración **OPCIONAL** (ADR-0127): el módulo dueño puede no estar instalado en
   * este hub (`sales` consulta `verifactu` solo si existe). Devuelve `undefined` **únicamente**
   * ante `module_not_installed`; el llamador decide el default (`?? []`) — el SDK no inventa el
   * tipo de una query que no conoce.
   *
   * Todo lo demás EXPLOTA como en `query()`: una query renombrada en un módulo presente, un
   * permiso denegado o un handler roto son contratos rotos, no ausencias. Esto NO es un
   * `.catch(() => [])` — esa forma se tragaba las dos cosas y por eso se retiró.
   *
   * **Short-circuit (hub#1211):** when `installedModules` (injected by the shell) PROVES the owner
   * module is absent, this returns `undefined` without calling the transport — before, it learned
   * the absence by making the request anyway, so every absent optional integration left a
   * `404 POST /api/query` in the console on EVERY call. Without that proof (option not injected,
   * or not resolved yet), it takes the usual path: ask, and catch the absence. The core namespace
   * `hub.*` never short-circuits (it is not a module and cannot be absent).
   */
  async queryOptional<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T | undefined> {
    if (this.isKnownAbsent(name)) return undefined;
    try {
      return await this.query<T>(name, params);
    } catch (e) {
      // `module_inactive` (cascada ADR-0128) equivale a ausencia: un módulo desactivado no está
      // disponible, y el consumidor OBLIGATORIO nunca pregunta (la cascada lo apagó con su dep).
      if (e instanceof ErploraError && (e.code === 'module_not_installed' || e.code === 'module_inactive')) return undefined;
      throw e;
    }
  }
  /**
   * Ejecuta una **query de lista** (paginada): aplana `ListParams` y devuelve la página
   * `{rows,total,limit,offset}`. Úsala con `createListController` para el `<data-table>`.
   */
  async queryPage<T = unknown>(name: string, params: ListParams = {}): Promise<Page<T>> {
    try {
      return (await this.transport.query(name, buildListParams(params))) as Page<T>;
    } catch (e) {
      // hub#2288: same sentence as `query()`. `queryAll`/`queryAllOptional` and the list
      // controller read through here, so they get it without a wrap of their own.
      throw unreachableRead(e, this.locale);
    }
  }
  /**
   * Trae **TODAS** las filas de una query de lista. Sin tope, salvo que el llamador pase un `limit`.
   *
   * Para cuando la vista no quiere «una página» sino el conjunto entero: la rejilla de productos de
   * un TPV (un cajero tiene que poder vender TODO lo que vende la casa), un `<ion-select>` de
   * categorías fiscales, el mapa producto↔categoría… Ahí paginar no es una feature, es un fallo.
   *
   * Existe porque la forma en que se pedía eso —`query(name, { page_size: 200 })`— **no funcionaba**:
   * `page_size` no es un parámetro del runtime (lee `limit`), así que se ignoraba en silencio y
   * llegaban las 50 filas del `page_size` del manifest. Un restaurante con 80 platos solo podía
   * vender 50: los otros 30 no existían en el TPV y el buscador tampoco los encontraba.
   *
   * Cómo: una primera página (la que el módulo declare) trae ya el `total`; si faltan filas, se pide
   * el resto **por su total exacto**. Ningún número mágico cableado, y dos viajes como mucho.
   */
  async queryAll<T = unknown>(name: string, params: ListParams = {}): Promise<T[]> {
    const first = await this.queryPage<T>(name, { ...params, offset: 0 });
    // Una query SIN bloque `list` no devuelve sobre: contesta el array pelado. Se acepta tal cual.
    if (Array.isArray(first)) return first as T[];
    const rows = Array.isArray(first?.rows) ? first.rows : [];
    // El llamador mandó su propio `limit`: quiere ESE tope, no todo. Se respeta.
    if (params.limit != null) return rows;
    const total = first?.total ?? rows.length;
    if (rows.length >= total) return rows;
    const full = await this.queryPage<T>(name, { ...params, limit: total, offset: 0 });
    return Array.isArray(full?.rows) ? full.rows : rows;
  }
  /**
   * The WHOLE set of a query owned by an **OPTIONAL** module (ADR-0127) — {@link queryAll}'s
   * result with {@link queryOptional}'s tolerance, because until ERPlora/sales#186 there was no
   * way to ask for both at once and the POS paid for it:
   *
   * · `queryAll` brings everything, but a hub without the owner module gets `module_not_installed`
   *   in the face — so it cannot be used for an integration the hub may not have.
   * · `queryOptional` survives that absence, but answers ONE PAGE: `/api/query` on a query with a
   *   `list` block goes through `execute_query_page`, and with no `limit` the size is the
   *   manifest's `page_size` — 50 by default. A hair salon with 60 services could only sell 50,
   *   and nothing said so.
   *
   * So: `undefined` **only** when the module is absent (`module_not_installed`, or `module_inactive`
   * — the ADR-0128 cascade leaves a disabled module just as unavailable). Everything else EXPLODES,
   * exactly like {@link queryOptional}: a renamed query, a denied permission or a broken handler
   * are broken contracts, not absences. And `[]` keeps meaning "installed, nothing to offer", which
   * is a different answer from "not installed" and must stay tellable apart by the caller.
   *
   * **Short-circuit (hub#1211):** same guard as {@link queryOptional} — when `installedModules`
   * PROVES the owner is absent, this returns `undefined` without ever calling the transport.
   */
  async queryAllOptional<T = unknown>(name: string, params: ListParams = {}): Promise<T[] | undefined> {
    if (this.isKnownAbsent(name)) return undefined;
    try {
      return await this.queryAll<T>(name, params);
    } catch (e) {
      if (e instanceof ErploraError && (e.code === 'module_not_installed' || e.code === 'module_inactive')) return undefined;
      throw e;
    }
  }
  /**
   * Command dispatch, with the honest verdict of hub#906 on top of the transport:
   *
   * When the transport itself failed ({@link SERVER_UNAVAILABLE} — the hub died mid-request, the
   * proxy answered its 502 page, the network dropped), the action **may have committed** before
   * the answer was lost, so the caller gets an {@link UnknownOutcomeError} whose `message` is the
   * localized «we can't tell — check before trying again» sentence, and the shell's notifier
   * (wired to the global toast in `apps/web/src/lib/runtime.ts`) is told once as the default net —
   * a module that renders nothing still leaves the cashier with a verdict instead of a raw
   * exception. Domain refusals (`permission_denied`, `requires_elevation`, …) pass untouched: the
   * hub answered, the outcome is known, and the module orients by the code as always. Queries are
   * NOT captured (see {@link query}): a read that failed did nothing, and toasting every failed
   * dashboard poll would bury the one toast that matters.
   *
   * A screen that resolves the doubt itself passes `{ resolvesOutcome: true }` (hub#2375): the
   * verdict is thrown all the same, only the toast is skipped for that call.
   */
  command<T = unknown>(name: string, payload?: Record<string, unknown>, opts: CommandOptions = {}): Promise<T> {
    return (this.transport.command(name, payload) as Promise<T>).catch((e: unknown) => {
      // The verdict is hub#2320's shared one; `resolvesOutcome` (hub#2375) only withholds the toast.
      throw unknownOutcome(e, this.locale, opts.resolvesOutcome === true ? undefined : this.opts.notifier);
    });
  }
  /**
   * Command a una integración **OPCIONAL** (ADR-0127, simétrica a {@link queryOptional} —
   * hub#1428): el módulo dueño puede no estar instalado en este hub. `combos` (`depends_on: []`)
   * da de alta un producto en `inventory` desde su propio selector SOLO si `inventory` está.
   * Devuelve `undefined` **únicamente** ante `module_not_installed`/`module_inactive` (el mismo
   * par que `queryOptional`, ADR-0128); el llamador decide el default.
   *
   * Cualquier otra causa EXPLOTA igual que en {@link command}: un command inexistente en un
   * módulo presente, un permiso denegado, un handler roto, o el verdict `SERVER_UNAVAILABLE` de
   * {@link UnknownOutcomeError} (hub#906) — que NO es una ausencia, es "no sabemos si se
   * escribió", y perdonarlo le mentiría al llamante que no pasó nada.
   *
   * **Diseñada para acciones que el llamante puede ABANDONAR limpiamente si el módulo falta**
   * (el alta rápida de `combos` no es un paso de una cadena que ya asumió la escritura hecha).
   * Y no hay ventana de carrera que resolver: el runtime resuelve "¿existe el módulo?" DENTRO de
   * la misma transacción que la escritura, antes de tocar la BD (igual que en
   * `queries::execute_page`) — así que `undefined` significa siempre "no se escribió nada",
   * nunca "se escribió y no lo sabemos".
   *
   * **Short-circuit (hub#1211):** cuando `installedModules` PRUEBA que el módulo dueño está
   * ausente, esto devuelve `undefined` sin llamar al transporte — el intento de escritura ni
   * siquiera se dispara. El namespace del core `hub.*` nunca se corta en corto (nunca está
   * ausente, ver {@link isKnownAbsent}).
   */
  async commandOptional<T = unknown>(
    name: string,
    payload?: Record<string, unknown>,
    opts: CommandOptions = {},
  ): Promise<T | undefined> {
    if (this.isKnownAbsent(name)) return undefined;
    try {
      return await this.command<T>(name, payload, opts);
    } catch (e) {
      // `module_inactive` (cascada ADR-0128) equivale a ausencia: un módulo desactivado no está
      // disponible, y el consumidor OBLIGATORIO nunca pregunta (la cascada lo apagó con su dep).
      if (e instanceof ErploraError && (e.code === 'module_not_installed' || e.code === 'module_inactive')) return undefined;
      throw e;
    }
  }
  /** Suscribe a un evento de dominio; devuelve una función para cancelar. */
  on(event: string, cb: (payload: unknown) => void): () => void {
    return this.transport.subscribe(event, cb);
  }
  /**
   * [`on`] with the hub's [`EventMeta`] (hub#1980): which shell tab caused the event. A transport
   * without frames delivers an empty meta — «no tab known», never a guessed one.
   */
  onEvent(event: string, cb: (payload: unknown, meta: EventMeta) => void): () => void {
    if (this.transport.subscribeWithMeta) return this.transport.subscribeWithMeta(event, cb);
    return this.transport.subscribe(event, (payload) => cb(payload, {}));
  }
  /**
   * SOLO para mostrar/ocultar UI. La seguridad real la revalida Rust en cada call:
   * si el WC se salta este check, el runtime rechaza igual con PermissionDenied.
   * Soporta el wildcard "*" (rol admin) y permisos con namespace de módulo.
   */
  hasPermission(perm: string): boolean {
    const perms = this.opts.permissions?.();
    if (!perms) return false;
    return perms.has('*') || perms.has(perm);
  }
  notify(n: Notification): void {
    this.opts.notifier?.(n);
  }

  /**
   * Idioma activo del shell (ADR-0055). El shell lo persiste en `localStorage('erplora.locale')`
   * al cambiarlo (y emite `erplora:locale-changed`); por defecto `'es'` (el producto nace en
   * España, igual que el i18n del shell). Los Web Components de módulo lo leen para `t()`.
   */
  get locale(): string {
    try {
      return localStorage.getItem('erplora.locale') || 'es';
    } catch {
      return 'es';
    }
  }

  /**
   * Moneda ISO-4217 del HUB (ADR-0059). Global del hub (sin override por usuario; decisión del
   * humano). El shell la inyecta vía `opts.currency` (fuente: `/api/hub/context`, misma que el
   * dashboard/billing). Si no se inyecta, lee la que el shell publica en
   * `globalThis.__erploraCurrency` (mirror de cómo `locale` lee `localStorage`) y, en último
   * término, degrada a `'EUR'`. Los Web Components de módulo la leen para formatear dinero en vez
   * de hardcodear `€`/`EUR`.
   */
  get currency(): string {
    try {
      const injected = this.opts.currency?.();
      if (injected && injected.trim()) return injected.trim().toUpperCase();
      const published = (globalThis as { __erploraCurrency?: string }).__erploraCurrency;
      if (typeof published === 'string' && published.trim()) return published.trim().toUpperCase();
    } catch {
      /* noop — degradación elegante */
    }
    return 'EUR';
  }

  /**
   * La zona horaria IANA del NEGOCIO, ya resuelta (hub#731, hub#1022): `Europe/Madrid`,
   * `Atlantic/Canary`… La inyecta el shell vía `opts.timezone` (fuente: `/api/hub/context`, que el
   * runtime resuelve con `settings::timezone_of`); sin inyección, la que el shell publicó en
   * `globalThis.__erploraTimezone`; en último término, `'UTC'`. Un módulo que agenda NUNCA
   * hardcodea el huso ni lo deduce del navegador: el negocio está donde está, aunque el cliente
   * viaje. NO se normaliza a mayúsculas (`currency` sí): los nombres IANA son case-sensitive ante
   * la tzdb y `EUROPE/MADRID` no existe.
   */
  get timezone(): string {
    try {
      const injected = this.opts.timezone?.();
      if (injected && injected.trim()) return injected.trim();
      const published = (globalThis as { __erploraTimezone?: string }).__erploraTimezone;
      if (typeof published === 'string' && published.trim()) return published.trim();
    } catch {
      /* noop — degradación elegante */
    }
    return 'UTC';
  }

  /**
   * The mode of THIS device (hub#358): `shared` (the till at the counter) or `personal` (somebody's
   * own device). Modules use it to pick the friction a flow asks for — e.g. the time clock only
   * checks the geofence on a `personal` device, since the till is already at the shop.
   *
   * **Fails towards the strict mode**, like the shell's `device-mode.ts`: no injected getter, a
   * getter that throws, or anything that is not EXACTLY `'personal'` reads as `'shared'`. It is a
   * friction hint, never a permission — the runtime revalidates every call.
   */
  get deviceMode(): DeviceMode {
    try {
      return this.opts.deviceMode?.() === 'personal' ? 'personal' : 'shared';
    } catch {
      return 'shared';
    }
  }

  /** `Intl.NumberFormat` de moneda con la moneda del hub (o `opts.currency`) y el locale activo. */
  private moneyFmt(opts?: FormatMoneyOptions): Intl.NumberFormat {
    return new Intl.NumberFormat(opts?.locale ?? this.locale, {
      style: 'currency',
      currency: opts?.currency ?? this.currency,
      // hub#1090: CLDR deja sin agrupar los 4 dígitos en español (minimumGroupingDigits=2), pero
      // la regla vinculante del CLAUDE.md raíz es la del sector: agrupar SIEMPRE desde 4 dígitos
      // («1.234,56 €»). `true` es la forma booleana del `'always'` de MDN y la única que tipa
      // contra la lib ES2022 del shell. Este formateador es el que ejecutan los módulos de dinero
      // (`globalThis.erplora.formatMoney`, cableado en el shell) — una sola puerta.
      useGrouping: true,
      ...(opts?.maximumFractionDigits != null
        ? { maximumFractionDigits: opts.maximumFractionDigits }
        : {}),
    });
  }

  /**
   * Formatea un importe en **UNIDADES MÍNIMAS** (entero) con la moneda del hub (ADR-0059/0123).
   * Es la entrada canónica de los Web Components de módulo.
   *
   * **Ya no divide entre 100 a ciegas**: divide entre `10^decimales-de-la-moneda`. En EUR son 2, en
   * **JPY son 0** (`1999` son **1999 ¥**, no 19,99) y en KWD son 3. El `/100` que había clavado aquí
   * era un bug esperando a que alguien pusiera su hub fuera del euro — y la app es gratuita.
   */
  formatMoney(minor: number, opts?: FormatMoneyOptions): string {
    return this.moneyFmt(opts).format(minorToMajor(minor, this.currencyDecimals));
  }

  /**
   * Los **decimales de la moneda del hub** — la escala del dinero. Los inyecta el shell desde
   * `/api/hub/context` (`currency_decimals`), que a su vez los resuelve del registro ISO-4217 o de
   * lo que el hub haya declarado a mano para una moneda que el registro no conozca.
   *
   * Si el shell no los inyecta, se resuelven del código de moneda; y si tampoco, 2. Nunca se asumen
   * a ciegas: asumir 2 en una moneda de 0 decimales es cobrar 100 veces de más.
   */
  get currencyDecimals(): number {
    const injected = this.opts?.currencyDecimals?.();
    if (typeof injected === 'number') return injected;
    const published = (globalThis as { __erploraCurrencyDecimals?: number })
      .__erploraCurrencyDecimals;
    if (typeof published === 'number') return published;
    return decimalsForCurrency(this.currency);
  }

  /**
   * Formatea un importe ya en UNIDADES mayores (euros, no céntimos) con la moneda del hub. Para
   * datos que llegan en unidades (totales de factura, KPIs). Misma resolución de moneda/locale que
   * `formatMoney`.
   */
  formatAmount(units: number, opts?: FormatMoneyOptions): string {
    return this.moneyFmt(opts).format(units || 0);
  }

  /** Atajo de [`eurosToCents`] (la frontera con nombre; ADR-0123). */
  eurosToCents(euros: string | number | undefined): number {
    return eurosToCents(euros);
  }

  /** Atajo de [`centsToEuros`]. */
  centsToEuros(cents: number | undefined): string {
    return centsToEuros(cents);
  }

  /**
   * Traduce una clave del catálogo `ui` del MÓDULO (ADR-0055). `catalog` = `{ <lang>: { ui: {…} } }`
   * (lo importa el WC de sus `locales/*.json`; el bundler lo inlinea en el `dist`). Resuelve por
   * el idioma activo con fallback `locale → 'en' → la clave cruda`. Interpola `{param}`.
   *
   * Uso en el WC (Lit):
   *   import es from '../../locales/es.json'; import en from '../../locales/en.json';
   *   const C = { es, en };
   *   …  ${erplora.t(C, 'ui.addProduct')}  …  ${erplora.t(C, 'ui.greet', { name })}
   */
  t(catalog: Record<string, unknown>, key: string, params?: Record<string, unknown>): string {
    // hub#1570: this is the one call every module Web Component already makes, and the catalogue it
    // hands over carries the module's translated REFUSALS too (`errors`, ADR-0398). Remembering
    // them here is what lets a domain refusal be spoken in the user's language on every screen
    // without any of the 27 module repos adding a line. Indexed once per catalogue object, not per
    // render, and it never touches what `t()` returns.
    rememberRefusalTexts(catalog);
    const dict = (catalog[this.locale] ?? catalog.en ?? {}) as Record<string, unknown>;
    let cur: unknown = dict;
    for (const part of key.split('.')) {
      cur = cur && typeof cur === 'object' ? (cur as Record<string, unknown>)[part] : undefined;
    }
    let out = typeof cur === 'string' ? cur : key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        out = out.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
      }
    }
    return out;
  }
}

/**
 * Selección por flag de arranque (ARQUITECTURA.md §7.6). `http+ws` y `http+sse` comparten el
 * mismo RPC por HTTP y solo difieren en el canal push de eventos (WebSocket vs Server-Sent
 * Events, hub#19); `ws` es alias histórico de `http+ws`. Nombre `http+sse` = decisión del humano.
 */
export type TransportKind = 'http+ws' | 'http+sse' | 'ws';

/**
 * Fábrica: construye el cliente según el flag de transporte del boot. ADR-0050: los DATOS van
 * siempre por HTTP+WS (mismo origen que el runtime) — ya no hay variante `ipc`. El transporte de
 * HARDWARE lo compone el shell aparte (`IpcBridgeTransport` en la app instalada) y lo inyecta;
 * aquí se deja el «sin hardware», que es la verdad en un navegador (ADR-0196 §3).
 */
export function createClient(
  kind: TransportKind,
  deps: { http?: HttpWsOptions; tauri?: TauriBridge } = {},
  clientOpts?: ConstructorParameters<typeof ErploraClient>[1],
): ErploraClient {
  // Datos por HTTP + push por WS (def.) o SSE (hub#19); hardware solo si el shell lo inyecta.
  //
  // El tercer argumento es **equivalente a omitirlo** — el getter `peripherals` construye ese mismo
  // objeto en cuanto alguien lo pide— y por eso ningún test lo mata (superviviente equivalente
  // declarado de la campaña de mutación de hub#339, el único de 20). Se deja explícito a propósito:
  // ESTA línea es la que cableaba `new BridgeClient()`, o sea el sitio exacto por el que el WS a
  // `localhost:12321` entraba aunque el shell hubiera elegido bien su transporte. Verlo aquí es lo
  // que impide que vuelva de tapadillo.
  const httpOpts: HttpWsOptions = { ...deps.http, push: kind === 'http+sse' ? 'sse' : (deps.http?.push ?? 'ws') };
  return new ErploraClient(new HttpWsTransport(httpOpts), clientOpts, new UnavailableBridgeTransport());
}

// ─────────────────────────────────────────────────────────────────────────────
// Hardware local (impresoras de red / cajón). Canal SEPARADO del transporte de
// datos (ARQUITECTURA.md §2.7): el navegador no abre TCP a la impresora; la app
// instalada sí, en proceso (`invoke` → `erplora-peripherals`). ADR-0196 §3 dejó
// ese camino como el ÚNICO: fuera el WS local `:12321` y su superficie.
// ─────────────────────────────────────────────────────────────────────────────

/** Impresora descubierta por el hardware local (`network:{ip}:{port}`). */
export interface BridgePrinter {
  id: string;
  name: string;
  /** Transporte. Siempre `network`. */
  type: string;
  /**
   * Familia de la impresora: `'a4'` (de oficina, anuncia IPP) o `'unknown'`.
   *
   * El puerto 9100 es un tubo tonto: una térmica y una láser A4 escuchan las dos ahí pero hablan
   * idiomas distintos (ESC/POS vs PCL/PostScript), así que mandarle un ticket a una A4 saca folios
   * de basura. Solo el anuncio mDNS `_ipp._tcp` la delata con certeza; lo demás queda `'unknown'`
   * porque **no se adivina**. Opcional: el bridge Kotlin todavía no lo emite.
   */
  category?: string;
  status: string;
  paper_width: number;
  mac?: string;
}

/** Dispositivo del registro persistente del Bridge (con su rol asignado). */
export interface BridgeDevice {
  /**
   * Identidad estable del dispositivo: la MAC normalizada cuando el sistema pudo resolverla por
   * ARP y, si no, el `printer_id` (`network:{ip}:{port}`). Es lo que hay que pasar a
   * `setDeviceRole`/`setDeviceName`/`removeDevice`.
   */
  key: string;
  /**
   * MAC real, solo si ARP la resolvió. **Opcional a propósito**: en Android nunca está
   * disponible (no existe el binario `arp` y `/proc/net/arp` está restringido desde Android 10),
   * y en escritorio falla con VPN, contenedores o firewall. Para identificar el dispositivo usa
   * `key`, no esto.
   */
  mac?: string;
  ip: string;
  port: number;
  name: string;
  role?: string | null;
  type: string;
  first_seen: string;
  last_seen: string;
  status: string;
}

export interface BridgeStatus {
  online: boolean;
  version?: string;
}

/**
 * El `status`/`code` de «el SO bloqueó el escaneo». Un solo literal para los dos transportes
 * (invoke y WS), espejo de `discovery::LOCAL_NETWORK_PERMISSION_DENIED` en `crates/peripherals`.
 */
export const LOCAL_NETWORK_PERMISSION_DENIED = 'local_network_permission_denied';

/**
 * Resultado de un descubrimiento tal y como viaja por el cable. Espejo de `PrinterDiscovery`
 * (`crates/peripherals/src/discovery.rs`).
 */
export type PrinterDiscoveryResult =
  | { status: 'scanned'; printers: BridgePrinter[] }
  | { status: typeof LOCAL_NETWORK_PERMISSION_DENIED; permission?: string };

/**
 * El SO no da acceso a la red local, así que el escaneo NUNCA llegó a correr.
 *
 * Se rechaza en vez de resolver un array vacío a propósito: `printers.length === 0` significaba
 * dos cosas opuestas —«conecta una impresora» y «dale permiso a la app»— y quien llamaba no tenía
 * forma de distinguirlas. Rechazando, todo estado vacío que ya existía sigue siendo honesto sin
 * tocarlo, y quien quiera puede leer `permission` para señalar el interruptor exacto.
 */
export class LocalNetworkPermissionDeniedError extends Error {
  readonly code = LOCAL_NETWORK_PERMISSION_DENIED;
  /** El permiso que el SO denegó, si el transporte lo nombra. */
  readonly permission?: string;

  constructor(permission?: string, message?: string) {
    super(message || `local network access denied${permission ? ` (${permission})` : ''}`);
    this.name = 'LocalNetworkPermissionDeniedError';
    this.permission = permission;
  }
}

/**
 * Desenvuelve el outcome: la lista si el escaneo corrió, un rechazo tipado si no llegó a correr.
 * Nunca convierte «bloqueado» en «vacío» — es justo el paso donde se perdía la diferencia.
 *
 * Acepta también el array pelado, y no por cortesía: la app de escritorio es un **binario
 * instalado** y la PWA que carga se sirve del hub, así que un shell viejo puede seguir devolviendo
 * `BridgePrinter[]`. Leerle un `.printers` inexistente daría `[]` — o sea, esconder impresoras que
 * SÍ se encontraron, la misma mentira mirando al otro lado.
 */
export function printersOrThrow(outcome: PrinterDiscoveryResult | BridgePrinter[]): BridgePrinter[] {
  if (Array.isArray(outcome)) return outcome;
  if (outcome?.status === LOCAL_NETWORK_PERMISSION_DENIED) {
    throw new LocalNetworkPermissionDeniedError(outcome.permission);
  }
  return outcome?.printers ?? [];
}

/**
 * Transporte de hardware (periféricos) — abstracción intercambiable, igual que `ErploraTransport`
 * para los datos. El shell elige la implementación por entorno (app instalada →
 * {@link IpcBridgeTransport} sobre `invoke`; navegador a secas → {@link UnavailableBridgeTransport},
 * ADR-0196 §3). Los módulos consumen esto vía `erplora.peripherals`, sin conocer el transporte.
 */
export interface BridgeTransport {
  detect(timeoutMs?: number): Promise<BridgeStatus>;
  discoverPrinters(): Promise<BridgePrinter[]>;
  getDevices(): Promise<BridgeDevice[]>;
  print(printerId: string, documentType: string, data: Record<string, unknown>, jobId?: string): Promise<void>;
  /**
   * A printer's test sheet.
   *
   * `data` is the SAME envelope `print` takes (hub#1803): `locale` decides the language the paper
   * comes out in (`Locale::from_document`, hub#1159) and `business_name` heads it, exactly as it
   * heads the ticket. It is optional because the installed app can be newer than the module
   * calling it — with no envelope the sheet still prints, in the fallback language, never an error.
   */
  testPrint(printerId: string, data?: Record<string, unknown>): Promise<void>;
  openDrawer(printerId: string, pin?: number): Promise<void>;
  /**
   * Asigna un rol a un dispositivo. `keyOrMac` es el {@link BridgeDevice.key} — o una MAC, que el
   * registro resuelve igual. Usa `printer.mac ?? printer.id`: en Android la MAC nunca existe.
   * (El campo del protocolo JSON se sigue llamando `mac` por compatibilidad.)
   */
  setDeviceRole(keyOrMac: string, role: string): Promise<BridgeDevice[]>;
  /**
   * Adds a network printer by the address the owner TYPED (hub#1924) — the way in when the scan
   * cannot see it: another subnet, an isolated guest Wi-Fi, mDNS blocked by the router.
   *
   * The app connects to `host:port` first and saves ONLY a printer that answers; from then on it
   * is listed by every `discoverPrinters()` and takes a role like any other. Resolves with that
   * printer. Rejects with an {@link ErploraError} whose `code` is {@link INVALID_PRINTER_ADDRESS},
   * {@link PRINTER_UNREACHABLE} or {@link PRINTER_ADD_FAILED} (or `hardware_unavailable` outside
   * the app).
   *
   * **Optional** because a module can run on a hub whose SDK predates it: check that it exists
   * before offering the form.
   *
   * @param host  A dotted IPv4 address, as the printer's self-test sheet prints it.
   * @param port  The raw print port; 9100 when omitted.
   */
  addNetworkPrinter?(host: string, port?: number): Promise<BridgePrinter>;
  /**
   * Muestra una notificación del SISTEMA — la del SO, no un toast dentro de la app.
   *
   * Para eso existe: avisar cuando **nadie está mirando la pantalla**. El caso que la motiva es la
   * comanda — entra un pedido y cocina tiene que enterarse aunque la tablet esté en otra vista o
   * bloqueada. Un toast de la app no sirve ahí.
   *
   * Disponible para CUALQUIER módulo (`erplora.peripherals.notify(...)`), no solo para cocina.
   *
   * Best-effort por contrato: si la plataforma no puede mostrarla —permiso denegado, entorno sin
   * escritorio— **no lanza**. Una notificación que falla no puede tumbar la venta ni la comanda.
   */
  notify(title: string, body: string): Promise<void>;
}

/**
 * El `code` de «en ESTE dispositivo no hay hardware». Un módulo lo compara con esto, nunca con el
 * texto: el mensaje lo pone el shell en el idioma del hub y por tanto cambia; el código no.
 *
 * No es lo mismo que {@link LOCAL_NETWORK_PERMISSION_DENIED}, y confundirlos le cuesta la tarde al
 * usuario: allí hay hardware y falta un permiso que puede conceder; aquí no hay ningún camino a la
 * impresora en este dispositivo y lo que toca es instalar la app.
 */
export const HARDWARE_UNAVAILABLE = 'hardware_unavailable';

/**
 * The three `code`s {@link BridgeTransport.addNetworkPrinter} rejects with (hub#1924). A screen
 * compares against these, never against the message. The first two send the owner to opposite
 * places — fix what they typed, or go look at the printer — which is why they are kept apart.
 */
export const INVALID_PRINTER_ADDRESS = 'invalid_printer_address';
/** Nothing answered on that address and port: the printer was NOT added. */
export const PRINTER_UNREACHABLE = 'printer_unreachable';
/** Anything else — e.g. an installed app older than this hub, that does not know the command. */
export const PRINTER_ADD_FAILED = 'printer_add_failed';

/**
 * El entorno NO tiene acceso al hardware — hoy, un navegador a secas (ADR-0196 §3).
 *
 * Es el precio explícito de retirar el bridge: hasta ahora la PWA llegaba a la impresora por un
 * WebSocket a `localhost:12321` contra un segundo proceso, y con él venían PNA (Private Network
 * Access), el mixed-content de una página `https` abriendo `ws://localhost` y la clave pública con
 * la que se verificaba offline el token de emparejamiento. Queda **un solo** camino: la app
 * instalada, en proceso, por `invoke` ({@link IpcBridgeTransport}).
 *
 * Por qué existe este objeto en vez de dejar `peripherals` sin valor: un `undefined` reventaría en
 * el primer `erplora.peripherals.detect()` de cualquier módulo. Aquí la ausencia de hardware es una
 * **respuesta**, no una excepción de programación.
 *
 * Y por qué `detect()` es la única que no rechaza: es la sonda con la que un módulo decide qué
 * pintar. El módulo `printing` la llama SIN `try/catch` (`erp-printing-settings.ts →
 * refreshBridge`), así que un rechazo ahí le tumbaría la pantalla de ajustes entera en vez de
 * enseñar su estado «sin hardware». Las demás sí rechazan a propósito: resolver como si nada
 * dejaría al TPV dando por impreso un tique que no ha salido.
 */
export class UnavailableBridgeTransport implements BridgeTransport {
  /**
   * @param message  La frase para el usuario. Por defecto va en inglés técnico (para el log,
   *   igual que el resto de errores del SDK); el shell, que es quien tiene i18n, inyecta aquí la
   *   traducida — mismo reparto que en el escaneo bloqueado de hub#338.
   */
  constructor(
    private readonly message = 'hardware unavailable: install the ERPlora app on this device',
  ) {}

  private refuse(): Promise<never> {
    return Promise.reject(new ErploraError(HARDWARE_UNAVAILABLE, this.message));
  }

  async detect(): Promise<BridgeStatus> {
    return { online: false };
  }

  discoverPrinters(): Promise<BridgePrinter[]> {
    return this.refuse();
  }

  getDevices(): Promise<BridgeDevice[]> {
    return this.refuse();
  }

  print(): Promise<void> {
    return this.refuse();
  }

  testPrint(): Promise<void> {
    return this.refuse();
  }

  openDrawer(): Promise<void> {
    return this.refuse();
  }

  setDeviceRole(): Promise<BridgeDevice[]> {
    return this.refuse();
  }

  addNetworkPrinter(): Promise<BridgePrinter> {
    return this.refuse();
  }

  /** Best-effort por contrato: una notificación que no sale no puede tumbar la comanda. */
  async notify(): Promise<void> {}
}

/**
 * Transporte de hardware por Tauri **invoke** — la app instalada (`com.erplora.app`: escritorio,
 * Android, iOS). Delega en el crate `erplora-peripherals` en proceso (ARQUITECTURA.md §2.7); no hay
 * servidor local ni WebSocket. Desde ADR-0196 §3 es el **único** transporte que llega al hardware.
 */
/**
 * Android runtime permission that gates ALL traffic to the LAN (API 37+) — what discovery and
 * printing need. Mirror of `PermissionPolicy.ACCESS_LOCAL_NETWORK` on the Kotlin side.
 */
export const ANDROID_LOCAL_NETWORK_PERMISSION = 'android.permission.ACCESS_LOCAL_NETWORK';

/**
 * Android runtime permission for system notifications (API 33+) — what `notify` needs, and
 * nothing else does (hub#758). Mirror of `PermissionPolicy.POST_NOTIFICATIONS`.
 */
export const ANDROID_NOTIFICATIONS_PERMISSION = 'android.permission.POST_NOTIFICATIONS';

/**
 * Android runtime permission to talk to bonded Bluetooth devices (API 31+) — what a
 * `bluetooth:{mac}` print job and the bonded-printer half of discovery need (ADR-0204, hub#388).
 * Mirror of `PermissionPolicy.BLUETOOTH_CONNECT`.
 */
export const ANDROID_BLUETOOTH_CONNECT_PERMISSION = 'android.permission.BLUETOOTH_CONNECT';

/**
 * The permissions a job to THIS printer is about to use (hub#758/hub#388): RFCOMM for a
 * `bluetooth:{mac}` id, the LAN for everything else. Naming the wrong one would be the same
 * out-of-context dialog hub#758 removed, pointing the other way.
 */
function printerPermissions(printerId: string): string[] {
  return printerId.startsWith('bluetooth:')
    ? [ANDROID_BLUETOOTH_CONNECT_PERMISSION]
    : [ANDROID_LOCAL_NETWORK_PERMISSION];
}

export class IpcBridgeTransport implements BridgeTransport {
  constructor(private readonly tauri: TauriBridge) {}

  /**
   * Ensures the runtime permissions an operation is ABOUT to use — and only those (hub#758).
   *
   * Declaring them in the manifest is **not enough**: `ACCESS_LOCAL_NETWORK` (Android 17+) and
   * `POST_NOTIFICATIONS` (Android 13+) are granted at runtime, and their absence fails
   * **silently** — discovery returns `[]` and notifications never show, with no error anywhere.
   * Verified on the API 37 emulator.
   *
   * The request carries a SCOPE on purpose. Asked without one, the plugin used to request its
   * whole batch: tapping «Re-scan» popped the local-network dialog and then, with no visible
   * relation to anything, the notifications one — an opportunistic-looking ask the user rightly
   * denies. Each operation now names what it needs; the notifications dialog belongs to the
   * first flow that actually notifies.
   *
   * Idempotent on the native side: already granted means no dialog, so asking before every scan
   * costs the user nothing.
   *
   * Never propagates: a «no» from the user is an answer, not a failure. Without a printer the
   * till has to keep selling, and without notices the kitchen order still has to print.
   */
  private async ensurePermissions(permissions: string[]): Promise<void> {
    try {
      await this.tauri.invoke('plugin:erplora-android|request_permissions', { permissions });
    } catch {
      // On desktop the command has nothing to ask; on Android, the user said no. Carry on.
    }
  }

  async detect(): Promise<BridgeStatus> {
    try {
      const v = (await this.tauri.invoke('erplora_bridge_status', {})) as { version?: string };
      return { online: true, version: v?.version };
    } catch {
      return { online: false };
    }
  }

  /**
   * Re-escanea la red. Rechaza con {@link LocalNetworkPermissionDeniedError} si el SO no dio
   * permiso: ahí no hay lista vacía que devolver, hay una razón — y una lista vacía mandaría al
   * usuario a buscar una impresora que lleva encendida todo el rato (hub#338).
   */
  async discoverPrinters(): Promise<BridgePrinter[]> {
    // Both printer permissions: on Android the shell sweeps the LAN AND lists bonded Bluetooth
    // printers (ADR-0204). Still not the notifications one — that dialog has its own context.
    await this.ensurePermissions([
      ANDROID_LOCAL_NETWORK_PERMISSION,
      ANDROID_BLUETOOTH_CONNECT_PERMISSION,
    ]);
    const outcome = (await this.tauri.invoke('erplora_discover_printers', {})) as
      | PrinterDiscoveryResult
      | BridgePrinter[];
    return printersOrThrow(outcome);
  }

  getDevices(): Promise<BridgeDevice[]> {
    return this.tauri.invoke('erplora_get_devices', {}) as Promise<BridgeDevice[]>;
  }

  /**
   * Prints. Asks for the permission FIRST, exactly like discovery does (hub#337).
   *
   * Scanning used to be the only operation that asked, but a till hardly ever scans: the printer
   * is assigned to a role once and remembered, so a freshly installed device goes install → sell
   * → print with no discovery anywhere in it. The job leaves through a TCP socket on the LAN,
   * which Android blocks below the API level: it times out, the ticket never comes out, and
   * nothing is reported anywhere.
   */
  async print(
    printerId: string,
    documentType: string,
    data: Record<string, unknown>,
    jobId?: string,
  ): Promise<void> {
    await this.ensurePermissions(printerPermissions(printerId));
    await this.tauri.invoke('erplora_print', { printerId, documentType, data, jobId: jobId ?? null });
  }

  async testPrint(printerId: string, data?: Record<string, unknown>): Promise<void> {
    await this.ensurePermissions(printerPermissions(printerId));
    // `null`, not `undefined`: `undefined` disappears when the args are serialised, and the Rust
    // side declares `Option<Value>` — an explicit null is the shape that arrives as `None`.
    await this.tauri.invoke('erplora_test_print', { printerId, data: data ?? null });
  }

  /** The drawer opens through the printer's ESC/POS kick — so it goes over the local network too. */
  async openDrawer(printerId: string, pin = 2): Promise<void> {
    await this.ensurePermissions(printerPermissions(printerId));
    await this.tauri.invoke('erplora_open_drawer', { printerId, pin });
  }

  setDeviceRole(keyOrMac: string, role: string): Promise<BridgeDevice[]> {
    return this.tauri.invoke('erplora_set_device_role', { mac: keyOrMac, role }) as Promise<
      BridgeDevice[]
    >;
  }

  /**
   * The refusal keeps the shell's `code` (hub#1924): `{code, message}` from an app that knows the
   * command, a bare string from one that does not — the latter becomes {@link PRINTER_ADD_FAILED}
   * so the page still has a code to branch on.
   */
  async addNetworkPrinter(host: string, port = 9100): Promise<BridgePrinter> {
    // The connect crosses the LAN, which Android gates at runtime like printing does (hub#337).
    await this.ensurePermissions([ANDROID_LOCAL_NETWORK_PERMISSION]);
    try {
      return (await this.tauri.invoke('erplora_add_network_printer', { host, port })) as BridgePrinter;
    } catch (e) {
      const refusal = e as { code?: unknown; message?: unknown } | null;
      if (refusal && typeof refusal === 'object' && typeof refusal.code === 'string') {
        throw new ErploraError(refusal.code, String(refusal.message ?? refusal.code));
      }
      throw new ErploraError(PRINTER_ADD_FAILED, e instanceof Error ? e.message : String(e));
    }
  }

  /** Notificación del SO por el shell (que ES el bridge en Tauri). Best-effort: no propaga fallos. */
  async notify(title: string, body: string): Promise<void> {
    await this.ensurePermissions([ANDROID_NOTIFICATIONS_PERMISSION]);
    try {
      await this.tauri.invoke('erplora_notify', { title, body });
    } catch {
      // best-effort: permiso denegado o plataforma sin soporte no puede romper el flujo que avisa.
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────────────────
// LA FRONTERA EUROS ↔ CÉNTIMOS (ADR-0123)
//
// El dinero es un INTEGER de CÉNTIMOS en toda la pila (ADR-0007), pero un humano teclea EUROS: un
// `<input step="0.01">`, un CSV con el catálogo de un cliente, la etiqueta de un billete. Esa
// conversión es una FRONTERA, y toda frontera tiene que ser **una función con nombre**, no un `*100`
// suelto en medio de un componente.
//
// Hasta ahora no existía aquí, así que cada Web Component se la escribía a mano — y los que se
// olvidaron produjeron los bugs de ×100: un café de 2,20 € importado como producto de **2 céntimos**,
// y un billete de 20 € registrado como **20 céntimos** en el arqueo de caja.
//
// El gemelo en Rust es `erplora_guest_sdk::money::euros_to_cents`, para que el WC y el handler
// coincidan al céntimo.
// ─────────────────────────────────────────────────────────────────────────────────────────

/**
 * **Frontera 1 de 2:** lo que teclea un humano (unidad MAYOR) → **unidades mínimas** (lo que guarda
 * la BD).
 *
 * `decimals` son los de **la moneda del hub** (`erplora.currencyDecimals`), no un 2 fijo. En **JPY
 * son 0**: `1999` se teclea y se guarda como `1999` yenes, no como `199900`. En KWD son 3. Un `*100`
 * clavado aquí **cobra 100 veces mal** en cuanto el hub sale del euro — y la app es gratuita, así
 * que saldrá.
 *
 * `Math.round` no es un adorno: en IEEE-754, `0.29 * 100 = 28.999999999999996`, así que sin él un
 * precio de 0,29 € se guardaría como **28 céntimos**. Basura o vacío → `0`, nunca `NaN` (un `NaN` en
 * una columna `INTEGER` es corrupción silenciosa).
 */
export function majorToMinor(amount: string | number | undefined, decimals: number): number {
  const n = Number(amount);
  return Number.isFinite(n) ? Math.round(n * 10 ** decimals) : 0;
}

/**
 * **Frontera 2 de 2:** unidades mínimas → la unidad mayor que se le pinta a un humano.
 *
 * En EUR divide entre 100; en **JPY no divide** (la unidad mínima ES el yen); en KWD divide entre
 * 1000.
 */
export function minorToMajor(amount: number | undefined, decimals: number): number {
  return (amount ?? 0) / 10 ** decimals;
}

/**
 * EUROS → céntimos. Es `majorToMinor(x, 2)`.
 *
 * **Prefiere `majorToMinor` con `erplora.currencyDecimals`**: esta función asume una moneda de 2
 * decimales, que es exactamente la suposición que rompe en un hub en yenes. Se conserva para los
 * sitios donde la moneda es EUR **por contrato** (la fiscalidad española: VeriFactu).
 */
export function eurosToCents(euros: string | number | undefined): number {
  return majorToMinor(euros, 2);
}

/**
 * CÉNTIMOS → la cadena en EUROS con la que se rellena un `<input step="0.01">` de edición.
 * `undefined` → `''` (campo vacío, no «0.00»: no es lo mismo «sin precio» que «gratis»).
 */
export function centsToEuros(cents: number | undefined): string {
  return cents == null ? '' : (cents / 100).toFixed(2);
}

/**
 * Los decimales de una moneda ISO-4217. **No siempre son 2** — y esa suposición es un bug:
 *
 * * **JPY, KRW…** → **0**. La unidad mínima ES el yen: `1999` son 1999 ¥.
 * * **KWD, BHD, TND…** → **3**.
 * * El resto de las comunes → 2.
 *
 * Espejo del registro de Rust (`erplora_guest_sdk::currency`). Para una moneda que no está aquí, el
 * hub declara sus decimales a mano (`hub_settings.currency_decimals`) y el shell los inyecta; este
 * fallback solo actúa si nadie dijo nada.
 */
const ZERO_DECIMAL = new Set(['BIF','CLP','DJF','GNF','ISK','JPY','KMF','KRW','PYG','RWF','UGX','UYI','VND','VUV','XAF','XOF','XPF']);
const THREE_DECIMAL = new Set(['BHD','IQD','JOD','KWD','LYD','OMR','TND']);
const FOUR_DECIMAL = new Set(['CLF','UYW']);

export function decimalsForCurrency(code: string | undefined): number {
  const c = (code ?? '').trim().toUpperCase();
  if (ZERO_DECIMAL.has(c)) return 0;
  if (THREE_DECIMAL.has(c)) return 3;
  if (FOUR_DECIMAL.has(c)) return 4;
  return 2;
}
