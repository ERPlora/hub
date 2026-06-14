//! `GET /api/system` — estado REAL del sistema, axis-aware (ARQUITECTURA.md §1).
//!
//! Dos ejes determinan de dónde salen los datos:
//!   • backend de datos: SQLite (`single`) vs Postgres/Aurora (`cloud`) → por el DIALECTO real del
//!     adaptador (`Runtime::db().dialect()`), la autoridad es el runtime, no el navegador.
//!   • métricas/almacenamiento: si corremos en **ECS** (existe `ECS_CONTAINER_METADATA_URI_V4`)
//!     leemos el **ECS Task Metadata Endpoint v4** (`/task/stats` + `/task`); si no, somos LOCAL
//!     (Tauri/desktop) y leemos el SO con `sysinfo`.
//!
//! Por qué Task Metadata y no CloudWatch (decisión ADR-0046): es la contabilidad **cgroup del
//! propio task** (lo que CloudWatch agrega) pero en **tiempo real, sin IAM/coste/SDK** y respeta el
//! límite del Fargate. Evita el error de leer `/proc` y ver la RAM del host.
//!
//! Contrato (camelCase) consumido por `hub/apps/web/src/lib/system.ts`.
//! Documentos/copias/logs quedan como follow-up (necesitan listado S3/IAM y ruta de backups).

use axum::extract::State;
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_db::Dialect;
use serde_json::{json, Map, Value};

use crate::AppState;

/// GET /api/system — métricas + base de datos reales, según el despliegue.
pub async fn system_info(State(st): State<AppState>) -> Response {
    // ¿Estamos en ECS? El endpoint de metadata solo existe dentro de un task de ECS/Fargate.
    let ecs_uri = std::env::var("ECS_CONTAINER_METADATA_URI_V4")
        .ok()
        .filter(|s| !s.is_empty());
    let in_ecs = ecs_uri.is_some();

    // BD: dialecto real + tamaño/conexiones, leídos del adaptador del runtime (autoridad).
    let (dialect, database) = {
        let rt = st.runtime.lock().await;
        let db = rt.db();
        let dialect = db.dialect();
        let info = collect_database(db, dialect).await;
        (dialect, info)
    };

    // Eje A (backend de datos) = por el dialecto real. Eje B (shell): no es detectable con certeza
    // server-side; se aproxima por el despliegue (ECS o servir estático ⇒ web; si no ⇒ tauri local).
    let backend = match dialect {
        Dialect::Sqlite => "single",
        Dialect::Postgres => "cloud",
    };
    let serves_static = std::env::var("HUB_WEB_DIR")
        .map(|s| !s.is_empty())
        .unwrap_or(false);
    let shell = if in_ecs || serves_static { "web" } else { "tauri" };

    // CPU / memoria: ECS Task Metadata v4 (cloud) o `sysinfo` (local).
    let (cpu, memory) = match &ecs_uri {
        Some(uri) => ecs_metrics(&st.http, uri).await,
        None => local_metrics().await,
    };

    Json(json!({
        "ok": true,
        "data": {
            "backend": backend,
            "shell": shell,
            "hubVersion": format!("v{}", env!("CARGO_PKG_VERSION")),
            "cpu": cpu,
            "memory": memory,
            "database": database,
            // Origen del almacenamiento de documentos/copias (la lista en sí es follow-up).
            "storageSource": if in_ecs { "s3" } else { "disk" },
            "storageUsed": Value::Null,
            "documents": Value::Array(vec![]),
            "backups": Value::Array(vec![]),
            "logs": Value::Array(vec![]),
        }
    }))
    .into_response()
}

// ─────────────────────────── Base de datos ───────────────────────────

/// Motor + tamaño + conexiones reales. SQLite: tamaño por `PRAGMA`, 1 conexión. Postgres: sin
/// tamaño local (Aurora compartida por organización), conexiones por `pg_stat_activity`.
async fn collect_database(db: &dyn erplora_db::DatabaseAdapter, dialect: Dialect) -> Value {
    let no_params = Map::new();
    match dialect {
        Dialect::Sqlite => {
            let pages = scalar_i64(db, "PRAGMA page_count", &no_params).await;
            let page_size = scalar_i64(db, "PRAGMA page_size", &no_params).await;
            let size_label = match (pages, page_size) {
                (Some(p), Some(s)) if p >= 0 && s >= 0 => Some(human_bytes((p as u64) * (s as u64))),
                _ => None,
            };
            json!({
                "engine": "sqlite",
                "sizeLabel": size_label,
                "connections": 1,
                "connectionsLimit": Value::Null,
            })
        }
        Dialect::Postgres => {
            let connections = scalar_i64(
                db,
                "SELECT count(*) AS n FROM pg_stat_activity WHERE datname = current_database()",
                &no_params,
            )
            .await
            .unwrap_or(0);
            let limit = scalar_i64(
                db,
                "SELECT current_setting('max_connections')::int AS n",
                &no_params,
            )
            .await;
            json!({
                "engine": "postgres",
                "sizeLabel": Value::Null,   // Aurora compartida por organización: sin "tamaño local"
                "connections": connections,
                "connectionsLimit": limit,
            })
        }
    }
}

