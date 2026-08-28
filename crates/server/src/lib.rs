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
//!   GET  /api/modules/updates                qué versión ofrece hoy el marketplace por módulo
//!                                            instalado (hub#516). Bajo demanda, no en bucle.
//!   POST /api/modules/:id/activate
//!   POST /api/modules/:id/deactivate
//!   POST /api/modules/:id/uninstall
//!   POST /api/modules/:id/update {version?}  actualiza un módulo instalado (hub#516). Mismo
//!                                            pipeline verificado que instalar; sin `version`,
//!                                            resuelve la que toca (cuarentena y pin mandan).
//!   POST /api/query   {name, params}
//!   POST /api/command {name, payload}
//!   GET  /ws                                 stream de eventos (solo push)
//!   GET  /ws/print                           canal del host de impresión (bidireccional, hub#343)

use axum::body::Body;
use axum::extract::{Path, Query, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
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
pub mod assistant_report;
pub mod auth;
pub mod boot_announce;
pub mod daily_usage;
/// `shared` (counter till) vs `personal` (somebody's own device) — plan step 2b, hub#357.
pub mod device_mode;
/// The devices of a business and the gesture that cuts a lost one off — hub#455.
pub mod devices;
/// Step-up approvals: the manager's PIN, verified in the runtime, buys ONE action — hub#361.
pub mod elevation;
pub mod embed;
pub mod entitlement;
pub mod whatsapp_quota;
pub mod error_sink;
/// **Server-side agent runner** (ADR-0283 K5, hub#665): the tool loop of an `ai` step, in Rust and
/// outside the runtime's global lock. It lives here and not in the runtime because it needs
/// `cloud-client` — the runtime has no network by design.
pub mod agent_runner;
pub mod event_stream;
pub mod export_import;
/// ERPlora's DELEGATED fiscal certificate, fetched from the control plane (ADR-0202 §2 — hub#317).
pub mod fiscal_certificate;
/// The I/O half of a flow step (hub#662): the call itself, outside the runtime's global lock.
pub mod flow_io;
pub mod flows_api;
pub mod hub_users;
pub mod login_throttle;
pub mod public_door;
pub mod readiness;
pub mod reset;
pub mod inbound_poll;
pub mod ingest;
pub mod install;
pub mod install_guard;
pub mod logging;
pub mod media;
pub mod members;
pub mod module_storage;
pub mod notify_transport;
pub mod openapi;
/// Operable dead-letter of the event outbox: list · retry · discard — hub#660 (ADR-0127 phase 2).
pub mod outbox_admin;
pub mod print;
pub mod print_ws;
pub mod profile;
/// El otorgamiento de representación firmado (hub#817): se captura aquí y lo custodia el SaaS.
pub mod representation_grant;
pub mod router;
pub mod settings;
pub mod state;
pub mod shutdown;
pub mod system;
pub mod system_metrics;
pub mod usage_series;
pub mod tenant;
pub mod version;

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
    /// —que es SIEMPRE, en cloud y en la app instalada, porque la ventana de Tauri navega a este
    /// mismo servidor— la CSP de `tauri.conf` no alcanza al documento y esta es la única que hay.
    ///
    /// `String`, no `Option<String>`: «hub sin política» dejó de ser un estado representable
    /// (hub#708). Lo era, y por eso la flota entera sirvió la app a pelo durante semanas. Se
    /// rellena con [`resolve_csp`], que solo deja pasar un valor que el navegador pueda recibir.
    pub csp: String,
}

/// La parte de la política que NO depende del despliegue (hub#708). Es el gemelo de la CSP del
/// shell de Tauri (`apps/tauri/src-tauri/tauri.conf.json`), y las diferencias están enumeradas una
/// a una en `crates/server/tests/cloud_csp.rs` — un test falla si aparece una que nadie explicó.
///
/// Cada ensanche respecto del shell tiene un motivo concreto:
/// - `img-src blob:` / `media-src blob:` — el visor de `/files` y el avatar pintan bytes que YA
///   trajo el runtime, vía `URL.createObjectURL`; el navegador nunca toca el almacenamiento
///   (ADR-0047). Sin `media-src` explícito la etiqueta `<video>` cae en `default-src` y no pinta.
/// - `script-src 'self'` y `worker-src 'self'` explícitos aunque `default-src` ya los cubra: son
///   las dos directivas que deciden si un módulo puede ejecutar código ajeno, y así ensanchar
///   `default-src` mañana no las ensancha de rebote.
///
/// Y lo que NO lleva, también a propósito: **`form-action`**. No hereda de `default-src`, así que
/// su ausencia es una decisión: fijarla rompe el login con Google, cuya cadena de redirección sale
/// del hub, pasa por el SaaS y vuelve — sin error que el usuario pueda accionar.
const CSP_BASE: &str = "default-src 'self'; \
                        script-src 'self'; \
                        worker-src 'self'; \
                        style-src 'self' 'unsafe-inline'; \
                        img-src 'self' data: blob:; \
                        media-src 'self' blob:; \
                        frame-src 'none'; \
                        object-src 'none'; \
                        base-uri 'self'";

/// El `connect-src` mínimo: el propio origen **y el canal IPC de Tauri**.
///
/// Lo segundo no es cosmético y es fácil de pasar por alto: la ventana de la app instalada NO carga
/// un `dist` empaquetado, navega a `https://<hub>.erplora.com` (ADR-0159, `remote.urls` de
/// `capabilities/default.json`), así que el documento que gobierna esta política ES el de la app —
/// y su `invoke` viaja por `fetch("ipc://localhost/<cmd>")` (`tauri/src/ipc/protocol.rs`), que en
/// Windows y Android reescribe a `http://ipc.localhost/<cmd>`. Sin estas dos fuentes, `connect-src`
/// tumba TODO el hardware de la app instalada —imprimir, cajón, descubrimiento— en silencio.
///
/// En un navegador a secas son inertes: `ipc:` no es un esquema navegable y `ipc.localhost` no
/// resuelve. Cuestan cero fuera de la app.
const CSP_CONNECT_BASE: &str = "connect-src 'self' ipc: http://ipc.localhost";

/// La política que sirve este hub. Lo único que no puede ser constante es el **origen del Cloud**:
/// el front habla directo con él para el login, el refresh de JWT y las facturas
/// (`apps/web/src/lib/cloud.ts`), así que con `connect-src 'self'` a secas el hub se queda sin
/// login cloud. Sale de `HUB_CLOUD_API_URL` —lo que ESTE hub tiene configurado— y no de una
/// constante `https://erplora.com`, que es justo el pendiente (c) de ADR-0050: un self-host o un
/// staging con otro `VITE_CLOUD_API_URL` quedaba bloqueado por su propia CSP.
///
/// Sin Cloud configurado (dev, binario suelto) la política se queda en `'self'`: nada que permitir.
pub fn default_csp(cloud_base_url: &str) -> String {
    match cloud_origin(cloud_base_url) {
        Some(origin) => format!("{CSP_BASE}; {CSP_CONNECT_BASE} {origin}"),
        None => format!("{CSP_BASE}; {CSP_CONNECT_BASE}"),
    }
}

/// `https://erplora.com/algo/` → `https://erplora.com`. Una fuente de CSP es un ORIGEN: con la
/// ruta pegada el navegador la trata como path-matching y deja de casar con `/api/v1/...`.
/// Devuelve `None` si el valor no es una URL absoluta con host (incluye el string vacío).
fn cloud_origin(cloud_base_url: &str) -> Option<String> {
    let raw = cloud_base_url.trim();
    let (scheme, rest) = raw.split_once("://")?;
    if !scheme.eq_ignore_ascii_case("http") && !scheme.eq_ignore_ascii_case("https") {
        return None;
    }
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    // Un host con espacios, comillas o `;` rompería el header o inyectaría otra directiva.
    if authority.is_empty()
        || !authority
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | ':' | '[' | ']'))
    {
        return None;
    }
    Some(format!("{}://{}", scheme.to_ascii_lowercase(), authority))
}

/// Resuelve la CSP que va a servir el hub a partir del valor crudo de `HUB_CSP` (hub#708).
///
/// `HUB_CSP` **sustituye** la política; no la quita. Vacío, en blanco o imposible de meter en un
/// header (un salto de línea, un byte no-ASCII) cae a [`default_csp`] en vez de dejar el hub
/// desnudo — que es exactamente cómo se sirvió la flota entera hasta ahora: el aprovisionador
/// escribía `HUB_CSP_ENFORCE` y el runtime leía `HUB_CSP`, así que la rama "no hay valor" era la
/// única que corría y no emitía nada.
pub fn resolve_csp(raw: Option<String>, cloud_base_url: &str) -> String {
    raw.map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty() && HeaderValue::from_str(value).is_ok())
        .unwrap_or_else(|| default_csp(cloud_base_url))
}

