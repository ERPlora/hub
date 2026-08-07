//! Print queue **in the hub** (ADR-0196 §6, hub#341).
//!
//! Any device — the PWA in a phone included — enqueues `{ role, html, jobId }` here. The device
//! that has the installable app and sits on the printer's network registers as the **print host**
//! of that `role` and drains the queue over the runtime's WS (hub#342/#343). Because the queue
//! lives in the hub and not in the device:
//!
//!  - **`jobId` gives idempotency.** Re-sending the same job (a retried HTTP call, a double tap on
//!    "print", a reconnect) never produces a second ticket: the row is keyed by `(hub_id, job_id)`
//!    and a duplicate enqueue is a no-op that reports [`EnqueueOutcome::Duplicate`].
//!  - **With nobody connected the job WAITS.** It stays `pending` until a host of its role claims
//!    it — late, not lost. That is the case the standalone Bridge could not serve at all.
//!  - **The queue survives a restart of the runtime**, because it is a table and not an in-memory
//!    channel. That is the substantive difference with [`erplora_peripherals::PrintQueue`], whose
//!    retry/backoff shape this module mirrors: what changes is *where the queue lives*.
//!
//! ## State machine
//!
//! ```text
//!            enqueue                claim_next                mark_done
//!   (none) ──────────▶ pending ────────────────▶ printing ──────────────▶ done
//!                        ▲                          │
//!                        │  mark_failed             │ lease expires (host died)
//!                        └──────────────────────────┤
//!                                                   ▼   attempts >= MAX_ATTEMPTS
//!                                                  dead
//! ```
//!
//! `attempts` counts **hand-outs**, not failures: it is incremented when a host claims the job, so
//! a host that takes the job and dies without answering still burns an attempt and cannot spin the
//! queue forever. Every claim carries a **lease**; once it expires the job returns to `pending`
//! (see [`reclaim_expired`]) so a crashed print host does not strand the ticket.
//!
//! This module is the queue only. Registering a print host for a role (hub#342), draining it over
//! the WS (hub#343) and the `sdk.print` producer path (hub#344) are separate work.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;

/// Hand-outs a job gets before it is dead-lettered. Mirrors the intent of
/// `erplora_peripherals::RetryPolicy::max_attempts` (3) but slightly higher: here an attempt can
/// also be burnt by a print host that disconnects, not only by a printer that refuses the bytes.
pub const MAX_ATTEMPTS: i64 = 5;

/// How long a claimed job stays invisible to other hosts before it is handed out again. Long
/// enough for a slow thermal printer, short enough that a killed host does not strand the ticket.
pub const DEFAULT_LEASE_SECONDS: i64 = 90;

/// Waiting for a print host of its role.
pub const STATUS_PENDING: &str = "pending";
/// Claimed by a print host; invisible to other hosts until its lease expires.
pub const STATUS_PRINTING: &str = "printing";
/// Confirmed printed by the host that claimed it. Terminal.
pub const STATUS_DONE: &str = "done";
/// Gave up after [`MAX_ATTEMPTS`] hand-outs. Terminal, kept for diagnosis.
pub const STATUS_DEAD: &str = "dead";

/// Paper of the document. Not cosmetic: it is what lets the print host render an 80mm ticket as a
/// ticket and an invoice as A4 (same contract as `PrintRequest.format` in the web shell).
pub const FORMAT_RECEIPT: &str = "receipt";
/// A4 paper (invoices, delivery notes).
pub const FORMAT_A4: &str = "a4";

/// Upper bound for the document of a single job. A print job is a ticket or an invoice, not a
/// file upload: without a bound, any session could push arbitrary blobs into the hub's database.
pub const MAX_HTML_BYTES: usize = 512 * 1024;

/// What [`enqueue`] did. `Duplicate` is a **success**, not an error: it is the whole point of
/// `jobId`, and the caller reports "queued" to the user either way.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EnqueueOutcome {
    /// The job was written; it is now waiting for a print host.
    Queued,
    /// A job with that `jobId` already existed in this hub. Nothing was written or overwritten.
    Duplicate,
}

