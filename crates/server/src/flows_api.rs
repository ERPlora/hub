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
//! GET             /api/hub/flows/schema         el contrato que ESTE core aplica (hub#716)
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
use erplora_runtime::flows::{agent, approvals, grants, secrets, store, templates, NewFlow};
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

/// The HTTP status a `flow.*` code means — **the whole family, by rule** (hub#734).
///
/// Every refusal of the kernel travels as `RuntimeError::Domain` (§13.8), and `Domain` is `409`
/// everywhere else in the hub. That is right for a business conflict and was wrong for almost
/// everything here: a `schema_version` this core does not know, an unreadable `cron`, a secret name
/// that does not exist — all of them answered `409 Conflict`, which tells a caller to retry
/// something that will never change. §9 says this contract FREEZES, and a frozen contract has to be
/// programmable: the editor of flows decides what to paint from the status before it looks at the
/// code.
///
/// The mapping is **by family, not case by case**, so a code added tomorrow lands somewhere sane
/// without anybody remembering this function:
///
/// - `…not_found` → **404**. It does not exist — flow, approval, secret, recipient.
/// - `…_kind_not_available` → **501**. A *kind* of the frozen vocabulary this core cannot execute
///   yet. Not `flow.secret_not_available`, which is the rule «a secret is only readable from an
///   `http` step» and is a plain document error.
/// - everything else under `flow.` → **400**. The overwhelming majority: the document, the grant or
///   the name the caller sent is one the server cannot accept.
///
/// …and four exceptions ahead of the rule, each one a status the family default would get wrong:
///
/// - **403** for the three refusals by authority (`grant_denied`, `internal_command` — the latter
///   with the same status the dispatcher gives `RuntimeError::InternalCommand` — and
///   `approval_not_yours`, hub#950: authenticated, just not who the question was addressed to);
/// - **409** for the real conflicts, the ones `409` was always for: the request is well formed, the
///   caller is allowed, and the STATE says no;
/// - **409** for `secrets_key_missing` — this hub is not set up to hold secrets, the same shape as
///   `fiscal_precondition_failed`, with a remedy that is a deploy setting and not the request;
/// - **500** for `secret_unreadable` — a row of this hub that will not decrypt is nobody's request.
///
/// A code that is **not** `flow.*` falls through to [`crate::err_response`] unchanged: a module's
/// domain error reaching here through `POST …/run` keeps the one table it has everywhere else.
///
/// One whole class of `flow.*` code is deliberately absent: the **step-failure classifications**
/// — `flow.definition_gone`, `flow.io_step_gone`, `flow.step_output_lost` (`flows::executor`),
/// `flow.http_timeout`, `flow.http_blocked`, `flow.http_status` (`flow_io`), `flow.agent_timeout`,
/// `flow.agent_upstream`, `flow.agent_max_iters` (`agent_runner`) and `flow.release_revoked`
/// (`outbox`). They are stamped on a run row or an outbox row by a background tick; `POST …/run`
/// answers `202` long before any of them exists, so none of them can ever be the body of a
/// response here. Giving them a status would advertise a door they do not have.
fn flow_status(code: &str) -> Option<StatusCode> {
    // The namespace gate comes FIRST, before any suffix is looked at: a module's `not_found` is not
    // this kernel's, and the suffix rules below would happily claim it.
    if !code.starts_with("flow.") {
        return None;
    }
    let status = match code {
        // …and the third refusal by authority (hub#950): the caller authenticated, and is simply
        // not who the question was addressed to. `403` and not `409`: the state is fine, the
        // person is not the one who may change it.
        grants::ERR_GRANT_DENIED
        | grants::ERR_INTERNAL_COMMAND
        | approvals::ERR_APPROVAL_NOT_YOURS
        // …and the fourth (hub#1677): the caller is a module naming an automation of ANOTHER
        // module. Authenticated, allowed to administer this hub, and simply not the owner of the
        // recipe it is pointing at.
        | templates::ERR_TEMPLATE_NOT_YOURS => StatusCode::FORBIDDEN,
        approvals::ERR_APPROVAL_ALREADY_DECIDED
        | approvals::ERR_APPROVAL_EXPIRED
        | store::ERR_FLOW_DELETED
        | agent::ERR_NOT_IN_FLIGHT
        | ERR_FLOW_DISABLED
        | secrets::ERR_SECRETS_KEY_MISSING => StatusCode::CONFLICT,
        secrets::ERR_SECRET_UNREADABLE => StatusCode::INTERNAL_SERVER_ERROR,
        // `flow.not_found` has a `.` where the others have a `_`, so the suffix is matched without
        // it — and no code in the namespace ends in `not_found` meaning anything else.
        _ if code.ends_with("not_found") => StatusCode::NOT_FOUND,
        _ if code.ends_with("_kind_not_available") => StatusCode::NOT_IMPLEMENTED,
        _ => StatusCode::BAD_REQUEST,
    };
    Some(status)
}

