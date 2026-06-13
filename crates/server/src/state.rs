//! Estado compartido del server: el runtime (tras un lock), el canal de eventos para WS,
//! y la configuración de despliegue (hub_id + Cloud Portal + cache de módulos).
use std::path::PathBuf;
use std::sync::{Arc, RwLock};

use erplora_runtime::{EventSink, Runtime};
use erplora_vector::VectorStore;
use serde_json::{json, Value as Json};
use tokio::sync::{broadcast, Mutex};

/// Índice vectorial compartido para el routing de tools (§9.2b) y la ingestión de embeddings de
/// módulos al instalar (§9.6). `None` = no hay índice → el asistente degrada a "todos los tools"
/// (§9.5). Es un trait object para no acoplar el server a SQLite vs pgvector.
pub type SharedVectorStore = Arc<dyn VectorStore + Send + Sync>;

/// Frame que se reenvía tal cual a los clientes WebSocket (ya serializado como JSON `Value`).
///
/// Los eventos del runtime se publican con la forma `{"name":…, "payload":…}` (compat con el
/// `EventSink` previo); la instalación de módulos publica el frame exacto que espera el
/// frontend: `{"type":"module.installed","module_id":"…"}`.
pub type WsEvent = Json;

/// Implementa `EventSink` del runtime publicando en un canal broadcast (→ WebSocket).
#[derive(Debug)]
pub struct BroadcastSink {
    tx: broadcast::Sender<WsEvent>,
}

impl EventSink for BroadcastSink {
    fn emit(&self, event: &str, payload: &Json) {
        // Si no hay suscriptores, `send` falla; lo ignoramos a propósito.
        let _ = self.tx.send(json!({ "name": event, "payload": payload }));
    }
}

/// Modo de autenticación del server (ARQUITECTURA.md §2.3/§2.9):
///  - `Dev`: confía en cabeceras `X-User-Id`/`X-Permissions` (desarrollo local, sin Cloud).
///  - `Session`: identidad LOCAL real. El login (PIN o JWT cloud) abre una **sesión server-side**
///    (`hub_session`); cada petición lleva `X-Hub-Session` y el runtime resuelve el `hub_user` y
///    sus permisos por rol. Se activa con `HUB_AUTH=session`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AuthMode {
    Dev,
    Session,
}

/// Configuración de despliegue del hub (ARQUITECTURA.md §2.3; decisiones del humano):
///  - `hub_id`: lo inyecta el despliegue vía env `HUB_ID` (sin selector de hub).
///  - `cloud_base_url`: el Cloud Portal contra el que se resuelven marketplace + asistente.
///  - `module_cache`: raíz local donde `erplora-source` descomprime los módulos descargados.
///  - `auth_mode` + `jwt_public_key`: ver [`AuthMode`]. La clave pública (PEM) la resuelve
///    `main` al arrancar (env `HUB_JWT_PUBLIC_KEY` o `GET /api/v1/auth/public-key/` del Cloud).
#[derive(Clone, Debug)]
pub struct HubConfig {
    pub hub_id: String,
    pub cloud_base_url: String,
    pub module_cache: PathBuf,
    pub auth_mode: AuthMode,
    pub jwt_public_key: Option<String>,
    /// Credencial de **máquina** del hub (`cloud_api_token`), enviada como `X-Hub-Token` para
    /// hablar con el Cloud en endpoints hub-scoped (marketplace, entitlement, asistente, install)
    /// **sin** usuario logueado. La inyecta el despliegue (env `HUB_CLOUD_API_TOKEN`, ECS) o la
    /// persiste el shell Tauri tras enrolar (`GET /api/v1/hub/device/enroll/`). Es un **secreto**:
    /// vive solo aquí (runtime), nunca en el navegador. `None` en dev/local sin enrolar → se cae al
    /// JWT del usuario activo. Ver ARQUITECTURA.md §2.3.
    pub cloud_api_token: Option<String>,
    /// **Device-trust** del login por PIN (§2.9, hub#15). Si está activo (`HUB_DEVICE_TRUST=enforce`)
    /// y el cliente manda `device_id`, el login por PIN se rechaza salvo que el dispositivo haya sido
    /// marcado de confianza (tras un login online cloud previo). Por defecto **desactivado** para no
    /// romper dev/local: un cliente que no manda `device_id` nunca se ve afectado.
    /// TODO(humano): el host (Tauri/web) debe aportar un `device_id` estable; cerrar el diseño en §2.9.
    pub device_trust_enforce: bool,
}

