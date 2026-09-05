//! Print queue — HTTP layer over `erplora_runtime::print_queue` (hub#341, ADR-0196 §6).
//!
//! Two endpoints, both mounted in [`crate::app`] and both behind a **user session** (the same gate
//! as the rest of the core API — enqueueing is not anonymous). The queue is also readable through
//! the **dispatcher** since hub#1107 (`hub.print.coverage` / `hub.print.jobs`, `hub_users::core_query`),
//! which is how a MODULE gets at it; both doors share one shape (`print_queue::status_view`,
//! `print_hosts::coverage_view`) so they cannot drift:
//!
//!  - `POST /api/print/jobs` → body `{ jobId, role?, documentType, document, format? }`. Enqueues
//!    the document. **`role` is optional since hub#987**: omitted — the normal shape — the hub
//!    routes it by `documentType` through its own map; sent, it is a full override in deprecation.
//!    **Idempotent by `jobId`**: a retry answers `200` with `status: "duplicate"` instead of
//!    queueing a second ticket. The document travels **structured** — the shape
//!    `escpos::render_document` reads — never as HTML (hub#501).
//!  - `GET  /api/print/jobs?role=&status=&limit=` → the queue as a **status view**: what is waiting,
//!    what is printing, what died and why. It deliberately omits the document, which travels to the
//!    print host that claims the job (hub#343), not to whoever polls the queue.
//!
//! And two more that get **one** job unstuck (hub#1108) — the half no layer had at all:
//!
//! | Endpoint | Auth | Contract |
//! |----------|------|----------|
//! | `POST /api/print/jobs/{jobId}/retry` | **admin** (+ `printer` if a module names itself) | A `dead` job back to `pending`, `attempts = 0`. `409` naming the state otherwise. |
//! | `POST /api/print/jobs/{jobId}/discard` | **admin** (+ `printer`) | Retires a `pending`/`dead` job, stamped with who, when and why. **Never a delete.** |
//!
//! **Writing to the queue is admin, reading it is any session, and that asymmetry is the point**:
//! hub#987 decided the reader is whoever is standing next to the printer; binning a ticket is the
//! owner's gesture, behind the same door as the station CRUD.
//!
//! And three more for the **print host registry** (hub#342), the other half of ADR-0196 §6 — who
//! is going to take the job out:
//!
//! | Endpoint | Contract |
//! |----------|----------|
//! | `POST /api/print/hosts` | `{ role, label? }` for the CALLER's `X-Device-Id`. Idempotent. No
//!   `label` registers it under the name the business gave the device (hub#1560). |
//! | `POST /api/print/hosts/heartbeat` | "still here", for every role that device drains. |
//! | `GET`/`DELETE /api/print/hosts` | the registry (+ per-role coverage), and retiring a device. |
//!
//! And four for the **stations** themselves (hub#457) — the destinations both of the above resolve
//! against, now rows instead of words:
//!
//! | Endpoint | Auth | Contract |
//! |----------|------|----------|
//! | `GET /api/print/stations` | user session | every destination of this hub. |
//! | `POST /api/print/stations` | **admin** | `{ label, key? }`; no `key` derives one. |
//! | `PATCH /api/print/stations/{id}` | **admin** | `{ label }` — the key is immutable. |
//! | `DELETE /api/print/stations/{id}` | **admin** | `404` / `409` (work queued, or `receipt`) / `200`. |
//!
//! Reading is any session because it is what a screen reads to **offer** a destination; writing is
//! admin because it defines what the queues of the business *are* — the same door as `/api/keys`.
//!
//! And three for the **routing** (hub#987) — the other arrow of that same diagram, plus the alarm:
//!
//! | Endpoint | Auth | Contract |
//! |----------|------|----------|
//! | `GET /api/print/routes` | user session | the `documentType → station` map, + the fallback. |
//! | `PUT /api/print/routes` | **admin** | `{ documentType, stationKey }` — where this comes out. |
//! | `GET /api/print/undrained` | user session | what is stuck, for the bell. **Not admin** — see there. |
//!
//! **A device only ever registers, beats for or retires ITSELF**: the subject of the write doors is
//! the caller's `X-Device-Id` and there is no parameter to name another one — which is why an
//! ordinary session suffices for them. The app has to be able to do this when it starts, long after
//! whoever configured the hub went home, and the gesture is "this device, in my hands". The single
//! exception is retiring **somebody else's** device (the till that was replaced or stolen), which
//! takes an **admin** session — the same asymmetry as `/api/device/mode`.
//!
//! The `hub_id` comes from the deployment (not spoofable), like every other handler here.
use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::print_hosts::{self, PrintHost, RoleCoverage};
use erplora_runtime::print_queue::{self, EnqueueOutcome, NewPrintJob, PrintJob};
use erplora_runtime::print_stations::{DeleteOutcome, PrintStation};
use serde_json::{json, Value};

