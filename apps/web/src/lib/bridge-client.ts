// Sonda de hardware local + URLs de descarga que aún usan las pantallas de Sistema y Panel.
//
// 🪦 **Lo que ya no está** (ADR-0196, ejecutado en hub#340): el Bridge standalone. Con él se fueron
// el canal `WS /ws` de `localhost:12321`, su **token de emparejamiento** (`localStorage` +
// `?token=` en la URL del WebSocket, la única vía por la que un `WebSocket` de navegador podía
// presentar credenciales) y el refresco cada 12 min contra `GET /api/bridge/token`. hub#339 había
// quitado ya el único cliente que presentaba ese token; el refresco siguió vivo hasta aquí, y una
// credencial que nadie lee no es peso muerto: es un secreto con caducidad y sin dueño.
//
// El acceso al hardware vive hoy en la **app instalada** (`erplora.peripherals` → `invoke`
// in-process, sin puerto local y sin token). Lo que queda en este fichero es la sonda `GET /status`
// y el enlace de descarga:
//
// ⚠️ Ambos siguen mirando al producto retirado y tienen issue propia — **no se arreglan aquí**:
//   - `detectBridge()` pregunta a `:12321`, donde ya no escucha nadie, así que dentro de la app
//     instalada contesta `{online:false}` aunque haya impresora → **hub#524** (la pregunta debe ir
//     por la misma puerta que los módulos, `getClient().peripherals.detect()`).
//   - `bridgeDownloadUrl()` apunta a `/bridge/download/`, que sirve el binario del Bridge en vez de
//     la app → **hub#507** (repuntar a `/app/download/`, que el Cloud ya sirve desde saas#1242).

import { config } from './config';

/** Host del Bridge local (retirado). Lo conserva la sonda de `detectBridge` hasta hub#524. */
export const BRIDGE_HOST = 'http://localhost:12321';

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
