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
    /// El Cloud respondió 410 `hub_not_found`: el hub fue borrado/revocado. Señal inequívoca
    /// (distinta de un token caducado) para que el frontend haga logout + `forget_hub`.
    #[error("hub_not_found")]
    HubGone,
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
    /// El hub fue borrado/revocado en el Cloud (410 `hub_not_found`): el frontend debe hacer
    /// logout + olvidar la identidad local (`forget_hub`) y re-registrar en el próximo login
    /// (por `X-Device-Id`, §2.9b). NO se cae a la caché de gracia: la identidad ya no existe.
    HubGone,
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
        Self {
            client: CloudClient::new(base_url),
            cache_dir: cache_dir.into(),
        }
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
        let auth = Auth::UserJwt {
            hub_id: hub_id.to_string(),
            access: access_jwt.to_string(),
        };
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
            // Hub borrado/revocado: NO cae a la caché de gracia (la identidad ya no existe);
            // el frontend hará logout + forget_hub y re-registrará en el próximo login.
            Err(GateError::HubGone) => GateOutcome::HubGone,
            Err(online_err) => {
                // Sin red (o error transitorio): intenta el token cacheado en gracia.
                match self.load_cached(now_unix) {
                    Some(claims) => GateOutcome::Unlocked {
                        modules: claims.modules,
                        deployment_mode: claims.deployment_mode,
                        offline: true,
                    },
                    None => GateOutcome::NeedsActivation {
                        reason: online_err.to_string(),
                    },
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
    let resp = builder
        .send()
        .await
        .map_err(|e| GateError::Http(e.to_string()))?;
    let status = resp.status();
    if !status.is_success() {
        // 410 Gone = el Cloud responde `hub_not_found` (hub borrado/revocado): señal inequívoca
        // para logout + forget, distinta de un token caducado (401 → refresh).
        if status.as_u16() == 410 {
            return Err(GateError::HubGone);
        }
        return Err(GateError::Http(format!("status {status}")));
    }
    resp.text()
        .await
        .map_err(|e| GateError::Http(e.to_string()))
}

fn now_unix() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
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

// ── Camino de datos: HTTP+WS directo al runtime embebido (ADR-0050) ──────────────────────────────
//
// Ya NO hay handlers `invoke` de datos: `erplora_query`/`erplora_command` + `forward_to_runtime` +
// `IpcError` se ELIMINARON, y con ellos el `IpcTransport` del SDK. El front (`apps/web`) habla
// HTTP+WS al runtime Axum embebido por loopback (`127.0.0.1:8787`, ver `embedded_serve_config`/
// `spawn_embedded_runtime`) vía `HttpWsTransport`, igual que la PWA de Hub Cloud contra ECS.
//
// PENDIENTE (columna core/humano) para CERRAR ADR-0050 en Hub Local: que el front y el runtime
// compartan ORIGEN, para que ese `HttpWsTransport` (mismo origen, sin URL absoluta) alcance el
// loopback sin CORS — p. ej. que el runtime embebido sirva el `dist/` (`with_static_frontend`, ver
// `crates/server/src/lib.rs`; contrato cubierto por `crates/server/tests/spa_frontend.rs`) y la
// ventana Tauri cargue de `http://127.0.0.1:8787` en vez del protocolo de assets.
//
// `invoke` queda SOLO para lo nativo (`device_context`/`enroll_device`/…) y el HARDWARE en Hub Local
// (`erplora_bridge_*`, más abajo: el shell ES el bridge, §2.7) — ambos legítimos por ADR-0050.

const DEVICE_ID_FILE: &str = "device.id";

/// Identidad de dispositivo que el frontend envía al hacer login (ARQUITECTURA.md §2.9b:
/// **un hub por dispositivo**). `client_type` mapea al `deployment_mode` del Cloud
/// (`hub-desktop` → desktop). El frontend lo manda como `X-Client-Type` + `X-Device-Id`.
#[derive(Debug, Clone, Serialize)]
pub struct DeviceContext {
    pub id: String,
    pub client_type: String,
    /// Plataforma física, separada del contrato legacy de `client_type`. El SaaS puede registrar
    /// Android/Windows explícitamente sin romper clientes que aún mapean ambos a `hub-desktop`.
    pub platform: String,
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
    let cache_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| GateError::Io(e.to_string()))?;
    let id = ensure_device_id(&cache_dir)?;
    // Compatibilidad: el endpoint Cloud vigente registra `hub-desktop` y `hub-local`. La
    // plataforma real viaja además en X-Device-Platform; cuando el SaaS amplíe su taxonomía no
    // habrá que regenerar el id de esta instalación. Desarrollo local puede forzar hub-local.
    let client_type = std::env::var("HUB_CLIENT_TYPE")
        .ok()
        .filter(|v| matches!(v.as_str(), "hub-desktop" | "hub-local"))
        .unwrap_or_else(|| "hub-desktop".to_string());
    let platform = if cfg!(target_os = "android") {
        "android"
    } else if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(target_os = "linux") {
        "linux"
    } else {
        "desktop"
    };
    Ok(DeviceContext {
        id,
        client_type,
        platform: platform.to_string(),
    })
}