/// The one refusal of the family that the runtime spells inline (`flows::executor`) instead of
/// exporting: a manual run of a flow whose author turned it off. Named here so [`flow_status`] can
/// list it with the other conflicts instead of matching a bare string.
///
/// It is a copy of a literal, so it can drift — and what stops it is not a comment:
/// `tests/flows_api_test.rs::a_disabled_flow_refuses_to_be_run_by_hand` asks the real router and
/// would answer `400` the day the runtime renames it, because it would fall to the family default.
/// Publishing it from the runtime is the proper fix and belongs with whoever owns that file.
const ERR_FLOW_DISABLED: &str = "flow.disabled";

/// The kernel's own errors, given the HTTP status [`flow_status`] says they mean.
fn flow_err(e: RuntimeError) -> Response {
    if let RuntimeError::Domain { code, message } = &e {
        if let Some(status) = flow_status(code) {
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
        enabled: body
            .get("enabled")
            .and_then(|v| v.as_bool())
            .unwrap_or(true),
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

/// The `manage_flows` half of the gate: if the request NAMES a module, that module must have the
/// capability declared in its manifest and granted by the owner. A request that names none passes
/// — the shell and `curl` with an admin session are not modules.
///
/// Shared with the event-shape door (`outbox_admin::event_shape`, hub#715), which the same editor
/// reads through and which therefore has to be behind the same two gates. One implementation on
/// purpose: two copies of a default-deny check is how one of them ends up being the lenient one.
pub(crate) async fn require_flows_capability(
    headers: &HeaderMap,
    rt: &erplora_runtime::Runtime,
) -> Result<(), Response> {
    require_module_capability(headers, rt, CapabilityKind::ManageFlows)
        .await
        .map(|_| ())
}

/// The same gate for **any** capability a core door hangs on (hub#1108): if the request NAMES a
/// module, that module must have `kind` declared in its manifest and granted by the owner; a
/// request that names none passes, because the shell, `curl` with an admin session and the QA agent
/// are not modules.
///
/// One implementation, parameterised, rather than one copy per door: two copies of a default-deny
/// check is how one of them ends up being the lenient one. The print queue's recovery gestures use
/// it with [`CapabilityKind::Printer`] — the capability the owner already grants for "this module
/// may reach the printer" — for the same reason flows use `manage_flows`: without it, a typed SDK
/// surface would hand every installed module the power to bin another module's tickets the moment
/// an admin happens to be logged in.
///
/// **Hands back WHICH module walked through** (hub#1532), or `None` when the caller named none.
/// The gate had to resolve it to check the grant and then dropped it, so the one layer that knows
/// the answer to «which module did this?» was also the only one that never wrote it down. Returning
/// it costs nothing and is the only honest source: it is the name the grant was checked against,
/// not a second read of the header, which is what would let the two drift apart.
pub(crate) async fn require_module_capability(
    headers: &HeaderMap,
    rt: &erplora_runtime::Runtime,
    kind: CapabilityKind,
) -> Result<Option<String>, Response> {
    let Some(module) = calling_module(headers) else {
        return Ok(None);
    };
    rt.require_module_capability(&module, kind)
        .await
        .map_err(crate::err_response)?;
    Ok(Some(module))
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
        let rt = arc.read().await;
        let admin = match auth::require_admin_session(&$headers, &$st.config, &rt).await {
            Ok(admin) => admin,
            Err(e) => return rejected(e),
        };
        if let Err(response) = crate::flows_api::require_flows_capability(&$headers, &rt).await {
            return response;
        }
        let who = format!("hub_user:{}", admin.id);
        (arc.clone(), who)
    }};
}

/// The same human door **without** the module capability (hub#1677, ADR-0470).
///
/// Three doors use it and no more: turning a factory recipe on, turning it off, and reading the
/// listing they are turned on from. What they have in common is that the caller does not COMPOSE
/// anything — it picks which of the recipes its own publisher already wrote, signed and had
/// validated by the toolkit gate. Asking for `manage_flows` there would be asking for «the
/// capability with the widest reach of all» in order to press one switch, and it would be asked for
/// in the very screen the owner went to precisely to avoid Settings → Permissions.
///
/// 🔴 **It is not a second copy of the gate — it is the gate with one half deliberately absent, and
/// the missing half is replaced by a NARROWER rule at the call site**: `activate`/`deactivate`
/// refuse a module that names an automation which is not its own, and the listing serves such a
/// module only its own recipes. Nothing here is more permissive than `admin_session!` for anybody
/// who is not the recipe's own module.
///
/// The human half does not move: anonymous is still `401` and a cashier still `403`. Turning an
/// automation on IS getting the hub's primitives with nobody watching (ADR-0283 §9), and no new
/// route opens that.
macro_rules! admin_session_no_capability {
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

/// **A module may only point at its OWN recipes** (ADR-0470 §1).
///
/// A request that names no module passes: the shell is not a module and names none, and it is the
/// only surface that reaches this without a header today.
///
/// ⚠️ Same honest limit as the rest of `X-Erplora-Module`: in the browser the id is DECLARED, not
/// authenticated. It is one gap and not two — a module that would lie here can already read the
/// session token out of the same document — and it closes when module components are isolated.
fn refuse_unless_own(headers: &HeaderMap, module: &str) -> Result<(), Response> {
    match calling_module(headers) {
        Some(caller) if caller != module => Err(flow_err(RuntimeError::Domain {
            code: templates::ERR_TEMPLATE_NOT_YOURS.to_string(),
            message: format!(
                "`{caller}` cannot turn the automations of `{module}` on or off: a module only \
                 activates its own"
            ),
        })),
        _ => Ok(()),
    }
}

// ── flows ─────────────────────────────────────────────────────────────────────────────────────

pub async fn list_flows(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.read().await;
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
    let rt = arc.read().await;
    match rt.create_flow(&new, &who).await {
        Ok(flow) => (
            StatusCode::CREATED,
            Json(json!({ "ok": true, "data": flow })),
        )
            .into_response(),
        Err(e) => flow_err(e),
    }
}

pub async fn get_flow(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.read().await;
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
    match rt.delete_flow(&id, &who).await {
        Ok(()) => {
            Json(json!({ "ok": true, "data": { "id": id, "deleted": true } })).into_response()
        }
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
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

// ── the contract itself (hub#716) ─────────────────────────────────────────────────────────────

/// `GET /api/hub/flows/schema` — **the flow contract this core enforces**, plus the version that
/// enforces it.
///
/// `schemas/flow.schema.json` shipped with the hub and was reachable by nobody: no route, no npm
/// package. The visual editor is a module installed from the marketplace and updated on its own
/// clock (hub#516), so it would have had to carry a copy — a photo of whichever core it was built
/// against. On a park of hubs running different versions that copy is wrong for somebody by
/// construction: an editor ahead of its hub offers a step the hub refuses to save, and an editor
/// behind it hides one that works. Asking the hub is the only answer that survives the park.
///
/// The body is [`erplora_runtime::flows::flow_schema`], which is the file EMBEDDED at compile
/// time — not a copy maintained here, and not a file read from disk next to the binary.
/// `crates/runtime/tests/flow_schema_matches_the_runtime.rs` already keeps that file honest
/// against `flows::def`, so serving those exact bytes extends the guarantee to the consumer:
/// what the editor validates against is what the hub judges with.
///
/// **Same door as the rest of §9**, and the document is not the reason. An unauthenticated route
/// that reports the exact core version is a fingerprint of the hub for anyone who can reach the
/// origin, and a surface with one exception is a surface nobody remembers the rule of.
pub async fn get_schema(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (_arc, _) = admin_session!(st, headers);
    Json(json!({
        "ok": true,
        "data": {
            // The document version, so an editor can refuse to open something this core cannot run.
            "schema_version": erplora_runtime::flows::SCHEMA_VERSION,
            // …and WHICH core answered, which is the whole reason this is asked instead of bundled.
            "core_version": crate::version::HUB_VERSION,
            "schema": erplora_runtime::flows::flow_schema(),
        }
    }))
    .into_response()
}

/// `GET /api/hub/flows/templates` — las automatizaciones que traen DE FÁBRICA los módulos
/// instalados (hub#1611).
///
/// La galería del módulo `flows` ofrecía solo las plantillas escritas dentro de sí misma, así que
/// un negocio que instalaba el módulo de WhatsApp no encontraba la automatización que ese módulo
/// trae consigo: había que construirla a mano, paso a paso. Los módulos ya la publican —la carpeta
/// `flows/` viaja en el zip desde `module-toolkit#209`— y el runtime ya la registra al instalar;
/// esto es lo que la saca a la pantalla.
///
/// Se sirve del **registro**, no del disco: la carga la hizo el instalador, y `rehydrate_installed`
/// vuelve a pasar por él en cada arranque. Así esta ruta no toca el sistema de ficheros por
/// petición, y un módulo pausado no ofrece plantillas porque no está activo en el registro.
///
/// Por plantilla: el **módulo de origen** (la galería tiene que decir de dónde sale lo que ofrece),
/// la **familia**, los **documentos por idioma** (el `en` es la fuente, ADR-0055/0199; se sirven
/// todos porque `erplora validate` garantizó que son la misma automatización con otras palabras),
/// los **grants que pedirá** y el **suelo de versión por plantilla**.
///
/// 🔴 Los `grants` que van aquí son **una petición, no una concesión**: se le enseñan al dueño para
/// que los autorice él. Una plantilla nace apagada y sin permisos, como cualquier otra.
///
/// Y viajan **con su `payload`** (hub#1623, hub#1654): el pin es parte de lo que el permiso DICE, no
/// decoración — «puede anular citas» y «puede anular citas COMO CLIENTA» son permisos distintos, y
/// solo el segundo es seguro en una receta cuyo payload redacta un modelo leyendo el mensaje de un
/// desconocido. La galería lo pinta y lo devuelve tal cual en `PUT …/flows/{id}/grants`, que es
/// donde acaba en la fila de `_flow_grants` que `check_payload_pin` exige después. Un pin perdido
/// en este tramo es un permiso ANCHO concedido por un dueño que creyó estar acotándolo, y **sin un
/// solo error en pantalla**.
pub async fn list_templates(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, _) = admin_session_no_capability!(st, headers);
    let rt = arc.read().await;
    // 🔴 **Who gets to see WHAT** (hub#1677, ADR-0470 §5). Until here this door asked the caller for
    // `manage_flows`, and the module that most needs to read it does not declare it on purpose:
    // `whatsapp_inbox` ships the recipe and paints the screen that turns it on, and asking it for
    // «the capability with the widest reach of all» to read its own card is the very trip through
    // Settings → Permissions that ADR-0470 exists to remove.
    //
    // So the capability stops being a gate and becomes the SCOPE:
    //   · no module named (the shell)          → the whole gallery, as before;
    //   · a module WITH `manage_flows`         → the whole gallery, as before (this is the editor);
    //   · a module WITHOUT it                  → its own recipes and its own discards, nothing else.
    // Nobody is served more than they were; the third case used to be a flat `capability_denied`.
    let only_mine = match calling_module(&headers) {
        None => None,
        Some(module) => {
            if rt
                .has_module_capability(&module, CapabilityKind::ManageFlows)
                .await
            {
                None
            } else {
                Some(module)
            }
        }
    };
    let mine = |module_id: &str| only_mine.as_deref().is_none_or(|own| own == module_id);
    // What this hub has already built from a recipe, so the module's card can say «active» or
    // «paused» instead of guessing by trigger event + command — the heuristic of wi#79, which could
    // not tell two families of the same module apart.
    let installed = match rt.installed_flow_templates().await {
        Ok(installed) => installed,
        Err(e) => return flow_err(e),
    };
    let data: Vec<_> = rt
        .registry()
        .flow_templates()
        .into_iter()
        .filter(|(module_id, _)| mine(module_id))
        .map(|(module_id, tpl)| {
            json!({
                "module": module_id,
                "family": tpl.family,
                "documents": tpl.documents,
                "grants": tpl.grants,
                "requires": tpl.requires,
                // `null` and not absent when it is not installed: the screen has to tell «no» from
                // «this hub is too old to know», and an absent key reads as the second one.
                "installed": installed
                    .get(&templates::template_ref(module_id, &tpl.family))
                    .map(|(flow_id, enabled)| json!({ "flow_id": flow_id, "enabled": enabled }))
                    .unwrap_or(Value::Null),
            })
        })
        .collect();
    // Y lo que este hub NO ofrece, con su motivo (hub#1649). Va en la misma respuesta a propósito:
    // la pantalla donde se nota que una automatización falta es esta, y una galería que solo
    // enumera lo que hay deja «el módulo no trae ninguna» y «la trae y el hub la ha descartado»
    // exactamente iguales. Se lee el `code`; el `detail` es prosa para una persona (ADR-0055).
    let discarded: Vec<_> = rt
        .registry()
        .flow_template_discards()
        .into_iter()
        .filter(|(module_id, _)| mine(module_id))
        .map(|(module_id, discard)| {
            let mut row = json!({
                "module": module_id,
                "family": discard.family,
                "code": discard.code,
                "detail": discard.detail,
            });
            // hub#2123: the neighbour a floor names, as data. Only the floor codes carry it; on
            // the rest the key is absent, not `null` (a `null` would read as «no neighbour needed»).
            if let Some(requires) = &discard.requires {
                row["requires"] = json!(requires);
            }
            row
        })
        .collect();
    Json(json!({ "ok": true, "data": data, "discarded": discarded })).into_response()
}

/// `POST /api/hub/flows/templates/{module}/{family}/activate` — **the one tap** (hub#1677,
/// ADR-0470).
///
/// Builds the module's own factory recipe (or finds the one already built), gives it EXACTLY the
/// permissions its sidecar declared — pins included — and leaves it running. `201` when it built
/// it, `200` when it found it: pressing it twice is one automation, not two.
///
/// A recipe this hub discarded refuses with the discard's own code (`409`), the same code the
/// listing serves, so the module paints the reason instead of a mute failure.
pub async fn activate_template(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path((module, family)): Path<(String, String)>,
) -> Response {
    let (arc, who) = admin_session_no_capability!(st, headers);
    if let Err(response) = refuse_unless_own(&headers, &module) {
        return response;
    }
    let rt = arc.read().await;
    match rt.activate_flow_template(&module, &family, &who).await {
        Ok(activation) => (
            if activation.created {
                StatusCode::CREATED
            } else {
                StatusCode::OK
            },
            Json(json!({ "ok": true, "data": activation.flow })),
        )
            .into_response(),
        Err(e) => flow_err(e),
    }
}

/// `POST /api/hub/flows/templates/{module}/{family}/deactivate` — a **pause**, never a delete.
///
/// The grants stay and so does the run history: what that automation did needs an owner that still
/// exists, and turning it back on must not ask the person to authorise again what they already
/// authorised. A family that was never activated is `404`: there is nothing to pause.
pub async fn deactivate_template(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path((module, family)): Path<(String, String)>,
) -> Response {
    let (arc, who) = admin_session_no_capability!(st, headers);
    if let Err(response) = refuse_unless_own(&headers, &module) {
        return response;
    }
    let rt = arc.read().await;
    match rt.deactivate_flow_template(&module, &family, &who).await {
        Ok(flow) => Json(json!({ "ok": true, "data": flow })).into_response(),
        Err(e) => flow_err(e),
    }
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
    match rt.delete_flow_secret(&name, &who).await {
        Ok(()) => {
            Json(json!({ "ok": true, "data": { "name": name, "deleted": true } })).into_response()
        }
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
    let status = params
        .get("status")
        .map(String::as_str)
        .filter(|s| !s.is_empty());
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
    body: Option<Json<Value>>,
) -> Response {
    decide(st, headers, id, true, comment_of(body)).await
}

/// `POST /api/hub/flows/approvals/{id}/reject` — nothing runs, and the run stops: the steps written
/// after an agent step assumed it acted.
pub async fn reject(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    body: Option<Json<Value>>,
) -> Response {
    decide(st, headers, id, false, comment_of(body)).await
}

/// The optional `{"comment": "…"}` (hub#950) — what the person typed while deciding, which ends up
/// on the row and in `steps.<id>.comment`.
///
/// `Option<Json<Value>>` because these two routes have always been called with **no body at all**,
/// and a required extractor would answer `400` to every existing caller. Anything that is not a
/// string is the empty comment: a decision must never fail over the note attached to it.
fn comment_of(body: Option<Json<Value>>) -> String {
    body.and_then(|Json(v)| {
        v.get("comment")
            .and_then(|c| c.as_str())
            .map(str::to_string)
    })
    .unwrap_or_default()
}

async fn decide(
    st: AppState,
    headers: HeaderMap,
    id: String,
    approve: bool,
    comment: String,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let rt = arc.read().await;
    match rt.decide_flow_approval(&id, approve, &who, &comment).await {
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

    /// hub#734 — the whole `flow.` namespace against the status it must answer with.
    ///
    /// It lives here and not in `tests/flows_api_test.rs` because **half of this table has no
    /// reachable door**: every grant kind and every step kind is available since hub#821/hub#665,
    /// so nothing a request can carry produces a `…_kind_not_available` any more, and
    /// `secret_unreadable` needs a row that will not decrypt. Those are exactly the entries a
    /// router test cannot pin, and the ones a future kind would resurrect.
    #[test]
    fn every_error_code_of_the_kernel_answers_the_status_it_means() {
        use erplora_runtime::flows::{def, http, notify};

        let table = [
            // Not there.
            (store::ERR_FLOW_NOT_FOUND, StatusCode::NOT_FOUND),
            (approvals::ERR_APPROVAL_NOT_FOUND, StatusCode::NOT_FOUND),
            (secrets::ERR_SECRET_NOT_FOUND, StatusCode::NOT_FOUND),
            (notify::ERR_RECIPIENT_NOT_FOUND, StatusCode::NOT_FOUND),
            // The list a message promised, which the run never published (hub#1646): the same
            // shape as a recipient nobody could be found for, and pinned here rather than left to
            // the `not_found` suffix rule, so renaming it cannot silently turn it into a `400`.
            (notify::ERR_OPTIONS_NOT_FOUND, StatusCode::NOT_FOUND),
            // …and the text it promised, on the same terms (hub#1660).
            (notify::ERR_TEXT_NOT_FOUND, StatusCode::NOT_FOUND),
            // Refused by an authority.
            (grants::ERR_GRANT_DENIED, StatusCode::FORBIDDEN),
            (grants::ERR_INTERNAL_COMMAND, StatusCode::FORBIDDEN),
            // A kind of the frozen vocabulary this core cannot execute yet.
            (
                def::ERR_STEP_KIND_NOT_AVAILABLE,
                StatusCode::NOT_IMPLEMENTED,
            ),
            (
                grants::ERR_GRANT_KIND_NOT_AVAILABLE,
                StatusCode::NOT_IMPLEMENTED,
            ),
            // Real conflicts: well formed, allowed, and the state says no.
            (ERR_FLOW_DISABLED, StatusCode::CONFLICT),
            (
                approvals::ERR_APPROVAL_ALREADY_DECIDED,
                StatusCode::CONFLICT,
            ),
            (approvals::ERR_APPROVAL_EXPIRED, StatusCode::CONFLICT),
            (store::ERR_FLOW_DELETED, StatusCode::CONFLICT),
            (agent::ERR_NOT_IN_FLIGHT, StatusCode::CONFLICT),
            (secrets::ERR_SECRETS_KEY_MISSING, StatusCode::CONFLICT),
            // Not the caller's fault at all.
            (
                secrets::ERR_SECRET_UNREADABLE,
                StatusCode::INTERNAL_SERVER_ERROR,
            ),
            // …and the family default: what the caller sent cannot be accepted.
            (def::ERR_UNKNOWN_SCHEMA_VERSION, StatusCode::BAD_REQUEST),
            (def::ERR_INVALID_DEFINITION, StatusCode::BAD_REQUEST),
            (def::ERR_UNKNOWN_OPERATOR, StatusCode::BAD_REQUEST),
            (def::ERR_SECRET_NOT_AVAILABLE, StatusCode::BAD_REQUEST),
            (def::ERR_INVALID_CRON, StatusCode::BAD_REQUEST),
            (def::ERR_INVALID_AT, StatusCode::BAD_REQUEST),
            (grants::ERR_UNKNOWN_GRANT_KIND, StatusCode::BAD_REQUEST),
            (grants::ERR_INVALID_HTTP_PATTERN, StatusCode::BAD_REQUEST),
            (grants::ERR_INVALID_NOTIFY_GRANT, StatusCode::BAD_REQUEST),
            (grants::ERR_INVALID_RECIPIENT_GRANT, StatusCode::BAD_REQUEST),
            (secrets::ERR_INVALID_SECRET_NAME, StatusCode::BAD_REQUEST),
            (notify::ERR_RECIPIENT_AMBIGUOUS, StatusCode::BAD_REQUEST),
            (notify::ERR_RECIPIENT_INVALID, StatusCode::BAD_REQUEST),
            (http::ERR_HTTP_URL_INVALID, StatusCode::BAD_REQUEST),
        ];

        for (code, expected) in table {
            assert_eq!(
                flow_status(code),
                Some(expected),
                "`{code}` must answer {expected}"
            );
        }
    }

    /// The other half of the same contract: this door does not reclassify what is not its own. A
    /// module's domain error arriving through `POST …/run` keeps the `409` it has everywhere else,
    /// and it keeps it because `flow_status` declines rather than because it guessed right.
    #[test]
    fn a_code_from_outside_the_namespace_is_not_reclassified_here() {
        assert_eq!(flow_status("stock.insufficient"), None);
        assert_eq!(
            flow_status("not_found"),
            None,
            "a bare code is not a flow's"
        );
        let response = flow_err(RuntimeError::Domain {
            code: "stock.insufficient".to_string(),
            message: "no hay bastante".to_string(),
        });
        assert_eq!(response.status(), StatusCode::CONFLICT);
    }
}
