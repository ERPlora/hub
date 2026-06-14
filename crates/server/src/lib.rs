//! erplora-server — servidor Axum del runtime del tenant en modo cloud (ARQUITECTURA.md §7.5).
//!
//! Expone `execute_query`/`execute_command` por HTTP, los eventos por WebSocket (`/ws`), y la
//! **gestión de módulos** (listar / instalar / activar / desactivar / desinstalar = hot-plug).
//!
//! Rutas:
//!   GET  /healthz
//!   GET  /api/navigation                     menú de módulos ACTIVOS
//!   GET  /api/modules                        módulos instalados + estado
//!   POST /api/modules/install   {dir}        instala desde carpeta (extraída por erplora-source)
//!   POST /api/modules/:id/activate
//!   POST /api/modules/:id/deactivate
//!   POST /api/modules/:id/uninstall
//!   POST /api/query   {name, params}
//!   POST /api/command {name, payload}
//!   GET  /ws                                 stream de eventos (solo push)

use axum::body::Body;
use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::{Path, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use futures_util::StreamExt;
use serde::Deserialize;
use serde_json::{json, Map, Value};

pub mod assistant;
pub mod auth;
pub mod backup;
pub mod embed;
pub mod ingest;
pub mod install;
pub mod logging;
pub mod media;
pub mod router;
pub mod session;
pub mod state;
pub mod system;
pub mod tenant;

pub use state::{AppState, AuthMode, HubConfig, MachineToken, DEV_HUB_ID, WsEvent};
pub use tenant::{
    EnvOrgResolver, OrgDescriptor, OrgId, OrgResolver, RuntimeFactory, TenantError, TenantRouter,
};

/// Configuración de arranque del runtime **embebible** — la usan el binario (`main.rs`) y el shell
/// **Tauri in-process** (§11). Envuelve la [`HubConfig`] de despliegue + parámetros de proceso.
#[derive(Clone, Debug)]
pub struct ServeConfig {
    /// Ruta del fichero SQLite (se crea si no existe).
    pub sqlite_path: String,
    /// Dirección de escucha. Por defecto `127.0.0.1:8787`.
    pub bind: String,
    /// Carpeta opcional de módulos a instalar al arrancar (hub vacío / dev).
    pub modules_dir: Option<String>,
    /// Configuración de despliegue (hub_id, Cloud, `auth_mode`, token de máquina…).
    pub hub: HubConfig,
    /// Celda **externa** del token de máquina (hot-reload). Si `Some`, el runtime la comparte con
    /// el shell Tauri, que la actualiza tras enrolar/rotar sin reiniciar la app. Si `None`, el
    /// runtime crea la suya sembrada con `hub.cloud_api_token` (caso binario/ECS).
    pub machine_token_cell: Option<state::MachineToken>,
}

impl ServeConfig {
    /// Igual que el binario: `HUB_SQLITE_PATH` / `HUB_BIND` / `HUB_MODULES_DIR` + [`HubConfig::from_env`].
    pub fn from_env() -> Self {
        Self {
            sqlite_path: std::env::var("HUB_SQLITE_PATH").unwrap_or_else(|_| "erplora.db".into()),
            bind: std::env::var("HUB_BIND").unwrap_or_else(|_| "127.0.0.1:8787".into()),
            modules_dir: std::env::var("HUB_MODULES_DIR").ok().filter(|s| !s.is_empty()),
            hub: HubConfig::from_env(),
            machine_token_cell: None,
        }
    }
}

/// Trae la clave pública RSA del Cloud (`GET /api/v1/auth/public-key/`) para verificar los JWT de
/// usuario offline. `None` si el Cloud no responde o no la trae.
async fn fetch_jwt_public_key(cloud_base_url: &str) -> Option<String> {
    let url = format!("{}/api/v1/auth/public-key/", cloud_base_url.trim_end_matches('/'));
    let resp = reqwest::Client::new().get(&url).send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: Value = resp.json().await.ok()?;
    v.get("public_key").and_then(|k| k.as_str()).filter(|s| !s.is_empty()).map(|s| s.to_string())
}

/// Resuelve el SQL de seed de configuración inicial desde el entorno (hub#36):
///  - `HUB_SEED_SQL` — SQL inline (gana si está presente y no vacío). Lo usa ECS/terraform.
///  - `HUB_SEED_SQL_PATH` — ruta a un fichero `.sql` (alternativa para local/dev).
///
/// `Ok(None)` si no se configura ninguno (arranque normal sin seed). Un `HUB_SEED_SQL_PATH` que
/// no se puede leer es un error de configuración → aborta el arranque con un mensaje claro.
fn load_seed_sql() -> Result<Option<String>, Box<dyn std::error::Error>> {
    if let Some(sql) = std::env::var("HUB_SEED_SQL").ok().filter(|s| !s.trim().is_empty()) {
        return Ok(Some(sql));
    }
    if let Some(path) = std::env::var("HUB_SEED_SQL_PATH").ok().filter(|s| !s.trim().is_empty()) {
        let sql = std::fs::read_to_string(&path)
            .map_err(|e| format!("HUB_SEED_SQL_PATH={path}: no se pudo leer el seed: {e}"))?;
        return Ok(Some(sql));
    }
    Ok(None)
}

/// Arranca el runtime completo y **sirve Axum** en `cfg.bind` hasta que termina. Punto de entrada
/// único del binario y del shell Tauri (in-process, §11): abre SQLite, instala los módulos del dir
/// si se indica, resuelve la clave pública del Cloud si falta, monta el [`AppState`], lanza el
/// **relay del outbox** (poll 1s + backoff, §5.4) y sirve. La credencial de máquina viaja en
/// `cfg.hub.cloud_api_token` (Tauri la inyecta desde el keychain; ECS desde el env).
pub async fn serve(mut cfg: ServeConfig) -> Result<(), Box<dyn std::error::Error>> {
    use erplora_db::SqliteAdapter;
    use erplora_runtime::Runtime;

    use erplora_vector::{SqliteVectorStore, VectorStore};

    // Logging del hub → consola + `media/_logs/` (rotación diaria, retención 6 meses, ADR-0047).
    // Se monta lo primero para capturar el arranque. El guard se mantiene vivo toda la función
    // (al soltarlo se pierden los logs en cola del appender no-bloqueante).
    let _log_guard = logging::init(&cfg.hub.media_dir);

    // Path del SQLite del hub: fuente del dump de backup (`VACUUM INTO`); se captura antes de mover
    // `cfg` al state.
    let sqlite_path = cfg.sqlite_path.clone();
    // sqlx-style URL: `sqlite://<path>?mode=rwc` crea el fichero si falta.
    let sqlite_url = format!("sqlite://{}?mode=rwc", sqlite_path);
    let db = SqliteAdapter::connect(&sqlite_url).await?;
    // El runtime se construye con el `hub_id` del despliegue (config, no spoofable): scope del
    // estado de módulos (`hub_module`) y de las migraciones de sistema (hub#31 / hub#37).
    let mut runtime = Runtime::with_hub_id(Box::new(db), cfg.hub.hub_id.clone());

    // Plugins nativos first-party (ADR-0009): motores compliance-crítico horneados en el
    // runtime. Hoy solo `verifactu` (cadena fiscal + transmisión AEAT TLS-mutua).
    runtime.register_native(
        "verifactu",
        std::sync::Arc::new(erplora_verifactu::VerifactuEngine),
    );

    if let Some(dir) = &cfg.modules_dir {
        // Instala los módulos del dir resolviendo el orden de `depends_on` por topo-sort (hub#16):
        // una dependencia se instala antes que quien la declara, sin depender del orden del FS.
        // `install_all_from_dir` es tolerante (loguea ✓/✗ por módulo y salta los rotos); aquí solo
        // registramos un error externo (read_dir fallido o ciclo de dependencias del conjunto).
        if let Err(e) = runtime.install_all_from_dir(std::path::Path::new(dir)).await {
            eprintln!("✗ instalación de módulos: {e}");
        }
    }

    // En `HUB_AUTH=session` el login cloud necesita la clave pública RSA del Cloud; el PIN no. Si no
    // se logra traer, se arranca igual (login cloud quedará no disponible).
    if cfg.hub.auth_mode == AuthMode::Session && cfg.hub.jwt_public_key.is_none() {
        cfg.hub.jwt_public_key = fetch_jwt_public_key(&cfg.hub.cloud_base_url).await;
        if cfg.hub.jwt_public_key.is_none() {
            eprintln!("auth: sin clave pública del Cloud → login cloud no disponible (PIN sí)");
        }
    }
    eprintln!("auth: modo {:?}", cfg.hub.auth_mode);

    // Índice vectorial local (§9.2b routing + §9.6 ingestión). Opción A de §9.5: vectores en una
    // tabla SQLite + coseno por fuerza bruta, sobre una conexión propia al MISMO fichero del hub
    // (la tabla `knowledge_chunk` es independiente de los datos de negocio). La generación de
    // embeddings sigue yendo SIEMPRE por el Cloud (§9.3); este store solo guarda/busca vectores.
    let vector_db = SqliteAdapter::connect(&sqlite_url).await?;
    let vector_store = SqliteVectorStore::new(vector_db);
    vector_store.ensure_schema().await?;
    let vector_store: state::SharedVectorStore = std::sync::Arc::new(vector_store);

    // Celda del token de máquina: externa (compartida con el shell Tauri para hot-reload) o propia.
    let state = match cfg.machine_token_cell.take() {
        Some(cell) => AppState::with_config_cell(runtime, cfg.hub, cell),
        None => AppState::with_config(runtime, cfg.hub),
    }
    .with_vector(vector_store);
    // Tablas de sistema del runtime (outbox + scheduler) — para el caso de hub vacío sin módulos.
    state.runtime.lock().await.ensure_system_tables().await?;

    // Seed de configuración inicial (hub#36): SQL idempotente que se aplica UNA vez al arrancar,
    // tras las tablas de sistema. Mecanismo genérico (NO "modo demo"): el host lo pasa por env —
    // `HUB_SEED_SQL` (SQL inline, p. ej. el del despliegue demo) o `HUB_SEED_SQL_PATH` (fichero).
    // Si ambos están, gana el inline. La idempotencia la garantiza el propio SQL (`WHERE NOT
    // EXISTS`/`ON CONFLICT`). Un seed roto aborta el arranque (error claro), no se traga en silencio.
    if let Some(seed_sql) = load_seed_sql()? {
        let n = state.runtime.lock().await.apply_seed(&seed_sql).await?;
        eprintln!("seed: aplicadas {n} sentencia(s) de configuración inicial");
    }

    // Transporte de `host.notify` (ADR-0012): cliente real de email/sms/whatsapp. Hoy un MOCK
    // (decisión de dependencia del humano para el SMTP/SMS reales; ver crates/runtime/host_notify.rs).
    // El mock pasa por el Outbox como cualquier transporte, así que la mecánica de reintentos/
    // dead-letter del listener-host queda real. TODO: sustituir por el transporte real (lettre/HTTP).
    state
        .runtime
        .lock()
        .await
        .set_notify_transport(std::sync::Arc::new(erplora_runtime::host_notify::MockTransport::new()));

    // Transporte de `host.backup_upload` (ADR-0040/0042, opción B): dump consistente del SQLite
    // (`VACUUM INTO`) + STREAM `POST` al Cloud, que lo guarda en S3 con cifrado de SERVIDOR (SSE).
    // El hub NO cifra ni habla con S3. Si el hub está **enrolado** (hay token de máquina) se registra
    // el transporte REAL (`backup::CloudBackupTransport`); si no, el MOCK (que "streamea" un dump
    // sintético) para que la mecánica Outbox (reintentos/dead-letter) siga real en dev/sin Cloud.
    {
        let real = backup::build_transport(
            sqlite_path.clone(),
            &state.config.cloud_base_url,
            state.config.hub_id.clone(),
            state.machine_token.clone(),
            state.http.clone(),
        );
        let transport: std::sync::Arc<dyn erplora_runtime::host_backup::BackupTransport> = match real {
            Some(t) => {
                eprintln!("backup: transporte real (dump + stream al Cloud) activo");
                t
            }
            None => {
                eprintln!("backup: hub sin enrolar → transporte MOCK (no sube al Cloud)");
                std::sync::Arc::new(erplora_runtime::host_backup::MockTransport::new())
            }
        };
        state.runtime.lock().await.set_backup_transport(transport);
    }

    // Catch-up del scheduler al arrancar (ADR-0011): un hub que estuvo apagado ejecuta UNA sola
    // vez las tareas con backlog vencido (collapse) y reprograma el resto. Se hace antes del loop.
    {
        let hub_id = state.config.hub_id.clone();
        let rt = state.runtime.lock().await;
        match rt.scheduler_catch_up(&hub_id).await {
            Ok(n) if n > 0 => eprintln!("scheduler: catch-up de arranque ejecutó {n} tarea(s)"),
            Ok(_) => {}
            Err(e) => eprintln!("scheduler catch-up: {e}"),
        }
    }

    // Bucle de background: relay de eventos del outbox (§5.4) + barrido del scheduler (ADR-0011).
    // Ambos comparten el mismo tick de 1s y el mismo lock del runtime (un ECS container por hub).
    {
        let runtime = state.runtime.clone();
        let hub_id = state.config.hub_id.clone();
        tokio::spawn(async move {
            loop {
                {
                    let rt = runtime.lock().await;
                    // Entrega at-least-once asíncrona del outbox a sus listeners (+ listener-host
                    // de host.notify para los eventos `*.reminder.due`).
                    if let Err(e) = rt.process_outbox().await {
                        eprintln!("relay outbox: {e}");
                    }
                    // Scheduled tasks vencidas → execute_command del propio módulo (sin usuario).
                    if let Err(e) = rt.process_scheduler(&hub_id).await {
                        eprintln!("scheduler: {e}");
                    }
                }
                tokio::time::sleep(std::time::Duration::from_millis(1000)).await;
            }
        });
    }

    // Router de API + (opcional) frontend estático. Si `HUB_WEB_DIR` apunta al `dist/` de Vite,
    // se sirve con fallback SPA a `index.html` (combo cloud + web-PWA, §3): /api, /ws y /healthz
    // los resuelve el router; cualquier otra ruta cae al `ServeDir`. Sin `HUB_WEB_DIR` (Tauri,
    // que sirve su propio webview) solo se montan las rutas de API.
    let router = match std::env::var("HUB_WEB_DIR").ok().filter(|s| !s.is_empty()) {
        Some(dir) => {
            eprintln!("sirviendo frontend estático desde {dir} (fallback SPA → index.html)");
            with_static_frontend(app(state), &dir)
        }
        None => app(state),
    };

    let listener = tokio::net::TcpListener::bind(&cfg.bind).await?;
    eprintln!("erplora-server escuchando en http://{}", cfg.bind);
    tracing::info!(bind = %cfg.bind, "erplora-server arrancado");
    // Apagado limpio (ECS/Tauri): Ctrl-C o SIGTERM → deja de aceptar conexiones y drena las en
    // vuelo antes de salir, en vez de cortar a mitad (importante para ECS al desescalar/desplegar).
    axum::serve(listener, router)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}

/// Espera Ctrl-C o (en Unix) SIGTERM. ECS envía SIGTERM al desescalar/desplegar; al recibirla,
/// `axum::serve` deja de aceptar conexiones nuevas y drena las en vuelo antes de cerrar.
async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c().await.expect("instalar handler de Ctrl-C");
    };
    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("instalar handler de SIGTERM")
            .recv()
            .await;
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();
    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
    eprintln!("apagado: señal recibida, drenando conexiones en vuelo…");
}