const MACHINE_TOKEN_FILE: &str = "machine.token";

fn machine_token_path(cache_dir: &std::path::Path) -> PathBuf {
    cache_dir.join(MACHINE_TOKEN_FILE)
}

// ── Keychain del SO (desktop) ─────────────────────────────────────────────────────────────────
// El token de máquina es un secreto: en desktop va al **keychain del SO** (macOS Keychain,
// Windows Credential Manager, Linux Secret Service vía el crate `keyring`). En **Android** el
// crate `keyring` no tiene backend, así que NO se compila (dep target-específica en Cargo.toml) y
// se cae al fichero 0600 dentro del sandbox por-app de Android. Una sola entrada por dispositivo
// (un hub por dispositivo, §2.9b) → cuenta fija.
#[cfg(not(target_os = "android"))]
const KEYRING_SERVICE: &str = "com.erplora.hub";
#[cfg(not(target_os = "android"))]
const KEYRING_ACCOUNT: &str = "machine-token";

#[cfg(not(target_os = "android"))]
fn keyring_set(token: &str) -> bool {
    keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT)
        .and_then(|e| e.set_password(token))
        .is_ok()
}
#[cfg(not(target_os = "android"))]
fn keyring_get() -> Option<String> {
    let e = keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).ok()?;
    let t = e.get_password().ok()?.trim().to_string();
    (!t.is_empty()).then_some(t)
}
#[cfg(not(target_os = "android"))]
fn keyring_delete() -> bool {
    keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT)
        .and_then(|e| e.delete_credential())
        .is_ok()
}
#[cfg(target_os = "android")]
fn keyring_set(_token: &str) -> bool {
    false
}
#[cfg(target_os = "android")]
fn keyring_get() -> Option<String> {
    None
}
#[cfg(target_os = "android")]
fn keyring_delete() -> bool {
    false
}

/// Escribe el token en un fichero con permisos **restrictivos** (0600 en unix). Fallback cuando el
/// keychain del SO no está disponible (Android, o Linux sin Secret Service / headless).
fn persist_token_file(cache_dir: &std::path::Path, token: &str) -> Result<(), GateError> {
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
        f.write_all(token.as_bytes())
            .map_err(|e| GateError::Io(e.to_string()))?;
    }
    #[cfg(not(unix))]
    {
        std::fs::write(&path, token).map_err(|e| GateError::Io(e.to_string()))?;
    }
    Ok(())
}

/// Persiste el token de máquina: **keychain del SO** primero (desktop); si no está disponible,
/// fichero 0600. Cuando el keychain acepta, **borra** cualquier copia legacy en fichero para no
/// dejar el secreto en claro.
fn persist_machine_token(cache_dir: &std::path::Path, token: &str) -> Result<(), GateError> {
    if keyring_set(token) {
        let _ = std::fs::remove_file(machine_token_path(cache_dir));
        return Ok(());
    }
    persist_token_file(cache_dir, token)
}

/// Lee el token de máquina persistido (keychain del SO → fichero), si existe. Lo usará el arranque
/// del **runtime embebido** para exponerlo como `HUB_CLOUD_API_TOKEN` (que `HubConfig::from_env`
/// lee) — igual que ECS lo inyecta por env. `None` si el dispositivo aún no está enrolado.
pub fn load_machine_token(cache_dir: &std::path::Path) -> Option<String> {
    keyring_get().or_else(|| {
        std::fs::read_to_string(machine_token_path(cache_dir))
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
    })
}

const HUB_ID_FILE: &str = "hub.id";

