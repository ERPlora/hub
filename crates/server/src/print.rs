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
//! The `hub_id` comes from the deployment (not spoofable), like every other handler here.
use axum::extract::{Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::print_queue::{EnqueueOutcome, NewPrintJob, PrintJob};
use serde_json::{json, Value};

use crate::auth;
use crate::state::AppState;

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
        Ok(outcome) => Json(json!({
            "ok": true,
            "jobId": job.job_id.trim(),
            "status": match outcome {
                EnqueueOutcome::Queued => "queued",
                EnqueueOutcome::Duplicate => "duplicate",
            },
        }))
        .into_response(),
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