/// Construye el router con todas las rutas montadas sobre `state`.
pub fn app(state: AppState) -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/api/hub/context", get(hub_context))
        .route("/api/system", get(system::system_info))
        // Gestor de la carpeta `media/` (pantalla /files). Browse + raw + upload + delete + mkdir.
        .route("/api/media", get(media::media_list).delete(media::media_delete))
        .route("/api/media/raw", get(media::media_raw))
        .route("/api/media/upload", post(media::media_upload))
        .route("/api/media/folder", post(media::media_create_folder))
        .route("/api/navigation", get(navigation))
        .route("/api/modules", get(list_modules))
        .route("/api/modules/install", post(install_module))
        .route("/api/modules/request-install", post(request_install))
        // Proxies hub-scoped al Cloud (el token de máquina se queda en el runtime, no en el navegador)
        .route("/api/entitlement", get(proxy_entitlement))
        .route("/api/marketplace/catalog", get(proxy_marketplace_catalog))
        .route("/api/modules/:id/activate", post(activate_module))
        .route("/api/modules/:id/deactivate", post(deactivate_module))
        .route("/api/modules/:id/uninstall", post(uninstall_module))
        .route("/api/query", post(query))
        .route("/api/command", post(command))
        .route("/api/auth/pin", post(auth_pin))
        .route("/api/auth/set-pin", post(auth_set_pin))
        .route("/api/auth/cloud", post(auth_cloud))
        .route("/api/auth/refresh", post(auth_refresh))
        .route("/api/auth/logout", post(auth_logout))
        .route("/api/assistant/chat/stream", post(assistant_chat_stream))
        .route("/ws", get(ws_upgrade))
        // SSE: alternativa a /ws para el MISMO canal de eventos (hub#19). Se suscribe al mismo
        // `AppState.events` (broadcast, N suscriptores), así que no duplica el fan-out. Da gratis
        // reconexión del navegador (EventSource) + keep-alive (idle timeout del ALB). Nombre de
        // ruta = decisión del humano (`/api/events` por defecto).
        .route("/api/events", get(sse_events))
        // Log de cada request (método/ruta/estado/latencia) a INFO → consola + `media/_logs/`
        // (ADR-0047): la primera población real de la carpeta media. La respuesta se loguea a INFO;
        // los fallos del propio servidor a ERROR.
        .layer(
            tower_http::trace::TraceLayer::new_for_http()
                .on_response(
                    tower_http::trace::DefaultOnResponse::new().level(tracing::Level::INFO),
                )
                .on_failure(
                    tower_http::trace::DefaultOnFailure::new().level(tracing::Level::ERROR),
                ),
        )
        .with_state(state)
}

