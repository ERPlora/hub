//! **The REST contract of the automation kernel** (ADR-0283 K7 / §9, hub#661) — and it is FROZEN.
//!
//! ```text
//! GET/POST        /api/hub/flows                lista / crea
//! GET/PUT/DELETE  /api/hub/flows/{id}           PUT valida el documento y re-siembra los triggers
//! GET/PUT         /api/hub/flows/{id}/grants    replace COMPLETO, admin
//! POST            /api/hub/flows/{id}/run       disparo manual
//! GET             /api/hub/flows/{id}/runs      · GET /api/hub/flows/runs/{run_id} (con steps)
//! GET             /api/hub/flows/secrets        NOMBRES · PUT/DELETE …/secrets/{name} (write-only)
//! GET             /api/hub/flows/approvals      la bandeja (hub#665)
//! POST            /api/hub/flows/approvals/{id}/approve|reject
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
use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::flows::{approvals, grants, store, NewFlow};
use erplora_runtime::manifest::CapabilityKind;
use erplora_runtime::RuntimeError;
use serde_json::{json, Value};

use crate::auth;
use crate::state::AppState;

/// Default page of `GET …/runs` when the caller does not ask for one.
const RUNS_PAGE: i64 = 50;

/// The biggest page anybody may ask for. The runtime clamps it again — this is the door, not the
/// guarantee.
const MAX_RUNS_PAGE: i64 = store::MAX_RUNS_PAGE;

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
            store::ERR_FLOW_NOT_FOUND | approvals::ERR_APPROVAL_NOT_FOUND => {
                Some(StatusCode::NOT_FOUND)
            }
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

/// The header by which a caller names **the module it is acting for** (hub#714).
///
/// The editor of flows is a module (pm#110) and had no declared way in here: the SDK speaks
/// `query`/`command` to the dispatcher, and this surface is core REST on purpose. What it *could*
/// do was lift the session token out of `localStorage` and call the door itself — the module's Web
/// Component runs in the shell's own document, same origin, no sandbox. That works only while the
/// user is an admin and breaks the day the shell moves the session into an httpOnly cookie.
///
/// So `@erplora/module-sdk` gained a typed `flows` surface that stamps this header, and the header
/// is read HERE and nowhere else in the core: it is not an "act as this module" switch.
///
/// ⚠️ **It is a DECLARATION, not an authentication.** In a browser where every module shares one
/// document, nothing stops a module from writing another's id — but nothing stops it from reading
/// the session token either, so this is one gap, not two, and it closes when module components are
/// isolated. What the gate buys today is still real: the modules that may EVER administer flows
/// are fixed at install time by a **signed manifest** the owner saw and a grant they can revoke,
/// and the enforcement already lives server-side — the day the shell can prove who is calling,
/// only the provenance of this header improves and the kernel does not move.
const MODULE_HEADER: &str = "x-erplora-module";

/// The module the caller says it is acting for, if any. Blank is the same as absent: the shell
/// itself, `curl` with an admin session and the QA agent are not modules and name none.
fn calling_module(headers: &HeaderMap) -> Option<String> {
    headers
        .get(MODULE_HEADER)
        .and_then(|v| v.to_str().ok())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
}

/// Resolves the admin session and hands back the runtime plus «who is doing this», already in the
/// `hub_user:<id>` form the audit columns store.
///
/// **Two gates, and the order is not cosmetic** (hub#714). First the human: `require_admin_session`
/// is untouched, so an anonymous caller still gets `401` and a cashier still gets `403` — putting
/// the capability first would answer `403` to a caller who never authenticated. Then the module:
/// if the request names one, that module needs `manage_flows` **declared and granted**.
///
/// Both are mandatory and neither replaces the other. The session says «a person allowed to
/// administer this hub is here»; the capability says «and the owner chose THIS module as the tool
/// they administer it with». Without the second one, adding a flows surface to the SDK would have
/// handed the kernel to every installed module for free: the inventory app the owner installed
/// could write an automation that runs commands in their name while nobody is watching. That is an
/// escalation this change would have introduced, so it is gated in the same change.
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
        if let Some(module) = calling_module(&$headers) {
            if let Err(e) = rt
                .require_module_capability(&module, CapabilityKind::ManageFlows)
                .await
            {
                return crate::err_response(e);
            }
        }
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

/// `GET /api/hub/flows/{id}/runs?limit=&before=` — the history of one flow, newest first.
///
/// **It is paged, and the page is a cursor.** A hub with live flows makes runs without stopping
/// (that is what a flow is), so an unpaged listing is a screen that stops loading within a month of
/// somebody using this seriously. `before` is the id of the last run of the previous page — a
/// cursor and not an `OFFSET`, because runs keep arriving at the head while a person reads, and an
/// offset shifts the page under them: rows get served twice or skipped, and a count of "this sale
/// fired five steps" comes out as four.
pub async fn list_runs(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    Query(page): Query<RunsPage>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.lock().await;
    if let Err(e) = rt.get_flow(&id).await {
        return flow_err(e);
    }
    let limit = page.limit.unwrap_or(RUNS_PAGE).clamp(1, MAX_RUNS_PAGE);
    match rt.list_flow_runs(&id, limit, page.before.as_deref()).await {
        Ok(runs) => {
            // A cursor only when the page was full: a short page is the end of the history, and
            // handing out a cursor for it means one more request that answers nothing.
            let next = (runs.len() as i64 == limit)
                .then(|| runs.last().map(|r| r.id.clone()))
                .flatten();
            Json(json!({ "ok": true, "data": runs, "next_cursor": next })).into_response()
        }
        Err(e) => flow_err(e),
    }
}