/// Lee el `hub_id` (de Cloud) persistido al enrolar. Lo usa el runtime embebido como `X-Hub-Id`
/// en las llamadas hub-scoped firmadas con el token de máquina. `None` si aún no se enroló.
pub fn load_hub_id(cache_dir: &std::path::Path) -> Option<String> {
    std::fs::read_to_string(cache_dir.join(HUB_ID_FILE))
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

/// Pide la credencial de máquina del hub al Cloud (`enroll` o `enroll_rotate`) y la persiste
/// (token en keychain; `hub_id` en `app_data_dir` para que el runtime embebido lo use como
/// `X-Hub-Id`). El [`EnrollGrant`] trae ambos.
async fn fetch_and_persist_token(
    cache_dir: &std::path::Path,
    hub_id: String,
    access_token: String,
    rotate: bool,
) -> Result<String, GateError> {
    let client = CloudClient::new(base_url());
    let auth = Auth::UserJwt {
        hub_id,
        access: access_token,
    };
    let req = if rotate {
        client.enroll_rotate(&auth)
    } else {
        client.enroll(&auth)
    };
    let body = exec(req).await?;
    let grant = EnrollGrant::parse(&body).map_err(|e| GateError::Parse(e.to_string()))?;
    persist_machine_token(cache_dir, &grant.cloud_api_token)?;
    std::fs::create_dir_all(cache_dir).map_err(|e| GateError::Io(e.to_string()))?;
    std::fs::write(cache_dir.join(HUB_ID_FILE), &grant.hub_id)
        .map_err(|e| GateError::Io(e.to_string()))?;
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
    let cache_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| GateError::Io(e.to_string()))?;
    let out = fetch_and_persist_token(&cache_dir, hub_id, access_token, false).await?;
    apply_persisted_identity(&app, &cache_dir);
    Ok(out)
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
    let cache_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| GateError::Io(e.to_string()))?;
    let out = fetch_and_persist_token(&cache_dir, hub_id, access_token, true).await?;
    apply_persisted_identity(&app, &cache_dir);
    Ok(out)
}

/// Olvida la identidad de máquina de ESTE dispositivo. Lo invoca el frontend cuando el Cloud
/// responde 410 `hub_not_found` (hub borrado/revocado): borra el token de máquina (keychain +
/// fichero), el `hub_id` cacheado y el entitlement firmado cacheado, y resetea la celda viva del
/// runtime embebido (deja de firmar con el token viejo, sin reiniciar). CONSERVA el `device.id`
/// (ancla estable §2.9b) para que el siguiente login re-registre el hub por dispositivo. Best-effort:
/// no falla si algún recurso ya no existe.
#[tauri::command]
fn forget_hub(app: tauri::AppHandle) -> Result<(), GateError> {
    use tauri::Manager;
    let cache_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| GateError::Io(e.to_string()))?;
    let _ = keyring_delete();
    let _ = std::fs::remove_file(machine_token_path(&cache_dir));
    let _ = std::fs::remove_file(cache_dir.join(HUB_ID_FILE));
    let _ = std::fs::remove_file(cache_dir.join(TOKEN_FILE));
    let _ = std::fs::remove_file(cache_dir.join(PUBKEY_FILE));
    if let Some(h) = app.try_state::<MachineIdentityHandle>() {
        if let Ok(mut g) = h.token.write() {
            *g = None;
        }
        if let Ok(mut g) = h.hub_id.write() {
            *g = erplora_server::DEV_HUB_ID.to_string();
        }
    }
    Ok(())
}

/// Identidad de máquina compartida entre el shell Tauri y el runtime embebido. Token y `hub_id`
/// cambian juntos al completar el alta; así nunca se firma con una credencial nueva y el UUID
/// placeholder anterior.
#[derive(Clone)]
struct MachineIdentityHandle {
    token: erplora_server::MachineToken,
    hub_id: erplora_server::HubId,
}

/// Actualiza la identidad viva con lo recién persistido tras enrolar/rotar.
fn apply_persisted_identity(app: &tauri::AppHandle, cache_dir: &std::path::Path) {
    use tauri::Manager;
    if let Some(h) = app.try_state::<MachineIdentityHandle>() {
        if let Ok(mut g) = h.token.write() {
            *g = load_machine_token(cache_dir);
        }
        if let Some(persisted_hub_id) = load_hub_id(cache_dir) {
            if let Ok(mut g) = h.hub_id.write() {
                *g = persisted_hub_id;
            }
        }
    }
}

