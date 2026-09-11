// Cliente de `GET /api/system/metrics` — telemetría de recursos del Hub FRENTE A LOS LÍMITES DEL
// PLAN (ADR-0154, hub#203). Alimenta la sección «Plan y límites» de la pantalla de Sistema:
// RAM/CPU/BD frente a la cuota del contenedor (cgroups v2, ADR-0096) y dispositivos/sesiones
// frente a `max_devices` del entitlement. Su norte es el free tier: hacer visible el techo y
// empujar el upgrade (deep-link al marketplace del SaaS).
//
// El runtime Rust es la AUTORIDAD (lee su cgroup, su BD y el claim del entitlement). El navegador
// solo pinta. Fuera de un contenedor (Tauri/desktop, dev) memoria/CPU llegan como `null` y la UI
// lo muestra como «n/a». Contrato implementado en `crates/server/src/system_metrics.rs`.

// `config` was imported for `upgradeLink()`, the one thing here that built a Cloud address. With
// that gone (hub#479) this module only reads the runtime's own metrics — it no longer knows the
// SaaS exists.
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

/** Base de datos: tamaño real + cuota del plan; `null` para plan ilimitado o token antiguo. */
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

/** Personas activas del hub frente al tope de plazas del plan (`0` = ilimitado). */
export interface UserMetric {
  active: number;
  maxUsers: number;
}

/** Respuesta de `GET /api/system/metrics` (campo `data` del envelope del runtime). */
export interface SystemMetrics {
  /** Slug del plan contratado (`free`, `restaurant`…) o `null` si el claim no lo trae. */
  plan: string | null;
  memory: ResourceMetric;
  cpu: CpuMetric;
  database: DbMetric;
  sessions: SessionMetric;
  users: UserMetric;
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
): 'memory' | 'database' | 'devices' | 'users' | null {
  if (m.plan !== 'free') return null;
  if ((m.memory.fraction ?? 0) >= threshold) return 'memory';
  if ((m.database.fraction ?? 0) >= threshold) return 'database';
  if (m.sessions.maxDevices > 0 && m.sessions.devices >= m.sessions.maxDevices) return 'devices';
  // Plazas de personal: a diferencia de RAM/BD no tiene umbral del 80 % — una plaza es entera o no
  // es, así que solo avisa cuando ya están TODAS ocupadas y el alta siguiente se va a rechazar.
  if (m.users.maxUsers > 0 && m.users.active >= m.users.maxUsers) return 'users';
  return null;
}

/** ¿Mostrar el CTA de upgrade? (plan free rozando algún límite). */
export function shouldPromptUpgrade(m: SystemMetrics, threshold = UPGRADE_THRESHOLD): boolean {
  return upgradeReason(m, threshold) !== null;
}

// `upgradeLink()` lived here: a deep-link to the SaaS plans marketplace, with its own `utm_content`
// to attribute the conversions born at the resource ceiling. It is gone (hub#479).
//
// Not because the trip was broken — it worked — but because a link from inside the app to a page
// that can take money is STEERING, and steering is what gets a listing rejected on Google Play and
// on Microsoft Store. The Hub still says the shop is running out of room; it no longer offers the
// door. Buying and upgrading live on erplora.com, which is the only place ERPlora sells.
//
// `upgradeReason()` above stays exactly as it was: knowing you are near the ceiling is useful on
// its own, and it is what the panel now words as guidance instead of a button.
