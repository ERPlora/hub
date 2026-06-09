//! Estado compartido del server: el runtime (tras un lock), el canal de eventos para WS,
//! y la configuración de despliegue (hub_id + Cloud Portal + cache de módulos).
use std::path::PathBuf;
use std::sync::Arc;

use erplora_runtime::{EventSink, Runtime};
use serde_json::{json, Value as Json};
use tokio::sync::{broadcast, Mutex};

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

/// Modo de autenticación del server (ARQUITECTURA.md §2.3):
///  - `Dev`: confía en cabeceras `X-User-Id`/`X-Permissions` (desarrollo local, sin Cloud).
///  - `Jwt`: **verifica** el access JWT del usuario (RS256) contra la clave pública del Cloud;
///    `user_id` sale del token (no del header). Se activa con `HUB_AUTH=jwt`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AuthMode {
    Dev,
    Jwt,
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
            Ok("jwt") => AuthMode::Jwt,
            _ => AuthMode::Dev,
        };
        // Inyección directa de la clave (PEM) por entorno; si no, `main` la trae del Cloud.
        let jwt_public_key = std::env::var("HUB_JWT_PUBLIC_KEY").ok().filter(|s| !s.trim().is_empty());
        Self { hub_id, cloud_base_url, module_cache, auth_mode, jwt_public_key }
    }
}

/// Estado de la app Axum. El runtime no es `Sync` para mutación, así que va tras un `Mutex`;
/// para 1–30 usuarios por hub (ARQUITECTURA.md §7.5) es más que suficiente.
#[derive(Clone)]
pub struct AppState {
    pub runtime: Arc<Mutex<Runtime>>,
    pub events: broadcast::Sender<WsEvent>,
    pub config: HubConfig,
    /// Cliente HTTP async (rustls) compartido para hablar con el Cloud (descargas + proxy SSE).
    pub http: reqwest::Client,
}

impl AppState {
    /// Crea el estado y conecta el `EventSink` del runtime al canal broadcast.
    pub fn new(runtime: Runtime) -> Self {
        Self::with_config(runtime, HubConfig::from_env())
    }

    /// Variante con config explícita (tests / arranque controlado).
    pub fn with_config(mut runtime: Runtime, config: HubConfig) -> Self {
        let (tx, _rx) = broadcast::channel::<WsEvent>(256);
        let sink = Arc::new(BroadcastSink { tx: tx.clone() });
        runtime.set_event_sink(sink);
        Self {
            runtime: Arc::new(Mutex::new(runtime)),
            events: tx,
            config,
            http: reqwest::Client::new(),
        }
    }

    /// Publica un frame WS crudo (lo usa el flujo de instalación → `module.installed`).
    pub fn broadcast(&self, frame: Json) {
        let _ = self.events.send(frame);
    }
}