/// Construye la config del **runtime embebido** (§11) para este dispositivo: SQLite + caché de
/// módulos en `app_data_dir`, modo `Session` (identidad local real, login PIN/JWT), y la **celda
/// compartida** del token de máquina (hot-reload). El `hub_id` sale de lo persistido al enrolar
/// (placeholder de dev hasta el primer enrol).
/// CSP del documento en Hub Local (ADR-0050). Con el doc servido por el Axum embebido en
/// `127.0.0.1:8787`, `'self'` ES ese origen; la CSP de `tauri.conf` ya no aplica al doc (solo la
/// inyecta el protocolo de assets), así que la emite el runtime (ver `erplora_server::with_csp`).
/// Conserva `ipc:` (macOS/Linux) + `http://ipc.localhost` (Windows/Android) para que `invoke`
/// (device_context + hardware) siga funcionando, y `ws://127.0.0.1:8787` para los eventos.
const LOOPBACK_CSP: &str = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ipc: http://ipc.localhost ws://127.0.0.1:8787 https://erplora.com; frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'";

fn embedded_serve_config(
    cache_dir: &std::path::Path,
    machine_token_cell: erplora_server::MachineToken,
    hub_id_cell: erplora_server::HubId,
    web_dir: Option<String>,
) -> erplora_server::ServeConfig {
    erplora_server::ServeConfig {
        sqlite_path: cache_dir.join("erplora.db").to_string_lossy().into_owned(),
        database_url: None, // Tauri/local = SQLite embebido (offline-first); Postgres solo en hub AWS cloud
        bind: "127.0.0.1:8787".to_string(),
        modules_dir: None, // los módulos se descargan en runtime desde el marketplace (no horneados)
        hub: erplora_server::HubConfig {
            hub_id: load_hub_id(cache_dir)
                .unwrap_or_else(|| erplora_server::DEV_HUB_ID.to_string()),
            cloud_base_url: base_url(),
            module_cache: cache_dir.join("modules"),
            auth_mode: erplora_server::AuthMode::Session,
            jwt_public_key: None, // `serve()` la trae del Cloud si hay red (login cloud); PIN no la necesita
            cloud_api_token: None, // la celda compartida es la fuente del token (hot-reload)
            device_trust_enforce: false, // hub#15: gate de login por PIN; el host debe aportar device_id antes de activarlo
            media_dir: cache_dir.join("media"), // ficheros/documentos locales en el app data dir (junto a SQLite y módulos)
            sector: None, // sector/tipo de negocio (ADR-0054): no cableado en local/Tauri → preset de widgets degrada
        },
        machine_token_cell: Some(machine_token_cell),
        hub_id_cell: Some(hub_id_cell),
        // ADR-0050 (mismo origen): el runtime embebido sirve el `dist/` empaquetado (desktop prod) para
        // que el webview cargue front + datos del mismo origen. `None` en dev (Vite sirve) y móvil.
        web_dir,
        // CSP del doc emitida por el runtime (la de `tauri.conf` no aplica al doc servido por Axum).
        csp: Some(LOOPBACK_CSP.to_string()),
    }
}

/// Arranca el runtime embebido (`erplora_server::serve`) en un **hilo dedicado con su propio
/// runtime tokio**, aislado del runtime async de Tauri. El webview le habla por loopback. El token
/// de máquina vive en la celda compartida: un enrol/rotación lo aplica **en caliente** (#22).
fn spawn_embedded_runtime(
    cache_dir: PathBuf,
    machine_token_cell: erplora_server::MachineToken,
    hub_id_cell: erplora_server::HubId,
    web_dir: Option<String>,
) {
    std::thread::spawn(move || {
        let rt = match tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
        {
            Ok(rt) => rt,
            Err(e) => {
                eprintln!("runtime embebido: no se pudo crear tokio: {e}");
                return;
            }
        };
        rt.block_on(async move {
            if let Err(e) = erplora_server::serve(embedded_serve_config(
                &cache_dir,
                machine_token_cell,
                hub_id_cell,
                web_dir,
            ))
            .await
            {
                eprintln!("runtime embebido terminó: {e}");
            }
        });
    });
}

