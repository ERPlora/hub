//! API pública por módulo (ADR-0057, `architecture/hub/public-api.md`) — capa HTTP.
//!
//! Dos superficies, ambas montadas en [`crate::app`]:
//!
//! 1. **Gestión de keys** (`/api/keys…`): la maneja un admin desde el dashboard, autenticada por
//!    **sesión** (owner/admin), NO por una API key. Crear / listar / rotar / revocar.
//! 2. **Datos** (`/api/v1/{module}/q|c/…`): la consume el tercero con su `Authorization: Bearer
//!    erpl_live_…`. Mapeo 1:1 a las dos puertas del dispatcher (`execute_query`/`execute_command`)
//!    con la **doble puerta** del flag `expose_api` (la operación debe existir, pertenecer al
//!    `{module}` de la ruta y estar marcada `expose_api`).
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Map, Value};

use erplora_runtime::api_keys::ScopeEntry;

use crate::auth;
use crate::state::AppState;

// ── 1) Gestión de keys (auth = sesión admin owner/admin) ────────────────────────────────────

#[derive(Deserialize)]
pub struct CreateKeyReq {
    name: String,
    #[serde(default)]
    scope: Vec<ScopeEntry>,
    #[serde(default = "default_rate_limit")]
    rate_limit_per_minute: i64,
}

fn default_rate_limit() -> i64 {
    erplora_runtime::api_keys::DEFAULT_RATE_LIMIT_PER_MINUTE
}

/// `401` para fallo de auth del admin (sin sesión / sesión inválida / rol insuficiente).
fn admin_unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// Mapea un `RuntimeError` de la gestión de keys a una respuesta HTTP (mismo formato que el resto).
fn key_err(e: erplora_runtime::RuntimeError) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({ "ok": false, "error": e.to_string() })),
    )
        .into_response()
}

/// GET /api/keys — lista las keys del hub (sin secreto). Auth = sesión admin.
pub async fn list_keys(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return admin_unauthorized(e);
    }
    match rt.list_api_keys().await {
        Ok(keys) => Json(json!({ "ok": true, "data": keys })).into_response(),
        Err(e) => key_err(e),
    }
}

/// POST /api/keys — crea una key. Body `{name, scope:[{module,read,write}]}`. Devuelve el secreto
/// **una sola vez**: `{id, name, secret, prefix, scope}`. Auth = sesión admin.
pub async fn create_key(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CreateKeyReq>,
) -> Response {
    let rt = st.runtime.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(u) => u,
        Err(e) => return admin_unauthorized(e),
    };
    // Auditoría: quién creó la key (no es `apikey:…`, es el hub_user admin).
    let created_by = format!("hub_user:{}", admin.id);
    match rt
        .create_api_key(
            &req.name,
            &req.scope,
            req.rate_limit_per_minute,
            &created_by,
        )
        .await
    {
        Ok(secret) => Json(json!({ "ok": true, "data": secret })).into_response(),
        Err(e) => key_err(e),
    }
}

/// POST /api/keys/{id}/rotate — nuevo secreto (invalida el anterior). `{secret, …}` una vez.
/// 404 si la key no existe en este hub. Auth = sesión admin.
pub async fn rotate_key(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return admin_unauthorized(e);
    }
    match rt.rotate_api_key(&id).await {
        Ok(Some(secret)) => Json(json!({ "ok": true, "data": secret })).into_response(),
        Ok(None) => key_not_found(),
        Err(e) => key_err(e),
    }
}

/// DELETE /api/keys/{id} — revoca (kill-switch inmediato): `status='revoked'`. 404 si no existe.
/// Auth = sesión admin.
pub async fn revoke_key(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return admin_unauthorized(e);
    }
    match rt.revoke_api_key(&id).await {
        Ok(true) => Json(json!({ "ok": true })).into_response(),
        Ok(false) => key_not_found(),
        Err(e) => key_err(e),
    }
}

fn key_not_found() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({ "ok": false, "error": "API key no encontrada" })),
    )
        .into_response()
}

// ── 2) Superficie de datos (auth = Auth::ApiKey, capa A genérica) ───────────────────────────

#[derive(Deserialize, Default)]
pub struct DataBody {
    /// Para queries: params de filtro/orden/paginación. Para commands: el payload.
    #[serde(default)]
    params: Map<String, Value>,
    #[serde(default)]
    payload: Map<String, Value>,
}