/// UUID fijo de desarrollo si no se inyecta `HUB_ID` (decisión tomada — flag para humano).
pub const DEV_HUB_ID: &str = "00000000-0000-0000-0000-000000000001";

impl HubConfig {
    /// Lee la configuración del entorno con defaults de desarrollo locales.
    pub fn from_env() -> Self {
        let hub_id = std::env::var("HUB_ID").unwrap_or_else(|_| DEV_HUB_ID.to_string());
        let cloud_base_url =
            std::env::var("HUB_CLOUD_API_URL").unwrap_or_else(|_| "https://erplora.com".to_string());
        let module_cache = std::env::var("HUB_MODULE_CACHE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| std::env::temp_dir().join("erplora-modules"));
        let auth_mode = match std::env::var("HUB_AUTH").as_deref() {
            Ok("session") => AuthMode::Session,
            _ => AuthMode::Dev,
        };
        // Inyección directa de la clave (PEM) por entorno; si no, `main` la trae del Cloud.
        let jwt_public_key = std::env::var("HUB_JWT_PUBLIC_KEY").ok().filter(|s| !s.trim().is_empty());
        // Token de máquina (ECS lo inyecta como `HUB_CLOUD_API_TOKEN`; Tauri lo setea tras enrolar).
        let cloud_api_token =
            std::env::var("HUB_CLOUD_API_TOKEN").ok().filter(|s| !s.trim().is_empty());
        let device_trust_enforce =
            matches!(std::env::var("HUB_DEVICE_TRUST").as_deref(), Ok("enforce"));
        Self {
            hub_id,
            cloud_base_url,
            module_cache,
            auth_mode,
            jwt_public_key,
            cloud_api_token,
            device_trust_enforce,
        }
    }
}

/// Celda compartida del **token de máquina** (`cloud_api_token`). Mutable en vivo: el shell Tauri
/// la actualiza tras enrolar/rotar y el runtime embebido toma el token nuevo **sin reiniciar la
/// app** (`auth::machine_auth` la lee en cada petición). En ECS basta el valor inicial del env.
pub type MachineToken = Arc<RwLock<Option<String>>>;

/// Estado de la app Axum. El runtime no es `Sync` para mutación, así que va tras un `Mutex`;
/// para 1–30 usuarios por hub (ARQUITECTURA.md §7.5) es más que suficiente.
///
/// **Dos modos de topología** (ADR-0005):
///  - **single-tenant (N=1)** — `tenants = None`: hay UN runtime (`runtime`), el del hub/org del
///    despliegue. Es el modo actual (un contenedor ECS por hub, o local Tauri). Todas las
///    peticiones usan ese runtime. **Comportamiento sin cambios.**
///  - **cloud compartido (N orgs)** — `tenants = Some(router)`: el proceso sirve **N** orgs; el
///    runtime de cada petición se resuelve por su `hub_id` vía el [`TenantRouter`] (un pool por
///    org). El campo `runtime` sigue existiendo como **fallback/bootstrap** (tablas de sistema,
///    arranque), pero el camino de datos va por el router. Ver [`AppState::runtime_for`].
#[derive(Clone)]
pub struct AppState {
    pub runtime: Arc<Mutex<Runtime>>,
    pub events: broadcast::Sender<WsEvent>,
    pub config: HubConfig,
    /// Token de máquina **vivo** (hot-reload). Se siembra del `config.cloud_api_token` o de una
    /// celda externa (shell Tauri). Léelo con [`AppState::machine_token`].
    pub machine_token: MachineToken,
    /// Cliente HTTP async (rustls) compartido para hablar con el Cloud (descargas + proxy SSE).
    pub http: reqwest::Client,
    /// Gateway multi-tenant (ADR-0005, hub#24). `None` = modo single-tenant actual (N=1); `Some` =
    /// tier "cloud compartido" (N orgs, un pool por org). Aditivo: no rompe el modo single-tenant.
    pub tenants: Option<Arc<crate::tenant::TenantRouter>>,
    /// Índice vectorial para routing de tools (§9.2b) + ingestión de embeddings (§9.6). `None` =
    /// sin índice (degradación §9.5: el asistente manda todos los tools). Lo siembra `serve()`.
    pub vector: Option<SharedVectorStore>,
}

impl AppState {
    /// Crea el estado y conecta el `EventSink` del runtime al canal broadcast.
    pub fn new(runtime: Runtime) -> Self {
        Self::with_config(runtime, HubConfig::from_env())
    }

