// Identidad de dispositivo para el caso "un hub por dispositivo" (ARQUITECTURA.md §2.9b).
//
// El shell Tauri expone el comando `device_context` (con `withGlobalTauri` → accesible por
// `window.__TAURI__.core.invoke`, sin necesidad de la dependencia npm `@tauri-apps/api`).
// Devuelve un id estable por instalación (persistido en `app_data_dir` por el shell) + el
// `client_type`. En una web-pwa pura no hay Tauri → `null`, y el login va como cliente `hub`
// genérico (comportamiento legacy: un hub por `deployment_mode`).

export interface DeviceContext {
  id: string;
  clientType: 'hub-desktop' | 'hub-local';
}

interface TauriCore {
  invoke?: (cmd: string, args?: unknown) => Promise<unknown>;
}

function tauriCore(): TauriCore | null {
  const g = (window as unknown as { __TAURI__?: { core?: TauriCore } }).__TAURI__;
  return g?.core?.invoke ? g.core : null;
}

/** True si corremos dentro del shell Tauri. */
export function isTauri(): boolean {
  return tauriCore() !== null;
}

/**
 * Invoca un comando Tauri vía el global `window.__TAURI__` (sin la dep npm `@tauri-apps/api`).
 * Devuelve `null` si NO corremos en Tauri (web-pwa) → el llamador degrada con elegancia.
 * Tauri v2 mapea las claves camelCase del objeto a los params snake_case del comando Rust.
 */
export async function invokeTauri<T>(cmd: string, args?: Record<string, unknown>): Promise<T | null> {
  const core = tauriCore();
  if (!core?.invoke) return null;
  return (await core.invoke(cmd, args)) as T;
}

/** Lee la identidad de dispositivo del shell Tauri, o `null` en web-pwa pura. */
export async function getDeviceContext(): Promise<DeviceContext | null> {
  const core = tauriCore();
  if (!core?.invoke) return null;
  try {
    const ctx = (await core.invoke('device_context')) as { id?: string; client_type?: string };
    if (ctx && typeof ctx.id === 'string' && ctx.id) {
      const clientType = ctx.client_type === 'hub-local' ? 'hub-local' : 'hub-desktop';
      return { id: ctx.id, clientType };
    }
  } catch {
    /* ignore — degradar a web */
  }
  return null;
}

/**
 * Cabeceras de identificación para el login. En Tauri manda `X-Client-Type` (desktop/local)
 * + `X-Device-Id` para que el Cloud cree/resuelva el hub de ESTE dispositivo (§2.9b). En web
 * pura cae a `X-Client-Type: hub` (no dispara el registro por dispositivo).
 */
export async function loginHeaders(): Promise<Record<string, string>> {
  const dev = await getDeviceContext();
  if (!dev) return { 'X-Client-Type': 'hub' };
  return { 'X-Client-Type': dev.clientType, 'X-Device-Id': dev.id };
}
