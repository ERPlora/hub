//! **The HTTP door of the owner's rules** (hub#1701, ADR-0476).
//!
//! ```text
//! GET/POST        /api/hub/policies              list / create
//! GET             /api/hub/policies/checkpoints  where a rule may be placed
//! GET/PUT/DELETE  /api/hub/policies/{id}
//! ```
//!
//! **Core REST, not `hub.*` commands** — same split as the flows (`flows_api.rs`, ADR-0283 §9): a
//! rule is not a module's data, it is the hub's own configuration, and it goes on the same shelf as
//! the keys, the users or the dead-letter.
//!
//! **Door = the local session of a PERSON who is owner/admin**, never an API key nor the machine
//! token. A rule decides whether a sale can be charged; a copyable integration credential, stored in
//! a third party's `.env`, does not decide that.
//!
//! 🔴 And **without a module capability**, unlike `admin_session!` of the flows: there the
//! capability exists because the SDK exposes the flows surface to the modules, and without it any
//! installed module could write itself an automation that runs commands on the owner's behalf. Here
//! there is no SDK surface to open — the rules are written from the hub's own screen — so asking for
//! a capability would be asking permission for a door that does not exist.
//!
//! `created_by`/`updated_by` ALWAYS come from the resolved session, never from the body (same rule
//! as `granted_by` in `flows_api.rs` and `discarded_by` in `outbox_admin.rs`).
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::policies::{self, NewPolicy};
use erplora_runtime::RuntimeError;
use serde_json::{json, Value};

use crate::auth;
use crate::state::AppState;

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

/// The HTTP status a `policy.*` code means — **by family, not case by case** (same rule as
/// [`crate::flows_api`], hub#734).
///
/// Every refusal of the core travels as `RuntimeError::Domain`, and `Domain` is `409` in the rest of
/// the hub. Here that would be false almost always: `409` tells the caller «retry, the state will
/// change» and none of these three things changes on its own. The owner's screen decides what to
/// paint by looking at the status **before** looking at the code, so the distinction has to be
/// there:
///
/// - `…not_found` → **404**. It does not exist: neither the rule, nor the checkpoint it claims to
///   gate.
/// - `policy.outcome_not_available` → **501**. The consequence IS in the vocabulary and this core
///   does not know how to apply it yet (`elevate:`, hub#1710). It is the only one of the family
///   fixed by **waiting for a release** instead of by correcting the rule, and telling it `400`
///   would send the owner off to rewrite something that is already right.
/// - the rest of `policy.` → **400**. What the caller sent wrong.
///
/// ⚠️ A code that does **not** start with `policy.` falls through to [`crate::err_response`]
/// untouched: a module's `not_found` is not this kernel's, and the suffix rule would happily claim
/// it. It is the first line on purpose, before looking at any suffix.
///
/// [`policies::ERR_BLOCKED`] is not mapped here and that is not an oversight: a rule in force denies
/// through `/api/commands/…`, which is the dispatcher's surface, not this one.
fn policy_status(code: &str) -> Option<StatusCode> {
    if !code.starts_with("policy.") {
        return None;
    }
    let status = match code {
        policies::ERR_OUTCOME_NOT_AVAILABLE => StatusCode::NOT_IMPLEMENTED,
        // `policy.not_found` carries a `.` where the others carry a `_`, so the suffix is compared
        // without it — and no code of the family ends in `not_found` meaning anything else.
        _ if code.ends_with("not_found") => StatusCode::NOT_FOUND,
        _ => StatusCode::BAD_REQUEST,
    };
    Some(status)
}

/// The core's errors, with the status [`policy_status`] says they mean.
fn policy_err(e: RuntimeError) -> Response {
    if let RuntimeError::Domain { code, message } = &e {
        if let Some(status) = policy_status(code) {
            return (
                status,
                Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
            )
                .into_response();
        }
    }
    crate::err_response(e)
}

/// Resolves the admin session and returns the runtime plus «who is doing this», already in the
/// `hub_user:<id>` shape the audit columns store.
///
/// Anonymous → `401`; cashier → `403`; API key → `401`/`403`, because `require_admin_session` only
/// looks at the local session and a key does not carry one.
macro_rules! admin_session {
    ($st:expr, $headers:expr) => {{
        let arc = match $st.runtime_for(&$st.hub_id()).await {
            Ok(arc) => arc,
            Err(e) => return crate::tenant_rejected(e),
        };
        let rt = arc.read().await;
        let admin = match auth::require_admin_session(&$headers, &$st.config, &rt).await {
            Ok(admin) => admin,
            Err(e) => return rejected(e),
        };
        let who = format!("hub_user:{}", admin.id);
        (arc.clone(), who)
    }};
}

/// Reads the body of a `POST`/`PUT`.
///
/// A body missing a field — or carrying `mode` as a number — is the caller's error, not the owner's:
/// it comes out as `400 invalid_payload` with serde's reason, which says exactly which field is
/// missing. The fields the person CAN get wrong while writing (the checkpoint, the condition, the
/// consequence, the message) are judged by `policies::validate`, with its own code.
fn new_policy(body: &Value) -> Result<NewPolicy, Response> {
    serde_json::from_value::<NewPolicy>(body.clone())
        .map_err(|e| bad_request("invalid_payload", &e.to_string()))
}

/// `GET /api/hub/policies/checkpoints` — where the owner may put a rule.
///
/// It comes from the Registry, not from the database: these are the checkpoints declared by the
/// modules **installed and active** right now. It is the list the screen needs in order to offer
/// places, and the same one that decides whether a stored rule still applies.
pub async fn list_checkpoints(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.read().await;
    Json(json!({ "ok": true, "data": rt.policy_checkpoints() })).into_response()
}

pub async fn list_policies(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.read().await;
    match rt.list_policies().await {
        Ok(policies) => Json(json!({ "ok": true, "data": policies })).into_response(),
        Err(e) => policy_err(e),
    }
}

pub async fn create_policy(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let new = match new_policy(&body) {
        Ok(new) => new,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    match rt.create_policy(&new, &who).await {
        Ok(policy) => (
            StatusCode::CREATED,
            Json(json!({ "ok": true, "data": policy })),
        )
            .into_response(),
        Err(e) => policy_err(e),
    }
}

pub async fn get_policy(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.read().await;
    match rt.get_policy(&id).await {
        Ok(policy) => Json(json!({ "ok": true, "data": policy })).into_response(),
        Err(e) => policy_err(e),
    }
}

/// `PUT /api/hub/policies/{id}` — the whole rule, not a patch: it is the same validation as the
/// creation, so promoting from `warn` to `enforce` goes through the same hoop as writing it.
pub async fn update_policy(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    Json(body): Json<Value>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let new = match new_policy(&body) {
        Ok(new) => new,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    match rt.update_policy(&id, &new, &who).await {
        Ok(policy) => Json(json!({ "ok": true, "data": policy })).into_response(),
        Err(e) => policy_err(e),
    }
}

/// `DELETE /api/hub/policies/{id}` — soft-delete: the row survives because it is the only record
/// that this rule was ever in force, and it stops applying on the very next command.
pub async fn delete_policy(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let rt = arc.read().await;
    match rt.delete_policy(&id, &who).await {
        Ok(()) => {
            Json(json!({ "ok": true, "data": { "id": id, "deleted": true } })).into_response()
        }
        Err(e) => policy_err(e),
    }
}