/// A job as the producer submits it. Field names are camelCase over the wire to match the shell's
/// `PrintRequest` (`apps/web/src/lib/print.ts`), which is the producer that already exists.
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NewPrintJob {
    /// Idempotency key chosen by the producer. Two enqueues with the same one are one job.
    pub job_id: String,
    /// Printer role: `receipt` (default of the shell), `kitchen`, `bar`, …
    pub role: String,
    /// Self-contained HTML of the document (no web components, no app CSS).
    pub html: String,
    /// Paper format. Defaults to [`FORMAT_RECEIPT`].
    #[serde(default = "default_format")]
    pub format: String,
}

fn default_format() -> String {
    FORMAT_RECEIPT.to_string()
}

/// A queued job as the hub stores it. `html` is included because the print host needs it to render;
/// [`list`] is the observability view and returns the same shape.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PrintJob {
    pub job_id: String,
    pub role: String,
    pub html: String,
    pub format: String,
    pub status: String,
    pub attempts: i64,
    pub created_at: String,
    pub last_error: String,
}

/// Columns every read of the queue returns, in the order [`row_to_job`] expects.
const JOB_COLUMNS: &str = "job_id, role, html, format, status, attempts, created_at, last_error";

/// Rejection of a malformed job, before it reaches the database.
fn invalid(detail: impl Into<String>) -> RuntimeError {
    RuntimeError::InvalidPayload {
        name: "print.enqueue".to_string(),
        detail: detail.into(),
    }
}

/// Enqueues a job for `role`, **idempotently by `job_id`**.
///
/// Re-enqueueing a `job_id` this hub already knows is [`EnqueueOutcome::Duplicate`]: nothing is
/// written and, crucially, nothing is **overwritten** — the document the printer is about to
/// produce is the one that was queued first. That holds for the whole life of the row, so a
/// re-send after the ticket printed does not print it again either.
pub async fn enqueue(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    job: &NewPrintJob,
) -> Result<EnqueueOutcome> {
    let job_id = job.job_id.trim();
    let role = job.role.trim();
    if job_id.is_empty() {
        return Err(invalid("job_id is required (it is the idempotency key)"));
    }
    if role.is_empty() {
        return Err(invalid("role is required (which printer prints this)"));
    }
    if job.html.trim().is_empty() {
        return Err(invalid("html is required (there is no document to print)"));
    }
    if job.html.len() > MAX_HTML_BYTES {
        return Err(invalid(format!(
            "html is {} bytes, over the {MAX_HTML_BYTES} byte cap for a print job",
            job.html.len()
        )));
    }
    if job.format != FORMAT_RECEIPT && job.format != FORMAT_A4 {
        return Err(invalid(format!(
            "unknown paper format `{}` (expected `{FORMAT_RECEIPT}` or `{FORMAT_A4}`)",
            job.format
        )));
    }

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("job_id".into(), json!(job_id));
    p.insert("role".into(), json!(role));
    p.insert("html".into(), json!(job.html));
    p.insert("format".into(), json!(job.format));
    p.insert("now".into(), json!(now_rfc3339()));
    // `ON CONFLICT DO NOTHING` (and not `DO UPDATE`) IS the idempotency guard: a repeated jobId
    // must neither add a second row nor rewrite the one already queued.
    let res = db
        .execute(
            "INSERT INTO _print_queue \
             (hub_id, job_id, role, html, format, status, attempts, created_at) \
             VALUES (:hub_id, :job_id, :role, :html, :format, 'pending', 0, :now) \
             ON CONFLICT (hub_id, job_id) DO NOTHING",
            &p,
        )
        .await?;
    Ok(if res.affected > 0 {
        EnqueueOutcome::Queued
    } else {
        EnqueueOutcome::Duplicate
    })
}

