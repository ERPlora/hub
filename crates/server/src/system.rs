//! `GET /api/system` — estado REAL del sistema (Postgres-only, ADR-0154).
//!
//! Tras ADR-0154 el Hub es Postgres-only y PWA: `backend` es SIEMPRE `"cloud"` y `shell` SIEMPRE
//! `"web"` (ya no hay SQLite/single ni Tauri/desktop, ni detección por dialecto). El runtime es la
//! autoridad: mide las métricas y reporta la BD, nada se infiere en el navegador. Lo que cambia es
//! la FUENTE de CPU/memoria según el despliegue:
//!   • **ECS Task Metadata Endpoint v4** (`/task/stats` + `/task`) si corremos en un task de
//!     ECS/Fargate (proveedor AWS de reserva; existe `ECS_CONTAINER_METADATA_URI_V4`).
//!   • **cgroup v2** (`/sys/fs/cgroup/*`) si corremos en un contenedor Docker (Hetzner/Swarm, infra
//!     activa) — respeta el límite del contenedor, no `/proc` (que vería la RAM del host).
//!   • **`sysinfo`** (uso del SO) como último recurso en desarrollo local (ni ECS ni cgroup v2).
//!
//! Por qué Task Metadata y no CloudWatch (decisión ADR-0046): es la contabilidad **cgroup del
//! propio task** (lo que CloudWatch agrega) pero en **tiempo real, sin IAM/coste/SDK** y respeta el
//! límite del Fargate. Evita el error de leer `/proc` y ver la RAM del host.
//!
//! Documentos/almacenamiento (gateado por `in_ecs`, no por el dialecto): en cloud (ECS) vía el Cloud
//! (`GET /api/v1/hub/device/storage/`, el Hub no tiene credenciales S3); en el resto (Docker/dev),
//! del disco local (`media/`) → por eso `storageSource` es `"s3"` en ECS y `"disk"` en Docker/dev.
//! Logs = outbox de eventos. Las copias, importaciones y restauraciones pertenecen a Ajustes → Datos
//! y copias, no a Sistema.
//!
//! Contrato (camelCase) consumido por `hub/apps/web/src/lib/system.ts`.

use axum::extract::State;
use axum::http::HeaderMap;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::{json, Map, Value};

use crate::{auth, AppState};

