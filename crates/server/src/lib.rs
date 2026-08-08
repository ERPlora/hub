//! erplora-server — servidor Axum del runtime del tenant en modo cloud (ARQUITECTURA.md §7.5).
//!
//! Expone `execute_query`/`execute_command` por HTTP, los eventos por WebSocket (`/ws`), y la
//! **gestión de módulos** (listar / instalar / activar / desactivar / desinstalar = hot-plug).
//!
//! Rutas:
//!   GET  /healthz
//!   GET  /api/navigation                     menú de módulos ACTIVOS
//!   GET  /api/modules                        módulos instalados + estado
//!   POST /api/modules/install   {dir}        instala desde carpeta (extraída por erplora-source).
//!                                            **Solo dev** (`HUB_DEV_MODE`) y confinado al staging
//!                                            del hub — ver `install_guard` (hub#239).
//!   POST /api/modules/:id/activate
//!   POST /api/modules/:id/deactivate
//!   POST /api/modules/:id/uninstall
//!   POST /api/query   {name, params}
//!   POST /api/command {name, payload}
//!   GET  /ws                                 stream de eventos (solo push)
//!   GET  /ws/print                           canal del host de impresión (bidireccional, hub#343)

use axum::body::Body;
use axum::extract::{Path, Query, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use futures_util::StreamExt;
use serde::Deserialize;
use serde_json::{json, Map, Value};

pub mod activity;
pub mod api_keys;
pub mod assistant;
pub mod auth;
pub mod bootstrap;
pub mod daily_usage;
/// `shared` (counter till) vs `personal` (somebody's own device) — plan step 2b, hub#357.
pub mod device_mode;
/// The devices of a business and the gesture that cuts a lost one off — hub#455.
pub mod devices;
/// Step-up approvals: the manager's PIN, verified in the runtime, buys ONE action — hub#361.
pub mod elevation;
pub mod embed;
pub mod entitlement;
pub mod error_sink;
pub mod event_stream;
pub mod export_import;
/// ERPlora's DELEGATED fiscal certificate, fetched from the control plane (ADR-0202 §2 — hub#317).
pub mod fiscal_certificate;
pub mod hub_users;
pub mod login_throttle;
pub mod reset;
pub mod ingest;
pub mod install;
pub mod install_guard;
pub mod logging;
pub mod media;
pub mod members;
pub mod module_storage;
pub mod openapi;
pub mod print;
pub mod print_ws;
pub mod profile;
pub mod router;
pub mod settings;
pub mod state;
pub mod system;
pub mod system_metrics;
pub mod tenant;

pub use state::{AppState, AuthMode, HubConfig, HubId, MachineToken, WsEvent, DEV_HUB_ID};
pub use tenant::{
    EnvOrgResolver, OrgDescriptor, OrgId, OrgResolver, RuntimeFactory, TenantError, TenantRouter,
};

/// Configuración de arranque del runtime del hub — la usa el binario (`main.rs`). Envuelve la
/// [`HubConfig`] de despliegue + parámetros de proceso. Hub Cloud es Postgres-only (ADR-0154).
#[derive(Clone, Debug)]
pub struct ServeConfig {
    /// DSN de Postgres (`HUB_DATABASE_URL`) — **obligatorio** (ADR-0154). Vacío ⇒ el arranque
    /// falla con un error claro (`serve` hace fail-fast). El Cloud lo inyecta al desplegar.
    pub database_url: String,
    /// Dirección de escucha. Por defecto `127.0.0.1:8787`.
    pub bind: String,
    /// Carpeta opcional de módulos a instalar al arrancar (hub vacío / dev).
    pub modules_dir: Option<String>,
    /// Configuración de despliegue (hub_id, Cloud, `auth_mode`, token de máquina…).
    pub hub: HubConfig,
    /// Celda **externa** del token de máquina (hot-reload tras enrolar/rotar sin reiniciar). Si
    /// `None`, el runtime crea la suya sembrada con `hub.cloud_api_token` (caso binario/Cloud).
    pub machine_token_cell: Option<state::MachineToken>,
    /// Celda externa del `hub_id` vivo. Cloud/binario usa una celda interna sembrada desde `HUB_ID`.
    pub hub_id_cell: Option<state::HubId>,
    /// Ruta del `dist/` de Vite a servir en el **MISMO origen** que `/api` (ADR-0050). `Some` ⇒ el
    /// runtime monta el front con fallback SPA (`with_static_frontend`), de modo que
    /// `HttpWsTransport` (RUNTIME_URL='') alcance el loopback sin CORS; `from_env` lo vuelca desde
    /// `HUB_WEB_DIR`. `None` ⇒ solo API (dev con Vite, que proxya, o binario sin front).
    pub web_dir: Option<String>,
    /// Valor del header `Content-Security-Policy` a emitir (ADR-0050). Cuando el doc lo sirve Axum
    /// (mismo origen), el runtime lo emite. `None` ⇒ no se añade header (estado previo). El
    /// contenido es columna de seguridad/humano.
    pub csp: Option<String>,
}

impl ServeConfig {
    /// Igual que el binario: `HUB_DATABASE_URL` (obligatorio) / `HUB_BIND` / `HUB_MODULES_DIR` +
    /// [`HubConfig::from_env`].
    pub fn from_env() -> Self {
        let hub = HubConfig::from_env();
        Self {
            database_url: std::env::var("HUB_DATABASE_URL").unwrap_or_default(),
            bind: std::env::var("HUB_BIND").unwrap_or_else(|_| "127.0.0.1:8787".into()),
            // Una sola lectura de `HUB_MODULES_DIR` (la de `HubConfig`): el mismo valor gobierna el
            // escaneo de arranque y el staging admitido por `/api/modules/install` (hub#239).
            modules_dir: hub
                .dev_modules_dir
                .as_ref()
                .map(|p| p.to_string_lossy().into_owned()),
            hub,
            machine_token_cell: None,
            hub_id_cell: None,
            // ECS/binario: el `dist/` se sirve de disco por `HUB_WEB_DIR` (paridad Hub Cloud).
            web_dir: std::env::var("HUB_WEB_DIR").ok().filter(|s| !s.is_empty()),
            // CSP opcional vía env (None por defecto = comportamiento previo). En Tauri la fija el shell.
            csp: std::env::var("HUB_CSP").ok().filter(|s| !s.is_empty()),
        }
    }
}

/// Trae la clave pública RSA del Cloud (`GET /api/v1/auth/public-key/`) para verificar los JWT de
/// usuario offline. `None` si el Cloud no responde o no la trae.
async fn fetch_jwt_public_key(cloud_base_url: &str) -> Option<String> {
    let url = format!(
        "{}/api/v1/auth/public-key/",
        cloud_base_url.trim_end_matches('/')
    );
    // Timeout ACOTADO: esta llamada corre ANTES de bindear el listener en `serve()`. Sin límite, una
    // red hostil (captive portal / DNS lento / host inalcanzable) retrasaría el arranque del servidor
    // mucho más que el `wait_for_runtime` del shell Tauri → la ventana cargaría un loopback que aún no
    // escucha (ADR-0050). El login cloud degrada a "no disponible" si no llega; el PIN no la necesita.
    let client = match reqwest::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(3))
        .timeout(std::time::Duration::from_secs(5))
        .build()
    {
        Ok(c) => c,
        Err(_) => return None,
    };
    let resp = client.get(&url).send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: Value = resp.json().await.ok()?;
    v.get("public_key")
        .and_then(|k| k.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
}

/// Resuelve el SQL de seed de configuración inicial desde el entorno (hub#36):
///  - `HUB_SEED_SQL` — SQL inline (gana si está presente y no vacío). Lo usa ECS/terraform.
///  - `HUB_SEED_SQL_PATH` — ruta a un fichero `.sql` (alternativa para local/dev).
///
/// `Ok(None)` si no se configura ninguno (arranque normal sin seed). Un `HUB_SEED_SQL_PATH` que
/// no se puede leer es un error de configuración → aborta el arranque con un mensaje claro.
fn load_seed_sql() -> Result<Option<String>, Box<dyn std::error::Error>> {
    if let Some(sql) = std::env::var("HUB_SEED_SQL")
        .ok()
        .filter(|s| !s.trim().is_empty())
    {
        return Ok(Some(sql));
    }
    if let Some(path) = std::env::var("HUB_SEED_SQL_PATH")
        .ok()
        .filter(|s| !s.trim().is_empty())
    {
        let sql = std::fs::read_to_string(&path)
            .map_err(|e| format!("HUB_SEED_SQL_PATH={path}: no se pudo leer el seed: {e}"))?;
        return Ok(Some(sql));
    }
    Ok(None)
}

/// Normaliza el DSN de `HUB_DATABASE_URL` para sqlx. El Cloud lo inyecta en forma SQLAlchemy
/// (`postgresql+asyncpg://user:pass@host:5432/db`), pero sqlx (`PgPool::connect`) espera el esquema
/// estándar `postgresql://`/`postgres://` (sin el sufijo de driver `+asyncpg`/`+psycopg`). Se quita
/// solo ese sufijo; el resto del DSN (credenciales/host/db) se respeta tal cual.
pub fn normalize_pg_dsn(url: &str) -> String {
    url.replacen("postgresql+asyncpg://", "postgresql://", 1)
        .replacen("postgres+asyncpg://", "postgres://", 1)
        .replacen("postgresql+psycopg://", "postgresql://", 1)
        .replacen("postgresql+psycopg2://", "postgresql://", 1)
}

/// Arranca el runtime completo y **sirve Axum** en `cfg.bind` hasta que termina. Punto de entrada
/// único del binario y del shell Tauri (in-process, §11): abre SQLite, instala los módulos del dir
/// si se indica, resuelve la clave pública del Cloud si falta, monta el [`AppState`], lanza el
/// **relay del outbox** (poll 1s + backoff, §5.4) y sirve. La credencial de máquina viaja en
/// `cfg.hub.cloud_api_token` (Tauri la inyecta desde el keychain; ECS desde el env).
pub async fn serve(mut cfg: ServeConfig) -> Result<(), Box<dyn std::error::Error>> {
    use erplora_runtime::Runtime;

    // Logging del hub → consola + `media/_logs/` (rotación diaria, retención 6 meses, ADR-0047).
    // Se monta lo primero para capturar el arranque. El guard se mantiene vivo toda la función
    // (al soltarlo se pierden los logs en cola del appender no-bloqueante).
    let _log_guard = logging::init(&cfg.hub.media_dir);

    // Backend de datos: **Postgres-only** (ADR-0154). `HUB_DATABASE_URL` es obligatoria — sin ella
    // el arranque falla con un error claro (fail-fast). El Cloud lo inyecta en forma SQLAlchemy
    // (`postgresql+asyncpg://…`); sqlx quiere `postgresql://…` → se normaliza (`normalize_pg_dsn`).
    let dsn = normalize_pg_dsn(cfg.database_url.trim());
    if dsn.is_empty() {
        return Err("HUB_DATABASE_URL es obligatoria (Hub Cloud es Postgres-only, ADR-0154): \
                    define el DSN Postgres del hub"
            .into());
    }
    eprintln!("db: backend Postgres vía HUB_DATABASE_URL");
    let db: Box<dyn erplora_db::DatabaseAdapter> =
        Box::new(erplora_db::PgAdapter::connect(&dsn).await?);
    // Identidad viva: en Cloud nace del deployment; en el primer arranque Tauri la aporta el
    // shell y puede pasar del placeholder al UUID registrado sin reiniciar.
    let hub_id_cell = cfg
        .hub_id_cell
        .take()
        .unwrap_or_else(|| std::sync::Arc::new(std::sync::RwLock::new(cfg.hub.hub_id.clone())));
    if let Ok(hub_id) = hub_id_cell.read() {
        cfg.hub.hub_id = hub_id.clone();
    }

    // El runtime se construye con el `hub_id` del despliegue (config, no spoofable): scope del
    // estado de módulos (`hub_module`) y de las migraciones de sistema (hub#31 / hub#37).
    let mut runtime = Runtime::with_hub_id(db, cfg.hub.hub_id.clone());

    // DEMO efímera (ADR-0197, hub#376): se sella ya, antes incluso de instalar módulos o aplicar
    // migraciones, para que los cierres estén puestos durante TODO el arranque. `AppState` vuelve a
    // sellarlo (mismo valor, idempotente) porque su constructor es el embudo de todos los hosts.
    runtime.set_demo_hub(cfg.hub.demo);
    if cfg.hub.demo {
        eprintln!(
            "demo: hub efímero (ADR-0197) — entorno fiscal clavado a `testing`, certificado \
             propio e identidad fiscal cerrados"
        );
    }

    // El mismo backend de ficheros sirve a TODOS los módulos: disco bajo `media/modules/` en
    // Local y proxy Cloud→S3 en Cloud. Se inyecta antes de instalar para que cada manifest con
    // `static_files.folder` materialice su carpeta al activarse.
    let machine_token_cell = cfg.machine_token_cell.take().unwrap_or_else(|| {
        std::sync::Arc::new(std::sync::RwLock::new(cfg.hub.cloud_api_token.clone()))
    });
    // Backend de ficheros de módulos: proxy autenticado Hub→Cloud→Object Storage (ADR-0154), sin
    // credenciales de almacenamiento en el Hub.
    let module_storage = module_storage::ModuleMediaStorage::cloud(
        cfg.hub.cloud_base_url.clone(),
        cfg.hub.hub_id.clone(),
        machine_token_cell.clone(),
    );
    runtime.set_module_storage(std::sync::Arc::new(module_storage));

    // Plugins nativos first-party (ADR-0009): motores compliance-crítico horneados en el
    // runtime. Hoy solo `verifactu` (cadena fiscal + transmisión AEAT TLS-mutua).
    runtime.register_native(
        "verifactu",
        std::sync::Arc::new(erplora_verifactu::VerifactuEngine),
    );

    // Escaneo de `HUB_MODULES_DIR` al arrancar: SOLO en modo desarrollo explícito (hub#239). En
    // producción ese dir es `/tmp/modules` (contenedor stateless) y se instalaba todo subdirectorio
    // con un `module.json` sin verificar nada — un dir escribible convertido en cargador de código.
    // Los módulos de un hub real vienen del marketplace (grant + SHA256, ADR-0015).
    match install_guard::boot_scan_dir(cfg.hub.dev_mode, cfg.modules_dir.as_deref()) {
        Some(dir) => {
            // Instala los módulos del dir resolviendo el orden de `depends_on` por topo-sort (hub#16):
            // una dependencia se instala antes que quien la declara, sin depender del orden del FS.
            // `install_all_from_dir` es tolerante (loguea ✓/✗ por módulo y salta los rotos); aquí solo
            // registramos un error externo (read_dir fallido o ciclo de dependencias del conjunto).
            eprintln!("dev: instalando módulos de HUB_MODULES_DIR={dir} (modo desarrollo)");
            if let Err(e) = runtime
                .install_all_from_dir(std::path::Path::new(dir))
                .await
            {
                eprintln!("✗ instalación de módulos: {e}");
            }
        }
        None => {
            if let Some(ignored) = &cfg.modules_dir {
                eprintln!(
                    "módulos: HUB_MODULES_DIR={ignored} IGNORADO (sin HUB_DEV_MODE): en producción \
                     los módulos se instalan desde el marketplace, con SHA256 verificado"
                );
            }
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

    // Índice vectorial del asistente (§9.2b routing + §9.6 ingestión). Hoy **None**: el store
    // pgvector para Postgres es un follow-up (ADR-0154; hub#204 / pm#29). Mientras tanto el
    // asistente degrada a "todos los tools" (§9.5). La generación de embeddings sigue yendo por el
    // Cloud (§9.3). TODO(humano): `PgVectorStore` (pgvector) para el índice de routing/RAG.
    let vector_store: Option<state::SharedVectorStore> = None;

    // Celda del token de máquina: externa (compartida con el shell Tauri para hot-reload) o propia.
    let mut state = AppState::with_config_cells(runtime, cfg.hub, machine_token_cell, hub_id_cell);
    if let Some(vs) = vector_store {
        state = state.with_vector(vs);
    }
    // Tablas de sistema del runtime (outbox + scheduler) — para el caso de hub vacío sin módulos.
    state.runtime.lock().await.ensure_system_tables().await?;

    // **Owner sembrado del env** (ADR-0157, corrección de Ioan): el owner es el CREADOR del hub y el
    // despliegue lo trae ya inyectado por el provisioning del SaaS como `HUB_OWNER_EMAIL`. Se siembra
    // un `hub_user` role=admin (cloud_user_id NULL, sin PIN) tras las tablas de sistema —`admin` es
    // lo más alto del plano de NEGOCIO desde hub#349; la PROPIEDAD sigue siendo del plano de la
    // cuenta—; en su primer login `auth_cloud` lo enlaza por email. **Idempotente** (no duplica ni
    // pisa un rol existente),
    // así que es seguro en cada arranque. Sin el env (dev/local) es un no-op silencioso. Sustituye al
    // bootstrap «primer login = owner» (retirado): el owner ya no depende de quién entre primero.
    if let Some(owner_email) = std::env::var("HUB_OWNER_EMAIL")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
    {
        match state.runtime.lock().await.seed_owner(&owner_email).await {
            Ok(true) => eprintln!("auth: owner sembrado del env (HUB_OWNER_EMAIL={owner_email})"),
            Ok(false) => {} // ya existía: idempotente.
            Err(e) => eprintln!("✗ seed del owner (HUB_OWNER_EMAIL={owner_email}): {e}"),
        }
    }

    // Re-hidrata el Registry tras un reinicio: re-registra los módulos ya instalados de este hub
    // desde la caché de descargas (`module_cache/<id>/<version>/`). Sin esto, un runtime con
    // `modules_dir: None` (el caso descarga-desde-marketplace, p. ej. el shell Tauri) arrancaría
    // con el Registry vacío aunque `hub_module` + las tablas del módulo persistan → el módulo
    // "desaparecería" del runtime al reiniciar (no expondría queries/commands/nav). Tolerante.
    {
        let cache_root = state.config.module_cache.clone();
        match state
            .runtime
            .lock()
            .await
            .rehydrate_installed(&cache_root)
            .await
        {
            Ok(ids) if !ids.is_empty() => eprintln!("módulos re-hidratados: {}", ids.join(", ")),
            Ok(_) => {}
            Err(e) => eprintln!("✗ re-hidratación de módulos: {e}"),
        }
    }

    // Auto-curación del contrato STATELESS (Hub Cloud): el `module_cache` es efímero (`/tmp`) y se
    // vacía en cada redeploy/reschedule, así que `rehydrate_installed` no encuentra las carpetas y
    // los módulos que `hub_module` marca instalados quedan SIN registrar → "desaparecen" del runtime.
    // El diseño stateless (reschedulable, sin volumen) implica **re-descargarlos del marketplace**:
    // el hub se auto-cura re-bajando esos módulos con su token de máquina. Best-effort — un módulo
    // que no se pueda re-bajar (red/entitlement) se omite con log, no aborta el arranque.
    // `install_from_cloud` resuelve `depends_on` en orden (nested install).
    {
        let missing = state
            .runtime
            .lock()
            .await
            .installed_but_unregistered()
            .await
            .unwrap_or_default();
        if !missing.is_empty() {
            match auth::machine_auth(&state) {
                Some(machine) => {
                    let cache_root = state.config.module_cache.clone();
                    let cloud = state.config.cloud_base_url.clone();
                    eprintln!("cache vacío: re-descargando {} módulo(s) instalados del marketplace…", missing.len());
                    for (id, version) in missing {
                        let mut rt = state.runtime.lock().await;
                        // Progreso no-op: en el arranque aún no hay clientes WS a los que retransmitir.
                        match install::install_from_cloud(&state.http, &cloud, &cache_root, &machine, &mut rt, &id, &version, &|_, _| {}, &state.config.signature_policy()).await {
                            Ok(_) => eprintln!("✓ módulo re-descargado: {id}@{version}"),
                            Err(e) => eprintln!("✗ re-descarga de {id}@{version}: {e}"),
                        }
                    }
                }
                None => eprintln!(
                    "⚠ {} módulo(s) instalados sin caché y hub sin enrolar (sin token de máquina): no se re-descargan",
                    missing.len()
                ),
            }
        }
    }

    // Seed de configuración inicial (hub#36): SQL idempotente que se aplica UNA vez al arrancar,
    // tras las tablas de sistema. Mecanismo genérico (NO "modo demo"): el host lo pasa por env —
    // `HUB_SEED_SQL` (SQL inline, p. ej. el del despliegue demo) o `HUB_SEED_SQL_PATH` (fichero).
    // Si ambos están, gana el inline. La idempotencia la garantiza el propio SQL (`WHERE NOT
    // EXISTS`/`ON CONFLICT`). Un seed roto aborta el arranque (error claro), no se traga en silencio.
    if let Some(seed_sql) = load_seed_sql()? {
        let n = state.runtime.lock().await.apply_seed(&seed_sql).await?;
        eprintln!("seed: aplicadas {n} sentencia(s) de configuración inicial");
    }

    // **Perfil fiscal** (ADR-0259 D2/D4, hub#550): qué debe este hub, resuelto contra lo que hay
    // montado de verdad. Va AQUÍ y no junto a `ensure_system_tables` por dos razones que son la
    // misma: el registry ya está re-hidratado (así se sabe si queda algún proveedor del régimen) y
    // el seed ya escribió el `country_code` (así se sabe qué régimen es). Antes de este punto las
    // dos mitades de la respuesta no existen.
    //
    // **No aborta el arranque.** Un hub que no abre es una tienda que no cobra; y como `BLOCKED` es
    // DERIVADO, no hay nada que se quede mal escrito por no haber corrido: la siguiente lectura lo
    // vuelve a calcular. Aquí nada rechaza todavía (eso es hub#556).
    {
        let rt = state.runtime.lock().await;
        match rt.refresh_fiscal_profile().await {
            Ok(mode) => eprintln!("fiscal: perfil del hub resuelto → {mode:?}"),
            Err(e) => eprintln!("✗ fiscal: no se pudo resolver el perfil del hub (ADR-0259): {e}"),
        }
    }

    // Transporte de `host.notify` (ADR-0012): cliente real de email/sms/whatsapp. Hoy un MOCK
    // (decisión de dependencia del humano para el SMTP/SMS reales; ver crates/runtime/host_notify.rs).
    // El mock pasa por el Outbox como cualquier transporte, así que la mecánica de reintentos/
    // dead-letter del listener-host queda real. TODO: sustituir por el transporte real (lettre/HTTP).
    state
        .runtime
        .lock()
        .await
        .set_notify_transport(std::sync::Arc::new(
            erplora_runtime::host_notify::MockTransport::new(),
        ));

    // Registro GLOBAL de errores ("todo controlado", un único embudo): instala el sink que reenvía
    // al Cloud (`POST /api/v1/hub/device/error-report/`, X-Hub-Token) cada error del runtime
    // (core + módulos), del panic hook y de la ruta local del frontend. Best-effort (spawn detached);
    // si el hub no está enrolado el sink descarta en silencio. Se hace una sola vez al arrancar.
    install_error_reporting(&state);

    // Catch-up del scheduler al arrancar (ADR-0011): un hub que estuvo apagado ejecuta UNA sola
    // vez las tareas con backlog vencido (collapse) y reprograma el resto. Se hace antes del loop.
    {
        let hub_id = state.hub_id();
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
        let scheduler_state = state.clone();
        tokio::spawn(async move {
            loop {
                {
                    let hub_id = scheduler_state.hub_id();
                    let rt = scheduler_state.runtime.lock().await;
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

    // Job de **revalidación híbrida del entitlement** (crate::entitlement): refresca el token
    // firmado del Cloud cada `HUB_ENTITLEMENT_REVALIDATE_SECS` (default 24h) con la credencial
    // de máquina y actualiza el estado que leen el gate de query/command y `/api/entitlement`.
    // Primer tick al arrancar (siembra el estado cuanto antes). Sin token de máquina (dev/local
    // sin enrolar) el tick se salta SIN contar fallo → el gate queda fail-open, como hoy.
    //
    // El heartbeat es además el **segundo disparador de refetch del certificado delegado**
    // (ADR-0202 §2 punto 4): sube lo que este hub tiene instalado y baja la versión que sirve el
    // plano de control, así que una rotación converge por la llamada que YA se hacía, sin canal de
    // push ni scheduler nuevo. El presupuesto es compartido con los otros dos disparadores
    // (`fiscal_certificate::RefetchBudget`) porque el Cloud cuenta un solo total por hub.
    let certificate_budget = std::sync::Arc::new(fiscal_certificate::RefetchBudget::hourly());
    {
        let st = state.clone();
        let certificate_budget = certificate_budget.clone();
        let secs = entitlement::interval_secs(
            std::env::var("HUB_ENTITLEMENT_REVALIDATE_SECS")
                .ok()
                .as_deref(),
        );
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(std::time::Duration::from_secs(secs));
            loop {
                tick.tick().await;
                let Some(auth) = auth::machine_auth(&st) else {
                    continue;
                };
                // Same 24h tick, no second scheduler: report canonical daily business usage.
                // Collection happens before network I/O, then both Cloud calls run independently:
                // an entitlement failure must not suppress business-usage retention (or vice versa).
                let now = entitlement::now_unix();
                let now_iso = chrono::Utc::now().to_rfc3339();
                let mut usage = {
                    let runtime = st.runtime.lock().await;
                    let mut usage =
                        daily_usage::collect_daily_usage(runtime.db(), runtime.hub_id(), &now_iso)
                            .await;
                    // Lo que este hub tiene del certificado DELEGADO (ADR-0202 §2.5). Mismo lock
                    // que el resto del snapshot: es la lectura barata, y no puede sostenerse
                    // durante la llamada de red de abajo.
                    if let Some((version, not_after)) =
                        fiscal_certificate::delegated_certificate_report(
                            runtime.db(),
                            runtime.hub_id(),
                        )
                        .await
                    {
                        usage.cert_version = Some(version);
                        usage.cert_not_after = not_after;
                    }
                    usage
                };
                // ADR-0175: la actividad de usuario viaja en ESTE heartbeat, y solo si la hubo.
                // Un hub encendido que nadie toca no manda la marca — que es exactamente lo que el
                // Cloud tiene que observar para poder apagarlo.
                let pending_activity = st.activity.pending();
                usage.last_user_activity_at = pending_activity.map(activity::to_iso8601);
                let entitlement_request = entitlement::fetch_verified_claims(
                    &st.http,
                    &st.config.cloud_base_url,
                    &auth,
                    now,
                );
                let heartbeat_request = daily_usage::send_heartbeat(
                    &st.http,
                    &st.config.cloud_base_url,
                    &auth,
                    &usage,
                );
                let (outcome, heartbeat_result) =
                    tokio::join!(entitlement_request, heartbeat_request);
                entitlement::record_outcome(&st.entitlement, outcome, now);
                match heartbeat_result {
                    // Confirmar SOLO tras un envío correcto: si se diera por reportada una marca
                    // que no llegó, el Cloud seguiría contando días y adelantaría el apagado.
                    Ok(response) => {
                        if let Some(ts) = pending_activity {
                            st.activity.mark_reported(ts);
                        }
                        // Segundo disparador (ADR-0202 §2 punto 4): versión distinta ⇒ refetch. El
                        // propio contrato lo hace pasar UNA vez — al instalarla, la local pasa a
                        // ser la anunciada y el latido siguiente ya no pide nada.
                        fiscal_certificate::refetch_once(
                            fiscal_certificate::RefetchTrigger::Heartbeat {
                                announced: response.cert_version,
                            },
                            &certificate_budget,
                            &st.http,
                            &st.config.cloud_base_url,
                            &auth,
                            &st.runtime,
                            &st.hub_id(),
                        )
                        .await;
                    }
                    Err(error) => tracing::warn!(%error, "daily usage heartbeat failed"),
                }
            }
        });
    }

    // Import del blueprint que el SaaS DECLARÓ para este hub (ADR-0212, hub#406): lo que hace que
    // un hub recién provisionado —la demo— nazca con catálogo en vez de con el asistente de setup.
    //
    // 🔴 Va en su propia task, NO en el camino de arranque. El seed de arriba se aplica con `?` y
    // un seed roto aborta el boot a propósito; esto no puede: un blueprint que no se pueda importar
    // debe dejar un hub que FUNCIONA (degradado, sin catálogo), nunca un visitante sin hub. Por eso
    // `spawn_declared_blueprint_import` devuelve un handle y no un Result — no hay nada que `?`
    // pueda propagar hasta aquí. Sin las claves de env no lanza nada y no toca el Cloud.
    bootstrap::spawn_declared_blueprint_import(&state);

    // Disparadores 1 y 3 del refetch del certificado delegado (ADR-0202 §2 punto 4): el de
    // ARRANQUE y el del FALLO TLS contra la AEAT. (El 2 —el heartbeat— va en el tick de arriba.)
    //
    // 🔴 En su propia task, igual que el import de blueprint y por el mismo motivo: un plano de
    // control inalcanzable tiene que dejar un hub que FUNCIONA, no un hub que no termina de
    // arrancar. El seed de arriba sí aborta el boot, y es la excepción a propósito.
    fiscal_certificate::spawn_refetch_service(&state, certificate_budget);

    // Router de API + (opcional) frontend estático en el MISMO origen (`cfg.web_dir`). En ECS/binario
    // lo vuelca `from_env` desde `HUB_WEB_DIR`; en Tauri (Hub Local, ADR-0050) lo fija el shell con la
    // ruta del `dist/` empaquetado (`resource_dir()`), para que el webview cargue front + datos del
    // mismo origen. `None` ⇒ solo API (dev con Vite, que proxya).
    if let Some(dir) = cfg.web_dir.as_deref() {
        eprintln!("sirviendo frontend estático desde {dir} (fallback SPA → index.html)");
    }
    let mut router = build_router(state, cfg.web_dir.as_deref());
    // CSP (ADR-0050): con el doc servido por Axum, la CSP de `tauri.conf` no aplica → la emitimos aquí.
    if let Some(csp) = cfg.csp.as_deref() {
        router = with_csp(router, csp);
    }

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

/// Instala el **registro global de errores** del runtime: el sink que reenvía al Cloud + el panic
/// hook. Idempotente en la práctica (el `OnceLock` interno ignora un segundo `install`; el hook se
/// re-encadena al anterior). Lo llama [`serve`] una vez al arrancar, con el `AppState` ya montado.
fn install_error_reporting(state: &AppState) {
    use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry};

    // El sink lee el token de máquina VIVO (hot-reload) de la celda del state, así que un enrol
    // posterior habilita el reporte sin reiniciar. La versión del hub = la del build del server.
    let sink = error_sink::CloudErrorSink::new(
        &state.config.cloud_base_url,
        state.hub_id.clone(),
        state.machine_token.clone(),
        state.http.clone(),
        format!("v{}", env!("CARGO_PKG_VERSION")),
    );
    ErrorRegistry::install(std::sync::Arc::new(sink));

    // Panic hook: convierte cualquier `panic!` del proceso en un `ErrorEvent` (source=hub,
    // code=panic, severity=unexpected) y lo reporta al registro global ANTES de delegar en el hook
    // por defecto (que sigue logueando/abortando). `report` es seguro desde aquí (no hace panic!).
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        // Mensaje: el payload del panic (str/String) si es legible.
        let message = info
            .payload()
            .downcast_ref::<&str>()
            .map(|s| s.to_string())
            .or_else(|| info.payload().downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "panic (payload no legible)".to_string());
        // Stack: ubicación del panic + backtrace si está habilitado (RUST_BACKTRACE).
        let location = info
            .location()
            .map(|l| format!("{}:{}:{}", l.file(), l.line(), l.column()))
            .unwrap_or_default();
        let backtrace = std::backtrace::Backtrace::capture().to_string();
        let stack = if backtrace.is_empty() || backtrace.contains("disabled backtrace") {
            location
        } else {
            format!("{location}\n{backtrace}")
        };

        let event = ErrorEvent::new(
            erplora_runtime::error_registry::source::HUB,
            "panic",
            message,
            erplora_runtime::error_registry::severity::UNEXPECTED,
        )
        .with_stack(stack);
        ErrorRegistry::global().report(event);

        // Conserva el comportamiento previo (log a stderr / abort según config).
        previous(info);
    }));
}

/// Espera Ctrl-C o (en Unix) SIGTERM. ECS envía SIGTERM al desescalar/desplegar; al recibirla,
/// `axum::serve` deja de aceptar conexiones nuevas y drena las en vuelo antes de cerrar.
async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("instalar handler de Ctrl-C");
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
    let registration_state = state.clone();
    let activity_state = state.activity.clone();
    Router::new()
        .route("/healthz", get(healthz))
        .route("/api/hub/context", get(hub_context))
        .route("/api/system", get(system::system_info))
        // Telemetría de recursos vs límites del plan (ADR-0154, hub#203). Sesión admin.
        .route("/api/system/metrics", get(system_metrics::system_metrics))
        // Settings del hub (store key/value de sistema, tabla `hub_settings`). GET = cualquier
        // sesión de usuario; PUT = sesión admin (owner/admin). Contrato del frontend.
        .route(
            "/api/settings",
            get(settings::get_settings).put(settings::put_settings),
        )
        // Personal (core): los usuarios REALES del hub (`hub_user`) — incluido el owner, que entra
        // por Cloud y no tiene PIN. GET = cualquier sesión; alta/edición/baja = sesión admin. La
        // pantalla de Personal NO depende del módulo `staff` (que es otra cosa: profesional
        // reservable, comisiones, horarios). Ver `crate::hub_users`.
        .route(
            "/api/hub/users",
            get(hub_users::list_users).post(hub_users::create_user),
        )
        .route(
            "/api/hub/users/:id",
            axum::routing::put(hub_users::update_user)
                .delete(hub_users::deactivate_user),
        )
        .route("/api/hub/roles", get(hub_users::list_roles))
        .route(
            "/api/hub/roles/:key",
            axum::routing::put(hub_users::set_role_activation),
        )
        // Modo del DISPOSITIVO (paso 2b, hub#357): `shared` (mostrador) vs `personal` (equipo
        // propio). GET = **sin sesión** (lo lee la pantalla de login, que es anterior a cualquier
        // sesión) y un dispositivo desconocido recibe `shared`; PUT = sesión **admin**, como
        // ajustes o el catálogo de roles. Ver `crate::device_mode`.
        .route(
            "/api/device/mode",
            get(device_mode::get_device_mode).put(device_mode::put_device_mode),
        )
        // Los dispositivos del negocio y el gesto «se me ha perdido la tablet» (hub#455). Las DOS
        // puertas exigen sesión **admin**, a diferencia de la de arriba: esta ENUMERA el negocio
        // entero (cuándo se usó cada dispositivo, cuánto le queda a su sesión), que es una lista de
        // la compra para quien tenga uno robado. Ver `crate::devices`.
        .route("/api/devices", get(devices::list_devices))
        .route(
            "/api/devices/:device_id",
            axum::routing::delete(devices::revoke_device),
        )
        // Perfil del usuario autenticado. Sin `/:id`: solo permite leer/editar el propio.
        .route(
            "/api/profile",
            get(profile::get_profile).put(profile::put_profile),
        )
        .route(
            "/api/profile/avatar",
            get(profile::get_avatar)
                .post(profile::upload_avatar)
                .delete(profile::delete_avatar)
                .layer(axum::extract::DefaultBodyLimit::max(3 * 1024 * 1024)),
        )
        // Certificado fiscal del negocio (ADR-0079): recurso del hub, subido en Ajustes → Negocio.
        // Identidad fiscal hacia el SaaS (ADR-0201 7/11): la casilla «usar estos datos también
        // para mi factura de ERPlora». La llamada la hace el RUNTIME — el cloud_api_token nunca
        // cruza al navegador.
        .route(
            "/api/business/fiscal-identity",
            post(settings::publish_fiscal_identity),
        )
        .route(
            "/api/business/certificate",
            get(settings::get_business_certificate)
                .put(settings::put_business_certificate)
                .delete(settings::delete_business_certificate),
        )
        // Export/import del hub a blueprint (ADR-0113): capa server sobre el motor del runtime
        // (`export_hub`/`import_sections`). Auth = sesión admin (owner/admin), como /api/settings.
        // El inspect recibe el zip crudo → body limit propio (el default de axum son 2 MiB).
        .route("/api/hub/export", post(export_import::export_blueprint))
        // Lo que alimenta las casillas por tabla del formulario (hub#534): sin el recuento,
        // la lista es una fila de nombres que nadie sabe interpretar.
        .route("/api/hub/export/tables", get(export_import::export_tables))
        .route(
            "/api/hub/import/inspect",
            post(export_import::import_inspect).layer(axum::extract::DefaultBodyLimit::max(
                export_import::MAX_BLUEPRINT_BYTES,
            )),
        )
        .route("/api/hub/import", post(export_import::import_blueprint))
        // Reset del hub — volver a cero (ADR-0170): el espejo destructivo del export. Mismo gate
        // admin. El `plan` es dry-run (lo que la UI pinta antes de confirmar); el límite fiscal
        // (facturas remitidas a la AEAT) lo aplica el MOTOR, no esta capa.
        .route("/api/hub/reset/plan", post(reset::reset_plan))
        .route("/api/hub/reset", post(reset::reset_hub))
        // Lotes de importación (ADR-0170): listar qué trajo cada blueprint y deshacer uno sin
        // tocar lo que el usuario creó después.
        .route("/api/hub/import/batches", get(reset::import_batches))
        .route("/api/hub/import/undo", post(reset::undo_import_batch))
        // Gestor de la carpeta `media/` (pantalla /files). Browse + raw + upload + delete + mkdir.
        .route(
            "/api/media",
            get(media::media_list).delete(media::media_delete),
        )
        .route("/api/media/raw", get(media::media_raw))
        .route("/api/media/upload", post(media::media_upload))
        .route("/api/media/folder", post(media::media_create_folder))
        .route("/api/media/rename", post(media::media_rename))
        .route("/api/navigation", get(navigation))
        .route("/api/modules", get(list_modules))
        .route("/api/modules/install", post(install_module))
        .route("/api/modules/request-install", post(request_install))
        // Assets web de un módulo instalado (module.json + `dist/*.esm.js` + wasm/icons) servidos
        // desde la CACHÉ de descargas, resueltos por la VERSIÓN instalada. En Hub Cloud los módulos
        // se descargan en runtime al `module_cache` (NO se hornean en el `web_dir`), así que sin esta
        // ruta `/modules/**` caía al fallback SPA (`index.html`) y NINGÚN Web Component cargaba: toda
        // la UI de módulos quedaba muerta ("No se pudo cargar el módulo").
        .route("/modules/:id/*path", get(serve_module_asset))
        // Proxies hub-scoped al Cloud (el token de máquina se queda en el runtime, no en el navegador)
        .route("/api/entitlement", get(proxy_entitlement))
        .route("/api/marketplace/catalog", get(proxy_marketplace_catalog))
        // Which build of the installable app the Cloud publishes (hub#400). The page cannot ask
        // erplora.com itself: `connect-src 'self' ipc:` kills it, and silently.
        .route("/api/app/release", get(proxy_app_release))
        // Blueprints: «fuente nube» del import (Ajustes → Datos). ADR-0121.
        .route("/api/blueprints/catalog", get(proxy_blueprints_catalog))
        .route("/api/blueprints/:slug/download", get(download_blueprint))
        .route("/api/modules/:id/activate", post(activate_module))
        .route("/api/modules/:id/deactivate", post(deactivate_module))
        .route("/api/modules/:id/uninstall", post(uninstall_module))
        .route(
            "/api/modules/:id/capabilities",
            get(settings::get_module_capabilities).put(settings::put_module_capabilities),
        )
        .route("/api/query", post(query))
        .route("/api/command", post(command))
        // hub#361: the manager approves ONE action. The PIN is verified in the runtime, and the
        // token that comes back is presented on the retry in `X-Elevation-Token` — never in the
        // command payload, so a command body stays pure data.
        .route("/api/elevation/approve", post(elevation::approve))
        // ── Print queue of the hub (ADR-0196 §6, hub#341) ───────────────────────────────────
        // Enqueue `{jobId, role, html}` (idempotent by `jobId`) and observe the queue. Drenarla
        // por el WS del runtime es hub#343. Auth = sesión de usuario.
        .route(
            "/api/print/jobs",
            get(print::list_jobs).post(print::enqueue_job),
        )
        // ── Registro de HOSTS de impresión (ADR-0196 §6, hub#342) ────────────────────────────
        // Quién drena cada rol. Un dispositivo se registra/late/se retira A SÍ MISMO (el sujeto es
        // su `X-Device-Id`, no hay parámetro para nombrar otro) → basta sesión de usuario: la app
        // tiene que poder hacerlo al arrancar. La excepción es retirar el dispositivo de OTRO
        // (la caja robada o sustituida), que pide sesión **admin**, como `/api/device/mode`.
        // El `live` NO se almacena: se deriva del último latido — un equipo apagado no escribe.
        .route(
            "/api/print/hosts",
            get(print::list_hosts)
                .post(print::register_host)
                .delete(print::retire_host),
        )
        .route("/api/print/hosts/heartbeat", post(print::host_heartbeat))
        // ── API pública por módulo (ADR-0057, public-api.md) ────────────────────────────────
        // Gestión de keys (auth = sesión admin owner/admin; NO una api key).
        .route(
            "/api/keys",
            get(api_keys::list_keys).post(api_keys::create_key),
        )
        .route("/api/keys/:id/rotate", post(api_keys::rotate_key))
        .route("/api/keys/:id", axum::routing::delete(api_keys::revoke_key))
        // Superficie de datos (auth = Auth::ApiKey, capa A genérica). Doble puerta `expose_api`.
        .route("/api/v1/:module/q/:query", post(api_keys::data_query))
        .route("/api/v1/:module/c/:command", post(api_keys::data_command))
        // OpenAPI 3.1 dinámico per-hub, **gateado por sesión de usuario** (interno, no público —
        // ADR-0057 §4 refinado 2026-06-24). El Swagger UI YA NO lo sirve el server: lo renderiza una
        // vista Vue interna del Hub (`apps/web/ApiDocsPage.vue`, `swagger-ui-dist` de npm) que pide
        // este spec con el fetch autenticado del web app (`X-Hub-Session`).
        .route("/api/v1/openapi.json", get(openapi::openapi_json))
        // Reporte de errores del FRONTEND (same-origin, sin auth cloud): el web app postea sus
        // errores JS aquí y el runtime los funnelea al registro global → Cloud (el secreto de
        // máquina nunca toca el navegador). Ver `frontend_error_report`.
        .route("/api/error-report", post(frontend_error_report))
        .route("/api/auth/pin", post(auth_pin))
        .route("/api/auth/set-pin", post(auth_set_pin))
        .route("/api/auth/cloud", post(auth_cloud))
        .route("/api/auth/courier", post(auth_courier))
        .route("/api/auth/logout", post(auth_logout))
        // ── Gestión de usuarios-login del Hub (identidad, ADR-0157 §7 / checklist core #2) ──────
        // Alta/baja/listado de quién puede ENTRAR en el hub. Gate owner/admin (sesión, NO api key).
        // Cada alta/baja crea/desactiva el `hub_user` local Y notifica al SaaS (`members`). NO es
        // `staff.*` (negocio): es identidad.
        .route(
            "/api/members",
            get(members::list_members).post(members::add_member),
        )
        .route(
            "/api/members/:email",
            axum::routing::delete(members::remove_member),
        )
        .route("/api/assistant/chat/stream", post(assistant_chat_stream))
        // The EVENT channel (hub#504): needs an API key of this hub that may read. See
        // `event_stream` — the credential travels in the header, in the first frame (`/ws`) or as
        // a single-use ticket (`/api/events`), never as a long-lived secret in the URL.
        .route("/ws", get(event_stream::upgrade))
        // El canal del HOST DE IMPRESIÓN (ADR-0196 §6, hub#343): el primer WS cliente→servidor del
        // hub. Ruta propia y no un frame más de `/ws` porque su contrato es otro — por `/ws/print`
        // viaja el DOCUMENTO del tique y exige sesión + registro de host, mientras que `/ws` es un
        // fan-out de eventos de dominio a cualquier key con lectura.
        .route("/ws/print", get(print_ws::upgrade))
        // SSE: alternativa a /ws para el MISMO canal de eventos (hub#19). Se suscribe al mismo
        // `AppState.events` (broadcast, N suscriptores), así que no duplica el fan-out. Da gratis
        // reconexión del navegador (EventSource) + keep-alive (idle timeout del ALB). Nombre de
        // ruta = decisión del humano (`/api/events` por defecto).
        .route("/api/events", get(event_stream::sse))
        // Where the app asks for its credential for the channel (session → single-use ticket).
        .route("/api/events/ticket", post(event_stream::mint_ticket))
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
        // Marca de actividad de usuario (`crate::activity`): una petición autenticada y aceptada
        // significa que alguien está usando este hub. Viaja al Cloud en el heartbeat de
        // `daily_usage`, que apaga (60d) y acaba borrando (120d) los hubs free que nadie usa.
        .layer(axum::middleware::from_fn_with_state(
            activity_state,
            track_user_activity,
        ))
        // Primera barrera del runtime: una máquina real sin UUID+credencial Cloud solo puede
        // consultar salud/contexto para pintar el login. Demo es la única excepción.
        .layer(axum::middleware::from_fn_with_state(
            registration_state,
            require_machine_registration,
        ))
        .with_state(state)
}

async fn healthz() -> &'static str {
    "ok"
}

/// Anota que **alguien está usando** este hub (ver `crate::activity`).
///
/// Punto ÚNICO a propósito: cada handler resuelve la auth a su manera (sesión, API key, token de
/// máquina), y colgar la marca de cada uno se desincronizaría al añadir el siguiente. Aquí se ve
/// lo que importa — llevaba credencial y no se rechazó — sin tocar ninguna firma.
///
/// Coste por petición: leer una cabecera y un `fetch_max` atómico. Ninguna escritura a disco.
async fn track_user_activity(
    State(activity): State<std::sync::Arc<crate::activity::ActivityState>>,
    request: axum::extract::Request,
    next: Next,
) -> Response {
    let has_credential = auth::session_token(request.headers()).is_some()
        || auth::api_key_token(request.headers()).is_some();
    let response = next.run(request).await;
    if crate::activity::is_user_activity(has_credential, response.status().as_u16()) {
        activity.touch(entitlement::now_unix());
    }
    response
}

/// Bloquea toda la superficie de negocio hasta completar el registro de la máquina. El login
/// email/password inicial va directamente al SaaS; después Tauri adopta `hub_id + token` y vuelve
/// a consultar `/api/hub/context`, que ya pasa esta barrera.
async fn require_machine_registration(
    State(st): State<AppState>,
    request: axum::extract::Request,
    next: Next,
) -> Response {
    let path = request.uri().path();
    if matches!(path, "/healthz" | "/api/hub/context") || st.is_dev_hub() || st.machine_registered() {
        return next.run(request).await;
    }
    (
        StatusCode::PRECONDITION_REQUIRED,
        Json(json!({
            "ok": false,
            "error": {
                "code": "machine_registration_required",
                "message": "este dispositivo debe registrarse con el Cloud antes de usar el Hub"
            }
        })),
    )
        .into_response()
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

/// Añade el header `Content-Security-Policy` a TODAS las respuestas (ADR-0050). Cuando el documento
/// lo sirve el propio Axum (Hub Local mismo-origen, o Hub Cloud), la CSP de `tauri.conf` ya **no**
/// aplica al doc (solo la inyecta el protocolo de assets de Tauri), así que el runtime debe emitirla.
/// En las respuestas de API el header es inocuo. El valor lo decide el llamador (es columna de
/// seguridad/humano): en Tauri lo fija `embedded_serve_config`; en ECS sale de `HUB_CSP` (o `None`).
pub fn with_csp(router: Router, csp: &str) -> Router {
    use axum::http::header::CONTENT_SECURITY_POLICY;
    use axum::http::HeaderValue;
    // No abortar el arranque por una CSP mal formada (p. ej. `HUB_CSP` de ECS con un salto de línea o
    // byte no-ASCII): se loguea y se sigue SIN header en vez de panicar. En Tauri el input es la const
    // `LOOPBACK_CSP` (siempre válida); este guard protege el camino ECS (`HUB_CSP` del entorno).
    match HeaderValue::from_str(csp) {
        Ok(value) => router.layer(tower_http::set_header::SetResponseHeaderLayer::overriding(
            CONTENT_SECURITY_POLICY,
            value,
        )),
        Err(e) => {
            eprintln!("CSP inválida ignorada (no se emite header Content-Security-Policy): {e}");
            router
        }
    }
}

/// Compone el router de API (`app`) con, opcionalmente, el frontend estático servido en el **MISMO
/// origen** (ADR-0050). Es el camino REAL que monta tanto [`serve`] (ECS/binario, desde `HUB_WEB_DIR`)
/// como el runtime embebido del shell Tauri (Hub Local, desde `resource_dir()`), extraído aquí para
/// poder testearlo sin bindear puerto (`tower::ServiceExt::oneshot`). `web_dir = Some` ⇒ front + API
/// en un solo router; `None` ⇒ solo API (dev con Vite, que proxya).
pub fn build_router(state: AppState, web_dir: Option<&str>) -> Router {
    match web_dir.filter(|s| !s.is_empty()) {
        Some(dir) => with_static_frontend(app(state), dir),
        None => app(state),
    }
}

/// GET /api/hub/context — el `hub_id` inyectado por el despliegue (env `HUB_ID`) + el usuario
/// activo (hoy `null`; el frontend resuelve la sesión por separado) + `pin_users`: usuarios activos
/// con PIN del hub, para que el shell muestre el grid de login local directamente (sin depender de
/// un flag en localStorage) + `business_type`/`sector`: el sector del hub (env `HUB_SECTOR`) para
/// que el dashboard derive el preset "Recomendado" de widgets (ADR-0054) + `currency`/`language`:
/// settings del hub (tabla `hub_settings` ∪ defaults), lectura barata en el arranque del SPA para no
/// pegar a `/api/settings` por separado. Contrato del frontend.
async fn hub_context(State(st): State<AppState>) -> Response {
    let hub_id = st.hub_id();
    // El primer login Tauri puede haber adoptado el UUID real después de arrancar Axum. Antes de
    // abrir la sesión local reconciliamos el Runtime y aplicamos las migraciones scoped del nuevo
    // Hub. Es idempotente y convierte este endpoint de boot en la barrera de consistencia.
    let runtime = match st.runtime_for(&hub_id).await {
        Ok(runtime) => runtime,
        Err(error) => return tenant_rejected(error),
    };
    // Lee pin_users + settings en un único lock del runtime (lectura de arranque, sin gate).
    let (pin_users, currency, currency_decimals, language) = {
        let rt = runtime.lock().await;
        if let Err(error) = rt.ensure_system_tables().await {
            return err_response(error);
        }
        let pin_users: Vec<Value> = rt
            .list_pin_users()
            .await
            .unwrap_or_default()
            .into_iter()
            .map(|(id, name, role)| json!({ "id": id, "name": name, "role": role }))
            .collect();
        // Settings del hub: si la lectura falla (no debería), cae a los defaults del contrato para
        // no romper el arranque del SPA.
        let settings = rt.get_settings().await.unwrap_or_else(|_| json!({}));
        let currency = settings
            .get("currency")
            .cloned()
            .unwrap_or_else(|| json!("EUR"));
        // Los DECIMALES de la moneda (ADR-0123 §7). El front los necesita para las dos fronteras
        // (teclear y pintar): el dinero viaja en UNIDADES MÍNIMAS, y cuántas hay en una unidad mayor
        // depende de la moneda — EUR 2, **JPY 0**, KWD 3. Un `/100` clavado en el front cobra 100
        // veces mal en un hub en yenes.
        //
        // Precedencia: lo que el hub declare a mano (`currency_decimals`, para monedas que el
        // registro no conoce) → el registro ISO-4217 → el default explícito.
        let currency_decimals = settings
            .get("currency_decimals")
            .and_then(|v| v.as_i64())
            .map(|n| n as u32)
            .unwrap_or_else(|| {
                erplora_runtime::settings::decimals_of(currency.as_str().unwrap_or("EUR"))
            });
        let language = settings
            .get("language")
            .cloned()
            .unwrap_or_else(|| json!("es"));
        (pin_users, currency, currency_decimals, language)
    };
    // Sector del hub: el frontend lee `sector ?? business_type` (alias), así que emitimos ambas
    // claves con el mismo valor. `None` → `null` (degradación elegante: el board no aplica preset).
    let sector = st.config.sector.clone();
    // Demo/Dev es la única excepción al registro obligatorio. En cualquier runtime real se exige
    // tanto UUID Cloud como credencial de máquina; nunca se expone el secreto al navegador.
    let demo = st.is_dev_hub();
    let machine_registered = st.machine_registered();
    Json(json!({
        "hub_id": hub_id,
        "user": Value::Null,
        "pin_users": pin_users,
        "demo": demo,
        // ⚠️ NO es `demo`. Esa clave lleva años significando **modo `dev`** y el SPA la usa para
        // el fallback de login por PIN (`runtime.ts` → `config.demo`): cambiarle el sentido sería
        // abrir ese fallback en cada demo pública. Esta es la DEMO EFÍMERA de ADR-0197: el hub
        // real de una hora que el visitante prueba sin registrarse. La UI la lee para EXPLICAR
        // los cierres de hub#376 (entorno fiscal clavado, certificado e identidad congelados)
        // en vez de dejar un 409 sin contexto.
        "ephemeral_demo": st.config.demo,
        "machine_registered": machine_registered,
        "registration_required": !demo && !machine_registered,
        "public_key_loaded": st.config.jwt_public_key.is_some(),
        "business_type": sector,
        "sector": sector,
        // Settings de arranque (tabla `hub_settings` ∪ defaults). El SPA los usa para formato de
        // moneda + locale sin un fetch extra a `/api/settings`.
        "currency": currency,
        // Cuántos decimales tiene esa moneda. El front NO puede asumir 2 (ADR-0123 §7).
        "currency_decimals": currency_decimals,
        "language": language,
    }))
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
    // La credencial de máquina sirve para que ESTE Hub hable con Cloud, no para autorizar al
    // navegador. Exigimos primero la sesión local de un owner/admin: de lo contrario cualquier
    // módulo web same-origin podría disparar instalaciones usando indirectamente el token del Hub.
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    // Hub-scoped: token de máquina si el hub está enrolado; si no, JWT del usuario.
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response();
    };

    // Progreso por fases → WS `module.install.progress` (feedback visual del marketplace).
    // `module_id` = módulo en curso (puede ser una dep anidada); `root_id` = el pedido por el
    // usuario, para que el frontend actualice la card correcta aunque esté migrando una dep.
    let progress_state = st.clone();
    let root_id = req.module_id.clone();
    let on_progress = move |module_id: &str, phase: &str| {
        progress_state.broadcast(json!({
            "type": "module.install.progress",
            "module_id": module_id,
            "root_id": root_id,
            "phase": phase,
        }));
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
        &on_progress,
        &st.config.signature_policy(),
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
                        &st.hub_id(),
                        &installed.version,
                        &chunks,
                    )
                    .await
                    {
                        Ok(n) => {
                            tracing::info!(module_id = %installed.module_id, chunks = n, "embeddings indexados (§9.6)")
                        }
                        Err(e) => {
                            tracing::warn!(module_id = %installed.module_id, error = %e, "ingestión de embeddings falló (no crítico; router degrada)")
                        }
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
        Err(e) => {
            // Observabilidad (antes: 502 ciego sin log → invisible en Dokploy). Logueamos el error
            // real y mapeamos a un código honesto: un fallo instalando en el runtime (deps sin
            // satisfacer tras la resolución anidada = ciclo, migración, schema) NO es un 502 de
            // gateway. Así el operador distingue "fallo del Cloud/red" de "fallo instalando el módulo".
            tracing::error!(
                module_id = %req.module_id,
                requested_version = %req.version,
                error = %e,
                "request-install falló"
            );
            let code = match &e {
                install::InstallError::VersionNotFound(_) => StatusCode::NOT_FOUND,
                install::InstallError::Runtime(_) => StatusCode::UNPROCESSABLE_ENTITY,
                // Fallo de FIRMA (hub#239): el módulo no verifica — sin firma, firma inválida o
                // clave ajena. Es un rechazo de seguridad, NO un fallo de gateway: 403.
                install::InstallError::Source(source::SourceError::BadSignature(_)) => {
                    StatusCode::FORBIDDEN
                }
                // ADR-0060: el plan exige comprar dependencias. NO es un fallo del hub ni del
                // Cloud: es una decisión que le toca al usuario → 409 con los datos de compra.
                install::InstallError::Blocked { .. } => StatusCode::CONFLICT,
                install::InstallError::Cloud(_)
                | install::InstallError::Source(_)
                | install::InstallError::MissingSha256 { .. } => StatusCode::BAD_GATEWAY,
            };
            // Canal de errores de dominio (hub#139): además del mensaje humano viaja un `code`
            // estable contra el que la UI programa y traduce. Un install fallido no es mudo.
            let mut body = json!({
                "ok": false,
                "error": e.to_string(),
                "code": e.code(),
            });
            if let install::InstallError::Blocked {
                blocked_on,
                purchase,
                ..
            } = &e
            {
                body["blocked_on"] = json!(blocked_on);
                body["purchase"] = json!(purchase
                    .iter()
                    .map(|p| json!({
                        "module_id": p.module_id,
                        "module_type": p.module_type,
                        "price": p.price,
                        "currency": p.currency,
                        "purchase_url": p.purchase_url,
                    }))
                    .collect::<Vec<_>>());
            }
            (code, Json(body)).into_response()
        }
    }
}

/// GET /modules/:id/*path — sirve los assets web (`module.json`, `dist/*.esm.js`, wasm, icons) de un
/// módulo instalado desde la CACHÉ de descargas, resueltos por la VERSIÓN instalada
/// (`module_cache/<id>/<version>/<path>`). La versión sale del registro (el módulo debe estar
/// instalado). Guard anti path-traversal. Un asset ausente o un módulo no instalado → **404** (lo
/// maneja el cargador del Web Component); al ser ruta explícita NO cae al fallback SPA, así que nunca
/// se sirve `index.html` haciéndose pasar por JS/JSON (que es exactamente lo que rompía la UI).
async fn serve_module_asset(
    State(st): State<AppState>,
    Path((id, rel)): Path<(String, String)>,
) -> Response {
    // Anti path-traversal: ningún segmento `..` (incluido tras decodificar %2e%2e) ni vacío.
    if rel.split('/').any(|seg| seg == ".." || seg.is_empty()) {
        return StatusCode::NOT_FOUND.into_response();
    }
    // Versión instalada del módulo (del registro). Módulo no instalado → 404.
    let version = {
        let rt = st.runtime.lock().await;
        rt.modules()
            .into_iter()
            .find(|m| m.id == id)
            .map(|m| m.version)
    };
    let Some(version) = version else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let full = st.config.module_cache.join(&id).join(&version).join(&rel);
    match tokio::fs::read(&full).await {
        Ok(bytes) => (
            [(header::CONTENT_TYPE, module_asset_content_type(&rel))],
            bytes,
        )
            .into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

/// Content-Type de un asset de módulo por extensión (los que sirve [`serve_module_asset`]).
fn module_asset_content_type(rel: &str) -> &'static str {
    if rel.ends_with(".js") || rel.ends_with(".mjs") {
        "text/javascript"
    } else if rel.ends_with(".json") || rel.ends_with(".map") {
        "application/json"
    } else if rel.ends_with(".wasm") {
        "application/wasm"
    } else if rel.ends_with(".css") {
        "text/css"
    } else if rel.ends_with(".svg") {
        "image/svg+xml"
    } else {
        "application/octet-stream"
    }
}

/// Fallo de un GET hub-scoped al Cloud: sin credencial (401 local) o error de red (502).
/// Separado de la respuesta HTTP para que cada proxy construya su body (p. ej.
/// `proxy_entitlement` añade el bloque `revalidation` también en el fallo).
enum CloudGetError {
    NoCredential,
    Network(String),
}

/// GET hub-scoped al Cloud con la credencial de máquina (o JWT de usuario como fallback).
/// Devuelve status + body crudos del Cloud. El **secreto de máquina nunca sale al navegador**:
/// el web llama a estas rutas del runtime y es el runtime quien firma la petición al Cloud.
async fn cloud_get_raw(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
) -> Result<(StatusCode, axum::body::Bytes), CloudGetError> {
    let Some(auth) = auth::hub_scoped_auth(headers, st) else {
        return Err(CloudGetError::NoCredential);
    };
    let mut r = st.http.get(&req.url);
    for (k, v) in auth.headers() {
        r = r.header(k, v);
    }
    if let Some(language) = headers.get(axum::http::header::ACCEPT_LANGUAGE) {
        r = r.header(axum::http::header::ACCEPT_LANGUAGE, language);
    }
    let resp = r
        .send()
        .await
        .map_err(|e| CloudGetError::Network(e.to_string()))?;
    let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let body = resp
        .bytes()
        .await
        .map_err(|e| CloudGetError::Network(e.to_string()))?;
    Ok((status, body))
}

/// Respuesta HTTP para un [`CloudGetError`] (contrato previo de `proxy_cloud_get`, sin cambios).
fn cloud_get_error_response(e: CloudGetError) -> Response {
    match e {
        CloudGetError::NoCredential => (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response(),
        CloudGetError::Network(msg) => {
            (StatusCode::BAD_GATEWAY, Json(json!({ "ok": false, "error": msg }))).into_response()
        }
    }
}

/// Hub-scoped GET to the Cloud, returning its JSON untouched (see [`cloud_get_raw`]).
async fn proxy_cloud_get(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
) -> Response {
    match cloud_get_raw(st, headers, req).await {
        Ok((status, body)) => cloud_json_passthrough(status, body),
        Err(e) => cloud_get_error_response(e),
    }
}

/// Hands the front the Cloud's JSON as it came: same status, `no-store`, nothing reinterpreted.
fn cloud_json_passthrough(status: StatusCode, body: axum::body::Bytes) -> Response {
    (
        status,
        [
            (axum::http::header::CONTENT_TYPE, "application/json"),
            (axum::http::header::CACHE_CONTROL, "no-store"),
        ],
        body,
    )
        .into_response()
}

/// GET público al Cloud. Solo se usa para metadatos publicados del catálogo Demo; nunca para
/// descargas, entitlement ni operaciones de un Hub. No añade identidad de usuario o máquina.
async fn proxy_public_cloud_get(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
) -> Response {
    let mut request = st.http.get(&req.url);
    for (name, value) in req.headers {
        request = request.header(name, value);
    }
    if let Some(language) = headers.get(axum::http::header::ACCEPT_LANGUAGE) {
        request = request.header(axum::http::header::ACCEPT_LANGUAGE, language);
    }
    let response = match request.send().await {
        Ok(response) => response,
        Err(error) => {
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "ok": false, "error": error.to_string() })),
            )
                .into_response()
        }
    };
    let status =
        StatusCode::from_u16(response.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    match response.bytes().await {
        Ok(body) => (
            status,
            [
                (axum::http::header::CONTENT_TYPE, "application/json"),
                (axum::http::header::CACHE_CONTROL, "no-store"),
            ],
            body,
        )
            .into_response(),
        Err(error) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({ "ok": false, "error": error.to_string() })),
        )
            .into_response(),
    }
}

