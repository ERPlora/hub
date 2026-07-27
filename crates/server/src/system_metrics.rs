//! `GET /api/system/metrics` — telemetría de recursos del hub FRENTE A LOS LÍMITES DEL PLAN
//! (ADR-0154, hub#203). Crítico para escalar el free tier: hace visible al cliente cuánto
//! consume su hub contra la cuota que le da su plan y le empuja a subir cuando roza el techo.
//!
//! Módulo NUEVO y autocontenido a propósito (coordinación ADR-0154): el refactor paralelo que
//! elimina SQLite/Tauri toca `system.rs`/`media.rs`/`module_storage.rs`; este fichero no depende
//! de ellos para minimizar conflictos. El endpoint hermano `GET /api/system` (system.rs) sigue
//! siendo la vista de diagnóstico general; este es la vista "recursos vs plan".
//!
//! Contrato JSON (camelCase) consumido por `apps/web/src/lib/system-metrics.ts`:
//! ```json
//! { "ok": true, "data": {
//!     "plan": "free" | null,
//!     "memory":   { "usedBytes": u64|null, "limitBytes": u64|null, "fraction": f64|null },
//!     "cpu":      { "usedCores": f64|null, "limitCores": f64|null, "fraction": f64|null },
//!     "database": { "engine": "postgres"|"sqlite", "sizeBytes": u64|null, "limitBytes": u64|null, "fraction": f64|null },
//!     "sessions": { "active": i64, "devices": i64, "maxDevices": u32 }
//! }}
//! ```
//!
//! Memoria/CPU salen del **cgroup v2** del contenedor (`/sys/fs/cgroup/memory.*` + `cpu.*`), que
//! respeta el límite que el SaaS asigna por plan (ADR-0096, cgroups v2). Fuera de un contenedor
//! (Tauri/desktop, dev) los ficheros no existen → devolvemos `null` y la UI lo pinta como «n/a».
//! El lector va tras el trait [`CgroupReader`] para inyectar fakes en los tests (TDD).

use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_db::{DatabaseAdapter, Params};
use serde::Serialize;
use serde_json::{json, Value};

use crate::{auth, AppState};

// ─────────────────────────── Lector de cgroup (tras trait, testeable) ───────────────────────────

/// Lee los pseudo-ficheros de cgroup v2. Tras un trait para inyectar un fake en test: el lector
/// real (`SysCgroupReader`) toca `/sys/fs/cgroup/*`, que solo existe dentro de un contenedor Linux.
pub trait CgroupReader: Send + Sync {
    /// Contenido de `/sys/fs/cgroup/{file}` o `None` si no existe (fuera de contenedor).
    fn read(&self, file: &str) -> Option<String>;
}

/// Lector real: `std::fs` sobre `/sys/fs/cgroup`.
pub struct SysCgroupReader;

impl CgroupReader for SysCgroupReader {
    fn read(&self, file: &str) -> Option<String> {
        std::fs::read_to_string(format!("/sys/fs/cgroup/{file}")).ok()
    }
}

// ─────────────────────────── Estructuras del contrato ───────────────────────────

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MemoryMetric {
    pub used_bytes: Option<u64>,
    pub limit_bytes: Option<u64>,
    pub fraction: Option<f64>,
}