async fn healthz() -> &'static str {
    "ok"
}

/// Envuelve el router de API para servir el frontend estático (el `dist/` de Vite) con **fallback
/// SPA** a `index.html`: las rutas de API (`/api/*`, `/ws`, `/healthz`) las resuelve el router; el
/// resto cae al `ServeDir`, y las rutas del router SPA cliente (sin fichero en disco) sirven el
/// `index.html`. Para el combo cloud + web-PWA (§3).
pub fn with_static_frontend(router: Router, web_dir: &str) -> Router {
    use tower_http::services::{ServeDir, ServeFile};
    let index = format!("{}/index.html", web_dir.trim_end_matches('/'));
    router.fallback_service(ServeDir::new(web_dir).fallback(ServeFile::new(index)))
}

/// GET /api/hub/context — el `hub_id` inyectado por el despliegue (env `HUB_ID`) + el usuario
/// activo (hoy `null`; el frontend resuelve la sesión por separado) + `pin_users`: usuarios activos
/// con PIN del hub, para que el shell muestre el grid de login local directamente (sin depender de
/// un flag en localStorage). Contrato del frontend.
async fn hub_context(State(st): State<AppState>) -> Response {
    let pin_users: Vec<Value> = {
        let rt = st.runtime.lock().await;
        rt.list_pin_users().await.unwrap_or_default()
    }
    .into_iter()
    .map(|(id, name, role)| json!({ "id": id, "name": name, "role": role }))
    .collect();
    Json(json!({ "hub_id": st.config.hub_id, "user": Value::Null, "pin_users": pin_users }))
        .into_response()
}