/// GET /api/entitlement — entitlement firmado del hub (proxy de `/api/v1/hub/device/entitlement/`).
///
/// **Aditivo** (revalidación híbrida, `crate::entitlement`): a la respuesta del Cloud se le añade
/// el bloque `revalidation` (`blocked_modules` + `grace_until` + `last_check`…) con el estado
/// local del job periódico — también cuando el Cloud no responde (fallo de red), que es justo
/// cuando la UI necesita pintar «funcionará hasta {fecha}». El contrato previo no cambia:
/// mismo status y mismos campos, solo se AÑADE la clave.
async fn proxy_entitlement(State(st): State<AppState>, headers: HeaderMap) -> Response {
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    // `entitlement(auth)` solo usa `auth` para las cabeceras; las reescribe `cloud_get_raw`.
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token: String::new(),
    };

    // Estado local de revalidación sobre los módulos INSTALADOS de este hub.
    let installed: Vec<String> = {
        let rt = st.runtime.lock().await;
        rt.modules().into_iter().map(|m| m.id).collect()
    };
    let revalidation = st
        .entitlement
        .read()
        .map(|g| g.revalidation_json(&installed, entitlement::now_unix()))
        .unwrap_or(Value::Null);

    match cloud_get_raw(&st, &headers, cloud.entitlement(&placeholder)).await {
        Ok((status, body)) => match serde_json::from_slice::<Value>(&body) {
            // Body objeto JSON → se le inyecta la clave aditiva.
            Ok(Value::Object(mut obj)) => {
                obj.insert("revalidation".into(), revalidation);
                (status, Json(Value::Object(obj))).into_response()
            }
            // Body no-objeto (raro: HTML de error, vacío) → tal cual, como antes.
            _ => (
                status,
                [(axum::http::header::CONTENT_TYPE, "application/json")],
                body,
            )
                .into_response(),
        },
        Err(CloudGetError::Network(msg)) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({ "ok": false, "error": msg, "revalidation": revalidation })),
        )
            .into_response(),
        Err(e) => cloud_get_error_response(e),
    }
}