impl ServeConfig {
    /// Igual que el binario: `HUB_DATABASE_URL` (obligatorio) / `HUB_BIND` / `HUB_MODULES_DIR` +
    /// [`HubConfig::from_env`].
    pub fn from_env() -> Self {
        let hub = HubConfig::from_env();
        // Antes del literal: `hub` se mueve dentro y la política necesita su `cloud_base_url`.
        let csp = resolve_csp(std::env::var("HUB_CSP").ok(), &hub.cloud_base_url);
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
            // Nunca `None`: `HUB_CSP` solo puede SUSTITUIR la política (ver `resolve_csp`).
            csp,
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

    // Índice vectorial del asistente (§9.2b routing + §9.6 ingestión) — Postgres + pgvector
    // (hub#204 / pm#29). Con los 24 módulos instalados el catálogo de tools que viaja en CADA
    // turno son ~58k tokens; el router lo recorta a los módulos relevantes, y para eso necesita
    // este índice.
    //
    // **Nunca aborta el arranque.** Si pgvector no está disponible en esta BD (la imagen no lo
    // trae, o el rol del hub no puede crear la extensión — ADR-0201 da a cada hub su BD y su rol),
    // se queda en `None` y el asistente degrada a ofrecer todos los tools (§9.5), que es
    // exactamente lo que hacía antes. Más caro de prompt, nunca roto. Lo que el asistente SABE del
    // hub no depende de esto: el mapa de módulos va en el system prompt
    // (`assistant::build_instructions`). Los embeddings siguen saliendo por el Cloud (§9.3).
    let vector_store: Option<state::SharedVectorStore> = match erplora_db::PgAdapter::connect(&dsn)
        .await
    {
        Ok(vdb) => {
            let store = erplora_vector::PgVectorStore::new(
                std::sync::Arc::new(vdb),
                erplora_vector::DEFAULT_DIMS,
            );
            match erplora_vector::VectorStore::ensure_schema(&store).await {
                Ok(()) => {
                    eprintln!("asistente: índice vectorial pgvector listo (router §9.2b activo)");
                    Some(std::sync::Arc::new(store) as state::SharedVectorStore)
                }
                Err(e) => {
                    eprintln!(
                        "asistente: sin índice vectorial ({e}); se ofrecen TODOS los tools (§9.5). \
                         Instala pgvector en esta BD para abaratar el prompt."
                    );
                    None
                }
            }
        }
        Err(e) => {
            eprintln!("asistente: sin índice vectorial (pool: {e}); se ofrecen todos los tools (§9.5)");
            None
        }
    };

    // Celda del token de máquina: externa (compartida con el shell Tauri para hot-reload) o propia.
    let mut state = AppState::with_config_cells(runtime, cfg.hub, machine_token_cell, hub_id_cell);
    if let Some(vs) = vector_store {
        state = state.with_vector(vs);
    }
    // Tablas de sistema del runtime (outbox + scheduler) — para el caso de hub vacío sin módulos.
    state.runtime.lock().await.ensure_system_tables().await?;

    // Marca de actividad de usuario (hub#670): se ADOPTA la que dejó el proceso anterior, y a
    // partir de aquí se escribe sola cada `HUB_ACTIVITY_PERSIST_SECS`.
    //
    // Va justo después de las migraciones (su tabla nace en la v39) y ANTES de que arranquen el
    // latido y el router: el latido manda `pending()` en su PRIMER tick, y sin la marca adoptada
    // ese tick diría «aquí no ha entrado nadie» de un hub que sí se usa. Perderla no es cosmético
    // — es el reloj con el que el Cloud apaga (60d) y BORRA (120d) un hub free, y borrar no se
    // deshace. Ambas llamadas son best-effort: un hub cuya marca no se pueda leer o escribir tiene
    // que arrancar igual, con el reloj empezado de nuevo, nunca quedarse sin arrancar.
    activity::restore_from_db(&state).await;
    activity::spawn_persistence(&state);

    // **¿Nos han cambiado el binario?** (hub#564, ADR-0269 §3.5). Nadie se lo dice al hub: la imagen
    // se re-resuelve FUERA del contenedor, la task se sustituye, y el binario nuevo arranca
    // reportando otro número. Compararlo con el último que anotamos es todo el mecanismo — y es
    // también lo que hace VISIBLE un rollback automático, porque Swarm revirtiendo un despliegue
    // malo, visto desde aquí dentro, es exactamente una versión que baja.
    //
    // Va justo detrás de `ensure_system_tables` porque necesita su tabla (v40) y nada más: cuanto
    // más tarde se anote, más ventana hay de que el arranque se caiga antes y el salto se pierda.
    // Best-effort: no poder escribir el historial nunca impide abrir la tienda.
    {
        let rt = state.runtime.lock().await;
        match erplora_runtime::update_history::note_core_version(
            rt.db(),
            &state.hub_id(),
            version::HUB_VERSION,
        )
        .await
        {
            Ok(Some(entry)) => eprintln!(
                "✓ versión del core: {} → {} ({})",
                entry.from_version, entry.to_version, entry.outcome
            ),
            Ok(None) => {}
            Err(e) => eprintln!("✗ no se pudo anotar la versión del core (hub#564): {e}"),
        }
    }

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
                    // Pins de soporte de este hub (hub#516): `module_id → pinned_version`.
                    let pins: std::collections::HashMap<String, String> = {
                        let rt = state.runtime.lock().await;
                        erplora_runtime::installer::installed_with_pin(rt.db(), &state.hub_id())
                            .await
                            .unwrap_or_default()
                            .into_iter()
                            .filter_map(|(id, _, pin)| pin.map(|p| (id, p)))
                            .collect()
                    };

                    for (id, version) in missing {
                        // 🔄 Los módulos se actualizan SOLOS (hub#516): se resuelve la ÚLTIMA versión
                        // instalable, no la registrada. Es lo único que faltaba — la re-descarga del
                        // arranque ya existía porque el `module_cache` es `/tmp`.
                        //
                        // Seguro porque hub#542 valida el SQL de la migración y traduce sus `DROP` a
                        // rename, hub#517 garantiza que no hay nada que deshacer al revertir, y
                        // hub#538 deja `/readyz` en DOWN si el módulo no carga — así Swarm revierte
                        // el despliegue en vez de dejar el hub «sano» con el TPV roto.
                        let target = resolve_module_target(&state, &machine, &id, &version, pins.get(&id).map(String::as_str)).await;

                        let mut rt = state.runtime.lock().await;
                        // El nombre que lee el dueño, capturado ANTES de tocar nada (hub#564): si el
                        // intento pierde el módulo, el registry ya no lo tiene y la entrada del
                        // historial se quedaría con el id — que es justo lo que la regla 3 prohíbe.
                        let module_name = rt
                            .registry()
                            .installed
                            .iter()
                            .find(|m| m.id == id)
                            .map(|m| m.name.clone())
                            .unwrap_or_else(|| id.clone());
                        // Progreso no-op: en el arranque aún no hay clientes WS a los que retransmitir.
                        let attempt = match install::install_from_cloud(&state.http, &cloud, &cache_root, &machine, &mut rt, &id, target.version(), &|_, _| {}, &state.config.signature_policy()).await {
                            Ok(_) if target.is_update() => {
                                eprintln!("✓ módulo actualizado: {id} {version} → {}", target.version());
                                Some(erplora_runtime::module_update::Outcome::Updated { from: version.clone(), to: target.version().to_string() })
                            }
                            Ok(_) => { eprintln!("✓ módulo re-descargado: {id}@{}", target.version()); None }
                            Err(e) if target.is_update() => {
                                // ⚠️ Una actualización que falla NO puede dejar al hub SIN el módulo:
                                // un hub con la versión de ayer funciona, uno sin el módulo no. Se
                                // cae a la que tenía registrada.
                                eprintln!("✗ actualización de {id} a {}: {e} — vuelvo a {version}", target.version());
                                let fallback = install::install_from_cloud(&state.http, &cloud, &cache_root, &machine, &mut rt, &id, &version, &|_, _| {}, &state.config.signature_policy()).await;
                                match &fallback {
                                    Ok(_) => eprintln!("✓ {id} sigue en {version}"),
                                    Err(e) => eprintln!("✗ {id}@{version} tampoco: {e}"),
                                }
                                // Y no puede ser un silencio (update-model §3.1.1): si actualizamos
                                // solos, una actualización que se cae —y más aún un hub que arranca
                                // SIN el módulo— tiene que llegar a alguien, no morir en un log del
                                // contenedor. Best-effort: sin sink (hub sin enrolar) se descarta.
                                report_failed_module_update(&id, &version, target.version(), &e.to_string(), fallback.is_ok());
                                Some(match &fallback {
                                    Ok(_) => erplora_runtime::module_update::Outcome::RolledBack { stayed_on: version.clone(), error: e.to_string() },
                                    Err(fe) => erplora_runtime::module_update::Outcome::Lost { module: id.clone(), error: format!("{e}; la vuelta atrás tampoco: {fe}") },
                                })
                            }
                            Err(e) => { eprintln!("✗ re-descarga de {id}@{version}: {e}"); None }
                        };

                        // Y tampoco puede ser un silencio PARA EL DUEÑO (hub#564): el `error_sink`
                        // de arriba nos avisa a NOSOTROS, pero quien se encuentra la caja distinta
                        // por la mañana es quien abre la tienda. La misma decisión que usa el botón
                        // —`from_module_outcome`— para que las dos puertas no cuenten lo mismo de
                        // dos maneras. Best-effort: el historial nunca impide arrancar.
                        if let Some(attempt) = attempt {
                            if let Some(change) = erplora_runtime::update_history::from_module_outcome(&id, &module_name, target.version(), &attempt) {
                                if let Err(e) = erplora_runtime::update_history::record(rt.db(), &state.hub_id(), change).await {
                                    eprintln!("✗ no se pudo anotar el historial de {id} (hub#564): {e}");
                                }
                            }
                        }
                    }
                }
                None => eprintln!(
                    "⚠ {} módulo(s) instalados sin caché y hub sin enrolar (sin token de máquina): no se re-descargan",
                    missing.len()
                ),
            }

            // 🛟 **Y si el marketplace no dio, la copia PROPIA del hub** (hub#571). Todo lo de
            // arriba depende del SaaS: un reinicio con el Cloud caído, un DNS torcido o el router
            // del cliente apagado dejaban al hub arrancando SIN un solo módulo — `/readyz` en DOWN,
            // Swarm recreando el contenedor en bucle y el bar sin TPV. Este es el único camino que
            // no pasa por la red: los bytes se guardaron en la base del propio hub al instalar y se
            // vuelven a verificar aquí igual que una descarga (SHA256 + firma según la política).
            //
            // Va DESPUÉS y no antes a propósito: la vía del marketplace es también la de la
            // actualización automática (hub#516/ADR-0269), y adelantarla convertiría cada arranque
            // en «quédate donde estás». Primero se intenta llegar a lo que toca; esto es la red que
            // impide caer por debajo de lo que ya se tenía.
            let still_missing = state
                .runtime
                .lock()
                .await
                .installed_but_unregistered()
                .await
                .unwrap_or_default();
            if !still_missing.is_empty() {
                eprintln!(
                    "marketplace inalcanzable para {} módulo(s): reponiendo de la copia local…",
                    still_missing.len()
                );
                let cache_root = state.config.module_cache.clone();
                let policy = state.config.signature_policy();
                let orphans = {
                    let mut rt = state.runtime.lock().await;
                    install::restore_from_local_packages(
                        &cache_root,
                        &mut rt,
                        &still_missing,
                        &policy,
                    )
                    .await;
                    rt.installed_but_unregistered().await.unwrap_or_default()
                };
                // Ni copia, ni marketplace, ni tarea vieja a la que volver: aquí la regla «nunca con
                // menos» no se puede cumplir, porque no hay ninguna alternativa que la cumpla. Lo
                // que NO puede pasar es que sea un silencio — un hub que arranca incompleto tiene
                // que llegar a alguien, no morir en el log de un contenedor.
                if !orphans.is_empty() {
                    report_incomplete_boot(&orphans);
                }
            }
        }
    }

    // Backfill del índice vectorial (§9.6): la ingesta normal corre en el hook de INSTALL, que ya
    // pasó para todo hub existente — sin esto, su índice quedaría vacío para siempre y el router
    // (§9.2b) nunca se activaría. Solo embebe la DIFERENCIA (módulos activos aún no indexados):
    // los embeddings son llamadas metered al Cloud (§9.3), así que reiniciar no cuesta nada.
    // En tarea de fondo: el arranque no espera a la red, y un fallo aquí no toca el arranque.
    if let (Some(store), Some(machine)) = (state.vector.clone(), auth::machine_auth(&state)) {
        let runtime = state.runtime.clone();
        let http = state.http.clone();
        let cloud = state.config.cloud_base_url.clone();
        let hub_id = state.hub_id();
        tokio::spawn(async move {
            let embedder = embed::CloudEmbedder::new(http, &cloud, machine);
            let rt = runtime.lock().await;
            let (modules, chunks) =
                embed::backfill_index(&embedder, store.as_ref(), rt.registry(), &hub_id).await;
            if modules > 0 {
                tracing::info!(modules, chunks, "índice vectorial backfilleado (§9.6)");
            }
        });
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

    // **El PAÍS que el SaaS acuñó al aprovisionar** (`HUB_COUNTRY`, ADR-0207 — hub#69). Va AQUÍ,
    // después del seed SQL (que también puede escribir `country_code`, y quien lo escribe manda
    // sobre un default) y ANTES del perfil fiscal, que deriva el régimen del país: sembrarlo
    // después dejaría el perfil calculado sobre el país equivocado hasta el siguiente arranque.
    //
    // Se lee del entorno aquí y no en `HubConfig` por lo mismo que `HUB_SEED_SQL` o
    // `HUB_OWNER_EMAIL`: es una entrada de ARRANQUE que se consume una vez y no vuelve a hacer
    // falta — a partir de este punto la autoridad es `hub_settings.country_code`, que es lo único
    // que leen el motor de impuestos, la checklist y el filtro del marketplace.
    //
    // NUNCA pisa una respuesta que el hub ya tenga: el env es la SUGERENCIA del alta («corregible»,
    // ADR-0207), y quien la corrigió en Ajustes manda sobre ella.
    match state
        .runtime
        .lock()
        .await
        .ensure_provisioned_country(&std::env::var("HUB_COUNTRY").unwrap_or_default())
        .await
    {
        Ok(true) => eprintln!("país: `country_code` sembrado desde HUB_COUNTRY (ADR-0207)"),
        Ok(false) => {}
        // No aborta el arranque: un hub que no abre es peor que un hub con el país por defecto.
        Err(e) => eprintln!("✗ país: no se pudo sembrar el país del aprovisionamiento: {e}"),
    }

    // **La DEMO arranca con su identidad fiscal ya puesta** (hub#684). Va AQUÍ, después del seed
    // (que escribe el `country_code`) y ANTES del perfil fiscal, que es quien deriva `READY` de
    // «identidad ∧ certificado»: sembrarla después dejaría el perfil calculado sobre un hub sin
    // identidad hasta el siguiente arranque.
    //
    // Es el CORE escribiendo el marcador de posición de la demo, no una puerta: los tres cierres de
    // ADR-0197 §4 siguen intactos — el visitante no puede CAMBIAR el NIF, ni subir un certificado
    // `own`, ni salir de `testing`. Lo que se arregla es que la checklist le pedía justo el dato
    // que el producto le prohibía escribir, y que su venta se cobraba sin llegar a emitir factura
    // (`invoice.create_from_sale` estampa `:business_tax_id` y el gate de ADR-0203 la rechazaba).
    match state.runtime.lock().await.ensure_demo_fiscal_identity().await {
        Ok(true) => eprintln!("demo: identidad fiscal de la demo sembrada (hub#684)"),
        Ok(false) => {}
        // No aborta el arranque: un hub que no abre es peor que una demo con la checklist a medias.
        Err(e) => eprintln!("✗ demo: no se pudo sembrar la identidad fiscal de la demo: {e}"),
    }

    // **Perfil fiscal** (ADR-0273 D2/D4, hub#550): qué debe este hub, resuelto contra lo que hay
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
            Err(e) => eprintln!("✗ fiscal: no se pudo resolver el perfil del hub (ADR-0273): {e}"),
        }
    }

    // Transporte de `host.notify` (ADR-0012 + ADR-0283 §5 K4, hub#663): el cliente REAL. Email y
    // WhatsApp salen por el **proxy del SaaS** (`/api/v1/hub/device/notify/{email,whatsapp}/`) con
    // la credencial de máquina; el hub nunca guarda credenciales de Meta/SES (patrón del LLM).
    //
    // El mock sigue disponible, pero **hay que pedirlo por su nombre** (`HUB_NOTIFY_TRANSPORT=mock`)
    // y no se cae en él por accidente: un mock devuelve `Sent` sin enviar nada, y el outbox marca
    // entonces el evento como entregado — un recordatorio que nunca salió y del que nadie se entera.
    // Un hub sin enrolar falla RUIDOSAMENTE (reintento → dead-letter), que sí se ve.
    state
        .runtime
        .lock()
        .await
        .set_notify_transport(notify_transport::build(
            state.http.clone(),
            &state.config.cloud_base_url,
            state.hub_id.clone(),
            state.machine_token.clone(),
            std::env::var(notify_transport::TRANSPORT_ENV).ok(),
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
                // I/O que el tick de flujos deja preparada (hub#662). Se recoge DENTRO del bloque
                // con lock y se despacha FUERA: el `dispatch` no debe tocar el lock que acabamos de
                // soltar, y el bucle de 1 s no puede esperar a una llamada de 30 s.
                let mut pending_io = Vec::new();
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
                    // Kernel de automatización (ADR-0283, hub#661): dispara los triggers de reloj,
                    // despierta los `delay` vencidos y avanza los runs reclamados. Comparte este
                    // lock con los dos de arriba, y por eso su trabajo está ACOTADO por tick
                    // (`MAX_RUNS_PER_TICK` × `MAX_STEPS_PER_TICK`, todos sin I/O): un step `http` o
                    // un turno de IA aquí dentro congelaría los commands de todo el hub, así que
                    // esos van por claim → I/O → complete FUERA del lock (hub#662/#665).
                    match rt.process_flows().await {
                        Ok(report) => pending_io = report.pending_io,
                        Err(e) => eprintln!("flows: {e}"),
                    }
                }
                // Ya sin el lock: cada llamada se va a su propia tarea y vuelve por
                // `complete_flow_io` cuando termine (crates/server/src/flow_io.rs).
                if !pending_io.is_empty() {
                    flow_io::dispatch(&scheduler_state, pending_io);
                }
                tokio::time::sleep(std::time::Duration::from_millis(1000)).await;
            }
        });
    }

    // **Retención del historial** (hub#699, `erplora_runtime::retention`): el outbox y los runs de
    // flujos eran append-only — ninguna fila se borraba nunca — y sus columnas anchas (`input`,
    // `output`, `payload`, todas TEXT) crecían de por vida en una BD que se paga por GB. A los 90
    // días se poda lo TERMINAL, y solo eso: un `pending` (aún por entregar) y un `dead` (esperando
    // decisión humana) sobreviven a cualquier edad, porque son la durabilidad, no el historial.
    //
    // Tick PROPIO y horario, no el bucle de 1s: el barrido no es urgente y el bucle de 1s sostiene
    // el lock del runtime para el relay de eventos. El lock se coge **por pasada**, no para todo el
    // barrido, así que entre dos DELETE acotados el relay entra sin esperar. Que sea horario y no
    // diario es lo que deja a un hub con un año de atraso ponerse al día en unas horas en vez de en
    // meses, sin que ninguna pasada deje de ser pequeña.
    {
        let st = state.clone();
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(std::time::Duration::from_secs(3600));
            loop {
                tick.tick().await;
                let hub_id = st.hub_id();

                // **Antes de podar, cerrar lo que caducó** (hub#972). El TTL de 72 h de una
                // aprobación solo se miraba al intentar decidirla, así que una propuesta que nadie
                // contestó no se podía ni aprobar ni rechazar —las dos vías pasan por la misma
                // puerta— y su run se quedaba en `waiting_approval` PARA SIEMPRE: exento de la poda
                // de abajo, con el `payload` verbatim dentro (el nombre y el teléfono de una
                // clienta). El barrido lo pasa a `expired`, aplica la política que dice la FILA
                // (`on_expire`, defecto `reject`) y deja el run en estado terminal — que es lo que
                // lo mete en la poda de 90 días, en esta misma vuelta.
                //
                // Pasadas acotadas con el lock cogido **por pasada**, igual que la poda de abajo:
                // cerrar una propuesta no es un DELETE, es terminar (o reanudar) un run, y una
                // bandeja con un año de abandono no puede quedarse el lock un minuto entero.
                {
                    let mut swept = erplora_runtime::flows::ExpirySweepReport::default();
                    for _ in 0..erplora_runtime::retention::MAX_PASSES {
                        let runtime = st.runtime.lock().await;
                        let pass = runtime.sweep_expired_flow_approvals().await;
                        drop(runtime);
                        match pass {
                            Ok(p) if p.is_empty() => break,
                            Ok(p) => swept.merge(p),
                            Err(e) => {
                                tracing::warn!(error = %e, "flows: el barrido de aprobaciones caducadas falló");
                                break;
                            }
                        }
                    }
                    if !swept.is_empty() {
                        tracing::info!(
                            expired = swept.expired,
                            runs_stopped = swept.runs_stopped,
                            runs_resumed = swept.runs_resumed,
                            stranded = swept.stranded,
                            "flows: propuestas caducadas cerradas"
                        );
                    }
                }

                // Dos relojes, uno por tabla (hub#903): el historial a 90 días y el RECIBO de una
                // aprobación humana a cuatro años. Se calculan juntos al principio de la vuelta
                // para que todas las pasadas de este tick midan contra el mismo instante.
                let cutoffs = erplora_runtime::retention::Cutoffs::now();
                let mut total = erplora_runtime::retention::PruneReport::default();
                for _ in 0..erplora_runtime::retention::MAX_PASSES {
                    let runtime = st.runtime.lock().await;
                    let pass =
                        erplora_runtime::retention::prune_once(runtime.db(), &hub_id, &cutoffs)
                            .await;
                    drop(runtime);
                    match pass {
                        Ok(p) if p.is_empty() => break,
                        Ok(p) => total.merge(p),
                        Err(e) => {
                            tracing::warn!(error = %e, "retention: la poda de historial falló");
                            break;
                        }
                    }
                }
                // Solo si borró algo: una poda silenciosa es indistinguible de una pérdida de datos
                // el día que alguien busca un evento viejo y no está, pero "borradas 0 filas" cada
                // hora es ruido que enseña a no leer el log.
                if !total.is_empty() {
                    tracing::info!(
                        events = total.events,
                        delivery_markers = total.delivery_markers,
                        runs = total.runs,
                        run_steps = total.run_steps,
                        approvals = total.approvals,
                        receipts = total.receipts,
                        retention_days = erplora_runtime::retention::RETENTION_DAYS,
                        approval_audit_days = erplora_runtime::retention::APPROVAL_AUDIT_DAYS,
                        "retention: historial terminal podado"
                    );
                }
            }
        });
    }

    // **WhatsApp entrante** (ADR-0283 K1c, `architecture/hub/flows.md` §6): el hub POLLEA su
    // bandeja en el SaaS y convierte cada mensaje en el evento core
    // `hub.whatsapp.message_received`. El SaaS no puede llamar a un hub (ADR-0213) y los hubs
    // viven tras NAT, así que la única dirección posible es esta.
    //
    // Tick PROPIO y no el bucle de 1s de arriba, por dos razones: su periodo es otro (5s) y, sobre
    // todo, hace **I/O de red** — meterlo en el bucle del relay tendría el lock del runtime
    // cogido durante un round-trip HTTP y pararía la entrega de eventos de todo el hub.
    // `poll_once` coge el lock solo para el gate y para las escrituras (ver su doc).
    //
    // El propio tick se auto-gatea: sin el módulo `whatsapp_inbox` activo y con entitlement, no
    // sale ni una petición (720 GET/hora por hub que sí lo usa).
    {
        let poll_state = state.clone();
        let poller = inbound_poll::InboundPoller::new(
            state.http.clone(),
            &state.config.cloud_base_url,
            state.hub_id.clone(),
            state.machine_token.clone(),
        );
        let secs = inbound_poll::interval_secs(
            std::env::var(inbound_poll::INTERVAL_ENV).ok().as_deref(),
        );
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(std::time::Duration::from_secs(secs));
            tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
            loop {
                tick.tick().await;
                match poller
                    .poll_once(&poll_state.runtime, &poll_state.entitlement)
                    .await
                {
                    Ok(report) if report.ingested > 0 => tracing::info!(
                        ingested = report.ingested,
                        acked = report.acked,
                        "whatsapp entrante: mensajes ingeridos como evento core"
                    ),
                    Ok(_) => {}
                    // Un fallo de red aquí NO es fatal: los mensajes siguen pendientes en el SaaS
                    // y el siguiente tick los recoge (nada se pierde por no haber podido leer).
                    Err(e) => tracing::warn!("whatsapp entrante: {e}"),
                }
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
    // Un solo presupuesto por proceso, y vive en `AppState` porque desde hub#817 hay un CUARTO
    // disparador (firmar el Anexo I) que sale de una petición, no de estos bucles.
    let certificate_budget = state.certificate_budget.clone();
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
                // hub#975: la telemetría de recursos viaja en el MISMO latido, del sampler único
                // de `system_metrics` (fuera del lock de arriba: el muestreo de CPU duerme 100 ms).
                // Best-effort: fuera de contenedor los campos viajan ausentes, nunca un 0 falso.
                daily_usage::sample_resource_metrics()
                    .await
                    .apply_to(&mut usage);
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
                // La cuota del canal de WhatsApp se refleja en el medidor del módulo (hub#1089).
                // Se lee EN VIVO de `whatsapp/plan/` con esta MISMA credencial de máquina, no de
                // un claim del token: ese endpoint devuelve tier + consumo, y el consumo es un
                // contador que se mueve con cada mensaje. Si el Cloud no contesta no se escribe
                // nada — el medidor conserva lo que ya medía, porque en este canal `0` significa
                // «sin tope» y un fallo de red no es un plan. Un hub sin el módulo ni pregunta.
                match whatsapp_quota::sync_once(
                    &st.runtime,
                    &st.http,
                    &st.config.cloud_base_url,
                    &auth,
                )
                .await
                {
                    whatsapp_quota::QuotaSync::Written(limit) => {
                        tracing::debug!(monthly_limit = limit, "cuota de WhatsApp al día")
                    }
                    // Los demás casos ya se han contado donde tocaba (o son el no-op esperado
                    // en la flota que no compró el canal): aquí no se repite el ruido.
                    other => tracing::trace!(?other, "sincronización de cuota de WhatsApp"),
                }
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

    // ⛔ Aquí iba el import del blueprint DECLARADO por el SaaS (ADR-0212 / hub#406), y ya no va:
    // **un hub nace VACÍO** (ADR-0293). Era el único paso del arranque que instalaba módulos por su
    // cuenta —`ImportSelection.modules` = todos los del manifest de la plantilla—, así que un hub
    // recién provisionado amanecía con el vertical entero puesto (13 apps con el blueprint
    // `restaurante` de la demo).
    //
    // ERPlora es un **ERP genérico, no un POS**: el vertical lo elige el usuario. Un hub nuevo trae
    // su configuración y nada más, y la primera pantalla le ofrece los blueprints para que importe
    // el suyo. Sembrárselo al nacer decide por él justo lo que el producto le deja elegir.
    //
    // Las dos claves de env (`HUB_BOOTSTRAP_BLUEPRINT`, `HUB_BOOTSTRAP_BLUEPRINT_LOCALE`) siguen
    // llegando en el despliegue de las demos y **se ignoran a propósito**; `HubConfig::from_env` ya
    // no las lee. Lo vigila `tests/newborn_hub_is_empty.rs`, que arranca el hub de verdad con ellas
    // puestas y comprueba que no se le pide un solo blueprint al Cloud.

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
    // El router consume el `state`; el aviso de arranque de más abajo necesita el suyo, y el
    // apagado el suyo (hub#670: el último flush de la marca de actividad).
    let announce_state = state.clone();
    let shutdown_state = state.clone();
    // hub#926: el precalentado de handlers también necesita el suyo (el router consume `state`).
    let warm_state = state.clone();
    // CSP (ADR-0050, hub#708): con el doc servido por Axum —que es SIEMPRE, también en la app
    // instalada, cuya ventana navega aquí— la de `tauri.conf` no alcanza al documento. Sin rama:
    // la política se emite siempre, y `cfg.csp` es `String` para que "sin CSP" ni se pueda escribir.
    let router = build_serving_router(state, cfg.web_dir.as_deref(), &cfg.csp);

    let listener = tokio::net::TcpListener::bind(&cfg.bind).await?;
    eprintln!("erplora-server escuchando en http://{}", cfg.bind);
    tracing::info!(bind = %cfg.bind, "erplora-server arrancado");

    // «Ya atiendo» (hub#712): en cuanto el agregado de `/readyz` diga `UP`, un latido al Cloud
    // para que un hub recién desplegado pase a `active` sin esperar al sondeo del SaaS.
    //
    // 🔑 Va AQUÍ, después de bindear: el socket ya escucha, así que el aviso no puede adelantar
    // al hub que anuncia. Antes de este punto marcaríamos listo un hub que todavía no atiende, y
    // eso es peor que tardar. En su propia task y best-effort, como el import de blueprint y el
    // refetch del certificado: un plano de control inalcanzable deja un hub que FUNCIONA.
    boot_announce::spawn(&announce_state);
    // Precalentar los handlers WASM (hub#926). La caché en disco de wasmtime vive DENTRO del
    // contenedor, así que un deploy la estrena vacía: medido en producción, las dos primeras ventas
    // tras desplegar costaron 8,2 s y 5,7 s, y las siguientes 75-91 ms. Compilar hay que compilar;
    // lo que se elige aquí es hacerlo mientras nadie espera, no en el primer cobro del día.
    //
    // En su propia task y DESPUÉS de bindear, como el resto del arranque: el hub ya atiende, y si
    // el precalentado tarda —o un módulo trae bytes rotos— no retrasa ni tumba nada.
    {
        tokio::spawn(async move {
            // Se toma la caché (un `Arc` compartido con el registro) y se SUELTA el candado del
            // runtime antes de compilar: calentar no puede bloquear a quien esté cobrando.
            let (cache, modules) = {
                let rt = warm_state.runtime.lock().await;
                (
                    std::sync::Arc::clone(&rt.registry().wasm_cache),
                    rt.registry().handlers_to_warm_up(),
                )
            };
            if modules.is_empty() {
                return;
            }
            let total = modules.len();
            // `spawn_blocking`: compilar es trabajo de CPU y no debe ocupar un worker async.
            match tokio::task::spawn_blocking(move || {
                erplora_runtime::wasm_cache::warm_up(
                    &cache,
                    &modules,
                    erplora_runtime::wasm_cache::Limits::from_env(),
                )
            })
            .await
            {
                Ok(warmed) => eprintln!("wasm: {warmed}/{total} handler(s) precalentados"),
                Err(e) => eprintln!("wasm: precalentado abortado: {e}"),
            }
        });
    }

    // Apagado limpio (ECS/Tauri): Ctrl-C o SIGTERM → deja de aceptar conexiones y drena las en
    // vuelo antes de salir, en vez de cortar a mitad (importante para ECS al desescalar/desplegar).
    axum::serve(listener, router)
        .with_graceful_shutdown(shutdown_signal(shutdown_state))
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
        version::display(),
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
async fn shutdown_signal(state: AppState) {
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
    // 🔑 Seguir ACEPTANDO antes de cerrar (hub#646). `with_graceful_shutdown` empieza a apagar en
    // cuanto este future resuelve, así que retrasarlo es lo que mantiene el listener abierto —
    // justo el tiempo que Traefik tarda en dejar de mandarnos tráfico. Sin esto, cada actualización
    // devuelve 502 a quien llegue en esa ventana.
    let drain = shutdown::drain_delay();
    if !drain.is_zero() {
        eprintln!(
            "apagado: señal recibida — sigo aceptando {}s para que Traefik deje de enrutar aquí…",
            drain.as_secs()
        );
        tokio::time::sleep(drain).await;
    }
    // Último flush de la marca de actividad (hub#670) antes de cerrar. El write-behind ya la
    // escribe cada minuto, así que esto solo cierra el último minuto — pero el SIGTERM de un
    // blue/green (ADR-0269) llega en CADA actualización, y ese minuto es justo el que contiene la
    // visita de quien estaba usando el hub cuando se desplegó.
    activity::flush(&state).await;
    eprintln!("apagado: cierro el listener y dreno las conexiones en vuelo…");
}

/// Construye el router con todas las rutas montadas sobre `state`.
pub fn app(state: AppState) -> Router {
    let registration_state = state.clone();
    let activity_state = state.activity.clone();
    Router::new()
        .route("/healthz", get(healthz))
        // Un hub no se indexa (ver `with_noindex`). Va en el router de API, ANTES del
        // fallback SPA: sin esta ruta, `/robots.txt` devolvía `index.html` con un 200, que
        // un rastreador lee como «este sitio no tiene reglas».
        .route("/robots.txt", get(robots_txt))
        // Liveness ≠ readiness (hub#538): `/healthz` dice si el proceso responde;
        // `/readyz` dice si puede ATENDER. El `HEALTHCHECK` del contenedor apunta al
        // segundo, que es el que Swarm mira para decidir si revierte.
        .route("/readyz", get(readiness::readyz))
        .route("/api/hub/context", get(hub_context))
        .route("/api/system", get(system::system_info))
        // Telemetría de recursos vs límites del plan (ADR-0154, hub#203). Sesión admin.
        .route("/api/system/metrics", get(system_metrics::system_metrics))
        // Series de uso (CPU/RAM/conexiones) para /system: proxy con caché al endpoint device
        // del SaaS (saas#1511) — el machine token vive en el runtime, nunca en el navegador.
        .route("/api/system/usage-series", get(usage_series::usage_series))
        // Qué le hemos cambiado a este hub y desde qué versión (hub#564). Solo lectura: la
        // contrapartida de actualizar sin preguntar (ADR-0269) es que se pueda SABER, no decidir.
        .route(
            "/api/system/update-history",
            get(system::update_history),
        )
        // The responsible declaration of THIS version, inside the product (art. 13.2 RRSIF —
        // hub#528). Projects the same `SistemaInformatico` block that travels in every record:
        // the producer facts the control plane serves + this binary's `Version` + the `hub_id`
        // as `NumeroInstalacion`. Never constants.
        .route(
            "/api/system/declaration",
            get(settings::get_responsible_declaration),
        )
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
        // El `PUT` **nombra** el dispositivo (hub#494) y el `DELETE` lo corta: dos gestos con
        // consecuencias distintas, por eso son dos métodos y no un campo del mismo cuerpo.
        .route(
            "/api/devices/:device_id",
            axum::routing::delete(devices::revoke_device).put(devices::rename_device),
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
            "/api/fiscal/representation-grant",
            get(representation_grant::get_representation_grant)
                .post(representation_grant::post_representation_grant)
                // 🔴 El límite por defecto de axum son 2 MB y aquí viajan hasta CUATRO documentos
                // escaneados (hub#1293): sin esto, el rechazo lo da el framework antes de llegar a
                // `validate` y la pantalla no tiene ningún código que enseñar.
                .layer(axum::extract::DefaultBodyLimit::max(
                    representation_grant::MAX_UPLOAD_BYTES,
                )),
        )
        // El modelo oficial pre-relleno, para imprimir y firmar a mano o firmar con AutoFirma
        // (hub#1293). Proxy puro hacia el SaaS, que es donde vive el texto: admin, como la subida.
        .route(
            "/api/fiscal/representation-grant/model",
            post(representation_grant::post_representation_grant_model),
        )
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
        // Reintento SOLO de lo que no entró (hub#845): deriva la selección del informe persistido,
        // vuelve a bajar la MISMA versión del catálogo y re-ejecuta. Lo ya aplicado no se duplica
        // (propiedad del motor: guardas por clave técnica hub#260 + clave natural ADR-0304).
        .route("/api/hub/import/retry", post(export_import::retry_import))
        // Reset del hub — volver a cero (ADR-0170): el espejo destructivo del export. Mismo gate
        // admin. El `plan` es dry-run (lo que la UI pinta antes de confirmar); el límite fiscal
        // (facturas remitidas a la AEAT) lo aplica el MOTOR, no esta capa.
        .route("/api/hub/reset/plan", post(reset::reset_plan))
        .route("/api/hub/reset", post(reset::reset_hub))
        // Lotes de importación (ADR-0170): listar qué trajo cada blueprint y deshacer uno sin
        // tocar lo que el usuario creó después.
        .route("/api/hub/import/batches", get(reset::import_batches))
        .route("/api/hub/import/undo", post(reset::undo_import_batch))
        // Último informe de importación persistido (hub#763): lo que el Dashboard anuncia y la
        // pestaña Datos recupera al montarse, para que la navegación no pierda el informe accionable.
        .route("/api/hub/import/report", get(reset::import_report))
        // Gestor de la carpeta `media/` (pantalla /files). Browse + raw + upload + delete + mkdir.
        .route(
            "/api/media",
            get(media::media_list).delete(media::media_delete),
        )
        .route("/api/media/raw", get(media::media_raw))
        // Where the app asks for the credential the BROWSER can attach on its own (hub#791): an
        // `<img src>` carries no header, so the read door above also takes a cookie. Read-only and
        // scoped by `Path` to that door — the writing routes below stay header-only.
        .route("/api/media/session", post(media::mint_media_session))
        .route("/api/media/upload", post(media::media_upload))
        .route("/api/media/folder", post(media::media_create_folder))
        .route("/api/media/rename", post(media::media_rename))
        .route("/api/media/move", post(media::media_move))
        .route("/api/navigation", get(navigation))
        .route("/api/modules", get(list_modules))
        .route("/api/modules/install", post(install_module))
        .route("/api/modules/request-install", post(request_install))
        // Qué versión ofrece hoy el marketplace para cada módulo instalado (hub#516). Bajo demanda:
        // lo pide la pantalla de Apps al abrirse, no un sondeo en bucle.
        .route("/api/modules/updates", get(list_module_updates))
        // Assets web de un módulo instalado (module.json + `dist/*.esm.js` + wasm/icons) servidos
        // desde la CACHÉ de descargas, resueltos por la VERSIÓN instalada. En Hub Cloud los módulos
        // se descargan en runtime al `module_cache` (NO se hornean en el `web_dir`), así que sin esta
        // ruta `/modules/**` caía al fallback SPA (`index.html`) y NINGÚN Web Component cargaba: toda
        // la UI de módulos quedaba muerta ("No se pudo cargar el módulo").
        // hub#935 — la MISMA ruta para todas las versiones era el defecto: el bundle de un módulo
        // actualizado llegaba a una url que las cachés (borde y navegador) ya tenían resuelta con
        // los bytes de la versión anterior, así que la pantalla seguía ejecutando el código viejo
        // sin ningún aviso. Con la versión en la RUTA (la query no vale: el borde la ignora para la
        // clave de caché) cada versión tiene una dirección que ninguna caché ha visto antes.
        .route("/modules/:id/v/:version/*path", get(serve_module_asset_at))
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
        // Actualizar un módulo SIN reiniciar el contenedor (hub#675/hub#516). Es la pieza que
        // faltaba: hasta ahora un fix de módulo esperaba a que saliera una imagen nueva del hub,
        // porque los módulos solo se recogen al arrancar y el rollout excluye a quien ya está en la
        // imagen. Es también el botón «Actualizar» del dueño, y con `{"version": "…"}` la palanca de
        // soporte.
        .route("/api/modules/:id/update", post(update_module))
        .route("/api/modules/:id/versions", get(list_module_versions))
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
        // Sacar del atasco UN trabajo (hub#1108): devolverlo a la cola o retirarlo. Sesión
        // **admin** (+ capability `printer` si quien llama es un módulo): leer la cola es
        // cualquier sesión —quien está al lado de la impresora—, pero tirar un tique a la basura o
        // volver a lanzarlo es el gesto del dueño, con el precedente del CRUD de estaciones.
        // Descartar NUNCA borra: la fila queda sellada con quién, cuándo y por qué.
        .route("/api/print/jobs/:job_id/retry", post(print::retry_job))
        .route("/api/print/jobs/:job_id/discard", post(print::discard_job))
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
        // ── Estaciones de impresión, como FILAS (hub#457) ────────────────────────────────────
        // «Qué impresora imprime esto» deja de ser una cadena comparada literalmente y pasa a ser
        // una FILA con id: el mercado entero (Toast, Square, Lightspeed, Odoo, Simphony…) enlaza
        // ítem→estación←impresora por referencia, nunca por un texto tecleado al imprimir. Leer
        // basta sesión (el TPV ofrece los destinos); crear/renombrar/borrar es sesión **admin**,
        // como `/api/keys`: define qué colas TIENE el negocio, no qué hace la caja de hoy.
        .route(
            "/api/print/stations",
            get(print::list_stations).post(print::create_station),
        )
        .route(
            "/api/print/stations/:id",
            axum::routing::patch(print::rename_station).delete(print::delete_station),
        )
        // El mapa `documentType → estación` (hub#987): el módulo dice QUÉ imprime, el hub DÓNDE sale.
        .route(
            "/api/print/routes",
            get(print::list_routes).put(print::set_route),
        )
        // Lo que NO se está drenando, para la campana. Sesión de usuario, no admin: quien está en
        // el mostrador es quien puede encender la caja y quien se va a quedar sin darle el tique.
        .route(
            "/api/print/undrained",
            get(print::undrained_stations),
        )
        // ── API pública por módulo (ADR-0057, public-api.md) ────────────────────────────────
        // Gestión de keys (auth = sesión admin owner/admin; NO una api key).
        .route(
            "/api/keys",
            get(api_keys::list_keys).post(api_keys::create_key),
        )
        .route("/api/keys/:id/rotate", post(api_keys::rotate_key))
        .route("/api/keys/:id", axum::routing::delete(api_keys::revoke_key))
        // ── Dead-letter del outbox, operable (hub#660 — ADR-0127 fase 2) ────────────────────
        // Misma puerta que la gestión de keys: sesión local de un humano owner/admin. Reintentar
        // re-ejecuta el command de otro módulo con la autoridad de ESE módulo (hub#686) y descartar
        // cierra un registro para siempre, así que NO se abren a una API key ni al token de máquina.
        .route("/api/hub/events/dead", get(outbox_admin::list_dead))
        .route("/api/hub/events/dead/count", get(outbox_admin::count_dead))
        .route("/api/hub/events/discarded", get(outbox_admin::list_discarded))
        .route("/api/hub/events/retry-all", post(outbox_admin::retry_all_dead))
        .route("/api/hub/events/:id/retry", post(outbox_admin::retry_dead))
        .route(
            "/api/hub/events/:id/discard",
            post(outbox_admin::discard_dead),
        )
        // Correlación (hub#666): qué disparó ESTE evento — los runs que arrancó y los eventos que
        // provocó su entrega. Misma puerta admin: el trace dibuja lo que hace el negocio entero.
        .route("/api/hub/events/:id/trace", get(outbox_admin::trace_event))
        // Catálogo de campos de un evento (hub#715): lo que el picker del editor de flujos ofrece.
        // Segmento estático de un solo tramo, así que no compite con `/:id/…`. Puerta admin **y**
        // capability `manage_flows` si quien llama es un módulo — lo que traen los eventos de un
        // negocio es la forma de ese negocio, y no la lee cualquier módulo instalado.
        .route("/api/hub/events/shape", get(outbox_admin::event_shape))
        // Catálogo de NOMBRES de evento (hub#823): la unión de lo que los módulos instalados
        // declaran y lo que el outbox vio de verdad — el desplegable «Cuando pase…» del editor de
        // flujos deja de sembrarse a mano. Solo nombres, nunca payloads; misma doble puerta que
        // `…/shape` (ADR-0312): sesión admin + `manage_flows` si quien llama nombra un módulo.
        .route("/api/hub/events", get(outbox_admin::list_events))
        // ── Kernel de automatización (ADR-0283 K7, hub#661) ────────────────────────────────
        // REST del core, NO commands `hub.*`: el core se congela y el dispatcher no es donde se
        // añade superficie nueva (§9). Misma puerta que las keys y la dead-letter: sesión local de
        // un humano owner/admin — `PUT …/grants` es la pantalla donde una persona decide qué puede
        // hacer el hub cuando no hay nadie mirando, y una credencial de integración copiable no
        // decide eso (podría concederse a sí misma todo el hub a través de un flujo).
        //
        // ⚠️ `/flows/runs/:run_id` va ANTES de `/flows/:id/...` en este `Router` solo por
        // legibilidad: matchit resuelve el segmento estático `runs` con prioridad sobre el
        // parámetro `:id`, y `tests/flows_api_test.rs` lo comprueba contra el router de verdad.
        .route(
            "/api/hub/flows",
            get(flows_api::list_flows).post(flows_api::create_flow),
        )
        .route("/api/hub/flows/runs/:run_id", get(flows_api::get_run))
        // `schema` is a static segment too (hub#716): the contract the editor builds its UI from,
        // served by the hub instead of copied into every module's bundle. It goes here for the
        // same reason as `runs` — matchit resolves the static segment ahead of `:id`, and
        // `tests/flows_schema_route.rs` checks it against the real router.
        .route("/api/hub/flows/schema", get(flows_api::get_schema))
        // `secrets` es igual: segmento estático, gana al `:id` (hub#662). El GET devuelve NOMBRES —
        // no hay endpoint que devuelva un secreto, y esa ausencia es el diseño (ADR-0283 §4).
        .route("/api/hub/flows/secrets", get(flows_api::list_secrets))
        .route(
            "/api/hub/flows/secrets/:name",
            axum::routing::put(flows_api::put_secret).delete(flows_api::delete_secret),
        )
        .route(
            "/api/hub/flows/:id",
            get(flows_api::get_flow)
                .put(flows_api::update_flow)
                .delete(flows_api::delete_flow),
        )
        .route(
            "/api/hub/flows/:id/grants",
            get(flows_api::list_grants).put(flows_api::replace_grants),
        )
        .route("/api/hub/flows/:id/run", post(flows_api::start_run))
        .route("/api/hub/flows/:id/runs", get(flows_api::list_runs))
        // ── Bandeja de aprobación (ADR-0283 D3, hub#665) ───────────────────────────────────
        // `approvals` es un segmento ESTÁTICO y matchit lo resuelve con prioridad sobre `:id`, así
        // que no se lo come `/flows/:id` aunque vaya después (igual que `/flows/runs/:run_id`);
        // `tests/agent_runner_test.rs` lo comprueba contra el router de verdad.
        // Misma puerta que el resto: sesión local de un humano owner/admin. Aquí es lo esencial —
        // esta fila ES el registro de una persona autorizando al hub a escribir sin nadie
        // delante, así que `decided_by` sale de la sesión resuelta y JAMÁS del body.
        .route("/api/hub/flows/approvals", get(flows_api::list_approvals))
        .route(
            "/api/hub/flows/approvals/:id/approve",
            post(flows_api::approve),
        )
        .route(
            "/api/hub/flows/approvals/:id/reject",
            post(flows_api::reject),
        )
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
        // hub#963 — the public door. `/p/:locator` is the only path in this router that answers
        // somebody with NO session: the diner holding a ticket. Its authorisation is the locator
        // itself (`public_door`), and the mint below is the session-gated side of the same pair.
        .route(
            "/p/:locator",
            get(public_door::show).post(public_door::redeem),
        )
        .route("/api/hub/public-claims", post(public_door::mint_claim))
        .route("/api/error-report", post(frontend_error_report))
        .route("/api/auth/pin", post(auth_pin))
        .route("/api/auth/badge", post(auth_badge))
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
        // Report of inappropriate AI-generated content (Microsoft Store policy 11.16, hub#946):
        // any signed-in hub user; funneled into the global error registry (ADR-0052) → Cloud.
        .route("/api/assistant/report", post(assistant_report::report))
        // El plan del asistente y su checkout, por el runtime (saas#1540). Van AQUÍ y no desde el
        // navegador porque la credencial hub-scoped es secreto del runtime (ADR-0003): el web app
        // no tiene —ni debe tener— con qué firmar estas llamadas.
        .route("/api/assistant/config", get(assistant_config))
        .route("/api/assistant/checkout", post(assistant_checkout))
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

/// **Liveness**: ¿el proceso responde? Nada más — y por eso es un literal.
///
/// La pregunta que de verdad importa al desplegar («¿puedo atender?») la contesta
/// [`readiness::readyz`], y es la que mira el `HEALTHCHECK`. Mezclarlas fue el bug: durante meses
/// esto FUE el healthcheck del contenedor, así que un hub sin BD, con las migraciones a medias o
/// sin un solo módulo cargado pasaba por sano.
/// Manda al Cloud que una actualización automática de módulo se cayó (hub#516).
///
/// Si actualizamos solos y sin preguntar (ADR-0269), una actualización que falla no puede quedarse
/// en un `eprintln!` del contenedor: `outcome` distingue el caso tolerable —el hub siguió con la
/// versión de ayer— del que no lo es: **el hub arrancó sin el módulo**, que es el único desenlace
/// que este modelo prohíbe. Best-effort por contrato del registro: sin sink (hub sin enrolar) se
/// descarta en silencio.
fn report_failed_module_update(
    module_id: &str,
    from: &str,
    to: &str,
    error: &str,
    fell_back: bool,
) {
    use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry};

    ErrorRegistry::global().report(
        ErrorEvent::new(
            erplora_runtime::error_registry::source::HUB,
            "module_update_failed",
            format!("no se pudo actualizar `{module_id}` de {from} a {to}: {error}"),
            erplora_runtime::error_registry::severity::UNEXPECTED,
        )
        .with_module(module_id.to_string())
        .with_context(json!({
            "from": from,
            "to": to,
            // `stayed_on_previous` = el hub sirve; `no_module` = arrancó incompleto.
            "outcome": if fell_back { "stayed_on_previous" } else { "no_module" },
        })),
    );
}

/// El informe de un arranque **incompleto** (hub#571), sin mandarlo todavía.
///
/// Aparte para poder fijarlo con un test: lo que importa de este evento es su **contenido** —el
/// código estable contra el que se programa y los módulos que faltan—, no que se haya llamado a un
/// sink global.
///
/// Es un fallo **del hub**, no de un módulo: lo que se cayó es el arranque, y colgárselo al primero
/// de la lista mandaría a mirar donde no es.
fn incomplete_boot_event(orphans: &[(String, String)]) -> erplora_runtime::error_registry::ErrorEvent {
    use erplora_runtime::error_registry::{severity, source, ErrorEvent};

    let names: Vec<String> = orphans
        .iter()
        .map(|(id, version)| format!("{id}@{version}"))
        .collect();
    ErrorEvent::new(
        source::HUB,
        "module_boot_incomplete",
        format!(
            "el hub arrancó SIN {} módulo(s) instalados: {} — ni el marketplace ni la copia local \
             pudieron reponerlos",
            orphans.len(),
            names.join(", ")
        ),
        severity::UNEXPECTED,
    )
    .with_context(json!({
        "count": orphans.len(),
        "modules": orphans
            .iter()
            .map(|(id, version)| json!({ "module_id": id, "version": version }))
            .collect::<Vec<_>>(),
    }))
}

/// Manda al Cloud que este hub arrancó **sin** alguno de sus módulos (hub#571).
///
/// Es el caso que ADR-0269 no puede cumplir: no hay copia, no hay versión anterior y no hay tarea
/// vieja a la que volver. Lo único que sí está en nuestra mano es que **no sea un silencio** — un
/// hub incompleto que solo lo cuenta en el log de un contenedor es un hub que nadie arregla.
/// Best-effort por contrato del registro: sin sink (hub sin enrolar) se descarta.
fn report_incomplete_boot(orphans: &[(String, String)]) {
    eprintln!(
        "🔴 el hub arranca SIN {} módulo(s): {}",
        orphans.len(),
        orphans
            .iter()
            .map(|(id, v)| format!("{id}@{v}"))
            .collect::<Vec<_>>()
            .join(", ")
    );
    erplora_runtime::error_registry::ErrorRegistry::global().report(incomplete_boot_event(orphans));
}

/// La versión que debe correr un módulo en este arranque (hub#516).
///
/// Delega en [`install::resolve_target`] — **el mismo resolutor que usa el botón «Actualizar»** y
/// que `/api/modules/updates`. Una segunda copia de esta decisión sería una segunda política: la
/// automática y la manual acabarían ofreciendo cosas distintas.
async fn resolve_module_target(
    state: &AppState,
    machine: &cloud_client::Auth,
    module_id: &str,
    installed: &str,
    pinned: Option<&str>,
) -> erplora_runtime::module_update::Target {
    install::resolve_target(
        &state.http,
        &state.config.cloud_base_url,
        machine,
        module_id,
        installed,
        pinned,
    )
    .await
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
    // `/p/...` (hub#963) is in the allow-list for the same reason the three above are: the person
    // on the other side is a CUSTOMER holding a printed ticket. They cannot enrol a device, and a
    // hub that already put a locator on paper has to honour it whatever state its enrolment is in.
    if matches!(path, "/healthz" | "/readyz" | "/api/hub/context")
        || public_door::is_public_path(path)
        || st.is_dev_hub()
        || st.machine_registered()
    {
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

/// `X-Robots-Tag: noindex` en TODAS las respuestas del hub + `/robots.txt`.
///
/// Un hub es la caja de un cliente: **nunca** se indexa. No es una preferencia de SEO —
/// `{slug}.erplora.com` dice quién es el cliente, la portada dice qué módulos tiene instalados, y
/// detrás hay un login de un TPV real. Y no hay nada que ganar en el otro platillo: ninguna página
/// de un hub es un resultado de búsqueda que queramos.
///
/// Dos capas porque tapan agujeros distintos: el `robots.txt` es para el rastreador que pregunta,
/// y la cabecera para el que no —y para la URL que un `robots.txt` no sabe describir, como un
/// enlace profundo que alguien pegó en una issue pública—. `noarchive` va porque una copia
/// cacheada de una pantalla de caja no debe sobrevivir a la pantalla.
///
/// La tercera capa vive en `apps/web/index.html` (meta `robots`), que es la copia del documento
/// que esta capa NO cubre: la que va empaquetada dentro de la app instalada. Contrato completo en
/// `crates/server/tests/never_indexed.rs`.
const ROBOTS_TAG: &str = "noindex, nofollow, noarchive";

/// Cuerpo del `robots.txt` de un hub: sin `Allow`, sin `Sitemap`, sin excepciones.
const HUB_ROBOTS_TXT: &str = "User-agent: *\nDisallow: /\n";

async fn robots_txt() -> impl axum::response::IntoResponse {
    (
        [(
            axum::http::header::CONTENT_TYPE,
            "text/plain; charset=utf-8",
        )],
        HUB_ROBOTS_TXT,
    )
}

/// Añade la cabecera a lo que salga del router — incluidos los 404 y el fallback SPA, que son
/// justo las respuestas que una capa montada «por ruta» se dejaría fuera.
pub fn with_noindex(router: Router) -> Router {
    router.layer(tower_http::set_header::SetResponseHeaderLayer::overriding(
        axum::http::HeaderName::from_static("x-robots-tag"),
        HeaderValue::from_static(ROBOTS_TAG),
    ))
}

/// Añade el header `Content-Security-Policy` a TODAS las respuestas (ADR-0050). La CSP de
/// `tauri.conf` **no** aplica a este documento —solo la inyecta el protocolo de assets de Tauri, y
/// la ventana de la app instalada navega a ESTE servidor (ADR-0159)—, así que el runtime es el
/// único que puede emitirla. En las respuestas de API el header es inocuo.
///
/// El valor sale siempre de [`resolve_csp`]: [`default_csp`] salvo que `HUB_CSP` lo sustituya. La
/// mención a un `embedded_serve_config` y a un `None` que había aquí quedó obsoleta: el runtime
/// embebido del shell ya no existe, y desde hub#708 tampoco existe el caso «sin política».
pub fn with_csp(router: Router, csp: &str) -> Router {
    use axum::http::header::CONTENT_SECURITY_POLICY;
    // No abortar el arranque por una CSP mal formada (un salto de línea, un byte no-ASCII), pero
    // TAMPOCO servir sin política: se cae a la de por defecto y se avisa. `resolve_csp` ya filtra
    // el camino de `HUB_CSP`; esto cubre a cualquier otro llamador. Servir sin header era la rama
    // que dejó a la flota entera sin CSP (hub#708), así que aquí ya no existe.
    let value = HeaderValue::from_str(csp).unwrap_or_else(|e| {
        eprintln!("CSP inválida ({e}): se sirve la política por defecto en su lugar");
        HeaderValue::from_str(&default_csp("")).expect("la CSP por defecto siempre es un header")
    });
    router.layer(tower_http::set_header::SetResponseHeaderLayer::overriding(
        CONTENT_SECURITY_POLICY,
        value,
    ))
}

/// El router que monta [`serve`] de verdad: API + (opcional) front estático + la CSP, que **no** es
/// opcional. Extraído por el mismo motivo que [`build_router`] en su día: para poder afirmar sobre
/// la composición REAL sin bindear un puerto. Que la cabecera no dependa de una rama `if let` es el
/// contrato que fija `crates/server/tests/cloud_csp.rs`.
pub fn build_serving_router(state: AppState, web_dir: Option<&str>, csp: &str) -> Router {
    with_noindex(with_csp(build_router(state, web_dir), csp))
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
    let (pin_users, currency, currency_decimals, language, timezone) = {
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
        // La zona horaria del negocio ya RESUELTA (hub#731). En `settings` la clave viaja cruda
        // (`null` = «dedúcela del país») porque tiene que poder volver por un `PUT`; aquí se
        // expone el nombre IANA real, que es lo que la UI necesita para enseñar a qué hora local
        // se va a disparar un flujo. Si la lectura falla, UTC — que es lo que el reloj hará.
        let timezone = rt.timezone_name().await.unwrap_or_else(|_| "UTC".to_string());
        (pin_users, currency, currency_decimals, language, timezone)
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
        // Which Cloud this hub belongs to (hub#1164): the same `HUB_CLOUD_API_URL` the CSP
        // `connect-src` is built from. The web app resolves its Cloud base URL from here at boot
        // instead of a build-time constant, so one image serves pre and prod alike. Empty when no
        // Cloud is configured (dev binary): the shell then keeps its build-time fallback.
        "cloud_base_url": st.config.cloud_base_url,
        "business_type": sector,
        "sector": sector,
        // Settings de arranque (tabla `hub_settings` ∪ defaults). El SPA los usa para formato de
        // moneda + locale sin un fetch extra a `/api/settings`.
        "currency": currency,
        // Cuántos decimales tiene esa moneda. El front NO puede asumir 2 (ADR-0123 §7).
        "currency_decimals": currency_decimals,
        "language": language,
        // Nombre IANA del reloj del NEGOCIO (hub#731) — resuelto, nunca `null`.
        "timezone": timezone,
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
            let chunks = ingest::collect_chunks(rt.registry(), &installed.module_id);
            drop(rt);
            index_module_embeddings(&st, &auth, &installed.module_id, &installed.version, chunks)
                .await;

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
            install_error_response(&e)
        }
    }
}

/// Ingestión de embeddings (§9.6): recoge el texto agéntico del módulo (`agent.description` +
/// `ai.description` de queries/commands), lo embebe **vía el proxy del Cloud** (§9.3 — el Hub nunca
/// llama a un proveedor de embeddings directamente) y lo registra en el índice vectorial para el
/// routing de tools (§9.2b).
///
/// Best-effort: un fallo aquí NO aborta nada (el módulo ya está instalado y operativo; el router
/// degrada a "todos"). Corre también tras un **update** (hub#516): la versión nueva puede describir
/// tools distintas, y un índice que se queda con el texto de la versión anterior enruta a ciegas.
async fn index_module_embeddings(
    st: &AppState,
    auth: &cloud_client::Auth,
    module_id: &str,
    version: &str,
    chunks: Vec<ingest::PendingChunk>,
) {
    if chunks.is_empty() {
        return;
    }
    let Some(store) = &st.vector else {
        tracing::info!(module_id = %module_id, chunks = chunks.len(), "sin índice vectorial; ingestión de embeddings omitida (§9.5)");
        return;
    };
    let embedder =
        embed::CloudEmbedder::new(st.http.clone(), &st.config.cloud_base_url, auth.clone());
    match embed::index_chunks(&embedder, store.as_ref(), &st.hub_id(), version, &chunks).await {
        Ok(n) => tracing::info!(module_id = %module_id, chunks = n, "embeddings indexados (§9.6)"),
        Err(e) => {
            tracing::warn!(module_id = %module_id, error = %e, "ingestión de embeddings falló (no crítico; router degrada)")
        }
    }
}

/// Cuerpo (opcional) de `POST /api/modules/:id/update`. Sin `version` = **la última**, que es lo
/// que se ofrece por defecto; con `version` = la que se eligió (palanca de soporte).
///
/// Elegir una versión concreta **no la clava**: el arranque siguiente vuelve a resolver la última
/// (ADR-0269 — nadie se queda atrás). Clavar es el **pin de soporte**, herramienta nuestra, y no se
/// toca desde aquí.
#[derive(Deserialize, Default)]
struct UpdateModuleReq {
    #[serde(default)]
    version: Option<String>,
}

/// **Actualiza un módulo sin reiniciar el contenedor** (hub#675 + hub#516).
///
/// Es lo que hace que un fix de módulo **no espere a una imagen nueva del hub**: los módulos solo se
/// recogían al arrancar, y `rollout_hub_fleet` excluye a los hubs que ya están en la imagen
/// objetivo, así que no había campaña que provocase el reinicio.
///
/// Va por [`install::update_from_cloud`] y **no** por `install_from_cloud`, y la diferencia no es
/// cosmética: con el plan del Cloud (ADR-0060) el módulo que ya está instalado viaja en el set
/// instalado, vuelve como `already_satisfied` y `execute_plan` lo **salta** — el update habría dicho
/// que sí sin descargar nada. La puerta de update lo excluye del set y no lo salta.
///
/// **Si la versión nueva falla, la anterior sigue puesta**, y por dos caminos que se componen: el
/// runtime repone en memoria lo que el módulo aportaba (hub#516, `Registry::snapshot_module`), y
/// encima `update_with_fallback` confirma reinstalando la que había. `Outcome::Lost` queda para lo
/// que de verdad lo es: que ni siquiera eso valga y el hub se quede sin el módulo.
///
/// Auth = **sesión local de admin** *más* credencial hub-scoped, igual que `request-install`. La
/// sesión no es un detalle: sin ella, cualquier módulo web same-origin podría disparar
/// actualizaciones usando indirectamente el token de máquina del hub.
async fn update_module(
    State(st): State<AppState>,
    Path(module_id): Path<String>,
    headers: HeaderMap,
    body: Option<Json<UpdateModuleReq>>,
) -> Response {
    use erplora_runtime::module_update::{update_with_fallback, Outcome};

    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response();
    };

    // La versión que tiene ahora: es a la que hay que volver si la nueva falla.
    let installed = {
        let rt = st.runtime.lock().await;
        rt.registry().module_version(&module_id)
    };
    if !st.runtime.lock().await.registry().is_installed(&module_id) {
        return install_error_response(&install::InstallError::NotInstalled(module_id));
    }

    // Vacío / `latest` = lo que el resolutor decida (el MISMO del arranque: cuarentena y pin
    // mandan, nunca hacia atrás). Se resuelve AQUÍ, antes de tocar nada, porque el destino tiene que
    // ser una versión concreta: es la que se compara con la instalada para saber si hay algo que
    // hacer, y la que se reporta como `from → to`.
    let requested = body
        .map(|Json(b)| b)
        .unwrap_or_default()
        .version
        .unwrap_or_default();
    let target = {
        let rt = st.runtime.lock().await;
        install::resolve_update_target(
            &st.http,
            &st.config.cloud_base_url,
            &auth,
            &rt,
            &module_id,
            &requested,
        )
        .await
    };

    // Mismas fases que instalar (`resolving → downloading → verifying → installing`): la card del
    // catálogo ya sabe pintarlas, así que actualizar se ve igual de vivo que instalar.
    let progress_state = st.clone();
    let root_id = module_id.clone();
    let on_progress = move |current: &str, phase: &str| {
        progress_state.broadcast(json!({
            "type": "module.install.progress",
            "module_id": current,
            "root_id": root_id,
            "phase": phase,
        }));
    };

    // El fallo del PRIMER intento se guarda entero, no como texto: un plan `blocked` (dependencia
    // premium sin comprar) o un `NotInstalled` son decisiones que le tocan al usuario, con su código
    // y su puntero de compra — convertirlos en «no se pudo, sigues en la anterior» perdería la única
    // información accionable que llevan.
    let first_error: std::sync::Arc<std::sync::Mutex<Option<install::InstallError>>> =
        std::sync::Arc::new(std::sync::Mutex::new(None));

    // `update_with_fallback` compara `from`/`to` y decide la secuencia; la instalación real la pone
    // este closure. Pedir la versión de partida es barato: `update_from_cloud` ve `to == from` y no
    // descarga nada, así que la vuelta atrás confirma sin repetir trabajo.
    let outcome = update_with_fallback(&installed, &target, |version| {
        let st = st.clone();
        let auth = auth.clone();
        let module_id = module_id.clone();
        let on_progress = &on_progress;
        let first_error = first_error.clone();
        async move {
            let mut rt = st.runtime.lock().await;
            let result = install::update_from_cloud(
                &st.http,
                &st.config.cloud_base_url,
                &st.config.module_cache,
                &auth,
                &mut rt,
                &module_id,
                &version,
                on_progress,
                &st.config.signature_policy(),
            )
            .await;
            match result {
                Ok(_) => Ok(()),
                Err(e) => {
                    let message = e.to_string();
                    first_error.lock().unwrap().get_or_insert(e);
                    Err(message)
                }
            }
        }
    })
    .await;

    // Lo que el dueño verá mañana en Sistema → Actualizaciones (hub#564). Se anota AQUÍ, con el
    // resultado en la mano: el estado actual del hub no se puede restar de sí mismo para deducir
    // una transición, así que si no se escribe cuando ocurre, no existe. Misma decisión que el
    // arranque (`from_module_outcome`), y `AlreadyThere` no escribe nada porque no cambió nada.
    // Best-effort: no poder anotar el historial no convierte una actualización buena en un error.
    {
        let rt = st.runtime.lock().await;
        let module_name = rt
            .registry()
            .installed
            .iter()
            .find(|m| m.id == module_id)
            .map(|m| m.name.clone())
            .unwrap_or_else(|| module_id.clone());
        if let Some(change) =
            erplora_runtime::update_history::from_module_outcome(&module_id, &module_name, &target, &outcome)
        {
            if let Err(e) =
                erplora_runtime::update_history::record(rt.db(), &st.hub_id(), change).await
            {
                tracing::warn!(module_id = %module_id, error = %e, "no se pudo anotar el historial de actualización (hub#564)");
            }
        }
    }

    // Un fallo con decisión del usuario detrás (409 `install_blocked`, 404 `update_not_installed`)
    // se cuenta como lo que es, no como «no se pudo».
    if !matches!(outcome, Outcome::Updated { .. } | Outcome::AlreadyThere(_)) {
        if let Some(e) = first_error.lock().unwrap().as_ref() {
            if matches!(
                e,
                install::InstallError::Blocked { .. } | install::InstallError::NotInstalled(_)
            ) {
                return install_error_response(e);
            }
        }
    }

    match outcome {
        Outcome::AlreadyThere(version) => {
            Json(json!({ "ok": true, "data": { "module_id": module_id, "version": version, "updated": false } })).into_response()
        }
        Outcome::Updated { from, to } => {
            // La versión nueva puede describir tools distintas: un índice que se queda con el texto
            // de la anterior enruta a ciegas.
            let chunks = {
                let rt = st.runtime.lock().await;
                ingest::collect_chunks(rt.registry(), &module_id)
            };
            index_module_embeddings(&st, &auth, &module_id, &to, chunks).await;
            // Lo único que el dueño ve de toda la maquinaria (ADR-0269 §3.5): qué cambió y de qué
            // versión a cuál. `module.installed` va detrás porque es el evento que el shell YA
            // escucha (App.vue) para refrescar entitlement + nav.
            st.broadcast(json!({
                "type": "module.updated",
                "module_id": module_id,
                "from": from,
                "to": to,
            }));
            st.broadcast(json!({ "type": "module.installed", "module_id": module_id }));
            Json(json!({ "ok": true, "data": { "module_id": module_id, "from": from, "version": to, "updated": true } })).into_response()
        }
        // 200, no 5xx: la actualización no salió, pero **el módulo sigue funcionando**. Devolver un
        // error haría pensar que el hub se quedó tocado, y no es el caso.
        Outcome::RolledBack { stayed_on, error } => Json(json!({
            "ok": true,
            "data": { "module_id": module_id, "version": stayed_on, "updated": false },
            "warning": { "code": "module.update_failed_kept_previous", "message": error },
        }))
        .into_response(),
        Outcome::Lost { module, error } => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "ok": false, "error": { "code": "module.update_lost", "message": format!("`{module}`: {error}") } })),
        )
            .into_response(),
    }
}

