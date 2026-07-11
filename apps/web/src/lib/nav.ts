// Navegación de módulos del shell: estado reactivo compartido entre el shell (App.vue, que
// pinta la sección "Módulos" en el menú) y las vistas que cambian qué hay instalado
// (AppsPage, al recibir el evento WS `module.installed`).
//
// Las entradas salen del RUNTIME (`GET /api/navigation` vía module-loader.loadMenu): los módulos
// instalados y activos que reporta el runtime, no un set hardcodeado.
// `refreshModuleNav()` recarga (p.ej. tras instalar/activar un módulo).
import { computed, ref } from 'vue';
import { loadMenu } from './module-loader';
import { listInstalledModules } from './runtime';

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

/** Nº de módulos instalados según el RUNTIME. `null` = aún no lo sabemos. */
const _installedCount = ref<number | null>(null);
let _inflight: Promise<void> | null = null;

/**
 * Un hub recién provisionado se despliega vacío (ADR-0087): sin módulos, aterriza en un dashboard en
 * blanco y nada le dice al usuario que su siguiente paso es instalar `setup` desde Apps.
 * Esto lo detecta para que el shell le empuje. Es un EMPUJÓN del core; el wizard vive fuera, en el módulo.
 *
 * Se mide contra `/api/modules` (lo que el runtime tiene instalado), NO contra `moduleNav`: el menú
 * descarta módulos sin entitlement o cuyo `module.json` estático no se sirva, así que un hub bien
 * configurado con los assets caídos acabaría viendo "Configura tu hub". `null` (aún sin respuesta)
 * no es un hub vacío.
 */
export const needsFirstRun = computed<boolean>(() => _installedCount.value === 0);

/**
 * Garantiza que sabemos cuántos módulos hay instalados, memoizando la petición en vuelo. El guard del
 * router la espera: sin esto decidiría antes de tener la respuesta. Si falla, no se fija el contador
 * y la siguiente navegación reintenta (un fallo de red no es un hub vacío).
 */
export async function ensureInstalledModules(): Promise<void> {
  if (_installedCount.value !== null) return;
  _inflight ??= refreshInstalledModules().finally(() => {
    _inflight = null;
  });
  await _inflight;
}

/** (Re)cuenta los módulos instalados. No lanza. Llamar tras instalar/desinstalar. */
export async function refreshInstalledModules(): Promise<void> {
  try {
    _installedCount.value = (await listInstalledModules()).length;
  } catch {
    // Runtime aún sin responder: NO fijamos el contador; se reintenta en la siguiente navegación.
  }
}

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
  } catch {
    // Sin runtime/manifests todavía: deja la lista como está (no rompe el shell).
  }
}
