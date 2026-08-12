// Navegación de módulos del shell: estado reactivo compartido entre el shell (App.vue, que
// pinta la sección "Módulos" en el menú) y las vistas que cambian qué hay instalado
// (AppsPage, al recibir el evento WS `module.installed`).
//
// Las entradas salen del RUNTIME (`GET /api/navigation` vía module-loader.loadMenu): los módulos
// instalados y activos que reporta el runtime, no un set hardcodeado.
// `refreshModuleNav()` recarga (p.ej. tras instalar/activar un módulo).
import { ref } from 'vue';
import { loadMenu } from './module-loader';
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