/// `GET /api/modules/updates` — qué versión ofrece hoy el marketplace para cada módulo instalado
/// (hub#516). **Bajo demanda**, no en bucle: lo pregunta la pantalla de Apps cuando alguien la
/// abre. Un sondeo periódico costaría una llamada por módulo (24) contra el Cloud sin que nadie
/// esté mirando, y la vía desatendida ya la cubre el arranque, que resuelve la última versión.
///
/// Usa **el mismo resolutor** que el arranque, así que lo que el botón ofrece es exactamente lo que
/// la actualización automática haría sola: nunca una versión en cuarentena, nunca hacia atrás, y el
/// pin de soporte gana. Si el Cloud no contesta, `latest == installed` y no se ofrece nada —
/// inventar una versión sería peor que no decir nada.
async fn list_module_updates(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let installed: Vec<(String, String, Option<String>)> = {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
        match erplora_runtime::installer::installed_with_pin(rt.db(), &st.hub_id()).await {
            Ok(rows) => rows,
            Err(e) => {
                return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(json!({ "ok": false, "error": e.to_string() })),
                )
                    .into_response()
            }
        }
    };

    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        // Sin credencial no se puede preguntar al marketplace. No es un error: es «no lo sé», y
        // «no lo sé» nunca se pinta como «hay actualización».
        return Json(json!({ "ok": true, "data": [] })).into_response();
    };

    let mut out = Vec::with_capacity(installed.len());
    for (module_id, version, pinned) in installed {
        let target = install::resolve_target(
            &st.http,
            &st.config.cloud_base_url,
            &auth,
            &module_id,
            &version,
            pinned.as_deref(),
        )
        .await;
        out.push(json!({
            "module_id": module_id,
            "installed": version,
            "latest": target.version(),
            "update_available": target.is_update(),
            "pinned": pinned,
        }));
    }
    Json(json!({ "ok": true, "data": out })).into_response()
}

