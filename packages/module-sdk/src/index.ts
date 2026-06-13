// @erplora/module-sdk — puente que usan los Web Components (Stencil). ARQUITECTURA.md §7.1, §7.5–7.6.
//
// El transporte es intercambiable y se elige en el boot (RUNTIME_TRANSPORT):
//   - IpcTransport     → Tauri invoke + Tauri events            (backend `single`, local)
//   - HttpWsTransport  → HTTP POST query/command + WS eventos    (backend `cloud`)
// El módulo solo ve la interfaz `ErploraTransport`; nada de su código depende del transporte.
//
// Principio (decisión 2026-05-31): el 90% de la lógica vive en **Rust** (el runtime es la
// autoridad: valida permiso, hub_id, payload y ejecuta). El WC es una mini-app que llama a
// `query`/`command`/`on`; nunca toca la BD ni confía en su propio `hasPermission` para seguridad.

export interface ErploraTransport {
  query(name: string, params?: Record<string, unknown>): Promise<unknown>;
  command(name: string, payload?: Record<string, unknown>): Promise<unknown>;
  subscribe(event: string, cb: (payload: unknown) => void): () => void;
}

export interface Notification {
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
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
  ) {
    super(message);
    this.name = 'ErploraError';
  }
}

/** Sobre de respuesta estándar del server Axum (`crates/server`). */
interface Envelope {
  ok: boolean;
  data?: unknown;
  error?: { code: string; message: string };
}

