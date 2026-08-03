// Subsistema "alertas de módulo" (ADR-0067, bucket "estado que se autocura" → banner del dashboard).
//
// Hermano de `setup-status.ts`, pero para ESTADO DE RUNTIME en vez de estado de configuración. Donde
// setup-status alerta de "módulo instalado pero SIN CONFIGURAR" (se cura al configurar), este lib
// alerta de "módulo con un BACKLOG operativo" (se cura al drenar). Primer adoptante: la cola de
// contingencia de VeriFactu (N facturas sin transmitir a la AEAT porque no hay conexión) — el TPV
// sigue funcionando y la tarea programada las envía sola al recuperar la red, así que la señal se cura
// sin intervención: es estado derivado, no un evento (los eventos van a la campana, core diferido).
//
// GENÉRICO (el Hub es internacional y no conoce módulos concretos): la declaración vive en el
// `module.json` del módulo y el shell solo la TRANSPORTA y evalúa, igual que `setup`/`widgets`. Aquí
// está SOLO la evaluación pura (fila + declaración → alerta | null); la recolección con I/O (correr la
// query de cada manifest instalado y publicar la lista reactiva para el banner) se ata aparte.
//
// NOTA (columna del humano): la FORMA final del bloque `alerts` en el contrato (`module.schema.json` +
// `@erplora/module-types`) la valida Ioan. Aquí el tipo es local a propósito, para no tocar el contrato
// compartido antes de que la forma esté aprobada.

import { computed, ref } from 'vue';
import type { ErploraClient } from '@erplora/module-sdk';
import type { AlertCheck, AlertSeverity, ModuleAlertDef } from '@erplora/module-types';

import { loadInstalledManifests } from './module-loader';

// El contrato del bloque `alerts` (declaración del module.json) vive en `@erplora/module-types`,
// junto a `setup`/`widgets`; se re-exporta aquí por comodidad de los consumidores del shell.
export type { AlertCheck, AlertSeverity, ModuleAlertDef } from '@erplora/module-types';

const SEVERITIES = new Set<AlertSeverity>(['info', 'warning', 'danger']);

/** Una alerta ACTIVA, lista para pintarse en el banner del dashboard. */
export interface ActiveAlert {
  moduleId: string;
  title: string;
  /** Subtexto opcional (tranquilizador offline-first), si el módulo lo declaró. */
  hint?: string;
  route: string;
  icon: string;
  severity: AlertSeverity;
  /** Contador (si el módulo declaró `count_field` y la fila lo trae numérico). */
  count?: number;
}

type Row = Record<string, unknown>;

/** ¿"verdadero" en sentido laxo? (mismo criterio que setup-status para coherencia). */
function isTruthy(v: unknown): boolean {
  return v !== null && v !== undefined && v !== '' && v !== 0 && v !== false && v !== '0';
}

/** Convierte a número finito o `undefined` (tolerante a strings numéricos; null/''/no-numérico → undefined). */
function finiteNum(v: unknown): number | undefined {
  if (v === null || v === undefined || v === '') return undefined;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : undefined;
}

/**
 * ¿Se cumple la condición `when` sobre la fila? Robusto ante valores ausentes/nulos: una comparación
 * numérica contra un valor no numérico NUNCA dispara (no queremos alertar por datos basura).
 */
export function alertPasses(row: Row, check: AlertCheck): boolean {
  const v = row[check.field];
  if (check.gt !== undefined) {
    const n = finiteNum(v);
    return n !== undefined && n > check.gt;
  }
  if (check.gte !== undefined) {
    const n = finiteNum(v);
    return n !== undefined && n >= check.gte;
  }
  if (check.truthy !== undefined) {
    return check.truthy ? isTruthy(v) : !isTruthy(v);
  }
  if (check.equals !== undefined) {
    return String(v) === String(check.equals);
  }
  return false;
}

/** Severidad efectiva: columna válida > literal declarado > `warning` por defecto. */
function resolveSeverity(row: Row, def: ModuleAlertDef): AlertSeverity {
  const fromCol = def.severity_field ? String(row[def.severity_field] ?? '').toLowerCase() : '';
  if (SEVERITIES.has(fromCol as AlertSeverity)) return fromCol as AlertSeverity;
  if (def.severity && SEVERITIES.has(def.severity)) return def.severity;
  return 'warning';
}

/**
 * Evalúa la declaración de una alerta contra la 1ª fila de su query. Devuelve la alerta ACTIVA o
 * `null` (sin fila, condición no cumplida, o declaración inválida — nunca rompe el dashboard).
 */