/// GET /api/marketplace/catalog — the real marketplace catalogue.
///
/// A registered Hub uses `/api/v1/marketplace/modules/` with its machine token so the answer is
/// scoped to that Hub. Demo, the one exception to registration, consumes the public metadata
/// catalogue `/api/v1/marketplace/catalog/`; no protected operation ever becomes public.
///
/// **On the way through it records what the marketplace offered** (hub#371). This is the only time
/// the hub ever sees the catalogue, and the "your apps" item of `hub.setup.status` needs it to tell
/// *"you still have to install an app"* apart from *"there is nothing you can install"* — which is
/// not the user's task but our own breakdown. The query cannot ask for itself: it is read by the
/// dashboard, by the assistant and by a strip on every screen, so a round-trip to the SaaS would put
/// the control plane on the critical path of every page. The whole rule of what counts as an answer
/// lives in `setup_status::record_catalog_response`, not here: a 403 or an odd body records nothing.
///
/// Demo is deliberately left out: its public catalogue is SaaS metadata, not *"what THIS hub can
/// install"*, so counting its rows would answer a different question.
/// Which build of the installable app the Cloud publishes right now (hub#400).
///
/// The page asks the runtime instead of the Cloud because it is served under
/// `connect-src 'self' ipc:`: a cross-origin fetch dies in the browser, without a log the till
/// could show. Here there is no CSP and the Cloud address is already configured.
///
/// **No credential travels.** The version of a public download is public (it is on the store
/// listing), and asking anonymously is what lets a hub in demo, unenrolled or just woken up still
/// tell its till that a newer app exists — with a token those hubs would get a 401, which the page
/// reads as "nothing new". Note the asymmetry with the marketplace proxy right above: that one
/// grants entitlements, this one reports a number.
///
/// A Cloud that does not answer produces an error status, never a version: the page turns anything
/// that is not a version into `unknown` — silence — and a number invented here would point a till
/// at an installer that does not exist.
async fn proxy_app_release(State(st): State<AppState>, headers: HeaderMap) -> Response {
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    proxy_public_cloud_get(&st, &headers, cloud.app_release()).await
}