function unwrap(env: Envelope): unknown {
  if (!env.ok) {
    const e = env.error;
    throw new ErploraError(e?.code ?? 'error', e?.message ?? 'unknown error');
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
    this.ws = new this.WebSocketImpl(this.wsUrl);
    this.ws.onmessage = (ev: MessageEvent) => this.handleFrame(ev.data);
    this.ws.onclose = () => {
      this.pushStarted = false;
      this.ws = undefined;
      // Reabre si aún hay suscriptores (degradación elegante: query/command siguen por HTTP).
      if (this.listeners.size > 0) setTimeout(() => this.ensurePush(), 1000);
    };
  }

  /** SSE: el navegador reconecta solo (con `Last-Event-ID`), no necesitamos reabrir a mano. */
  private ensureSse(): void {
    if (!this.EventSourceImpl) return;
    this.pushStarted = true;
    this.es = new this.EventSourceImpl(this.sseUrl);
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
// Transporte local (Tauri): invoke para RPC + listen para eventos.
// La app Tauri expone `query`/`command` como comandos invoke que llaman al MISMO
// runtime Rust embebido; los eventos llegan por el bus de Tauri. ARQUITECTURA.md §7.6.
// ─────────────────────────────────────────────────────────────────────────────

/** Subconjunto de la API de Tauri que necesita el transporte (inyectable para tests). */
export interface TauriBridge {
  invoke(cmd: string, args: Record<string, unknown>): Promise<unknown>;
  listen(event: string, cb: (e: { payload: unknown }) => void): Promise<() => void>;
}

export class IpcTransport implements ErploraTransport {
  constructor(private readonly tauri: TauriBridge) {}

  async query(name: string, params: Record<string, unknown> = {}): Promise<unknown> {
    const env = (await this.tauri.invoke('erplora_query', { name, params })) as Envelope;
    return unwrap(env);
  }

  async command(name: string, payload: Record<string, unknown> = {}): Promise<unknown> {
    const env = (await this.tauri.invoke('erplora_command', { name, payload })) as Envelope;
    return unwrap(env);
  }

  subscribe(event: string, cb: (payload: unknown) => void): () => void {
    // listen es async; devolvemos un unsub síncrono que espera al handle real.
    let unlisten: (() => void) | undefined;
    let cancelled = false;
    this.tauri
      .listen(event, (e) => cb(e.payload))
      .then((fn) => {
        if (cancelled) fn();
        else unlisten = fn;
      });
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }
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
    } = {},
    bridge?: BridgeTransport,
  ) {
    this.bridge = bridge;
  }

  /**
   * Hardware local (impresoras de red / cajón) — el módulo llama AQUÍ, nunca al Bridge directo.
   * El shell decide el transporte (ws-localhost en web-PWA, invoke en Tauri); el módulo ni se
   * entera. Igual que el WC nunca toca la BD, tampoco toca el Bridge (ARQUITECTURA.md §2.7).
   */
  get peripherals(): BridgeTransport {
    return (this.bridge ??= new BridgeClient());
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
   * Ejecuta una **query de lista** (paginada): aplana `ListParams` y devuelve la página
   * `{rows,total,limit,offset}`. Úsala con `createListController` para el `<data-table>`.
   */
  async queryPage<T = unknown>(name: string, params: ListParams = {}): Promise<Page<T>> {
    const data = (await this.transport.query(name, buildListParams(params))) as Page<T>;
    return data;
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
}

/**
 * Selección por flag de arranque (ARQUITECTURA.md §7.6). `http+ws` y `http+sse` comparten el
 * mismo RPC por HTTP y solo difieren en el canal push de eventos (WebSocket vs Server-Sent
 * Events, hub#19); `ws` es alias histórico de `http+ws`. Nombre `http+sse` = decisión del humano.
 */
export type TransportKind = 'ipc' | 'http+ws' | 'http+sse' | 'ws';

/** Fábrica: construye el cliente según el flag de transporte del boot. */
export function createClient(
  kind: TransportKind,
  deps: { http?: HttpWsOptions; tauri?: TauriBridge } = {},
  clientOpts?: ConstructorParameters<typeof ErploraClient>[1],
): ErploraClient {
  if (kind === 'ipc') {
    if (!deps.tauri) throw new Error('IpcTransport requiere el bridge de Tauri');
    // Datos por invoke + hardware por invoke (el shell Tauri ES el bridge, §2.7).
    return new ErploraClient(new IpcTransport(deps.tauri), clientOpts, new IpcBridgeTransport(deps.tauri));
  }
  // Datos por HTTP + push por WS (def.) o SSE (hub#19); hardware por WS-localhost (Bridge §2.7).
  const httpOpts: HttpWsOptions = { ...deps.http, push: kind === 'http+sse' ? 'sse' : (deps.http?.push ?? 'ws') };
  return new ErploraClient(new HttpWsTransport(httpOpts), clientOpts, new BridgeClient());
}

// ─────────────────────────────────────────────────────────────────────────────
// Bridge de hardware local (impresoras de red / cajón). Canal SEPARADO del
// transporte de datos (ARQUITECTURA.md §2.7): el navegador no abre TCP a la
// impresora, el Bridge sí. La PWA habla con el Bridge en localhost:12321
// (GET /status + WS /ws). En el shell Tauri esto será `invoke` (pendiente).
// ─────────────────────────────────────────────────────────────────────────────

export const BRIDGE_DEFAULT_PORT = 12321;

/** Impresora descubierta por el Bridge (`network:{ip}:{port}`). */
export interface BridgePrinter {
  id: string;
  name: string;
  type: string;
  status: string;
  paper_width: number;
  mac?: string;
}

/** Dispositivo del registro persistente del Bridge (con su rol asignado). */
export interface BridgeDevice {
  mac: string;
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
 * Transporte de hardware (periféricos) — abstracción intercambiable, igual que `ErploraTransport`
 * para los datos. El shell elige la implementación según Axis B (web-PWA → `WsBridgeTransport`
 * sobre `ws://localhost`; Tauri → `IpcBridgeTransport` sobre `invoke`). Los módulos consumen esto
 * vía `erplora.peripherals`, sin conocer el transporte.
 */
export interface BridgeTransport {
  detect(timeoutMs?: number): Promise<BridgeStatus>;
  discoverPrinters(): Promise<BridgePrinter[]>;
  getDevices(): Promise<BridgeDevice[]>;
  print(printerId: string, documentType: string, data: Record<string, unknown>, jobId?: string): Promise<void>;
  testPrint(printerId: string): Promise<void>;
  openDrawer(printerId: string, pin?: number): Promise<void>;
  setDeviceRole(mac: string, role: string): Promise<BridgeDevice[]>;
}

/**
 * Transporte de hardware por **WebSocket** (combo web-PWA). Detección por `GET /status` y
 * comandos por WS (un comando → primer evento esperado). Mismo contrato JSON que el binario Rust
 * `apps/bridge` y `bridge.js`. `BridgeClient` es un alias histórico de `WsBridgeTransport`.
 */
export class BridgeClient implements BridgeTransport {
  private readonly base: string;
  private readonly wsUrl: string;

  constructor(host: string = `localhost:${BRIDGE_DEFAULT_PORT}`) {
    this.base = `http://${host}`;
    this.wsUrl = `ws://${host}/ws`;
  }

  /** ¿Está el Bridge corriendo en este equipo? `GET /status` con timeout corto. */
  async detect(timeoutMs = 800): Promise<BridgeStatus> {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(`${this.base}/status`, { signal: ctrl.signal });
      if (!res.ok) return { online: false };
      const b = (await res.json()) as { ok?: boolean; version?: string };
      return { online: b.ok === true, version: b.version };
    } catch {
      return { online: false };
    } finally {
      clearTimeout(t);
    }
  }

  /** Abre el WS, envía una acción y resuelve con el primer evento de `resolveOn`. */
  private request(
    action: Record<string, unknown>,
    resolveOn: string[],
    rejectOn: string[] = ['error'],
    timeoutMs = 20000,
  ): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
      let ws: WebSocket;
      try {
        ws = new WebSocket(this.wsUrl);
      } catch (e) {
        reject(e as Error);
        return;
      }
      const done = (fn: () => void) => {
        clearTimeout(timer);
        try {
          ws.close();
        } catch {
          /* noop */
        }
        fn();
      };
      const timer = setTimeout(() => done(() => reject(new Error('bridge timeout'))), timeoutMs);
      ws.onmessage = (ev: MessageEvent) => {
        let msg: Record<string, unknown>;
        try {
          msg = JSON.parse(String(ev.data));
        } catch {
          return;
        }
        const event = msg.event as string;
        if (rejectOn.includes(event)) {
          done(() => reject(new Error((msg.error as string) || (msg.message as string) || event)));
        } else if (resolveOn.includes(event)) {
          done(() => resolve(msg));
        }
      };
      ws.onerror = () => done(() => reject(new Error('bridge ws error')));
      ws.onopen = () => ws.send(JSON.stringify(action));
    });
  }

  /** Re-escanea la red (subred 9100 + mDNS) y devuelve las impresoras. */
  async discoverPrinters(): Promise<BridgePrinter[]> {
    const r = await this.request({ action: 'discover_printers' }, ['printers']);
    return (r.printers as BridgePrinter[]) ?? [];
  }

  /** Dispositivos del registro (con sus roles). */
  async getDevices(): Promise<BridgeDevice[]> {
    const r = await this.request({ action: 'get_devices' }, ['devices']);
    return (r.devices as BridgeDevice[]) ?? [];
  }

  /** Página de prueba en la impresora indicada. */
  async testPrint(printerId: string): Promise<void> {
    await this.request({ action: 'test_print', printer_id: printerId }, ['print_complete'], [
      'error',
      'print_error',
    ]);
  }

  /** Imprime un documento (`document_type` + `data`); el Bridge renderiza el ESC/POS. */
  async print(
    printerId: string,
    documentType: string,
    data: Record<string, unknown>,
    jobId?: string,
  ): Promise<void> {
    await this.request(
      { action: 'print', printer_id: printerId, document_type: documentType, data, job_id: jobId ?? null },
      ['print_complete'],
      ['error', 'print_error'],
    );
  }

  /** Abre el cajón por el kick ESC/POS de la impresora. */
  async openDrawer(printerId: string, pin = 2): Promise<void> {
    await this.request({ action: 'open_drawer', printer_id: printerId, pin }, ['drawer_opened']);
  }

  /** Asigna un rol (receipt/kitchen/bar/label) a un dispositivo y devuelve el registro. */
  async setDeviceRole(mac: string, role: string): Promise<BridgeDevice[]> {
    const r = await this.request({ action: 'set_device_role', mac, role }, ['devices']);
    return (r.devices as BridgeDevice[]) ?? [];
  }
}