/// `GET /api/modules/:id/versions` — entre qué versiones puede elegir este hub (hub#675).
///
/// Es la lista del **desplegable de versión**, y sirve a las dos puertas: instalar (el módulo aún no
/// está: valen todas las publicadas) y actualizar (solo hacia delante desde la instalada). Por eso
/// **no es un 404** pedir las versiones de algo que no está instalado —esa regla es de `update`, no
/// de esta— y por eso `installed` puede venir `null`.
///
/// La política la pone `module_update::offer`, la misma pieza que decide la actualización
/// automática: fuera la cuarentena, fuera el retroceso, y un módulo clavado por soporte no ofrece
/// nada. Sin eso, el desplegable sería una segunda puerta con una segunda política.
///
/// Auth = **sesión de admin**, igual que instalar y actualizar. Sin ella no se pregunta al Cloud:
/// la respuesta viaja con la credencial de máquina del hub, y cualquier módulo web same-origin
/// podría usarla de rebote para leer el catálogo.
async fn list_module_versions(
    State(st): State<AppState>,
    Path(module_id): Path<String>,
    headers: HeaderMap,
) -> Response {
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }

    // Todo lo que hace falta del hub, y **se suelta el candado**: la llamada al Cloud viene después.
    // Sostener el `Mutex<Runtime>` durante un round-trip de red congelaría `/api/query` y
    // `/api/command` —el TPV— mientras el marketplace tarda en contestar.
    let (installed, pinned) = {
        let rt = st.runtime.lock().await;
        (
            install::installed_version(&rt, &module_id),
            install::support_pin(&rt, &module_id).await,
        )
    };

    // Sin credencial no se puede preguntar al marketplace. No es un error: es «no lo sé», y «no lo
    // sé» se pinta como «no hay nada que elegir», nunca como una lista inventada.
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return Json(json!({
            "ok": true,
            "data": { "module_id": module_id, "installed": installed, "latest": null, "versions": [] },
        }))
        .into_response();
    };

    let versions = install::offered_versions(
        &st.http,
        &st.config.cloud_base_url,
        &auth,
        &module_id,
        installed.as_deref(),
        pinned.as_deref(),
    )
    .await;

    Json(json!({
        "ok": true,
        "data": {
            "module_id": module_id,
            "installed": installed,
            // La que se ofrece por defecto: la primera de la lista. `null` = no hay nada que elegir.
            "latest": versions.first(),
            "versions": versions,
        },
    }))
    .into_response()
}