/// Hands the oldest `pending` job of `role` to a print host, leasing it for `lease_seconds`.
///
/// `FOR UPDATE SKIP LOCKED` makes the hand-out atomic: two hosts of the same role racing on the
/// same queue take **different** jobs, never the same ticket twice. The claim burns one attempt, so
/// a host that takes the job and disappears cannot keep it circulating forever.
pub async fn claim_next(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    role: &str,
    claimed_by: &str,
    lease_seconds: i64,
) -> Result<Option<PrintJob>> {
    let lease_expires_at =
        (chrono::Utc::now() + chrono::Duration::seconds(lease_seconds)).to_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("role".into(), json!(role));
    p.insert("claimed_by".into(), json!(claimed_by));
    p.insert("lease".into(), json!(lease_expires_at));
    let sql = format!(
        "UPDATE _print_queue SET status = '{STATUS_PRINTING}', attempts = attempts + 1, \
           claimed_by = :claimed_by, lease_expires_at = :lease \
         WHERE hub_id = :hub_id AND job_id = ( \
           SELECT job_id FROM _print_queue \
           WHERE hub_id = :hub_id AND role = :role AND status = '{STATUS_PENDING}' \
           ORDER BY seq LIMIT 1 FOR UPDATE SKIP LOCKED) \
         RETURNING {JOB_COLUMNS}"
    );
    let res = db.query(&sql, &p).await?;
    Ok(res.rows.first().map(row_to_job))
}

/// The host confirms the job came out of the printer. Terminal: it is never handed out again, and
/// its `job_id` keeps guarding against a re-send.
///
/// Returns whether a job was actually confirmed (`false` = unknown id, or already terminal).
pub async fn mark_done(db: &dyn DatabaseAdapter, hub_id: &str, job_id: &str) -> Result<bool> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("job_id".into(), json!(job_id));
    p.insert("now".into(), json!(now_rfc3339()));
    // A job whose lease expired may already be back in `pending` (or claimed by another host) when
    // the original host finally answers. Confirming it anyway is the right call: the paper came
    // out, so what we must avoid is printing it a second time.
    let sql = format!(
        "UPDATE _print_queue SET status = '{STATUS_DONE}', completed_at = :now, \
           lease_expires_at = '', claimed_by = '' \
         WHERE hub_id = :hub_id AND job_id = :job_id \
           AND status IN ('{STATUS_PENDING}', '{STATUS_PRINTING}')"
    );
    Ok(db.execute(&sql, &p).await?.affected > 0)
}

/// The host could not print it (no paper, printer off, socket refused).
///
/// Returns `true` if the job went back to the queue for another attempt, `false` if it ran out of
/// hand-outs and was dead-lettered (kept, with its reason, for diagnosis).
pub async fn mark_failed(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    job_id: &str,
    error: &str,
) -> Result<bool> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("job_id".into(), json!(job_id));
    p.insert("error".into(), json!(error));
    p.insert("max".into(), json!(MAX_ATTEMPTS));
    let sql = format!(
        "UPDATE _print_queue \
         SET status = CASE WHEN attempts >= :max THEN '{STATUS_DEAD}' ELSE '{STATUS_PENDING}' END, \
             last_error = :error, claimed_by = '', lease_expires_at = '' \
         WHERE hub_id = :hub_id AND job_id = :job_id AND status = '{STATUS_PRINTING}' \
         RETURNING status"
    );
    let res = db.query(&sql, &p).await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["status"].as_str())
        .is_some_and(|s| s == STATUS_PENDING))
}

/// Returns to the queue every job whose lease expired — the print host claimed it and never
/// answered (app closed, device asleep, network gone). Without this a crashed host would strand
/// the ticket in `printing` forever, which is exactly the "lost job" ADR-0196 §6 rules out.
///
/// A job that runs out of hand-outs this way is dead-lettered instead of requeued. Returns how many
/// rows were swept.
pub async fn reclaim_expired(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<usize> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("max".into(), json!(MAX_ATTEMPTS));
    p.insert("timeout".into(), json!("print host lease expired"));
    let sql = format!(
        "UPDATE _print_queue \
         SET status = CASE WHEN attempts >= :max THEN '{STATUS_DEAD}' ELSE '{STATUS_PENDING}' END, \
             last_error = CASE WHEN attempts >= :max THEN :timeout ELSE last_error END, \
             claimed_by = '', lease_expires_at = '' \
         WHERE hub_id = :hub_id AND status = '{STATUS_PRINTING}' \
           AND lease_expires_at <> '' AND lease_expires_at <= :now"
    );
    Ok(db.execute(&sql, &p).await?.affected as usize)
}

