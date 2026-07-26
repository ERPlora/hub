// Cliente de `GET /api/system/metrics` — telemetría de recursos del Hub FRENTE A LOS LÍMITES DEL
// PLAN (ADR-0154, hub#203). Alimenta la sección «Plan y límites» de la pantalla de Sistema:
// RAM/CPU/BD frente a la cuota del contenedor (cgroups v2, ADR-0096) y dispositivos/sesiones
// frente a `max_devices` del entitlement. Su norte es el free tier: hacer visible el techo y
// empujar el upgrade (deep-link al marketplace del SaaS).
//
// El runtime Rust es la AUTORIDAD (lee su cgroup, su BD y el claim del entitlement). El navegador
// solo pinta. Fuera de un contenedor (Tauri/desktop, dev) memoria/CPU llegan como `null` y la UI
// lo muestra como «n/a». Contrato implementado en `crates/server/src/system_metrics.rs`.

import { config } from './config';
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Métrica de recurso con uso y límite absolutos + fracción para la barra. `null` = no medible. */
export interface ResourceMetric {
  usedBytes: number | null;
  limitBytes: number | null;
  fraction: number | null;
}

/** CPU en cores (más natural que % para un límite de cgroup como "0,5 vCPU"). */
export interface CpuMetric {
  usedCores: number | null;
  limitCores: number | null;
  fraction: number | null;
}

/** Base de datos: tamaño real + cuota del plan (hoy `null`: el claim no la trae — follow-up). */
export interface DbMetric {
  engine: string;
  sizeBytes: number | null;
  limitBytes: number | null;
  fraction: number | null;
}

/** Sesiones activas y dispositivos distintos frente al tope del plan (`0` = ilimitado). */
export interface SessionMetric {
  active: number;
  devices: number;
  maxDevices: number;
}

/** Respuesta de `GET /api/system/metrics` (campo `data` del envelope del runtime). */
export interface SystemMetrics {
  /** Slug del plan contratado (`free`, `restaurant`…) o `null` si el claim no lo trae. */
  plan: string | null;
  memory: ResourceMetric;
  cpu: CpuMetric;
  database: DbMetric;
  sessions: SessionMetric;
}

interface Envelope<T> {
  ok: boolean;
  data?: T;
  error?: string | { message?: string };
}

/** Umbral por defecto (80%) a partir del cual, en plan free, se sugiere subir de plan. */
export const UPGRADE_THRESHOLD = 0.8;

/**
 * Obtiene la telemetría de recursos del runtime (`GET /api/system/metrics`). NO inventa datos: si
 * el endpoint no responde devuelve `null` para que la UI muestre un error recuperable.
 */
export async function fetchSystemMetrics(): Promise<SystemMetrics | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/system/metrics`, { headers: runtimeHeaders() });
    if (!res.ok) return null;
    const env = (await res.json()) as Envelope<SystemMetrics>;
    return env.ok && env.data ? env.data : null;
  } catch {
    return null;
  }
}

/** Bytes legibles (base 1024, etiqueta KB/MB/GB como el runtime). `—` si no es medible. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return '—';
  const KB = 1024;
  const MB = KB * 1024;
  const GB = MB * 1024;
  // Un decimal, recortando el «.0» sobrante — mismo contrato que `human_bytes`/`fmt_decimal` del
  // runtime Rust: un límite exacto se lee «96 MB», nunca «96.0 MB» (confundible con el uso).
  const d1 = (n: number) => n.toFixed(1).replace(/\.0$/, '');
  if (bytes >= GB) return `${d1(bytes / GB)} GB`;
  if (bytes >= MB) {
    const mb = bytes / MB;
    return `${mb >= 100 ? Math.round(mb) : d1(mb)} MB`;
  }
  if (bytes >= KB) return `${Math.round(bytes / KB)} KB`;
  return `${bytes} B`;
}

/** Fracción 0..1 → % entero; `null` si no medible. */
export function toPct(fraction: number | null | undefined): number | null {
  return fraction == null || !Number.isFinite(fraction) ? null : Math.round(fraction * 100);
}

/** Motivo del aviso de upgrade (solo plan free), o `null` si no procede. Uno solo, para la copy. */
export function upgradeReason(
  m: SystemMetrics,
  threshold = UPGRADE_THRESHOLD,
): 'memory' | 'database' | 'devices' | null {
  if (m.plan !== 'free') return null;
  if ((m.memory.fraction ?? 0) >= threshold) return 'memory';
  if ((m.database.fraction ?? 0) >= threshold) return 'database';
  if (m.sessions.maxDevices > 0 && m.sessions.devices >= m.sessions.maxDevices) return 'devices';
  return null;
}

/** ¿Mostrar el CTA de upgrade? (plan free rozando algún límite). */
export function shouldPromptUpgrade(m: SystemMetrics, threshold = UPGRADE_THRESHOLD): boolean {
  return upgradeReason(m, threshold) !== null;
}

/**
 * Deep-link al marketplace de planes del SaaS (el Hub NO vende, ADR-0114): abre el navegador
 * externo. Mismo patrón que `BillingPage` (`plansDeepLink`), con `utm_content` propio para atribuir
 * las conversiones que nacen del techo de recursos.
 */
export function upgradeLink(): string {
  return `${config.cloudApiUrl}/dashboard/marketplace/plans/?hub=${encodeURIComponent(
    config.hubId,
  )}&utm_source=hub&utm_content=system-limits`;
}