async fn proxy_marketplace_catalog(State(st): State<AppState>, headers: HeaderMap) -> Response {
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    if st.is_dev_hub() {
        return proxy_public_cloud_get(&st, &headers, cloud.public_marketplace_modules()).await;
    }
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token: String::new(),
    };
    match cloud_get_raw(&st, &headers, cloud.marketplace_modules(&placeholder)).await {
        Ok((status, body)) => {
            let rt = st.runtime.lock().await;
            if let Err(e) =
                erplora_runtime::setup_status::record_catalog_response(rt.db(), status.as_u16(), &body)
                    .await
            {
                // Recording is a side effect of the proxy: if it fails the catalogue is served all
                // the same and the checklist is left not knowing — which is "pending", never a
                // false "unavailable".
                tracing::warn!(error = %e, "could not record the catalogue offer for the checklist");
            }
            cloud_json_passthrough(status, body)
        }
        Err(e) => cloud_get_error_response(e),
    }
}

/// GET /api/blueprints/catalog — catálogo de blueprints (proxy de `/api/v1/catalog/blueprints/`).
///
/// La **«fuente nube»** del panel de import (Ajustes → Datos). [ADR-0121]
async fn proxy_blueprints_catalog(State(st): State<AppState>, headers: HeaderMap) -> Response {
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token: String::new(),
    };
    proxy_cloud_get(&st, &headers, cloud.blueprints_catalog(&placeholder)).await
}

