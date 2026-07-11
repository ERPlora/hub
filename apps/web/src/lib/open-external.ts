// Abre una URL en el navegador EXTERNO del usuario (deep-link de compra hacia el SaaS, docs…).
//
// - Web/PWA: pestaña nueva con `noopener` (la página abierta no puede tocar `window.opener`).
// - Tauri: el WebView no debe navegar fuera del shell → plugin opener (navegador del SISTEMA).
//   El plugin se importa en diferido para no arrastrar `@tauri-apps/api` al bundle web; requiere
//   además registrar `tauri-plugin-opener` en el lado Rust del shell (apps/tauri/src-tauri).
//
// Detección de Tauri = la de lib/device.ts (`window.__TAURI__.core.invoke`).
import { isTauri } from './device';

/** Abre `url` fuera del shell: navegador del sistema en Tauri, pestaña nueva en web. */
export async function openExternal(url: string): Promise<void> {
  if (isTauri()) {
    const { openUrl } = await import('@tauri-apps/plugin-opener');
    await openUrl(url);
    return;
  }
  window.open(url, '_blank', 'noopener');
}
