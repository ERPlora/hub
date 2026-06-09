//! ERPlora Hub — shell Tauri **gratuito** (desktop/Android) con el **gate de arranque
//! por entitlement** (ARQUITECTURA.md §1, §2.8).
//!
//! Al arrancar, la app no monta el runtime de negocio hasta resolver el entitlement:
//!
//! 1. Si hay red: pide al Cloud la clave pública + el token de entitlement firmado
//!    (`GET /api/v1/hub/device/entitlement/`), lo verifica, lo **cachea** y desbloquea.
//! 2. Si NO hay red: usa el token cacheado y lo verifica **offline** contra la clave
//!    pública cacheada; sigue operando mientras esté dentro de la ventana de gracia.
//! 3. Si no hay token válido ni cacheado: **pantalla de login/activación** (Locked) — el
//!    frontend (`apps/web`) no monta los módulos de negocio.
//!
//! La verificación criptográfica y la regla de gracia viven en `erplora-cloud-client`
//! (`entitlement::verify_entitlement`); aquí solo está el I/O (HTTP + caché en disco) y
//! el pegamento con Tauri `invoke`.

use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use erplora_cloud_client::{
    entitlement::EntitledModule, verify_entitlement, Auth, CloudClient, EnrollGrant,
    EntitlementClaims, EntitlementResponse, PreparedRequest,
};
use serde::{Deserialize, Serialize};

const TOKEN_FILE: &str = "entitlement.jwt";
const PUBKEY_FILE: &str = "cloud_public_key.pem";

#[derive(Debug, thiserror::Error)]
pub enum GateError {
    #[error("http error: {0}")]
    Http(String),
    #[error("io error: {0}")]
    Io(String),
    #[error("respuesta del Cloud inválida: {0}")]
    Parse(String),
    #[error("verificación del entitlement fallida: {0}")]
    Verify(String),
}

impl serde::Serialize for GateError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

/// Resultado del gate que se devuelve al frontend.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum GateOutcome {
    /// Entitlement válido: el frontend monta SOLO estos módulos.
    Unlocked {
        modules: Vec<EntitledModule>,
        deployment_mode: String,
        /// `true` si se resolvió sin red, desde el token cacheado (modo gracia).
        offline: bool,
    },
    /// Sin entitlement válido: mostrar login/activación, no montar negocio.
    NeedsActivation { reason: String },
}

/// Respuesta del endpoint público de clave (`GET /api/v1/auth/public-key/`).
#[derive(Debug, Deserialize)]
struct PublicKeyResponse {
    public_key: String,
    #[serde(default)]
    #[allow(dead_code)]
    algorithm: String,
}

/// Gate de entitlement: construye peticiones con `CloudClient` y cachea en `cache_dir`.
pub struct EntitlementGate {
    client: CloudClient,
    cache_dir: PathBuf,
}

impl EntitlementGate {
    pub fn new(base_url: impl Into<String>, cache_dir: impl Into<PathBuf>) -> Self {
        Self { client: CloudClient::new(base_url), cache_dir: cache_dir.into() }
    }

    fn token_path(&self) -> PathBuf {
        self.cache_dir.join(TOKEN_FILE)
    }

    fn pubkey_path(&self) -> PathBuf {
        self.cache_dir.join(PUBKEY_FILE)
    }

    /// Intenta resolver desde la caché local, verificando firma + ventana de gracia.
    /// `None` si no hay caché o el token ya no es válido.
    fn load_cached(&self, now_unix: i64) -> Option<EntitlementClaims> {
        let token = std::fs::read_to_string(self.token_path()).ok()?;
        let pubkey = std::fs::read_to_string(self.pubkey_path()).ok()?;
        verify_entitlement(token.trim(), pubkey.trim(), now_unix).ok()
    }

    fn write_cache(&self, token: &str, pubkey_pem: &str) -> Result<(), GateError> {
        std::fs::create_dir_all(&self.cache_dir).map_err(|e| GateError::Io(e.to_string()))?;
        std::fs::write(self.token_path(), token).map_err(|e| GateError::Io(e.to_string()))?;
        std::fs::write(self.pubkey_path(), pubkey_pem).map_err(|e| GateError::Io(e.to_string()))?;
        Ok(())
    }