/// Ejecuta una query escalar y devuelve el primer valor de la primera fila como `i64`
/// (tolera que venga como número o como texto). `None` si falla o no hay filas.
async fn scalar_i64(db: &dyn erplora_db::DatabaseAdapter, sql: &str, params: &Map<String, Value>) -> Option<i64> {
    let res = db.query(sql, params).await.ok()?;
    let row = res.rows.first()?;
    let obj = row.as_object()?;
    let v = obj.values().next()?;
    value_to_i64(v)
}

fn value_to_i64(v: &Value) -> Option<i64> {
    match v {
        Value::Number(n) => n.as_i64().or_else(|| n.as_f64().map(|f| f as i64)),
        Value::String(s) => s.trim().parse::<i64>().ok(),
        _ => None,
    }
}

// ─────────────────────────── Métricas: ECS (cloud) ───────────────────────────

/// CPU/memoria desde el ECS Task Metadata Endpoint v4. Defensivo: si algo falta, `fraction: null`
/// (el front muestra el gauge a 0 sin romperse). Una sola llamada a `/task/stats` ya trae `precpu`
/// (la muestra previa del agente) → delta instantáneo válido sin segundo sondeo.
async fn ecs_metrics(http: &reqwest::Client, base: &str) -> (Value, Value) {
    let base = base.trim_end_matches('/');
    let stats = fetch_json(http, &format!("{base}/task/stats")).await;
    let task = fetch_json(http, &format!("{base}/task")).await;

    // Límites del task (vCPU + MiB), si están declarados.
    let task_cpu = task
        .as_ref()
        .and_then(|t| t.pointer("/Limits/CPU"))
        .and_then(|v| v.as_f64());
    let task_mem_mib = task
        .as_ref()
        .and_then(|t| t.pointer("/Limits/Memory"))
        .and_then(|v| v.as_f64());

    let Some(stats) = stats.as_ref().and_then(|s| s.as_object()) else {
        return (Value::Null, Value::Null);
    };

    // Agrega CPU y memoria de todos los contenedores del task (normalmente uno).
    let (mut cpu_delta, mut sys_delta, mut online, mut mem_used) = (0u64, 0u64, 0f64, 0u64);
    for c in stats.values() {
        cpu_delta += sub_u64(c, "/cpu_stats/cpu_usage/total_usage", "/precpu_stats/cpu_usage/total_usage");
        let sd = sub_u64(c, "/cpu_stats/system_cpu_usage", "/precpu_stats/system_cpu_usage");
        sys_delta = sys_delta.max(sd); // el system usage es del host, igual entre contenedores
        if let Some(n) = c.pointer("/cpu_stats/online_cpus").and_then(|v| v.as_f64()) {
            online = online.max(n);
        }
        mem_used += container_mem_used(c);
    }
    if online == 0.0 {
        online = task_cpu.unwrap_or(1.0).max(1.0);
    }

    // Núcleos usados (formula Docker): (cpu_delta / system_delta) * online_cpus.
    let used_cores = if sys_delta > 0 {
        (cpu_delta as f64 / sys_delta as f64) * online
    } else {
        0.0
    };
    let cpu_limit = task_cpu.filter(|c| *c > 0.0).unwrap_or(online);
    let cpu = json!({
        "usedLabel": format!("{} cores", fmt_decimal(used_cores, 2)),
        "limitLabel": format!("{} vCPU", fmt_decimal(cpu_limit, if cpu_limit.fract() == 0.0 { 0 } else { 2 })),
        "fraction": if cpu_limit > 0.0 { Some((used_cores / cpu_limit).clamp(0.0, 1.0)) } else { None },
    });

    let mem_limit = task_mem_mib
        .map(|m| (m * 1024.0 * 1024.0) as u64)
        .filter(|m| *m > 0)
        .or_else(|| {
            // Fallback: límite reportado por el primer contenedor.
            stats
                .values()
                .next()
                .and_then(|c| c.pointer("/memory_stats/limit"))
                .and_then(|v| v.as_u64())
        });
    let memory = json!({
        "usedLabel": human_bytes(mem_used),
        "limitLabel": mem_limit.map(human_bytes),
        "fraction": match mem_limit {
            Some(l) if l > 0 => Some((mem_used as f64 / l as f64).clamp(0.0, 1.0)),
            _ => None,
        },
    });

    (cpu, memory)
}