use crate::auth;
use crate::state::AppState;

/// Header carrying the device identity of the caller (ADR-0154), the same one `/api/device/mode`
/// reads. An identifier, never a credential: here it can only ever say **which device is speaking
/// about itself**, and what authorises the write is the session.
const DEVICE_ID_HEADER: &str = "x-device-id";

/// Default page size of the queue listing. A hub with more than this waiting has a printer problem,
/// not a paging problem.
const DEFAULT_LIMIT: i64 = 100;

/// Query string of the listing. Every filter is optional.
#[derive(Debug, Default, serde::Deserialize)]
pub struct QueueFilter {
    pub role: Option<String>,
    pub status: Option<String>,
    pub limit: Option<i64>,
}

/// `401` for an auth failure (no session / invalid session).
fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// A queued job as the listing reports it: everything **except** the document.
///
/// **The shape lives in the runtime** (`print_queue::status_view`), not here (hub#1107): the same
/// view is served by the core query `hub.print.jobs`, which a module reads through the dispatcher,
/// and two hand-written copies of "the queue seen from outside" would drift — starting with the
/// field that must never appear.
fn summary(job: &PrintJob) -> Value {
    print_queue::status_view(job)
}

/// POST /api/print/jobs — enqueue a document for a printer role. Auth = any user session.
pub async fn enqueue_job(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<NewPrintJob>>,
) -> Response {
    let Some(Json(job)) = body else {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "ok": false,
                "error": {
                    "code": "invalid_payload",
                    "message": "expected { jobId, role, documentType, document }"
                }
            })),
        )
            .into_response();
    };
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.enqueue_print_job(&job).await {
        // A duplicate is a SUCCESS: `jobId` did its job. The caller shows "queued" either way — it
        // asked for one ticket and there is exactly one ticket.
        Ok(outcome) => {
            // Nudge the print hosts of that role (hub#343) so the ticket comes out now instead of
            // on the next poll. **Only on a real enqueue**: waking every host for a duplicate would
            // send them all to an empty queue for a job that is already out.
            //
            // The frame carries the ROLE and nothing else. It travels on the shared event
            // broadcast, and `/ws` fans that out to **anyone** — that channel asks for no
            // credential at all (hub#504, found here, not caused here). So this frame must not say
            // what the ticket is: the document only ever leaves through `/ws/print`, past both
            // guards.
            if outcome == EnqueueOutcome::Queued {
                st.broadcast(json!({
                    "type": crate::print_ws::EVENT_JOB_QUEUED,
                    "role": job.role.trim(),
                }));
            }
            Json(json!({
                "ok": true,
                "jobId": job.job_id.trim(),
                "status": match outcome {
                    EnqueueOutcome::Queued => "queued",
                    EnqueueOutcome::Duplicate => "duplicate",
                },
            }))
            .into_response()
        }
        Err(e) => crate::err_response(e),
    }
}

/// GET /api/print/jobs — the queue, in hand-out order. Auth = any user session.
pub async fn list_jobs(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(filter): Query<QueueFilter>,
) -> Response {
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let limit = filter.limit.unwrap_or(DEFAULT_LIMIT);
    match rt
        .print_queue(filter.role.as_deref(), filter.status.as_deref(), limit)
        .await
    {
        Ok(jobs) => {
            let jobs: Vec<Value> = jobs.iter().map(summary).collect();
            Json(json!({ "ok": true, "jobs": jobs })).into_response()
        }
        Err(e) => crate::err_response(e),
    }
}

