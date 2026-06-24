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

/** Una API key tal y como la lista el runtime (`GET /api/keys`). Sin el secreto (solo el prefijo). */
export interface ApiKey {
  id: string;
  /** Etiqueta legible que le dio el admin (p.ej. "Gestoría — facturas"). */
  name: string;
  /** Prefijo visible del token (p.ej. "erpl_live_a1b2…") — lo único que se ve tras crearla. */
  prefix: string;
  /** Scope = matriz módulo × {lectura, escritura}; solo los módulos con algún permiso. */
  scope: ApiKeyScopeEntry[];
  /** Estado de la credencial; `active` = utilizable, `revoked` = kill-switch aplicado. */
  status: 'active' | 'revoked';
  /** ISO-8601 de creación. */
  created_at: string;
  /** ISO-8601 del último uso, o `null` si nunca se usó. */
  last_used_at: string | null;
}

/** Respuesta de `POST /api/keys`: la key creada + el secreto que se muestra UNA sola vez. */
export interface ApiKeyCreated {
  id: string;
  name: string;
  /** Secreto completo (`erpl_live_<id>_<secret>`). No se vuelve a mostrar: cópialo ahora. */
  secret: string;
  prefix: string;
  scope: ApiKeyScopeEntry[];
}

/** Payload de creación: nombre + matriz de scope (solo entradas con r y/o w marcados). */
export interface CreateApiKeyInput {
  name: string;
  scope: ApiKeyScopeEntry[];
}

/** Envelope estándar del runtime (`{ ok, data }`); algunas rutas devuelven el cuerpo directo. */
interface Envelope<T> {
  ok?: boolean;
  data?: T;
  error?: { message?: string };
}

/**
 * Tolera ambas formas del runtime: el envelope `{ ok, data }` y el cuerpo plano. Si viene envelope
 * lo desenvuelve; si no, asume que el JSON ES el dato. Lanza con el mensaje del runtime si `ok=false`.
 */
function unwrap<T>(body: unknown): T {
  const env = body as Envelope<T>;
  if (env && typeof env === 'object' && ('ok' in env || 'data' in env)) {
    if (env.ok === false) throw new Error(env.error?.message ?? 'Error del runtime');
    return (env.data ?? (body as T)) as T;
  }
  return body as T;
}

/** GET /api/keys → lista de keys del hub (sin secretos). Lanza si el runtime falla. */
export async function listApiKeys(): Promise<ApiKey[]> {
  const res = await fetch(`${RUNTIME_URL}/api/keys`, { headers: runtimeHeaders() });
  if (!res.ok) throw new Error(`keys → ${res.status}`);
  const data = unwrap<ApiKey[]>(await res.json());
  return Array.isArray(data) ? data : [];
}

/** POST /api/keys → crea una key y devuelve el secreto (mostrar UNA vez). Lanza si el runtime falla. */
export async function createApiKey(input: CreateApiKeyInput): Promise<ApiKeyCreated> {
  const res = await fetch(`${RUNTIME_URL}/api/keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const env = (await res.json().catch(() => ({}))) as Envelope<unknown>;
    throw new Error(env.error?.message ?? `keys.create → ${res.status}`);
  }
  return unwrap<ApiKeyCreated>(await res.json());
}

/** POST /api/keys/{id}/rotate → nuevo secreto (invalida el anterior). Lanza si el runtime falla. */
export async function rotateApiKey(id: string): Promise<{ secret: string }> {
  const res = await fetch(`${RUNTIME_URL}/api/keys/${encodeURIComponent(id)}/rotate`, {
    method: 'POST',
    headers: runtimeHeaders(),
  });
  if (!res.ok) {
    const env = (await res.json().catch(() => ({}))) as Envelope<unknown>;
    throw new Error(env.error?.message ?? `keys.rotate → ${res.status}`);
  }
  return unwrap<{ secret: string }>(await res.json());
}

/** DELETE /api/keys/{id} → revoca (kill-switch inmediato). Lanza si el runtime falla. */
export async function revokeApiKey(id: string): Promise<void> {
  const res = await fetch(`${RUNTIME_URL}/api/keys/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: runtimeHeaders(),
  });
  if (!res.ok) {
    const env = (await res.json().catch(() => ({}))) as Envelope<unknown>;
    throw new Error(env.error?.message ?? `keys.revoke → ${res.status}`);
  }
}
