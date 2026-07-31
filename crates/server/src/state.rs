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
///    sus permisos por rol. Es el modo de **producción** y el **default** (fail-closed).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AuthMode {
    Dev,
    Session,
}

/// Variable de entorno que selecciona el [`AuthMode`].
pub const AUTH_MODE_ENV: &str = "HUB_AUTH";

/// Resuelve el [`AuthMode`] desde el valor crudo de `HUB_AUTH` (**fail-closed**, hub#241).
///
/// El default era `Dev`: un despliegue que olvidara la variable arrancaba **sin autenticación**
/// (el navegador dictaba `X-User-Id`/`X-Permissions`) y nadie se enteraba, porque todo "funcionaba".
/// Un fallo de configuración no puede abrir el hub: sin variable → [`AuthMode::Session`]
/// (producción/Cloud). El modo de desarrollo se pide **explícitamente** con `HUB_AUTH=dev`.
///
/// Un valor desconocido también cae a `Session` con un aviso: un typo (`HUB_AUTH=develop`) no
/// puede degradar la seguridad del hub.
pub fn parse_auth_mode(raw: Option<&str>) -> AuthMode {
    match raw.map(str::trim) {
        Some("dev") => AuthMode::Dev,
        Some("session") | None => AuthMode::Session,
        Some(other) => {
            eprintln!(
                "auth: {AUTH_MODE_ENV}=`{other}` no es un modo conocido (`dev`|`session`) → \
                 se usa `session` (fail-closed)"
            );
            AuthMode::Session
        }
    }
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
    /// Raíz de la carpeta `media/` del hub: path por defecto de TODOS los ficheros (adjuntos de
    /// módulos, registros `_logs/`, actividad `_system/`). La navega la pantalla /files
    /// (`crate::media`). La inyecta el despliegue vía env `HUB_MEDIA_DIR`; default `./media`
    /// (relativo al CWD del proceso), creado de forma perezosa al primer acceso. En cloud (S3) el
    /// listado de objetos es follow-up del humano (igual que documentos en `system.rs`).
    pub media_dir: PathBuf,
    /// **Device-trust** del login por PIN (§2.9, hub#15). Si está activo (`HUB_DEVICE_TRUST=enforce`)
    /// y el cliente manda `device_id`, el login por PIN se rechaza salvo que el dispositivo haya sido
    /// marcado de confianza (tras un login online cloud previo). Por defecto **desactivado** para no
    /// romper dev/local: un cliente que no manda `device_id` nunca se ve afectado.
    /// TODO(humano): el host (Tauri/web) debe aportar un `device_id` estable; cerrar el diseño en §2.9.
    pub device_trust_enforce: bool,
    /// **Sector / tipo de negocio** del hub (`hosteleria`|`retail`|`gestoria`|`rrhh`|`belleza`|`general`), lo
    /// inyecta el despliegue vía env `HUB_SECTOR` (hermano de `HUB_LANGUAGE`/`HUB_CURRENCY`). Lo
    /// expone `GET /api/hub/context` para que el dashboard derive el preset "Recomendado" de widgets
    /// (ADR-0054). `None` = sector no determinable → el board degrada (preset vacío, el usuario activa
    /// widgets a mano). El Cloud captura el tipo de negocio en el onboarding y lo traduce a este env en
    /// la inyección ECS (`aws.py::BUSINESS_TYPE_TO_SECTOR`, ADR-0071); `belleza` = preset del vertical
    /// servicios/peluquería. El sector NO se persiste en el modelo `Hub` (vive en
    /// `pending_metadata['business_type']`): este env es la fuente del contrato runtime↔Cloud.
    pub sector: Option<String>,
}

/// UUID fijo de desarrollo si no se inyecta `HUB_ID` (decisión tomada — flag para humano).
pub const DEV_HUB_ID: &str = "00000000-0000-0000-0000-000000000001";

impl HubConfig {
    /// Lee la configuración del entorno. El [`AuthMode`] sale de `HUB_AUTH` **fail-closed**
    /// (sin variable → `Session`, ver [`parse_auth_mode`]).
    pub fn from_env() -> Self {
        // Fail-closed (hub#241): sin `HUB_AUTH` se arranca en modo producción (`Session`).
        let raw_auth = std::env::var(AUTH_MODE_ENV).ok();
        Self::from_env_with_auth(parse_auth_mode(raw_auth.as_deref()))
    }