/// `401` para fallo de auth de API key (token ausente/ inválido/ revocado).
fn api_unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// Auth + cuota para cualquier superficie consumida por terceros. La cuota vive en Postgres y se
/// consume antes del dispatcher, incluyendo replays idempotentes y errores de payload.
pub(crate) async fn external_principal(
    headers: &HeaderMap,
    config: &crate::state::HubConfig,
    rt: &erplora_runtime::Runtime,
) -> Result<erplora_runtime::api_keys::ApiKeyPrincipal, Response> {
    let principal = auth::api_key_principal(headers, config, rt)
        .await
        .map_err(api_unauthorized)?;
    let decision = rt
        .consume_api_key_rate_limit(&principal)
        .await
        .map_err(key_err)?;
    if !decision.allowed {
        let mut response = (
            StatusCode::TOO_MANY_REQUESTS,
            Json(json!({
                "ok": false,
                "error": { "code": "rate_limited", "message": "cuota de API key agotada" }
            })),
        )
            .into_response();
        if let Ok(value) =
            axum::http::HeaderValue::from_str(&decision.retry_after_seconds.to_string())
        {
            response
                .headers_mut()
                .insert(axum::http::header::RETRY_AFTER, value);
        }
        return Err(response);
    }
    Ok(principal)
}

/// `404` cuando la operación no existe, no pertenece al `{module}` de la ruta, o no está
/// `expose_api` (primera de las dos puertas, §5). NO revela si la operación existe pero es privada
/// (mismo 404 para "no existe" y "no expuesta"): no filtra la superficie interna a un tercero.
fn not_exposed(kind: &str, module: &str, name: &str) -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({
            "ok": false,
            "error": { "code": "not_found", "message": format!("{kind} `{name}` no expuesta en el módulo `{module}`") }
        })),
    )
        .into_response()
}

/// POST /api/v1/{module}/q/{query} — ejecuta `execute_query("{module}.{query}", params)` con la
/// **doble puerta** `expose_api` + gate de permisos del runtime. Auth = `Auth::ApiKey`.
pub async fn data_query(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path((module, query)): Path<(String, String)>,
    body: Option<Json<DataBody>>,
) -> Response {
    let name = format!("{module}.{query}");
    let body = body.map(|b| b.0).unwrap_or_default();

    // Enrutado multi-tenant (ADR-0005) por el `hub_id` del despliegue (la API key NO trae hub_id).
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;

    // Puerta 1: la operación debe existir, pertenecer al módulo de la ruta y estar `expose_api`.
    if !rt.registry().is_query_exposed(&module, &name) {
        return not_exposed("query", &module, &name);
    }
    // Auth de API key (puerta 2 = el gate de permisos lo aplica `execute_query` con el ctx de la key).
    let ctx = match external_principal(&headers, &st.config, &rt).await {
        Ok(principal) => principal.context,
        Err(response) => return response,
    };

    if rt.is_list_query(&name) {
        match rt.execute_query_page(&name, &body.params, &ctx).await {
            Ok(page) => Json(json!({ "ok": true, "data": page })).into_response(),
            Err(e) => crate::err_response(e),
        }
    } else {
        match rt.execute_query(&name, &body.params, &ctx).await {
            Ok(rows) => Json(json!({ "ok": true, "data": rows })).into_response(),
            Err(e) => crate::err_response(e),
        }
    }
}

/// POST /api/v1/{module}/c/{command} — ejecuta `execute_command("{module}.{command}", payload)`
/// con la misma doble puerta. Auth = `Auth::ApiKey`.
pub async fn data_command(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path((module, command)): Path<(String, String)>,
    body: Option<Json<DataBody>>,
) -> Response {
    let name = format!("{module}.{command}");
    let body = body.map(|b| b.0).unwrap_or_default();

    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;

    if !rt.registry().is_command_exposed(&module, &name) {
        return not_exposed("command", &module, &name);
    }
    let ctx = match external_principal(&headers, &st.config, &rt).await {
        Ok(principal) => principal.context,
        Err(response) => return response,
    };

    match rt.execute_command(&name, &body.payload, &ctx).await {
        Ok(data) => Json(json!({ "ok": true, "data": data })).into_response(),
        Err(e) => crate::err_response(e),
    }
}