    /// Refresca online: descarga clave pública + token, los verifica y los cachea.
    async fn refresh(
        &self,
        hub_id: &str,
        access_jwt: &str,
        now_unix: i64,
    ) -> Result<EntitlementClaims, GateError> {
        // 1) Clave pública (endpoint público, sin auth).
        let pk_body = exec(self.client.public_key()).await?;
        let pk: PublicKeyResponse =
            serde_json::from_str(&pk_body).map_err(|e| GateError::Parse(e.to_string()))?;

        // 2) Entitlement firmado (con el JWT del usuario + X-Hub-Id).
        let auth = Auth::UserJwt { hub_id: hub_id.to_string(), access: access_jwt.to_string() };
        let ent_body = exec(self.client.entitlement(&auth)).await?;
        let ent =
            EntitlementResponse::parse(&ent_body).map_err(|e| GateError::Parse(e.to_string()))?;

        // 3) Verifica la firma offline-style (misma ruta que usaremos sin red).
        let claims = verify_entitlement(&ent.token, &pk.public_key, now_unix)
            .map_err(|e| GateError::Verify(e.to_string()))?;

        // 4) Cachea token + clave para los próximos arranques sin red.
        self.write_cache(&ent.token, &pk.public_key)?;
        Ok(claims)
    }

    /// Punto de entrada del gate: intenta online; si falla la red, cae a la caché.
    pub async fn resolve(&self, hub_id: &str, access_jwt: &str, now_unix: i64) -> GateOutcome {
        match self.refresh(hub_id, access_jwt, now_unix).await {
            Ok(claims) => GateOutcome::Unlocked {
                modules: claims.modules,
                deployment_mode: claims.deployment_mode,
                offline: false,
            },
            Err(online_err) => {
                // Sin red (o error transitorio): intenta el token cacheado en gracia.
                match self.load_cached(now_unix) {
                    Some(claims) => GateOutcome::Unlocked {
                        modules: claims.modules,
                        deployment_mode: claims.deployment_mode,
                        offline: true,
                    },
                    None => GateOutcome::NeedsActivation { reason: online_err.to_string() },
                }
            }
        }
    }
}

/// Ejecuta una `PreparedRequest` del `CloudClient` con reqwest y devuelve el body.
async fn exec(req: PreparedRequest) -> Result<String, GateError> {
    let client = reqwest::Client::new();
    let mut builder = match req.method {
        "POST" => client.post(&req.url),
        _ => client.get(&req.url),
    };
    for (k, v) in req.headers {
        builder = builder.header(k, v);
    }
    let resp = builder.send().await.map_err(|e| GateError::Http(e.to_string()))?;
    if !resp.status().is_success() {
        return Err(GateError::Http(format!("status {}", resp.status())));
    }
    resp.text().await.map_err(|e| GateError::Http(e.to_string()))
}

fn now_unix() -> i64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs() as i64).unwrap_or(0)
}

fn base_url() -> String {
    std::env::var("HUB_CLOUD_API_URL").unwrap_or_else(|_| "https://erplora.com".to_string())
}

/// Comando `invoke` del gate. El frontend lo llama al arrancar con el `hub_id` y el JWT
/// del usuario logueado; recibe los módulos a montar (o que debe mostrar activación).
#[tauri::command]
async fn validate_entitlement(
    app: tauri::AppHandle,
    hub_id: String,
    access_token: String,
) -> Result<GateOutcome, GateError> {
    use tauri::Manager;
    let cache_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| GateError::Io(e.to_string()))?;
    let gate = EntitlementGate::new(base_url(), cache_dir);
    Ok(gate.resolve(&hub_id, &access_token, now_unix()).await)
}

const DEVICE_ID_FILE: &str = "device.id";

/// Identidad de dispositivo que el frontend envía al hacer login (ARQUITECTURA.md §2.9b:
/// **un hub por dispositivo**). `client_type` mapea al `deployment_mode` del Cloud
/// (`hub-desktop` → desktop). El frontend lo manda como `X-Client-Type` + `X-Device-Id`.
#[derive(Debug, Clone, Serialize)]
pub struct DeviceContext {
    pub id: String,
    pub client_type: String,
}

/// Lee (o crea y persiste) un id de dispositivo estable por instalación en `app_data_dir`.
/// Sobrevive a limpiezas de caché del webview: identifica **esta** instalación Tauri.
fn ensure_device_id(cache_dir: &std::path::Path) -> Result<String, GateError> {
    let path = cache_dir.join(DEVICE_ID_FILE);
    if let Ok(existing) = std::fs::read_to_string(&path) {
        let trimmed = existing.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }
    let id = uuid::Uuid::new_v4().to_string();
    std::fs::create_dir_all(cache_dir).map_err(|e| GateError::Io(e.to_string()))?;
    std::fs::write(&path, &id).map_err(|e| GateError::Io(e.to_string()))?;
    Ok(id)
}

