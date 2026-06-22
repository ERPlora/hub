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