/// Status HTTP de un fallo del pipeline de instalación/actualización. Compartido por
/// `request-install` y `update` (hub#516): el mismo fallo tiene que contarse igual por las dos
/// puertas, o la UI acaba programando contra dos contratos.
fn install_error_status(e: &install::InstallError) -> StatusCode {
    match e {
        install::InstallError::VersionNotFound(_) => StatusCode::NOT_FOUND,
        // Actualizar algo que no está instalado: no hay recurso al que aplicar la operación.
        install::InstallError::NotInstalled(_) => StatusCode::NOT_FOUND,
        install::InstallError::Runtime(_) => StatusCode::UNPROCESSABLE_ENTITY,
        // Fallo de FIRMA (hub#239): el módulo no verifica — sin firma, firma inválida o
        // clave ajena. Es un rechazo de seguridad, NO un fallo de gateway: 403.
        install::InstallError::Source(source::SourceError::BadSignature(_)) => StatusCode::FORBIDDEN,
        // ADR-0060: el plan exige comprar dependencias. NO es un fallo del hub ni del
        // Cloud: es una decisión que le toca al usuario → 409 con los datos de compra.
        install::InstallError::Blocked { .. } => StatusCode::CONFLICT,
        install::InstallError::Cloud(_)
        | install::InstallError::Source(_)
        | install::InstallError::MissingSha256 { .. } => StatusCode::BAD_GATEWAY,
    }
}

/// Respuesta de un fallo del pipeline, con el canal de errores de dominio (hub#139): además del
/// mensaje humano viaja un `code` estable contra el que la UI programa y traduce. Un install —o un
/// update— fallido no es mudo.
fn install_error_response(e: &install::InstallError) -> Response {
    let mut body = json!({
        "ok": false,
        "error": e.to_string(),
        "code": e.code(),
    });
    if let install::InstallError::Blocked {
        blocked_on,
        purchase,
        ..
    } = e
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
    (install_error_status(e), Json(body)).into_response()
}

/// Lo que se le dice a las cachés sobre un asset servido por la ruta **con** versión: el contenido
/// de una versión publicada no cambia jamás (republicar exige subir la versión), así que se puede
/// guardar para siempre. Es lo que hace que la url versionada además sea *más rápida* que la de
/// antes, no solo más correcta.
const MODULE_ASSET_IMMUTABLE: &str = "public, max-age=31536000, immutable";

/// Y lo que se le dice sobre la ruta **sin** versión: ahí el contenido SÍ cambia bajo los pies (es
/// «la versión instalada», sea cual sea hoy), así que guardarla sin preguntar es exactamente el
/// defecto de hub#935. `no-cache` no prohíbe almacenarla: obliga a revalidarla antes de usarla.
const MODULE_ASSET_REVALIDATE: &str = "no-cache, must-revalidate";

/// Un segmento de ruta que no puede salir del `module_cache` (ni `..` ni vacío ni separadores).
fn is_safe_path_segment(seg: &str) -> bool {
    !seg.is_empty() && seg != ".." && seg != "." && !seg.contains('/') && !seg.contains('\\')
}

