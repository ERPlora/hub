//! Cliente de **pairing device-code** del Bridge (ADR-0154, hub#201).
//!
//! El Bridge standalone es una app **genérica** (mismo binario en toda máquina, sin vínculo a un
//! hub) que necesita una credencial para hablar con el SaaS **sin** que el operador copie tokens a
//! mano. Este módulo implementa el flujo device-code (estilo OAuth 2.0 Device Authorization Grant)
//! contra los endpoints `api/v1/bridge/` del SaaS (saas#811):
//!
//!   1. **Directo** — `pair_start` pide un `device_code` + `user_code`, abre el navegador en
//!      `verification_uri_complete`, y hace *poll* (`pair_poll`) respetando `interval`/`slow_down`
//!      hasta que el usuario aprueba (o expira). Al aprobar persiste el `bridge_device_token`.
//!   2. **Inverso** — si el usuario prefiere teclear el `user_code` en la UI local del Bridge,
//!      `pair_redeem` lo canjea (misma respuesta que un poll aprobado).
//!   3. **Refresh** — con el `bridge_device_token` persistido, `refresh_bridge_jwt` obtiene JWTs
//!      cortos (`POST token/` con `X-Bridge-Token`) para lo que necesite firmar hacia el SaaS.
//!
//! **Persistencia (0600):** el `bridge_device_token` + `hub_url` + `hub_id` (+ `hub_name` para la
//! UI/tray) se guardan en un fichero con permisos `0600`, igual que `BRIDGE_TOKEN_FILE` en
//! `auth.rs`. La verificación de los JWT que presenta la PWA (`auth.rs`) **no cambia**: este módulo
//! solo gestiona la credencial de MÁQUINA del Bridge hacia el SaaS.
//!
//! Los tests viven en `pairing_test.rs` (incluido con `#[path]`), escritos ANTES que esta
//! implementación (TDD): arrancan un SaaS mock en un puerto efímero y ejercen cada rama del
//! contrato (pending/slow_down/expired/denied/approved), la persistencia 0600 y el refresh.

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::{Deserialize, Serialize};

/// Env var de la ruta del fichero donde se persiste el emparejamiento (override para tests).
pub const ENV_PAIRING_FILE: &str = "BRIDGE_PAIRING_FILE";
/// Nombre por defecto del fichero de emparejamiento (junto al cwd, igual que `bridge-token`).
const DEFAULT_PAIRING_FILE: &str = "bridge-pairing.json";

/// Emparejamiento persistido del Bridge con un hub del SaaS. **No** contiene el `bridge_jwt` corto
/// (ese se re-mintea bajo demanda con [`refresh_bridge_jwt`]); solo la credencial de máquina de
/// larga vida (`bridge_device_token`) y los datos del hub para la UI.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Pairing {
    pub hub_id: String,
    pub hub_name: String,
    pub hub_url: String,
    /// Credencial de máquina de larga vida (secreto): se envía como `X-Bridge-Token` para re-mintar
    /// JWTs cortos. Persistida 0600; nunca se loggea ni se expone en `/status`.
    pub bridge_device_token: String,
    /// URL de la clave pública del SaaS para verificar los JWT que emite (informativa).
    #[serde(default)]
    pub saas_public_key_url: Option<String>,
}

/// Respuesta de `POST pair/start/` — el device-code y cómo hacer el poll.
#[derive(Debug, Clone, Deserialize)]
pub struct StartResponse {
    pub device_code: String,
    pub user_code: String,
    pub verification_uri: String,
    pub verification_uri_complete: String,
    pub expires_in: u64,
    pub interval: u64,
}

/// Datos entregados por el SaaS al aprobar el emparejamiento (poll o redeem).
#[derive(Debug, Clone)]
pub struct Approval {
    pub hub_id: String,
    pub hub_name: String,
    pub hub_url: String,
    /// JWT corto inicial que emite el SaaS al aprobar. El Bridge NO lo persiste (solo guarda el
    /// `bridge_device_token`); los JWT frescos se re-mintan con [`refresh_bridge_jwt`]. Campo del
    /// contrato conservado para el consumidor (WS/runtime); de ahí el `allow(dead_code)`.
    #[allow(dead_code)]
    pub bridge_jwt: String,
    #[allow(dead_code)]
    pub bridge_jwt_expires_in: u64,
    pub bridge_device_token: String,
    pub saas_public_key_url: Option<String>,
}