impl MemoryMetric {
    /// Fuera de contenedor (o error de lectura): todo `null` → la UI muestra «n/a».
    fn unavailable() -> Self {
        Self { used_bytes: None, limit_bytes: None, fraction: None }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CpuMetric {
    pub used_cores: Option<f64>,
    pub limit_cores: Option<f64>,
    pub fraction: Option<f64>,
}

impl CpuMetric {
    fn unavailable() -> Self {
        Self { used_cores: None, limit_cores: None, fraction: None }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DbMetric {
    pub engine: String,
    pub size_bytes: Option<u64>,
    pub limit_bytes: Option<u64>,
    pub fraction: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionMetric {
    pub active: i64,
    pub devices: i64,
    pub max_devices: u32,
}

// ─────────────────────────── Parsers de cgroup v2 (puros) ───────────────────────────

fn parse_u64(s: &str) -> Option<u64> {
    s.trim().parse().ok()
}

/// `memory.max`: número (bytes) o `"max"` (sin límite → `None`).
fn parse_mem_max(s: &str) -> Option<u64> {
    let s = s.trim();
    if s == "max" {
        None
    } else {
        s.parse().ok()
    }
}

/// `inactive_file` de `memory.stat` = caché de página a restar (como `docker stats` en cgroup v2).
fn parse_inactive_file(stat: &str) -> u64 {
    stat.lines()
        .find_map(|l| {
            l.strip_prefix("inactive_file ")
                .and_then(|v| v.trim().parse().ok())
        })
        .unwrap_or(0)
}

/// `usage_usec` acumulado de `cpu.stat` (μs de CPU consumidos desde el arranque del cgroup).
fn parse_cpu_usage_usec(stat: &str) -> Option<u64> {
    stat.lines().find_map(|l| {
        l.strip_prefix("usage_usec ")
            .and_then(|v| v.trim().parse().ok())
    })
}

/// `cpu.max` = `"<quota> <period>"`; `"max <period>"` = sin límite → `None`. Devuelve cores
/// (quota/period).
fn parse_cpu_max_cores(s: &str) -> Option<f64> {
    let mut it = s.split_whitespace();
    let quota = it.next()?;
    let period: f64 = it.next()?.parse().ok()?;
    if quota == "max" {
        None
    } else {
        Some(quota.parse::<f64>().ok()? / period)
    }
}

/// Fracción de uso 0..1 = `used / limit`, saturada; `None` si no hay límite conocido (`> 0`).
fn fraction(used: f64, limit: Option<f64>) -> Option<f64> {
    limit.filter(|l| *l > 0.0).map(|l| (used / l).clamp(0.0, 1.0))
}

// ─────────────────────────── Lectura de memoria/CPU vía el trait ───────────────────────────

/// Memoria usada (menos caché de página) y límite del cgroup. `unavailable` si `memory.current`
/// no existe (fuera de contenedor).
pub fn read_memory(r: &dyn CgroupReader) -> MemoryMetric {
    let Some(current) = r.read("memory.current").as_deref().and_then(parse_u64) else {
        return MemoryMetric::unavailable();
    };
    let inactive = r
        .read("memory.stat")
        .map(|s| parse_inactive_file(&s))
        .unwrap_or(0);
    let used = current.saturating_sub(inactive);
    let limit = r.read("memory.max").as_deref().and_then(parse_mem_max);
    MemoryMetric {
        used_bytes: Some(used),
        limit_bytes: limit,
        fraction: fraction(used as f64, limit.map(|l| l as f64)),
    }
}

/// `usage_usec` acumulado del cgroup (una muestra). `None` si no hay `cpu.stat`.
pub fn read_cpu_usage_usec(r: &dyn CgroupReader) -> Option<u64> {
    r.read("cpu.stat").as_deref().and_then(parse_cpu_usage_usec)
}

/// Límite de CPU en cores del cgroup (`cpu.max`). `None` = sin límite o fuera de contenedor.
pub fn read_cpu_limit_cores(r: &dyn CgroupReader) -> Option<f64> {
    r.read("cpu.max").as_deref().and_then(parse_cpu_max_cores)
}

/// Métrica de CPU a partir de dos muestras de `usage_usec` separadas `elapsed_usec` μs:
/// `used_cores = Δusage / Δtiempo`, `fraction = used_cores / limit_cores`. `unavailable` si falta
/// alguna muestra (fuera de contenedor) o el intervalo es 0.
pub fn cpu_metric(
    start: Option<u64>,
    end: Option<u64>,
    elapsed_usec: u64,
    limit_cores: Option<f64>,
) -> CpuMetric {
    let (Some(start), Some(end)) = (start, end) else {
        return CpuMetric::unavailable();
    };
    if elapsed_usec == 0 {
        return CpuMetric::unavailable();
    }
    let used_cores = end.saturating_sub(start) as f64 / elapsed_usec as f64;
    CpuMetric {
        used_cores: Some(used_cores),
        limit_cores,
        fraction: fraction(used_cores, limit_cores),
    }
}

/// Intervalo entre las dos muestras de `usage_usec` para estimar el uso instantáneo de CPU.
const CPU_SAMPLE_GAP_MS: u64 = 100;

/// Muestrea memoria + CPU del cgroup de forma **bloqueante** (IO de disco + `sleep` de la segunda
/// muestra de CPU). El llamador la envuelve en `spawn_blocking` para no parar el executor async.
/// `pub(crate)`: la pestaña Recursos (`system.rs`) reusa ESTE sampler testeado — una sola lectura
/// de cgroup en el crate, sin parsers duplicados.
pub(crate) fn sample_cgroup(r: &dyn CgroupReader) -> (MemoryMetric, CpuMetric) {
    let memory = read_memory(r);
    let start = read_cpu_usage_usec(r);
    std::thread::sleep(std::time::Duration::from_millis(CPU_SAMPLE_GAP_MS));
    let end = read_cpu_usage_usec(r);
    let cpu = cpu_metric(start, end, CPU_SAMPLE_GAP_MS * 1_000, read_cpu_limit_cores(r));
    (memory, cpu)
}

// ─────────────────────────── Base de datos + sesiones (adapter) ───────────────────────────

/// Un GiB en bytes. El contrato SaaS expresa `max_database_size_gb` en GiB, igual que el modelo
/// `Plan`; el endpoint System expone bytes para compartir formato con RAM y el cliente web.
const BYTES_PER_GIB: u64 = 1024 * 1024 * 1024;

/// Convierte la cuota del entitlement a bytes. El widening `u32 -> u64` antes de multiplicar hace
/// segura incluso la cuota máxima representable; `0` conserva la semántica ilimitada/autoscaling.
fn database_limit_bytes(max_database_size_gb: u32) -> Option<u64> {
    if max_database_size_gb == 0 {
        None
    } else {
        Some(u64::from(max_database_size_gb) * BYTES_PER_GIB)
    }
}

/// Tamaño real de la BD (Postgres-only, ADR-0154): `pg_database_size(current_database())`, frente
/// a la cuota firmada del plan. Sin cuota conocida (token antiguo o `0` ilimitado), límite y
/// fracción quedan `null` para que la UI no invente un techo.
async fn read_database(db: &dyn DatabaseAdapter, limit_bytes: Option<u64>) -> DbMetric {
    let no_params = Params::new();
    let size = scalar_u64(
        db,
        "SELECT pg_database_size(current_database()) AS n",
        &no_params,
    )
    .await;
    DbMetric {
        engine: "postgres".into(),
        size_bytes: size,
        limit_bytes,
        fraction: size
            .and_then(|used| fraction(used as f64, limit_bytes.map(|limit| limit as f64))),
    }
}

/// Sesiones activas (no caducadas) y nº de dispositivos distintos (`device_id` no nulo), más el
/// `max_devices` del plan. La comparación `expires_at > :now` sobre ISO-8601 es lexicográfica
/// (misma técnica que `identity::resolve_session`), portable SQLite/Postgres.
async fn read_sessions(db: &dyn DatabaseAdapter, max_devices: u32, now: &str) -> SessionMetric {
    let mut p = Params::new();
    p.insert("now".into(), json!(now));
    let active = scalar_i64(
        db,
        "SELECT count(*) AS n FROM hub_session WHERE expires_at > :now",
        &p,
    )
    .await
    .unwrap_or(0);
    let devices = scalar_i64(
        db,
        "SELECT count(DISTINCT device_id) AS n FROM hub_session \
         WHERE expires_at > :now AND device_id IS NOT NULL",
        &p,
    )
    .await
    .unwrap_or(0);
    SessionMetric { active, devices, max_devices }
}

/// Ejecuta una query escalar y devuelve el primer valor de la primera fila como `i64` (tolera
/// número o texto). `None` si falla o no hay filas.
async fn scalar_i64(db: &dyn DatabaseAdapter, sql: &str, params: &Params) -> Option<i64> {
    let res = db.query(sql, params).await.ok()?;
    let row = res.rows.first()?;
    let v = row.as_object()?.values().next()?;
    match v {
        Value::Number(n) => n.as_i64().or_else(|| n.as_f64().map(|f| f as i64)),
        Value::String(s) => s.trim().parse::<i64>().ok(),
        _ => None,
    }
}

async fn scalar_u64(db: &dyn DatabaseAdapter, sql: &str, params: &Params) -> Option<u64> {
    scalar_i64(db, sql, params)
        .await
        .and_then(|n| u64::try_from(n).ok())
}

// ─────────────────────────── Handler ───────────────────────────

/// `GET /api/system/metrics` — uso de recursos vs límites del plan. **Sesión admin** requerida
/// (owner/admin), como `export/import` y `settings`: es información de gestión del hub.
pub async fn system_metrics(State(st): State<AppState>, headers: HeaderMap) -> Response {
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": e.message() })),
            )
                .into_response();
        }
    }

    // Plan + límites del último entitlement verificado. Fail-open: sin claim conocido, plan
    // nulo y límites a 0 (ilimitados), como el resto del gate.
    let (plan, max_devices, max_database_size_gb) = match st.entitlement.read() {
        Ok(g) => (
            g.last_claims.as_ref().and_then(|c| c.plan.clone()),
            g.max_devices(),
            g.max_database_size_gb(),
        ),
        Err(_) => (None, 0, 0),
    };
    let database_limit = database_limit_bytes(max_database_size_gb);

    // Memoria/CPU del cgroup v2 en un hilo bloqueante (IO de `/sys` + `sleep` del muestreo de CPU).
    let (memory, cpu) = tokio::task::spawn_blocking(|| sample_cgroup(&SysCgroupReader))
        .await
        .unwrap_or_else(|_| (MemoryMetric::unavailable(), CpuMetric::unavailable()));

    // BD + sesiones bajo un único lock del runtime.
    let now = chrono::Utc::now().to_rfc3339();
    let (database, sessions) = {
        let rt = st.runtime.lock().await;
        let db = rt.db();
        (
            read_database(db, database_limit).await,
            read_sessions(db, max_devices, &now).await,
        )
    };

    Json(json!({
        "ok": true,
        "data": {
            "plan": plan,
            "memory": memory,
            "cpu": cpu,
            "database": database,
            "sessions": sessions,
        }
    }))
    .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    struct FakeCgroup(HashMap<String, String>);

    impl FakeCgroup {
        fn new(pairs: &[(&str, &str)]) -> Self {
            Self(
                pairs
                    .iter()
                    .map(|(k, v)| (k.to_string(), v.to_string()))
                    .collect(),
            )
        }
    }

    impl CgroupReader for FakeCgroup {
        fn read(&self, file: &str) -> Option<String> {
            self.0.get(file).cloned()
        }
    }

    #[test]
    fn memory_reads_current_minus_cache_over_limit() {
        // 12 MiB usados, 2 MiB de caché a restar, límite 96 MiB (plan free ADR-0154).
        let r = FakeCgroup::new(&[
            ("memory.current", "12582912\n"),
            ("memory.stat", "anon 1\ninactive_file 2097152\nfile 3\n"),
            ("memory.max", "100663296\n"),
        ]);
        let m = read_memory(&r);
        assert_eq!(m.used_bytes, Some(12_582_912 - 2_097_152)); // 10 MiB
        assert_eq!(m.limit_bytes, Some(100_663_296));
        let f = m.fraction.expect("fracción con límite");
        assert!((f - (10_485_760.0 / 100_663_296.0)).abs() < 1e-9);
    }

    #[test]
    fn memory_unavailable_outside_container() {
        // Sin `memory.current` = fuera de contenedor (Tauri/desktop/dev) → todo null («n/a»).
        let m = read_memory(&FakeCgroup::new(&[]));
        assert_eq!(m, MemoryMetric::unavailable());
        assert!(m.used_bytes.is_none() && m.limit_bytes.is_none() && m.fraction.is_none());
    }

    #[test]
    fn memory_no_limit_when_max_is_unlimited() {
        let r = FakeCgroup::new(&[("memory.current", "1000\n"), ("memory.max", "max\n")]);
        let m = read_memory(&r);
        assert_eq!(m.used_bytes, Some(1000));
        assert_eq!(m.limit_bytes, None);
        assert_eq!(m.fraction, None);
    }

    #[test]
    fn cpu_metric_computes_cores_and_fraction() {
        // 50_000 μs consumidos en 100_000 μs = 0.5 cores; límite 1 core → 50%.
        let c = cpu_metric(Some(1_000_000), Some(1_050_000), 100_000, Some(1.0));
        assert_eq!(c.used_cores, Some(0.5));
        assert_eq!(c.limit_cores, Some(1.0));
        assert_eq!(c.fraction, Some(0.5));
    }

    #[test]
    fn cpu_metric_unavailable_when_a_sample_is_missing() {
        assert_eq!(
            cpu_metric(None, Some(1), 100_000, Some(1.0)),
            CpuMetric::unavailable()
        );
        assert_eq!(
            cpu_metric(Some(1), None, 100_000, Some(1.0)),
            CpuMetric::unavailable()
        );
    }

    #[test]
    fn cpu_metric_no_fraction_without_limit() {
        let c = cpu_metric(Some(0), Some(50_000), 100_000, None);
        assert_eq!(c.used_cores, Some(0.5));
        assert_eq!(c.limit_cores, None);
        assert_eq!(c.fraction, None);
    }

    #[test]
    fn cgroup_parsers_cover_numbers_and_unlimited() {
        assert_eq!(parse_mem_max("134217728\n"), Some(134_217_728));
        assert_eq!(parse_mem_max("max\n"), None);
        assert_eq!(parse_inactive_file("anon 1\ninactive_file 4096\nfile 8\n"), 4096);
        assert_eq!(parse_inactive_file("anon 1\n"), 0);
        assert_eq!(parse_cpu_usage_usec("usage_usec 999\nuser_usec 1\n"), Some(999));
        assert_eq!(parse_cpu_usage_usec("nr_throttled 0\n"), None);
        assert_eq!(parse_cpu_max_cores("50000 100000"), Some(0.5));
        assert_eq!(parse_cpu_max_cores("100000 100000"), Some(1.0));
        assert_eq!(parse_cpu_max_cores("max 100000"), None);
    }

    #[test]
    fn database_quota_converts_gib_to_bytes_and_zero_is_unlimited() {
        assert_eq!(database_limit_bytes(0), None);
        assert_eq!(database_limit_bytes(1), Some(1_073_741_824));
        assert_eq!(database_limit_bytes(5), Some(5_368_709_120));
        assert_eq!(
            database_limit_bytes(u32::MAX),
            Some(u64::from(u32::MAX) * BYTES_PER_GIB)
        );
    }

    #[test]
    fn free_tier_prod_fixture_limit_from_cgroup_not_from_plan() {
        // Fixture REAL del free tier en prod (hub#207 diagnóstico 2026-07-27): el task de Swarm
        // corre con Limits.MemoryBytes=100663296 (96 MiB) y NanoCPUs=100000000 (0,1 vCPU →
        // cpu.max "10000 100000"). El LÍMITE mostrado sale SIEMPRE de `memory.max` del cgroup —
        // la cuota de memoria viene del cgroup; no del entitlement (que aporta plan, dispositivos
        // y cuota de BD).
        let r = FakeCgroup::new(&[
            ("memory.current", "11534336\n"), // 11 MiB
            ("memory.stat", "anon 7340032\ninactive_file 4194304\nfile 4194304\n"), // 4 MiB caché
            ("memory.max", "100663296\n"),    // 96 MiB (NUNCA 64: eso sería otro contenedor)
            ("cpu.max", "10000 100000"),      // 0,1 vCPU
        ]);
        let m = read_memory(&r);
        assert_eq!(m.limit_bytes, Some(100_663_296));
        assert_eq!(m.used_bytes, Some(7_340_032)); // 11 MiB − 4 MiB caché = 7 MiB
        // 7 MiB de 96 MiB ≈ 7% — el «7% de RAM» observado en prod es coherente con estos valores.
        let pct = (m.fraction.expect("fracción con límite") * 100.0).round();
        assert_eq!(pct, 7.0);
        assert_eq!(read_cpu_limit_cores(&r), Some(0.1));
    }

    #[test]
    fn cpu_readers_through_the_trait() {
        let r = FakeCgroup::new(&[
            ("cpu.stat", "usage_usec 12345\nuser_usec 1\n"),
            ("cpu.max", "50000 100000"),
        ]);
        assert_eq!(read_cpu_usage_usec(&r), Some(12345));
        assert_eq!(read_cpu_limit_cores(&r), Some(0.5));
        let empty = FakeCgroup::new(&[]);
        assert_eq!(read_cpu_usage_usec(&empty), None);
        assert_eq!(read_cpu_limit_cores(&empty), None);
    }
}
