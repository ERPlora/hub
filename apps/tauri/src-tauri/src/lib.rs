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

// ── Camino de datos: handlers `invoke` → runtime embebido (issue #5) ────────────────────────────
//
// El runtime de negocio corre embebido como servidor Axum por loopback (`127.0.0.1:8787`, ver
// `embedded_serve_config`/`spawn_embedded_runtime`). El `IpcTransport` del SDK
// (`packages/module-sdk/src/index.ts:425`) invoca `erplora_query`/`erplora_command` con
// `{name, params}` / `{name, payload}` y espera de vuelta el **envelope** `{ok, data?, error?}`.
//
// La forma más simple y correcta de delegar (sin tocar la API pública de `erplora-server`, que es
// columna de otro worker) es **reenviar la invocación al mismo servidor loopback** por HTTP
// (`reqwest`, ya en el árbol de deps) hacia `POST /api/query` y `/api/command`, y devolver su JSON
// tal cual — exactamente lo que ya hace hoy `HttpWsTransport` desde `apps/web` (que en Tauri apunta
// a este mismo loopback). Así el envelope sale ya formado por el runtime (rutas en
// `crates/server/src/lib.rs:290-291`).
//
// Auth: en modo `Session` (el de `embedded_serve_config`) el runtime gatea query/command por la
// cabecera `X-Hub-Session` (más `X-Hub-Id` / `Authorization: Bearer` opcionales) —
// `crates/server/src/auth.rs::authenticate`. El contrato `invoke` del `IpcTransport` hoy NO viaja
// con esas cabeceras; para no CAMBIAR el contrato del SDK (columna del humano) estos handlers las
// aceptan como argumentos `invoke` **opcionales** (`Option<String>`), de modo que el frontend pueda
// adjuntar la sesión sin romper el shape `{name, params}` existente. Sin sesión, el runtime
// responde 401 en modo Session (comportamiento correcto). Ver nota de diseño en el reporte.

/// URL base del runtime embebido por loopback. Coincide con `embedded_serve_config().bind`.
const EMBEDDED_RUNTIME_URL: &str = "http://127.0.0.1:8787";

/// Error de los handlers de datos `invoke`. Se serializa como string para el frontend.
#[derive(Debug, thiserror::Error)]
pub enum IpcError {
    #[error("transporte loopback: {0}")]
    Transport(String),
}

impl serde::Serialize for IpcError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

/// Reenvía un POST JSON al runtime embebido (loopback) y devuelve el **envelope** crudo
/// (`{ok, data?, error?}`) como `serde_json::Value`. Adjunta las cabeceras de auth que el shell
/// haya recibido por `invoke` (sesión/hub/bearer), igual que `HttpWsTransport` desde `apps/web`.
async fn forward_to_runtime(
    path: &str,
    body: serde_json::Value,
    session: Option<String>,
    hub_id: Option<String>,
    bearer: Option<String>,
) -> Result<serde_json::Value, IpcError> {
    let client = reqwest::Client::new();
    let mut builder = client
        .post(format!("{EMBEDDED_RUNTIME_URL}{path}"))
        .header("Content-Type", "application/json");
    if let Some(s) = session.as_deref().filter(|s| !s.is_empty()) {
        builder = builder.header("X-Hub-Session", s);
    }
    if let Some(h) = hub_id.as_deref().filter(|s| !s.is_empty()) {
        builder = builder.header("X-Hub-Id", h);
    }
    if let Some(b) = bearer.as_deref().filter(|s| !s.is_empty()) {
        builder = builder.header("Authorization", format!("Bearer {b}"));
    }
    let resp = builder
        .json(&body)
        .send()
        .await
        .map_err(|e| IpcError::Transport(e.to_string()))?;
    // El runtime ya forma el envelope (incluso en 4xx: `{ok:false,error:…}`), así que devolvemos
    // el cuerpo tal cual sin tratar el status como error de transporte.
    resp.json::<serde_json::Value>().await.map_err(|e| IpcError::Transport(e.to_string()))
}

