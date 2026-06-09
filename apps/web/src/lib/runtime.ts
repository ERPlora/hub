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