/// Comando `invoke` que devuelve la identidad de dispositivo para el login.
#[tauri::command]
fn device_context(app: tauri::AppHandle) -> Result<DeviceContext, GateError> {
    use tauri::Manager;
    let cache_dir: PathBuf =
        app.path().app_data_dir().map_err(|e| GateError::Io(e.to_string()))?;
    let id = ensure_device_id(&cache_dir)?;
    Ok(DeviceContext { id, client_type: "hub-desktop".to_string() })
}

const MACHINE_TOKEN_FILE: &str = "machine.token";

fn machine_token_path(cache_dir: &std::path::Path) -> PathBuf {
    cache_dir.join(MACHINE_TOKEN_FILE)
}

/// Persiste el token de máquina con permisos **restrictivos** (0600 en unix): es un secreto del
/// hub. (Un backend de keychain del SO sería aún mejor, pero requiere el toolchain Tauri v2 para
/// verificarse; este fichero con permisos de propietario es el endurecimiento mínimo y portable.)
fn persist_machine_token(cache_dir: &std::path::Path, token: &str) -> Result<(), GateError> {
    std::fs::create_dir_all(cache_dir).map_err(|e| GateError::Io(e.to_string()))?;
    let path = machine_token_path(cache_dir);
    #[cfg(unix)]
    {
        use std::io::Write;
        use std::os::unix::fs::OpenOptionsExt;
        let mut f = std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .open(&path)
            .map_err(|e| GateError::Io(e.to_string()))?;
        f.write_all(token.as_bytes()).map_err(|e| GateError::Io(e.to_string()))?;
    }
    #[cfg(not(unix))]
    {
        std::fs::write(&path, token).map_err(|e| GateError::Io(e.to_string()))?;
    }
    Ok(())
}

/// Lee el token de máquina persistido, si existe. Lo usará el arranque del **runtime embebido**
/// para exponerlo como `HUB_CLOUD_API_TOKEN` (que `HubConfig::from_env` lee) — igual que ECS lo
/// inyecta por env. `None` si el dispositivo aún no está enrolado.
pub fn load_machine_token(cache_dir: &std::path::Path) -> Option<String> {
    std::fs::read_to_string(machine_token_path(cache_dir))
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

/// Pide la credencial de máquina del hub al Cloud (`enroll` o `enroll_rotate`) y la persiste.
async fn fetch_and_persist_token(
    cache_dir: &std::path::Path,
    hub_id: String,
    access_token: String,
    rotate: bool,
) -> Result<String, GateError> {
    let client = CloudClient::new(base_url());
    let auth = Auth::UserJwt { hub_id, access: access_token };
    let req = if rotate { client.enroll_rotate(&auth) } else { client.enroll(&auth) };
    let body = exec(req).await?;
    let grant = EnrollGrant::parse(&body).map_err(|e| GateError::Parse(e.to_string()))?;
    persist_machine_token(cache_dir, &grant.cloud_api_token)?;
    Ok(grant.hub_id)
}

/// Enrola ESTE dispositivo: con el JWT de un owner/admin pide al Cloud la credencial de máquina
/// del hub (`cloud_api_token`) y la **persiste** en `app_data_dir`. El runtime embebido la usará
/// luego como `X-Hub-Token` para llamadas hub-scoped sin usuario logueado (§2.3). Devuelve el
/// `hub_id` enrolado. Se llama una vez, tras el login del propietario.
#[tauri::command]
async fn enroll_device(
    app: tauri::AppHandle,
    hub_id: String,
    access_token: String,
) -> Result<String, GateError> {
    use tauri::Manager;
    let cache_dir: PathBuf =
        app.path().app_data_dir().map_err(|e| GateError::Io(e.to_string()))?;
    fetch_and_persist_token(&cache_dir, hub_id, access_token, false).await
}

/// **Rota** la credencial de máquina (owner/admin): el Cloud genera un token nuevo (invalida el
/// anterior) y se re-persiste. Para respuesta a compromiso o rotación periódica. §2.3.
#[tauri::command]
async fn rotate_machine_token(
    app: tauri::AppHandle,
    hub_id: String,
    access_token: String,
) -> Result<String, GateError> {
    use tauri::Manager;
    let cache_dir: PathBuf =
        app.path().app_data_dir().map_err(|e| GateError::Io(e.to_string()))?;
    fetch_and_persist_token(&cache_dir, hub_id, access_token, true).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            validate_entitlement,
            device_context,
            enroll_device,
            rotate_machine_token
        ])
        .run(tauri::generate_context!())
        .expect("error while running ERPlora Tauri app");
}