/// Handler `invoke` del camino de datos: ejecuta una **query** en el runtime embebido y devuelve
/// el envelope `{ok, data?, error?}`. Contrato del `IpcTransport` (`invoke('erplora_query',
/// {name, params})`). `session`/`hub_id`/`bearer` son opcionales (auth, ver nota arriba).
#[tauri::command]
async fn erplora_query(
    name: String,
    params: Option<serde_json::Value>,
    session: Option<String>,
    hub_id: Option<String>,
    bearer: Option<String>,
) -> Result<serde_json::Value, IpcError> {
    let body = serde_json::json!({ "name": name, "params": params.unwrap_or(serde_json::json!({})) });
    forward_to_runtime("/api/query", body, session, hub_id, bearer).await
}

/// Handler `invoke` del camino de datos: ejecuta un **command** en el runtime embebido y devuelve
/// el envelope `{ok, data?, error?}`. Contrato del `IpcTransport` (`invoke('erplora_command',
/// {name, payload})`).
#[tauri::command]
async fn erplora_command(
    name: String,
    payload: Option<serde_json::Value>,
    session: Option<String>,
    hub_id: Option<String>,
    bearer: Option<String>,
) -> Result<serde_json::Value, IpcError> {
    let body = serde_json::json!({ "name": name, "payload": payload.unwrap_or(serde_json::json!({})) });
    forward_to_runtime("/api/command", body, session, hub_id, bearer).await
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
#[cfg(target_os = "android")]
fn keyring_set(_token: &str) -> bool {
    false
}
#[cfg(target_os = "android")]
fn keyring_get() -> Option<String> {
    None
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
        f.write_all(token.as_bytes()).map_err(|e| GateError::Io(e.to_string()))?;
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
    let auth = Auth::UserJwt { hub_id, access: access_token };
    let req = if rotate { client.enroll_rotate(&auth) } else { client.enroll(&auth) };
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
    let cache_dir: PathBuf =
        app.path().app_data_dir().map_err(|e| GateError::Io(e.to_string()))?;
    let out = fetch_and_persist_token(&cache_dir, hub_id, access_token, false).await?;
    apply_persisted_token(&app, &cache_dir); // hot-reload: el runtime usa el token ya, sin reiniciar
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
    let cache_dir: PathBuf =
        app.path().app_data_dir().map_err(|e| GateError::Io(e.to_string()))?;
    let out = fetch_and_persist_token(&cache_dir, hub_id, access_token, true).await?;
    apply_persisted_token(&app, &cache_dir); // hot-reload del token rotado
    Ok(out)
}

/// Celda del token de máquina compartida entre el shell Tauri y el runtime embebido (**hot-reload**,
/// #22). Tras enrolar/rotar, el comando actualiza esta celda y el runtime toma el token nuevo en la
/// siguiente petición **sin reiniciar la app**. Vive en el estado gestionado de Tauri.
#[derive(Clone)]
struct MachineTokenHandle(erplora_server::MachineToken);

/// Actualiza la celda viva con el token recién persistido (keychain→fichero) tras enrolar/rotar.
fn apply_persisted_token(app: &tauri::AppHandle, cache_dir: &std::path::Path) {
    use tauri::Manager;
    if let Some(h) = app.try_state::<MachineTokenHandle>() {
        if let Ok(mut g) = h.0.write() {
            *g = load_machine_token(cache_dir);
        }
    }
}

/// Construye la config del **runtime embebido** (§11) para este dispositivo: SQLite + caché de
/// módulos en `app_data_dir`, modo `Session` (identidad local real, login PIN/JWT), y la **celda
/// compartida** del token de máquina (hot-reload). El `hub_id` sale de lo persistido al enrolar
/// (placeholder de dev hasta el primer enrol).
fn embedded_serve_config(
    cache_dir: &std::path::Path,
    machine_token_cell: erplora_server::MachineToken,
) -> erplora_server::ServeConfig {
    erplora_server::ServeConfig {
        sqlite_path: cache_dir.join("erplora.db").to_string_lossy().into_owned(),
        bind: "127.0.0.1:8787".to_string(),
        modules_dir: None, // los módulos se descargan en runtime desde el marketplace (no horneados)
        hub: erplora_server::HubConfig {
            hub_id: load_hub_id(cache_dir).unwrap_or_else(|| erplora_server::DEV_HUB_ID.to_string()),
            cloud_base_url: base_url(),
            module_cache: cache_dir.join("modules"),
            auth_mode: erplora_server::AuthMode::Session,
            jwt_public_key: None, // `serve()` la trae del Cloud si hay red (login cloud); PIN no la necesita
            cloud_api_token: None, // la celda compartida es la fuente del token (hot-reload)
            // DSN del remoto de sync (Cloud DB). Ausente en local-gratis → sync deshabilitado.
            cloud_db_url: std::env::var("HUB_CLOUD_DB_URL").ok().filter(|s| !s.trim().is_empty()),
        },
        machine_token_cell: Some(machine_token_cell),
    }
}

/// Arranca el runtime embebido (`erplora_server::serve`) en un **hilo dedicado con su propio
/// runtime tokio**, aislado del runtime async de Tauri. El webview le habla por loopback. El token
/// de máquina vive en la celda compartida: un enrol/rotación lo aplica **en caliente** (#22).
fn spawn_embedded_runtime(cache_dir: PathBuf, machine_token_cell: erplora_server::MachineToken) {
    std::thread::spawn(move || {
        let rt = match tokio::runtime::Builder::new_multi_thread().enable_all().build() {
            Ok(rt) => rt,
            Err(e) => {
                eprintln!("runtime embebido: no se pudo crear tokio: {e}");
                return;
            }
        };
        rt.block_on(async move {
            if let Err(e) =
                erplora_server::serve(embedded_serve_config(&cache_dir, machine_token_cell)).await
            {
                eprintln!("runtime embebido terminó: {e}");
            }
        });
    });
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
        let (events_tx, mut events_rx) =
            tokio::sync::mpsc::unbounded_channel::<WatchdogEvent>();
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
    state.queue.enqueue(PrintJob { job_id, target, payload, attempts: 0 })?;
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
    state.queue.enqueue(PrintJob { job_id: None, target, payload, attempts: 0 })?;
    Ok(())
}

/// `erplora_open_drawer` — abre el cajón vía kick ESC/POS por el socket de la impresora.
#[tauri::command]
async fn erplora_open_drawer(
    printer_id: String,
    pin: Option<u8>,
) -> Result<(), HardwareError> {
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
        .setup(|app| {
            use tauri::Manager;
            // Arranca el runtime local ANTES de que el webview lo necesite (login `/api/auth/cloud`,
            // query/command, entitlement). app_data_dir es la raíz de datos por-instalación.
            if let Ok(cache_dir) = app.path().app_data_dir() {
                // Celda compartida del token de máquina: la siembra el keychain/fichero y se
                // conserva en el estado de Tauri para actualizarla en caliente tras enrolar/rotar.
                let cell: erplora_server::MachineToken =
                    std::sync::Arc::new(std::sync::RwLock::new(load_machine_token(&cache_dir)));
                app.manage(MachineTokenHandle(cell.clone()));
                // Estado de hardware (issue #29): registro de dispositivos + cola de impresión, y
                // lanza el watchdog + el worker de la cola como tareas async del shell. `devices.json`
                // se persiste en `app_data_dir` (misma raíz por-instalación que el resto de datos).
                app.manage(build_peripherals_state(cache_dir.join(DEVICES_FILE)));
                spawn_embedded_runtime(cache_dir, cell);
            } else {
                eprintln!("runtime embebido: no se pudo resolver app_data_dir; no se arranca");
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            validate_entitlement,
            device_context,
            enroll_device,
            rotate_machine_token,
            // Camino de datos (issue #5): query/command → runtime embebido.
            erplora_query,
            erplora_command,
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