/// GET /api/blueprints/:slug/download — baja el `.blueprint.zip` y lo sirve al front.
///
/// El runtime hace de intermediario a propósito (ADR-0003): pide al SaaS la **URL firmada** con su
/// `X-Hub-Token` —que **nunca** llega al navegador—, descarga el zip de Object Storage y
/// **verifica el SHA256 ANTES de entregarlo**. Un hash que no casa aborta con 502 sin devolver
/// bytes: es el mismo contrato no-saltable que el install de módulos (ADR-0015).
///
/// Devuelve el zip crudo, así que el front lo trata **igual que un fichero local** y reusa el
/// flujo existente `inspect` → `import` (cero lógica de import duplicada).
async fn download_blueprint(
    State(st): State<AppState>,
    Path(slug): Path<String>,
    headers: HeaderMap,
) -> Response {
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    // Credencial hub-scoped: el token de máquina NUNCA llega al navegador (ADR-0003).
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return cloud_get_error_response(CloudGetError::NoCredential);
    };
    // El panel de import baja por slug sin idioma: si el catálogo tuviera ese slug en dos idiomas,
    // el SaaS contesta 400 y el front lo enseña — elegir uno al azar sería peor.
    match fetch_blueprint(&st, &auth, &slug, None).await {
        Ok(fetched) => (
            StatusCode::OK,
            [(axum::http::header::CONTENT_TYPE, "application/zip")],
            fetched.zip,
        )
            .into_response(),
        Err(BlueprintFetchError::Cloud { status, body }) => (
            status,
            [(axum::http::header::CONTENT_TYPE, "application/json")],
            body,
        )
            .into_response(),
        Err(BlueprintFetchError::Network(msg)) => {
            cloud_get_error_response(CloudGetError::Network(msg))
        }
        Err(BlueprintFetchError::Other(msg)) => bad_gateway(msg),
    }
}