impl From<Approval> for Pairing {
    fn from(a: Approval) -> Self {
        Pairing {
            hub_id: a.hub_id,
            hub_name: a.hub_name,
            hub_url: a.hub_url,
            bridge_device_token: a.bridge_device_token,
            saas_public_key_url: a.saas_public_key_url,
        }
    }
}

/// Resultado de un poll/redeem, mapeado del contrato del SaaS.
#[derive(Debug, Clone)]
pub enum PollOutcome {
    /// El usuario aún no ha aprobado — seguir haciendo poll.
    Pending,
    /// Vamos demasiado rápido — subir el `interval` +5s (device-code estándar).
    SlowDown,
    /// Aprobado — credenciales listas.
    Approved(Approval),
    /// El usuario rechazó el emparejamiento.
    Denied,
    /// El `device_code`/`user_code` caducó.
    Expired,
}

/// Respuesta de `POST token/` — un `bridge_jwt` corto re-minteado. API pública consumida por los
/// tests y el futuro cableado del runtime/WS (aún no invocada en producción) → `allow(dead_code)`.
#[allow(dead_code)]
#[derive(Debug, Clone, Deserialize)]
pub struct TokenResponse {
    pub token: String,
    pub expires_in: u64,
    pub hub_url: String,
}

/// Errores tipados del flujo de pairing.
#[derive(Debug, thiserror::Error)]
pub enum PairingError {
    #[error("error de red hablando con el SaaS: {0}")]
    Http(String),
    #[error("el SaaS respondió {status}: {body}")]
    Status { status: u16, body: String },
    #[error("respuesta del SaaS ilegible: {0}")]
    Decode(String),
    #[error("respuesta de poll inesperada del SaaS: {0}")]
    Unexpected(String),
    #[error("el emparejamiento fue denegado por el usuario")]
    Denied,
    #[error("el código de emparejamiento caducó antes de aprobarse")]
    Expired,
    #[error("tiempo de emparejamiento agotado ({0}s) sin aprobación")]
    Timeout(u64),
    #[error("no se pudo persistir el emparejamiento: {0}")]
    Persist(String),
}

/// Ruta del fichero de emparejamiento (`BRIDGE_PAIRING_FILE`, por defecto junto al cwd).
pub fn pairing_file_path() -> PathBuf {
    std::env::var(ENV_PAIRING_FILE)
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(DEFAULT_PAIRING_FILE))
}

/// Cliente HTTP con timeouts acotados (una red hostil no debe colgar el Bridge).
pub fn http_client() -> reqwest::Client {
    reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(15))
        .build()
        .unwrap_or_default()
}

/// `true` si hay un emparejamiento persistido y legible. Helper público (tests / arranque
/// programático); en el runtime el estado vivo lo lleva `AppState.pairing` → `allow(dead_code)`.
#[allow(dead_code)]
pub fn is_paired(path: &Path) -> bool {
    load_pairing(path).is_some()
}

/// Carga el emparejamiento persistido, o `None` si no existe / no es legible / está corrupto.
pub fn load_pairing(path: &Path) -> Option<Pairing> {
    let raw = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&raw).ok()
}

/// Persiste el emparejamiento en JSON con permisos `0600` (mismo patrón que `persist_token` en
/// `auth.rs`): en unix restringe el fichero al dueño; el `bridge_device_token` es secreto.
pub fn save_pairing(path: &Path, pairing: &Pairing) -> Result<(), PairingError> {
    let json =
        serde_json::to_string_pretty(pairing).map_err(|e| PairingError::Persist(e.to_string()))?;
    std::fs::write(path, json).map_err(|e| PairingError::Persist(e.to_string()))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))
            .map_err(|e| PairingError::Persist(e.to_string()))?;
    }
    tracing::info!(path = %path.display(), "Bridge: emparejamiento persistido (0600)");
    Ok(())
}

/// Etiqueta de estado para el menú de la bandeja (ADR-0154). Pura para poder testearla sin GUI.
/// La consume el modelo del tray (feature `tray`) y los tests; sin la feature no se cablea en el
/// binario headless → `allow(dead_code)`.
#[allow(dead_code)]
pub fn status_label(pairing: Option<&Pairing>) -> String {
    match pairing {
        Some(p) => format!("Paired with {}", p.hub_name),
        None => "Not paired".to_string(),
    }
}