// ── Getting a stuck job UNSTUCK (hub#1108) ────────────────────────────────────────────────────
//
// `_print_queue` had no way out at any level: no endpoint, no runtime op, no command, no SDK
// surface. A `dead` job stayed dead and a job nobody was ever going to print (a QA session, a badly
// written flow) held its station hostage forever — `DELETE /api/print/stations/{id}` answers `409`
// while anything is `pending`.
//
// **Two gates, and the order is not cosmetic** (the same pattern as `outbox_admin`):
//
//  1. The person: an **admin** session. Reading the queue is any session (hub#987 — whoever is
//     standing next to the printer is who can turn the till on), but throwing a ticket in the bin or
//     re-firing one is the owner's or the manager's gesture, and it has the precedent of the station
//     CRUD next door. Putting the capability first would answer `403` to a caller who never
//     authenticated.
//  2. The module: if the request NAMES one (`X-Erplora-Module`, stamped by `@erplora/module-sdk`),
//     that module needs the **`printer`** capability declared in its manifest and granted by the
//     owner. Without it, "an admin is logged in" would mean every installed module can bin every
//     other one's tickets. A caller that names no module — the shell, `curl` — passes on the session
//     alone.

/// `401` when the session is missing or invalid, `403` when it is valid but the role does not
/// administer the hub. The distinction is not cosmetic: re-authenticating gets a cashier nowhere.
///
/// The older handlers in this file answer `401` to both through [`unauthorized`]; that is theirs to
/// keep, and copying it into a new door would spread it.
fn admin_rejected(e: auth::AuthError) -> Response {
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

/// `404` when there is no such job **in this hub**: never existed, or another tenant's — the two are
/// indistinguishable on purpose. Never a silent `200` that pretends something moved.
fn no_such_job() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({
            "ok": false,
            "error": { "code": "not_found", "message": "no hay ningún trabajo con ese jobId" }
        })),
    )
        .into_response()
}

/// `409` naming the state the job is really in, so a screen can say WHY instead of reporting a move
/// that never happened. `code` is stable and machine-readable; the state travels as data.
fn wrong_state(code: &str, status: String, message: &str) -> Response {
    (
        StatusCode::CONFLICT,
        Json(json!({
            "ok": false,
            "error": { "code": code, "message": message, "status": status }
        })),
    )
        .into_response()
}

/// Resolves the admin session AND the module capability, in that order. Returns who is doing this,
/// already in the `hub_user:<id>` form the audit columns store.
async fn admin_and_printer_capability(
    headers: &HeaderMap,
    st: &AppState,
    rt: &erplora_runtime::Runtime,
) -> Result<String, Response> {
    let admin = auth::require_admin_session(headers, &st.config, rt)
        .await
        .map_err(admin_rejected)?;
    crate::flows_api::require_module_capability(
        headers,
        rt,
        erplora_runtime::manifest::CapabilityKind::Printer,
    )
    .await?;
    Ok(format!("hub_user:{}", admin.id))
}

/// POST /api/print/jobs/{jobId}/retry — put a dead job back in front of the print hosts, with its
/// hand-outs reset. Auth = **admin** session (+ `printer` if a module names itself).
///
/// `409` when the job is not `dead`, naming the state it IS in: a `pending` one is already waiting,
/// a `printing` one is in a host's hands (and the lease already covers a host that died), a `done`
/// one came out of the printer and a `discarded` one is a decision somebody took.
pub async fn retry_job(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(job_id): Path<String>,
) -> Response {
    use erplora_runtime::print_queue::RequeueOutcome;
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(arc) => arc,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(response) = admin_and_printer_capability(&headers, &st, &rt).await {
        return response;
    }
    match rt.retry_print_job(&job_id).await {
        Ok(RequeueOutcome::Requeued) => Json(json!({
            "ok": true,
            "data": { "jobId": job_id, "status": print_queue::STATUS_PENDING }
        }))
        .into_response(),
        Ok(RequeueOutcome::NotFound) => no_such_job(),
        Ok(RequeueOutcome::NotRequeueable { status }) => wrong_state(
            "print.job_not_requeueable",
            status,
            "solo un trabajo `dead` se puede reintentar",
        ),
        Err(e) => crate::err_response(e),
    }
}

/// Body of `POST …/discard`: **one field**, the reason (same shape as the outbox's, hub#955).
///
/// Everything else in the stamp comes from inside — `discardedAt` from the clock, `discardedBy` from
/// the resolved session — so this body has no more surface than the reason needs. It is optional:
/// demanding an explanation to close a row is how a recovery queue stops being drained.
#[derive(Debug, Default, serde::Deserialize)]
pub struct DiscardReq {
    reason: Option<String>,
}