/// Un `.blueprint.zip` ya descargado y **verificado**, con la versión que dijo el SaaS.
pub(crate) struct FetchedBlueprint {
    pub zip: axum::body::Bytes,
    pub version: String,
}

/// Por qué no se pudo traer un blueprint. Separa lo que el SaaS contestó (se reenvía tal cual al
/// front) de lo que pasó de camino, para que el llamador HTTP conserve su contrato de error.
pub(crate) enum BlueprintFetchError {
    /// El SaaS contestó un status de error (404 sin bundle, 400 slug ambiguo, 5xx…).
    Cloud {
        status: StatusCode,
        body: axum::body::Bytes,
    },
    /// No se pudo hablar con el Cloud / con Object Storage.
    Network(String),
    /// Respuesta ilegible o **integridad rota**: el mensaje ya es legible.
    Other(String),
}

impl BlueprintFetchError {
    /// Motivo en una línea (log, informe de error al Cloud).
    pub fn message(&self) -> String {
        match self {
            BlueprintFetchError::Cloud { status, body } => format!(
                "el SaaS contestó {status} al resolver el blueprint: {}",
                String::from_utf8_lossy(body)
            ),
            BlueprintFetchError::Network(msg) => msg.clone(),
            BlueprintFetchError::Other(msg) => msg.clone(),
        }
    }
}

/// Resuelve, descarga y **verifica** un `.blueprint.zip` del catálogo del SaaS.
///
/// Es el cuerpo de [`download_blueprint`] sin el guard de sesión de usuario, porque el arranque
/// (ADR-0212) hace exactamente esto **sin nadie logueado**: se autentica con el token de máquina.
/// El orden no es negociable (ADR-0015/ADR-0121): 1) el SaaS da URL firmada + `sha256`, 2) se baja
/// el zip de Object Storage, 3) **se verifica el hash ANTES de devolver un solo byte**.
pub(crate) async fn fetch_blueprint(
    st: &AppState,
    auth: &cloud_client::Auth,
    slug: &str,
    locale: Option<&str>,
) -> Result<FetchedBlueprint, BlueprintFetchError> {
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let req = cloud.blueprint_download(slug, locale, auth);

    // 1) URL firmada + sha256 + versión (hub-scoped: se autentica el runtime, no el usuario).
    let mut r = st.http.get(&req.url);
    for (k, v) in auth.headers() {
        r = r.header(k, v);
    }
    let resp = r
        .send()
        .await
        .map_err(|e| BlueprintFetchError::Network(e.to_string()))?;
    let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let body = resp
        .bytes()
        .await
        .map_err(|e| BlueprintFetchError::Network(e.to_string()))?;
    if !status.is_success() {
        return Err(BlueprintFetchError::Cloud { status, body });
    }

    let info: Value = serde_json::from_slice(&body)
        .map_err(|e| BlueprintFetchError::Other(format!("respuesta de blueprint ilegible: {e}")))?;
    let (Some(url), Some(expected)) = (info["url"].as_str(), info["sha256"].as_str()) else {
        return Err(BlueprintFetchError::Other(
            "el SaaS no expuso url/sha256 del blueprint".to_string(),
        ));
    };
    let version = info["version"].as_str().unwrap_or_default().to_string();

    // 2) Descarga directa de Object Storage (URL prefirmada: sin credenciales nuestras).
    let zip = match st.http.get(url).send().await {
        Ok(r) if r.status().is_success() => r
            .bytes()
            .await
            .map_err(|e| BlueprintFetchError::Network(format!("descarga interrumpida: {e}")))?,
        Ok(r) => {
            return Err(BlueprintFetchError::Other(format!(
                "Object Storage devolvió {} al bajar el blueprint",
                r.status()
            )))
        }
        Err(e) => {
            return Err(BlueprintFetchError::Network(format!(
                "no se pudo descargar el blueprint: {e}"
            )))
        }
    };

    // 3) 🔴 Integridad NO-SALTABLE (ADR-0015): si el hash no casa, no se entrega ni un byte.
    let actual = {
        use sha2::{Digest, Sha256};
        let mut h = Sha256::new();
        h.update(&zip);
        format!("{:x}", h.finalize())
    };
    if actual != expected {
        return Err(BlueprintFetchError::Other(format!(
            "integridad del blueprint «{slug}»: sha256 esperado {expected}, obtenido {actual} — import abortado"
        )));
    }

    Ok(FetchedBlueprint { zip, version })
}