/// Memoria usada de un contenedor = `usage` − caché de página (cgroup v1 `stats.cache`, v2
/// `stats.inactive_file`), como hace `docker stats`.
fn container_mem_used(c: &Value) -> u64 {
    let usage = c.pointer("/memory_stats/usage").and_then(|v| v.as_u64()).unwrap_or(0);
    let cache = c
        .pointer("/memory_stats/stats/cache")
        .and_then(|v| v.as_u64())
        .or_else(|| c.pointer("/memory_stats/stats/inactive_file").and_then(|v| v.as_u64()))
        .unwrap_or(0);
    usage.saturating_sub(cache)
}

fn sub_u64(v: &Value, a: &str, b: &str) -> u64 {
    let x = v.pointer(a).and_then(|n| n.as_u64()).unwrap_or(0);
    let y = v.pointer(b).and_then(|n| n.as_u64()).unwrap_or(0);
    x.saturating_sub(y)
}

async fn fetch_json(http: &reqwest::Client, url: &str) -> Option<Value> {
    let resp = http.get(url).send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    resp.json::<Value>().await.ok()
}

// ─────────────────────────── Métricas: LOCAL (Tauri/desktop) ───────────────────────────

/// CPU/memoria del SO con `sysinfo`. La medición de CPU necesita dos refrescos separados por un
/// intervalo mínimo → se hace en un hilo bloqueante para no parar el executor async.
async fn local_metrics() -> (Value, Value) {
    let res = tokio::task::spawn_blocking(|| {
        use sysinfo::System;
        let mut sys = System::new();
        sys.refresh_cpu_usage();
        std::thread::sleep(sysinfo::MINIMUM_CPU_UPDATE_INTERVAL);
        sys.refresh_cpu_usage();
        sys.refresh_memory();
        let cores = sys.cpus().len().max(1) as f64;
        let cpu_pct = sys.global_cpu_usage() as f64; // media 0..100 de todos los núcleos
        let used = sys.used_memory(); // bytes
        let total = sys.total_memory(); // bytes
        (cpu_pct, cores, used, total)
    })
    .await;

    let Ok((cpu_pct, cores, used, total)) = res else {
        return (Value::Null, Value::Null);
    };

    let used_cores = (cpu_pct / 100.0) * cores;
    let cpu = json!({
        "usedLabel": format!("{} cores", fmt_decimal(used_cores, 2)),
        "limitLabel": format!("{} núcleos", cores as u64),
        "fraction": (cpu_pct / 100.0).clamp(0.0, 1.0),
    });
    let memory = json!({
        "usedLabel": human_bytes(used),
        "limitLabel": human_bytes(total),
        "fraction": if total > 0 { Some((used as f64 / total as f64).clamp(0.0, 1.0)) } else { None },
    });
    (cpu, memory)
}

// ─────────────────────────── Formato (es-ES) ───────────────────────────

/// Bytes legibles con separador decimal español (coma). p.ej. 642 MB, 1,2 GB, 8,6 MB.
fn human_bytes(bytes: u64) -> String {
    const KIB: f64 = 1024.0;
    const MIB: f64 = KIB * 1024.0;
    const GIB: f64 = MIB * 1024.0;
    let b = bytes as f64;
    if b >= GIB {
        format!("{} GB", fmt_decimal(b / GIB, 1))
    } else if b >= MIB {
        let mb = b / MIB;
        // Sin decimales a partir de 100 MB (ruido); con 1 decimal por debajo.
        format!("{} MB", fmt_decimal(mb, if mb >= 100.0 { 0 } else { 1 }))
    } else if b >= KIB {
        format!("{} KB", fmt_decimal(b / KIB, 0))
    } else {
        format!("{bytes} B")
    }
}

/// Número con `decimals` cifras y coma decimal (es-ES), recortando `,0` sobrante.
fn fmt_decimal(value: f64, decimals: usize) -> String {
    let s = format!("{value:.decimals$}");
    let s = if decimals > 0 {
        s.trim_end_matches('0').trim_end_matches('.').to_string()
    } else {
        s
    };
    s.replace('.', ",")
}