/// POST /api/print/jobs/{jobId}/discard — retire a job nobody is ever going to print. Auth =
/// **admin** session (+ `printer` if a module names itself).
///
/// **Never a delete**: the row survives, stamped with `discardedAt`, `discardedBy` and
/// `discardReason`, and no print host is handed it again. `409` for a `printing` job — the lease
/// already covers the host that died, and binning a ticket a live host is rendering would be the
/// silent loss this queue exists to prevent.
pub async fn discard_job(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(job_id): Path<String>,
    body: Option<Json<DiscardReq>>,
) -> Response {
    use erplora_runtime::print_queue::DiscardOutcome;
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(arc) => arc,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    let who = match admin_and_printer_capability(&headers, &st, &rt).await {
        Ok(who) => who,
        Err(response) => return response,
    };
    // The audit half comes from the SESSION, never from the body: `DiscardReq` has no
    // `discardedBy` field, so a payload carrying one changes nothing.
    let reason = body.and_then(|Json(b)| b.reason).unwrap_or_default();
    match rt.discard_print_job(&job_id, &who, &reason).await {
        Ok(DiscardOutcome::Discarded(stamp)) => {
            Json(json!({ "ok": true, "data": stamp })).into_response()
        }
        Ok(DiscardOutcome::NotFound) => no_such_job(),
        Ok(DiscardOutcome::NotDiscardable { status }) => wrong_state(
            "print.job_not_discardable",
            status,
            "un trabajo que un host está imprimiendo no se descarta bajo sus manos",
        ),
        Err(e) => crate::err_response(e),
    }
}

// ── Print host registry (hub#342) ─────────────────────────────────────────────────────────────

/// The device the request comes FROM, trimmed, or `""` when the client identifies none.
///
/// A header of blanks has to land on the same branch as no header at all: it is a client that did
/// not say which device it is, never a lookup for `"  "`.
fn device_id_of(headers: &HeaderMap) -> &str {
    headers
        .get(DEVICE_ID_HEADER)
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default()
        .trim()
}

/// `422` for a caller that did not say which device it is talking about.
fn device_required() -> Response {
    (
        StatusCode::UNPROCESSABLE_ENTITY,
        Json(json!({
            "ok": false,
            "error": {
                "code": "invalid_payload",
                "message": "this door acts on the calling device: send X-Device-Id"
            }
        })),
    )
        .into_response()
}

/// A registered host over the wire.
fn host_json(host: &PrintHost) -> Value {
    json!({
        "deviceId": host.device_id,
        "role": host.role,
        "label": host.label,
        "live": host.live,
        "registeredAt": host.registered_at,
        "registeredBy": host.registered_by,
        "lastSeenAt": host.last_seen_at,
    })
}

/// Per-role coverage over the wire: facts, not a sentence. The phrasing the owner reads ("nothing
/// is printing the kitchen's tickets") belongs to the UI, which is the layer that can translate it.
/// Same story as [`summary`]: the shape is `print_hosts::coverage_view`, shared with the core query
/// `hub.print.coverage` (hub#1107), so the shell's settings tab and a module's Printers screen
/// cannot disagree about which station is stuck.
fn coverage_json(c: &RoleCoverage) -> Value {
    print_hosts::coverage_view(c)
}

/// A routed document type as the API reports it.
fn route_json(r: &erplora_runtime::print_routes::PrintRoute) -> Value {
    json!({
        "documentType": r.document_type,
        "stationId": r.station_id,
        // Empty on both when the row dangles (the station was deleted). The screen paints THAT as
        // broken and offers to repoint it — hiding it would make a broken map look complete.
        "stationKey": r.station_key,
        "stationLabel": r.station_label,
    })
}

/// Body of `PUT /api/print/routes` — point one document type at one station.
#[derive(Debug, Default, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SetRoute {
    /// One of `print_queue::DOCUMENT_TYPES`.
    pub document_type: String,
    /// The station's wire key, as `GET /api/print/stations` lists them.
    pub station_key: String,
}

/// Body of `POST /api/print/hosts`. There is deliberately **no `deviceId`**: a device registers
/// itself, and the id comes from the header.
#[derive(Debug, Default, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RegisterHost {
    /// Which queue this device drains: `receipt`, `kitchen`, `bar`, `label`, …
    pub role: String,
    /// Human name for the owner's screen. Absent is the ordinary shape: the hub registers the
    /// device under the name the business gave it, or under the platform it announces (hub#1560).
    #[serde(default)]
    pub label: Option<String>,
}