    /// Como [`from_env`](Self::from_env) pero con el [`AuthMode`] **explícito**. Es la vía por la
    /// que un test (o un arranque controlado) pide el modo `Dev` sin depender de una variable de
    /// proceso compartida: desde hub#241 el default del entorno es `Session` (fail-closed), así
    /// que el modo permisivo hay que pedirlo a propósito, también en los tests.
    pub fn from_env_with_auth(auth_mode: AuthMode) -> Self {
        let hub_id = std::env::var("HUB_ID").unwrap_or_else(|_| DEV_HUB_ID.to_string());
        let cloud_base_url = std::env::var("HUB_CLOUD_API_URL")
            .unwrap_or_else(|_| "https://erplora.com".to_string());
        let module_cache = std::env::var("HUB_MODULE_CACHE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| std::env::temp_dir().join("erplora-modules"));
        // Inyección directa de la clave (PEM) por entorno; si no, `main` la trae del Cloud.
        let jwt_public_key = std::env::var("HUB_JWT_PUBLIC_KEY")
            .ok()
            .filter(|s| !s.trim().is_empty());
        // Token de máquina (ECS lo inyecta como `HUB_CLOUD_API_TOKEN`; Tauri lo setea tras enrolar).
        let cloud_api_token = std::env::var("HUB_CLOUD_API_TOKEN")
            .ok()
            .filter(|s| !s.trim().is_empty());
        let device_trust_enforce =
            matches!(std::env::var("HUB_DEVICE_TRUST").as_deref(), Ok("enforce"));
        // Sector / tipo de negocio del hub (preset "Recomendado" del dashboard, ADR-0054). Vacío o
        // ausente → `None` (degradación elegante; el board sigue funcionando sin preset).
        let sector = std::env::var("HUB_SECTOR")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        // Carpeta media del hub (logs `_logs/`, perfiles, export/import…). Por defecto `./media`;
        // el despliegue la fija explícitamente con `HUB_MEDIA_DIR`. En Hub Cloud (ADR-0154) los
        // ficheros de módulos viven en Object Storage vía el Cloud; `media_dir` es scratch local.
        let media_dir = std::env::var("HUB_MEDIA_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("media"));
        Self {
            hub_id,
            cloud_base_url,
            module_cache,
            auth_mode,
            jwt_public_key,
            cloud_api_token,
            device_trust_enforce,
            media_dir,
            sector,
        }
    }
}

/// Celda compartida del **token de máquina** (`cloud_api_token`). Mutable en vivo: el shell Tauri
/// la actualiza tras enrolar/rotar y el runtime embebido toma el token nuevo **sin reiniciar la
/// app** (`auth::machine_auth` la lee en cada petición). En ECS basta el valor inicial del env.
pub type MachineToken = Arc<RwLock<Option<String>>>;

/// `hub_id` vivo de la máquina. Durante el primer arranque Tauri nace con [`DEV_HUB_ID`] y, tras
/// registrar el `device_id` en el Cloud, adopta el UUID real en la misma operación que el token.
/// En Cloud ya viene fijado por el despliegue y la celda no cambia.
pub type HubId = Arc<RwLock<String>>;

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
    /// Identidad de Hub **viva**. Token e id se actualizan juntos al completar el registro de la
    /// máquina, evitando firmar una llamada con el token nuevo y el UUID placeholder anterior.
    pub hub_id: HubId,
    /// Cliente HTTP async (rustls) compartido para hablar con el Cloud (descargas + proxy SSE).
    pub http: reqwest::Client,
    /// Gateway multi-tenant (ADR-0005, hub#24). `None` = modo single-tenant actual (N=1); `Some` =
    /// tier "cloud compartido" (N orgs, un pool por org). Aditivo: no rompe el modo single-tenant.
    pub tenants: Option<Arc<crate::tenant::TenantRouter>>,
    /// Índice vectorial para routing de tools (§9.2b) + ingestión de embeddings (§9.6). `None` =
    /// sin índice (degradación §9.5: el asistente manda todos los tools). Lo siembra `serve()`.
    pub vector: Option<SharedVectorStore>,
    /// Estado de la **revalidación híbrida del entitlement** (módulos de pago): lo escribe el job
    /// periódico de `serve()` y lo leen el gate de `query`/`command` y el proxy `/api/entitlement`.
    /// Estado inicial = fail-open (nada bloqueado). Ver `crate::entitlement`.
    pub entitlement: crate::entitlement::SharedRevalidation,
}

impl AppState {
    /// Crea el estado y conecta el `EventSink` del runtime al canal broadcast.
    pub fn new(runtime: Runtime) -> Self {
        Self::with_config(runtime, HubConfig::from_env())
    }

    /// Variante con config explícita (tests / arranque controlado). Crea la celda del token de
    /// máquina sembrada con `config.cloud_api_token`.
    pub fn with_config(runtime: Runtime, config: HubConfig) -> Self {
        let token = Arc::new(RwLock::new(config.cloud_api_token.clone()));
        let hub_id = Arc::new(RwLock::new(config.hub_id.clone()));
        Self::with_config_cells(runtime, config, token, hub_id)
    }