/** Alias semántico del transporte de hardware por WebSocket (combo web-PWA). */
export { BridgeClient as WsBridgeTransport };

/**
 * Transporte de hardware por Tauri **invoke** (combos Tauri). El shell Tauri delega en el crate
 * `erplora-peripherals` (apps/tauri/README §2.7.1); no hay servidor localhost ni WS. Mismos
 * métodos que `WsBridgeTransport`, así que el módulo no distingue el transporte.
 */
export class IpcBridgeTransport implements BridgeTransport {
  constructor(private readonly tauri: TauriBridge) {}

  async detect(): Promise<BridgeStatus> {
    try {
      const v = (await this.tauri.invoke('erplora_bridge_status', {})) as { version?: string };
      return { online: true, version: v?.version };
    } catch {
      return { online: false };
    }
  }

  discoverPrinters(): Promise<BridgePrinter[]> {
    return this.tauri.invoke('erplora_discover_printers', {}) as Promise<BridgePrinter[]>;
  }

  getDevices(): Promise<BridgeDevice[]> {
    return this.tauri.invoke('erplora_get_devices', {}) as Promise<BridgeDevice[]>;
  }

  async print(
    printerId: string,
    documentType: string,
    data: Record<string, unknown>,
    jobId?: string,
  ): Promise<void> {
    await this.tauri.invoke('erplora_print', { printerId, documentType, data, jobId: jobId ?? null });
  }

  async testPrint(printerId: string): Promise<void> {
    await this.tauri.invoke('erplora_test_print', { printerId });
  }

  async openDrawer(printerId: string, pin = 2): Promise<void> {
    await this.tauri.invoke('erplora_open_drawer', { printerId, pin });
  }

  setDeviceRole(mac: string, role: string): Promise<BridgeDevice[]> {
    return this.tauri.invoke('erplora_set_device_role', { mac, role }) as Promise<BridgeDevice[]>;
  }
}