/// Lee `module_cache/<id>/<version>/<rel>` y lo devuelve con su content-type y su política de caché.
async fn read_module_asset(
    st: &AppState,
    id: &str,
    version: &str,
    rel: &str,
    cache_control: &'static str,
) -> Response {
    // Anti path-traversal: ningún segmento `..` (incluido tras decodificar %2e%2e) ni vacío.
    if rel.split('/').any(|seg| !is_safe_path_segment(seg)) {
        return StatusCode::NOT_FOUND.into_response();
    }
    let full = st.config.module_cache.join(id).join(version).join(rel);
    match tokio::fs::read(&full).await {
        Ok(bytes) => (
            [
                (header::CONTENT_TYPE, module_asset_content_type(rel)),
                (header::CACHE_CONTROL, cache_control),
            ],
            bytes,
        )
            .into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

/// GET /modules/:id/v/:version/*path — el MISMO asset, direccionado por versión (hub#935).
///
/// Existe porque un módulo actualizado no llegaba al navegador: todas las versiones se servían desde
/// la misma url y sin una sola cabecera de caché, así que el borde cacheaba el `.js` por extensión
/// (`cf-cache-status: HIT`) y el `import()` del shell seguía recibiendo el bundle anterior mientras
/// el `module.json` ya decía la versión nueva. El fallo era MUDO: manifest nuevo, servidor nuevo,
/// pantalla vieja. Un `?v=` no lo arregla —el borde ignora la query para la clave de caché—; una
/// ruta distinta sí, porque ninguna caché la ha visto antes.
///
/// Sirve **cualquier versión presente en la caché de descargas**, no solo la instalada: es lo que la
/// hace inmutable de verdad (una pestaña abierta desde antes de actualizar sigue resolviendo su
/// bundle) y lo que permite declararla cacheable un año. El módulo sí tiene que estar instalado.
async fn serve_module_asset_at(
    State(st): State<AppState>,
    Path((id, version, rel)): Path<(String, String, String)>,
) -> Response {
    // La versión es un segmento de ruta más y llega del cliente: hostil hasta que se demuestre.
    if !is_safe_path_segment(&version) {
        return StatusCode::NOT_FOUND.into_response();
    }
    let installed = {
        let rt = st.runtime.lock().await;
        rt.modules().into_iter().any(|m| m.id == id)
    };
    if !installed {
        return StatusCode::NOT_FOUND.into_response();
    }
    read_module_asset(&st, &id, &version, &rel, MODULE_ASSET_IMMUTABLE).await
}

/// GET /modules/:id/*path — sirve los assets web (`module.json`, `dist/*.esm.js`, wasm, icons) de un
/// módulo instalado desde la CACHÉ de descargas, resueltos por la VERSIÓN instalada
/// (`module_cache/<id>/<version>/<path>`). La versión sale del registro (el módulo debe estar
/// instalado). Guard anti path-traversal. Un asset ausente o un módulo no instalado → **404** (lo
/// maneja el cargador del Web Component); al ser ruta explícita NO cae al fallback SPA, así que nunca
/// se sirve `index.html` haciéndose pasar por JS/JSON (que es exactamente lo que rompía la UI).
///
/// Sigue siendo la ruta del `module.json` —quien DICE en qué versión está el módulo— y el respaldo
/// para clientes anteriores a hub#935. Por eso va marcada «revalida siempre»: su contenido cambia
/// cada vez que se actualiza el módulo, y servirla de una caché es servir la versión de ayer.
async fn serve_module_asset(
    State(st): State<AppState>,
    Path((id, rel)): Path<(String, String)>,
) -> Response {
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
    read_module_asset(&st, &id, &version, &rel, MODULE_ASSET_REVALIDATE).await
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
    cloud_get_raw_full(st, headers, req)
        .await
        .map(|(status, _retry_after, body)| (status, body))
}

/// Como [`cloud_get_raw`] pero devolviendo además el `Retry-After` en segundos cuando el Cloud lo
/// manda (hub#1167). Sólo lo necesita quien tiene que **dejar de llamar**: DRF pone esa cabecera
/// en sus 429 y es el único que sabe cuánto le queda a la ventana de la hora — en producción se
/// han visto 2828 s. Estimarla es peor que leerla, y seguir llamando durante ese rato mantiene
/// vacío un cubo de tokens que comparte toda la flota (saas#1640).
async fn cloud_get_raw_full(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
) -> Result<(StatusCode, Option<i64>, axum::body::Bytes), CloudGetError> {
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
    // `Retry-After` admite segundos o una fecha HTTP; DRF manda siempre segundos. Una fecha o un
    // valor ilegible se ignoran (=> `None`) y el llamador aplica su default acotado: preferimos
    // una ventana nuestra a una interpretación inventada de la ajena.
    let retry_after = resp
        .headers()
        .get(axum::http::header::RETRY_AFTER)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.trim().parse::<i64>().ok());
    let body = resp
        .bytes()
        .await
        .map_err(|e| CloudGetError::Network(e.to_string()))?;
    Ok((status, retry_after, body))
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

    let now = entitlement::now_unix();

    // ¿Hace falta salir a la red? El shell pregunta una vez por `focus` de ventana y otra por cada
    // vista de módulo que monta; sin este corte cada una de esas veces era una llamada al SaaS.
    let decision = st
        .entitlement_proxy
        .read()
        .map(|cache| cache.decide(now))
        .unwrap_or(entitlement::Decision::Ask);
    match decision {
        entitlement::Decision::Serve(body) => {
            return entitlement_response(StatusCode::OK, body, revalidation)
        }
        entitlement::Decision::RateLimited => return rate_limited_response(revalidation),
        entitlement::Decision::Ask => {}
    }

    match cloud_get_raw_full(&st, &headers, cloud.entitlement(&placeholder)).await {
        // El SaaS nos está limitando la tasa. Ni el status ni su prosa pueden llegar al navegador:
        // el shell lee el error como «no hay módulos» y degrada pantallas de módulos ya comprados,
        // y el `{"detail":"Request was throttled…"}` de DRF es inglés dentro de una UI en español.
        Ok((StatusCode::TOO_MANY_REQUESTS, retry_after, _body)) => {
            let served = match st.entitlement_proxy.write() {
                Ok(mut cache) => {
                    cache.open_backoff(retry_after, now);
                    cache.last_good().cloned()
                }
                Err(_) => None,
            };
            report_cloud_rate_limited(retry_after, served.is_some());
            match served {
                Some(body) => entitlement_response(StatusCode::OK, body, revalidation),
                None => rate_limited_response(revalidation),
            }
        }
        Ok((status, _retry_after, body)) => match serde_json::from_slice::<Value>(&body) {
            // Body objeto JSON → se le inyecta la clave aditiva.
            Ok(Value::Object(obj)) => {
                // Sólo se guarda lo que el Cloud dio por bueno: cachear un 4xx/5xx lo convertiría
                // en la verdad del hub durante toda la ventana de frescura.
                if status.is_success() {
                    if let Ok(mut cache) = st.entitlement_proxy.write() {
                        cache.store_success(Value::Object(obj.clone()), now);
                    }
                }
                entitlement_response(status, Value::Object(obj), revalidation)
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

/// Respuesta del proxy de entitlement: el cuerpo del Cloud con el bloque aditivo `revalidation`,
/// que SIEMPRE se recalcula (es estado local, y es justo lo que la UI necesita cuando el Cloud no
/// contesta) y por eso nunca se guarda en la caché.
fn entitlement_response(status: StatusCode, body: Value, revalidation: Value) -> Response {
    match body {
        Value::Object(mut obj) => {
            obj.insert("revalidation".into(), revalidation);
            (status, Json(Value::Object(obj))).into_response()
        }
        other => (status, Json(other)).into_response(),
    }
}

/// El único caso en que el rate-limit del Cloud se le cuenta al shell: no había ningún entitlement
/// bueno que servir. Viaja con **código estable** en el envelope de siempre
/// (`{"ok":false,"error":{"code":…}}`) para que la UI lo traduzca por código (ADR-0055) en vez de
/// pintar la frase inglesa que escribió DRF.
fn rate_limited_response(revalidation: Value) -> Response {
    (
        StatusCode::TOO_MANY_REQUESTS,
        Json(json!({
            "ok": false,
            "error": {
                "code": entitlement::CLOUD_RATE_LIMITED,
                "message": "the Cloud is rate-limiting this hub; the entitlement could not be refreshed",
            },
            "revalidation": revalidation,
        })),
    )
        .into_response()
}

/// Deja el rate-limit VISIBLE. Un límite que falla en silencio es peor que uno que grita: sin esto
/// la única huella era una línea roja en la consola del navegador del cajero, que nadie recoge.
/// Va al log del runtime **y** al registro de errores, que es el canal que llega al Cloud.
fn report_cloud_rate_limited(retry_after: Option<i64>, served_from_cache: bool) {
    use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry};

    tracing::warn!(
        retry_after_secs = retry_after.unwrap_or(-1),
        served_from_cache,
        "el Cloud limita la tasa del entitlement (saas#1640)"
    );
    ErrorRegistry::global().report(
        ErrorEvent::new(
            erplora_runtime::error_registry::source::HUB,
            entitlement::CLOUD_RATE_LIMITED,
            "el Cloud respondió 429 al refrescar el entitlement",
            erplora_runtime::error_registry::severity::UNEXPECTED,
        )
        .with_context(json!({
            "retry_after_secs": retry_after,
            // `cache` = el cajero no se enteró; `none` = se le contó el fallo, que es lo grave.
            "outcome": if served_from_cache { "cache" } else { "none" },
        })),
    );
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

async fn proxy_marketplace_catalog(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<LocaleQuery>,
) -> Response {
    // **The country the catalogue is asked about is read HERE, from this hub's own settings**
    // (ADR-0062, hub#69) — never from the request. The page cannot widen what its till is offered,
    // and it does not have to know the rule: what comes back is already filtered.
    //
    // **The language is the opposite case, and on purpose** (hub#1003, ADR-0364). The Cloud serves
    // the catalogue per language now, but only to a caller that says which one — silence means
    // English, which is the bug. Unlike the country, it comes from `?locale=` (ADR-0055, the same
    // param `navigation` takes): the country is a fact about the *hub* and a page must not be able
    // to widen it, whereas the language is a fact about the *person reading right now*, and only
    // the page knows which one that is. Widening nothing is exactly what it can do with it.
    //
    // The hub's stored `language` is the fallback, not the source — that is what serves a caller
    // that has not said (an old web build, a script), and it beats defaulting to English for a hub
    // that has told us in its settings which language it reads in.
    let catalog = {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
        let (country_code, region_code) = rt.country_and_region().await;
        let requested = q.locale.unwrap_or_default();
        let language = if requested.trim().is_empty() {
            rt.language().await
        } else {
            requested
        };
        cloud_client::CatalogQuery::new(
            cloud_client::CountryFilter::new(&country_code, &region_code),
            &language,
        )
    };
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    if st.is_dev_hub() {
        return proxy_public_cloud_get(&st, &headers, cloud.public_marketplace_modules(&catalog))
            .await;
    }
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token: String::new(),
    };
    match cloud_get_raw(&st, &headers, cloud.marketplace_modules(&placeholder, &catalog)).await {
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
/// **Qué plan tiene este hub** (saas#1540): tier, consumo del mes y planes contratables.
///
/// El hub solo descubría su plan cuando ya lo había AGOTADO, así que quedarse sin mensajes solo
/// podía presentarse como una avería. Va por el runtime y no desde el navegador porque la
/// credencial hub-scoped es **secreto del runtime** (ADR-0003): el web app no tiene —ni debe
/// tener— con qué firmar esta llamada.
///
/// Reutiliza `proxy_cloud_get`, que ya devuelve el JSON del Cloud sin reinterpretar: un 402/429
/// del SaaS es información que el llamador necesita, y traducirlo a un genérico es exactamente el
/// fallo que esta issue documenta.
async fn assistant_config(State(st): State<AppState>, headers: HeaderMap) -> Response {
    // The hub's machine token further down (`hub_scoped_auth`) is the credential the runtime uses
    // to TALK to the Cloud, not a gate on who is asking (ADR-0003): without this session check the
    // route answered anybody who reached the hub's URL — ERPlora/hub#1254. A read any signed-in
    // user needs (the drawer prints the tier and what is left of the month), so: session.
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return auth_rejected(e);
        }
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: String::new(),
        token: String::new(),
    };
    proxy_cloud_get(&st, &headers, cloud.assistant_config(&placeholder)).await
}

/// **Abrir el checkout del plan del asistente** (saas#1540, ADR-0033) → `{"checkout_url": …}`.
///
/// Sin este camino, un «ver planes» no lleva a ninguna parte: el único momento de conversión del
/// tier gratuito moría en una frase.
async fn assistant_checkout(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    // Contracting the plan is billed to the hub, so it is the ADMIN door — the same one as
    // settings, API keys and the certificate. Until ERPlora/hub#1254 the only credential here was
    // the OUTBOUND machine token, and any anonymous caller who reached the hub could open Stripe
    // checkout sessions in its name.
    {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return auth_rejected(e);
        }
    }
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial" })),
        )
            .into_response();
    };
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let req = cloud.assistant_checkout(&auth);
    let mut r = st.http.post(&req.url);
    for (k, v) in auth.headers() {
        r = r.header(k, v);
    }
    match r.json(&body).send().await {
        Ok(resp) => {
            let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            let bytes = resp.bytes().await.unwrap_or_default();
            cloud_json_passthrough(status, bytes)
        }
        Err(e) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({ "ok": false, "error": e.to_string() })),
        )
            .into_response(),
    }
}

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
    let (all_tools, active_user, active_modules, instructions) = {
        let rt = st.runtime.lock().await;
        let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
            Ok(c) => c,
            Err(e) => return unauthorized(e),
        };
        let tools = assistant::assemble_tools(rt.registry(), &ctx);
        let active = rt.registry().active_module_count();
        // El system prompt del turno (§9.2). Se arma con el MISMO lock que las tools: el mapa de
        // módulos que describe y el catálogo que ofrece tienen que ser la misma foto del registry.
        // Absorbe además los `system` del cliente (el briefing de `hub.setup.status`, ADR-0230),
        // que el Cloud descarta en su frontera — `instructions` es el único canal que sobrevive.
        // La fecha/hora ACTUAL viaja en cada turno: el reloj del modelo se congeló al entrenar,
        // y en un ERP «hoy» es estructural (ventas de hoy, trimestre, vencimientos).
        let now = chrono::Utc::now();
        let instructions = assistant::build_instructions(
            rt.registry(),
            &assistant::client_system_messages(&frontend),
            &format!("{} ({})", now.format("%Y-%m-%dT%H:%M:%SZ"), now.format("%A")),
        );
        (tools, ctx.user_id.clone(), active, instructions)
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

    // Lo que el catálogo YA resolvió sobre cada tool, para anotar los eventos `function_call`
    // que reenviamos. El drawer no tiene catálogo propio donde consultarlo, y ninguna de estas
    // tres cosas puede venir del modelo — son hechos del manifest:
    //
    //   · `kind`         — el web app auto-ejecuta las LECTURAS y confirma las ESCRITURAS (§9.2).
    //   · `risk`         — cuánto daño hace la operación (hub#1042).
    //   · `money_fields` — qué argumentos son dinero, para que la tarjeta enseñe «15,00 €» y no
    //                      `price_cents: 1500` (hub#1040): el único punto donde un humano puede
    //                      cazar un ×100, y el único del producto donde no salía en euros.
    let tool_notes: std::collections::HashMap<String, serde_json::Value> = tools
        .iter()
        .filter_map(|t| {
            let name = t.get("name").and_then(|v| v.as_str())?;
            let mut note = serde_json::Map::new();
            if let Some(kind) = t.get("kind").and_then(|v| v.as_str()) {
                note.insert("kind".to_string(), serde_json::json!(kind));
            }
            if let Some(risk) = t.get("risk").and_then(|v| v.as_str()) {
                note.insert("risk".to_string(), serde_json::json!(risk));
            }
            let money = t
                .get("parameters")
                .map(|p| assistant::money_fields(&p.to_string()))
                .unwrap_or_default();
            if !money.is_empty() {
                note.insert("money_fields".to_string(), serde_json::json!(money));
            }
            if note.is_empty() {
                return None;
            }
            Some((name.to_string(), serde_json::Value::Object(note)))
        })
        .collect();

    let body = assistant::build_cloud_body(&frontend, tools, Some(&active_user), &instructions);

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
                if let Some(frame) = assistant::translate_sse_line(line, &tool_notes) {
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
                        if let Some(frame) = assistant::translate_sse_line(rest.trim(), &tool_notes) {
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
        E::InvalidField { .. } => (StatusCode::UNPROCESSABLE_ENTITY, "invalid_field".into()),
        E::CertificateTypeMismatch { .. } => {
            (StatusCode::CONFLICT, "certificate_type_mismatch".into())
        }
        E::ManifestRejected { code, .. } => (StatusCode::UNPROCESSABLE_ENTITY, code.clone().into()),
        // hub#1088: `business_tax_id` refused with its own stable code per failure kind — the
        // same `422` as `invalid_payload` (what was sent does not validate) with the code the UI
        // translates (es/en), so "the control letter is wrong" and "this is no NIF at all" are
        // two different answers instead of one generic refusal.
        E::InvalidTaxId { code, .. } => (StatusCode::UNPROCESSABLE_ENTITY, (*code).into()),
        // hub#1086: the payload does not carry a bind the query's own SQL references. `422`
        // like `invalid_payload` (it IS a payload-contract refusal, caught before any read),
        // with its own stable code so the caller can tell "you did not send what the query
        // needs" from "what you sent does not validate".
        E::MissingRequiredParam { .. } => {
            (StatusCode::UNPROCESSABLE_ENTITY, "missing_required_param".into())
        }
        // hub#1173: the twin of the above at the same door — a param the LIST query does not
        // declare. Same `422` (it is a payload-contract refusal, caught before any read) with its
        // own stable code, so the caller can tell "that query has no such filter" from "you did
        // not send what it needs" — and fix the call instead of trusting a page that quietly held
        // the whole list.
        E::UnknownFilter { .. } => (StatusCode::UNPROCESSABLE_ENTITY, "unknown_filter".into()),
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
        // hub#554: this hub already emitted, so its tax id is the anchor of a live chain and of the
        // `BillingProfile` upstream (ADR-0201 decisión 5). `409` for the same reason: the request
        // is well-formed and the caller is allowed, it conflicts with what this hub HAS DONE. Its
        // own code, never the demo one — the demo lock has a way out (create your own hub) and this
        // one does not.
        E::BusinessTaxIdFrozen { .. } => (StatusCode::CONFLICT, "business_tax_id_frozen".into()),
        // hub#69: same 409 as its sibling — the request is well formed, the STATE of the hub is
        // what refuses it (ADR-0273: the country freezes at go-live).
        E::HubCountryFrozen { .. } => (StatusCode::CONFLICT, "hub_country_frozen".into()),
        // hub#360 (paso 2b): a refusal a MANAGER could approve. `403` like `permission_denied` —
        // it IS a refusal and nothing ran — but with its own stable code, so the UI can tell
        // "ask the manager" (offer the PIN dialog, hub#363) from "this is not for you". Falling
        // into the generic `400 {code:"error"}` bucket would have made the whole chain undecidable.
        E::RequiresElevation { .. } => (StatusCode::FORBIDDEN, "requires_elevation".into()),
        // hub#714: the module→host permission the OWNER grants (ADR-0079). `403` with its own
        // stable code — the same one `error_registry::error_code_of` already publishes — because
        // it is a refusal with a remedy nobody could guess from a bare `400 {code:"error"}`: go to
        // Settings → Permissions and grant it. It is NOT `permission_denied` (that is the user's
        // RBAC, another axis entirely) and NOT `requires_elevation` (no manager's PIN opens it).
        E::CapabilityDenied { .. } => (StatusCode::FORBIDDEN, "capability_denied".into()),
        // hub#775: a `protects` guard refused the command because a precondition of the route is
        // unmet (the drawer is closed). `409`: the request is well-formed and the caller is
        // allowed, it conflicts with the hub's current state — same shape as the fiscal
        // precondition and the demo locks. Its own code, never `permission_denied`: the action
        // that resolves it is "open the drawer", not "ask the manager".
        E::ProtectsGuard { .. } => (StatusCode::CONFLICT, "protects_guard".into()),
        // hub#1101: other installed modules declare this one in `depends_on`. `409` for the same
        // reason as its neighbours above — the request is well-formed and the caller is allowed,
        // it conflicts with the SHAPE of what this hub has installed. Its own stable code, never
        // the generic `400 {code:"error"}` bucket: the screen does not merely report this one, it
        // ACTS on it (lists the dependants and offers «remove it anyway»), and it cannot do that
        // against an error it cannot tell apart.
        E::HasDependents { .. } => (StatusCode::CONFLICT, "has_dependents".into()),
        E::NotImplemented(_) => (StatusCode::NOT_IMPLEMENTED, "not_implemented".into()),
        // hub#1074: everything else keeps the `400` it always had, but NOT the flat `"error"` code
        // it used to collapse into. `error_code_of` is the registry of stable codes this hub
        // already publishes upstream (`db`, `read_unavailable`, `certificate`…), so the code a
        // caller reads over HTTP is the same one the error report carries — one table, not two.
        // That flat bucket is what forced the UI to paint `error.message`: with nothing to branch
        // on, the raw sentence was all a screen had (hub#1102).
        _ => (
            StatusCode::BAD_REQUEST,
            erplora_runtime::error_registry::error_code_of(e),
        ),
    }
}

/// What a client is told when the failure is the hub's own plumbing (hub#1074).
///
/// Deliberately generic and stable: the `code` beside it is what a caller branches on and what the
/// shell translates (ADR-0055), and the detail belongs in the server log, not in a cashier's
/// dialog.
const REDACTED_MESSAGE: &str = "the request could not be completed — the hub recorded the details";

/// Does this sentence carry the database driver's own words?
///
/// Second line of defence behind [`may_reach_the_client`] (hub#1074). Several variants whose
/// message IS authored by us wrap a `DbError` inside it —
/// `Other("reset: la transacción falló, nada se borró: {e}")` is the pattern, and there are ~50
/// `Other` sites — so a per-variant rule alone would keep publishing `sqlx` through the very
/// variants we deliberately let speak. Matching the driver's signature covers those without
/// silencing the half of `Other` that says something a person can act on ("usuario no encontrado").
fn carries_driver_text(message: &str) -> bool {
    const MARKS: [&str; 4] = [
        "sqlx",
        "error returned from database",
        "PoolTimedOut",
        " at line ",
    ];
    MARKS.iter().any(|mark| message.contains(mark))
}

