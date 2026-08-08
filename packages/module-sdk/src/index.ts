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

export interface ErploraTransport {
  query(name: string, params?: Record<string, unknown>): Promise<unknown>;
  command(name: string, payload?: Record<string, unknown>): Promise<unknown>;
  subscribe(event: string, cb: (payload: unknown) => void): () => void;
}

export interface Notification {
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
}

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
} as const;

export function dataTableLabels(locale = 'es'): Record<string, string> {
  return locale.toLowerCase().startsWith('en') ? DATA_TABLE_LABELS_EN : DATA_TABLE_LABELS_ES;
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
  /** `col -> valor` (eq/like) o `col -> {from,to}` (range). Valores vacíos/null se omiten. */
  filters?: Record<string, unknown>;
  /** Params de **contexto obligatorios** que la query base referencia con su nombre crudo
   *  (p.ej. una sub-lista de hijos: `{ params: { bom_id } }` → bindea `:bom_id`). Se pasan
   *  verbatim al wire, sin prefijo `f_`. */
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

/** Subconjunto del cliente SDK que necesita el controlador (inyectable para tests). */
export interface ListClient {
  queryPage<R = unknown>(name: string, params: ListParams): Promise<Page<R>>;
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
  }

  /** Nº de páginas según el total del servidor (mínimo 1). */
  get pageCount(): number {
    return Math.max(1, Math.ceil(this.total / this.state.pageSize));
  }

  /** (Re)carga la página actual desde el servidor. */
  async load(): Promise<void> {
    const s = this.state;
    const mySeq = ++this.seq;
    this.loading = true;
    this.error = '';
    this.onChange();
    try {
      const page = await this.client.queryPage<T>(this.queryName, {
        limit: s.pageSize,
        offset: s.page * s.pageSize,
        search: s.search,
        sort: s.sort,
        dir: s.dir,
        filters: s.filters,
        params: s.context,
      });
      if (mySeq !== this.seq) return; // llegó una carga más reciente
      this.rows = page.rows ?? [];
      this.total = page.total ?? this.rows.length;
    } catch (e) {
      if (mySeq !== this.seq) return;
      this.rows = [];
      this.total = 0;
      this.error = e instanceof Error ? e.message : 'Error cargando datos';
    } finally {
      if (mySeq === this.seq) {
        this.loading = false;
        this.onChange();
      }
    }
  }

  setPage(page: number): void {
    this.state.page = Math.max(0, page);
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
  ) {
    super(message);
    this.name = 'ErploraError';
  }
}

/** Sobre de respuesta estándar del server Axum (`crates/server`). */
interface Envelope {
  ok: boolean;
  data?: unknown;
  error?: { code: string; message: string; permission?: string };
}

