// Cliente de la pantalla /system — contrato `GET /api/system` del runtime del Hub.
//
// La pantalla de Sistema muestra DATOS REALES, no demo. Pero la fuente cambia según los dos ejes
// de la arquitectura (hub/ARQUITECTURA.md §1, hub/CLAUDE.md):
//
//   • Eje A — backend de datos:  'single' (SQLite embebido)  | 'cloud' (Aurora/Postgres, 1 ECS/hub)
//   • Eje B — shell:             'tauri' (acceso a SO/disco) | 'web' (navegador, sin hardware)
//
// El runtime Rust es la AUTORIDAD: sabe su adaptador de DB y bajo qué shell corre, así que es él
// quien reporta `backend`/`shell` y mide las métricas (no se infieren en el navegador). La fuente
// recomendada de cada métrica está documentada en `architecture/hub/system-info.md` (contrato
// que implementa el humano en `crates/server`). Resumen:
//
//   métrica            cloud (ECS Fargate)                         single (Tauri/desktop)
//   ─────────────────  ──────────────────────────────────────────  ───────────────────────────────
//   CPU / memoria      ECS Task Metadata v4 `/task/stats` (cgroup   crate `sysinfo` (uso real del SO)
//                      real, respeta el límite del task, sin IAM)
//   tamaño BD          n/a (Aurora compartida por organización)    `PRAGMA page_count*page_size`
//   conexiones BD      `pg_stat_activity` del pool (real)          pool SQLite (≈1)
//   documentos         listado S3 `erplora-storage` del hub        listado del disco local
//   copias             módulo backup → S3 (ADR-0040)               módulo backup → disco
//
// Mientras el endpoint no exista, `fetchSystemInfo` devuelve `null`: las tarjetas KPI se muestran
// igualmente con valores a 0 (CPU/Memoria/Conexiones 0, BD sin tamaño) y las pestañas de datos
// (Documentos/Copias/Registros) muestran su estado vacío propio — nunca números inventados.

import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Eje A — backend de datos del hub. Lo reporta el runtime (sabe su adaptador). */
export type DataBackend = 'cloud' | 'single';
/** Eje B — shell bajo el que corre el runtime. */
export type ShellKind = 'tauri' | 'web';

/** Una métrica de uso (CPU, memoria). Valores ya formateados por el runtime para mostrar. */
export interface UsageMetric {
  /** Valor actual formateado, p.ej. "612 MB" / "0,4 cores". */
  usedLabel: string;
  /** Capacidad/límite formateado, p.ej. "2 GB" / "2 vCPU". `null` si no aplica. */
  limitLabel?: string | null;
  /** Fracción 0..1 para la barra de progreso. `null` si no es medible. */
  fraction?: number | null;
  /** Serie reciente (uso %) para la sparkline. Vacío/ausente = sin histórico. */
  history?: number[];
}

/** Estado de la base de datos del hub. */
export interface DatabaseInfo {
  /** Motor real: 'sqlite' (single) | 'postgres' | 'aurora' (cloud). */
  engine: 'sqlite' | 'postgres' | 'aurora' | string;
  /** Tamaño formateado, p.ej. "8,6 MB". `null` cuando no es medible (Aurora compartida). */
  sizeLabel?: string | null;
  /** Conexiones activas reales (pool / pg_stat_activity). */
  connections: number;
  /** Límite de conexiones; `null` si no aplica. */
  connectionsLimit?: number | null;
}

/** Un documento de almacenamiento (objeto S3 en cloud, fichero del disco en Tauri). */
export interface StorageDoc {
  name: string;
  sizeLabel: string;
  /** ISO 8601. */
  modified: string;
  kind?: string | null;
  /** URL firmada S3 (cloud) o ruta local (Tauri); `null` si no descargable. */
  url?: string | null;
}

/** Una copia de seguridad (objeto S3 del módulo backup en cloud, fichero local en Tauri). */
export interface BackupEntry {
  /** ISO 8601. */
  when: string;
  sizeLabel: string;
  url?: string | null;
}

/** Una línea del registro de eventos del runtime. */
export interface SystemLogEntry {
  /** ISO 8601 o "HH:MM:SS". */
  when: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  message: string;
  meta?: string | null;
}

/** Respuesta de `GET /api/system` (campo `data` del envelope del runtime). */
export interface SystemInfo {
  backend: DataBackend;
  shell: ShellKind;
  /** Versión del hub (pestaña Actualizaciones). */
  hubVersion?: string | null;
  cpu?: UsageMetric | null;
  memory?: UsageMetric | null;
  database: DatabaseInfo;
  /** Origen del almacenamiento de documentos: 's3' (cloud) | 'disk' (Tauri). */
  storageSource?: 's3' | 'disk' | null;
  /** Capacidad de almacenamiento formateada para la barra (p.ej. "2,1 GB / 8 GB"). */
  storageUsed?: UsageMetric | null;
  documents?: StorageDoc[];
  backups?: BackupEntry[];
  logs?: SystemLogEntry[];
}

/** Envelope estándar del runtime (`{ ok, data }`), igual que el resto de endpoints. */
interface Envelope<T> {
  ok: boolean;
  data?: T;
  error?: { message?: string };
}

/**
 * Obtiene el estado real del sistema del runtime (`GET /api/system`).
 *
 * NO lanza ni inventa datos: si el endpoint todavía no existe (404) o el runtime no responde,
 * devuelve `null` para que la UI muestre estados de carga/vacíos reales en vez de mock. La
 * pantalla de Sistema decide qué enseñar según `backend`/`shell` cuando sí hay datos.
 */
export async function fetchSystemInfo(): Promise<SystemInfo | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/system`, { headers: runtimeHeaders() });
    if (!res.ok) return null;
    const env = (await res.json()) as Envelope<SystemInfo>;
    return env.ok && env.data ? env.data : null;
  } catch {
    return null;
  }
}