/// May the `Display` of this error travel to the caller as human text? (hub#1074)
///
/// The rule the PUBLIC door already applied (`public_door::domain_detail`), brought to the
/// AUTHENTICATED one — the door the UI, the assistant, the flows and the API all come through. A
/// pool error tells the cashier nothing and tells a stranger too much, and until this gate
/// `/api/command` answered a foreign-key violation with the engine, its driver, the table, the
/// constraint and an internal line number (ERPlora/pricing#29 painted exactly that in red in front
/// of a user).
///
/// The match is **exhaustive on purpose**: a new variant must not inherit either answer by falling
/// into a `_` arm — whoever adds it has to say which side of the door it stands on.
fn may_reach_the_client(e: &erplora_runtime::RuntimeError) -> bool {
    use erplora_runtime::RuntimeError as E;
    match e {
        // ── Plumbing. Each of these is the `Display` of a foreign library (sqlx, serde, wasmtime,
        // jsonschema, std::io) and none of it is anything a caller can act on.
        E::Io(_) | E::Manifest { .. } | E::Db(_) | E::Wasm(_) | E::Native(_) | E::Schema { .. } => {
            false
        }
        // hub#1209: the half-migrated hub the money backfill refuses to guess about. It is raised
        // by an ops subcommand and by the boot path, never inside a request, so it does not travel
        // through this door at all — and if it ever did, its sentence is an inventory of this
        // hub's own table.column names: internal shape a caller can neither act on nor need. Ops
        // reads it in the log and in the error registry, which is where it is aimed.
        E::MoneyUnitAmbiguous { .. } => false,
        // ── Sentences this hub, or a module, wrote ON PURPOSE for whoever reads them: they name
        // the operation, the permission, the app or the business rule that refused, which is what
        // the screen has to be able to say. What they must never do is smuggle driver text in, and
        // `carries_driver_text` is the net underneath them.
        E::ManifestUnknownField { .. }
        | E::CoreVersionTooOld { .. }
        | E::ManifestCoreFloorUnreadable { .. }
        | E::QueryNotFound(_)
        | E::ModuleNotInstalled { .. }
        | E::ModuleInactive { .. }
        | E::CommandNotFound(_)
        | E::InternalCommand(_)
        | E::MinAffectedRows { .. }
        | E::Domain { .. }
        | E::PermissionDenied(_)
        | E::RequiresElevation { .. }
        | E::CapabilityDenied { .. }
        | E::MissingDependency { .. }
        | E::HasDependents { .. }
        | E::DependencyTooOld { .. }
        | E::DependencyFloorUnreadable { .. }
        | E::DependencyCycle { .. }
        | E::EventLoop
        | E::EventNotDeclared { .. }
        | E::InvalidPayload { .. }
        // hub#1070 (#1185): the three shapes the core refuses a CONTRACT with — a field of a
        // payload, a certificate whose declared type is not the one served, a manifest that
        // breaks an installer rule. All three are authored by us for whoever has to fix them
        // (a user, a module author), and all three carry their own stable code.
        | E::InvalidField { .. }
        | E::CertificateTypeMismatch { .. }
        | E::ManifestRejected { .. }
        | E::MissingRequiredParam { .. }
        // hub#1173: un filtro que la lista no declara es el descuido de QUIEN LLAMA, en la misma
        // puerta que `MissingRequiredParam` — y `severity_of` ya los clasifica juntos. La frase la
        // escribimos nosotros y es justo la que arregla el fallo: nombra la query, el parámetro
        // rechazado y los aceptados. Redactarla dejaría a quien integra con un 400 y sin saber
        // qué parámetro escribió mal, que es peor que el bug que el error previene.
        | E::UnknownFilter { .. }
        | E::Notify(_)
        | E::Print(_)
        | E::Storage(_)
        | E::Certificate(_)
        | E::ReadUnavailable { .. }
        | E::ProtectsGuard { .. }
        | E::FiscalPrecondition { .. }
        | E::InvalidTaxId { .. }
        | E::DemoLocked { .. }
        | E::BusinessTaxIdFrozen { .. }
        | E::HubCountryFrozen { .. }
        | E::NotImplemented(_)
        | E::Other(_) => true,
    }
}

/// Status + body of the error envelope every authenticated door answers with.
///
/// Split out of [`err_response`] (hub#1074) so the redaction policy can be exercised variant by
/// variant without an HTTP round trip and without a database: what a client is allowed to read is
/// a security rule, and a rule that can only be tested through a fixture that happens to fail in
/// the right way is a rule with holes in its coverage.
pub(crate) fn error_payload(e: &erplora_runtime::RuntimeError) -> (StatusCode, Value) {
    use erplora_runtime::RuntimeError as E;
    let (status, code) = err_status_and_code(e);
    // hub#1074: the detail is not thrown away, it changes audience. Until here it travelled to the
    // client and left NO trace on the server; now it is the other way round.
    // hub#1074 + #1185: `InvalidField` is the one refusal whose `Display` is built FOR THE LOG —
    // «`hub.users`: field `name` required: the name is required». `name`, `field` and `reason` are
    // the contract, and they already travel as data below; putting them in front of the person
    // filling the form puts backticks and an internal door name on a screen, which is the exact
    // shape hub#1102 took off the till. So the sentence that travels is the authored `detail`, and
    // the structure stays structure.
    let detail = match e {
        E::InvalidField { detail, .. } => detail.clone(),
        _ => e.to_string(),
    };
    let message = if may_reach_the_client(e) && !carries_driver_text(&detail) {
        detail
    } else {
        tracing::error!(code = %code, detail = %detail, "response to the client redacted: the detail stays in this log (hub#1074)");
        REDACTED_MESSAGE.to_string()
    };
    let mut error = json!({ "code": code, "message": message });
    // hub#360: the missing permission travels as a FIELD, never parsed out of the message — it is
    // what the dialog names and what hub#361 re-checks. Only on the elevation branch: a flat
    // refusal must not look like an offer to elevate.
    if let E::RequiresElevation { permission } = e {
        error["permission"] = json!(permission);
    }
    // hub#1101: same rule — the apps that would break travel as a FIELD, never parsed out of the
    // sentence, because that list is what the confirmation dialog enumerates.
    if let E::HasDependents { dependents, .. } = e {
        error["dependents"] = json!(dependents);
    }
    // hub#1070: the field and the reason travel as data, so the UI translates by code and a
    // client never has to read the prose.
    if let E::InvalidField { field, reason, .. } = e {
        error["field"] = json!(field);
        error["reason"] = json!(reason);
    }
    if let E::ManifestRejected { at, .. } = e {
        error["at"] = json!(at);
    }
    // hub#1102: and the same rule again for the read a `required` preload could not resolve. The
    // shell translates the CODE (`read_unavailable`) and names the missing app from this field;
    // before it, the only place that query lived was inside an English sentence the till printed
    // verbatim on the Charge dialog.
    if let E::ReadUnavailable { query } = e {
        error["query"] = json!(query);
    }
    // hub#1102: the APP a refusal is about, for the refusals whose remedy names one — install it,
    // switch it back on, grant it a permission. Same rule as the fields above: the sentence that
    // names it («Falta la app Impuestos») must not be built by pulling backticks out of
    // «módulo no instalado: `taxes` (requerido por `sales.complete_sale`)».
    //
    // On `MissingDependency` the app that is missing is `dep`, NOT `module`: `module` is the one
    // being installed, and sending the owner after that one is sending them nowhere.
    match e {
        E::ModuleNotInstalled { module, .. }
        | E::ModuleInactive { module, .. }
        | E::CapabilityDenied { module, .. } => error["module"] = json!(module),
        E::MissingDependency { dep, .. } => error["module"] = json!(dep),
        _ => {}
    }
    // hub#1094: same rule again — the fields the schema refused. The Settings screen the shell
    // generates for ANY module swallowed this 422 (press «Save», nothing changes) precisely
    // because a sentence is all it got, and it will not parse one. The split happens at the
    // runtime, one function below the `format!` that wrote the detail. The key is ABSENT when the
    // refusal names no field (the ~25 doors that raise `InvalidPayload` by hand write prose): a
    // caller that keys on its presence must not read "this is about fields" into all of them.
    if let E::InvalidPayload { detail, .. } = &e {
        let fields = erplora_runtime::registry::invalid_payload_fields(detail);
        if !fields.is_empty() {
            error["fields"] = json!(fields);
        }
    }
    (status, json!({ "ok": false, "error": error }))
}

pub(crate) fn err_response(e: erplora_runtime::RuntimeError) -> Response {
    let (status, body) = error_payload(&e);
    (status, Json(body)).into_response()
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
pub(crate) fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// The same refusal, telling **"who are you"** apart from **"not you"** (hub#660): a valid session
/// with an insufficient role answers `403`, because re-authenticating as the same cashier would
/// never help. The body carries a **stable code** (`unauthorized` / `forbidden`) next to the
/// message, the shape of [`tenant_rejected`] and of the dead-letter doors (`outbox_admin`): the UI
/// branches on the code, never on prose (hub#1241). One implementation on purpose — two copies of
/// a refusal is how one ends up being the permissive one.
pub(crate) fn auth_rejected(e: auth::AuthError) -> Response {
    let (status, code) = if e.is_forbidden() {
        (StatusCode::FORBIDDEN, "forbidden")
    } else {
        (StatusCode::UNAUTHORIZED, "unauthorized")
    };
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": e.message() } })),
    )
        .into_response()
}

/// Query param de idioma para los endpoints localizables (ADR-0055). `?locale=es`; default `en`.
#[derive(serde::Deserialize)]
pub(crate) struct LocaleQuery {
    pub(crate) locale: Option<String>,
}

