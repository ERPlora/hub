//! `GET /api/system` — estado REAL del sistema (Postgres-only, ADR-0154).
//!
//! Tras ADR-0154 el Hub es Postgres-only, PWA y cloud-only: `backend` es SIEMPRE `"cloud"`, `shell`
//! SIEMPRE `"web"` y `storageSource` SIEMPRE `"s3"` (ya no hay SQLite/single, Tauri/desktop ni disco
//! local — todo eso murió con ADR-0154). El runtime es la autoridad: mide las métricas y reporta la
//! BD, nada se infiere en el navegador. Lo que cambia es la FUENTE de CPU/memoria según el despliegue:
//!   • **ECS Task Metadata Endpoint v4** (`/task/stats` + `/task`) si corremos en un task de
//!     ECS/Fargate (proveedor AWS de reserva; existe `ECS_CONTAINER_METADATA_URI_V4`).
//!   • **cgroup v2** (`/sys/fs/cgroup/*`) si corremos en un contenedor Docker (Hetzner/Swarm, infra
//!     activa) — respeta el límite del contenedor, no `/proc` (que vería la RAM del host).
//!   • En **desarrollo local** (ni ECS ni cgroup v2) no hay métricas de host → `cpu`/`memory` = null.
//!
//! Por qué Task Metadata y no CloudWatch (decisión ADR-0046): es la contabilidad **cgroup del
//! propio task** (lo que CloudWatch agrega) pero en **tiempo real, sin IAM/coste/SDK** y respeta el
//! límite del Fargate. Evita el error de leer `/proc` y ver la RAM del host.
//!
//! Documentos/almacenamiento: SIEMPRE vía el Cloud (`GET /api/v1/hub/device/storage/`, `X-Hub-Token`
//! + `X-Hub-Id`) — el Hub no tiene credenciales S3, así que nunca lee del disco. Logs = outbox de
//! eventos. Las copias, importaciones y restauraciones pertenecen a Ajustes → Datos y copias, no a
//! Sistema.
//!
//! Contrato (camelCase) consumido por `hub/apps/web/src/lib/system.ts`.

use axum::extract::{Query, State};
use axum::http::HeaderMap;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::{json, Map, Value};

use crate::{auth, AppState, LocaleQuery};

/// `GET /api/system/update-history` — what we changed on this hub, and from which version
/// (hub#564, ADR-0269 §3.5).
///
/// We update on our own, always, without asking and without cutting service. The counterpart we owe
/// the owner is **transparency**: they do not get to choose *when*, so they are owed *what*. This is
/// the door that answers it, and it is READ-ONLY on purpose — there is no update control for the
/// owner here and there must not be one, because a button to postpone is the thing ADR-0269
/// decided against.
///
/// Only what MOVED comes back (a hub nobody has updated answers an empty list), newest first, no
/// further back than the window. Names are the ones the owner reads, translated to `?locale=`.
///
/// `reason` travels but the screen does not print it: it is the verbatim error behind a rollback,
/// which is the first thing we ask for on an incident and the last thing to put in front of
/// somebody running a hairdresser's.
pub async fn update_history(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<LocaleQuery>,
) -> Response {
    // Which versions this hub runs is a map of its attack surface: an unauthenticated reader would
    // learn exactly which known bug applies. Same session gate as `/api/system`.
    let locale = q.locale.as_deref().unwrap_or("en");
    let rt = st.runtime.read().await;
    if let Err(error) = auth::require_user_session(&headers, &st.config, &rt).await {
        return (
            axum::http::StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": error.message() })),
        )
            .into_response();
    }

    let entries = match erplora_runtime::update_history::recent(
        rt.db(),
        &st.hub_id(),
        erplora_runtime::update_history::DEFAULT_LIMIT,
        erplora_runtime::update_history::DEFAULT_MAX_AGE_DAYS,
    )
    .await
    {
        Ok(entries) => entries,
        Err(e) => {
            return (
                axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({ "ok": false, "error": e.to_string() })),
            )
                .into_response()
        }
    };

    let registry = rt.registry();
    let data: Vec<Value> = entries
        .iter()
        .map(|e| {
            json!({
                "component": e.component,
                "id": e.id,
                "name": erplora_runtime::update_history::display_name(registry, e, locale),
                "from": e.from_version,
                "to": e.to_version,
                "outcome": e.outcome,
                "reason": e.reason,
                "at": e.at,
            })
        })
        .collect();

    Json(json!({ "ok": true, "data": data })).into_response()
}

