//! **The REST contract of the automation kernel** (ADR-0283 K7 / §9, hub#661) — and it is FROZEN.
//!
//! ```text
//! GET/POST        /api/hub/flows                lista / crea
//! GET/PUT/DELETE  /api/hub/flows/{id}           PUT valida el documento y re-siembra los triggers
//! GET/PUT         /api/hub/flows/{id}/grants    replace COMPLETO, admin
//! POST            /api/hub/flows/{id}/run       disparo manual
//! GET             /api/hub/flows/{id}/runs      · GET /api/hub/flows/runs/{run_id} (con steps)
//! ```
//!
//! **Core REST, not `hub.*` commands.** The dispatcher is deliberately not where this goes
//! (ADR-0283 §9): the core is being frozen, and the precedent for core surface that is not a
//! module capability already exists — `api_keys`, `hub_users`, `print`, `elevation`. A flow is not
//! a module's data; it is the hub's own configuration, and it belongs on the same shelf.
//!
//! **Auth = the local session of a human owner/admin** (`api_keys.rs`, ADR-0057 §6), never an API
//! key and never the machine token. The reason is the grants: `PUT …/grants` is the screen where a
//! person decides what the hub may do while nobody is watching. Handing that to a stored,
//! copyable, long-lived integration credential would make the whole default-deny design decorative
//! — a key with flow access could grant itself every command in the hub through a flow.
//!
//! `granted_by`, `created_by` and `started_by` always come from the RESOLVED session, never from
//! the body (same rule as `discarded_by` in `outbox_admin.rs`).
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::flows::{grants, store, NewFlow};
use erplora_runtime::RuntimeError;
use serde_json::{json, Value};

use crate::auth;
use crate::state::AppState;

/// How many runs `GET …/runs` returns. The runtime caps it again; this is the page size.
const RUNS_PAGE: i64 = 50;

fn rejected(e: auth::AuthError) -> Response {
    let (status, code) = if e.is_forbidden() {
        (StatusCode::FORBIDDEN, "forbidden")
    } else {
        (StatusCode::UNAUTHORIZED, "unauthorized")
    };
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": e.message() } })),
    )
        .into_response()
}

