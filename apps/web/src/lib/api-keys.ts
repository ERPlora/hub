// Cliente de la pestaña «API keys» (Usuarios → API keys) — contrato REST del runtime del Hub.
//
// La API key es un tipo de credencial LOCAL del Hub (ADR-0057, architecture/hub/public-api.md §6):
// un principal no-humano que resuelve al mismo `RequestContext { hub_id, user_id, permissions }`
// que ya consume el dispatcher. Su lifecycle (crear / rotar / revocar) se gestiona como el de un
// usuario, en la sección de Usuarios. El secreto se hashea (argon2id, como el PIN) y se muestra
// UNA sola vez al crear/rotar; después solo se ve el prefijo.
//
// Estas rutas las implementa otro worker en `crates/server`; aquí construimos el cliente EXACTO
// contra el contrato cerrado:
//   GET    /api/keys             → ApiKey[]
//   POST   /api/keys             { name, scope } → ApiKeyCreated (incluye `secret` una vez)
//   POST   /api/keys/{id}/rotate → { secret }
//   DELETE /api/keys/{id}        → revoca (kill-switch)
//
// Reusa el transporte de `runtime.ts`: mismo `RUNTIME_URL` (mismo origen) y `runtimeHeaders()`
// (X-Hub-Id + X-Hub-Session del admin actual). El navegador nunca firma hacia el Cloud: habla solo
// con el runtime local, que es la autoridad de permisos.

import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Permiso de la key sobre un módulo: lectura (queries) y/o escritura (commands). */
export interface ApiKeyScopeEntry {
  /** Id del módulo instalado (p.ej. "inventory", "invoice"). */
  module: string;
  /** Lectura → la key obtiene el `permission` de cada query `expose_api` del módulo. */
  read: boolean;
  /** Escritura → la key obtiene el `permission` de cada command `expose_api` del módulo. */
  write: boolean;
}

/**
 * What a key may do (hub#504, ADR-0057 §7 extended). The SAME model a user has: full access ·
 * read only · write only · or the per-module checkboxes (`custom`).
 *
 * The blanket modes are not sugar over the matrix: they also cover modules installed LATER, which
 * is exactly what a static matrix cannot say.
 */
export type ApiKeyAccess = 'full' | 'read_only' | 'write_only' | 'custom';

/** Una API key tal y como la lista el runtime (`GET /api/keys`). Sin el secreto (solo el prefijo). */
export interface ApiKey {
  id: string;
  /** Etiqueta legible que le dio el admin (p.ej. "Gestoría — facturas"). */
  name: string;
  /** Prefijo visible del token (p.ej. "erpl_live_a1b2…") — lo único que se ve tras crearla. */
  prefix: string;
  /** Scope = matriz módulo × {lectura, escritura}; solo los módulos con algún permiso. */
  scope: ApiKeyScopeEntry[];
  /** Permission mode. Only with `custom` does the `scope` matrix decide. */
  access?: ApiKeyAccess;
  /**
   * `true` = the hub issued it to itself (hub#504): it is what ERPlora reads live changes with.
   * It cannot be rotated or revoked — the runtime refuses — so the screen offers no button.
   */
  system?: boolean;
  /** Estado de la credencial; `active` = utilizable, `revoked` = kill-switch aplicado. */
  status: 'active' | 'revoked';
  /** ISO-8601 de creación. */
  created_at: string;
  /** ISO-8601 del último uso, o `null` si nunca se usó. */
  last_used_at: string | null;
  /** Cuota durable aplicada antes de llegar al dispatcher. */
  rate_limit_per_minute: number;
}

/** Respuesta de `POST /api/keys`: la key creada + el secreto que se muestra UNA sola vez. */
export interface ApiKeyCreated {
  id: string;
  name: string;
  /** Secreto completo (`erpl_live_<id>_<secret>`). No se vuelve a mostrar: cópialo ahora. */
  secret: string;
  prefix: string;
  scope: ApiKeyScopeEntry[];
  access?: ApiKeyAccess;
  rate_limit_per_minute: number;
}

/** Create payload: name + mode + scope matrix (only entries with r and/or w ticked). */
export interface CreateApiKeyInput {
  name: string;
  scope: ApiKeyScopeEntry[];
  /** Permission mode; without it the runtime assumes `custom` (the matrix), as before hub#504. */
  access?: ApiKeyAccess;
  rate_limit_per_minute: number;
}

/** Envelope estándar del runtime (`{ ok, data }`); algunas rutas devuelven el cuerpo directo. */
interface Envelope<T> {
  ok?: boolean;
  data?: T;
  /** `{ code, message }` on every refusal of this door since hub#1700; a bare string before it. */
  error?: unknown;
  code?: unknown;
}