/// GET /api/system — métricas + base de datos reales, según el despliegue.
pub async fn system_info(State(st): State<AppState>, headers: HeaderMap) -> Response {
    // Sistema expone logs, métricas y detalles del almacenamiento. Es información interna del Hub:
    // la protección de la ruta Vue no sustituye la autenticación de la API.
    {
        let rt = st.runtime.read().await;
        if let Err(error) = auth::require_user_session(&headers, &st.config, &rt).await {
            return (
                axum::http::StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": error.message() })),
            )
                .into_response();
        }
    }

    // ¿Estamos en ECS? El Task Metadata Endpoint solo existe dentro de un task de ECS/Fargate
    // (proveedor AWS de reserva). En Hetzner/Docker (infra activa) no existe → cgroup v2.
    let ecs_uri = std::env::var("ECS_CONTAINER_METADATA_URI_V4")
        .ok()
        .filter(|s| !s.is_empty());

    // BD + logs (mismo lock del runtime; su outbox es el feed de eventos).
    let (database, logs) = {
        let rt = st.runtime.read().await;
        let db = rt.db();
        let database = collect_database(db).await;
        let logs = collect_logs(db, &st.hub_id()).await;
        (database, logs)
    };

    // Hub Cloud es Postgres-only y PWA (ADR-0154): backend siempre "cloud", shell siempre "web".
    let backend = "cloud";
    let shell = "web";

    // CPU / memoria según el despliegue: ECS Task Metadata v4 (AWS de reserva) o cgroup v2
    // (Hetzner/Docker, activo). En desarrollo local (ni ECS ni cgroup) no hay métricas de host.
    let (cpu, memory) = match &ecs_uri {
        Some(uri) => ecs_metrics(&st.http, uri).await,
        None if in_cgroup_v2() => docker_metrics().await,
        None => (Value::Null, Value::Null),
    };

    // Documentos / almacenamiento SIEMPRE vía el Cloud (Postgres-only, ADR-0154): el Hub no tiene
    // credenciales S3, así que firma hacia `GET /api/v1/hub/device/storage/` con su token de máquina.
    let (documents, storage_used) = cloud_storage(
        &st.http,
        &st.config.cloud_base_url,
        &st.hub_id(),
        st.machine_token(),
    )
    .await;

    Json(json!({
        "ok": true,
        "data": {
            "backend": backend,
            "shell": shell,
            "hubVersion": crate::version::display(),
            "cpu": cpu,
            "memory": memory,
            "database": database,
            "storageSource": "s3",
            "storageUsed": storage_used,
            "documents": documents,
            "logs": logs,
        }
    }))
    .into_response()
}

// ─────────────────────────── Base de datos ───────────────────────────

/// Motor + conexiones reales (Postgres-only, ADR-0154). Sin "tamaño local" (BD Postgres compartida
/// por organización); conexiones por `pg_stat_activity`.
async fn collect_database(db: &dyn erplora_db::DatabaseAdapter) -> Value {
    let no_params = Map::new();
    let connections = scalar_i64(
        db,
        "SELECT count(*) AS n FROM pg_stat_activity WHERE datname = current_database()",
        &no_params,
    )
    .await
    .unwrap_or(0);
    // Límite CONTRATADO = el CONNECTION LIMIT del rol del hub (lo fija Cloud al provisionar
    // según el plan: `ALTER ROLE … CONNECTION LIMIT n`). `rolconnlimit = -1` ⇒ el rol no
    // tiene tope propio → caemos al `max_connections` del cluster (tope físico del servidor).
    let role_limit = scalar_i64(
        db,
        "SELECT rolconnlimit FROM pg_roles WHERE rolname = current_user",
        &no_params,
    )
    .await
    .filter(|&n| n >= 0);
    let limit = match role_limit {
        Some(n) => Some(n),
        None => {
            scalar_i64(
                db,
                "SELECT current_setting('max_connections')::int AS n",
                &no_params,
            )
            .await
        }
    };
    json!({
        "engine": "postgres",
        "sizeLabel": Value::Null,   // BD Postgres compartida por organización: sin "tamaño local"
        "connections": connections,
        "connectionsLimit": limit,
    })
}