async fn navigation(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<LocaleQuery>,
) -> Response {
    let locale = q.locale.as_deref().unwrap_or("en");
    let rt = st.runtime.lock().await;
    let ctx = match auth::require_user_session(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx,
        Err(e) => return unauthorized(e),
    };
    let reg = rt.registry();
    let items: Vec<Value> = rt
        .navigation()
        .iter()
        // hub#1052: una pestaña con `permission` solo se sirve a quien la tiene. Antes no había
        // dónde declararlo, así que el módulo la pintaba para todos y el usuario descubría el
        // límite estrellándose contra un 403 — `flows` lo dice en su propio código: mandar al
        // cajero a revisar sus permisos «lo mandaría a un sitio al que no puede ir».
        //
        // El predicado es el MISMO que el de la puerta real (`permissions::has`), así que el menú
        // y el command no pueden discrepar sobre qué significa un permiso. Sin `permission` la
        // entrada es visible, como en todos los manifests publicados hasta hoy.
        .filter(|n| {
            n.nav
                .permission
                .as_deref()
                .is_none_or(|p| erplora_runtime::permissions::has(&ctx, p))
        })
        .map(|n| {
            let entry = reg.installed.iter().find(|m| m.id == n.module_id);
            let mod_fallback = entry
                .map(|m| m.name.as_str())
                .unwrap_or(n.module_id.as_str());
            json!({
                "module_id": n.module_id,
                // Nombre del módulo traducido (ADR-0055): lo usa el shell para el sidebar y las
                // tarjetas del dashboard (un ítem por módulo).
                "module_name": reg.module_name_localized(&n.module_id, mod_fallback, locale),
                // Versión INSTALADA (hub#935). Con ella el shell construye la url versionada del
                // bundle (`/modules/<id>/v/<version>/…`) sin depender del `module.json`, que es un
                // asset y sí puede llegar de una caché: si llegara atrasado, el shell pediría la url
                // de la versión vieja —cacheada— y volveríamos al fallo mudo que motivó la issue.
                // Esta respuesta va autenticada y ninguna caché la toca.
                "module_version": entry.map(|m| m.version.clone()),
                "id": n.nav.id,
                // Label de la pestaña traducido (ADR-0055): locale → en → label del manifest.
                "label": reg.nav_label_localized(&n.module_id, &n.nav.id, &n.nav.label, locale),
                "icon": n.nav.icon, "component": n.nav.component,
            })
        })
        .collect();
    // `active_modules` = módulos instalados **y activos** (hub#894). **Aditivo**: `ok`/`data` intactos.
    //
    // `data` es el menú, y por sí solo no distingue las dos cosas que producen el mismo array vacío:
    // un hub recién nacido y un hub con 12 módulos cuyo menú salió vacío de todas formas. La primera
    // es un hecho que merece pintarse («añade tu primera app»); la segunda no, y se pintaba igual —
    // un hub real de producción (12/12 según `/readyz`) le dijo a su dueña que no tenía apps y le
    // ofreció instalar las que ya tenía. Este número le da al shell contra qué comprobar la lista
    // vacía en vez de creérsela.
    //
    // Cuenta los **activos**, no los instalados, y la diferencia importa: un módulo que el admin
    // apagó a propósito NO se espera que aporte menú, así que contarlo convertiría un hub apagado a
    // conciencia en un falso «no he podido cargar tus apps». El denominador es lo que el hub espera
    // que aporte, no lo que tiene guardado.
    let active_modules = reg
        .installed
        .iter()
        .filter(|m| reg.is_active(&m.id))
        .count();
    Json(json!({ "ok": true, "data": items, "active_modules": active_modules })).into_response()
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
                // ADITIVO (hub#521): lo que el core NO entendió de su `module.json` y aun así
                // instaló. Vacío en un módulo que encaja con el contrato — que es lo normal. Es la
                // superficie CONSULTABLE del aviso: sin ella, «el hub lo ignora en silencio» se
                // arreglaría escribiendo el silencio en un log que nadie mira.
                "manifest_warnings": m.manifest_warnings,
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

/// Body of `POST /api/modules/:id/uninstall` (hub#1101). Optional in full: the historical call
/// sends nothing at all, and «nothing» has to keep meaning the SAFE answer.
#[derive(serde::Deserialize, Default)]
struct UninstallReq {
    /// «Other apps need this one — remove it anyway». Only the caller that was shown the list
    /// (the confirmation dialog of hub#773, or support driving the API on purpose) sends it.
    /// It opens the dependants gate and NOTHING else: the fiscal locks are not the owner's
    /// question and stay shut (ADR-0202 R2, ADR-0273 D5).
    #[serde(default)]
    force: bool,
}

async fn uninstall_module(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    body: Option<Json<UninstallReq>>,
) -> Response {
    let force = body.map(|Json(b)| b.force).unwrap_or_default();
    let mut rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let outcome = if force {
        rt.uninstall_forced(&id).await
    } else {
        rt.uninstall(&id).await
    };
    match outcome {
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
    let mut ctx = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(c) => c,
        Err(e) => return unauthorized(e),
    };
    // Entitlement-blocked module ids (hub#1175), stamped on the context so the runtime's own idea
    // of "available" — `hub.setup.status` reads it right next to `is_active` — cannot promise a
    // route the entitlement gate below is about to refuse for a DIFFERENT query. Same source as
    // `revalidation.blocked_modules` on `GET /api/entitlement` (`proxy_entitlement`): this hub's
    // installed ids against the last verified claims.
    let installed: Vec<String> = rt.modules().into_iter().map(|m| m.id).collect();
    if let Ok(revalidation) = st.entitlement.read() {
        ctx.blocked_modules = revalidation
            .blocked_modules(&installed, entitlement::now_unix())
            .into_iter()
            .collect();
    }
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
    if let Some(refusal) = device_trust_gate(&st, &rt, device_id).await {
        return refusal;
    }
    // Brute-force guard (hub#329): checked BEFORE verifying, so a locked identity stops leaking
    // the right/wrong signal an attacker is fishing for.
    if let Some(retry_after_secs) = st.login_throttle.locked_for(&req.name) {
        return too_many_attempts(retry_after_secs);
    }
    match rt.verify_pin(&req.name, &req.pin).await {
        Ok(Some(user)) => {
            st.login_throttle.record_success(&req.name);
            // Límite de dispositivos del plan (ADR-0154): lo aporta el estado de entitlement del
            // server (fail-open a 0 = ilimitado si el lock está envenenado o aún no hubo refresh).
            let max_devices = st.entitlement.read().map(|g| g.max_devices()).unwrap_or(0);
            mint_session(
                &rt,
                user,
                device_id,
                max_devices,
                &erplora_runtime::identity::Credential::pin(),
            )
            .await
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

/// `429` de la guarda de fuerza bruta, idéntico en las dos puertas de login local.
fn too_many_attempts(retry_after_secs: u64) -> Response {
    (
        StatusCode::TOO_MANY_REQUESTS,
        Json(json!({
            "ok": false,
            "error": "demasiados intentos fallidos: espera unos minutos",
            "code": "too_many_attempts",
            "retry_after_secs": retry_after_secs
        })),
    )
        .into_response()
}

/// El gate de **device-trust** (§2.9, hub#330), compartido por las dos credenciales locales.
///
/// Vive en una función y no duplicado en cada puerta porque una placa que se saltase este gate
/// sería, literalmente, la vuelta atrás de hub#330: el hub responde en la internet pública y una
/// tarjeta se clona con un Flipper Zero. `None` = puede pasar.
async fn device_trust_gate(
    st: &AppState,
    rt: &erplora_runtime::Runtime,
    device_id: Option<&str>,
) -> Option<Response> {
    if st.config.device_trust_enforce {
        // No `device_id`, no bypass (hub#330): the check used to sit in an `if let Some(..)` with
        // no `else`, so leaving the field out walked past the gate entirely. The hub lives on the
        // public internet, so an unidentified device is the shape of the attack, not an oversight.
        let Some(device_id) = device_id else {
            return Some(
                (
                    StatusCode::FORBIDDEN,
                    Json(json!({
                        "ok": false,
                        "error": "this client did not identify its device",
                        "code": "device_unidentified"
                    })),
                )
                    .into_response(),
            );
        };
        match rt.is_device_trusted(device_id).await {
            Ok(true) => {}
            Ok(false) => {
                // Demo hubs adopt the FIRST device that shows up (hub#630). A demo visitor has no
                // account, and an online cloud login is the only thing that otherwise earns a
                // device its trust — so without this the PIN door on a demo could never be opened
                // by anybody: the hub came up, the seeded `Demo` user was there, and every login
                // answered `device_untrusted` until the reaper destroyed it.
                //
                // First use, not "off". The gate stays enforced and only the empty case is
                // special: once a device is adopted, the next one is refused exactly as always, so
                // whoever opened the demo keeps it and somebody who later guesses the URL does not
                // walk into their session. `Registry::demo_hub` is sealed at boot from `HUB_DEMO`
                // and has no writer (ADR-0197 §4), so this cannot be turned on from outside.
                //
                // The rule itself lives in `device_mode::demo_would_adopt`, SHARED with the read
                // door that decides whether the pinpad is painted (hub#514): when the two drifted,
                // this branch became unreachable — no pinpad, no PIN submit, no adoption.
                let adopt = match device_mode::demo_would_adopt(st.config.demo, rt, device_id).await
                {
                    Ok(adopt) => adopt,
                    Err(e) => return Some(err_response(e)),
                };
                if !adopt {
                    return Some(
                        (
                            StatusCode::FORBIDDEN,
                            Json(json!({
                                "ok": false,
                                "error": "this device has not signed in with an account yet",
                                "code": "device_untrusted"
                            })),
                        )
                            .into_response(),
                    );
                }
                if let Err(e) = rt.trust_device(device_id, "Demo (first device)").await {
                    return Some(err_response(e));
                }
            }
            Err(e) => return Some(err_response(e)),
        }
    }
    None
}

#[derive(serde::Deserialize)]
struct BadgeReq {
    /// Lo que el lector escribió como ráfaga de teclado (o lo que se tecleó, para un iButton).
    badge: String,
    #[serde(default)]
    device_id: Option<String>,
}

/// Login local por **PLACA** → abre sesión. Body `{badge, device_id?}` → `{ok, token, user}`
/// (401 si falla). hub#658.
///
/// La placa resuelve la identidad ENTERA: sustituye al par (nombre, PIN) del pinpad, nunca al PIN
/// solo. Por eso este cuerpo no lleva nombre — y por eso la respuesta no dice nunca si la tarjeta
/// existe: un 401 igual para «esa placa no es de nadie» y «esa placa es de alguien dado de baja».
///
/// **Las tres barandillas del PIN se mantienen enteras**: el mismo gate de device-trust
/// ([`device_trust_gate`]), la misma guarda de fuerza bruta y el mismo límite de dispositivos del
/// plan. La guarda se cuenta contra el **índice** de la tarjeta y no contra un nombre —aquí no hay
/// nombre que teclear— y eso además la hace más precisa: bloquea la tarjeta que se está probando,
/// sin que nadie pueda dejar fuera a un compañero pasando cinco veces una tarjeta rota a su nombre.
async fn auth_badge(State(st): State<AppState>, Json(req): Json<BadgeReq>) -> Response {
    let rt = st.runtime.lock().await;
    let device_id = req
        .device_id
        .as_deref()
        .map(str::trim)
        .filter(|id| !id.is_empty());
    if let Some(refusal) = device_trust_gate(&st, &rt, device_id).await {
        return refusal;
    }
    // La clave del índice para poder acotar los intentos SIN guardar el número de la tarjeta en
    // ninguna estructura del servidor: lo que entra en el contador es el índice, que ya es lo que
    // la traza guarda.
    let throttle_key = match rt.badge_index_key().await {
        Ok(key) => format!(
            "badge:{}",
            erplora_runtime::identity::badge_index(&key, &req.badge)
        ),
        Err(e) => return err_response(e),
    };
    if let Some(retry_after_secs) = st.login_throttle.locked_for(&throttle_key) {
        return too_many_attempts(retry_after_secs);
    }
    match rt.verify_badge(&req.badge).await {
        Ok(Some(matched)) => {
            st.login_throttle.record_success(&throttle_key);
            let max_devices = st.entitlement.read().map(|g| g.max_devices()).unwrap_or(0);
            mint_session(
                &rt,
                matched.user,
                device_id,
                max_devices,
                &erplora_runtime::identity::Credential::badge(&matched.badge_index),
            )
            .await
        }
        Ok(None) => {
            st.login_throttle.record_failure(&throttle_key);
            (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": "placa no reconocida", "code": "badge_rejected" })),
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
    let user_agent = devices::user_agent_of(&headers).to_string();
    open_cloud_session(&st, &token, body.map(|value| value.0), None, &user_agent).await
}

/// Shared implementation for ordinary Cloud login and the shell courier.  Keeping the JWT gate,
/// membership check and local user linking in one function ensures the courier cannot create a
/// more privileged path than `POST /api/auth/cloud`.
async fn open_cloud_session(
    st: &AppState,
    token: &str,
    body: Option<CloudLoginReq>,
    cloud_tokens: Option<Value>,
    // The `User-Agent` of the login request: the name a device this hub has never seen is born with
    // (hub#494). It has to travel from the handler because this function sees no headers, and there
    // is nothing else in the request that says anything about the **device** — ADR-0257 made the id
    // opaque, and `name` in the body is the person.
    user_agent: &str,
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
            // El nombre por defecto (hub#494) sale del **User-Agent**, y solo cuenta si el hub no
            // conocía ya el dispositivo: `trust_device_with_default_name` lo escribe únicamente en
            // el INSERT. `name` —la persona— sigue yendo a `label`, que es lo que es: una pista de
            // quién entró la última vez, no el nombre de la tablet.
            if let Some(device_id) = device_id.as_deref() {
                let default_name = devices::default_device_name(user_agent);
                let _ = rt
                    .trust_device_with_default_name(device_id, &name, &default_name)
                    .await;
            }
            // Límite de dispositivos del plan (ADR-0154), como en el login por PIN.
            let max_devices = st.entitlement.read().map(|g| g.max_devices()).unwrap_or(0);
            mint_session_with_extra(
                &rt,
                user,
                device_id.as_deref(),
                max_devices,
                &erplora_runtime::identity::Credential::cloud(),
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
// `HeaderMap` va antes del `Json` a propósito: el extractor del cuerpo consume la petición y tiene
// que ser el último. Lo necesita el nombre por defecto del dispositivo (hub#494): esta puerta abre
// sesión igual que `/api/auth/cloud`, así que un login por el shell nativo no puede dejar la tablet
// sin nombre solo por haber entrado por aquí.
async fn auth_courier(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CourierReq>,
) -> Response {
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
    open_cloud_session(
        &st,
        &access,
        Some(login),
        Some(cloud_tokens),
        devices::user_agent_of(&headers),
    )
    .await
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
    credential: &erplora_runtime::identity::Credential,
) -> Response {
    mint_session_with_extra(rt, user, device_id, max_devices, credential, None).await
}

async fn mint_session_with_extra(
    rt: &erplora_runtime::Runtime,
    user: erplora_runtime::identity::HubUser,
    device_id: Option<&str>,
    max_devices: u32,
    // **Con qué se probó la identidad** (hub#658). Viaja hasta la fila de `hub_session` porque el
    // login es la mitad de la traza que contesta «alguien usó mi tarjeta»; la otra mitad la escribe
    // `_elevation_audit`.
    credential: &erplora_runtime::identity::Credential,
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
    match rt
        .create_session_with_credential(&user.id, ttl_secs, device_id, credential)
        .await
    {
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
mod incomplete_boot_report_tests {
    //! hub#571: un hub que arranca SIN alguno de sus módulos no puede ser un silencio.
    use super::incomplete_boot_event;

    #[test]
    fn the_report_names_every_module_that_could_not_be_mounted() {
        let event = incomplete_boot_event(&[
            ("sales".to_string(), "3.2.0".to_string()),
            ("taxes".to_string(), "1.4.0".to_string()),
        ]);

        assert_eq!(event.error_code, "module_boot_incomplete");
        assert_eq!(event.severity, erplora_runtime::error_registry::severity::UNEXPECTED);
        // Los módulos, con su versión, para que quien lo lea sepa QUÉ falta sin abrir el hub.
        assert_eq!(event.context["modules"][0]["module_id"], "sales");
        assert_eq!(event.context["modules"][0]["version"], "3.2.0");
        assert_eq!(event.context["modules"][1]["module_id"], "taxes");
        assert_eq!(event.context["count"], 2);
        assert!(event.message.contains("sales"), "{}", event.message);
        assert!(event.message.contains("taxes"), "{}", event.message);
    }

    /// El evento es del HUB, no de un módulo: no hay un culpable al que colgárselo — lo que falló
    /// es el arranque, y atribuirlo al primero de la lista mandaría a mirar donde no es.
    #[test]
    fn the_failure_belongs_to_the_hub_and_not_to_one_of_the_modules() {
        let event = incomplete_boot_event(&[("sales".to_string(), "3.2.0".to_string())]);
        assert_eq!(event.source, erplora_runtime::error_registry::source::HUB);
        assert_eq!(event.module_id, None);
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

    /// hub#1094: the generic Settings screen swallowed the 422 — «Save» came back
    /// `invalid_payload` and nothing on screen changed. It cannot mark the offending controls
    /// while the only thing it gets is a sentence, and parsing the sentence is exactly what this
    /// house does not do: the list travels as a FIELD, like `permission` (hub#360) and
    /// `dependents` (hub#1101) already do.
    #[tokio::test]
    async fn invalid_payload_names_the_offending_fields_as_a_field_of_the_envelope() {
        let (status, body) = shape(RuntimeError::InvalidPayload {
            name: "kitchen.settings.update".into(),
            detail: "/auto_bump_delay_seconds: null is not of type \"integer\"; \
                     /default_order_type: \"\" is not one of [\"dine_in\"]"
                .into(),
        })
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(body["error"]["code"], "invalid_payload");
        assert_eq!(
            body["error"]["fields"],
            serde_json::json!(["auto_bump_delay_seconds", "default_order_type"]),
        );
    }

    /// The other refusals must NOT grow the field: a caller that keys on its presence would read
    /// «this one is about fields» into every hand-written rejection in the runtime.
    #[tokio::test]
    async fn a_refusal_that_names_no_field_carries_no_fields_key() {
        let (_, body) = shape(RuntimeError::InvalidPayload {
            name: "hub.device_mode.set".into(),
            detail: "modo de dispositivo desconocido: `kiosko`".into(),
        })
        .await;
        assert!(
            body["error"].get("fields").is_none(),
            "una negativa sin campos no debe inventarse la clave, got {body}"
        );
    }
}

#[cfg(test)]
mod error_redaction_tests {
    //! hub#1074 / hub#1102 — WHAT a client is allowed to read when the hub fails.
    //!
    //! The HTTP end of this lives in `tests/error_redaction_door.rs` (a real foreign-key violation
    //! through `/api/command`). Here the policy is pinned variant by variant, because the door test
    //! can only reach the variants a fixture happens to be able to provoke — and a security rule
    //! whose coverage depends on that has holes exactly where nobody looks.
    use super::{error_payload, REDACTED_MESSAGE};
    use erplora_runtime::RuntimeError;

    fn error_of(e: RuntimeError) -> serde_json::Value {
        error_payload(&e).1["error"].clone()
    }

    /// Plumbing that wraps a foreign library never speaks to a client. (The `Db` variant of the
    /// same family needs a real `sqlx::Error` to build, so it is pinned where it actually happens:
    /// `tests/error_redaction_door.rs` provokes a genuine foreign-key violation over
    /// `/api/command` and asserts the driver's words never come back.)
    #[test]
    fn plumbing_is_redacted_and_keeps_its_stable_code() {
        let e = RuntimeError::Io(std::io::Error::other("/srv/erplora/modules/sales: permission denied"));

        let error = error_of(e);
        assert_eq!(error["message"], REDACTED_MESSAGE);
        assert_eq!(error["code"], "io");
    }

    /// The net under the variants we DO let speak: `Other` is a grab-bag of ~50 sites, half of
    /// which wrap a `DbError` inside an otherwise perfectly readable sentence
    /// (`reset: la transacción falló, nada se borró: {e}`). Per-variant rules alone would keep
    /// publishing the driver through them.
    #[test]
    fn driver_text_smuggled_inside_an_authored_sentence_is_redacted_too() {
        let e = RuntimeError::Other(
            "reset: la transacción falló, nada se borró: sqlx: error returned from database".into(),
        );
        assert_eq!(error_of(e)["message"], REDACTED_MESSAGE);
    }

    /// …and the other half of `Other` still says something a person can act on.
    #[test]
    fn an_authored_sentence_without_driver_text_still_reaches_the_client() {
        let e = RuntimeError::Other("usuario no encontrado".into());
        assert_eq!(error_of(e)["message"], "usuario no encontrado");
    }

    /// ADR-0205 / hub#139: the one channel a module has to say something true about the request.
    /// Redacting this would silence the modules, which is the opposite of the point.
    #[test]
    fn a_module_domain_rejection_is_never_redacted() {
        let e = RuntimeError::Domain {
            code: "inventory.insufficient_stock".into(),
            message: "Not enough stock".into(),
        };
        let error = error_of(e);
        assert_eq!(error["code"], "inventory.insufficient_stock");
        assert_eq!(error["message"], "Not enough stock");
    }

    /// hub#1102: the cashier's dialog printed `required read \`taxes.rules.list\` is unavailable —
    /// the command was aborted (hub#701)`. The code is what the shell translates and the query is
    /// a field it reads; neither the backticks nor the issue number belong on a till.
    #[test]
    fn an_unavailable_required_read_carries_a_code_and_the_query_as_a_field() {
        let error = error_of(RuntimeError::ReadUnavailable {
            query: "taxes.rules.list".into(),
        });

        assert_eq!(error["code"], "read_unavailable");
        assert_eq!(error["query"], "taxes.rules.list");
        assert!(
            !error["message"].as_str().unwrap_or_default().contains("hub#"),
            "an issue number is not something a cashier can act on: {error}"
        );
    }

    /// A WASM trap is the hub's plumbing, not the module talking: a handler that wants to say
    /// something to the caller returns `Output.error`, which arrives as `Domain`.
    #[test]
    fn a_wasm_trap_is_plumbing() {
        assert_eq!(
            error_of(RuntimeError::Wasm("unreachable executed at 0x4f2".into()))["message"],
            REDACTED_MESSAGE
        );
    }

    /// The three variants #1185 added while this branch was open (`InvalidField`,
    /// `CertificateTypeMismatch`, `ManifestRejected`). The exhaustive `match` of
    /// `may_reach_the_client` made the compiler ask which side of the door each stands on; this
    /// pins the ANSWER, because «it compiles» only proves somebody chose, not that they chose
    /// right. All three are authored by us for whoever has to fix them, and all three carry a
    /// code and the offending element as data.
    #[test]
    fn the_contract_refusals_of_1185_reach_the_client_with_their_code_and_their_data() {
        let field = error_of(RuntimeError::InvalidField {
            name: "hub.users".into(),
            field: "name".into(),
            reason: "required".into(),
            detail: "the name is required".into(),
        });
        assert_eq!(field["code"], "invalid_field");
        assert_eq!(field["field"], "name");
        assert_eq!(field["reason"], "required");
        assert_eq!(field["message"], "the name is required");

        let manifest = error_of(RuntimeError::ManifestRejected {
            module: "kitchen".into(),
            at: "roles[0]".into(),
            code: "role_grants_admin".into(),
            detail: "a module never grants administration of the hub".into(),
        });
        assert_eq!(manifest["code"], "role_grants_admin");
        assert_eq!(manifest["at"], "roles[0]");
        assert_ne!(manifest["message"], REDACTED_MESSAGE);

        let cert = error_of(RuntimeError::CertificateTypeMismatch {
            declared: "seal".into(),
            served: "representative".into(),
        });
        assert_eq!(cert["code"], "certificate_type_mismatch");
        assert_ne!(cert["message"], REDACTED_MESSAGE);
    }

    /// …and the net still runs under them. `InvalidField.detail` is authored today, but the whole
    /// point of `carries_driver_text` is that «authored» is a habit, not a guarantee: the day a
    /// refusal interpolates a `DbError` into its detail, the driver must still not come out.
    #[test]
    fn a_contract_refusal_that_smuggles_driver_text_is_redacted_anyway() {
        let error = error_of(RuntimeError::InvalidField {
            name: "hub.users".into(),
            field: "name".into(),
            reason: "duplicate".into(),
            detail: "could not check: sqlx: error returned from database".into(),
        });
        assert_eq!(error["message"], REDACTED_MESSAGE);
        // The code and the data survive: what is redacted is the PROSE, never the contract.
        assert_eq!(error["code"], "invalid_field");
        assert_eq!(error["field"], "name");
    }

    /// The refusals a screen ACTS on keep their sentence AND their field. Redacting by default and
    /// exempting case by case would have swallowed these the day someone added a variant.
    #[test]
    fn refusals_the_screen_acts_on_keep_their_sentence() {
        let elevation = error_of(RuntimeError::RequiresElevation {
            permission: "sales.refund".into(),
        });
        assert_eq!(elevation["permission"], "sales.refund");
        assert!(
            elevation["message"].as_str().unwrap_or_default().contains("sales.refund"),
            "{elevation}"
        );

        let dependents = error_of(RuntimeError::HasDependents {
            module: "taxes".into(),
            dependents: vec!["sales".into(), "invoicing".into()],
        });
        assert_eq!(dependents["code"], "has_dependents");
        assert_eq!(dependents["dependents"][0], "sales");
        assert!(
            dependents["message"].as_str().unwrap_or_default().contains("sales"),
            "{dependents}"
        );
    }
}

#[cfg(test)]
mod error_field_tests {
    //! hub#1102 — the app an error is ABOUT travels as a field, never inside the sentence.
    //!
    //! Same rule as `permission` (hub#360) and `dependents` (hub#1101), for the same reason: the
    //! screen names the app («Falta la app Impuestos»), and the only way to name it from a message
    //! like «módulo no instalado: `taxes` (requerido por `sales.complete_sale`)» is to parse
    //! backticks out of prose — which is how a screen silently stops naming anything.
    use super::error_payload;
    use erplora_runtime::RuntimeError;

    fn error_of(e: RuntimeError) -> serde_json::Value {
        error_payload(&e).1["error"].clone()
    }

    #[test]
    fn a_missing_module_names_it_as_a_field() {
        let error = error_of(RuntimeError::ModuleNotInstalled {
            module: "taxes".into(),
            operation: "taxes.rules.list".into(),
        });
        assert_eq!(error["code"], "module_not_installed");
        assert_eq!(error["module"], "taxes");
    }

    #[test]
    fn a_switched_off_module_names_it_as_a_field() {
        let error = error_of(RuntimeError::ModuleInactive {
            module: "taxes".into(),
            operation: "taxes.rules.list".into(),
        });
        assert_eq!(error["code"], "module_inactive");
        assert_eq!(error["module"], "taxes");
    }

    /// The install-time twin: the app that is MISSING is `dep`, not the one being installed — that
    /// is the one the sentence has to send the owner after.
    #[test]
    fn an_unsatisfied_dependency_names_the_app_that_is_missing() {
        let error = error_of(RuntimeError::MissingDependency {
            module: "sales".into(),
            dep: "taxes".into(),
        });
        assert_eq!(error["code"], "missing_dependency");
        assert_eq!(error["module"], "taxes");
    }
}