/// 502 con el motivo en JSON (contrato de error del resto de proxies).
fn bad_gateway(reason: String) -> Response {
    (
        StatusCode::BAD_GATEWAY,
        Json(json!({ "ok": false, "error": reason })),
    )
        .into_response()
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
            let embedder =
                embed::CloudEmbedder::new(st.http.clone(), &st.config.cloud_base_url, auth.clone());
            router::assemble_routed_tools(
                &embedder,
                store.as_ref(),
                &st.hub_id(),
                &query,
                all_tools,
                active_modules,
                router::RouterConfig::default(),
            )
            .await
        }
        None => all_tools,
    };

    // Mapa name→kind (query/command) del catálogo ofrecido, para anotar los eventos
    // `function_call` que reenviamos: el web app auto-ejecuta las LECTURAS (query) y pide
    // confirmación antes de una ESCRITURA (command). §9.2.
    let tool_kinds: std::collections::HashMap<String, String> = tools
        .iter()
        .filter_map(|t| {
            let name = t.get("name").and_then(|v| v.as_str())?;
            let kind = t.get("kind").and_then(|v| v.as_str())?;
            Some((name.to_string(), kind.to_string()))
        })
        .collect();

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
                if let Some(frame) = assistant::translate_sse_line(line, &tool_kinds) {
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
                        if let Some(frame) = assistant::translate_sse_line(rest.trim(), &tool_kinds) {
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

/// HTTP status + stable error code of a runtime error.
///
/// Split out of [`err_response`] (hub#343) because the print host's WS channel has to answer with
/// **the same codes** and cannot go through a `Response` to get them. One table, so the code a
/// module or the drain declares cannot mean one thing over HTTP and another over the socket.
pub(crate) fn err_status_and_code(
    e: &erplora_runtime::RuntimeError,
) -> (StatusCode, std::borrow::Cow<'_, str>) {
    use erplora_runtime::RuntimeError as E;
    // `Cow` because `Domain` (hub#139) carries a module-declared dynamic code; every other
    // variant keeps its static stable code.
    match e {
        E::PermissionDenied(_) => (StatusCode::FORBIDDEN, "permission_denied".into()),
        E::QueryNotFound(_) | E::CommandNotFound(_) => (StatusCode::NOT_FOUND, "not_found".into()),
        // hub#131, hub#145: un command interno (prefijo `_`/`internal:true`) invocado desde un
        // origen EXTERNO. `403` (como `permission_denied`): el command EXISTE, pero esta puerta
        // no es la suya — nunca `404`, que sugeriría que ni siquiera está registrado.
        E::InternalCommand(_) => (StatusCode::FORBIDDEN, "internal_command".into()),
        // ADR-0127: `queryOptional` del SDK devuelve `undefined` SOLO con este código; un
        // `not_found` normal (contrato roto contra un módulo presente) sigue siendo un error.
        E::ModuleNotInstalled { .. } => (StatusCode::NOT_FOUND, "module_not_installed".into()),
        E::ModuleInactive { .. } => (StatusCode::NOT_FOUND, "module_inactive".into()),
        E::InvalidPayload { .. } => (StatusCode::UNPROCESSABLE_ENTITY, "invalid_payload".into()),
        // hub#139: a business rejection is NOT a generic WASM failure. The namespaced code
        // travels verbatim so the UI can translate it, and `queryOptional` never swallows it.
        // `409`: the request is well-formed, it conflicts with the current business state.
        E::Domain { code, .. } => (StatusCode::CONFLICT, code.as_str().into()),
        // hub#139/hub#140: the affected-rows gate carries its stable kind code (`not_found` /
        // `conflict`) to the caller instead of collapsing into the generic 400 bucket.
        E::MinAffectedRows { kind, .. } => (StatusCode::CONFLICT, kind.as_str().into()),
        // hub#328 (ADR-0203): the fiscal precondition gate — the hub's state (missing business
        // identity/certificate), not the request, blocks emitting fiscal documents. `409`: the
        // request is well-formed and allowed, it conflicts with the hub's current setup state.
        E::FiscalPrecondition { .. } => (StatusCode::CONFLICT, "fiscal_precondition_failed".into()),
        // hub#376 (ADR-0197 §4): this hub IS an ephemeral demo, so its fiscal environment,
        // certificate and identity are not its own. `409` for the same reason as above — the
        // request is well-formed and allowed, it conflicts with what this deploy IS. The code is
        // the SUBJECT of the lock, never a flat `demo_locked`: the UI has to be able to say WHICH
        // of the three refused, and three guards sharing one answer means two can be deleted with
        // the suite still green.
        E::DemoLocked { lock } => (StatusCode::CONFLICT, lock.as_str().into()),
        // hub#360 (paso 2b): a refusal a MANAGER could approve. `403` like `permission_denied` —
        // it IS a refusal and nothing ran — but with its own stable code, so the UI can tell
        // "ask the manager" (offer the PIN dialog, hub#363) from "this is not for you". Falling
        // into the generic `400 {code:"error"}` bucket would have made the whole chain undecidable.
        E::RequiresElevation { .. } => (StatusCode::FORBIDDEN, "requires_elevation".into()),
        E::NotImplemented(_) => (StatusCode::NOT_IMPLEMENTED, "not_implemented".into()),
        _ => (StatusCode::BAD_REQUEST, "error".into()),
    }
}

pub(crate) fn err_response(e: erplora_runtime::RuntimeError) -> Response {
    use erplora_runtime::RuntimeError as E;
    let (status, code) = err_status_and_code(&e);
    let mut error = json!({ "code": code, "message": e.to_string() });
    // hub#360: the missing permission travels as a FIELD, never parsed out of the message — it is
    // what the dialog names and what hub#361 re-checks. Only on the elevation branch: a flat
    // refusal must not look like an offer to elevate.
    if let E::RequiresElevation { permission } = &e {
        error["permission"] = json!(permission);
    }
    (status, Json(json!({ "ok": false, "error": error }))).into_response()
}

/// Respuesta para un fallo de **enrutado multi-tenant** (ADR-0005, hub#24):
///  - `UnknownOrg` → `403`: el `hub_id` de la petición no pertenece a ninguna org conocida; es un
///    intento de acceso cruzado o un hub no provisionado. **No** se cae a ninguna BD.
///  - `PoolLimit` → `503`: back-pressure (techo de orgs por proceso alcanzado), reintenta luego.
///  - `Connect`   → `502`: la Aurora de la org no responde (failover/credencial).
pub(crate) fn tenant_rejected(e: tenant::TenantError) -> Response {
    use tenant::TenantError as T;
    let (status, code) = match &e {
        T::UnknownOrg(_) => (StatusCode::FORBIDDEN, "unknown_org"),
        T::PoolLimit(_) => (StatusCode::SERVICE_UNAVAILABLE, "pool_limit"),
        T::Connect(_) => (StatusCode::BAD_GATEWAY, "org_db_unavailable"),
    };
    let body = json!({ "ok": false, "error": { "code": code, "message": e.to_string() } });
    (status, Json(body)).into_response()
}

/// Gate del dispatcher (revalidación híbrida del entitlement, ver `crate::entitlement`): si el
/// módulo dueño de la query/command está **bloqueado**, devuelve el error estable
/// `module_entitlement_blocked` (HTTP 402) con su `module_id` para que el front lo distinga y
/// pinte el aviso («funcionará hasta {fecha}»). `None` = no bloqueado → la ejecución sigue.
/// Defensa en profundidad: el enforcement REAL es el proxy del SaaS; aquí NUNCA se desinstala
/// ni se tocan datos. `module_id = None` (op desconocida) no se gatea: `execute_*` devolverá su
/// `not_found` de siempre.
fn entitlement_blocked(st: &AppState, module_id: Option<&str>) -> Option<Response> {
    let module_id = module_id?;
    let blocked = st
        .entitlement
        .read()
        .ok()?
        .is_blocked(module_id, entitlement::now_unix());
    if !blocked {
        return None;
    }
    let body = json!({ "ok": false, "error": {
        "code": "module_entitlement_blocked",
        "module_id": module_id,
        "message": format!("el módulo `{module_id}` no está incluido en el entitlement vigente del hub"),
    }});
    Some((StatusCode::PAYMENT_REQUIRED, Json(body)).into_response())
}

/// `401` uniforme para fallos de autenticación (modo Jwt: token ausente/ inválido).
fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// Query param de idioma para los endpoints localizables (ADR-0055). `?locale=es`; default `en`.
#[derive(serde::Deserialize)]
struct LocaleQuery {
    locale: Option<String>,
}

async fn navigation(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<LocaleQuery>,
) -> Response {
    let locale = q.locale.as_deref().unwrap_or("en");
    let rt = st.runtime.lock().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let reg = rt.registry();
    let items: Vec<Value> = rt
        .navigation()
        .iter()
        .map(|n| {
            let mod_fallback = reg
                .installed
                .iter()
                .find(|m| m.id == n.module_id)
                .map(|m| m.name.as_str())
                .unwrap_or(n.module_id.as_str());
            json!({
                "module_id": n.module_id,
                // Nombre del módulo traducido (ADR-0055): lo usa el shell para el sidebar y las
                // tarjetas del dashboard (un ítem por módulo).
                "module_name": reg.module_name_localized(&n.module_id, mod_fallback, locale),
                "id": n.nav.id,
                // Label de la pestaña traducido (ADR-0055): locale → en → label del manifest.
                "label": reg.nav_label_localized(&n.module_id, &n.nav.id, &n.nav.label, locale),
                "icon": n.nav.icon, "component": n.nav.component,
            })
        })
        .collect();
    Json(json!({ "ok": true, "data": items })).into_response()
}

async fn list_modules(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<LocaleQuery>,
) -> Response {
    let locale = q.locale.as_deref().unwrap_or("en");
    let rt = st.runtime.lock().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let reg = rt.registry();
    // Ids de módulos (activos) que exponen al menos una op `expose_api` (ADR-0057). Se calcula UNA
    // vez y se consulta por pertenencia → campo aditivo `has_public_api` por módulo, que usa la
    // matriz de scope de las API keys para listar solo módulos que conceden algo.
    let public_api: std::collections::HashSet<String> =
        reg.modules_with_public_api().into_iter().collect();
    let items: Vec<Value> = rt
        .modules()
        .into_iter()
        .map(|m| {
            json!({
                "id": m.id,
                // Nombre traducido (ADR-0055): locale → en → name del manifest.
                "name": reg.module_name_localized(&m.id, &m.name, locale),
                "version": m.version,
                "status": m.status,
                // Dependencias declaradas: el toggle del shell las usa para AVISAR de la cascada
                // (ADR-0128) antes de desactivar («también desactivará: …»).
                "depends_on": m.depends_on,
                // ADITIVO (ADR-0057): true si el módulo expone alguna query/command `expose_api`.
                "has_public_api": public_api.contains(&m.id),
            })
        })
        .collect();
    Json(json!({ "ok": true, "data": items })).into_response()
}

/// `POST /api/modules/install {dir}` — instala un módulo desde una carpeta YA extraída.
///
/// Vía de **desarrollo**: esquiva el pipeline del marketplace (grant + SHA256 obligatorio,
/// ADR-0015), así que va doblemente gateada (hub#239, ver [`install_guard`]): modo desarrollo
/// explícito + `dir` confinado en el staging del hub. La sesión admin sigue siendo necesaria,
/// pero **no basta**: el agujero no era de auth, era de superficie.
async fn install_module(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<InstallReq>,
) -> Response {
    let mut rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let dir = match install_guard::resolve_install_dir(
        st.config.dev_mode,
        &st.config.install_staging_roots(),
        &req.dir,
    ) {
        Ok(dir) => dir,
        Err(rejection) => return install_dir_rejected(&req.dir, rejection),
    };
    match rt.install_from_dir(&dir).await {
        Ok(id) => Json(json!({ "ok": true, "data": { "module_id": id } })).into_response(),
        Err(e) => err_response(e),
    }
}

/// Respuesta estable a un `dir` de instalación rechazado (hub#239). `403` cuando la vía está
/// cerrada por política (producción / fuera del staging), `422` cuando la ruta simplemente no
/// sirve. Se registra a WARN: un intento fuera del staging es señal de abuso, no ruido.
fn install_dir_rejected(requested: &str, rejection: install_guard::InstallDirRejection) -> Response {
    use install_guard::InstallDirRejection as R;
    let status = match rejection {
        R::DevModeRequired | R::OutsideStaging => StatusCode::FORBIDDEN,
        R::NotFound | R::NotADirectory => StatusCode::UNPROCESSABLE_ENTITY,
    };
    tracing::warn!(
        dir = %requested,
        code = rejection.code(),
        "instalación desde carpeta rechazada"
    );
    let body = json!({
        "ok": false,
        "error": { "code": rejection.code(), "message": rejection.message() },
    });
    (status, Json(body)).into_response()
}

async fn activate_module(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let mut rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.activate(&id).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn deactivate_module(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let mut rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.deactivate(&id).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

async fn uninstall_module(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let mut rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.uninstall(&id).await {
        Ok(()) => {
            drop(rt);
            // Borra del índice vectorial los chunks del módulo (§9.6): uninstall → delete chunks.
            // Best-effort: no falla la desinstalación si el store da error.
            if let Some(store) = &st.vector {
                if let Err(e) = embed::drop_module(store.as_ref(), &st.hub_id(), &id).await {
                    tracing::warn!(module_id = %id, error = %e, "no se pudieron borrar embeddings del módulo (no crítico)");
                }
            }
            Json(json!({ "ok": true })).into_response()
        }
        Err(e) => err_response(e),
    }
}

async fn query(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<QueryReq>,
) -> Response {
    // Tier cloud compartido (ADR-0005): resuelve el runtime de la ORG dueña del `hub_id` de la
    // petición (un pool por org). En single-tenant devuelve el runtime único. El rechazo cross-org
    // (hub_id de org desconocida) ocurre aquí, ANTES de tocar ninguna BD.
    let arc = match st.runtime_for(&auth::hub_id(&headers, &st.hub_id())).await {
        Ok(rt) => rt,
        Err(e) => return tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(c) => c,
        Err(e) => return unauthorized(e),
    };
    // Gate de entitlement (defensa en profundidad): módulo dueño bloqueado → 402 estable.
    let owner = rt
        .registry()
        .get_query(&req.name)
        .map(|q| q.module_id.clone());
    if let Some(resp) = entitlement_blocked(&st, owner.as_deref()) {
        return resp;
    }
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

async fn command(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CommandReq>,
) -> Response {
    // Mismo enrutado por org que `query` (ADR-0005): el `PgAdapter` de la org corre server-side.
    let arc = match st.runtime_for(&auth::hub_id(&headers, &st.hub_id())).await {
        Ok(rt) => rt,
        Err(e) => return tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(c) => c,
        Err(e) => return unauthorized(e),
    };
    // hub#361: a step-up approval the caller already obtained, presented OUT OF BAND. It is a
    // lookup key into the runtime's own store — an unknown or foreign one is worth exactly as
    // much as no header at all — and it is read here and not in `authenticate` on purpose:
    // `/api/query` never elevates (a PIN that unlocks a report leaves no trace of who approved),
    // and neither does the public API-key surface (nobody is standing at an integration).
    let ctx = match auth::elevation_token(&headers) {
        Some(token) => ctx.with_elevation_token(token),
        None => ctx,
    };
    // Gate de entitlement (defensa en profundidad): módulo dueño bloqueado → 402 estable.
    let owner = rt
        .registry()
        .get_command(&req.name)
        .map(|c| c.module_id.clone());
    if let Some(resp) = entitlement_blocked(&st, owner.as_deref()) {
        return resp;
    }
    match rt.execute_command(&req.name, &req.payload, &ctx).await {
        Ok(data) => Json(json!({ "ok": true, "data": data })).into_response(),
        Err(e) => err_response(e),
    }
}

/// Body de `POST /api/error-report` (lo postea el frontend). Forma libre del web app:
/// `{ type, message, stack?, url?, component?, module_id? }`. `type` mapea a `error_code`.
#[derive(Deserialize)]
struct FrontendErrorReq {
    /// Tipo del error JS (p. ej. `"js_error"`); se usa como `error_code` del evento.
    #[serde(default = "default_js_error_type")]
    r#type: String,
    #[serde(default)]
    message: String,
    #[serde(default)]
    stack: Option<String>,
    #[serde(default)]
    url: Option<String>,
    #[serde(default)]
    component: Option<String>,
    /// Si el error vino de un Web Component de módulo, su `module_id` (atribución).
    #[serde(default)]
    module_id: Option<String>,
}

fn default_js_error_type() -> String {
    "js_error".to_string()
}

/// POST /api/error-report — embudo del frontend hacia el registro global de errores.
///
/// Same-origin, **sin auth cloud** (el navegador nunca ve el `cloud_api_token`): el web app postea
/// su error JS y el runtime lo normaliza a un `ErrorEvent{ source:"frontend", … }`, lo manda al
/// registro global (que dedup/throttlea y reenvía al Cloud por el sink) y devuelve `{ "ok": true }`.
/// Severidad fija "unexpected" (un error JS no capturado es un fallo, no una acción de usuario).
async fn frontend_error_report(Json(req): Json<FrontendErrorReq>) -> Response {
    use erplora_runtime::error_registry::{severity, source, ErrorEvent, ErrorRegistry};

    let mut event = ErrorEvent::new(
        source::FRONTEND,
        req.r#type,
        req.message,
        severity::UNEXPECTED,
    )
    .with_context(json!({ "url": req.url, "component": req.component }));
    if let Some(stack) = req.stack {
        event = event.with_stack(stack);
    }
    if let Some(module_id) = req.module_id {
        event = event.with_module(module_id);
    }
    ErrorRegistry::global().report(event);

    Json(json!({ "ok": true })).into_response()
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
    /// Email inicial de la identidad Cloud. Solo si el perfil local aún no tiene uno: después el
    /// usuario es dueño de sus datos y un login no pisa una edición hecha en Perfil.
    #[serde(default)]
    email: Option<String>,
    /// Id del dispositivo a marcar de confianza tras este login online (§2.9). Opcional.
    #[serde(default)]
    device_id: Option<String>,
}

/// Login local por **PIN** → abre sesión. Body `{name, pin, device_id?}` → `{ok, token, user}`
/// (401 si falla). Con **device-trust armado** (por defecto; `HUB_DEVICE_TRUST=off` lo desarma) el
/// PIN se rechaza si el cliente no identifica el dispositivo o si ese dispositivo no es de
/// confianza — no hubo login online previo en él (§2.9, hub#330).
///
/// **Los dos rechazos son distintos a propósito**, y no es un oráculo: el que llama ya sabe si mandó
/// un id o no, así que separarlos no le dice nada que no supiera, y sí le dice a la pantalla cuál de
/// las **dos** frases enseñar («este navegador no puede identificarse» ≠ «entra una vez con tu
/// cuenta aquí»). Lo que sí se mantiene indistinguible es *desconocido* de *revocado*: los dos son
/// `device_untrusted`, con el mismo texto, para que la puerta no confirme si alguien cortó un
/// dispositivo perdido (ADR-0258).
async fn auth_pin(State(st): State<AppState>, Json(req): Json<PinReq>) -> Response {
    let rt = st.runtime.lock().await;
    // Qué dispositivo dice ser este cliente. **Se normaliza una sola vez** y de aquí sale todo lo
    // demás: una cabecera de espacios es un cliente que no se identificó, y tiene que caer en la
    // misma rama que no mandar nada — nunca en una búsqueda de `"  "` ni, con la puerta desarmada,
    // en una sesión cuyo dispositivo es la cadena vacía. Espejo de `device_mode::device_id_of`.
    let device_id = req
        .device_id
        .as_deref()
        .map(str::trim)
        .filter(|id| !id.is_empty());
    if st.config.device_trust_enforce {
        // No `device_id`, no bypass (hub#330): the check used to sit in an `if let Some(..)` with
        // no `else`, so leaving the field out walked past the gate entirely. The hub lives on the
        // public internet, so an unidentified device is the shape of the attack, not an oversight.
        let Some(device_id) = device_id else {
            return (
                StatusCode::FORBIDDEN,
                Json(json!({
                    "ok": false,
                    "error": "this client did not identify its device",
                    "code": "device_unidentified"
                })),
            )
                .into_response();
        };
        match rt.is_device_trusted(device_id).await {
            Ok(true) => {}
            Ok(false) => {
                return (
                    StatusCode::FORBIDDEN,
                    Json(json!({
                        "ok": false,
                        "error": "this device has not signed in with an account yet",
                        "code": "device_untrusted"
                    })),
                )
                    .into_response()
            }
            Err(e) => return err_response(e),
        }
    }
    // Brute-force guard (hub#329): checked BEFORE verifying, so a locked identity stops leaking
    // the right/wrong signal an attacker is fishing for.
    if let Some(retry_after_secs) = st.login_throttle.locked_for(&req.name) {
        return (
            StatusCode::TOO_MANY_REQUESTS,
            Json(json!({
                "ok": false,
                "error": "demasiados intentos fallidos: espera unos minutos",
                "code": "too_many_attempts",
                "retry_after_secs": retry_after_secs
            })),
        )
            .into_response();
    }
    match rt.verify_pin(&req.name, &req.pin).await {
        Ok(Some(user)) => {
            st.login_throttle.record_success(&req.name);
            // Límite de dispositivos del plan (ADR-0154): lo aporta el estado de entitlement del
            // server (fail-open a 0 = ilimitado si el lock está envenenado o aún no hubo refresh).
            let max_devices = st.entitlement.read().map(|g| g.max_devices()).unwrap_or(0);
            mint_session(&rt, user, device_id, max_devices).await
        }
        Ok(None) => {
            st.login_throttle.record_failure(&req.name);
            (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": "usuario o PIN incorrecto" })),
            )
                .into_response()
        }
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
    open_cloud_session(&st, &token, body.map(|value| value.0), None).await
}

/// Shared implementation for ordinary Cloud login and the shell courier.  Keeping the JWT gate,
/// membership check and local user linking in one function ensures the courier cannot create a
/// more privileged path than `POST /api/auth/cloud`.
async fn open_cloud_session(
    st: &AppState,
    token: &str,
    body: Option<CloudLoginReq>,
    cloud_tokens: Option<Value>,
) -> Response {
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
    let hub_id = st.hub_id();
    let cloud_user_id = claims.user_id_str();
    let device_id = body.as_ref().and_then(|b| b.device_id.clone());
    let email = body.as_ref().and_then(|b| b.email.clone());
    let name = body
        .as_ref()
        .and_then(|b| b.name.clone())
        .unwrap_or_else(|| format!("user:{cloud_user_id}"));
    // Rol LOCAL por defecto al provisionar un miembro nuevo que aún no tiene `hub_user` (ADR-0157
    // §6: los roles operativos del Hub son locales/custom, ortogonales al rol SaaS). Se elige el
    // rol de **mínimo privilegio** (`employee`), NO `admin` a ciegas: el auto-admin era el hueco
    // que este ADR cierra. Configurable por entorno (`HUB_DEFAULT_ROLE`).
    let base_role = std::env::var("HUB_DEFAULT_ROLE").unwrap_or_else(|_| "employee".into());
    // …unless the SaaS says this user is owner/admin OF THE HUB they are entering (ADR-0201:
    // membership is per hub). That fact already travelled in the token and the Hub threw it away, so
    // an account admin walked into their own hub as an `employee`, unable to import a blueprint or
    // to promote themselves: only the email seeded at deploy time had privilege. See
    // `local_role_for_cloud_login`: only owner/admin rise, and only to `admin`.
    //
    // The role travels in TWO shapes for as long as the transition lasts (hub#350): the new key
    // `hubs[].role` and the legacy mirror `organizations[].role` (× `hubs[].org`). Both are read —
    // that is what lets the SaaS retire the mirror (saas#1177) without dropping anybody's role —
    // and when they disagree the least privileged one wins (see `role_floor_for_cloud_login`).
    let cloud_roles = claims.role_keys_for_hub(&hub_id);
    let default_role = crate::auth::local_role_for_cloud_login(&cloud_roles, &base_role);
    // El mismo rol de cuenta es además un **SUELO reevaluado en CADA login** (paso 2b regla C,
    // hub#347), no solo el rol con el que se provisiona la fila nueva. Antes el rol local era una
    // foto del primer login —`get_or_link_cloud_user` devolvía la fila intacta— y ascender a
    // alguien en el SaaS no llegaba nunca al hub. El suelo solo SUBE: no baja el rol local (quitar
    // el acceso es desactivar el `hub_user`, regla D, no degradarlo en silencio) y no concede
    // `owner` (la propiedad sale de `HUB_OWNER_EMAIL`, ADR-0157).
    let role_floor = crate::auth::role_floor_for_cloud_login(&cloud_roles);
    // **Owner sembrado del env, NO «primer login = owner»** (ADR-0157, corrección de Ioan): el owner
    // es el CREADOR del hub, sembrado por el provisioning del SaaS (`HUB_OWNER_EMAIL`) ANTES del
    // primer login (ver `serve()`). El **enlace** del login con ese owner (y con cualquier usuario
    // **invitado** por el admin) se hace por **email**: `get_or_link_cloud_user` resuelve primero por
    // `cloud_user_id`, luego por email (fila pre-provisionada sin `cloud_user_id`, conservando su
    // rol), y solo si no hay coincidencia crea una fila con el rol de mínimo privilegio. Preferimos
    // el email del **token** (autenticado) sobre el del body (cliente).
    let login_email = if !claims.email.trim().is_empty() {
        Some(claims.email.clone())
    } else {
        email.clone()
    };
    let rt = st.runtime.lock().await;
    // ── Gate de presencia (ADR-0157 §5) + regla D (hub#348) ──────────────────────────────────
    // La autenticación (¿es un JWT válido del SaaS?) NO implica autorización (¿pertenece a ESTE
    // hub?). El token lleva el claim *coarse* `hubs: [{id, org}]` y el Hub solo deja entrar si el
    // `hub_id` de esta máquina figura ahí. Eso cerró el auto-admin (cualquier JWT válido quedaba
    // admin local); un token sin el claim (SaaS legacy) trae `hubs` vacío → no es miembro.
    //
    // Rechazar el login era solo la mitad: al miembro revocado le quedaban intactas la sesión ya
    // abierta (TTL 30 días), el PIN y su sitio en el pinpad, así que seguía trabajando como si
    // nada. La otra mitad —regla D— es **cerrar el `hub_user`**: desactivarlo cae de una vez sobre
    // todas esas puertas. Se hace ANTES de responder y con el mismo token autenticado que prueba
    // la revocación.
    if !claims.is_member_of_hub(&hub_id) {
        if let Err(e) = rt
            .revoke_cloud_access(&cloud_user_id, login_email.as_deref())
            .await
        {
            // El cierre local falló, pero el rechazo no se negocia: se registra y se sigue.
            tracing::error!(error = %e, "rule D: could not deactivate the revoked hub_user");
        }
        return (
            StatusCode::FORBIDDEN,
            Json(json!({
                "ok": false,
                "error": "you are not a member of this hub: ask an administrator for an invitation",
                "code": "not_a_member",
            })),
        )
            .into_response();
    }
    match rt
        .get_or_link_cloud_user(
            &cloud_user_id,
            &name,
            &default_role,
            login_email.as_deref(),
            role_floor,
        )
        .await
    {
        Ok(user) => {
            // Si es el primer login, siembra el correo Cloud en el perfil local. Una vez existe,
            // NO se sobreescribe: las ediciones de `/profile` pertenecen al usuario.
            if let Some(email) = email.filter(|s| !s.trim().is_empty()) {
                if let Ok(profile) = rt.user_profile(&user.id).await {
                    if profile.email.is_empty() {
                        let _ = rt
                            .update_user_profile(
                                &user.id,
                                &erplora_runtime::user_profile::UpdateUserProfile {
                                    first_name: profile.first_name,
                                    last_name: profile.last_name,
                                    email,
                                    preferences: profile.preferences,
                                },
                            )
                            .await;
                    }
                }
            }
            // Device-trust (§2.9): este es un login ONLINE correcto → marca el dispositivo de
            // confianza para habilitar luego el login local por PIN. Best-effort (no bloquea el
            // login si falla el marcado).
            if let Some(device_id) = device_id.as_deref() {
                let _ = rt.trust_device(device_id, &name).await;
            }
            // Límite de dispositivos del plan (ADR-0154), como en el login por PIN.
            let max_devices = st.entitlement.read().map(|g| g.max_devices()).unwrap_or(0);
            mint_session_with_extra(
                &rt,
                user,
                device_id.as_deref(),
                max_devices,
                cloud_tokens,
            )
            .await
        }
        // Puerta cerrada POR EL HUB (regla D, hub#348): el `hub_user` está desactivado y la
        // membresía no lo reabre. Es un rechazo de acceso, no un conflicto de estado, así que sale
        // como `403` con el mismo formato plano que `not_a_member` —el que ya lee el shell— en vez
        // del `409` genérico de un error de dominio.
        Err(erplora_runtime::RuntimeError::Domain { code, message })
            if code == erplora_runtime::identity::DEACTIVATED_ERROR_CODE =>
        {
            (
                StatusCode::FORBIDDEN,
                Json(json!({ "ok": false, "error": message, "code": code })),
            )
                .into_response()
        }
        Err(e) => err_response(e),
    }
}

#[derive(serde::Deserialize)]
struct CourierReq {
    code: String,
    #[serde(default)]
    device_id: Option<String>,
}

#[derive(serde::Deserialize)]
struct CourierGrantUser {
    id: String,
    name: String,
    email: String,
}

#[derive(serde::Deserialize)]
struct CourierGrant {
    access: String,
    refresh: String,
    user: CourierGrantUser,
}

/// Boot courier for the native shell.  The browser submits only the opaque code to its same-origin
/// runtime.  The runtime redeems it server-to-server with its machine credential, then feeds the
/// access JWT through the exact same `/api/auth/cloud` implementation.  JWTs never appear in a URL.
async fn auth_courier(State(st): State<AppState>, Json(req): Json<CourierReq>) -> Response {
    let code = req.code.trim();
    if code.is_empty() || code.len() > 128 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": "código courier inválido" })),
        )
            .into_response();
    }
    let Some(machine_auth) = auth::machine_auth(&st) else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "ok": false, "error": "hub sin credencial de máquina" })),
        )
            .into_response();
    };
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let prepared = cloud.session_courier(&machine_auth);
    let mut upstream = st.http.post(&prepared.url).json(&json!({ "code": code }));
    for (name, value) in prepared.headers {
        upstream = upstream.header(name, value);
    }
    let response = match upstream.send().await {
        Ok(response) => response,
        Err(error) => {
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "ok": false, "error": format!("courier no disponible: {error}") })),
            )
                .into_response()
        }
    };
    if !response.status().is_success() {
        let status = if response.status().as_u16() == 400 {
            StatusCode::BAD_REQUEST
        } else {
            StatusCode::BAD_GATEWAY
        };
        return (
            status,
            Json(json!({ "ok": false, "error": "código courier inválido o caducado" })),
        )
            .into_response();
    }
    let grant = match response.json::<CourierGrant>().await {
        Ok(grant) if !grant.access.is_empty() && !grant.refresh.is_empty() => grant,
        _ => {
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "ok": false, "error": "respuesta courier inválida" })),
            )
                .into_response()
        }
    };
    let cloud_tokens = json!({
        "access": grant.access,
        "refresh": grant.refresh,
        "cloud_user": {
            "id": grant.user.id,
            "name": grant.user.name,
            "email": grant.user.email,
        }
    });
    let access = cloud_tokens["access"].as_str().unwrap_or_default().to_string();
    let login = CloudLoginReq {
        name: cloud_tokens["cloud_user"]["name"].as_str().map(str::to_string),
        email: cloud_tokens["cloud_user"]["email"].as_str().map(str::to_string),
        device_id: req.device_id,
    };
    open_cloud_session(&st, &access, Some(login), Some(cloud_tokens)).await
}