/// Ejecuta una query escalar y devuelve el primer valor de la primera fila como `i64`
/// (tolera que venga como número o como texto). `None` si falla o no hay filas.
async fn scalar_i64(
    db: &dyn erplora_db::DatabaseAdapter,
    sql: &str,
    params: &Map<String, Value>,
) -> Option<i64> {
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

// ─────────────────────────── Logs (outbox de eventos) ───────────────────────────

/// Últimos eventos del outbox del runtime como feed de "registros". El nivel se deriva del estado:
/// error/`dead` → ERROR, `pending` → WARN, resto → INFO. Devuelve `[]` si la tabla aún no existe.
async fn collect_logs(db: &dyn erplora_db::DatabaseAdapter, hub_id: &str) -> Value {
    let mut params = Map::new();
    params.insert("hub_id".into(), Value::String(hub_id.to_string()));
    let sql = "SELECT event_name, status, last_error, created_at \
               FROM _event_outbox WHERE hub_id = :hub_id ORDER BY created_at DESC LIMIT 50";
    let rows = match db.query(sql, &params).await {
        Ok(r) => r.rows,
        Err(_) => return Value::Array(vec![]),
    };
    let logs: Vec<Value> = rows
        .iter()
        .filter_map(|row| {
            let o = row.as_object()?;
            let s = |k: &str| o.get(k).and_then(|v| v.as_str()).unwrap_or("").to_string();
            let status = s("status");
            let err = s("last_error");
            let level = if !err.is_empty() || status == "dead" {
                "ERROR"
            } else if status == "pending" {
                "WARN"
            } else {
                "INFO"
            };
            let meta = if err.is_empty() { status } else { err };
            Some(json!({ "when": s("created_at"), "level": level, "message": s("event_name"), "meta": meta }))
        })
        .collect();
    Value::Array(logs)
}

// ─────────────────────────── Almacenamiento: CLOUD (proxy a Cloud) ───────────────────────────

/// Documentos/uso vía el Cloud (`GET /api/v1/hub/device/storage/`, `X-Hub-Token`+`X-Hub-Id`).
/// El Cloud devuelve datos crudos (bytes/ISO) y aquí se formatean al contrato. `[]`/`null` si falla.
async fn cloud_storage(
    http: &reqwest::Client,
    cloud_base_url: &str,
    hub_id: &str,
    token: Option<String>,
) -> (Value, Value) {
    let empty = (Value::Array(vec![]), Value::Null);
    let Some(token) = token else { return empty };
    let url = format!(
        "{}/api/v1/hub/device/storage/",
        cloud_base_url.trim_end_matches('/')
    );
    let resp = http
        .get(&url)
        .header("X-Hub-Token", token)
        .header("X-Hub-Id", hub_id)
        .send()
        .await;
    let Ok(resp) = resp else { return empty };
    if !resp.status().is_success() {
        return empty;
    }
    let Ok(body) = resp.json::<Value>().await else {
        return empty;
    };

    let documents: Vec<Value> = body
        .get("documents")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .map(|d| {
                    let bytes = d.get("bytes").and_then(|v| v.as_u64()).unwrap_or(0);
                    json!({
                        "name": d.get("name").cloned().unwrap_or(Value::Null),
                        "sizeLabel": human_bytes(bytes),
                        "modified": d.get("modified").cloned().unwrap_or(Value::Null),
                        "kind": d.get("kind").cloned().unwrap_or(Value::Null),
                        "url": Value::Null,
                    })
                })
                .collect()
        })
        .unwrap_or_default();

    let storage_used = body
        .get("usage")
        .map(|u| {
            let used = u.get("used_bytes").and_then(|v| v.as_u64()).unwrap_or(0);
            let limit = u.get("limit_bytes").and_then(|v| v.as_u64());
            json!({
                "usedLabel": human_bytes(used),
                "limitLabel": limit.map(human_bytes),
                "fraction": match limit {
                    Some(l) if l > 0 => Some((used as f64 / l as f64).clamp(0.0, 1.0)),
                    _ => None,
                },
            })
        })
        .unwrap_or(Value::Null);

    (Value::Array(documents), storage_used)
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
        cpu_delta += sub_u64(
            c,
            "/cpu_stats/cpu_usage/total_usage",
            "/precpu_stats/cpu_usage/total_usage",
        );
        let sd = sub_u64(
            c,
            "/cpu_stats/system_cpu_usage",
            "/precpu_stats/system_cpu_usage",
        );
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
    let usage = c
        .pointer("/memory_stats/usage")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let cache = c
        .pointer("/memory_stats/stats/cache")
        .and_then(|v| v.as_u64())
        .or_else(|| {
            c.pointer("/memory_stats/stats/inactive_file")
                .and_then(|v| v.as_u64())
        })
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

// ─────────────────────────── Métricas: DOCKER (Hetzner, cgroup v2) ───────────────────────────

/// ¿Contenedor con cgroup v2? (Docker en Hetzner). El fichero solo existe dentro del contenedor.
fn in_cgroup_v2() -> bool {
    std::path::Path::new("/sys/fs/cgroup/memory.current").exists()
}

/// Contrato de la pestaña Recursos: SOLO `{ "fraction": f64|null }` por gauge (la UI pinta %; los
/// absolutos viven en `/api/system/metrics`). `null` = no medible («n/a») — un fallo parcial de
/// muestreo NUNCA se disfraza de 0% o 100%. Devuelve `(cpu, memory)`.
fn fractions_json(
    memory: &crate::system_metrics::MemoryMetric,
    cpu: &crate::system_metrics::CpuMetric,
) -> (Value, Value) {
    (
        json!({ "fraction": cpu.fraction }),
        json!({ "fraction": memory.fraction }),
    )
}