/// URL de un endpoint `bridge/` del SaaS, normalizando la barra final de la base.
fn endpoint(saas_url: &str, path: &str) -> String {
    format!("{}/api/v1/bridge/{}", saas_url.trim_end_matches('/'), path)
}

/// `POST {saas}/api/v1/bridge/pair/start/` con `{platform, version, host_name}`.
pub async fn pair_start(
    client: &reqwest::Client,
    saas_url: &str,
    platform: &str,
    version: &str,
    host_name: &str,
) -> Result<StartResponse, PairingError> {
    let resp = client
        .post(endpoint(saas_url, "pair/start/"))
        .json(&serde_json::json!({
            "platform": platform,
            "version": version,
            "host_name": host_name,
        }))
        .send()
        .await
        .map_err(|e| PairingError::Http(e.to_string()))?;
    let status = resp.status();
    if !status.is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(PairingError::Status { status: status.as_u16(), body });
    }
    resp.json::<StartResponse>()
        .await
        .map_err(|e| PairingError::Decode(e.to_string()))
}

/// Mapea el cuerpo JSON de un poll/redeem a [`PollOutcome`] según el contrato del SaaS (saas#811):
/// `{"status":"pending|denied|approved", ...}` | `{"error":"slow_down|expired"}`.
fn parse_poll(body: &serde_json::Value) -> Result<PollOutcome, PairingError> {
    if let Some(err) = body.get("error").and_then(|v| v.as_str()) {
        return match err {
            "slow_down" => Ok(PollOutcome::SlowDown),
            "expired" => Ok(PollOutcome::Expired),
            other => Err(PairingError::Unexpected(format!("error={other}"))),
        };
    }
    match body.get("status").and_then(|v| v.as_str()) {
        Some("pending") => Ok(PollOutcome::Pending),
        Some("denied") => Ok(PollOutcome::Denied),
        Some("approved") => Ok(PollOutcome::Approved(parse_approval(body)?)),
        Some(other) => Err(PairingError::Unexpected(format!("status={other}"))),
        None => Err(PairingError::Unexpected(body.to_string())),
    }
}

/// Extrae la [`Approval`] de un cuerpo `status:"approved"`.
fn parse_approval(body: &serde_json::Value) -> Result<Approval, PairingError> {
    let s = |key: &str| {
        body.get(key)
            .and_then(|v| v.as_str())
            .map(|s| s.to_string())
            .ok_or_else(|| PairingError::Decode(format!("falta el campo `{key}` en la aprobación")))
    };
    Ok(Approval {
        hub_id: s("hub_id")?,
        hub_name: s("hub_name")?,
        hub_url: s("hub_url")?,
        bridge_jwt: s("bridge_jwt")?,
        bridge_jwt_expires_in: body
            .get("bridge_jwt_expires_in")
            .and_then(|v| v.as_u64())
            .unwrap_or(0),
        bridge_device_token: s("bridge_device_token")?,
        saas_public_key_url: body
            .get("saas_public_key_url")
            .and_then(|v| v.as_str())
            .map(String::from),
    })
}

/// POST a un endpoint de poll/redeem con `body` y mapea la respuesta (independiente del status HTTP:
/// el device-code flow usa tanto 200 como 400 para señalar `pending`/`slow_down`/`expired`).
async fn post_poll(
    client: &reqwest::Client,
    url: String,
    body: serde_json::Value,
) -> Result<PollOutcome, PairingError> {
    let resp = client
        .post(url)
        .json(&body)
        .send()
        .await
        .map_err(|e| PairingError::Http(e.to_string()))?;
    let val: serde_json::Value = resp.json().await.map_err(|e| PairingError::Decode(e.to_string()))?;
    parse_poll(&val)
}

/// `POST {saas}/api/v1/bridge/pair/poll/` con `{device_code}` → [`PollOutcome`].
pub async fn pair_poll(
    client: &reqwest::Client,
    saas_url: &str,
    device_code: &str,
) -> Result<PollOutcome, PairingError> {
    post_poll(
        client,
        endpoint(saas_url, "pair/poll/"),
        serde_json::json!({ "device_code": device_code }),
    )
    .await
}

/// `POST {saas}/api/v1/bridge/pair/redeem/` con `{user_code}` → [`PollOutcome`] (flujo inverso).
pub async fn pair_redeem(
    client: &reqwest::Client,
    saas_url: &str,
    user_code: &str,
) -> Result<PollOutcome, PairingError> {
    post_poll(
        client,
        endpoint(saas_url, "pair/redeem/"),
        serde_json::json!({ "user_code": user_code }),
    )
    .await
}

