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

use erplora_runtime::api_keys::{ApiKeyAccess, ApiKeyScope, ScopeEntry};

use crate::auth;
use crate::event_stream;
use crate::state::AppState;

// ── 1) Gestión de keys (auth = sesión admin owner/admin) ────────────────────────────────────

#[derive(Deserialize)]
pub struct CreateKeyReq {
    name: String,
    /// The per-module checkboxes. Only read when `access` is `custom` — which is what it defaults
    /// to, so a client written before hub#504 keeps meaning exactly what it meant.
    #[serde(default)]
    scope: Vec<ScopeEntry>,
    /// `full` · `read_only` · `write_only` · `custom` (hub#504). Same shape a user's role has.
    #[serde(default)]
    access: ApiKeyAccess,
    #[serde(default = "default_rate_limit")]
    rate_limit_per_minute: i64,
}

fn default_rate_limit() -> i64 {
    erplora_runtime::api_keys::DEFAULT_RATE_LIMIT_PER_MINUTE
}

/// Refusal of the admin gate, with the **stable code** every other door of this hub sends
/// (hub#1700): `unauthorized` when there is no usable session, `403 forbidden` when the session is
/// fine and the role is not (hub#660) — re-authenticating as the same cashier would never help.
///
/// One implementation on purpose ([`crate::auth_rejected`], the same one `outbox_admin` and the
/// assistant use). Until this issue these four handlers had their own copy that flattened both
/// cases into `401 {"error": "<prose>"}`, and the panel could only say «check your connection».
fn admin_unauthorized(e: auth::AuthError) -> Response {
    crate::auth_rejected(e)
}

/// Mapea un `RuntimeError` de la gestión de keys a una respuesta HTTP (mismo formato que el resto).
///
/// hub#1700: the shared envelope, not a hand-rolled `400 {"error": "<prose>"}`. It is what carries
/// the code of the refusals this door raises that are neither auth nor "gone" — the hub's own key
/// (`api_key.system_key`, `409`) and a rate limit out of range — and the status each one deserves.
fn key_err(e: erplora_runtime::RuntimeError) -> Response {
    crate::err_response(e)
}

/// GET /api/keys — lista las keys del hub (sin secreto). Auth = sesión admin.
pub async fn list_keys(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let rt = st.runtime.read().await;
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
    let rt = st.runtime.read().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(u) => u,
        Err(e) => return admin_unauthorized(e),
    };
    // Auditoría: quién creó la key (no es `apikey:…`, es el hub_user admin). Y nunca
    // `SYSTEM_CREATED_BY`: la marca de "la emitió el hub" no se puede pedir desde fuera.
    let created_by = format!("hub_user:{}", admin.id);
    let scope = ApiKeyScope {
        access: req.access,
        modules: req.scope,
    };
    match rt
        .create_api_key(&req.name, &scope, req.rate_limit_per_minute, &created_by)
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
    let rt = st.runtime.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return admin_unauthorized(e);
    }
    match rt.rotate_api_key(&id).await {
        Ok(Some(secret)) => {
            // hub#2522: the old secret is dead, and so is every live channel it opened.
            st.stream_limiter.cut(&event_stream::key_tag(&id));
            Json(json!({ "ok": true, "data": secret })).into_response()
        }
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
    let rt = st.runtime.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return admin_unauthorized(e);
    }
    match rt.revoke_api_key(&id).await {
        Ok(true) => {
            // hub#2522: a kill-switch that leaves the open channels listening is not one.
            st.stream_limiter.cut(&event_stream::key_tag(&id));
            Json(json!({ "ok": true })).into_response()
        }
        Ok(false) => key_not_found(),
        Err(e) => key_err(e),
    }
}

/// `404` for a key this hub does not have — revoked and forgotten, or never here at all.
///
/// The code is what the panel turns into «that key no longer exists» (hub#1700); before it, this
/// answer was indistinguishable from an unreachable hub for anybody reading the body.
fn key_not_found() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({
            "ok": false,
            "error": { "code": "not_found", "message": "API key no encontrada" },
        })),
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

/// `404` when the operation does not exist, does not belong to the `{module}` of the path, or is
/// not `expose_api` (first of the two gates, §5). Only a caller with a valid key gets here
/// (hub#2550), and it gets the same `404` for "does not exist" and "not exposed": the internal
/// surface does not leak to a third party.
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
    let rt = arc.read().await;

    // The key (and its quota) first, the operation second (hub#2550): looking the operation up
    // before the key answered `404` or `401` to anybody, and told them by trying names which
    // operations this hub has installed and open. The permission gate is `execute_query`'s.
    let ctx = match external_principal(&headers, &st.config, &rt).await {
        Ok(principal) => principal.context,
        Err(response) => return response,
    };
    // Gate 1: the operation exists, belongs to the module of the path and is `expose_api`.
    if !rt.registry().is_query_exposed(&module, &name) {
        return not_exposed("query", &module, &name);
    }

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
    let rt = arc.read().await;

    // Same order as `data_query` (hub#2550): key, quota, then the operation.
    let ctx = match external_principal(&headers, &st.config, &rt).await {
        Ok(principal) => principal.context,
        Err(response) => return response,
    };
    if !rt.registry().is_command_exposed(&module, &name) {
        return not_exposed("command", &module, &name);
    }

    match rt.execute_command(&name, &body.payload, &ctx).await {
        Ok(data) => Json(json!({ "ok": true, "data": data })).into_response(),
        Err(e) => crate::err_response(e),
    }
}
