// Branding del hub: logo de marca con override por tenant + fallback OFFLINE.
//
// Comportamiento (pedido por el humano): un hub puede tener un logo PROPIO subido por su
// dueño; si no existe, se muestra el logo de ERPlora. El logo por defecto se sirve **LOCAL**
// (`/icons/logo.png`, horneado en la app — byte-idéntico al de erplora.com/static/img/logo.png)
// para que funcione SIN conexión a internet, tanto en local (Tauri) como en PWA. Nunca se
// referencia la URL remota de erplora.com como fuente del logo por defecto.
//
// La ENTREGA del logo personalizado (de dónde sale su URL: hoy el Cloud guarda
// `hubs/<hub_id>/store/logo.png` en S3) es una decisión de contrato del runtime/Cloud
// — columna del humano (ARQUITECTURA.md §2). Cuando se cablee, basta con llamar a
// `setHubLogo(url)` en el boot; la UI ya lo consume con fallback automático al logo local
// si la URL remota falla o el dispositivo está offline.

import { computed, ref } from 'vue';

/**
 * Logo de ERPlora por defecto. Servido LOCAL desde `public/icons/logo.png` (offline-safe).
 * Las rutas de assets de la app son absolutas a la raíz (no hay `base` de Vite — ver index.html
 * y manifest.webmanifest), así que `/icons/logo.png` resuelve igual en dev, PWA y Tauri.
 */
export const DEFAULT_HUB_LOGO = '/icons/logo.png';

const _customLogo = ref<string | null>(null);

/** URL del logo a mostrar: el personalizado del hub si existe, si no el de ERPlora (local). */
export const hubLogo = computed<string>(() => _customLogo.value ?? DEFAULT_HUB_LOGO);

/**
 * Fija (o limpia) el logo personalizado del hub. Lo llama el boot cuando el backend entregue
 * la URL del logo del tenant; con `null`/vacío la UI vuelve al logo de ERPlora local.
 */
export function setHubLogo(url: string | null | undefined): void {
  _customLogo.value = url && url.trim() ? url.trim() : null;
}
