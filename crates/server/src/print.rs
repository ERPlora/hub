//! Print queue — HTTP layer over `erplora_runtime::print_queue` (hub#341, ADR-0196 §6).
//!
//! Two endpoints, both mounted in [`crate::app`] and both behind a **user session** (the same gate
//! as the rest of the core API — enqueueing is not anonymous):
//!
//!  - `POST /api/print/jobs` → body `{ jobId, role, html, format? }`. Enqueues the document for the
//!    print host of that `role`. **Idempotent by `jobId`**: a retry answers `200` with
//!    `status: "duplicate"` instead of queueing a second ticket.
//!  - `GET  /api/print/jobs?role=&status=&limit=` → the queue as a **status view**: what is waiting,
//!    what is printing, what died and why. It deliberately omits the document; the HTML travels to
//!    the print host that claims the job (hub#343), not to whoever polls the queue.
//!
//! And three more for the **print host registry** (hub#342), the other half of ADR-0196 §6 — who
//! is going to take the job out:
//!
//! | Endpoint | Contract |
//! |----------|----------|
//! | `POST /api/print/hosts` | `{ role, label? }` for the CALLER's `X-Device-Id`. Idempotent. |
//! | `POST /api/print/hosts/heartbeat` | "still here", for every role that device drains. |
//! | `GET`/`DELETE /api/print/hosts` | the registry (+ per-role coverage), and retiring a device. |
//!
//! **A device only ever registers, beats for or retires ITSELF**: the subject of the write doors is
//! the caller's `X-Device-Id` and there is no parameter to name another one — which is why an
//! ordinary session suffices for them. The app has to be able to do this when it starts, long after
//! whoever configured the hub went home, and the gesture is "this device, in my hands". The single
//! exception is retiring **somebody else's** device (the till that was replaced or stolen), which
//! takes an **admin** session — the same asymmetry as `/api/device/mode`.
//!
//! The `hub_id` comes from the deployment (not spoofable), like every other handler here.
use axum::extract::{Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::print_hosts::{self, PrintHost, RoleCoverage};
use erplora_runtime::print_queue::{EnqueueOutcome, NewPrintJob, PrintJob};
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
fn summary(job: &PrintJob) -> Value {
    json!({
        "jobId": job.job_id,
        "role": job.role,
        "format": job.format,
        "status": job.status,
        "attempts": job.attempts,
        "createdAt": job.created_at,
        "lastError": job.last_error,
    })
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
                "error": { "code": "invalid_payload", "message": "expected { jobId, role, html }" }
            })),
        )
            .into_response();
    };
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
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
    let rt = arc.lock().await;
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
fn coverage_json(c: &RoleCoverage) -> Value {
    json!({ "role": c.role, "waiting": c.waiting, "liveHosts": c.live_hosts })
}

/// Body of `POST /api/print/hosts`. There is deliberately **no `deviceId`**: a device registers
/// itself, and the id comes from the header.
#[derive(Debug, Default, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RegisterHost {
    /// Which queue this device drains: `receipt`, `kitchen`, `bar`, `label`, …
    pub role: String,
    /// Human name for the owner's screen. Absent keeps the name the device already had.
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
    let rt = arc.lock().await;
    let ctx = match auth::require_user_session(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx,
        Err(e) => return unauthorized(e),
    };
    let device_id = device_id_of(&headers);
    if device_id.is_empty() {
        return device_required();
    }
    match rt
        .register_print_host(
            device_id,
            &input.role,
            input.label.as_deref().unwrap_or_default(),
            &ctx.user_id,
        )
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
    let rt = arc.lock().await;
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
    let rt = arc.lock().await;
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
    let rt = arc.lock().await;
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

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_runtime::print_queue;

    fn job() -> PrintJob {
        PrintJob {
            job_id: "j1".into(),
            role: "kitchen".into(),
            html: "<p>secret order</p>".into(),
            format: print_queue::FORMAT_RECEIPT.into(),
            status: print_queue::STATUS_PENDING.into(),
            attempts: 0,
            created_at: "2026-08-07T10:00:00+00:00".into(),
            last_error: String::new(),
        }
    }

    /// The listing view carries the state of the job and **not** its document: a screen polling the
    /// queue does not need every ticket's HTML, and the print host gets it another way (hub#343).
    #[test]
    fn the_listing_view_reports_state_without_the_document() {
        let v = summary(&job());
        assert_eq!(v["jobId"], json!("j1"));
        assert_eq!(v["role"], json!("kitchen"));
        assert_eq!(v["status"], json!("pending"));
        assert_eq!(v["attempts"], json!(0));
        assert!(
            v.get("html").is_none(),
            "the document never travels in the listing"
        );
    }
}
