// Subsistema "estado de configuración" (ADR-0063): detecta MÓDULOS instalados que aún NO están
// configurados y los surfacea como alerta SOLO en el DASHBOARD (banner) con un CTA a su pantalla
// de ajustes. Es un ESTADO DERIVADO que se cura solo: en cuanto el módulo queda configurado, deja
// de alertar. NO alimenta la campana de la topbar (esa es una central de notificaciones de EVENTOS
// futura, aparte — ver lib/shell.notificationCount).
//
// GENÉRICO (el Hub es internacional y no conoce módulos concretos): cada módulo declara su propio
// chequeo en `module.json` (`setup`, ver @erplora/module-types). El shell lo recolecta de los
// manifests instalados (misma fuente que los widgets, ADR-0054), corre la query REAL del módulo
// (CERO mocks) y evalúa `configured_when`. Solo se alerta de configuración REQUERIDA (`required`
// ausente = true; `required: false` = opcional, no molesta), a quien tiene permiso para configurar
// (gate ADMIN + `permission` del módulo) y solo de lo que la query confirme; si la query falla
// (sin permiso/boot) se omite.

import { computed, ref } from 'vue';
import type { ErploraClient } from '@erplora/module-sdk';
import type { ModuleSetupCheck, ModuleSetupDef } from '@erplora/module-types';

import { loadInstalledManifests } from './module-loader';
import { isAdmin } from './session';

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
 * Recalcula la lista de módulos pendientes de configurar (banner del dashboard).
 * Best-effort: cualquier fallo (red, permiso, boot temprano) degrada a "no alertar por ese módulo".
 * No-op para usuarios no-admin (no ven alertas de configuración).
 * NO toca la campana de la topbar: esa es una central de notificaciones de EVENTOS futura, aparte.
 */
export async function refreshSetupStatus(client: ErploraClient): Promise<void> {
  if (!isAdmin.value) {
    _pending.value = [];
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
    // Solo alerta la configuración REQUERIDA: `required` ausente = requerido (por defecto);
    // `required: false` = opcional → no molesta en el dashboard.
    if (def.required === false) continue;
    // Filtra por PERMISO de configurar: el gate ADMIN (arriba) ya restringe el grueso; si el módulo
    // declara un `permission` específico, además debe tenerlo el usuario actual. Sin un helper de
    // permisos finos en cliente hoy (session.ts solo expone el rol), el gate efectivo es ADMIN; la
    // query REAL (más abajo) revalida el permiso server-side y descarta lo que no pueda leer.
    if (def.permission && !hasSetupPermission(def.permission)) continue;
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
}

/**
 * ¿Puede el usuario actual configurar un módulo que pide `perm`? Hoy session.ts no expone un set de
 * permisos finos en cliente (la autoridad es el runtime, que revalida cada query), así que el gate
 * efectivo es ADMIN — owner/admin configura módulos. Cuando el shell exponga un `hasPermission(perm)`
 * limpio, basta con consultarlo aquí.
 */
function hasSetupPermission(_perm: string): boolean {
  return isAdmin.value;
}

/**
 * Contexto determinista para el asistente: resume el estado de configuración del hub a partir de
 * `pendingSetups` (DATOS REALES de setup-status, cero invenciones). Se siembra como mensaje `system`
 * al abrir el asistente desde el botón "Revisar configuración" del dashboard, para que el LLM arranque
 * sabiendo qué falta y a qué pantalla llevar al usuario. Escala solo: cualquier módulo nuevo con
 * bloque `setup` en su module.json aparece aquí automáticamente.
 */
export function seedSetupContext(): string {
  const list = pendingSetups.value;
  const header = 'Eres el asistente de configuración del hub ERPlora. Ayuda al usuario a dejar todo configurado.';
  if (!list.length) {
    return `${header}\n\nEstado: todos los módulos instalados están configurados correctamente. Si el usuario pregunta por algún módulo concreto, explícale cómo funciona y ofrécele ir a su pantalla.`;
  }
  const items = list
    .map((s) => {
      const desc = s.description ? ` — "${s.description}"` : '';
      return `• ${s.title}${desc}\n  Pantalla: ${s.route}`;
    })
    .join('\n');
  const n = list.length;
  return `${header}\n\nFaltan ${n} módulo(s) por configurar:\n${items}\n\n` +
    'Cuando el usuario pregunte cómo configurar algo, explica los pasos con la descripción de arriba y dile a qué pantalla ir (la ruta). ' +
    'Puedes usar las tools disponibles para consultar el estado real de los módulos. Ofrece ayudar a configurar cada uno.';
}