/// CPU/memoria del CONTENEDOR vía cgroup v2 — respeta el límite que el SaaS asigna según el plan
/// (no `/proc/meminfo`, que ve el host). Mismo lector/sampler testeado que `/api/system/metrics`
/// (`system_metrics::sample_cgroup` tras el trait `CgroupReader`): una sola implementación en el
/// crate; ambos endpoints no pueden divergir.
async fn docker_metrics() -> (Value, Value) {
    let sampled = tokio::task::spawn_blocking(|| {
        crate::system_metrics::sample_cgroup(&crate::system_metrics::SysCgroupReader)
    })
    .await;
    let Ok((memory, cpu)) = sampled else {
        return (Value::Null, Value::Null);
    };
    fractions_json(&memory, &cpu)
}

#[cfg(test)]
mod resources_tests {
    //! Pestaña Recursos (hub#207/#203, ADR-0154 §8: telemetría REAL): las fracciones de los gauges
    //! salen del MISMO lector de cgroup v2 testeado que `/api/system/metrics` (`CgroupReader`),
    //! nunca de una copia paralela de parsers. Fallo parcial de muestreo = `null` («n/a»), no un
    //! 0%/100% inventado.
    use super::fractions_json;
    use crate::system_metrics::{cpu_metric, read_cpu_limit_cores, read_memory, CgroupReader};
    use serde_json::json;
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
    fn recursos_fracciones_con_la_config_real_del_free_prod() {
        // Config REAL del contenedor free en prod (hub-ioanbeilicshell2, 2026-07-27):
        // memory.max = 100663296 (96 MiB, ADR-0154: el free subió de 64 a 96) y
        // cpu.max = "10000 100000" (cpuLimit 0.10). El gauge de RAM debe salir del cgroup
        // DEL CONTENEDOR: 7 340 032 B usados / 96 MiB ≈ 7%.
        let r = FakeCgroup::new(&[
            ("memory.current", "7647232\n"), // 7 340 032 anon + 307 200 de caché
            ("memory.stat", "anon 7340032\ninactive_file 307200\n"),
            ("memory.max", "100663296\n"),
            ("cpu.max", "10000 100000\n"),
        ]);
        let memory = read_memory(&r);
        // 20 000 μs de CPU en 200 000 μs = 0.1 cores = 100% del límite 0.10.
        let cpu = cpu_metric(
            Some(1_000_000),
            Some(1_020_000),
            200_000,
            read_cpu_limit_cores(&r),
        );

        let (cpu_json, mem_json) = fractions_json(&memory, &cpu);
        // Contrato de la pestaña Recursos: SOLO la fracción (la UI pinta %; sin absolutos).
        let mf = mem_json["fraction"].as_f64().expect("fracción de memoria");
        assert!((mf - 7_340_032.0 / 100_663_296.0).abs() < 1e-9);
        assert_eq!(mem_json.as_object().unwrap().len(), 1);
        let cf = cpu_json["fraction"].as_f64().expect("fracción de cpu");
        assert!((cf - 1.0).abs() < 1e-9);
        assert_eq!(cpu_json.as_object().unwrap().len(), 1);
    }

    #[test]
    fn recursos_sin_muestra_de_cpu_es_na_no_un_cero_inventado() {
        // Si falta una muestra de `cpu.stat` la fracción es `null` («n/a») — antes el muestreo
        // hacía `unwrap_or(0)` y un fallo parcial podía pintar 0% o clavarse en 100%.
        let r = FakeCgroup::new(&[
            ("memory.current", "7647232\n"),
            ("memory.max", "100663296\n"),
        ]);
        let memory = read_memory(&r);
        let cpu = cpu_metric(None, Some(1_000), 200_000, None);
        let (cpu_json, mem_json) = fractions_json(&memory, &cpu);
        assert_eq!(cpu_json, json!({ "fraction": null }));
        assert!(mem_json["fraction"].as_f64().is_some());
    }

    #[test]
    fn recursos_fuera_de_contenedor_todo_na() {
        // Sin cgroup (dev/Mac): memoria y CPU en `null`, jamás un 0% que parezca medido.
        let empty = FakeCgroup::new(&[]);
        let memory = read_memory(&empty);
        let cpu = cpu_metric(None, None, 200_000, None); // sin muestras = no disponible
        let (cpu_json, mem_json) = fractions_json(&memory, &cpu);
        assert_eq!(cpu_json, json!({ "fraction": null }));
        assert_eq!(mem_json, json!({ "fraction": null }));
    }
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