    /// Variante con config explícita (tests / arranque controlado). Crea la celda del token de
    /// máquina sembrada con `config.cloud_api_token`.
    pub fn with_config(runtime: Runtime, config: HubConfig) -> Self {
        let cell = Arc::new(RwLock::new(config.cloud_api_token.clone()));
        Self::with_config_cell(runtime, config, cell)
    }

    /// Como [`with_config`](Self::with_config) pero con una **celda de token externa** compartida
    /// (el shell Tauri la conserva para actualizarla en caliente tras enrolar/rotar).
    pub fn with_config_cell(mut runtime: Runtime, config: HubConfig, machine_token: MachineToken) -> Self {
        let (tx, _rx) = broadcast::channel::<WsEvent>(256);
        let sink = Arc::new(BroadcastSink { tx: tx.clone() });
        runtime.set_event_sink(sink);
        Self {
            runtime: Arc::new(Mutex::new(runtime)),
            events: tx,
            config,
            machine_token,
            http: reqwest::Client::new(),
            tenants: None,
            vector: None,
        }
    }

    /// Adjunta el índice vectorial (routing §9.2b + ingestión §9.6). Aditivo: sin él, el asistente
    /// degrada a "todos los tools" (§9.5).
    pub fn with_vector(mut self, store: SharedVectorStore) -> Self {
        self.vector = Some(store);
        self
    }

    /// Activa el modo **cloud compartido** (ADR-0005): adjunta el gateway multi-tenant. A partir de
    /// aquí, [`runtime_for`](Self::runtime_for) resuelve el runtime por org. Aditivo: el `runtime`
    /// single-tenant sigue ahí como fallback de bootstrap.
    pub fn with_tenants(mut self, router: Arc<crate::tenant::TenantRouter>) -> Self {
        self.tenants = Some(router);
        self
    }

    /// Resuelve el [`Runtime`] a usar para esta petición:
    ///  - **single-tenant** (`tenants = None`): siempre el `runtime` del despliegue (modo actual).
    ///  - **cloud compartido** (`tenants = Some`): el runtime de la org dueña del `hub_id` de la
    ///    petición, vía el [`TenantRouter`]. Si el `hub_id` no mapea a ninguna org, **se rechaza**
    ///    (`TenantError::UnknownOrg`) — un token de la org A no puede resolver el pool de la B.
    ///
    /// El `hub_id` viene de la auth ya existente (`X-Hub-Id` inyectado por el despliegue, no
    /// spoofable; ver `auth.rs`). La autoridad sigue **server-side**: el gate de permisos + el
    /// scoping `hub_id` los aplica el `Runtime` resuelto en `execute_query`/`execute_command`.
    pub async fn runtime_for(
        &self,
        hub_id: &str,
    ) -> Result<Arc<Mutex<Runtime>>, crate::tenant::TenantError> {
        match &self.tenants {
            Some(router) => router.resolve_runtime(hub_id).await,
            None => Ok(self.runtime.clone()),
        }
    }

    /// Lee el token de máquina vivo (clona). `None` si el hub no está enrolado.
    pub fn machine_token(&self) -> Option<String> {
        self.machine_token.read().ok().and_then(|g| g.clone())
    }

    /// Publica un frame WS crudo (lo usa el flujo de instalación → `module.installed`).
    pub fn broadcast(&self, frame: Json) {
        let _ = self.events.send(frame);
    }
}
