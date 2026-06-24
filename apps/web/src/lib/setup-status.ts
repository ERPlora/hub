// Subsistema "estado de configuración" (ADR-0063): detecta MÓDULOS instalados que aún NO están
// configurados y los surfacea como alertas (campana de la topbar + banner del dashboard) con un CTA
// a su pantalla de ajustes.
//
// GENÉRICO (el Hub es internacional y no conoce módulos concretos): cada módulo declara su propio
// chequeo en `module.json` (`setup`, ver @erplora/module-types). El shell lo recolecta de los
// manifests instalados (misma fuente que los widgets, ADR-0054), corre la query REAL del módulo
// (CERO mocks) y evalúa `configured_when`. Solo se alerta a ADMIN (configurar módulos es tarea de
// admin) y solo de lo que la query confirme; si la query falla (sin permiso/boot) se omite.

import { computed, ref } from 'vue';
import type { ErploraClient } from '@erplora/module-sdk';
import type { ModuleSetupCheck, ModuleSetupDef } from '@erplora/module-types';

import { loadInstalledManifests } from './module-loader';
import { isAdmin } from './session';
import { setNotificationCount } from './shell';

/** Un módulo instalado pendiente de configurar (lo que ve el usuario en la campana/dashboard). */
export interface PendingSetup {
  moduleId: string;
  title: string;
  description?: string;
  icon: string;
  /** Ruta de la pantalla de configuración del módulo. */
  route: string;
}

const _pending = ref<PendingSetup[]>([]);
/** Lista reactiva de módulos pendientes de configurar (la leen la campana y el dashboard). */
export const pendingSetups = computed<PendingSetup[]>(() => _pending.value);

type Row = Record<string, unknown>;

/** ¿"verdadero" en sentido laxo? (no null/undefined, no '', no 0/'0', no false). */
function truthy(v: unknown): boolean {
  return v !== null && v !== undefined && v !== '' && v !== 0 && v !== false && v !== '0';
}

/** Evalúa un check de `configured_when` sobre la fila del resultado. */
function passes(row: Row, c: ModuleSetupCheck): boolean {
  const v = row[c.field];
  if (c.truthy !== undefined) return c.truthy ? truthy(v) : !truthy(v);
  if (c.equals !== undefined) return String(v) === String(c.equals);
  return false;
}

/** Configurado ⇔ hay fila Y todos los checks pasan. Sin fila → NO configurado. */
function isConfigured(row: Row | undefined, def: ModuleSetupDef): boolean {
  if (!row) return false;
  return (def.configured_when ?? []).every((c) => passes(row, c));
}

/**
 * Recalcula la lista de módulos pendientes de configurar y actualiza el contador de la campana.
 * Best-effort: cualquier fallo (red, permiso, boot temprano) degrada a "no alertar por ese módulo".
 * No-op para usuarios no-admin (no ven alertas de configuración).
 */
export async function refreshSetupStatus(client: ErploraClient): Promise<void> {
  if (!isAdmin.value) {
    _pending.value = [];
    setNotificationCount(0);
    return;
  }
  let manifests;
  try {
    manifests = await loadInstalledManifests();
  } catch {
    return; // boot temprano / runtime aún no responde → mantenemos lo que hubiera
  }

  const out: PendingSetup[] = [];
  for (const { moduleId, manifest } of manifests) {
    const def = manifest.setup;
    if (!def?.query || !def.route || !Array.isArray(def.configured_when)) continue;
    let row: Row | undefined;
    try {
      const res = await client.query<Row | Row[]>(def.query, def.params ?? {});
      row = Array.isArray(res) ? res[0] : res;
    } catch {
      continue; // sin permiso / error → no se puede determinar → no se alerta
    }
    if (!isConfigured(row, def)) {
      out.push({
        moduleId,
        title: def.title,
        description: def.description,
        icon: def.icon || 'alert-circle-outline',
        route: def.route,
      });
    }
  }

  _pending.value = out;
  setNotificationCount(out.length);
}