/// The page a caller asked for. Both fields are optional: the plain URL still works.
#[derive(Debug, Default, serde::Deserialize)]
pub struct RunsPage {
    limit: Option<i64>,
    /// The id of the last run of the previous page — "older than this one".
    before: Option<String>,
}

// ── secrets (hub#662) ─────────────────────────────────────────────────────────────────────────

/// `GET /api/hub/flows/secrets` — **the names, never the values**.
///
/// There is no endpoint that returns a secret, and that is the design rather than an omission
/// (ADR-0283 §4): the only reader is the executor, while it builds the request that is about to
/// leave. A "reveal" button would turn one admin session into a copy of every API key the hub
/// holds, and a hub's credentials are its customer's, not ours.
pub async fn list_secrets(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.lock().await;
    match rt.list_flow_secrets().await {
        Ok(secrets) => Json(json!({ "ok": true, "data": secrets })).into_response(),
        Err(e) => flow_err(e),
    }
}

/// `PUT /api/hub/flows/secrets/{name}` — creates or rotates one. Body `{"value": "…"}`.
pub async fn put_secret(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(name): Path<String>,
    Json(body): Json<Value>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let Some(value) = body.get("value").and_then(|v| v.as_str()) else {
        return bad_request("invalid_payload", "a secret needs a `value`");
    };
    let rt = arc.lock().await;
    match rt.put_flow_secret(&name, value, &who).await {
        Ok(info) => Json(json!({ "ok": true, "data": info })).into_response(),
        Err(e) => flow_err(e),
    }
}

/// `DELETE /api/hub/flows/secrets/{name}` — a flow that references it stops working, loudly, which
/// is the point: it fails at the step instead of calling with an empty credential.
pub async fn delete_secret(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(name): Path<String>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let rt = arc.lock().await;
    match rt.delete_flow_secret(&name, &who).await {
        Ok(()) => Json(json!({ "ok": true, "data": { "name": name, "deleted": true } })).into_response(),
        Err(e) => flow_err(e),
    }
}

/// `GET /api/hub/flows/runs/{run_id}` — one run WITH its steps and the events it emitted.
///
/// The steps carry each step's resolved input, its output and its error: that is the only way to
/// answer «why did this flow do that?» after the fact. The events are the other half — they are
/// where the chain leaves the flow and continues into other modules, so «this sale set off these
/// five steps» can be followed all the way down instead of stopping at the run.
///
/// **Secrets never come out of here**: the steps are redacted against the flow's own definition in
/// the runtime (`flows::store::get_run`), so this is not a promise the HTTP layer has to keep.
pub async fn get_run(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(run_id): Path<String>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.lock().await;
    let (run, steps) = match rt.get_flow_run(&run_id).await {
        Ok(found) => found,
        Err(e) => return flow_err(e),
    };
    let events = match rt.events_of_run(&run_id).await {
        Ok(events) => events,
        Err(e) => return flow_err(e),
    };
    Json(json!({ "ok": true, "data": { "run": run, "steps": steps, "events": events } }))
        .into_response()
}

// ── approvals: the tray (hub#665, ADR-0283 D3) ────────────────────────────────────────────────

/// How many approvals `GET …/approvals` returns.
const APPROVALS_PAGE: i64 = 100;

/// `GET /api/hub/flows/approvals[?status=pending]` — what the hub proposed to do while nobody was
/// watching. Without `status` it lists everything, which is the audit of what it actually did.
pub async fn list_approvals(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.lock().await;
    let status = params.get("status").map(String::as_str).filter(|s| !s.is_empty());
    match rt.list_flow_approvals(status, APPROVALS_PAGE).await {
        Ok(items) => Json(json!({ "ok": true, "data": items })).into_response(),
        Err(e) => flow_err(e),
    }
}

/// `POST /api/hub/flows/approvals/{id}/approve` — runs **exactly** the proposed command, with the
/// grant re-checked at this moment and **without re-entering the model**
/// (`Runtime::decide_flow_approval`).
///
/// `decided_by` comes from the RESOLVED SESSION and is never read from the body — the same rule as
/// `discarded_by` in `outbox_admin.rs`, and here it is the whole audit: this row is the record of a
/// person authorising the hub to write.
pub async fn approve(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    decide(st, headers, id, true).await
}

/// `POST /api/hub/flows/approvals/{id}/reject` — nothing runs, and the run stops: the steps written
/// after an agent step assumed it acted.
pub async fn reject(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    decide(st, headers, id, false).await
}

async fn decide(st: AppState, headers: HeaderMap, id: String, approve: bool) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let rt = arc.lock().await;
    match rt.decide_flow_approval(&id, approve, &who).await {
        Ok(approval) => Json(json!({ "ok": true, "data": approval })).into_response(),
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
