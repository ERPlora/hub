// Bootstrap del transporte hacia el runtime local (Axum) del Hub.
//
// Decisión del humano (3): data-path LOCAL end-to-end primero → hablamos con el runtime
// Axum local (default http://127.0.0.1:8787), config-driven vía VITE_RUNTIME_URL para que
// pueda apuntar al Cloud más adelante. ARQUITECTURA.md §7.5–7.6.
//
// El hub_id NO se elige en UI (decisión 2): se obtiene del runtime en el boot
// (`GET /api/hub/context`) y se usa como X-Hub-Id en TODAS las llamadas.
//
// Expone:
//   - getClient() singleton (ErploraClient sobre HttpWsTransport)
//   - clientInjectionKey (provide/inject de Vue) para inyectar el cliente a las vistas
//   - bootHubContext() — se llama una vez en main.ts; resuelve hub_id y lo guarda en config
import type { InjectionKey } from 'vue';
import { ErploraClient, HttpWsTransport } from '@erplora/module-sdk';
import { config } from './config';
import { getAccessToken } from './cloud';
import { getHubSession } from './session';

/** Base URL del runtime local del Hub. Config-driven (VITE_RUNTIME_URL). */
export const RUNTIME_URL: string =
  (import.meta.env.VITE_RUNTIME_URL as string | undefined) ?? 'http://127.0.0.1:8787';

/** Respuesta de `GET /api/hub/context` del runtime. */
export interface HubContext {
  hub_id: string;
  user: unknown | null;
}

let _client: ErploraClient | null = null;

/**
 * Cabeceras de auth para cada llamada al runtime: X-Hub-Id (inyectado por deployment, leído
 * del runtime en boot) + Bearer del usuario activo si hay sesión. El runtime Rust revalida.
 */
function runtimeHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  if (config.hubId) h['X-Hub-Id'] = config.hubId;
  // Sesión local del runtime: autoridad de permisos en modo Session (gate de query/command).
  const session = getHubSession();
  if (session) h['X-Hub-Session'] = session;
  // JWT del usuario: fallback hub-scoped (marketplace/install) cuando el hub no está enrolado.
  const token = getAccessToken();
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

/** Singleton del cliente SDK (HTTP RPC + WS eventos) apuntado al runtime local. */
export function getClient(): ErploraClient {
  if (!_client) {
    const transport = new HttpWsTransport({
      baseUrl: RUNTIME_URL,
      headers: runtimeHeaders,
    });
    _client = new ErploraClient(transport);
  }
  return _client;
}

/** Clave de inyección Vue para el cliente del runtime. */
export const clientInjectionKey: InjectionKey<ErploraClient> = Symbol('erplora.client');

/** Respuesta de `POST /api/modules/request-install` del runtime. */
export interface InstallRequestResult {
  ok: boolean;
  module_id: string;
  version: string;
  status: string;
}

/**
 * Pide al runtime que instale (vía marketplace del Cloud) un módulo. El runtime descarga el
 * zip firmado, verifica SHA256 y aplica migraciones; al terminar emite el evento WS
 * `module.installed`. ARQUITECTURA.md §2.2/§4.
 */
export async function requestInstall(moduleId: string, version: string): Promise<InstallRequestResult> {
  const res = await fetch(`${RUNTIME_URL}/api/modules/request-install`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
    body: JSON.stringify({ module_id: moduleId, version }),
  });
  if (!res.ok) throw new Error(`request-install ${moduleId} → ${res.status}`);
  return (await res.json()) as InstallRequestResult;
}

/** Un módulo instalado según el runtime (`GET /api/modules`). `status` = active|inactive. */
export interface InstalledModule {
  id: string;
  name: string;
  status: 'active' | 'inactive';
  version: string;
}

/** Lista los módulos instalados en el runtime (fuente de verdad local, no el catálogo Cloud). */
export async function listInstalledModules(): Promise<InstalledModule[]> {
  const res = await fetch(`${RUNTIME_URL}/api/modules`, { headers: runtimeHeaders() });
  if (!res.ok) throw new Error(`modules → ${res.status}`);
  const env = (await res.json()) as { ok: boolean; data?: InstalledModule[] };
  return env.ok && env.data ? env.data : [];
}