#[derive(Deserialize)]
struct RequestInstallReq {
    module_id: String,
    #[serde(default)]
    version: String,
}

/// POST /api/modules/request-install — flujo real Cloud→descarga→runtime (ARQUITECTURA.md §2.2).
/// Auth = JWT del usuario + `X-Hub-Id` de las cabeceras. Tras instalar, emite el evento
/// `module.installed` por `/ws` y prepara la ingestión de embeddings (vía Cloud, pendiente §9.3).
async fn request_install(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<RequestInstallReq>,
) -> Response {
    // Hub-scoped: token de máquina si el hub está enrolado; si no, JWT del usuario.
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response();
    };

    let mut rt = st.runtime.lock().await;
    let result = install::install_from_cloud(
        &st.http,
        &st.config.cloud_base_url,
        &st.config.module_cache,
        &auth,
        &mut rt,
        &req.module_id,
        &req.version,
    )
    .await;

    match result {
        Ok(installed) => {
            // Ingestión de embeddings (§9.6): recoge el texto agéntico del módulo (agent.description
            // + ai.description de queries/commands), lo embebe **vía el proxy del Cloud** (§9.3 — el
            // Hub nunca llama a un proveedor de embeddings directamente) y lo registra en el índice
            // vectorial para el routing de tools (§9.2b). Best-effort: un fallo aquí NO aborta la
            // instalación (el módulo ya está instalado y operativo; el router degrada a "todos").
            let chunks = ingest::collect_chunks(rt.registry(), &installed.module_id);
            drop(rt);
            if !chunks.is_empty() {
                if let Some(store) = &st.vector {
                    let embedder = embed::CloudEmbedder::new(
                        st.http.clone(),
                        &st.config.cloud_base_url,
                        auth.clone(),
                    );
                    match embed::index_chunks(
                        &embedder,
                        store.as_ref(),
                        &st.config.hub_id,
                        &installed.version,
                        &chunks,
                    )
                    .await
                    {
                        Ok(n) => tracing::info!(module_id = %installed.module_id, chunks = n, "embeddings indexados (§9.6)"),
                        Err(e) => tracing::warn!(module_id = %installed.module_id, error = %e, "ingestión de embeddings falló (no crítico; router degrada)"),
                    }
                } else {
                    tracing::info!(module_id = %installed.module_id, chunks = chunks.len(), "sin índice vectorial; ingestión de embeddings omitida (§9.5)");
                }
            }

            // Evento WS con la forma exacta del contrato del frontend.
            st.broadcast(json!({ "type": "module.installed", "module_id": installed.module_id }));

            Json(json!({
                "ok": true,
                "module_id": installed.module_id,
                "version": installed.version,
                "status": "installed",
            }))
            .into_response()
        }
        Err(e) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({ "ok": false, "error": e.to_string() })),
        )
            .into_response(),
    }
}

