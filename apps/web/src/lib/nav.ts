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
  /** Nombre del icono ion-icon (los manifests usan iconos por nombre). */
  icon: string;
}

/** Entradas de menú de los módulos instalados (sección "Módulos" del shell). */
export const moduleNav = ref<ModuleNavItem[]>([]);

/** (Re)carga las entradas de menú leyendo los manifests instalados. No lanza. */
export async function refreshModuleNav(): Promise<void> {
  try {
    const entries = await loadMenu();
    moduleNav.value = entries.map((e) => ({
      path: `/m/${e.moduleId}`,
      label: e.nav.label,
      icon: e.nav.icon ?? 'cube-outline',
    }));
  } catch {
    // Sin runtime/manifests todavía: deja la lista como está (no rompe el shell).
  }
}
