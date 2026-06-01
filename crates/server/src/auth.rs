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
