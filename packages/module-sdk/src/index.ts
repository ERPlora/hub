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

// ─────────────────────────────────────────────────────────────────────────────
// Transporte cloud: HTTP (RPC) + WebSocket (solo push de eventos).
// HTTP para query/command (si cae el socket, las ventas siguen yendo por HTTP);
// WS solo para recibir eventos de dominio. ARQUITECTURA.md §7.6.
// ─────────────────────────────────────────────────────────────────────────────

export interface HttpWsOptions {
  /** Base URL del server del hub (p.ej. "" para mismo origen, o "http://localhost:8787"). */
  baseUrl?: string;
  /** URL del WebSocket de eventos. Por defecto deriva de baseUrl. */
  wsUrl?: string;
  /** Cabeceras de auth (X-Hub-Id, Authorization, …) calculadas por el shell. */
  headers?: () => Record<string, string>;
  /** Inyectable para tests (por defecto el fetch global). */
  fetchImpl?: typeof fetch;
  /** Inyectable para tests (por defecto el WebSocket global). */
  WebSocketImpl?: typeof WebSocket;
}

export class HttpWsTransport implements ErploraTransport {
  private readonly baseUrl: string;
  private readonly wsUrl: string;
  private readonly headers: () => Record<string, string>;
  private readonly fetchImpl: typeof fetch;
  private readonly WebSocketImpl?: typeof WebSocket;

  private ws?: WebSocket;
  private readonly listeners = new Map<string, Set<(p: unknown) => void>>();
  private wsStarted = false;

  constructor(opts: HttpWsOptions = {}) {
    this.baseUrl = opts.baseUrl ?? '';
    this.wsUrl = opts.wsUrl ?? deriveWsUrl(this.baseUrl);
    this.headers = opts.headers ?? (() => ({}));
    this.fetchImpl = opts.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.WebSocketImpl = opts.WebSocketImpl ?? (globalThis as { WebSocket?: typeof WebSocket }).WebSocket;
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
    this.ensureWs();
    return () => {
      set!.delete(cb);
      if (set!.size === 0) this.listeners.delete(event);
    };
  }

  /** Abre el WS (lazy) la primera vez que alguien se suscribe. */
  private ensureWs(): void {
    if (this.wsStarted || !this.WebSocketImpl) return;
    this.wsStarted = true;
    this.ws = new this.WebSocketImpl(this.wsUrl);
    this.ws.onmessage = (ev: MessageEvent) => {
      let msg: { event?: string; payload?: unknown };
      try {
        msg = JSON.parse(typeof ev.data === 'string' ? ev.data : '');
      } catch {
        return;
      }
      if (!msg.event) return;
      const set = this.listeners.get(msg.event);
      if (set) for (const cb of set) cb(msg.payload);
    };
    this.ws.onclose = () => {
      this.wsStarted = false;
      this.ws = undefined;
      // Reabre si aún hay suscriptores (degradación elegante: query/command siguen por HTTP).
      if (this.listeners.size > 0) setTimeout(() => this.ensureWs(), 1000);
    };
  }

  /** Cierra el WS (p.ej. al desmontar el shell). */
  close(): void {
    this.ws?.close();
  }
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
  constructor(
    private readonly transport: ErploraTransport,
    private readonly opts: {
      permissions?: () => ReadonlySet<string>;
      notifier?: (n: Notification) => void;
    } = {},
  ) {}

  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T> {
    return this.transport.query(name, params) as Promise<T>;
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

/** Selección por flag de arranque (ARQUITECTURA.md §7.6). */
export type TransportKind = 'ipc' | 'http+ws' | 'ws';

/** Fábrica: construye el cliente según el flag de transporte del boot. */
export function createClient(
  kind: TransportKind,
  deps: { http?: HttpWsOptions; tauri?: TauriBridge } = {},
  clientOpts?: ConstructorParameters<typeof ErploraClient>[1],
): ErploraClient {
  if (kind === 'ipc') {
    if (!deps.tauri) throw new Error('IpcTransport requiere el bridge de Tauri');
    return new ErploraClient(new IpcTransport(deps.tauri), clientOpts);
  }
  return new ErploraClient(new HttpWsTransport(deps.http), clientOpts);
}