/// `POST {saas}/api/v1/bridge/token/` con `X-Bridge-Token` → un `bridge_jwt` corto. API pública
/// para el runtime/WS (re-minta el JWT bajo demanda con el `bridge_device_token` persistido); aún
/// no invocada en producción → `allow(dead_code)` (consumida por tests).
#[allow(dead_code)]
pub async fn refresh_bridge_jwt(
    client: &reqwest::Client,
    saas_url: &str,
    bridge_device_token: &str,
) -> Result<TokenResponse, PairingError> {
    let resp = client
        .post(endpoint(saas_url, "token/"))
        .header("X-Bridge-Token", bridge_device_token)
        .send()
        .await
        .map_err(|e| PairingError::Http(e.to_string()))?;
    let status = resp.status();
    if !status.is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(PairingError::Status { status: status.as_u16(), body });
    }
    resp.json::<TokenResponse>()
        .await
        .map_err(|e| PairingError::Decode(e.to_string()))
}

/// Incremento estándar del intervalo al recibir `slow_down` (device-code / OAuth: +5s).
pub const SLOW_DOWN_BUMP: Duration = Duration::from_secs(5);

/// Bucle de poll: espera `interval`, hace `pair_poll`, sube el intervalo en `slow_down_bump` al
/// recibir `slow_down`, y corta al aprobar / denegar / expirar / agotar `timeout`. `slow_down_bump`
/// es un parámetro (no una constante fija) para que los tests ejerzan la rama `slow_down` en
/// milisegundos en vez de forzar una espera real de 5s; producción pasa [`SLOW_DOWN_BUMP`].
pub async fn poll_until_resolved(
    client: &reqwest::Client,
    saas_url: &str,
    device_code: &str,
    interval: Duration,
    slow_down_bump: Duration,
    timeout: Duration,
) -> Result<Approval, PairingError> {
    let deadline = tokio::time::Instant::now() + timeout;
    let mut interval = interval;
    loop {
        tokio::time::sleep(interval).await;
        if tokio::time::Instant::now() >= deadline {
            return Err(PairingError::Timeout(timeout.as_secs()));
        }
        match pair_poll(client, saas_url, device_code).await? {
            PollOutcome::Pending => {}
            PollOutcome::SlowDown => interval += slow_down_bump,
            PollOutcome::Approved(a) => return Ok(a),
            PollOutcome::Denied => return Err(PairingError::Denied),
            PollOutcome::Expired => return Err(PairingError::Expired),
        }
    }
}

/// Abre el navegador del sistema en `url` (best-effort). Si falla (headless / sin navegador),
/// degrada a un `warn` con la URL para que el operador la abra a mano — nunca aborta el pairing.
fn open_verification(url: &str) {
    match open::that(url) {
        Ok(_) => tracing::info!(%url, "Bridge: navegador abierto para el emparejamiento"),
        Err(e) => tracing::warn!(
            %url,
            error = %e,
            "Bridge: no pude abrir el navegador; abre esta URL para emparejar el hardware",
        ),
    }
}

/// Flujo directo completo: `pair_start` → abre el navegador (si `open_browser`) → `poll_until_resolved`
/// → persiste el emparejamiento. Devuelve el [`Pairing`] resultante.
#[allow(clippy::too_many_arguments)]
pub async fn run_direct_pairing(
    client: &reqwest::Client,
    saas_url: &str,
    path: &Path,
    platform: &str,
    version: &str,
    host_name: &str,
    open_browser: bool,
) -> Result<Pairing, PairingError> {
    let start = pair_start(client, saas_url, platform, version, host_name).await?;
    tracing::info!(
        user_code = %start.user_code,
        verification_uri = %start.verification_uri,
        "Bridge: empareja este equipo — código {} en {}",
        start.user_code,
        start.verification_uri,
    );
    if open_browser {
        open_verification(&start.verification_uri_complete);
    }
    let approval = poll_until_resolved(
        client,
        saas_url,
        &start.device_code,
        Duration::from_secs(start.interval),
        SLOW_DOWN_BUMP,
        Duration::from_secs(start.expires_in),
    )
    .await?;
    let pairing: Pairing = approval.into();
    save_pairing(path, &pairing)?;
    Ok(pairing)
}

#[cfg(test)]
#[path = "pairing_test.rs"]
mod tests;