/// Query string of `DELETE /api/print/hosts`.
#[derive(Debug, Default, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RetireHost {
    /// Retire from this role only. Absent = from every role (this device stops being a print host).
    pub role: Option<String>,
    /// Retire ANOTHER device (the till that was replaced or stolen). Requires an admin session;
    /// naming your own device is still your own device and needs none.
    pub device_id: Option<String>,
}

/// POST /api/print/hosts — this device drains `role`. Auth = any user session.
pub async fn register_host(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<RegisterHost>>,
) -> Response {
    let Some(Json(input)) = body else {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "ok": false,
                "error": { "code": "invalid_payload", "message": "expected { role }" }
            })),
        )
            .into_response();
    };
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    let ctx = match auth::require_user_session(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx,
        Err(e) => return unauthorized(e),
    };
    let device_id = device_id_of(&headers);
    if device_id.is_empty() {
        return device_required();
    }
    let label = match input.label.as_deref().map(str::trim) {
        Some(label) if !label.is_empty() => label.to_string(),
        _ => device_name(&rt, device_id, &headers).await,
    };
    match rt
        .register_print_host(device_id, &input.role, &label, &ctx.user_id)
        .await
    {
        Ok(host) => Json(json!({
            "ok": true,
            "host": host_json(&host),
            // The hub publishes the cadence so the client does not hard-code one that could drift
            // away from the window the hub uses to decide who is live.
            "heartbeatSeconds": print_hosts::HEARTBEAT_SECONDS,
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// The name to register a device under when it sends none (hub#1560).
///
/// The shell registers with the role and nothing else, and hub#1527 turned that silence into an
/// opaque `dev_…` id on the owner's Printers screen. The name is **not** minted here — this hub
/// already knows what the business calls each device (`hub_trusted_device.name`, hub#494): born
/// from the platform it announced on its first online login, renameable in Settings → Devices.
/// Reusing it is what keeps one tablet from having two names, one per screen.
///
/// Order, and why: what the **owner** typed beats what the **device** announced, and both beat
/// nothing. `""` is the honest last answer — `print_hosts::register` reads it as "keep the name
/// this device already had", so a hub that knows nothing about a device never blanks a name off
/// the screen to say so.
async fn device_name(
    rt: &erplora_runtime::Runtime,
    device_id: &str,
    headers: &HeaderMap,
) -> String {
    // Best-effort: a registry read that fails must not stop a till becoming a print host. Losing
    // the name costs the owner a legible row; losing the registration costs them the ticket.
    let named = rt.device_name(device_id).await.unwrap_or_else(|e| {
        tracing::warn!(
            device_id,
            error = %e,
            "print host registered without the name of the device: its name could not be read"
        );
        String::new()
    });
    if !named.is_empty() {
        return named;
    }
    crate::devices::default_device_name(crate::devices::user_agent_of(headers))
}

/// POST /api/print/hosts/heartbeat — still here. Auth = any user session.
///
/// `refreshed: 0` is a success, not a 404: it means this device hosts nothing here (its rows were
/// removed while it was away) and has to register again. A failure status would look like a broken
/// hub for what is a perfectly ordinary answer.
pub async fn host_heartbeat(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let device_id = device_id_of(&headers);
    if device_id.is_empty() {
        return device_required();
    }
    match rt.print_host_heartbeat(device_id).await {
        Ok(refreshed) => Json(json!({
            "ok": true,
            "refreshed": refreshed,
            "heartbeatSeconds": print_hosts::HEARTBEAT_SECONDS,
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// GET /api/print/hosts — the registry plus per-role coverage. Auth = any user session.
pub async fn list_hosts(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let hosts = match rt.print_hosts().await {
        Ok(hosts) => hosts,
        Err(e) => return crate::err_response(e),
    };
    match rt.print_coverage().await {
        Ok(coverage) => Json(json!({
            "ok": true,
            "hosts": hosts.iter().map(host_json).collect::<Vec<_>>(),
            "coverage": coverage.iter().map(coverage_json).collect::<Vec<_>>(),
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// DELETE /api/print/hosts?role=&deviceId= — retire a device from a role, or from all of them.
///
/// Auth = user session for **your own** device; **admin** session to retire another one. The split
/// is on the subject, not on the parameter: naming your own device explicitly is still your own
/// device. Without the admin half there would be no way to clean up a till that was stolen or
/// thrown away — it is off, so it can never retire itself — and without the user half the app
/// could not undo its own setup.
pub async fn retire_host(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(input): Query<RetireHost>,
) -> Response {
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let own = device_id_of(&headers);
    let target = input
        .device_id
        .as_deref()
        .map(str::trim)
        .filter(|id| !id.is_empty())
        .unwrap_or(own);
    if target.is_empty() {
        return device_required();
    }
    if target != own {
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    let role = input
        .role
        .as_deref()
        .map(str::trim)
        .filter(|r| !r.is_empty());
    match rt.unregister_print_host(target, role).await {
        Ok(removed) => Json(json!({ "ok": true, "removed": removed })).into_response(),
        Err(e) => crate::err_response(e),
    }
}

// ── Print stations: the destinations themselves (hub#457) ─────────────────────────────────────

/// A station over the wire.
fn station_json(s: &PrintStation) -> Value {
    json!({ "id": s.id, "key": s.key, "label": s.label, "createdAt": s.created_at })
}

/// Body of `POST /api/print/stations`.
#[derive(Debug, Default, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NewStation {
    /// The wire name. Absent or empty is **derived from the label**, which is the realistic
    /// gesture: the owner types "Barra de la terraza", not a slug.
    #[serde(default)]
    pub key: Option<String>,
    pub label: String,
}

/// Body of `PATCH /api/print/stations/{id}`. There is deliberately no `key`: it is what every
/// published contract sends and what every queued job already carries.
#[derive(Debug, Default, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RenameStation {
    pub label: String,
}

/// `409` for a delete the hub refuses on domain grounds (same channel as ADR-0205).
fn station_conflict(message: String) -> Response {
    (
        StatusCode::CONFLICT,
        Json(json!({
            "ok": false,
            "error": { "code": "station_in_use", "message": message }
        })),
    )
        .into_response()
}

/// `404` for a station id this hub does not know.
fn station_not_found() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({
            "ok": false,
            "error": { "code": "not_found", "message": "no such print station in this hub" }
        })),
    )
        .into_response()
}

/// GET /api/print/stations — every destination of this hub. Auth = any user session.
///
/// Not admin-only: this is what a screen reads to **offer** a destination, and it is the same list
/// the refusal of an unknown role already names.
pub async fn list_stations(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.print_stations().await {
        Ok(stations) => Json(json!({
            "ok": true,
            "stations": stations.iter().map(station_json).collect::<Vec<_>>(),
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// POST /api/print/stations — add a destination. Auth = **admin** session.
///
/// Admin and not any session, unlike registering a host: a host says "this device, in my hands,
/// drains that queue", while this defines what the queues of the business **are** — the same kind
/// of decision as issuing an API key or creating a user.
pub async fn create_station(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<NewStation>>,
) -> Response {
    let Some(Json(input)) = body else {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "ok": false,
                "error": { "code": "invalid_payload", "message": "expected { label }" }
            })),
        )
            .into_response();
    };
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt
        .create_print_station(input.key.as_deref().unwrap_or_default(), &input.label)
        .await
    {
        Ok(station) => {
            Json(json!({ "ok": true, "station": station_json(&station) })).into_response()
        }
        Err(e) => crate::err_response(e),
    }
}

/// PATCH /api/print/stations/{id} — rename the label. Auth = **admin** session.
pub async fn rename_station(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    body: Option<Json<RenameStation>>,
) -> Response {
    let Some(Json(input)) = body else {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "ok": false,
                "error": { "code": "invalid_payload", "message": "expected { label }" }
            })),
        )
            .into_response();
    };
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.rename_print_station(&id, &input.label).await {
        Ok(Some(station)) => {
            Json(json!({ "ok": true, "station": station_json(&station) })).into_response()
        }
        Ok(None) => station_not_found(),
        Err(e) => crate::err_response(e),
    }
}

/// DELETE /api/print/stations/{id} — retire a destination. Auth = **admin** session.
///
/// Three answers, and they are different on purpose: `404` (not a station here), `409` (it still
/// has work, or it is the protected `receipt`) and `200`. A delete that quietly did nothing would
/// leave the owner's screen disagreeing with the hub about what the business can print.
pub async fn delete_station(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.delete_print_station(&id).await {
        Ok(DeleteOutcome::Deleted) => Json(json!({ "ok": true })).into_response(),
        Ok(DeleteOutcome::NotFound) => station_not_found(),
        Ok(DeleteOutcome::HasWork(n)) => station_conflict(format!(
            "this station still has {n} job(s) waiting or printing: drain them before removing it"
        )),
        Ok(DeleteOutcome::Protected) => station_conflict(
            "the `receipt` station is the default of every till and cannot be removed".to_string(),
        ),
        Err(e) => crate::err_response(e),
    }
}

/// GET /api/print/routes — this hub's `documentType → station` map. Auth = any user session.
///
/// Any session and not admin, for the same reason as the station list: this is what a screen reads
/// to **show** where a document comes out. Changing it is the admin door below.
pub async fn list_routes(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.print_routes().await {
        Ok(routes) => Json(json!({
            "ok": true,
            "routes": routes.iter().map(route_json).collect::<Vec<_>>(),
            // The station a job falls open onto when its route is missing or broken. It travels so
            // the screen can say where an unrouted document ends up instead of guessing.
            "fallbackStation": erplora_runtime::print_stations::PROTECTED_KEY,
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// PUT /api/print/routes — point a document type at a station. Auth = **admin** session.
///
/// Admin for the same reason `POST /api/print/stations` is: this decides where the business's
/// paper comes out, which is a decision about the business and not about the device in your hand.
pub async fn set_route(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<SetRoute>>,
) -> Response {
    let Some(Json(input)) = body else {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "ok": false,
                "error": {
                    "code": "invalid_payload",
                    "message": "expected { documentType, stationKey }"
                }
            })),
        )
            .into_response();
    };
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(admin) => admin,
        Err(e) => return unauthorized(e),
    };
    match rt
        .set_print_route(&input.document_type, &input.station_key, &admin.id)
        .await
    {
        Ok(route) => Json(json!({ "ok": true, "route": route_json(&route) })).into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// GET /api/print/undrained — the cheap "is anything on fire" number for the topbar bell (hub#987).
///
/// Auth = **any user session**, and that is the substantive difference with the dead-letter count it
/// is modelled on (`/api/hub/events/dead/count`, hub#660, admin-only). A dead-letter needs an admin;
/// a queue nobody is draining needs whoever is at the counter — they are the one who can switch the
/// till back on, and they are the one about to hand a customer no receipt. Restricting this to
/// admins would hide the alarm from the only person standing next to the printer.
///
/// It carries the threshold it applied so no client re-invents one (same shape as
/// `heartbeatSeconds` on the host heartbeat).
pub async fn undrained_stations(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.print_undrained().await {
        Ok(stations) => Json(json!({
            "ok": true,
            "count": stations.len(),
            "thresholdSeconds": print_hosts::UNDRAINED_ALERT_SECONDS,
            "stations": stations.iter().map(coverage_json).collect::<Vec<_>>(),
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_runtime::print_queue;

    fn job() -> PrintJob {
        PrintJob {
            job_id: "j1".into(),
            role: "kitchen".into(),
            document_type: "kitchen_order".into(),
            document: json!({ "receipt_id": "K-1", "items": [{ "name": "Bacalao" }] }),
            format: print_queue::FORMAT_RECEIPT.into(),
            status: print_queue::STATUS_PENDING.into(),
            attempts: 0,
            created_at: "2026-08-07T10:00:00+00:00".into(),
            last_error: String::new(),
        }
    }

    /// The listing view carries the state of the job and **not** its document: a screen polling the
    /// queue does not need every ticket's lines and totals, and the print host gets them another way
    /// (hub#343). What it DOES carry is which kind of document is stuck, because that is the thing
    /// the owner needs to read.
    #[test]
    fn the_listing_view_reports_state_without_the_document() {
        let v = summary(&job());
        assert_eq!(v["jobId"], json!("j1"));
        assert_eq!(v["role"], json!("kitchen"));
        assert_eq!(v["documentType"], json!("kitchen_order"));
        assert_eq!(v["status"], json!("pending"));
        assert_eq!(v["attempts"], json!(0));
        for leak in ["document", "html"] {
            assert!(
                v.get(leak).is_none(),
                "the document never travels in the listing (`{leak}`)"
            );
        }
    }
}
