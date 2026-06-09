//! Autenticación de la petición → `RequestContext` (ARQUITECTURA.md §2.3, §2.5, §2.9).
//!
//! Dos modos (`HubConfig::auth_mode`):
//!  - **Dev**: confía en `X-Hub-Id` + `X-User-Id` + `X-Permissions` que pone el frontend tras el
//!    login. Para desarrollo local sin Cloud.
//!  - **Jwt**: **verifica** el access JWT del usuario (RS256) contra la clave pública del Cloud
//!    (`cloud_client::verify_user_jwt`). El `user_id` sale del token verificado (no del header,
//!    spoofable) y el `hub_id` del **config de despliegue** (1 contenedor = 1 hub, tampoco del
//!    header). La autoridad final de permisos sigue siendo el runtime.
//!
//! ⚠️ **Permisos por usuario — decisión de arquitectura PENDIENTE (columna del humano).** El JWT de
//! Cloud lleva solo identidad (`user_id` + `exp`), **no** permisos ni roles. Hasta decidir la fuente
//! (claim nuevo en el token, modelo de roles local del hub, o consulta a Cloud), el modo Jwt concede
//! `["*"]` al usuario autenticado — **igual que hoy** (Dev también concede `*`), sin regresión: lo
//! que esta capa añade es **identidad verificada** + `hub_id` no spoofable, no el gate de permisos.
use axum::http::HeaderMap;
use erplora_runtime::RequestContext;

use crate::state::{AuthMode, HubConfig};

const DEFAULT_HUB: &str = "local";
const DEFAULT_USER: &str = "local";

/// Error de autenticación (modo Jwt). Se mapea a `401 Unauthorized` en los handlers.
#[derive(Debug)]
pub enum AuthError {
    MissingToken,
    Invalid(String),
}

impl AuthError {
    pub fn message(&self) -> String {
        match self {
            AuthError::MissingToken => "falta Authorization: Bearer".to_string(),
            AuthError::Invalid(e) => format!("token inválido: {e}"),
        }
    }
}

/// Autentica la petición y construye el `RequestContext` según el modo configurado.
pub fn authenticate(headers: &HeaderMap, config: &HubConfig) -> Result<RequestContext, AuthError> {
    match config.auth_mode {
        AuthMode::Dev => Ok(context_from_headers(headers)),
        AuthMode::Jwt => {
            let pem = config
                .jwt_public_key
                .as_deref()
                .ok_or_else(|| AuthError::Invalid("modo jwt sin clave pública configurada".into()))?;
            let token = bearer(headers).ok_or(AuthError::MissingToken)?;
            let claims = cloud_client::verify_user_jwt(&token, pem)
                .map_err(|e| AuthError::Invalid(e.to_string()))?;
            // Identidad verificada del token; hub_id del despliegue (no del header). Permisos
            // diferidos a `*` (ver nota del módulo) — la decisión de scoping es del humano.
            Ok(RequestContext::new(config.hub_id.clone(), claims.user_id_str(), vec!["*".to_string()]))
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