/// The queue as it stands, in hand-out order (oldest first). `role`/`status` are optional filters;
/// this is what makes the order and the state of the queue observable — for the print host that
/// asks "what is pending for me" and for the screen that shows a stuck ticket.
pub async fn list(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    role: Option<&str>,
    status: Option<&str>,
    limit: i64,
) -> Result<Vec<PrintJob>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("lim".into(), json!(limit.clamp(1, 500)));
    let mut where_sql = String::from("hub_id = :hub_id");
    if let Some(role) = role {
        p.insert("role".into(), json!(role));
        where_sql.push_str(" AND role = :role");
    }
    if let Some(status) = status {
        p.insert("status".into(), json!(status));
        where_sql.push_str(" AND status = :status");
    }
    let sql =
        format!("SELECT {JOB_COLUMNS} FROM _print_queue WHERE {where_sql} ORDER BY seq LIMIT :lim");
    let res = db.query(&sql, &p).await?;
    Ok(res.rows.iter().map(row_to_job).collect())
}

/// Row of [`JOB_COLUMNS`] → [`PrintJob`].
fn row_to_job(row: &serde_json::Value) -> PrintJob {
    let s = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    PrintJob {
        job_id: s("job_id"),
        role: s("role"),
        html: s("html"),
        format: s("format"),
        status: s("status"),
        attempts: row["attempts"].as_i64().unwrap_or(0),
        created_at: s("created_at"),
        last_error: s("last_error"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::TestDb;
    use erplora_db::PgAdapter;

    /// A hub whose system schema is in place (the print queue is system migration v18).
    async fn queue_db() -> PgAdapter {
        let db = TestDb::new().await.adapter().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        db
    }

    fn job(job_id: &str, role: &str, html: &str) -> NewPrintJob {
        NewPrintJob {
            job_id: job_id.into(),
            role: role.into(),
            html: html.into(),
            format: FORMAT_RECEIPT.into(),
        }
    }

    async fn all(db: &PgAdapter, hub_id: &str) -> Vec<PrintJob> {
        list(db, hub_id, None, None, 100).await.unwrap()
    }

    /// **The idempotency guard.** Enqueueing the same `jobId` twice is ONE job: the second call is
    /// a no-op that reports `Duplicate`, and it does not overwrite the document already queued
    /// (a retry must never mutate the ticket the printer is about to produce).
    #[tokio::test]
    async fn enqueueing_the_same_job_id_twice_does_not_duplicate_the_job() {
        let db = queue_db().await;

        let first = enqueue(&db, "h1", &job("j1", "receipt", "<p>ticket</p>"))
            .await
            .unwrap();
        assert_eq!(first, EnqueueOutcome::Queued);

        // Same jobId, different body: the retry of a request whose response got lost.
        let second = enqueue(&db, "h1", &job("j1", "receipt", "<p>OTHER</p>"))
            .await
            .unwrap();
        assert_eq!(
            second,
            EnqueueOutcome::Duplicate,
            "a repeated jobId is not an error: it is the idempotency contract"
        );

        let jobs = all(&db, "h1").await;
        assert_eq!(jobs.len(), 1, "one jobId, one ticket");
        assert_eq!(
            jobs[0].html, "<p>ticket</p>",
            "the queued document is the first one; a retry never rewrites it"
        );
    }

    /// The queue is a table, not a channel: a runtime that restarts finds the job still waiting.
    /// `TestDb::adapter()` twice over the same schema is exactly "the process died and came back".
    #[tokio::test]
    async fn a_queued_job_survives_a_restart_of_the_runtime() {
        let test_db = TestDb::new().await;

        {
            let db = test_db.adapter().await;
            crate::installer::ensure_hub_module_table(&db)
                .await
                .unwrap();
            crate::identity::ensure_tables(&db).await.unwrap();
            crate::system_migrations::apply(&db, "h1").await.unwrap();
            enqueue(&db, "h1", &job("j1", "kitchen", "<p>order</p>"))
                .await
                .unwrap();
        }

        // New process over the same data: re-running the system migrations is idempotent and the
        // job is still there, still claimable.
        let db = test_db.adapter().await;
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        let claimed = claim_next(&db, "h1", "kitchen", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .expect("the job waited across the restart");
        assert_eq!(claimed.job_id, "j1");
        assert_eq!(claimed.html, "<p>order</p>");
    }

    /// A job already claimed by a print host is not handed to a second one while its lease holds.
    #[tokio::test]
    async fn a_claimed_job_is_not_handed_out_again() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "<p>t</p>"))
            .await
            .unwrap();

        let first = claim_next(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap();
        assert_eq!(first.map(|j| j.job_id), Some("j1".to_string()));

        let second = claim_next(&db, "h1", "receipt", "host-b", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap();
        assert!(second.is_none(), "two hosts must not print the same ticket");
    }

    /// A drained (confirmed) job is terminal: no host ever sees it again.
    #[tokio::test]
    async fn a_drained_job_is_never_handed_out_again() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "<p>t</p>"))
            .await
            .unwrap();
        claim_next(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .unwrap();
        assert!(mark_done(&db, "h1", "j1").await.unwrap());

        // Neither directly…
        assert!(
            claim_next(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_none()
        );
        // …nor through the lease sweeper (a done job has no lease to expire).
        assert_eq!(reclaim_expired(&db, "h1").await.unwrap(), 0);
        assert_eq!(all(&db, "h1").await[0].status, STATUS_DONE);
    }

    /// Even re-enqueueing the same `jobId` after it printed does not print it twice: the row still
    /// exists, so the idempotency key still holds. This is the double-tap the cashier does when the
    /// ticket is slow to come out.
    #[tokio::test]
    async fn re_enqueueing_a_job_id_that_already_printed_does_not_print_it_again() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "<p>t</p>"))
            .await
            .unwrap();
        claim_next(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .unwrap();
        mark_done(&db, "h1", "j1").await.unwrap();

        let again = enqueue(&db, "h1", &job("j1", "receipt", "<p>t</p>"))
            .await
            .unwrap();
        assert_eq!(again, EnqueueOutcome::Duplicate);
        assert!(
            claim_next(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_none()
        );
    }

    /// Order is observable and is the order of enqueue: the kitchen prints the first order first.
    #[tokio::test]
    async fn jobs_are_handed_out_in_enqueue_order() {
        let db = queue_db().await;
        for id in ["j1", "j2", "j3"] {
            enqueue(&db, "h1", &job(id, "kitchen", "<p>o</p>"))
                .await
                .unwrap();
        }

        let listed: Vec<String> = all(&db, "h1").await.into_iter().map(|j| j.job_id).collect();
        assert_eq!(listed, ["j1", "j2", "j3"], "the queue order is observable");

        let mut handed = Vec::new();
        while let Some(j) = claim_next(&db, "h1", "kitchen", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
        {
            handed.push(j.job_id);
        }
        assert_eq!(handed, ["j1", "j2", "j3"]);
    }

    /// A host of one role never takes the work of another: the bar does not print the kitchen's.
    #[tokio::test]
    async fn a_host_only_claims_jobs_of_its_own_role() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "kitchen", "<p>o</p>"))
            .await
            .unwrap();

        assert!(
            claim_next(&db, "h1", "bar", "host-bar", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_none(),
            "a bar host must not drain the kitchen queue"
        );
        assert!(
            claim_next(&db, "h1", "kitchen", "host-kitchen", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_some()
        );
    }

    /// A host that claims and dies does not strand the ticket: once the lease expires the job goes
    /// back to the queue for the next host. "Late, not lost" (ADR-0196 §6).
    #[tokio::test]
    async fn a_lease_that_expires_returns_the_job_to_the_queue() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "<p>t</p>"))
            .await
            .unwrap();

        // Lease already in the past = the host took it and never came back.
        claim_next(&db, "h1", "receipt", "dead-host", -1)
            .await
            .unwrap()
            .unwrap();
        assert!(
            claim_next(&db, "h1", "receipt", "host-b", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_none(),
            "still claimed until the sweeper runs"
        );

        assert_eq!(reclaim_expired(&db, "h1").await.unwrap(), 1);
        let back = claim_next(&db, "h1", "receipt", "host-b", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .expect("the job waits for the next host instead of being lost");
        assert_eq!(back.job_id, "j1");
        assert_eq!(back.attempts, 2, "the hand-out to the dead host counted");
    }

    /// A job the host cannot print goes back to the queue and, once out of hand-outs, is
    /// dead-lettered with its error instead of cycling forever.
    #[tokio::test]
    async fn a_failing_job_is_requeued_and_then_dead_lettered() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "<p>t</p>"))
            .await
            .unwrap();

        for _ in 0..(MAX_ATTEMPTS - 1) {
            claim_next(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .expect("still retryable");
            assert!(
                mark_failed(&db, "h1", "j1", "out of paper").await.unwrap(),
                "requeued"
            );
            assert_eq!(all(&db, "h1").await[0].status, STATUS_PENDING);
        }

        claim_next(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .expect("last hand-out");
        assert!(
            !mark_failed(&db, "h1", "j1", "out of paper").await.unwrap(),
            "out of attempts: dead-lettered, not requeued"
        );

        let dead = &all(&db, "h1").await[0];
        assert_eq!(dead.status, STATUS_DEAD);
        assert_eq!(dead.attempts, MAX_ATTEMPTS);
        assert_eq!(dead.last_error, "out of paper", "the reason is observable");
        assert!(
            claim_next(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_none()
        );
    }

    /// The queue is hub-scoped like the rest of the system schema: a job of one hub is invisible to
    /// another, and the same `jobId` in two hubs is two jobs.
    #[tokio::test]
    async fn the_queue_is_scoped_by_hub() {
        let db = queue_db().await;
        crate::system_migrations::apply(&db, "h2").await.unwrap();

        enqueue(&db, "h1", &job("j1", "receipt", "<p>h1</p>"))
            .await
            .unwrap();
        assert_eq!(
            enqueue(&db, "h2", &job("j1", "receipt", "<p>h2</p>"))
                .await
                .unwrap(),
            EnqueueOutcome::Queued,
            "the same jobId in another hub is another job"
        );

        assert!(
            claim_next(&db, "h2", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_some()
        );
        let h1 = claim_next(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .expect("h1 still has its own job");
        assert_eq!(h1.html, "<p>h1</p>");
    }

    /// The queue view can be filtered by role and status (what the print host and the UI ask for).
    #[tokio::test]
    async fn the_queue_can_be_filtered_by_role_and_status() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "<p>t</p>"))
            .await
            .unwrap();
        enqueue(&db, "h1", &job("j2", "kitchen", "<p>o</p>"))
            .await
            .unwrap();
        claim_next(&db, "h1", "kitchen", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .unwrap();

        let kitchen = list(&db, "h1", Some("kitchen"), None, 100).await.unwrap();
        assert_eq!(kitchen.len(), 1);
        assert_eq!(kitchen[0].status, STATUS_PRINTING);

        let pending = list(&db, "h1", None, Some(STATUS_PENDING), 100)
            .await
            .unwrap();
        assert_eq!(
            pending
                .iter()
                .map(|j| j.job_id.as_str())
                .collect::<Vec<_>>(),
            ["j1"]
        );
    }

    /// A job without an id, without a role or without a document is rejected before it reaches the
    /// database: an empty `jobId` would silently break the idempotency key for every other job.
    #[tokio::test]
    async fn a_job_without_id_role_or_document_is_rejected() {
        let db = queue_db().await;

        for bad in [
            job("", "receipt", "<p>t</p>"),
            job("j1", "", "<p>t</p>"),
            job("j1", "receipt", ""),
        ] {
            assert!(
                enqueue(&db, "h1", &bad).await.is_err(),
                "an incomplete job never reaches the queue"
            );
        }
        assert!(all(&db, "h1").await.is_empty());
    }

    /// The document is bounded: the print queue is not a file upload endpoint.
    #[tokio::test]
    async fn a_document_over_the_size_cap_is_rejected() {
        let db = queue_db().await;
        let huge = "x".repeat(MAX_HTML_BYTES + 1);
        assert!(enqueue(&db, "h1", &job("j1", "receipt", &huge))
            .await
            .is_err());
        assert!(all(&db, "h1").await.is_empty());
    }

    /// An unknown paper format is rejected: the print host would not know what to render.
    #[tokio::test]
    async fn an_unknown_paper_format_is_rejected() {
        let db = queue_db().await;
        let bad = NewPrintJob {
            job_id: "j1".into(),
            role: "receipt".into(),
            html: "<p>t</p>".into(),
            format: "a3".into(),
        };
        assert!(enqueue(&db, "h1", &bad).await.is_err());
        assert!(all(&db, "h1").await.is_empty());
    }
}
