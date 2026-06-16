// Fullscreen del shell (chrome — ADR-0048, Nivel 1).
//
// La capacidad la POSEE y maneja el SHELL: una vista de módulo solo la OPTA-IN declarando
// `navigation[].chrome: ["fullscreen"]` en su `module.json` (el módulo no trae el botón ni su
// lógica → respeta ADR-0022). La topbar (AppTopbar) muestra el toggle cuando la vista activa lo
// pide y llama aquí. Usa la Fullscreen API estándar sobre el documento.
import { computed, ref } from 'vue';

const _isFullscreen = ref<boolean>(false);
/** ¿Está el documento en pantalla completa? Reactivo (lo refleja el evento `fullscreenchange`). */
export const isFullscreen = computed<boolean>(() => _isFullscreen.value);

/** ¿El navegador soporta la Fullscreen API? (si no, el shell oculta el botón). */
export function fullscreenSupported(): boolean {
  return typeof document !== 'undefined' && !!document.documentElement.requestFullscreen;
}

/** Entra/sale de pantalla completa (toggle). No lanza: si el navegador la rechaza, no hace nada. */
export async function toggleFullscreen(): Promise<void> {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  } catch {
    // Permiso/gesto denegado por el navegador: el estado real lo fija `fullscreenchange`.
  }
}

// El estado fuente de verdad es del navegador: lo seguimos por evento (cubre también la salida
// con la tecla Esc, que no pasa por `toggleFullscreen`). Listener único a nivel de módulo.
if (typeof document !== 'undefined') {
  document.addEventListener('fullscreenchange', () => {
    _isFullscreen.value = !!document.fullscreenElement;
  });
}