fn bad_request(code: &str, message: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

/// The kernel's own errors, given the HTTP status they mean.
///
/// `RuntimeError::Domain` maps to `409` everywhere else, which is right for a business conflict
/// and wrong for these two: asking for a flow that is not in this hub is a `404` (and answering
/// `409` would make a caller retry something that will never exist), and a flow acting without a
/// grant is a `403`. Everything else — an invalid document, an unknown `schema_version` — is a
/// genuine conflict with what this hub accepts, so it falls through unchanged.
fn flow_err(e: RuntimeError) -> Response {
    if let RuntimeError::Domain { code, message } = &e {
        let status = match code.as_str() {
            store::ERR_FLOW_NOT_FOUND => Some(StatusCode::NOT_FOUND),
            grants::ERR_GRANT_DENIED => Some(StatusCode::FORBIDDEN),
            _ => None,
        };
        if let Some(status) = status {
            return (
                status,
                Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
            )
                .into_response();
        }
    }
    crate::err_response(e)
}

/// Reads `{name, enabled, definition}` off a request body. `enabled` defaults to **true**: the
/// person who just wrote a flow meant it to run, and an editor that saves silently-disabled flows
/// is one whose users think the kernel is broken.
fn new_flow(body: &Value) -> Result<NewFlow, Response> {
    let name = body
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .trim()
        .to_string();
    if name.is_empty() {
        return Err(bad_request("invalid_payload", "a flow needs a `name`"));
    }
    let Some(definition) = body.get("definition") else {
        return Err(bad_request(
            "invalid_payload",
            "a flow needs a `definition` document",
        ));
    };
    Ok(NewFlow {
        name,
        enabled: body.get("enabled").and_then(|v| v.as_bool()).unwrap_or(true),
        definition: definition.clone(),
    })
}

/// Resolves the admin session and hands back the runtime plus «who is doing this», already in the
/// `hub_user:<id>` form the audit columns store.
macro_rules! admin_session {
    ($st:expr, $headers:expr) => {{
        let arc = match $st.runtime_for(&$st.hub_id()).await {
            Ok(arc) => arc,
            Err(e) => return crate::tenant_rejected(e),
        };
        let rt = arc.lock().await;
        let admin = match auth::require_admin_session(&$headers, &$st.config, &rt).await {
            Ok(admin) => admin,
            Err(e) => return rejected(e),
        };
        let who = format!("hub_user:{}", admin.id);
        (arc.clone(), who)
    }};
}

// ── flows ─────────────────────────────────────────────────────────────────────────────────────

pub async fn list_flows(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.lock().await;
    match rt.list_flows().await {
        Ok(flows) => Json(json!({ "ok": true, "data": flows })).into_response(),
        Err(e) => flow_err(e),
    }
}

pub async fn create_flow(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let new = match new_flow(&body) {
        Ok(new) => new,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    match rt.create_flow(&new, &who).await {
        Ok(flow) => (StatusCode::CREATED, Json(json!({ "ok": true, "data": flow }))).into_response(),
        Err(e) => flow_err(e),
    }
}

pub async fn get_flow(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.lock().await;
    match rt.get_flow(&id).await {
        Ok(flow) => Json(json!({ "ok": true, "data": flow })).into_response(),
        Err(e) => flow_err(e),
    }
}

/// `PUT /api/hub/flows/{id}` — validates the document and **re-seeds `_flow_triggers`**, keeping
/// the clock of a trigger that did not change (`store::seed_triggers`).
pub async fn update_flow(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    Json(body): Json<Value>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let new = match new_flow(&body) {
        Ok(new) => new,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    match rt.update_flow(&id, &new, &who).await {
        Ok(flow) => Json(json!({ "ok": true, "data": flow })).into_response(),
        Err(e) => flow_err(e),
    }
}

/// `DELETE /api/hub/flows/{id}` — soft-delete. The row survives (it is the only record that this
/// automation ever existed), its triggers are disarmed and its grants revoked.
pub async fn delete_flow(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let rt = arc.lock().await;
    match rt.delete_flow(&id, &who).await {
        Ok(()) => Json(json!({ "ok": true, "data": { "id": id, "deleted": true } })).into_response(),
        Err(e) => flow_err(e),
    }
}

// ── grants ────────────────────────────────────────────────────────────────────────────────────

pub async fn list_grants(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.lock().await;
    if let Err(e) = rt.get_flow(&id).await {
        return flow_err(e);
    }
    match rt.list_flow_grants(&id).await {
        Ok(grants) => Json(json!({ "ok": true, "data": grants })).into_response(),
        Err(e) => flow_err(e),
    }
}

/// `PUT /api/hub/flows/{id}/grants` — a **complete replace** of `[{kind, value}]`.
///
/// A replace and not a patch because the question the screen answers is "what may this flow do?",
/// and that is a list a person reads whole. The list is refused as a whole if any entry names a
/// command that does not exist: half-applying it would leave the owner believing they granted
/// something they did not.
pub async fn replace_grants(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    Json(body): Json<Value>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let items = body.get("grants").cloned().unwrap_or(body);
    let wanted = match grants::parse_pairs(&items) {
        Ok(wanted) => wanted,
        Err(e) => return flow_err(e),
    };
    let rt = arc.lock().await;
    match rt.replace_flow_grants(&id, &wanted, &who).await {
        Ok(()) => match rt.list_flow_grants(&id).await {
            Ok(grants) => Json(json!({ "ok": true, "data": grants })).into_response(),
            Err(e) => flow_err(e),
        },
        Err(e) => flow_err(e),
    }
}

// ── runs ──────────────────────────────────────────────────────────────────────────────────────

/// `POST /api/hub/flows/{id}/run` — the `manual` trigger. It **starts** a run and returns its id;
/// the tick advances it. Executing it inline would hold the request open for the length of the
/// flow, delays included.
pub async fn start_run(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    body: Option<Json<Value>>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let input = body
        .map(|Json(v)| v.get("input").cloned().unwrap_or(v))
        .unwrap_or_else(|| json!({}));
    let rt = arc.lock().await;
    match rt.start_flow_run(&id, &input, &who).await {
        Ok(run_id) => (
            StatusCode::ACCEPTED,
            Json(json!({ "ok": true, "data": { "run_id": run_id, "status": "pending" } })),
        )
            .into_response(),
        Err(e) => flow_err(e),
    }
}

pub async fn list_runs(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.lock().await;
    if let Err(e) = rt.get_flow(&id).await {
        return flow_err(e);
    }
    match rt.list_flow_runs(&id, RUNS_PAGE).await {
        Ok(runs) => Json(json!({ "ok": true, "data": runs })).into_response(),
        Err(e) => flow_err(e),
    }
}

/// `GET /api/hub/flows/runs/{run_id}` — one run WITH its steps. The steps are the point: they carry
/// each step's resolved input, its output and its error, which is the only way to answer "why did
/// this flow do that?" after the fact.
pub async fn get_run(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(run_id): Path<String>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.lock().await;
    match rt.get_flow_run(&run_id).await {
        Ok((run, steps)) => {
            Json(json!({ "ok": true, "data": { "run": run, "steps": steps } })).into_response()
        }
        Err(e) => flow_err(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The full HTTP contract (sessions, statuses, the `runs/{id}` vs `{id}/runs` routing) lives in
    /// `tests/flows_api_test.rs`, against the real router. What belongs here is the body parsing,
    /// which is where a default silently changes behaviour.
    #[test]
    fn a_flow_defaults_to_enabled_because_nobody_writes_one_meaning_it_not_to_run() {
        let new = new_flow(&json!({ "name": "W", "definition": {} })).unwrap();
        assert!(new.enabled);
        let off = new_flow(&json!({ "name": "W", "definition": {}, "enabled": false })).unwrap();
        assert!(!off.enabled);
    }

    #[test]
    fn a_body_without_a_name_or_a_definition_is_refused_before_the_runtime_sees_it() {
        assert!(new_flow(&json!({ "definition": {} })).is_err());
        assert!(new_flow(&json!({ "name": "   ", "definition": {} })).is_err());
        assert!(new_flow(&json!({ "name": "W" })).is_err());
    }
}