/** Activa / desactiva / desinstala un módulo en el runtime (hot-plug). Lanza si el runtime falla. */
async function moduleAction(id: string, action: 'activate' | 'deactivate' | 'uninstall'): Promise<void> {
  const res = await fetch(`${RUNTIME_URL}/api/modules/${encodeURIComponent(id)}/${action}`, {
    method: 'POST',
    headers: runtimeHeaders(),
  });
  const env = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: { message?: string } };
  if (!res.ok || env.ok === false) {
    throw new Error(env.error?.message ?? `${action} ${id} → ${res.status}`);
  }
}

export const activateModule = (id: string): Promise<void> => moduleAction(id, 'activate');
export const deactivateModule = (id: string): Promise<void> => moduleAction(id, 'deactivate');
export const uninstallModule = (id: string): Promise<void> => moduleAction(id, 'uninstall');

/** Reporte de `POST /api/sync` del runtime (envelope `{ ok, data }`). */
export interface SyncReport {
  /** Filas empujadas hacia la nube. */
  pushed: number;
  /** Filas traídas de la nube. */
  pulled: number;
  /** True si la sync con la nube no está configurada (modo local). */
  disabled?: boolean;
}

/** Envelope crudo que devuelve el runtime para `/api/sync`. */
interface SyncEnvelope {
  ok: boolean;
  data?: SyncReport;
  error?: string;
}

/**
 * Dispara una sincronización con la nube (`POST /api/sync`, hub-scoped). Reusa la base URL y
 * las cabeceras de auth del runtime (X-Hub-Id + Bearer). Sin body. Devuelve el reporte
 * `{ pushed, pulled, disabled? }`; lanza si el transporte falla o el envelope trae `ok:false`.
 */
export async function syncNow(): Promise<SyncReport> {
  const res = await fetch(`${RUNTIME_URL}/api/sync`, {
    method: 'POST',
    headers: runtimeHeaders(),
  });
  if (!res.ok) throw new Error(`sync → ${res.status}`);
  const env = (await res.json()) as SyncEnvelope;
  if (!env.ok || !env.data) {
    throw new Error(env.error ?? 'La sincronización falló');
  }
  return env.data;
}

/** Estado del relay de sync (`GET /api/sync/status`, ADR-0031). */
export interface SyncStatus {
  /** ¿Hay Cloud DB configurada? `false` ⇒ tier local-only (sin sync). */
  configured: boolean;
  /** ¿El último intento de sync conectó con la nube? */
  online: boolean;
  /** Epoch (segundos) del último sync con éxito, o null. */
  last_sync_epoch: number | null;
  pushed: number;
  pulled: number;
  /** Último error, o null. */
  error: string | null;
}

/**
 * Lee el estado del relay de sync (`GET /api/sync/status`, sin auth). Para el indicador
 * online/offline de la UI. No lanza ante fallo de transporte: devuelve un estado "offline".
 */
export async function syncStatus(): Promise<SyncStatus> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/sync/status`);
    if (!res.ok) throw new Error(`status → ${res.status}`);
    const env = (await res.json()) as { ok: boolean; data?: SyncStatus };
    if (!env.ok || !env.data) throw new Error('sin datos');
    return env.data;
  } catch {
    return { configured: false, online: false, last_sync_epoch: null, pushed: 0, pulled: 0, error: null };
  }
}

/**
 * Obtiene el hub_id del runtime (`GET /api/hub/context`) y lo fija en `config.hubId`.
 * Se llama una vez en el boot (main.ts). Si el runtime no responde, deja el fallback
 * (VITE_HUB_ID) que ya trae `config`. No lanza: el boot del shell no debe romperse aquí.
 */
export async function bootHubContext(): Promise<HubContext | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/context`, {
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return null;
    const ctx = (await res.json()) as HubContext;
    if (ctx.hub_id) config.hubId = ctx.hub_id;
    return ctx;
  } catch {
    return null;
  }
}