/// GET /api/system — métricas + base de datos reales, según el despliegue.
pub async fn system_info(State(st): State<AppState>, headers: HeaderMap) -> Response {
    // Sistema expone logs, métricas y detalles del almacenamiento. Es información interna del Hub:
    // la protección de la ruta Vue no sustituye la autenticación de la API.
    {
        let rt = st.runtime.lock().await;
        if let Err(error) = auth::require_user_session(&headers, &st.config, &rt).await {
            return (
                axum::http::StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": error.message() })),
            )
                .into_response();
        }
    }

    // ¿Estamos en ECS? El endpoint de metadata solo existe dentro de un task de ECS/Fargate.
    let ecs_uri = std::env::var("ECS_CONTAINER_METADATA_URI_V4")
        .ok()
        .filter(|s| !s.is_empty());
    let in_ecs = ecs_uri.is_some();

    // BD + logs (mismo lock del runtime; su outbox es el feed de eventos).
    let (database, logs) = {
        let rt = st.runtime.lock().await;
        let db = rt.db();
        let database = collect_database(db).await;
        let logs = collect_logs(db, &st.hub_id()).await;
        (database, logs)
    };

    // Hub Cloud es Postgres-only y PWA (ADR-0154): backend siempre "cloud", shell siempre "web".
    let backend = "cloud";
    let shell = "web";

    // CPU / memoria: ECS Task Metadata v4 (cloud) o `sysinfo` (local).
    let (cpu, memory) = match &ecs_uri {
        Some(uri) => ecs_metrics(&st.http, uri).await,
        None if in_cgroup_v2() => docker_metrics().await,
        None => local_metrics().await,
    };

    // Documentos / almacenamiento usado. Se gatea por `in_ecs` (no por el dialecto): en
    // cloud va vía Cloud (el Hub no tiene credenciales S3); en local se lee del disco.
    let (documents, storage_used) = if in_ecs {
        cloud_storage(
            &st.http,
            &st.config.cloud_base_url,
            &st.hub_id(),
            st.machine_token(),
        )
        .await
    } else {
        // Carpeta media del hub, resuelta del entorno (igual que el arranque): HUB_MEDIA_DIR o `media`.
        let media_dir = std::env::var("HUB_MEDIA_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| std::path::PathBuf::from("media"));
        local_storage(&media_dir).await
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
            "storageSource": if in_ecs { "s3" } else { "disk" },
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

// ─────────────────────────── Almacenamiento: LOCAL (disco) ───────────────────────────

/// Documentos (raíz de `media/`) y uso de disco — todo del disco local.
async fn local_storage(media_dir: &std::path::Path) -> (Value, Value) {
    let documents = list_dir(media_dir);
    let storage_used = disk_usage(media_dir).await;
    (documents, storage_used)
}

/// Lista ficheros (no dirs ni ocultos) de `dir`, recientes primero (máx 100).
fn list_dir(dir: &std::path::Path) -> Value {
    let rd = match std::fs::read_dir(dir) {
        Ok(rd) => rd,
        Err(_) => return Value::Array(vec![]),
    };
    let mut entries: Vec<(String, u64, std::time::SystemTime)> = rd
        .flatten()
        .filter_map(|e| {
            let path = e.path();
            if !path.is_file() {
                return None;
            }
            let name = path.file_name()?.to_string_lossy().to_string();
            if name.starts_with('.') {
                return None; // .DS_Store y similares
            }
            let meta = std::fs::metadata(&path).ok()?;
            let mtime = meta.modified().unwrap_or(std::time::UNIX_EPOCH);
            Some((name, meta.len(), mtime))
        })
        .collect();
    entries.sort_by(|a, b| b.2.cmp(&a.2));
    entries.truncate(100);
    let items: Vec<Value> = entries
        .into_iter()
        .map(|(name, size, mtime)| {
            let when = fmt_iso(mtime);
            json!({
                "name": name,
                "sizeLabel": human_bytes(size),
                "modified": when,
                "kind": ext_of(&name),
                "url": format!("/api/media/raw?path={}", pct_encode(&name)),
            })
        })
        .collect();
    Value::Array(items)
}

/// Uso del disco que contiene `path` (punto de montaje con el prefijo más largo); si no se
/// identifica, el de mayor capacidad. `null` si no hay datos.
async fn disk_usage(path: &std::path::Path) -> Value {
    let path = path.to_path_buf();
    let res = tokio::task::spawn_blocking(move || {
        use sysinfo::Disks;
        let abs = std::fs::canonicalize(&path).unwrap_or(path);
        let disks = Disks::new_with_refreshed_list();
        let mut best: Option<(usize, u64, u64)> = None; // (len_montaje, total, disponible)
        let mut fallback: Option<(u64, u64)> = None; // (total, disponible) del de mayor total
        for d in disks.iter() {
            let (total, avail) = (d.total_space(), d.available_space());
            if fallback.map(|(t, _)| total > t).unwrap_or(true) {
                fallback = Some((total, avail));
            }
            let mp = d.mount_point();
            if abs.starts_with(mp) {
                let len = mp.as_os_str().len();
                if best.map(|(l, _, _)| len > l).unwrap_or(true) {
                    best = Some((len, total, avail));
                }
            }
        }
        best.map(|(_, t, a)| (t, a)).or(fallback)
    })
    .await
    .ok()
    .flatten();
    match res {
        Some((total, avail)) if total > 0 => {
            let used = total.saturating_sub(avail);
            json!({
                "usedLabel": human_bytes(used),
                "limitLabel": human_bytes(total),
                "fraction": (used as f64 / total as f64).clamp(0.0, 1.0),
            })
        }
        _ => Value::Null,
    }
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

// ─────────────────────────── Métricas: LOCAL (desarrollo, sysinfo) ───────────────────────────

/// CPU/memoria del SO con `sysinfo`. Fallback de desarrollo local (ni ECS ni cgroup v2). La medición
/// de CPU necesita dos refrescos separados por un intervalo mínimo → se hace en un hilo bloqueante
/// para no parar el executor async.
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

// ─────────────────────────── Métricas: DOCKER (Hetzner, cgroup v2) ───────────────────────────

/// ¿Contenedor con cgroup v2? (Docker en Hetzner). El fichero solo existe dentro del contenedor.
fn in_cgroup_v2() -> bool {
    std::path::Path::new("/sys/fs/cgroup/memory.current").exists()
}

fn read_str(path: &str) -> Option<String> {
    std::fs::read_to_string(path).ok()
}

/// `memory.max`: número (bytes) o `"max"` (sin límite → None).
fn parse_mem_max(s: &str) -> Option<u64> {
    let s = s.trim();
    if s == "max" {
        None
    } else {
        s.parse().ok()
    }
}

/// `inactive_file` de `memory.stat` = caché de página a restar (como `docker stats` en cgroup v2).
fn parse_mem_inactive_file(stat: &str) -> u64 {
    stat.lines()
        .find_map(|l| {
            l.strip_prefix("inactive_file ")
                .and_then(|v| v.trim().parse().ok())
        })
        .unwrap_or(0)
}

/// `usage_usec` acumulado de `cpu.stat` (μs de CPU consumidos).
fn parse_cpu_usage_usec(stat: &str) -> Option<u64> {
    stat.lines().find_map(|l| {
        l.strip_prefix("usage_usec ")
            .and_then(|v| v.trim().parse().ok())
    })
}

/// `cpu.max` = `"<quota> <period>"`; `"max <period>"` = sin límite → None. Devuelve cores (quota/period).
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

/// CPU/memoria del CONTENEDOR vía cgroup v2 — respeta el límite que el SaaS asigna según el plan
/// (no `/proc/meminfo`, que ve el host). La UI muestra solo el `%`, así que devolvemos solo `fraction`.
async fn docker_metrics() -> (Value, Value) {
    let res = tokio::task::spawn_blocking(|| {
        let mem_used = read_str("/sys/fs/cgroup/memory.current")
            .and_then(|s| s.trim().parse::<u64>().ok())
            .unwrap_or(0)
            .saturating_sub(
                read_str("/sys/fs/cgroup/memory.stat")
                    .map(|s| parse_mem_inactive_file(&s))
                    .unwrap_or(0),
            );
        let mem_limit = read_str("/sys/fs/cgroup/memory.max").and_then(|s| parse_mem_max(&s));

        let usec_1 = read_str("/sys/fs/cgroup/cpu.stat")
            .and_then(|s| parse_cpu_usage_usec(&s))
            .unwrap_or(0);
        std::thread::sleep(std::time::Duration::from_millis(100));
        let usec_2 = read_str("/sys/fs/cgroup/cpu.stat")
            .and_then(|s| parse_cpu_usage_usec(&s))
            .unwrap_or(0);
        let cores_used = usec_2.saturating_sub(usec_1) as f64 / 100_000.0; // 100 ms = 100_000 μs
        let cpu_limit = read_str("/sys/fs/cgroup/cpu.max").and_then(|s| parse_cpu_max_cores(&s));

        (mem_used, mem_limit, cores_used, cpu_limit)
    })
    .await;

    let Ok((mem_used, mem_limit, cores_used, cpu_limit)) = res else {
        return (Value::Null, Value::Null);
    };

    let cpu = json!({
        "fraction": cpu_limit
            .filter(|l| *l > 0.0)
            .map(|l| (cores_used / l).clamp(0.0, 1.0)),
    });
    let memory = json!({
        "fraction": mem_limit
            .filter(|l| *l > 0)
            .map(|l| (mem_used as f64 / l as f64).clamp(0.0, 1.0)),
    });
    (cpu, memory)
}

#[cfg(test)]
mod cgroup_tests {
    use super::{
        parse_cpu_max_cores, parse_cpu_usage_usec, parse_mem_inactive_file, parse_mem_max,
    };

    #[test]
    fn mem_max_numero_o_max() {
        assert_eq!(parse_mem_max("134217728\n"), Some(134_217_728)); // 128 MiB
        assert_eq!(parse_mem_max("max\n"), None); // sin límite
    }

    #[test]
    fn cpu_usage_usec() {
        let stat = "usage_usec 1234567\nuser_usec 1\nsystem_usec 2\n";
        assert_eq!(parse_cpu_usage_usec(stat), Some(1_234_567));
        assert_eq!(parse_cpu_usage_usec("nr_throttled 0\n"), None);
    }

    #[test]
    fn cpu_max_cores() {
        assert_eq!(parse_cpu_max_cores("100000 100000"), Some(1.0)); // 1 vCPU
        assert_eq!(parse_cpu_max_cores("50000 100000"), Some(0.5));
        assert_eq!(parse_cpu_max_cores("max 100000"), None); // sin límite
    }

    #[test]
    fn mem_inactive_file() {
        assert_eq!(
            parse_mem_inactive_file("anon 10\ninactive_file 4096\nfile 8192\n"),
            4096
        );
        assert_eq!(parse_mem_inactive_file("anon 10\n"), 0);
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

/// Extensión en minúsculas sin punto (`""` si no hay).
fn ext_of(name: &str) -> String {
    name.rsplit_once('.')
        .map(|(_, e)| e.to_lowercase())
        .filter(|e| !e.is_empty() && e.len() <= 8)
        .unwrap_or_default()
}

/// Percent-encode mínimo (RFC 3986 unreserved) para el querystring de `/api/media/raw?path=`.
fn pct_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// `SystemTime` → ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`). Algoritmo civil de Howard Hinnant
/// (sin dependencias de fecha). El front lo parsea con `new Date(iso)`.
fn fmt_iso(t: std::time::SystemTime) -> String {
    let secs = t
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0) as i64;
    let days = secs.div_euclid(86_400);
    let rem = secs.rem_euclid(86_400);
    let (hh, mm, ss) = (rem / 3600, (rem % 3600) / 60, rem % 60);
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    format!("{y:04}-{m:02}-{d:02}T{hh:02}:{mm:02}:{ss:02}Z")
}