/**
 * A refused call to the API keys door, carrying the runtime's own reason so the screen can show it.
 *
 * The `code` is the only part of a refusal that may be put in front of a person (hub#1697): the
 * `message` beside it is the line whoever wrote `api_keys.rs` left for the log — «API key no
 * encontrada» — and `ApiKeysPanel` translates the code with `localDoorSentence` instead.
 *
 * Until hub#1700 this client threw a bare `Error` built from `error.message` over an `error` that
 * was a **string**, so `.message` was `undefined` and what reached the panel was `keys.revoke →
 * 404`: not a code to branch on, not prose to show. Every refusal came out as «check your
 * connection», whatever it actually was.
 */
export class ApiKeysError extends Error {
  /** The door's stable code (`not_found`, `unauthorized`, `forbidden`, `api_key.system_key`). */
  readonly code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = 'ApiKeysError';
    this.code = code;
  }
}

function text(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() !== '' ? value : undefined;
}

/**
 * The reason a rejection gives, from either shape of the error body.
 *
 * Both are read for the same reason `lib/devices.ts` reads both: the code rides INSIDE `error` on
 * the shared envelope (`err_response`, `auth_rejected`) and beside it on the doors that write the
 * body by hand (`devices.rs`). A hub running an older build sends neither, and then there is no
 * code — `localDoorSentence` falls back to the panel's own line, which is the pre-hub#1700
 * behaviour and not a regression.
 */
function rejection(body: unknown, fallback: string): ApiKeysError {
  const envelope = body as Envelope<unknown> | null;
  const error = envelope?.error;
  const flat = text(envelope?.code);
  if (typeof error === 'string') return new ApiKeysError(error, flat);
  if (error && typeof error === 'object') {
    const { message, code } = error as { message?: unknown; code?: unknown };
    return new ApiKeysError(text(message) ?? fallback, text(code) ?? flat);
  }
  return new ApiKeysError(fallback, flat);
}

/** The body of a refusal, or `null` when the door answered something unreadable. */
async function refusalBody(res: Response): Promise<unknown> {
  return res.json().catch(() => null);
}

/**
 * Tolera ambas formas del runtime: el envelope `{ ok, data }` y el cuerpo plano. Si viene envelope
 * lo desenvuelve; si no, asume que el JSON ES el dato. Lanza con el motivo del runtime si `ok=false`
 * — con su código, porque un `200 {ok:false}` es una negativa igual que un `404`.
 */
function unwrap<T>(body: unknown, fallback: string): T {
  const env = body as Envelope<T>;
  if (env && typeof env === 'object' && ('ok' in env || 'data' in env)) {
    if (env.ok === false) throw rejection(body, fallback);
    return (env.data ?? (body as T)) as T;
  }
  return body as T;
}

/**
 * `fetch` against the door, turning a dead network into an `ApiKeysError` too.
 *
 * Nothing here is optimistic: a revocation that never left the browser must not look like one that
 * happened — the administrator has just cut off a credential they believe is compromised.
 */
async function call(url: string, init: RequestInit, where: string): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (error) {
    throw new ApiKeysError(error instanceof Error ? error.message : `${where} → offline`);
  }
}

/** GET /api/keys → lista de keys del hub (sin secretos). Lanza si el runtime falla. */
export async function listApiKeys(): Promise<ApiKey[]> {
  const res = await call(`${RUNTIME_URL}/api/keys`, { headers: runtimeHeaders() }, 'keys');
  if (!res.ok) throw rejection(await refusalBody(res), `keys → ${res.status}`);
  const data = unwrap<ApiKey[]>(await res.json(), `keys → ${res.status}`);
  return Array.isArray(data) ? data : [];
}

/** POST /api/keys → crea una key y devuelve el secreto (mostrar UNA vez). Lanza si el runtime falla. */
export async function createApiKey(input: CreateApiKeyInput): Promise<ApiKeyCreated> {
  const res = await call(
    `${RUNTIME_URL}/api/keys`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify(input),
    },
    'keys.create',
  );
  const fallback = `keys.create → ${res.status}`;
  if (!res.ok) throw rejection(await refusalBody(res), fallback);
  return unwrap<ApiKeyCreated>(await res.json(), fallback);
}

/** POST /api/keys/{id}/rotate → nuevo secreto (invalida el anterior). Lanza si el runtime falla. */
export async function rotateApiKey(id: string): Promise<{ secret: string }> {
  const res = await call(
    `${RUNTIME_URL}/api/keys/${encodeURIComponent(id)}/rotate`,
    { method: 'POST', headers: runtimeHeaders() },
    'keys.rotate',
  );
  const fallback = `keys.rotate → ${res.status}`;
  if (!res.ok) throw rejection(await refusalBody(res), fallback);
  return unwrap<{ secret: string }>(await res.json(), fallback);
}

/** DELETE /api/keys/{id} → revoca (kill-switch inmediato). Lanza si el runtime falla. */
export async function revokeApiKey(id: string): Promise<void> {
  const res = await call(
    `${RUNTIME_URL}/api/keys/${encodeURIComponent(id)}`,
    { method: 'DELETE', headers: runtimeHeaders() },
    'keys.revoke',
  );
  if (!res.ok) throw rejection(await refusalBody(res), `keys.revoke → ${res.status}`);
}
