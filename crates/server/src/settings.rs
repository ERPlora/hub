//! Settings del hub — capa HTTP del store key/value de **sistema** (tabla `hub_settings`, migración
//! v4; lógica en `erplora_runtime::settings`).
//!
//! Dos endpoints, ambos montados en [`crate::app`]:
//!  - `GET /api/settings` → objeto con TODAS las claves conocidas (fila ∪ defaults). Auth =
//!    **cualquier sesión de usuario válida** (`require_user_session`): leer la config es inofensivo.
//!  - `PUT /api/settings` → body `{ currency?, language?, api_docs_enabled?, … }` (parcial). Valida
//!    y persiste. Auth = **sesión admin** (owner/admin, `require_admin_session`). Devuelve el objeto
//!    completo actualizado.
//!
//! El `hub_id` viene del despliegue (config, no spoofable); el runtime de la petición se resuelve
//! por org vía `runtime_for` (ADR-0005), igual que `api_keys.rs`. La validación de claves conocidas
//! la hace el runtime; aquí solo se mapea auth + errores a HTTP.
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::{json, Map, Value};

use crate::auth;
use crate::state::AppState;

/// `401` para fallo de auth (sin sesión / sesión inválida / rol insuficiente).
fn unauthorized(e: auth::AuthError) -> Response {
    (StatusCode::UNAUTHORIZED, Json(json!({ "ok": false, "error": e.message() }))).into_response()
}

/// GET /api/settings — objeto con todas las claves conocidas (fila ∪ defaults). Auth = sesión de
/// usuario válida (cualquier rol). Devuelve `{ currency, language, api_docs_enabled, … }` **plano**
/// (no envuelto en `{ok,data}`): es el contrato directo que consume el frontend.
pub async fn get_settings(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.config.hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.get_settings().await {
        Ok(settings) => Json(settings).into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// PUT /api/settings — aplica un mapa parcial de settings (valida cada clave; rechaza desconocidas o
/// valores inválidos → 422). Auth = sesión admin (owner/admin). Body = objeto plano
/// `{ "currency": "USD", "language": "en", … }`. Devuelve el objeto completo actualizado (plano).
pub async fn put_settings(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<Map<String, Value>>>,
) -> Response {
    let updates = body.map(|b| b.0).unwrap_or_default();
    let arc = match st.runtime_for(&st.config.hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(u) => u,
        Err(e) => return unauthorized(e),
    };
    // Auditoría: quién cambió la config (el `hub_user` admin de la sesión).
    let updated_by = format!("hub_user:{}", admin.id);
    match rt.set_settings(&updates, &updated_by).await {
        Ok(settings) => Json(settings).into_response(),
        Err(e) => crate::err_response(e),
    }
}