export function evaluateAlert(
  moduleId: string,
  row: Row | undefined,
  def: ModuleAlertDef,
): ActiveAlert | null {
  if (!def || !def.query || !def.route || !def.when?.field) return null;
  if (!row) return null;
  if (!alertPasses(row, def.when)) return null;

  const count = def.count_field ? finiteNum(row[def.count_field]) : undefined;
  return {
    moduleId,
    title: def.title,
    route: def.route,
    icon: def.icon || 'alert-circle-outline',
    severity: resolveSeverity(row, def),
    ...(def.hint ? { hint: def.hint } : {}),
    ...(count !== undefined ? { count } : {}),
  };
}

// ── Recolección (I/O) ──────────────────────────────────────────────────────────────────────────

/** Resolución del permiso de la sesión: `true`/`false` decide; `null` = desconocido (no filtra). */
export type PermissionResolver = (permission: string) => boolean | null;

/** Traducción de una alerta (clave = `query`): título/subtexto en el idioma activo. */
type AlertLocale = Record<string, { title?: string; hint?: string }>;

/** Un manifest instalado con (posiblemente) un bloque `alerts` + su traducción del idioma activo. */
interface ManifestWithAlerts {
  moduleId: string;
  manifest: { alerts?: ModuleAlertDef[] };
  /** Traducciones del módulo (ADR-0055): `alerts.<query>.{title,hint}`. Inglés canónico si falta. */
  locale?: { alerts?: AlertLocale };
}

/** Dependencias inyectables de la recolección (query runner + permiso), para probarla sin I/O. */
export interface CollectAlertsDeps {
  query: (name: string, params?: Record<string, unknown>) => Promise<unknown>;
  hasPermission?: PermissionResolver;
}

/** 1ª fila del resultado de una query (array plano, motor de listas `{rows}`, u objeto/escalar suelto). */
function firstRow(result: unknown): Row | undefined {
  if (result == null) return undefined;
  if (Array.isArray(result)) return result[0] as Row | undefined;
  if (typeof result === 'object') {
    const obj = result as Record<string, unknown>;
    if (Array.isArray(obj.rows)) return obj.rows[0] as Row | undefined;
    return obj as Row;
  }
  return { value: result } as Row;
}

/**
 * Recorre los manifests instalados, corre la query de cada alerta declarada y devuelve las que están
 * ACTIVAS. Best-effort (mismo criterio que setup-status): cualquier fallo (red, permiso, boot) degrada
 * a "no alertar por esa entrada", nunca rompe el dashboard. Conserva el orden de los módulos.
 * Filtro por permiso EN CLIENTE (solo mostrar/ocultar; la query revalida en server); `null` = permiso
 * desconocido → degradación permisiva.
 */
export async function collectModuleAlerts(
  manifests: ManifestWithAlerts[],
  deps: CollectAlertsDeps,
): Promise<ActiveAlert[]> {
  const out: ActiveAlert[] = [];
  for (const { moduleId, manifest, locale } of manifests) {
    const defs = Array.isArray(manifest.alerts) ? manifest.alerts : [];
    for (const def of defs) {
      if (!def?.query || !def.route || !def.when?.field) continue;
      if (def.permission && deps.hasPermission && deps.hasPermission(def.permission) === false) continue;
      let row: Row | undefined;
      try {
        row = firstRow(await deps.query(def.query, def.params ?? {}));
      } catch {
        continue; // sin permiso / error / boot → no se puede determinar → no se alerta
      }
      const alert = evaluateAlert(moduleId, row, def);
      if (!alert) continue;
      // i18n (ADR-0055): title/hint canónicos (inglés) del manifest, traducidos por el locale del
      // módulo (clave = `query`); sin entrada se quedan los canónicos. Espeja los títulos de widget.
      const tr = locale?.alerts?.[def.query];
      if (tr?.title) alert.title = tr.title;
      if (tr?.hint) alert.hint = tr.hint;
      out.push(alert);
    }
  }
  return out;
}

const _alerts = ref<ActiveAlert[]>([]);
/** Lista reactiva de alertas de runtime activas (la lee el banner del dashboard). */
export const moduleAlerts = computed<ActiveAlert[]>(() => _alerts.value);

/**
 * Recalcula las alertas de runtime de los módulos instalados (banner del dashboard). Best-effort:
 * un fallo temprano (runtime aún sin responder) mantiene lo que hubiera. Reutiliza la misma fuente de
 * manifests que los widgets/setup-status.
 */
export async function refreshModuleAlerts(client: ErploraClient): Promise<void> {
  let manifests;
  try {
    manifests = await loadInstalledManifests();
  } catch {
    return;
  }
  const list: ManifestWithAlerts[] = manifests.map((m) => ({
    moduleId: m.moduleId,
    manifest: m.manifest, // `alerts` ya es parte del contrato `ModuleManifest` (@erplora/module-types)
    locale: m.locale, // traducción del idioma activo (ADR-0055): title/hint por `query`
  }));
  _alerts.value = await collectModuleAlerts(list, {
    query: (name, params) => client.query(name, params),
  });
}
