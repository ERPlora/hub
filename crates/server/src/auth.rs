//! Extracción del contexto de petición desde las cabeceras (ARQUITECTURA.md §2.3, §2.5, §2.9).
//!
//! Hoy: confía en `X-Hub-Id` + `X-User-Id` + `X-Permissions` que pone el frontend tras el
//! login. Cuando exista `erplora-cloud-client`, aquí se validará el JWT del usuario / el
//! `X-Hub-Token` de máquina contra el Cloud Portal. La autoridad de permisos ya es del runtime.
use axum::http::HeaderMap;
use erplora_runtime::RequestContext;

const DEFAULT_HUB: &str = "local";
const DEFAULT_USER: &str = "local";

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
