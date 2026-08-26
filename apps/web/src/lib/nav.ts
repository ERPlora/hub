// Navegación de módulos del shell: estado reactivo compartido entre el shell (App.vue, que
// pinta la sección "Módulos" en el menú) y las vistas que cambian qué hay instalado
// (AppsPage, al recibir el evento WS `module.installed`).
//
// Las entradas salen del RUNTIME (`GET /api/navigation` vía module-loader.loadMenu): los módulos
// instalados y activos que reporta el runtime, no un set hardcodeado.
// `refreshModuleNav()` recarga (p.ej. tras instalar/activar un módulo).
import { ref } from 'vue';
import { invalidateManifestCache, loadMenu } from './module-loader';
import type { ListLoadState } from './list-load-state';

export interface ModuleNavItem {
  /** Ruta del shell que monta el WC del módulo (`/m/:moduleId`). */
  path: string;
  label: string;
  /**
   * Valor para `<HubIcon :name>`: el SVG inline que hornea el módulo (option-b) o, si no lo trae,
   * el nombre Iconify del manifest. HubIcon (resolveIcon) acepta ambos — NO pre-resolver aquí
   * (pasar un data-URI ya resuelto haría que HubIcon lo re-resolviese y cayera al fallback).
   */
  icon: string;
}

/** Entradas de menú de los módulos instalados (sección "Módulos" del shell). */
export const moduleNav = ref<ModuleNavItem[]>([]);

/**
 * Qué sabe esta lista de su última petición (hub#770).
 *
 * Sin esto, «no lo he preguntado todavía» y «lo pregunté y falló» salían las dos como una lista
 * vacía, y una lista vacía se pinta como «aún no tienes apps» — que es una afirmación sobre el hub,
 * no sobre nosotros. Arranca en `loading` a propósito: el primer pintado del panel ocurre antes de
 * que termine ninguna petición, así que nacer en `ready` sería decirle «no tienes apps» a cada carga
 * en frío. Lo lee `listDisplay` (`lib/list-load-state.ts`).
 */
export const moduleNavState = ref<ListLoadState>('loading');

/** (Re)carga las entradas de menú desde el runtime (`/api/navigation`). No lanza. */
export async function refreshModuleNav(): Promise<void> {
  try {
    const entries = await loadMenu();
    // Un item por MÓDULO (no por entrada de navigation[]): las pestañas internas las
    // pinta ModuleView en su tabbar secundario. Label = nombre del módulo; icono = el
    // de la primera entrada de navegación.
    const byModule = new Map<string, ModuleNavItem>();
    for (const e of entries) {
      if (!byModule.has(e.moduleId)) {
        byModule.set(e.moduleId, {
          path: `/m/${e.moduleId}`,
          label: e.moduleName,
          icon: e.iconSvg ?? e.nav.icon ?? '',
        });
      }
    }
    moduleNav.value = [...byModule.values()];
    moduleNavState.value = 'ready';
  } catch {
    // Sin runtime/manifests todavía, o una sesión revocada (401): la lista se queda como estaba —
    // el último listado válido sigue siendo la mejor respuesta— pero se DICE que falló, para que
    // quien la pinta no confunda «no pude preguntar» con «este hub no tiene apps».
    moduleNavState.value = 'error';
  }
}

/**
 * Lo mismo, pero para cuando ha cambiado el CONJUNTO instalado (hub#1099) — instalar un módulo
 * desde /apps, desde el drawer del asistente, desde otro dispositivo o al importar un blueprint.
 *
 * Los `module.json` se leen UNA vez por sesión: con 25 módulos, releerlos en cada navegación
 * costaba ~1,6 MB por montaje y dejaba el ritmo en reposo creciendo hasta ~75 req/s. El precio de
 * esa caché es que alguien tiene que olvidarla cuando deja de ser verdad, y este es el único
 * momento en que eso pasa sin recargar la página.
 *
 * Las dos mitades van JUNTAS a propósito: una nav nueva con los manifests viejos describe un hub
 * que no existe —widgets (ADR-0054), slots (ADR-0043), `chrome` y `protects` del conjunto
 * anterior—, y ese fallo no se ve en pantalla, exactamente como el de hub#935.
 *
 * ACTUALIZAR un módulo no pasa por aquí: `reloadForModuleUpdate()` recarga la página entera (un
 * custom element solo se registra una vez) y la recarga se lleva esta caché por delante.
 */
export async function refreshModuleNavAfterInstall(): Promise<void> {
  invalidateManifestCache();
  await refreshModuleNav();
}

let localeWatchInstalled = false;

/**
 * Asks for the navigation again when the effective language changes (hub#781).
 *
 * The names in this list are localized BY THE RUNTIME (`/api/navigation?locale=`, ADR-0055): they
 * come from each module's own `locales/<lang>.json`, so the language is BAKED into the answer, not
 * resolved when it is painted. And the list was fetched exactly once, at boot — before
 * `/api/profile` had answered, so with the shell still on its default `es`.
 *
 * The result: a user whose preference was English saw Home, Employees, Settings and every other
 * chrome string in English, and their apps as `Clientes`, `Mesas`, `Impuestos`, `Inventario` — in
 * the sidebar, in the topbar launcher and on the panel card, which all read this one list.
 *
 * The shell already announced `erplora:locale-changed` on every change. Nobody in the shell was
 * listening: the event existed only to repaint module Web Components.
 *
 * Idempotent: two listeners would mean two fetches per change and a race over which answer lands
 * last — which is exactly how a list ends up in the wrong language after being right for a moment.
 */
export function bootModuleNavLocale(): void {
  if (localeWatchInstalled || typeof window === 'undefined') return;
  localeWatchInstalled = true;
  window.addEventListener('erplora:locale-changed', () => void refreshModuleNav());
}