/// GET hub-scoped al Cloud con la credencial de máquina (o JWT de usuario como fallback) y
/// devuelve el JSON tal cual. El **secreto de máquina nunca sale al navegador**: el web llama a
/// estas rutas del runtime y es el runtime quien firma la petición al Cloud.
async fn proxy_cloud_get(st: &AppState, headers: &HeaderMap, req: cloud_client::PreparedRequest) -> Response {
    let Some(auth) = auth::hub_scoped_auth(headers, st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response();
    };
    let mut r = st.http.get(&req.url);
    for (k, v) in auth.headers() {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) => {
            let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            match resp.bytes().await {
                Ok(body) => (status, [(axum::http::header::CONTENT_TYPE, "application/json")], body).into_response(),
                Err(e) => (StatusCode::BAD_GATEWAY, Json(json!({ "ok": false, "error": e.to_string() }))).into_response(),
            }
        }
        Err(e) => (StatusCode::BAD_GATEWAY, Json(json!({ "ok": false, "error": e.to_string() }))).into_response(),
    }
}

/// GET /api/entitlement — entitlement firmado del hub (proxy de `/api/v1/hub/device/entitlement/`).
async fn proxy_entitlement(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    // `entitlement(auth)` solo usa `auth` para las cabeceras; las reescribe `proxy_cloud_get`.
    let placeholder = cloud_client::Auth::HubToken { hub_id: st.config.hub_id.clone(), token: String::new() };
    proxy_cloud_get(&st, &headers, cloud.entitlement(&placeholder)).await
}

/// GET /api/marketplace/catalog — catálogo del marketplace (proxy de `/api/v1/marketplace/modules/`).
async fn proxy_marketplace_catalog(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let placeholder = cloud_client::Auth::HubToken { hub_id: st.config.hub_id.clone(), token: String::new() };
    proxy_cloud_get(&st, &headers, cloud.marketplace_modules(&placeholder)).await
}

/// POST /api/assistant/chat/stream — proxy SSE hacia el Cloud (ARQUITECTURA.md §9.3).
/// Reenvía el `Authorization: Bearer` + `X-Hub-Id` entrantes; ensambla las tools permitidas
/// (§9.2) y traduce el stream del Cloud al contrato del frontend (`token`/`done`).
async fn assistant_chat_stream(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(frontend): Json<Value>,
) -> Response {
    // Credencial hub-scoped: token de máquina del hub si está enrolado; si no, el JWT del usuario.
    // Así un cajero solo-local (sesión por PIN, sin JWT cloud) también usa el asistente.
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response();
    };
    // La sesión LOCAL del hub da el contexto/permisos para ensamblar las tools (gate = el de la UI)
    // y el id del usuario activo, que se manda como metadata de coste/auditoría (no permisos).
    let (all_tools, active_user, active_modules) = {
        let rt = st.runtime.lock().await;
        let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
            Ok(c) => c,
            Err(e) => return unauthorized(e),
        };
        let tools = assistant::assemble_tools(rt.registry(), &ctx);
        let active = rt.registry().active_module_count();
        (tools, ctx.user_id.clone(), active)
    };

    // Router de tools por vectores (§9.2b): embebe la última petición del usuario, busca en el
    // índice y recorta los tools a los módulos relevantes. Degrada a "todos los tools" si no hay
    // índice, si hay pocos módulos, o ante cualquier fallo del prefiltro (§9.5). El permiso lo
    // revalida igual el runtime: el router solo abarata el prompt, no es un gate.
    let tools = match &st.vector {
        Some(store) => {
            let query = assistant::last_user_message(&frontend);
            let embedder = embed::CloudEmbedder::new(
                st.http.clone(),
                &st.config.cloud_base_url,
                auth.clone(),
            );
            router::assemble_routed_tools(
                &embedder,
                store.as_ref(),
                &st.config.hub_id,
                &query,
                all_tools,
                active_modules,
                router::RouterConfig::default(),
            )
            .await
        }
        None => all_tools,
    };

    let body = assistant::build_cloud_body(&frontend, tools, Some(&active_user));

    // Construye la petición al Cloud (POST, Bearer + X-Hub-Id) y abre el stream.
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let req = cloud.assistant_chat_stream(&auth);
    let mut r = st.http.post(&req.url).json(&body);
    for (k, v) in &req.headers {
        r = r.header(*k, v);
    }

    let upstream = match r.send().await.and_then(|resp| resp.error_for_status()) {
        Ok(resp) => resp,
        Err(e) => {
            // Devuelve un único frame de error en el propio stream SSE.
            let frame = assistant::sse(&json!({ "type": "error", "error": e.to_string() }));
            return sse_response(Body::from(frame));
        }
    };

    // Re-streamea: parte el cuerpo del Cloud en líneas SSE y las traduce al contrato frontend.
    // Un buffer mantiene líneas partidas entre chunks de red.
    let mut buf = String::new();
    let mut byte_stream = upstream.bytes_stream();

    let translated = futures_util::stream::poll_fn(move |cx| {
        use std::task::Poll;
        loop {
            // Vacía líneas completas ya bufferizadas.
            if let Some(idx) = buf.find('\n') {
                let line: String = buf.drain(..=idx).collect();
                let line = line.trim_end_matches(['\r', '\n']);
                if let Some(frame) = assistant::translate_sse_line(line) {
                    return Poll::Ready(Some(Ok::<_, std::io::Error>(bytes_from(frame))));
                }
                continue;
            }
            // Pide más bytes al Cloud.
            match byte_stream.poll_next_unpin(cx) {
                Poll::Ready(Some(Ok(chunk))) => {
                    buf.push_str(&String::from_utf8_lossy(&chunk));
                }
                Poll::Ready(Some(Err(e))) => {
                    let frame = assistant::sse(&json!({ "type": "error", "error": e.to_string() }));
                    return Poll::Ready(Some(Ok(bytes_from(frame))));
                }
                Poll::Ready(None) => {
                    // Fin del stream del Cloud: procesa cualquier resto + cierra.
                    if !buf.is_empty() {
                        let rest = std::mem::take(&mut buf);
                        if let Some(frame) = assistant::translate_sse_line(rest.trim()) {
                            return Poll::Ready(Some(Ok(bytes_from(frame))));
                        }
                    }
                    return Poll::Ready(None);
                }
                Poll::Pending => return Poll::Pending,
            }
        }
    });

    sse_response(Body::from_stream(translated))
}