#[derive(serde::Deserialize)]
struct SetPinReq {
    pin: String,
}

/// Fija el PIN del **usuario de la sesión actual** (`X-Hub-Session`). Lo usa el alta de PIN tras el
/// primer login cloud (§2.9): el usuario ya está autenticado por su JWT→sesión y elige su PIN en
/// este dispositivo de confianza. Body `{pin}` (4 dígitos; vacío lo borra). → `{ok}` (401 sin sesión).
async fn auth_set_pin(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<SetPinReq>,
) -> Response {
    let rt = st.runtime.lock().await;
    let Some(token) = auth::session_token(&headers) else {
        return unauthorized(auth::AuthError::MissingSession);
    };
    let user = match rt.resolve_session(&token).await {
        Ok(Some(u)) => u,
        Ok(None) => {
            return unauthorized(auth::AuthError::Invalid(
                "sesión inválida o caducada".into(),
            ))
        }
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
///
/// `device_id` = identidad del dispositivo del login (o `None`); `max_devices` = límite del plan
/// (ADR-0154), leído del estado de entitlement del server. Con `max_devices == 1` y `device_id`
/// presente se aplica *single active device session*: se desalojan las sesiones de otros
/// dispositivos ANTES de abrir la nueva (takeover; la sesión desalojada da 401 en su siguiente
/// petición al no resolver). `0` = ilimitado / sin `device_id` = comportamiento actual.
async fn mint_session(
    rt: &erplora_runtime::Runtime,
    user: erplora_runtime::identity::HubUser,
    device_id: Option<&str>,
    max_devices: u32,
) -> Response {
    mint_session_with_extra(rt, user, device_id, max_devices, None).await
}

async fn mint_session_with_extra(
    rt: &erplora_runtime::Runtime,
    user: erplora_runtime::identity::HubUser,
    device_id: Option<&str>,
    max_devices: u32,
    extra: Option<Value>,
) -> Response {
    if let Err(e) = rt.enforce_device_limit(max_devices, device_id).await {
        return err_response(e);
    }
    // Cuánto vive la sesión lo decide el MODO DEL DISPOSITIVO (hub#358), no una constante global:
    // un mostrador caduca dentro del turno que abrió y el equipo propio conserva la sesión larga.
    // Sin `device_id` (cliente que no dice cuál es) sale la **corta** — la misma dirección
    // fail-closed que el propio modo: no identificarse nunca compra la sesión larga.
    let ttl_secs = match rt
        .session_ttl_for_device(device_id.unwrap_or_default())
        .await
    {
        Ok(ttl) => ttl,
        Err(e) => return err_response(e),
    };
    match rt.create_session(&user.id, ttl_secs, device_id).await {
        Ok(token) => {
            let permissions = rt.session_permissions(&user.role);
            let mut payload = json!({
                "ok": true,
                "token": token,
                "user": user,
                "permissions": permissions,
            });
            if let (Some(target), Some(source)) = (
                payload.as_object_mut(),
                extra.and_then(|value| value.as_object().cloned()),
            ) {
                target.extend(source);
            }
            Json(payload).into_response()
        }
        Err(e) => err_response(e),
    }
}

#[cfg(test)]
mod err_response_tests {
    //! hub#139: HTTP mapping of the domain error channel. The namespaced code must travel to
    //! the caller verbatim (the UI translates by code), on a status the SDK never swallows.
    use super::err_response;
    use axum::http::StatusCode;
    use erplora_runtime::RuntimeError;
    use http_body_util::BodyExt;
    use serde_json::Value;

    async fn shape(e: RuntimeError) -> (StatusCode, Value) {
        let resp = err_response(e);
        let status = resp.status();
        let bytes = resp.into_body().collect().await.unwrap().to_bytes();
        (status, serde_json::from_slice(&bytes).unwrap())
    }

    #[tokio::test]
    async fn domain_error_maps_to_409_with_the_namespaced_code() {
        let (status, body) = shape(RuntimeError::Domain {
            code: "inventory.insufficient_stock".into(),
            message: "Not enough stock".into(),
        })
        .await;
        assert_eq!(status, StatusCode::CONFLICT);
        assert_eq!(body["ok"], Value::Bool(false));
        assert_eq!(body["error"]["code"], "inventory.insufficient_stock");
        assert_eq!(body["error"]["message"], "Not enough stock");
    }

    #[tokio::test]
    async fn min_affected_rows_maps_to_409_with_its_stable_kind_code() {
        // Before hub#139 this fell into the generic 400 `{code:"error"}` bucket, erasing the
        // stable `not_found`/`conflict` code hub#140 introduced at the runtime layer.
        let (status, body) = shape(RuntimeError::MinAffectedRows {
            command: "w140.items.confirm".into(),
            required: 1,
            affected: 0,
            kind: erplora_runtime::errors::AffectedKind::NotFound,
        })
        .await;
        assert_eq!(status, StatusCode::CONFLICT);
        assert_eq!(body["error"]["code"], "not_found");
    }
}
