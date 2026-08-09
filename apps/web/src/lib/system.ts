// Cliente de la pantalla /system — contrato `GET /api/system` del runtime del Hub.
//
// La pantalla de Sistema muestra DATOS REALES, no demo. Tras ADR-0154 el Hub es Postgres-only, PWA
// y cloud-only: `backend` es SIEMPRE `'cloud'`, `shell` SIEMPRE `'web'` y `storageSource` SIEMPRE
// `'s3'` (ya no existen SQLite/single, Tauri/desktop ni disco local). El runtime Rust es la
// AUTORIDAD: mide las métricas y reporta la BD (nada se infiere en el navegador). Lo único que
// cambia con el despliegue es la FUENTE de CPU/memoria:
//
//   métrica       ECS/Fargate (AWS de reserva)        Docker (Hetzner/Swarm, activo)   dev local
//   ───────────   ─────────────────────────────────   ──────────────────────────────   ──────────
//   CPU/memoria   ECS Task Metadata v4 `/task/stats`   cgroup v2 `/sys/fs/cgroup/*`      (null)
//   BD            Postgres (sin "tamaño local")        Postgres                         Postgres
//   documentos    S3 vía el Cloud                      S3 vía el Cloud                  S3 vía el Cloud
//
// (Detalle de fuentes en `architecture/hub/system-info.md`, contrato que implementa el humano en
// `crates/server`.) Los documentos SIEMPRE salen del Cloud: el Hub no tiene credenciales S3.
//
// Mientras el endpoint no exista, `fetchSystemInfo` devuelve `null`: las tarjetas KPI se muestran
// igualmente con valores a 0 (CPU/Memoria/Conexiones 0, BD sin tamaño) y las pestañas de datos
// (Documentos/Registros) muestran su estado vacío propio — nunca números inventados. Las copias,
// importaciones y restauraciones se gestionan únicamente en Ajustes → Datos y copias.

import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Backend de datos del hub. Postgres-only (ADR-0154): el runtime siempre reporta `'cloud'`. */
export type DataBackend = 'cloud';
/** Shell bajo el que corre el runtime. PWA (ADR-0154): el runtime siempre reporta `'web'`. */
export type ShellKind = 'web';

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
  /** Motor real. Postgres-only (ADR-0154): siempre `'postgres'` (`'aurora'` reservado por si se
   *  activa el proveedor AWS de reserva, que expone la misma etiqueta Postgres-compatible). */
  engine: 'postgres' | 'aurora';
  /** Tamaño formateado, p.ej. "8,6 MB". `null` cuando no es medible (Aurora compartida). */
  sizeLabel?: string | null;
  /** Conexiones activas reales (pool / pg_stat_activity). */
  connections: number;
  /** Límite de conexiones; `null` si no aplica. */
  connectionsLimit?: number | null;
}

/** Un documento de almacenamiento (objeto S3 del hub, servido vía el Cloud). */
export interface StorageDoc {
  name: string;
  sizeLabel: string;
  /** ISO 8601. */
  modified: string;
  kind?: string | null;
  /** URL firmada S3 (vía el Cloud); `null` si no descargable. */
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
  /** Origen del almacenamiento de documentos. Cloud-only (ADR-0154): siempre `'s3'` (vía el Cloud;
   *  el Hub no tiene credenciales S3 ni lee del disco). */
  storageSource?: 's3' | null;
  /** Capacidad de almacenamiento formateada para la barra (p.ej. "2,1 GB / 8 GB"). */
  storageUsed?: UsageMetric | null;
  documents?: StorageDoc[];
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
 * NO lanza ni inventa datos: si el endpoint no responde, devuelve `null` para que la UI muestre un
 * error recuperable en vez de afirmar valores o estados que no ha podido comprobar.
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