fn bytes_from(s: String) -> axum::body::Bytes {
    axum::body::Bytes::from(s.into_bytes())
}

/// Envuelve un cuerpo como respuesta SSE (`text/event-stream`, sin buffering del proxy).
fn sse_response(body: Body) -> Response {
    Response::builder()
        .header(header::CONTENT_TYPE, "text/event-stream")
        .header(header::CACHE_CONTROL, "no-cache")
        .header("X-Accel-Buffering", "no")
        .body(body)
        .unwrap()
        .into_response()
}

#[derive(Deserialize)]
struct QueryReq {
    name: String,
    #[serde(default)]
    params: Map<String, Value>,
}

#[derive(Deserialize)]
struct CommandReq {
    name: String,
    #[serde(default)]
    payload: Map<String, Value>,
}

#[derive(Deserialize)]
struct InstallReq {
    /// Ruta a la carpeta del módulo ya extraída (la prepara erplora-source desde el S3 zip).
    dir: String,
}

fn err_response(e: erplora_runtime::RuntimeError) -> Response {
    use erplora_runtime::RuntimeError as E;
    let (status, code) = match &e {
        E::PermissionDenied(_) => (StatusCode::FORBIDDEN, "permission_denied"),
        E::QueryNotFound(_) | E::CommandNotFound(_) => (StatusCode::NOT_FOUND, "not_found"),
        E::InvalidPayload { .. } => (StatusCode::UNPROCESSABLE_ENTITY, "invalid_payload"),
        E::NotImplemented(_) => (StatusCode::NOT_IMPLEMENTED, "not_implemented"),
        _ => (StatusCode::BAD_REQUEST, "error"),
    };
    let body = json!({ "ok": false, "error": { "code": code, "message": e.to_string() } });
    (status, Json(body)).into_response()
}

/// Respuesta para un fallo de **enrutado multi-tenant** (ADR-0005, hub#24):
///  - `UnknownOrg` → `403`: el `hub_id` de la petición no pertenece a ninguna org conocida; es un
///    intento de acceso cruzado o un hub no provisionado. **No** se cae a ninguna BD.
///  - `PoolLimit` → `503`: back-pressure (techo de orgs por proceso alcanzado), reintenta luego.
///  - `Connect`   → `502`: la Aurora de la org no responde (failover/credencial).
fn tenant_rejected(e: tenant::TenantError) -> Response {
    use tenant::TenantError as T;
    let (status, code) = match &e {
        T::UnknownOrg(_) => (StatusCode::FORBIDDEN, "unknown_org"),
        T::PoolLimit(_) => (StatusCode::SERVICE_UNAVAILABLE, "pool_limit"),
        T::Connect(_) => (StatusCode::BAD_GATEWAY, "org_db_unavailable"),
    };
    let body = json!({ "ok": false, "error": { "code": code, "message": e.to_string() } });
    (status, Json(body)).into_response()
}

/// `401` uniforme para fallos de autenticación (modo Jwt: token ausente/ inválido).
fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

async fn navigation(State(st): State<AppState>) -> Response {
    let rt = st.runtime.lock().await;
    let items: Vec<Value> = rt
        .navigation()
        .iter()
        .map(|n| {
            json!({
                "module_id": n.module_id, "id": n.nav.id, "label": n.nav.label,
                "icon": n.nav.icon, "component": n.nav.component,
            })
        })
        .collect();
    Json(json!({ "ok": true, "data": items })).into_response()
}

async fn list_modules(State(st): State<AppState>) -> Response {
    let rt = st.runtime.lock().await;
    Json(json!({ "ok": true, "data": rt.modules() })).into_response()
}

