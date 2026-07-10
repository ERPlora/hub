// Cliente del Bridge local (combo cloud + web-PWA). ARQUITECTURA.md §2.7.
//
// El navegador NO puede abrir TCP crudo al puerto 9100 de la impresora; el Bridge sí. La PWA
// detecta el Bridge en `localhost:12321` (GET /status, timeout corto) y, cuando no está, ofrece
// descargarlo desde el Cloud Portal (`/bridge/download/<platform>/`, que redirige a S3 latest).
//
// El protocolo WS lo sirve el binario Rust `hub/apps/bridge` (mismo contrato JSON que el crate
// `crates/peripherals`). Este módulo es solo detección + URLs de descarga; el canal WS de
// comandos/eventos (print/open_drawer/…) se añadirá con el transporte de hardware del module-sdk.

import { config } from './config';

/** Host del Bridge local. Puerto fijo `BRIDGE_WS_PORT` (crates/peripherals/src/lib.rs). */
export const BRIDGE_HOST = 'http://localhost:12321';

/** Clave de `localStorage` donde la app guarda el token de emparejamiento del Bridge. */
const BRIDGE_TOKEN_KEY = 'erplora.bridge.token';

/**
 * Token de emparejamiento guardado, o `null` si aún no se emparejó (ADR-0050 §seguridad).
 * El Bridge muestra el código una vez al arrancar; el usuario lo introduce en Ajustes → Bridge,
 * que llama a {@link setBridgeToken}. El token NO es necesario para `GET /status` (abierto), solo
 * para abrir el canal `WS /ws` que maneja hardware.
 */
export function getBridgeToken(): string | null {
  try {
    const t = localStorage.getItem(BRIDGE_TOKEN_KEY);
    return t && t.trim() ? t.trim() : null;
  } catch {
    return null; // localStorage no disponible (SSR / modo restringido)
  }
}

/** Guarda (o borra, con `null`) el token de emparejamiento del Bridge. Lo llama la UI de Ajustes. */
export function setBridgeToken(token: string | null): void {
  try {
    if (token && token.trim()) localStorage.setItem(BRIDGE_TOKEN_KEY, token.trim());
    else localStorage.removeItem(BRIDGE_TOKEN_KEY);
  } catch {
    /* localStorage no disponible: no-op */
  }
}

/**
 * URL del canal WebSocket del Bridge (`ws://localhost:12321/ws`) con el token de emparejamiento
 * como query param (`?token=…`) — única vía por la que un `WebSocket` de navegador puede presentar
 * credenciales (no puede fijar cabeceras). La consumirá el transporte de hardware cuando se cablee
 * (hoy `bridge-client.ts` solo hace detección). Sin token emparejado, el Bridge responderá 401.
 */
export function bridgeWsUrl(): string {
  const ws = BRIDGE_HOST.replace(/^http/, 'ws');
  const token = getBridgeToken();
  return token ? `${ws}/ws?token=${encodeURIComponent(token)}` : `${ws}/ws`;
}

/**
 * Pide al **runtime** el token dedicado del Bridge (`GET /api/bridge/token`) y lo guarda, para que
 * el `BridgeClient` del SDK lo presente. El runtime firma la llamada al SaaS con su `cloud_api_token`
 * (nunca expuesto al navegador) y devuelve un JWT `aud=erplora-bridge` + `hub_id` (exp corto) que el
 * Bridge verifica offline contra la clave pública del SaaS (ADR-0050 §2.7). Ruta RELATIVA a propósito
 * (mismo origen que /api; evita un import circular con `runtime.ts`). `true` si se guardó un token.
 */
export async function refreshBridgeToken(): Promise<boolean> {
  try {
    const res = await fetch('/api/bridge/token', { headers: { accept: 'application/json' } });
    if (!res.ok) return false;
    const body = (await res.json()) as { token?: string };
    if (body.token && body.token.trim()) {
      setBridgeToken(body.token);
      return true;
    }
    return false;
  } catch {
    return false; // runtime no enrolado / offline: el hardware degrada, no rompe el arranque
  }
}

/** TTL del bridge-token = 15 min; refrescamos con margen (12 min) para no caducar en mitad del turno. */
const BRIDGE_TOKEN_REFRESH_MS = 12 * 60 * 1000;
let bridgeRefreshTimer: ReturnType<typeof setInterval> | undefined;

/**
 * Mantiene fresco el token del Bridge: lo pide una vez y luego cada 12 min (< TTL de 15). Idempotente
 * (un solo timer). Lo arranca el shell en el boot; el `BridgeClient` del SDK lee el token guardado en
 * cada conexión, así el refresco surte efecto sin recrear el cliente.
 */
export function startBridgeTokenRefresh(): void {
  void refreshBridgeToken();
  if (bridgeRefreshTimer) return;
  bridgeRefreshTimer = setInterval(() => void refreshBridgeToken(), BRIDGE_TOKEN_REFRESH_MS);
}

/** Plataformas de descarga expuestas por el Cloud (macOS es solo desarrollo local → fuera). */
export type BridgePlatform = 'windows' | 'linux' | 'android';

/** Resultado de la sonda de estado del Bridge. */
export interface BridgeStatus {
  online: boolean;
  /** Versión reportada por `GET /status` cuando está online. */
  version?: string;
}

/**
 * Detecta si el Bridge está corriendo en este equipo.
 * Hace `GET http://localhost:12321/status` con un timeout corto (el Bridge responde al instante;
 * si no hay nadie escuchando, abortamos rápido para no bloquear la UI).
 */
export async function detectBridge(timeoutMs = 800): Promise<BridgeStatus> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BRIDGE_HOST}/status`, {
      signal: controller.signal,
      // El Bridge permite CORS (`*`); pedimos JSON.
      headers: { accept: 'application/json' },
    });
    if (!res.ok) return { online: false };
    const body = (await res.json()) as { ok?: boolean; version?: string };
    return { online: body.ok === true, version: body.version };
  } catch {
    // Abort por timeout, conexión rechazada (no instalado), o respuesta no-JSON.
    return { online: false };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * URL de descarga del Bridge para una plataforma, servida por el Cloud Portal.
 * El endpoint del Cloud (`apps/public/bridge`) redirige al S3 `bridge/latest/<fichero>`,
 * así que siempre se descarga la última versión publicada por el CI.
 */
export function bridgeDownloadUrl(platform: BridgePlatform): string {
  const base = config.cloudApiUrl.replace(/\/+$/, '');
  return `${base}/bridge/download/${platform}/`;
}
