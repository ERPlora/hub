//! Autenticación de la petición → `RequestContext` (ARQUITECTURA.md §2.3, §2.5, §2.9).
//!
//! Dos modos (`HubConfig::auth_mode`):
//!  - **Dev**: confía en `X-Hub-Id` + `X-User-Id` + `X-Permissions` que pone el frontend. Para
//!    desarrollo local sin Cloud.
//!  - **Session** (modelo real, §2.9): la **autoridad de identidad/permisos es LOCAL**. El login
//!    (PIN local o JWT de usuario cloud — ver handlers en `lib.rs`) abre una **sesión server-side**
//!    (`hub_session`) y devuelve un token opaco; cada petición lo manda en `X-Hub-Session` y aquí se
//!    resuelve a un `hub_user` y a los **permisos de su rol** (`role_permissions` de los módulos
//!    activos). El `hub_id` viene del **config de despliegue** (no del header, no spoofable).
//!
//! El JWT de usuario (RS256) es solo el **adaptador de login cloud** (`cloud_client::verify_user_jwt`
//! en el handler de login): prueba *quién* es el usuario cloud → se mapea a un `hub_user` local
//! (`get_or_link_cloud_user`) → se abre sesión. Nunca es la fuente de permisos.
use axum::http::HeaderMap;
use erplora_runtime::{RequestContext, Runtime};

use crate::state::{AuthMode, HubConfig};

const DEFAULT_HUB: &str = "local";
const DEFAULT_USER: &str = "local";

/// Error de autenticación. Se mapea a `401 Unauthorized` en los handlers.
#[derive(Debug)]
pub enum AuthError {
    MissingSession,
    Invalid(String),
}

impl AuthError {
    pub fn message(&self) -> String {
        match self {
            AuthError::MissingSession => "falta sesión (cabecera X-Hub-Session)".to_string(),
            AuthError::Invalid(e) => format!("no autenticado: {e}"),
        }
    }
}

/// Token de sesión del hub (cabecera `X-Hub-Session`), si viene.
pub fn session_token(headers: &HeaderMap) -> Option<String> {
    header(headers, "x-hub-session")
}

/// Autentica la petición y construye el `RequestContext` según el modo configurado.
/// - `Dev`: confía en cabeceras (`X-User-Id`/`X-Permissions`).
/// - `Session`: resuelve la sesión server-side → `hub_user` → permisos del rol (autoridad local).
pub async fn authenticate(
    headers: &HeaderMap,
    config: &HubConfig,
    rt: &Runtime,
) -> Result<RequestContext, AuthError> {
    match config.auth_mode {
        AuthMode::Dev => Ok(context_from_headers(headers)),
        AuthMode::Session => {
            let token = session_token(headers).ok_or(AuthError::MissingSession)?;
            let user = rt
                .resolve_session(&token)
                .await
                .map_err(|e| AuthError::Invalid(e.to_string()))?
                .ok_or_else(|| AuthError::Invalid("sesión inválida o caducada".into()))?;
            // hub_id del despliegue (no spoofable); user_id + permisos de la identidad LOCAL.
            let perms = rt.permissions_for_role(&user.role);
            Ok(RequestContext::new(config.hub_id.clone(), user.id, perms))
        }
    }
}

/// Modo Dev: confía en las cabeceras que pone el frontend (sin verificación). Solo desarrollo.
pub fn context_from_headers(headers: &HeaderMap) -> RequestContext {
    let hub = header(headers, "x-hub-id").unwrap_or_else(|| DEFAULT_HUB.to_string());
    let user = header(headers, "x-user-id").unwrap_or_else(|| DEFAULT_USER.to_string());
    let perms = header(headers, "x-permissions")
        .map(|s| s.split(',').map(|p| p.trim().to_string()).filter(|p| !p.is_empty()).collect::<Vec<_>>())
        .unwrap_or_else(|| vec!["*".to_string()]); // dev: sin gateway, admin por defecto
    RequestContext::new(hub, user, perms)
}

fn header(headers: &HeaderMap, name: &str) -> Option<String> {
    headers.get(name).and_then(|v| v.to_str().ok()).map(|s| s.to_string())
}

/// Extrae el token Bearer del header `Authorization`, si existe.
pub fn bearer(headers: &HeaderMap) -> Option<String> {
    header(headers, "authorization")
        .and_then(|h| h.strip_prefix("Bearer ").map(|t| t.trim().to_string()))
}

/// `X-Hub-Id` de la petición, con fallback al `hub_id` de despliegue (config).
pub fn hub_id(headers: &HeaderMap, fallback: &str) -> String {
    header(headers, "x-hub-id").unwrap_or_else(|| fallback.to_string())
}

/// Construye la credencial `Auth::UserJwt` (Bearer + `X-Hub-Id`) para hablar con el Cloud
/// en nombre del usuario activo (ARQUITECTURA.md §2.3). `None` si no hay JWT en la petición.
pub fn user_auth(headers: &HeaderMap, fallback_hub: &str) -> Option<cloud_client::Auth> {
    let access = bearer(headers)?;
    Some(cloud_client::Auth::UserJwt { hub_id: hub_id(headers, fallback_hub), access })
}