async fn install_module(State(st): State<AppState>, Json(req): Json<InstallReq>) -> Response {
    let mut rt = st.runtime.lock().await;
    match rt.install_from_dir(std::path::Path::new(&req.dir)).await {
        Ok(id) => Json(json!({ "ok": true, "data": { "module_id": id } })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn activate_module(State(st): State<AppState>, Path(id): Path<String>) -> Response {
    let mut rt = st.runtime.lock().await;
    match rt.activate(&id).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn deactivate_module(State(st): State<AppState>, Path(id): Path<String>) -> Response {
    let mut rt = st.runtime.lock().await;
    match rt.deactivate(&id).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn uninstall_module(State(st): State<AppState>, Path(id): Path<String>) -> Response {
    let mut rt = st.runtime.lock().await;
    match rt.uninstall(&id).await {
        Ok(()) => {
            drop(rt);
            // Borra del índice vectorial los chunks del módulo (§9.6): uninstall → delete chunks.
            // Best-effort: no falla la desinstalación si el store da error.
            if let Some(store) = &st.vector {
                if let Err(e) = embed::drop_module(store.as_ref(), &st.config.hub_id, &id).await {
                    tracing::warn!(module_id = %id, error = %e, "no se pudieron borrar embeddings del módulo (no crítico)");
                }
            }
            Json(json!({ "ok": true })).into_response()
        }
        Err(e) => err_response(e),
    }
}

async fn query(State(st): State<AppState>, headers: HeaderMap, Json(req): Json<QueryReq>) -> Response {
    // Tier cloud compartido (ADR-0005): resuelve el runtime de la ORG dueña del `hub_id` de la
    // petición (un pool por org). En single-tenant devuelve el runtime único. El rechazo cross-org
    // (hub_id de org desconocida) ocurre aquí, ANTES de tocar ninguna BD.
    let arc = match st.runtime_for(&auth::hub_id(&headers, &st.config.hub_id)).await {
        Ok(rt) => rt,
        Err(e) => return tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(c) => c,
        Err(e) => return unauthorized(e),
    };
    // Queries de lista (con bloque `list`) devuelven `{rows,total,limit,offset}` para el pager;
    // el resto devuelve el array de filas tal cual (compat con get/stats/settings).
    if rt.is_list_query(&req.name) {
        match rt.execute_query_page(&req.name, &req.params, &ctx).await {
            Ok(page) => Json(json!({ "ok": true, "data": page })).into_response(),
            Err(e) => err_response(e),
        }
    } else {
        match rt.execute_query(&req.name, &req.params, &ctx).await {
            Ok(rows) => Json(json!({ "ok": true, "data": rows })).into_response(),
            Err(e) => err_response(e),
        }
    }
}

async fn command(State(st): State<AppState>, headers: HeaderMap, Json(req): Json<CommandReq>) -> Response {
    // Mismo enrutado por org que `query` (ADR-0005): el `PgAdapter` de la org corre server-side.
    let arc = match st.runtime_for(&auth::hub_id(&headers, &st.config.hub_id)).await {
        Ok(rt) => rt,
        Err(e) => return tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(c) => c,
        Err(e) => return unauthorized(e),
    };
    match rt.execute_command(&req.name, &req.payload, &ctx).await {
        Ok(data) => Json(json!({ "ok": true, "data": data })).into_response(),
        Err(e) => err_response(e),
    }
}

#[derive(serde::Deserialize)]
struct PinReq {
    name: String,
    pin: String,
    /// Id estable del dispositivo (lo aporta el host: Tauri = id de máquina; web-PWA = id
    /// persistido). Opcional: solo lo usa el gate de device-trust si está activo (hub#15, §2.9).
    #[serde(default)]
    device_id: Option<String>,
}

#[derive(serde::Deserialize)]
struct CloudLoginReq {
    #[serde(default)]
    name: Option<String>,
    /// Id del dispositivo a marcar de confianza tras este login online (§2.9). Opcional.
    #[serde(default)]
    device_id: Option<String>,
}

/// Login local por **PIN** → abre sesión. Body `{name, pin, device_id?}` → `{ok, token, user}`
/// (401 si falla). Si el **device-trust** está activo (`HUB_DEVICE_TRUST=enforce`) y el cliente
/// manda `device_id`, se rechaza el PIN si el dispositivo no es de confianza (no hubo login online
/// previo en él, §2.9).
async fn auth_pin(State(st): State<AppState>, Json(req): Json<PinReq>) -> Response {
    let rt = st.runtime.lock().await;
    // Gate de device-trust (opt-in): solo si está activo Y el cliente identifica el dispositivo.
    if st.config.device_trust_enforce {
        if let Some(device_id) = req.device_id.as_deref() {
            match rt.is_device_trusted(device_id).await {
                Ok(true) => {}
                Ok(false) => {
                    return (
                        StatusCode::FORBIDDEN,
                        Json(json!({
                            "ok": false,
                            "error": "dispositivo no de confianza: inicia sesión online (cloud) primero",
                            "code": "device_untrusted"
                        })),
                    )
                        .into_response()
                }
                Err(e) => return err_response(e),
            }
        }
    }
    match rt.verify_pin(&req.name, &req.pin).await {
        Ok(Some(user)) => mint_session(&rt, user).await,
        Ok(None) => (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "usuario o PIN incorrecto" })),
        )
            .into_response(),
        Err(e) => err_response(e),
    }
}

/// Login de **usuario cloud**: verifica el JWT (RS256) y lo mapea a un `hub_user` local (lo
/// provisiona si es la primera vez), abriendo sesión. Header `Authorization: Bearer <access>`;
/// body opcional `{name}`. → `{ok, token, user}`.
async fn auth_cloud(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<CloudLoginReq>>,
) -> Response {
    let Some(token) = auth::bearer(&headers) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "falta Authorization: Bearer" })),
        )
            .into_response();
    };
    let Some(pem) = st.config.jwt_public_key.as_deref() else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "ok": false, "error": "login cloud no disponible (sin clave pública)" })),
        )
            .into_response();
    };
    let claims = match cloud_client::verify_user_jwt(&token, pem) {
        Ok(c) => c,
        Err(e) => {
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": format!("token inválido: {e}") })),
            )
                .into_response()
        }
    };
    let cloud_user_id = claims.user_id_str();
    let body = body.map(|b| b.0);
    let device_id = body.as_ref().and_then(|b| b.device_id.clone());
    let name = body
        .and_then(|b| b.name)
        .unwrap_or_else(|| format!("user:{cloud_user_id}"));
    // Rol por defecto al provisionar un usuario cloud nuevo (bootstrap). Decisión de política —
    // configurable por entorno; ajustable luego por un admin del hub.
    let default_role = std::env::var("HUB_DEFAULT_ROLE").unwrap_or_else(|_| "admin".into());
    let rt = st.runtime.lock().await;
    match rt.get_or_link_cloud_user(&cloud_user_id, &name, &default_role).await {
        Ok(user) => {
            // Device-trust (§2.9): este es un login ONLINE correcto → marca el dispositivo de
            // confianza para habilitar luego el login local por PIN. Best-effort (no bloquea el
            // login si falla el marcado).
            if let Some(device_id) = device_id.as_deref() {
                let _ = rt.trust_device(device_id, &name).await;
            }
            mint_session(&rt, user).await
        }
        Err(e) => err_response(e),
    }
}