/// Ruta del `dist/` empaquetado a servir por el Axum embebido (ADR-0050, mismo origen). Solo en
/// desktop EMPAQUETADO: en **dev** el front lo sirve Vite (→ `None`), y en **móvil** `resource_dir()`
/// no es una ruta de FS servible por `ServeDir` (→ `None`; el webview carga el `dist` por el protocolo
/// de assets). `resource_dir()/dist` casa con el destino del recurso declarado en `tauri.conf` (§bundle).
fn resolve_web_dir(app: &tauri::App) -> Option<String> {
    if tauri::is_dev() {
        return None;
    }
    #[cfg(any(target_os = "android", target_os = "ios"))]
    {
        let _ = app;
        None
    }
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    {
        use tauri::Manager;
        app.path()
            .resource_dir()
            .ok()
            .map(|r| r.join("dist"))
            .filter(|p| p.join("index.html").exists())
            .map(|p| p.to_string_lossy().into_owned())
    }
}

/// Espera (con timeout) a que el runtime embebido acepte conexiones TCP en `addr`, para NO cargar la
/// ventana antes de que el loopback escuche (evita `ERR_CONNECTION_REFUSED`). Un connect TCP basta
/// como señal de "listo": `serve()` bindea el listener al final del arranque y empieza a aceptar acto
/// seguido. OJO: el bind ocurre tras abrir SQLite + instalar módulos + `fetch_jwt_public_key` (que ya
/// va ACOTADO por timeout, `crates/server`), así que en red hostil el bind puede tardar varios
/// segundos — de ahí el budget de 15s. (TODO humano: mover esta espera fuera del hilo principal —
/// página "loading" + redirección — para no congelar `setup`; ver M1 del review ADR-0050.)
#[cfg(not(any(target_os = "android", target_os = "ios")))]
fn wait_for_runtime(addr: &str, timeout: std::time::Duration) -> bool {
    let sock: std::net::SocketAddr = match addr.parse() {
        Ok(s) => s,
        Err(_) => return false,
    };
    let deadline = std::time::Instant::now() + timeout;
    while std::time::Instant::now() < deadline {
        if std::net::TcpStream::connect_timeout(&sock, std::time::Duration::from_millis(300))
            .is_ok()
        {
            return true;
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    false
}

/// Crea la ventana principal con la URL correcta según entorno (ADR-0050). En **desktop prod** carga
/// el runtime Axum embebido (`http://127.0.0.1:8787`) = mismo origen que `/api` (tras esperar a que
/// escuche), PERO solo si el runtime arrancó (`runtime_started`) y el `dist/` se empaquetó
/// (`web_dir_present`); en **dev** carga Vite (`http://127.0.0.1:5173`, que proxya `/api`,`/ws` →
/// 8787); en **móvil** carga el `dist` por el protocolo de assets. La ventana se crea aquí (no en
/// `tauri.conf`) para fijar la URL de una sola vez (el framework crea las ventanas de config ANTES
/// del `setup`, lo que provocaría un flash + doble origen).
///
/// DEGRADADO (C3/M2 del review): si el runtime NO arrancó (p. ej. `app_data_dir` falló) o el `dist/`
/// no está empaquetado, NO se navega al loopback (daría `ERR_CONNECTION_REFUSED` o 404 + cuelgue de
/// 15s + ventana muerta): se carga el SPA por el protocolo de assets (se ve el shell aunque no
/// alcance los datos) y se loguea el fallo de empaquetado/arranque.
fn open_main_window(
    app: &tauri::App,
    runtime_started: bool,
    web_dir_present: bool,
) -> tauri::Result<()> {
    use tauri::{WebviewUrl, WebviewWindowBuilder};

    #[cfg(any(target_os = "android", target_os = "ios"))]
    let url = {
        let _ = (runtime_started, web_dir_present);
        WebviewUrl::App("index.html".into())
    };
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    let url = if tauri::is_dev() {
        // Dev: el doc lo sirve Vite (5173), que proxya /api,/ws → 8787 (mismo origen). No se espera al
        // runtime aquí: las llamadas proxyadas reintentan si aún no está arriba.
        WebviewUrl::External("http://127.0.0.1:5173".parse().expect("url dev válida"))
    } else if runtime_started && web_dir_present {
        if !wait_for_runtime("127.0.0.1:8787", std::time::Duration::from_secs(15)) {
            eprintln!(
                "runtime embebido no respondió a tiempo; abro la ventana igualmente (el front reintenta)"
            );
        }
        WebviewUrl::External("http://127.0.0.1:8787".parse().expect("url prod válida"))
    } else {
        eprintln!(
            "arranque DEGRADADO (runtime_started={runtime_started}, dist_empaquetado={web_dir_present}): \
             cargo el SPA por el protocolo de assets (sin datos); revisa el empaquetado del dist / app_data_dir"
        );
        WebviewUrl::App("index.html".into())
    };

    WebviewWindowBuilder::new(app, "main", url)
        .title("ERPlora")
        .inner_size(1280.0, 800.0)
        .min_inner_size(960.0, 600.0)
        .build()?;
    Ok(())
}

// ── Camino de hardware: handlers `invoke` → erplora-peripherals (issue #29) ──────────────────────
//
// En los combos Tauri **el shell ES el bridge** (no hay proceso bridge aparte, §2.7): el hardware
// se expone por handlers `invoke` que delegan en `erplora-peripherals`, el mismo crate que usa el
// bridge standalone (`apps/bridge`) vía WebSocket. El contrato de datos es idéntico al de las
// frames WS del bridge: `discoverPrinters`/`getDevices` devuelven el array de
// `protocol::{PrinterInfo,Device}` (serde-serializado igual que `BridgePrinter`/`BridgeDevice` del
// SDK, `packages/module-sdk/src/index.ts:719`); `print`/`testPrint`/`openDrawer` no devuelven nada.
//
// El `Watchdog` del registry corre como tarea async del shell (auto-recuperación de IP por DHCP),
// y la `PrintQueue` con reintentos drena en segundo plano — igual que `apps/bridge`. Los outcomes
// y eventos del watchdog se loguean (en el bridge standalone viajan por WS; aquí el canal a la UI
// se cablearía con eventos Tauri en una fase posterior — columna del humano).

use erplora_peripherals::discovery::{self, parse_printer_id};
use erplora_peripherals::drawer;
use erplora_peripherals::escpos::{self, DocumentType};
use erplora_peripherals::protocol::{Device, PrinterInfo};
use erplora_peripherals::queue::{JobOutcome, PrintJob, PrintQueue, RetryPolicy};
use erplora_peripherals::registry::DeviceRegistry;

const DEVICES_FILE: &str = "devices.json";

/// Estado de hardware compartido entre handlers `invoke`: registro persistente de dispositivos +
/// cola de impresión con reintentos. Vive en el estado gestionado de Tauri (`app.manage`). El
/// registro y la cola van tras `Arc` para que las tareas de fondo (watchdog + worker de la cola)
/// compartan las mismas instancias que los handlers `invoke`.
struct PeripheralsState {
    registry: std::sync::Arc<DeviceRegistry>,
    queue: std::sync::Arc<PrintQueue>,
}

/// Construye el estado de hardware y **lanza** las tareas de fondo en el runtime tokio actual:
///   - worker de la `PrintQueue` (envío con reintentos; cada `JobOutcome` se loguea),
///   - `Watchdog` del registry (health-check + recovery por MAC ante cambio de IP DHCP).
/// Espejo de `spawn_queue_worker`/`spawn_watchdog` del bridge standalone (`apps/bridge/src/main.rs`).
/// En el bridge los eventos viajan por WS; aquí se loguean (el canal a la UI por eventos Tauri es
/// una fase posterior — columna del humano).
fn build_peripherals_state(devices_path: PathBuf) -> PeripheralsState {
    let registry = std::sync::Arc::new(DeviceRegistry::load(devices_path));
    let queue = std::sync::Arc::new(PrintQueue::new(RetryPolicy::default()));

    // Worker de la cola de impresión: drena y reintenta; loguea cada outcome. `async_runtime::spawn`
    // usa el runtime tokio global de Tauri, así que funciona desde el `setup` hook.
    let worker_queue = queue.clone();
    tauri::async_runtime::spawn(async move {
        let (outcomes_tx, mut outcomes_rx) = tokio::sync::mpsc::unbounded_channel::<JobOutcome>();
        tauri::async_runtime::spawn(async move {
            while let Some(outcome) = outcomes_rx.recv().await {
                match outcome {
                    JobOutcome::Completed { job_id } => {
                        eprintln!("peripherals: trabajo de impresión completado ({job_id:?})")
                    }
                    JobOutcome::Failed { job_id, error } => {
                        eprintln!("peripherals: trabajo de impresión fallido ({job_id:?}): {error}")
                    }
                }
            }
        });
        worker_queue.run(outcomes_tx).await;
        eprintln!("peripherals: worker de la cola de impresión terminado (cola cerrada)");
    });

    // Watchdog del registry: auto-recuperación de dispositivos tras cambio de IP por DHCP.
    let watchdog_registry = registry.clone();
    tauri::async_runtime::spawn(async move {
        use erplora_peripherals::registry::{Watchdog, WatchdogConfig, WatchdogEvent};
        let (events_tx, mut events_rx) = tokio::sync::mpsc::unbounded_channel::<WatchdogEvent>();
        tauri::async_runtime::spawn(async move {
            while let Some(ev) = events_rx.recv().await {
                match ev {
                    WatchdogEvent::Recovered(d) => {
                        eprintln!("peripherals: dispositivo recuperado {} ({})", d.name, d.mac)
                    }
                    WatchdogEvent::Lost(d) => {
                        eprintln!("peripherals: dispositivo perdido {} ({})", d.name, d.mac)
                    }
                }
            }
        });
        let watchdog = Watchdog::new(WatchdogConfig::default()).with_events(events_tx);
        watchdog.run(&watchdog_registry).await;
    });

    PeripheralsState { registry, queue }
}

/// Error de los handlers de hardware. Se serializa como string para el frontend (igual que el
/// `Event::Error` del bridge standalone se mapea a un rechazo de la promesa en el SDK).
#[derive(Debug, thiserror::Error)]
pub enum HardwareError {
    #[error("{0}")]
    Peripheral(#[from] erplora_peripherals::PeripheralError),
}

impl serde::Serialize for HardwareError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

/// `erplora_bridge_status` — el `IpcBridgeTransport.detect()` lo invoca para saber si el canal de
/// hardware existe (en Tauri siempre existe: el shell ES el bridge). Devuelve la versión del shell.
#[tauri::command]
fn erplora_bridge_status() -> serde_json::Value {
    serde_json::json!({ "version": env!("CARGO_PKG_VERSION") })
}

/// `erplora_discover_printers` — re-escanea la red (mDNS + subred), registra y devuelve las
/// impresoras. Espejo de `Command::DiscoverPrinters` del bridge; devuelve el array directo.
#[tauri::command]
async fn erplora_discover_printers(
    state: tauri::State<'_, PeripheralsState>,
) -> Result<Vec<PrinterInfo>, HardwareError> {
    Ok(discovery::discover_printers(&state.registry).await?)
}

/// `erplora_get_devices` — contenido del registro persistente de dispositivos (con sus roles).
#[tauri::command]
fn erplora_get_devices(state: tauri::State<'_, PeripheralsState>) -> Vec<Device> {
    state.registry.get_all()
}

/// `erplora_print` — renderiza el documento ESC/POS y lo **encola** para envío con reintentos
/// (mismo flujo que `Command::Print` del bridge). Errores previos al encolado (printer_id/payload
/// inválidos) se devuelven; el resultado del envío llega por el worker de la cola (log).
#[tauri::command]
fn erplora_print(
    state: tauri::State<'_, PeripheralsState>,
    printer_id: String,
    document_type: String,
    data: serde_json::Value,
    job_id: Option<String>,
) -> Result<(), HardwareError> {
    let target = parse_printer_id(&printer_id)?;
    let payload = escpos::render_document(DocumentType::from_wire(&document_type), &data)?;
    state.queue.enqueue(PrintJob {
        job_id,
        target,
        payload,
        attempts: 0,
    })?;
    Ok(())
}

/// `erplora_test_print` — encola una página de prueba en la impresora dada.
#[tauri::command]
fn erplora_test_print(
    state: tauri::State<'_, PeripheralsState>,
    printer_id: String,
) -> Result<(), HardwareError> {
    let target = parse_printer_id(&printer_id)?;
    let payload = escpos::render_test_page(&printer_id);
    state.queue.enqueue(PrintJob {
        job_id: None,
        target,
        payload,
        attempts: 0,
    })?;
    Ok(())
}

/// `erplora_open_drawer` — abre el cajón vía kick ESC/POS por el socket de la impresora.
#[tauri::command]
async fn erplora_open_drawer(printer_id: String, pin: Option<u8>) -> Result<(), HardwareError> {
    let target = parse_printer_id(&printer_id)?;
    drawer::open_drawer(&target, pin.unwrap_or(2)).await?;
    Ok(())
}

/// `erplora_set_device_role` — asigna rol (receipt/kitchen/bar/label) y devuelve el registro
/// actualizado. Espejo de `Command::SetDeviceRole`.
#[tauri::command]
fn erplora_set_device_role(
    state: tauri::State<'_, PeripheralsState>,
    mac: String,
    role: String,
) -> Result<Vec<Device>, HardwareError> {
    state.registry.set_role(&mac, &role)?;
    Ok(state.registry.get_all())
}

/// `erplora_set_device_name` — renombra un dispositivo y devuelve el registro actualizado.
#[tauri::command]
fn erplora_set_device_name(
    state: tauri::State<'_, PeripheralsState>,
    mac: String,
    name: String,
) -> Result<Vec<Device>, HardwareError> {
    state.registry.set_name(&mac, &name)?;
    Ok(state.registry.get_all())
}

/// `erplora_remove_device` — elimina un dispositivo del registro y devuelve el registro actualizado.
#[tauri::command]
fn erplora_remove_device(
    state: tauri::State<'_, PeripheralsState>,
    mac: String,
) -> Result<Vec<Device>, HardwareError> {
    state.registry.remove(&mac)?;
    Ok(state.registry.get_all())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Deep-link de compra (F4, ADR-0114): habilita `openUrl` (navegador del sistema) para el
        // front (`lib/open-external.ts`). El permiso lo acota `capabilities/default.json`.
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            use tauri::Manager;
            // ADR-0050 (mismo origen): en desktop prod el runtime embebido sirve el `dist/` empaquetado,
            // para que el webview cargue front + datos del MISMO origen (loopback). `None` en dev/móvil.
            let web_dir = resolve_web_dir(app);
            let mut runtime_started = false;
            // Arranca el runtime local ANTES de que el webview lo necesite (login `/api/auth/cloud`,
            // query/command, entitlement). app_data_dir es la raíz de datos por-instalación.
            if let Ok(cache_dir) = app.path().app_data_dir() {
                // Primer arranque: el `app_data_dir` puede no existir aún en disco. Créalo antes de
                // tocarlo (SQLite/módulos/media/token cuelgan de aquí), o el runtime embebido muere
                // al abrir `erplora.db` (sqlx code 14: unable to open database file).
                if let Err(e) = std::fs::create_dir_all(&cache_dir) {
                    eprintln!(
                        "runtime embebido: no se pudo crear app_data_dir ({}): {e}",
                        cache_dir.display()
                    );
                }
                // Celda compartida del token de máquina: la siembra el keychain/fichero y se
                // conserva en el estado de Tauri para actualizarla en caliente tras enrolar/rotar.
                let cell: erplora_server::MachineToken =
                    std::sync::Arc::new(std::sync::RwLock::new(load_machine_token(&cache_dir)));
                let hub_id_cell: erplora_server::HubId =
                    std::sync::Arc::new(std::sync::RwLock::new(
                        load_hub_id(&cache_dir)
                            .unwrap_or_else(|| erplora_server::DEV_HUB_ID.to_string()),
                    ));
                app.manage(MachineIdentityHandle {
                    token: cell.clone(),
                    hub_id: hub_id_cell.clone(),
                });
                // Estado de hardware (issue #29): registro de dispositivos + cola de impresión, y
                // lanza el watchdog + el worker de la cola como tareas async del shell. `devices.json`
                // se persiste en `app_data_dir` (misma raíz por-instalación que el resto de datos).
                app.manage(build_peripherals_state(cache_dir.join(DEVICES_FILE)));
                spawn_embedded_runtime(cache_dir, cell, hub_id_cell, web_dir.clone());
                runtime_started = true;
            } else {
                eprintln!("runtime embebido: no se pudo resolver app_data_dir; no se arranca");
            }
            // Crea la ventana SIEMPRE (sin ventana no hay app). La URL se acopla al estado real
            // (C3/M2 del review): si el runtime no arrancó o no hay `dist/`, NO navega al loopback.
            if let Err(e) = open_main_window(app, runtime_started, web_dir.is_some()) {
                eprintln!("no se pudo crear la ventana principal: {e}");
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            validate_entitlement,
            device_context,
            enroll_device,
            rotate_machine_token,
            forget_hub,
            // Datos: NO van por `invoke` (ADR-0050) — el front habla HTTP+WS al runtime embebido.
            // Camino de hardware (issue #29): impresoras de red ESC/POS + cajón → peripherals.
            erplora_bridge_status,
            erplora_discover_printers,
            erplora_get_devices,
            erplora_print,
            erplora_test_print,
            erplora_open_drawer,
            erplora_set_device_role,
            erplora_set_device_name,
            erplora_remove_device
        ])
        .run(tauri::generate_context!())
        .expect("error while running ERPlora Tauri app");
}