    /// Como [`with_config`](Self::with_config) pero con una **celda de token externa** compartida
    /// (el shell Tauri la conserva para actualizarla en caliente tras enrolar/rotar).
    pub fn with_config_cell(
        runtime: Runtime,
        config: HubConfig,
        machine_token: MachineToken,
    ) -> Self {
        let hub_id = Arc::new(RwLock::new(config.hub_id.clone()));
        Self::with_config_cells(runtime, config, machine_token, hub_id)
    }

    /// Variante completa para hosts embebidos: comparte tanto el token como el `hub_id` vivo.
    /// El shell los adopta de forma atómica desde la perspectiva del flujo de bootstrap.
    pub fn with_config_cells(
        mut runtime: Runtime,
        config: HubConfig,
        machine_token: MachineToken,
        hub_id: HubId,
    ) -> Self {
        let (tx, _rx) = broadcast::channel::<WsEvent>(256);
        let sink = Arc::new(BroadcastSink { tx: tx.clone() });
        runtime.set_event_sink(sink);
        Self {
            runtime: Arc::new(Mutex::new(runtime)),
            events: tx,
            config,
            machine_token,
            hub_id,
            http: reqwest::Client::new(),
            tenants: None,
            vector: None,
            entitlement: crate::entitlement::new_shared(),
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
            None => {
                // En single-tenant el primer login puede sustituir el placeholder de arranque por
                // el UUID real. Sincronizamos el Runtime antes de devolverlo para que sus helpers
                // internos (settings, perfil, instalación…) usen el mismo scope que la auth. La
                // autoridad es la celda del host, NUNCA el argumento (que en query/command puede
                // proceder de `X-Hub-Id` en modo dev).
                let effective_hub_id = self.hub_id();
                let mut runtime = self.runtime.lock().await;
                if runtime.hub_id() != effective_hub_id {
                    runtime.adopt_hub_id(effective_hub_id);
                }
                drop(runtime);
                Ok(self.runtime.clone())
            }
        }
    }

    /// Lee el `hub_id` vivo (clona). Si el lock estuviera envenenado, conserva el valor de
    /// arranque; nunca acepta un id aportado por el navegador como autoridad.
    pub fn hub_id(&self) -> String {
        self.hub_id
            .read()
            .map(|g| g.clone())
            .unwrap_or_else(|_| self.config.hub_id.clone())
    }

    /// Copia de configuración para gates de auth con el `hub_id` vivo ya reconciliado. Mantiene el
    /// resto de opciones inmutables y evita que un handler use accidentalmente el placeholder que
    /// existía antes del registro de la máquina.
    pub fn effective_config(&self) -> HubConfig {
        let mut config = self.config.clone();
        config.hub_id = self.hub_id();
        config
    }

    /// Demo/Dev es la única excepción al registro de máquina obligatorio.
    pub fn is_demo(&self) -> bool {
        self.config.auth_mode == AuthMode::Dev && self.hub_id() == DEV_HUB_ID
    }

    /// Una máquina real está vinculada solo si posee las dos mitades de su identidad: UUID Cloud
    /// y credencial secreta. Tener un JWT de usuario abierto no sustituye este estado.
    pub fn machine_registered(&self) -> bool {
        !self.is_demo() && self.hub_id() != DEV_HUB_ID && self.machine_token().is_some()
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

#[cfg(test)]
mod tests {
    use super::*;

    /// **Fail-closed (hub#241).** Sin `HUB_AUTH` el hub NO puede arrancar sin autenticación: el
    /// default es producción (`Session`). Antes era `Dev` y un despliegue que olvidara la variable
    /// aceptaba la identidad y los permisos que dictase el navegador (`X-User-Id`/`X-Permissions`).
    #[test]
    fn missing_env_defaults_to_session_not_dev() {
        assert_eq!(parse_auth_mode(None), AuthMode::Session);
        assert_ne!(parse_auth_mode(None), AuthMode::Dev);
    }

    /// El modo de desarrollo se pide EXPLÍCITAMENTE.
    #[test]
    fn dev_mode_must_be_requested_explicitly() {
        assert_eq!(parse_auth_mode(Some("dev")), AuthMode::Dev);
        assert_eq!(parse_auth_mode(Some(" dev ")), AuthMode::Dev);
    }

    #[test]
    fn session_is_accepted_verbatim() {
        assert_eq!(parse_auth_mode(Some("session")), AuthMode::Session);
    }

    /// Un typo (`develop`, `DEV`, vacío) NO degrada la seguridad: cae a `Session`.
    #[test]
    fn unknown_or_empty_value_falls_back_to_session() {
        for raw in ["develop", "DEV", "Dev", "", "true", "1"] {
            assert_eq!(
                parse_auth_mode(Some(raw)),
                AuthMode::Session,
                "`{raw}` no debe abrir el hub"
            );
        }
    }
}