/// Refresca la sesión **local** del header `X-Hub-Session` (hub#15): rota el token opaco y extiende
/// la expiración. → `{ok, token, user}` (401 si la sesión no es válida; el cliente debe re-loguear).
///
/// NOTA: este es el refresh de la **sesión server-side local** (token de `hub_session`), que es lo
/// que gatea las peticiones al runtime. El refresh del **JWT cloud** de usuario es distinto y va
/// contra el Cloud (`POST /api/v1/auth/refresh/`, `cloud_client::CloudClient::refresh`): lo dispara
/// el interceptor del Hub al recibir un 401, fuera de este endpoint.
/// TODO(humano): si se decide que el runtime también custodia/rota el JWT cloud (hoy lo lleva el
/// navegador), añadir aquí un proxy a `CloudClient::refresh` + persistencia del refresh rotado.
async fn auth_refresh(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let Some(token) = auth::session_token(&headers) else {
        return unauthorized(auth::AuthError::MissingSession);
    };
    let rt = st.runtime.lock().await;
    match rt.refresh_session(&token, erplora_runtime::identity::DEFAULT_SESSION_TTL_SECS).await {
        Ok(Some((new_token, user))) => {
            Json(json!({ "ok": true, "token": new_token, "user": user })).into_response()
        }
        Ok(None) => unauthorized(auth::AuthError::Invalid("sesión inválida o caducada".into())),
        Err(e) => err_response(e),
    }
}

#[derive(serde::Deserialize)]
struct SetPinReq {
    pin: String,
}

/// Fija el PIN del **usuario de la sesión actual** (`X-Hub-Session`). Lo usa el alta de PIN tras el
/// primer login cloud (§2.9): el usuario ya está autenticado por su JWT→sesión y elige su PIN en
/// este dispositivo de confianza. Body `{pin}` (4 dígitos; vacío lo borra). → `{ok}` (401 sin sesión).
async fn auth_set_pin(State(st): State<AppState>, headers: HeaderMap, Json(req): Json<SetPinReq>) -> Response {
    let rt = st.runtime.lock().await;
    let Some(token) = auth::session_token(&headers) else {
        return unauthorized(auth::AuthError::MissingSession);
    };
    let user = match rt.resolve_session(&token).await {
        Ok(Some(u)) => u,
        Ok(None) => return unauthorized(auth::AuthError::Invalid("sesión inválida o caducada".into())),
        Err(e) => return err_response(e),
    };
    match rt.set_pin(&user.id, &req.pin).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

/// Cierra la sesión del header `X-Hub-Session` (logout).
async fn auth_logout(State(st): State<AppState>, headers: HeaderMap) -> Response {
    if let Some(token) = auth::session_token(&headers) {
        let rt = st.runtime.lock().await;
        let _ = rt.delete_session(&token).await;
    }
    Json(json!({ "ok": true })).into_response()
}

/// Abre una sesión para `user` y devuelve `{ok, token, user}`.
async fn mint_session(rt: &erplora_runtime::Runtime, user: erplora_runtime::identity::HubUser) -> Response {
    match rt.create_session(&user.id, erplora_runtime::identity::DEFAULT_SESSION_TTL_SECS).await {
        Ok(token) => Json(json!({ "ok": true, "token": token, "user": user })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn ws_upgrade(State(st): State<AppState>, ws: WebSocketUpgrade) -> Response {
    ws.on_upgrade(move |socket| ws_loop(socket, st))
}

/// GET /api/events — el MISMO canal de eventos que `/ws`, servido como Server-Sent Events (hub#19).
/// Se suscribe al broadcast compartido `AppState.events` (no duplica el fan-out) y emite cada
/// evento como `data: <json>` (idéntico al frame que manda el WS). `KeepAlive` envía comentarios
/// periódicos para sobrevivir al idle timeout del ALB; el navegador (`EventSource`) reconecta solo.
async fn sse_events(
    State(st): State<AppState>,
) -> Sse<impl futures_util::stream::Stream<Item = Result<Event, std::convert::Infallible>>> {
    let rx = st.events.subscribe();
    let stream = futures_util::stream::unfold(rx, |mut rx| async move {
        loop {
            match rx.recv().await {
                Ok(ev) => {
                    let data = serde_json::to_string(&ev).unwrap_or_else(|_| "{}".into());
                    return Some((Ok(Event::default().data(data)), rx));
                }
                // Suscriptor lento: saltamos lo perdido y seguimos (igual que el WS).
                Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                // Canal cerrado: termina el stream.
                Err(tokio::sync::broadcast::error::RecvError::Closed) => return None,
            }
        }
    });
    Sse::new(stream).keep_alive(KeepAlive::default())
}

async fn ws_loop(mut socket: WebSocket, st: AppState) {
    let mut rx = st.events.subscribe();
    loop {
        match rx.recv().await {
            Ok(ev) => {
                let text = serde_json::to_string(&ev).unwrap_or_else(|_| "{}".into());
                if socket.send(Message::Text(text)).await.is_err() {
                    break;
                }
            }
            Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
            Err(_) => break,
        }
    }
}
