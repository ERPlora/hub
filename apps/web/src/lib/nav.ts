// Navegación de módulos del shell: estado reactivo compartido entre el shell (App.vue, que
// pinta la sección "Módulos" en el menú) y las vistas que cambian qué hay instalado
// (MarketplacePage, al recibir el evento WS `module.installed`).
//
// Las entradas salen de los manifests de los módulos instalados (module-loader.loadMenu).
// `refreshModuleNav()` recarga; `bumpNav()` fuerza una recarga (p.ej. tras instalar).
import { ref } from 'vue';
import { loadMenu } from './module-loader';

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

/** (Re)carga las entradas de menú leyendo los manifests instalados. No lanza. */
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
  } catch {
    // Sin runtime/manifests todavía: deja la lista como está (no rompe el shell).
  }
}