function unwrap(env: Envelope): unknown {
  if (!env.ok) {
    const e = env.error;
    throw new ErploraError(e?.code ?? 'error', e?.message ?? 'unknown error', e?.permission);
  }
  return env.data;
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

  private ws?: WebSocket;
  private es?: EventSource;
  private readonly listeners = new Map<string, Set<(p: unknown) => void>>();
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
  }

  private async post(path: string, body: unknown): Promise<unknown> {
    const res = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...this.headers() },
      body: JSON.stringify(body),
    });
    const env = (await res.json()) as Envelope;
    return unwrap(env);
  }

  query(name: string, params: Record<string, unknown> = {}): Promise<unknown> {
    return this.post('/api/query', { name, params });
  }

  command(name: string, payload: Record<string, unknown> = {}): Promise<unknown> {
    return this.post('/api/command', { name, payload });
  }

  subscribe(event: string, cb: (payload: unknown) => void): () => void {
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
    let msg: { event?: string; name?: string; type?: string; payload?: unknown };
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
    if (set) for (const cb of set) cb(msg.payload ?? msg);
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
// Cliente que usan los Web Components.
// ─────────────────────────────────────────────────────────────────────────────

export class ErploraClient {
  private bridge?: BridgeTransport;

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
    } = {},
    bridge?: BridgeTransport,
  ) {
    this.bridge = bridge;
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
   * Query genérica. Compat: si la query es de **lista** (`{rows,total,…}`), desenvuelve y entrega
   * solo `rows`, para que una vista antigua que aún use `query()` no se rompa al añadir un bloque
   * `list` a su query. Para paginar de verdad (total/página) usa `queryPage`.
   */
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T> {
    return this.transport.query(name, params).then(unwrapPage) as Promise<T>;
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
   */
  async queryOptional<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T | undefined> {
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
    const data = (await this.transport.query(name, buildListParams(params))) as Page<T>;
    return data;
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
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T> {
    return this.transport.command(name, payload) as Promise<T>;
  }
  /** Suscribe a un evento de dominio; devuelve una función para cancelar. */
  on(event: string, cb: (payload: unknown) => void): () => void {
    return this.transport.subscribe(event, cb);
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

  /** `Intl.NumberFormat` de moneda con la moneda del hub (o `opts.currency`) y el locale activo. */
  private moneyFmt(opts?: FormatMoneyOptions): Intl.NumberFormat {
    return new Intl.NumberFormat(opts?.locale ?? this.locale, {
      style: 'currency',
      currency: opts?.currency ?? this.currency,
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
  testPrint(printerId: string): Promise<void>;
  openDrawer(printerId: string, pin?: number): Promise<void>;
  /**
   * Asigna un rol a un dispositivo. `keyOrMac` es el {@link BridgeDevice.key} — o una MAC, que el
   * registro resuelve igual. Usa `printer.mac ?? printer.id`: en Android la MAC nunca existe.
   * (El campo del protocolo JSON se sigue llamando `mac` por compatibilidad.)
   */
  setDeviceRole(keyOrMac: string, role: string): Promise<BridgeDevice[]>;
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

  /** Best-effort por contrato: una notificación que no sale no puede tumbar la comanda. */
  async notify(): Promise<void> {}
}

/**
 * Transporte de hardware por Tauri **invoke** — la app instalada (`com.erplora.app`: escritorio,
 * Android, iOS). Delega en el crate `erplora-peripherals` en proceso (ARQUITECTURA.md §2.7); no hay
 * servidor local ni WebSocket. Desde ADR-0196 §3 es el **único** transporte que llega al hardware.
 */
export class IpcBridgeTransport implements BridgeTransport {
  constructor(private readonly tauri: TauriBridge) {}

  /**
   * Asegura los permisos de RUNTIME antes de tocar el hardware.
   *
   * Declararlos en el manifest **no basta**: `ACCESS_LOCAL_NETWORK` (Android 17+) y
   * `POST_NOTIFICATIONS` (Android 13+) se conceden en runtime, y su ausencia **falla en
   * silencio** — el descubrimiento devuelve `[]` y las notificaciones no salen, sin un solo
   * error. Verificado en el emulador API 37.
   *
   * Es idempotente en el lado nativo: si ya están concedidos no sale ningún diálogo, así que
   * llamarlo antes de cada escaneo no molesta al usuario.
   *
   * Nunca propaga: un «no» del usuario es una respuesta, no un fallo. Sin impresora el TPV
   * tiene que seguir cobrando, y sin avisos la comanda tiene que seguir imprimiéndose.
   */
  private async ensurePermissions(): Promise<void> {
    try {
      await this.tauri.invoke('plugin:erplora-android|request_permissions', {});
    } catch {
      // En escritorio el comando no existe o no hay nada que pedir; en Android, el usuario dijo
      // que no. En ambos casos se sigue.
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
    await this.ensurePermissions();
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
    await this.ensurePermissions();
    await this.tauri.invoke('erplora_print', { printerId, documentType, data, jobId: jobId ?? null });
  }

  async testPrint(printerId: string): Promise<void> {
    await this.ensurePermissions();
    await this.tauri.invoke('erplora_test_print', { printerId });
  }

  /** The drawer opens through the printer's ESC/POS kick — so it goes over the local network too. */
  async openDrawer(printerId: string, pin = 2): Promise<void> {
    await this.ensurePermissions();
    await this.tauri.invoke('erplora_open_drawer', { printerId, pin });
  }

  setDeviceRole(keyOrMac: string, role: string): Promise<BridgeDevice[]> {
    return this.tauri.invoke('erplora_set_device_role', { mac: keyOrMac, role }) as Promise<
      BridgeDevice[]
    >;
  }

  /** Notificación del SO por el shell (que ES el bridge en Tauri). Best-effort: no propaga fallos. */
  async notify(title: string, body: string): Promise<void> {
    await this.ensurePermissions();
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
