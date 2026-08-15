//! Print queue **in the hub** (ADR-0196 §6, hub#341).
//!
//! Any device — the PWA in a phone included — enqueues `{ role, documentType, document, jobId }`
//! here. The device that has the installable app and sits on the printer's network registers as the
//! **print host** of that `role` and drains the queue over the runtime's WS (hub#342/#343). Because
//! the queue lives in the hub and not in the device:
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
//! ## The document travels STRUCTURED, never as HTML (hub#501)
//!
//! The queue used to store the ticket as a self-contained `html` string. It could not become paper:
//! `erplora_peripherals::escpos::render_document` renders **documents**, a `document_type` plus a
//! JSON body, and there is no entry that takes HTML. Ioan's decision (2026-08-08) is that the
//! document travels structured and **the HTML→ESC/POS translator is not written** — not now and not
//! as a stopgap:
//!
//!  - a structured document can be rendered to whatever is needed — screen, 58mm paper, 80mm paper,
//!    PDF — and **re-rendered tomorrow**, when the business changes printer or wants the ticket
//!    somewhere else;
//!  - frozen HTML is a photograph tied to the paper width of the day it was produced, and for every
//!    other destination it is useless. A ticket has to be **re-printable** and **viewable from the
//!    hub**, and neither works from a photograph.
//!
//! Consequence for this module: `document_type` is checked against the **closed vocabulary the
//! renderer knows** ([`DOCUMENT_TYPES`]) at the door, and `document` must be a JSON **object**. A
//! kitchen ticket that fails quietly is worse than one that never queues: nobody finds out until
//! the plate is missing.
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
//! ## The role is a STATION, resolved — not a string, compared (hub#457)
//!
//! `role` used to be stored exactly as it arrived and matched literally against what a print host
//! had registered, so `Kitchen`, `kitchen` and `kitchn` were **three queues** and the third one
//! never had a host. Since hub#457 it is [resolved](crate::print_stations::resolve) against
//! `_print_station`: what gets stored is the station's own `key` and `id`, an unknown one is a
//! **422 naming the stations this hub has**, and [`claim_next`] filters by `station_id` — its
//! parameter is not even a word any more. Same shape as the [`DOCUMENT_TYPES`] guard below,
//! applied to the field that was missing it.
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

/// Upper bound for the document of a single job, measured on its serialised JSON. A print job is a
/// ticket or an invoice, not a file upload: without a bound, any session could push arbitrary blobs
/// into the hub's database.
pub const MAX_DOCUMENT_BYTES: usize = 512 * 1024;

/// **The document vocabulary of the queue** — the wire strings
/// `erplora_peripherals::escpos::DocumentType` renders, and nothing else.
///
/// It is duplicated here on purpose rather than imported: `erplora-peripherals` is the *device's*
/// crate (mDNS, TCP sockets, hardware discovery) and the hub server has no business linking it in
/// to know the name of a document. What keeps the two honest is a test on **each** side —
/// [`tests::the_queue_vocabulary_is_the_one_the_renderer_knows`] here, and
/// `escpos::tests::the_wire_vocabulary_is_exactly_these_eight` there — plus the strict parse at the
/// printer, which refuses anything that got past this list instead of silently printing it as
/// `Generic`. Two guards, at two layers, with **different** messages: neither can mask the other.
pub const DOCUMENT_TYPES: [&str; 8] = [
    "receipt",
    "kitchen_order",
    "invoice",
    "delivery_note",
    "barcode_label",
    "cash_session_report",
    // The bill taken to the table before charging (ADR-0141, hub#748). It is NOT a receipt and
    // must not be queued as one: the renderer prints it without series number, payment method or
    // QR, and with the notice that it is not an invoice.
    "prebill",
    "generic",
];

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
///
/// `deny_unknown_fields` is the **retirement of `html`** made loud: a producer still sending the
/// old shape is told so at the door instead of having its ticket silently queued with an empty
/// document and discovered missing at the printer.
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct NewPrintJob {
    /// Idempotency key chosen by the producer. Two enqueues with the same one are one job.
    pub job_id: String,
    /// **Override of the station, in deprecation** (hub#987). Empty — the normal shape now — means
    /// "the hub decides", and [`crate::print_routes::route_for`] resolves it from
    /// [`document_type`](Self::document_type). A producer that still names one gets exactly that
    /// station, so nothing published broke the day the map landed.
    ///
    /// It is `#[serde(default)]` and not `Option` on purpose: absent and `""` mean the same thing
    /// ("I am not naming a printer"), and two spellings of one meaning is how the sloppy-input bug
    /// of hub#457 got in.
    #[serde(default)]
    pub role: String,
    /// Which document this is, from [`DOCUMENT_TYPES`]. Not the same axis as `role`: the role says
    /// *which printer*, this says *what shape* — an `invoice` can come out of the receipt printer.
    pub document_type: String,
    /// The document itself, structured: the JSON object `escpos::render_document` reads.
    pub document: serde_json::Value,
    /// Paper format. Defaults to [`FORMAT_RECEIPT`].
    #[serde(default = "default_format")]
    pub format: String,
}

fn default_format() -> String {
    FORMAT_RECEIPT.to_string()
}

/// A queued job as the hub stores it. The document is included because the print host needs it to
/// render; [`list`] is the observability view and returns the same shape.
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PrintJob {
    pub job_id: String,
    pub role: String,
    pub document_type: String,
    pub document: serde_json::Value,
    pub format: String,
    pub status: String,
    pub attempts: i64,
    pub created_at: String,
    pub last_error: String,
}

/// Columns every read of the queue returns, in the order [`row_to_job`] expects.
const JOB_COLUMNS: &str =
    "job_id, role, document_type, document, format, status, attempts, created_at, last_error";

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
    if job_id.is_empty() {
        return Err(invalid("job_id is required (it is the idempotency key)"));
    }
    let document_type = job.document_type.trim();
    // The vocabulary is CLOSED, and that is the point of this guard. An unknown document type
    // used to map to `Generic`, so a typo (`kitchn`) printed a nameless list of key/value pairs
    // where the kitchen expected an order — a failure nobody saw until the plate was missing.
    // Here it is a refusal, with the accepted names in the message.
    //
    // It runs BEFORE the station is resolved (hub#987) because since the map exists the document
    // type is what *decides* the station: routing an unvalidated word would be looking up a key
    // that cannot be in the map and falling open on a payload that should have been refused.
    if !DOCUMENT_TYPES.contains(&document_type) {
        return Err(invalid(format!(
            "unknown document type `{document_type}` (expected one of {})",
            DOCUMENT_TYPES.join(", ")
        )));
    }
    // **Two doors, and they fail in opposite directions on purpose** (hub#987).
    //
    // `role` named  → [`crate::print_stations::resolve`], which REFUSES an unknown one with a 422
    //   naming this hub's stations (hub#457). The producer is a human or a UI here, so the typo has
    //   to be visible — the fail-open must not relax this.
    // `role` empty  → [`crate::print_routes::route_for`], which NEVER refuses. The job said only
    //   what it *is*; there is no typo to show anybody, and the only choice left is paper somewhere
    //   or paper nowhere. It falls open to `receipt`, the station a hub cannot delete.
    //
    // Either way what gets stored is the station's own `key` and `id`, so `Kitchen`, ` kitchen ` and
    // `kitchen` are one queue and `claim_next` — which filters by id — finds the job.
    let station = if job.role.trim().is_empty() {
        crate::print_routes::route_for(db, hub_id, document_type).await?
    } else {
        crate::print_stations::resolve(db, hub_id, &job.role).await?
    };
    let role = station.key.as_str();
    // The renderer reads the document BY KEY (`data.get("items")`, `data.get("total")`). Handed an
    // array, a string or a number it finds nothing, renders every default and prints a blank ticket
    // without erroring — the same silent failure one layer down.
    let Some(fields) = job.document.as_object() else {
        return Err(invalid(
            "document must be a JSON object (the fields the printer renders)",
        ));
    };
    if fields.is_empty() {
        return Err(invalid("document is empty (there is nothing to print)"));
    }
    let document = job.document.to_string();
    if document.len() > MAX_DOCUMENT_BYTES {
        return Err(invalid(format!(
            "document is {} bytes, over the {MAX_DOCUMENT_BYTES} byte cap for a print job",
            document.len()
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
    p.insert("station_id".into(), json!(station.id));
    p.insert("document_type".into(), json!(document_type));
    p.insert("document".into(), json!(document));
    p.insert("format".into(), json!(job.format));
    p.insert("now".into(), json!(now_rfc3339()));
    // `ON CONFLICT DO NOTHING` (and not `DO UPDATE`) IS the idempotency guard: a repeated jobId
    // must neither add a second row nor rewrite the one already queued.
    let res = db
        .execute(
            "INSERT INTO _print_queue \
             (hub_id, job_id, role, station_id, document_type, document, format, status, \
              attempts, created_at) \
             VALUES (:hub_id, :job_id, :role, :station_id, :document_type, :document, :format, \
                     'pending', 0, :now) \
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

/// Hands the oldest `pending` job of a **station** to a print host, leasing it for `lease_seconds`.
///
/// **The parameter is a `station_id`, not a word** (hub#457), and that is the point: the hand-out
/// can no longer be missed because two sides spelled the destination differently. There is nothing
/// to spell — the caller had to resolve a station first ([`crate::print_stations::resolve`]), and
/// an unresolvable one never gets this far.
///
/// `FOR UPDATE SKIP LOCKED` makes the hand-out atomic: two hosts of the same station racing on the
/// same queue take **different** jobs, never the same ticket twice. The claim burns one attempt, so
/// a host that takes the job and disappears cannot keep it circulating forever.
pub async fn claim_next(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    station_id: &str,
    claimed_by: &str,
    lease_seconds: i64,
) -> Result<Option<PrintJob>> {
    let lease_expires_at =
        (chrono::Utc::now() + chrono::Duration::seconds(lease_seconds)).to_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("station_id".into(), json!(station_id));
    p.insert("claimed_by".into(), json!(claimed_by));
    p.insert("lease".into(), json!(lease_expires_at));
    let sql = format!(
        "UPDATE _print_queue SET status = '{STATUS_PRINTING}', attempts = attempts + 1, \
           claimed_by = :claimed_by, lease_expires_at = :lease \
         WHERE hub_id = :hub_id AND job_id = ( \
           SELECT job_id FROM _print_queue \
           WHERE hub_id = :hub_id AND station_id = :station_id AND status = '{STATUS_PENDING}' \
           ORDER BY seq LIMIT 1 FOR UPDATE SKIP LOCKED) \
         RETURNING {JOB_COLUMNS}"
    );
    let res = db.query(&sql, &p).await?;
    Ok(res.rows.first().map(row_to_job))
}

/// Test-only sugar: resolve `role` to its station and claim from it.
///
/// It exists so the suites written before hub#457 keep reading as "claim the kitchen's next job"
/// instead of threading an id through every case. Production code resolves explicitly — see
/// [`crate::print_drain::claim`], which must check the caller against the registry on the way.
#[cfg(test)]
pub(crate) async fn claim_next_role(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    role: &str,
    claimed_by: &str,
    lease_seconds: i64,
) -> Result<Option<PrintJob>> {
    let station = crate::print_stations::resolve(db, hub_id, role).await?;
    claim_next(db, hub_id, &station.id, claimed_by, lease_seconds).await
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

/// Which printer role a job belongs to, or `None` when **this hub** has no such job.
///
/// Exists for the drain's authorisation (hub#343): a print host may only close a job of a role it
/// hosts, and to know that you first have to know the job's role. Scoped by `hub_id` like every
/// other read here, so another hub's `jobId` is simply not a job as far as this one is concerned.
pub async fn role_of(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    job_id: &str,
) -> Result<Option<String>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("job_id".into(), json!(job_id));
    let res = db
        .query(
            "SELECT role FROM _print_queue WHERE hub_id = :hub_id AND job_id = :job_id",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["role"].as_str())
        .map(str::to_string))
}

/// Row of [`JOB_COLUMNS`] → [`PrintJob`].
///
/// The document is stored as JSON **text** and parsed back here. A row that does not parse becomes
/// `Value::Null`, which is not a silent recovery: `null` is not an object, so the printer's own
/// guard refuses it and the job is reported `failed` with a reason instead of coming out blank.
/// Nothing written through [`enqueue`] can be in that state — only a row edited by hand.
fn row_to_job(row: &serde_json::Value) -> PrintJob {
    let s = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    PrintJob {
        job_id: s("job_id"),
        role: s("role"),
        document_type: s("document_type"),
        document: serde_json::from_str(&s("document")).unwrap_or(serde_json::Value::Null),
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

    /// A ticket whose only distinguishing mark is `marker`, so a test can tell two documents apart.
    fn job(job_id: &str, role: &str, marker: &str) -> NewPrintJob {
        NewPrintJob {
            job_id: job_id.into(),
            role: role.into(),
            document_type: "receipt".into(),
            document: json!({ "receipt_id": marker, "total": 12.5 }),
            format: FORMAT_RECEIPT.into(),
        }
    }

    async fn all(db: &PgAdapter, hub_id: &str) -> Vec<PrintJob> {
        list(db, hub_id, None, None, 100).await.unwrap()
    }

    /// A job that says only WHAT it is — the shape hub#987 makes normal, with the hub deciding
    /// where it comes out.
    fn routed_job(job_id: &str, document_type: &str) -> NewPrintJob {
        NewPrintJob {
            job_id: job_id.into(),
            role: String::new(),
            document_type: document_type.into(),
            document: json!({ "total": 12.5 }),
            format: FORMAT_RECEIPT.into(),
        }
    }

    /// The station a queued job really landed on.
    async fn landed_on(db: &PgAdapter, hub_id: &str, job_id: &str) -> String {
        all(db, hub_id)
            .await
            .into_iter()
            .find(|j| j.job_id == job_id)
            .expect("the job was queued")
            .role
    }

    /// **The module says WHAT, the hub says WHERE** (hub#987). A producer that names no station gets
    /// routed by its document type — so `sales` can stop shipping `role: 'receipt'` and a kitchen
    /// order still reaches the kitchen.
    #[tokio::test]
    async fn a_job_that_names_no_station_is_routed_by_its_document_type() {
        let db = queue_db().await;

        enqueue(&db, "h1", &routed_job("j-kitchen", "kitchen_order"))
            .await
            .unwrap();
        enqueue(&db, "h1", &routed_job("j-ticket", "receipt"))
            .await
            .unwrap();
        enqueue(&db, "h1", &routed_job("j-label", "barcode_label"))
            .await
            .unwrap();

        assert_eq!(landed_on(&db, "h1", "j-kitchen").await, "kitchen");
        assert_eq!(landed_on(&db, "h1", "j-ticket").await, "receipt");
        assert_eq!(landed_on(&db, "h1", "j-label").await, "label");
    }

    /// …and the hub's map is what decides it, not a constant: re-point the document type and the
    /// next identical job comes out somewhere else, with no module touched.
    #[tokio::test]
    async fn re_pointing_the_map_moves_the_next_job_without_touching_a_module() {
        let db = queue_db().await;
        crate::print_routes::set(&db, "h1", "kitchen_order", "bar", "u1")
            .await
            .unwrap();

        enqueue(&db, "h1", &routed_job("j1", "kitchen_order"))
            .await
            .unwrap();

        assert_eq!(landed_on(&db, "h1", "j1").await, "bar");
    }

    /// `role` survives as a **full override** (in deprecation, hub#987): a producer that still sends
    /// one gets exactly what it asked for, so nothing published breaks on the day this lands.
    #[tokio::test]
    async fn an_explicit_role_still_overrides_the_map() {
        let db = queue_db().await;

        // The map says `kitchen_order` → `kitchen`; this producer insists on the bar.
        let mut job = routed_job("j1", "kitchen_order");
        job.role = "bar".into();
        enqueue(&db, "h1", &job).await.unwrap();

        assert_eq!(landed_on(&db, "h1", "j1").await, "bar");
    }

    /// **The door does NOT relax.** The fail-open is for a job that lost its destination, never for
    /// a producer that named one that does not exist: there the producer is a human or a UI, and the
    /// typo has to be visible. Still a 422 naming this hub's real stations (hub#457).
    #[tokio::test]
    async fn an_explicit_unknown_station_is_still_refused_at_the_door() {
        let db = queue_db().await;
        let mut job = routed_job("j1", "kitchen_order");
        job.role = "kitchn".into();

        let err = enqueue(&db, "h1", &job).await.unwrap_err();

        assert!(
            matches!(err, RuntimeError::InvalidPayload { .. }),
            "naming a station that does not exist is a bad payload, not a routing gap: {err}"
        );
        assert!(err.to_string().contains("kitchen"), "{err}");
        assert!(all(&db, "h1").await.is_empty(), "and nothing was queued");
    }

    /// **Fail OPEN** (hub#987, the market decision of hub#457). The merchant deleted the station its
    /// kitchen orders were routed to. The next order must come out at the counter — late, loud and
    /// on paper — and never be dropped the way Clover and Loyverse drop it.
    #[tokio::test]
    async fn a_job_whose_route_broke_comes_out_at_the_counter_not_nowhere() {
        let db = queue_db().await;
        let bar = crate::print_stations::resolve(&db, "h1", "bar").await.unwrap();
        crate::print_routes::set(&db, "h1", "kitchen_order", "bar", "u1")
            .await
            .unwrap();
        crate::print_stations::delete(&db, "h1", &bar.id).await.unwrap();

        let outcome = enqueue(&db, "h1", &routed_job("j1", "kitchen_order"))
            .await
            .unwrap();

        assert_eq!(outcome, EnqueueOutcome::Queued, "the job is NOT refused");
        assert_eq!(
            landed_on(&db, "h1", "j1").await,
            crate::print_stations::PROTECTED_KEY,
            "a job that already got in and lost its destination falls open to `receipt`"
        );
    }

    /// A job carries the station it landed on as a resolved `station_id`, whichever door routed it.
    /// Without that, `claim_next` — which filters by id — would never hand out a routed job.
    #[tokio::test]
    async fn a_routed_job_is_claimable_by_the_host_of_the_station_it_landed_on() {
        let db = queue_db().await;
        enqueue(&db, "h1", &routed_job("j1", "kitchen_order"))
            .await
            .unwrap();

        let claimed = claim_next_role(&db, "h1", "kitchen", "till-1", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .expect("the kitchen's host finds the order the map sent there");
        assert_eq!(claimed.job_id, "j1");
    }

    /// **The idempotency guard.** Enqueueing the same `jobId` twice is ONE job: the second call is
    /// a no-op that reports `Duplicate`, and it does not overwrite the document already queued
    /// (a retry must never mutate the ticket the printer is about to produce).
    #[tokio::test]
    async fn enqueueing_the_same_job_id_twice_does_not_duplicate_the_job() {
        let db = queue_db().await;

        let first = enqueue(&db, "h1", &job("j1", "receipt", "T-first"))
            .await
            .unwrap();
        assert_eq!(first, EnqueueOutcome::Queued);

        // Same jobId, different body: the retry of a request whose response got lost.
        let second = enqueue(&db, "h1", &job("j1", "receipt", "T-OTHER"))
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
            jobs[0].document["receipt_id"], "T-first",
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
            enqueue(&db, "h1", &job("j1", "kitchen", "K-order"))
                .await
                .unwrap();
        }

        // New process over the same data: re-running the system migrations is idempotent and the
        // job is still there, still claimable.
        let db = test_db.adapter().await;
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        let claimed = claim_next_role(&db, "h1", "kitchen", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .expect("the job waited across the restart");
        assert_eq!(claimed.job_id, "j1");
        assert_eq!(claimed.document["receipt_id"], "K-order");
        assert_eq!(claimed.document_type, "receipt");
    }

    /// A job already claimed by a print host is not handed to a second one while its lease holds.
    #[tokio::test]
    async fn a_claimed_job_is_not_handed_out_again() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "T-1"))
            .await
            .unwrap();

        let first = claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap();
        assert_eq!(first.map(|j| j.job_id), Some("j1".to_string()));

        let second = claim_next_role(&db, "h1", "receipt", "host-b", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap();
        assert!(second.is_none(), "two hosts must not print the same ticket");
    }

    /// A drained (confirmed) job is terminal: no host ever sees it again.
    #[tokio::test]
    async fn a_drained_job_is_never_handed_out_again() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "T-1"))
            .await
            .unwrap();
        claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .unwrap();
        assert!(mark_done(&db, "h1", "j1").await.unwrap());

        // Neither directly…
        assert!(
            claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_none()
        );
        // …nor through the lease sweeper (a done job has no lease to expire).
        assert_eq!(reclaim_expired(&db, "h1").await.unwrap(), 0);
        assert_eq!(all(&db, "h1").await[0].status, STATUS_DONE);
    }

    /// **Confirming a job this hub does not have is a plain `false`, not a shrug.** The return value
    /// is the whole contract of `mark_done` — the drain answers `{"confirmed": …}` with it, and the
    /// host reads that to decide whether the debt is paid. A `mark_done` that always said "yes"
    /// would let a host tick off a ticket that was never queued here (another hub's `jobId`, a
    /// typo), and the frame it gets back would be a lie.
    ///
    /// Its positive twin is `a_drained_job_is_never_handed_out_again`. Both are needed: with only
    /// the positive one, "always true" passes.
    #[tokio::test]
    async fn confirming_a_job_this_hub_does_not_have_is_a_plain_no() {
        let db = queue_db().await;
        crate::system_migrations::apply(&db, "h2").await.unwrap();
        enqueue(&db, "h2", &job("j-next-door", "receipt", "T-h2"))
            .await
            .unwrap();

        assert!(
            !mark_done(&db, "h1", "never-existed").await.unwrap(),
            "an id this hub never had is not a confirmation"
        );
        assert!(
            !mark_done(&db, "h1", "j-next-door").await.unwrap(),
            "and neither is another hub's job, which from here is simply not a job"
        );

        // The neighbour is untouched throughout: its ticket is still waiting for its own host.
        assert_eq!(
            list(&db, "h2", None, None, 10).await.unwrap()[0].status,
            STATUS_PENDING,
            "confirming from the wrong hub must not close somebody else's ticket"
        );
    }

    /// A job that already reached a **terminal** state is not confirmable a second time either —
    /// which is what keeps the answer meaningful when a host re-sends its debt after a reconnect.
    #[tokio::test]
    async fn confirming_an_already_terminal_job_is_also_a_no() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "T-1")).await.unwrap();
        claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .unwrap();

        assert!(mark_done(&db, "h1", "j1").await.unwrap(), "the first one counts");
        assert!(
            !mark_done(&db, "h1", "j1").await.unwrap(),
            "the second one changed nothing, and says so"
        );
        assert_eq!(all(&db, "h1").await[0].status, STATUS_DONE);
    }

    /// Even re-enqueueing the same `jobId` after it printed does not print it twice: the row still
    /// exists, so the idempotency key still holds. This is the double-tap the cashier does when the
    /// ticket is slow to come out.
    #[tokio::test]
    async fn re_enqueueing_a_job_id_that_already_printed_does_not_print_it_again() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "T-1"))
            .await
            .unwrap();
        claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .unwrap();
        mark_done(&db, "h1", "j1").await.unwrap();

        let again = enqueue(&db, "h1", &job("j1", "receipt", "T-1"))
            .await
            .unwrap();
        assert_eq!(again, EnqueueOutcome::Duplicate);
        assert!(
            claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
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
            enqueue(&db, "h1", &job(id, "kitchen", "K-1"))
                .await
                .unwrap();
        }

        let listed: Vec<String> = all(&db, "h1").await.into_iter().map(|j| j.job_id).collect();
        assert_eq!(listed, ["j1", "j2", "j3"], "the queue order is observable");

        let mut handed = Vec::new();
        while let Some(j) = claim_next_role(&db, "h1", "kitchen", "host-a", DEFAULT_LEASE_SECONDS)
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
        enqueue(&db, "h1", &job("j1", "kitchen", "K-1"))
            .await
            .unwrap();

        assert!(
            claim_next_role(&db, "h1", "bar", "host-bar", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_none(),
            "a bar host must not drain the kitchen queue"
        );
        assert!(
            claim_next_role(&db, "h1", "kitchen", "host-kitchen", DEFAULT_LEASE_SECONDS)
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
        enqueue(&db, "h1", &job("j1", "receipt", "T-1"))
            .await
            .unwrap();

        // Lease already in the past = the host took it and never came back.
        claim_next_role(&db, "h1", "receipt", "dead-host", -1)
            .await
            .unwrap()
            .unwrap();
        assert!(
            claim_next_role(&db, "h1", "receipt", "host-b", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_none(),
            "still claimed until the sweeper runs"
        );

        assert_eq!(reclaim_expired(&db, "h1").await.unwrap(), 1);
        let back = claim_next_role(&db, "h1", "receipt", "host-b", DEFAULT_LEASE_SECONDS)
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
        enqueue(&db, "h1", &job("j1", "receipt", "T-1"))
            .await
            .unwrap();

        for _ in 0..(MAX_ATTEMPTS - 1) {
            claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .expect("still retryable");
            assert!(
                mark_failed(&db, "h1", "j1", "out of paper").await.unwrap(),
                "requeued"
            );
            assert_eq!(all(&db, "h1").await[0].status, STATUS_PENDING);
        }

        claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
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
            claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
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

        enqueue(&db, "h1", &job("j1", "receipt", "T-h1"))
            .await
            .unwrap();
        assert_eq!(
            enqueue(&db, "h2", &job("j1", "receipt", "T-h2"))
                .await
                .unwrap(),
            EnqueueOutcome::Queued,
            "the same jobId in another hub is another job"
        );

        assert!(
            claim_next_role(&db, "h2", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_some()
        );
        let h1 = claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .expect("h1 still has its own job");
        assert_eq!(h1.document["receipt_id"], "T-h1");
    }

    /// **Which role a job belongs to — the answer the drain's authorisation is built on.**
    ///
    /// `role_of` is what lets `print_drain` refuse a host that reaches for somebody else's queue, so
    /// it has to be right in three different ways and each one protects something different: the
    /// **real** role (or the guard compares against nothing), `None` for an id that does not exist
    /// (or the confirmation door doubles as a directory of `jobId`s), and `None` for **another
    /// hub's** job (or a neighbour's ticket becomes closable from here).
    ///
    /// The neighbour is **alive and holding its ticket** for the whole test, and is asserted
    /// untouched at the end: retiring its row first would let a query with no `hub_id` pass.
    #[tokio::test]
    async fn the_role_of_a_job_is_reported_only_for_this_hubs_own_jobs() {
        let db = queue_db().await;
        crate::system_migrations::apply(&db, "h2").await.unwrap();
        enqueue(&db, "h1", &job("j-mine", "kitchen", "K-1"))
            .await
            .unwrap();
        enqueue(&db, "h2", &job("j-next-door", "bar", "B-1"))
            .await
            .unwrap();

        assert_eq!(
            role_of(&db, "h1", "j-mine").await.unwrap(),
            Some("kitchen".to_string()),
            "the real role, or the drain's guard compares against nothing"
        );
        assert_eq!(
            role_of(&db, "h1", "never-existed").await.unwrap(),
            None,
            "an id nobody queued is not a job"
        );
        assert_eq!(
            role_of(&db, "h1", "j-next-door").await.unwrap(),
            None,
            "another hub's job is, from here, not a job at all"
        );

        // …and asking about it did not disturb it: it is still waiting for its own bar host.
        let neighbour = list(&db, "h2", None, None, 10).await.unwrap();
        assert_eq!(neighbour.len(), 1);
        assert_eq!(neighbour[0].status, STATUS_PENDING);
        assert_eq!(neighbour[0].role, "bar");
    }

    /// The queue view can be filtered by role and status (what the print host and the UI ask for).
    #[tokio::test]
    async fn the_queue_can_be_filtered_by_role_and_status() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "receipt", "T-1"))
            .await
            .unwrap();
        enqueue(&db, "h1", &job("j2", "kitchen", "K-2"))
            .await
            .unwrap();
        claim_next_role(&db, "h1", "kitchen", "host-a", DEFAULT_LEASE_SECONDS)
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

    /// A job without an id or without a document is rejected before it reaches the database: an
    /// empty `jobId` would silently break the idempotency key for every other job.
    ///
    /// ⚠️ **An empty `role` used to be on this list and deliberately is not any more** (hub#987).
    /// It was right while `role` was the only way to say where a job went; now it is the *normal*
    /// way to say "the hub decides", and the map routes it by document type
    /// ([`tests::a_job_that_names_no_station_is_routed_by_its_document_type`]). What is still
    /// refused is naming a station that does not exist — see
    /// [`tests::an_explicit_unknown_station_is_still_refused_at_the_door`], which is where that
    /// half of the guard moved.
    #[tokio::test]
    async fn a_job_without_id_or_document_is_rejected() {
        let db = queue_db().await;

        for bad in [
            job("", "receipt", "T-1"),
            NewPrintJob {
                job_id: "j1".into(),
                role: "receipt".into(),
                document_type: "receipt".into(),
                document: json!({}),
                format: FORMAT_RECEIPT.into(),
            },
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
        let huge = "x".repeat(MAX_DOCUMENT_BYTES + 1);
        assert!(enqueue(&db, "h1", &job("j1", "receipt", &huge))
            .await
            .is_err());
        assert!(all(&db, "h1").await.is_empty());
    }

    // ── The document travels structured (hub#501) ─────────────────────────────────────────────

    /// **The whole point of hub#501.** What comes out of the queue is the same structured document
    /// that went in — the shape `escpos::render_document` reads — and not a rendering of it. That is
    /// what lets the same ticket go to 58mm paper, 80mm paper, a PDF or a screen, today and next
    /// year, instead of being a photograph of one printer's width.
    #[tokio::test]
    async fn the_document_reaches_the_print_host_structured_and_unchanged() {
        let db = queue_db().await;
        let document = json!({
            "business_name": "Bar Manolo",
            "receipt_id": "T-42",
            "items": [{ "name": "Cafe", "quantity": 2, "total": 2.4 }],
            "total": 2.4,
        });
        enqueue(
            &db,
            "h1",
            &NewPrintJob {
                job_id: "j1".into(),
                role: "receipt".into(),
                document_type: "receipt".into(),
                document: document.clone(),
                format: FORMAT_RECEIPT.into(),
            },
        )
        .await
        .unwrap();

        let claimed = claim_next_role(&db, "h1", "receipt", "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .expect("the host claims the ticket");
        assert_eq!(
            claimed.document, document,
            "the host receives the document it can render, byte for byte the one queued"
        );
        assert_eq!(claimed.document_type, "receipt");
    }

    /// **A document type the renderer does not know is refused at the door.** An unknown type
    /// used to map to `Generic`, so a typo printed a nameless key/value dump where the kitchen
    /// expected an order — and nobody found out until the plate was missing. The refusal names
    /// the accepted vocabulary so the producer can fix it.
    #[tokio::test]
    async fn a_document_type_the_printer_does_not_know_is_rejected() {
        let db = queue_db().await;

        // `Kitchen` and `kitchn` are the two ways this goes wrong in practice: wrong case, and a
        // typo. Both used to become `Generic` in silence.
        for bad in ["Kitchen", "kitchn", "", "html"] {
            let err = enqueue(
                &db,
                "h1",
                &NewPrintJob {
                    job_id: "j1".into(),
                    role: "kitchen".into(),
                    document_type: bad.into(),
                    document: json!({ "receipt_id": "K-1" }),
                    format: FORMAT_RECEIPT.into(),
                },
            )
            .await
            .expect_err("an unprintable document type never reaches the queue");
            assert!(
                err.to_string().contains("kitchen_order"),
                "the refusal says what IS accepted, or the producer cannot fix it: {err}"
            );
        }
        assert!(all(&db, "h1").await.is_empty());
    }

    /// Every name in the vocabulary is actually accepted — otherwise the guard above could be a
    /// blanket refusal and no test would notice.
    #[tokio::test]
    async fn every_document_type_of_the_vocabulary_is_accepted() {
        let db = queue_db().await;
        for (i, kind) in DOCUMENT_TYPES.iter().enumerate() {
            enqueue(
                &db,
                "h1",
                &NewPrintJob {
                    job_id: format!("j{i}"),
                    role: "receipt".into(),
                    document_type: (*kind).into(),
                    document: json!({ "receipt_id": kind }),
                    format: FORMAT_RECEIPT.into(),
                },
            )
            .await
            .unwrap_or_else(|e| panic!("`{kind}` is in the vocabulary and must queue: {e}"));
        }
        assert_eq!(all(&db, "h1").await.len(), DOCUMENT_TYPES.len());
    }

    /// **The bill the waiter takes to the table can be queued** (hub#748).
    ///
    /// It is the paper a restaurant prints most often — once before every payment — and `prebill`
    /// was in neither of the two lists, so the queue refused it at the door and the renderer would
    /// have refused it one layer later. A hub whose queue cannot take the bill is a hub where the
    /// waiter has nothing to carry to the table.
    #[tokio::test]
    async fn the_bill_taken_to_the_table_can_be_queued() {
        let db = queue_db().await;
        enqueue(
            &db,
            "h1",
            &NewPrintJob {
                job_id: "prebill-o1-3".into(),
                role: "receipt".into(),
                document_type: "prebill".into(),
                document: json!({ "items": [{ "name": "Cafe", "quantity": 2, "total": 2.4 }], "total": 2.4 }),
                format: FORMAT_RECEIPT.into(),
            },
        )
        .await
        .expect("the bill is a document of this queue");
        assert_eq!(all(&db, "h1").await.len(), 1, "and it is waiting for a print host");
    }

    /// The queue's vocabulary is **the renderer's**, spelled the way the wire spells it. The
    /// counterpart lives in `escpos` (`the_wire_vocabulary_is_exactly_these_eight`); this side pins
    /// that nobody adds a name here that the printer would silently degrade to `Generic`.
    #[test]
    fn the_queue_vocabulary_is_the_one_the_renderer_knows() {
        assert_eq!(
            DOCUMENT_TYPES.len(),
            8,
            "adding a document type means adding it to escpos::DocumentType too"
        );
        for name in DOCUMENT_TYPES {
            assert_eq!(
                name,
                name.to_lowercase(),
                "the wire spelling is snake_case: `{name}` would not deserialise"
            );
        }
    }

    /// **A document that is not a JSON object is refused.** The renderer reads it by key, so an
    /// array or a string finds nothing, takes every default and prints a blank ticket without
    /// erroring — the same silent failure the type guard above prevents, one layer along.
    #[tokio::test]
    async fn a_document_that_is_not_an_object_is_rejected() {
        let db = queue_db().await;

        for bad in [
            json!("<p>ticket</p>"),
            json!([{ "name": "Cafe" }]),
            json!(42),
            json!(null),
            json!({}),
        ] {
            assert!(
                enqueue(
                    &db,
                    "h1",
                    &NewPrintJob {
                        job_id: "j1".into(),
                        role: "receipt".into(),
                        document_type: "receipt".into(),
                        document: bad.clone(),
                        format: FORMAT_RECEIPT.into(),
                    },
                )
                .await
                .is_err(),
                "{bad} is not a document the printer can render"
            );
        }
        assert!(all(&db, "h1").await.is_empty());
    }

    /// **The retired `html` field is refused, not ignored.** A producer that never got the memo
    /// would otherwise have its ticket queued with whatever else it sent and discover the loss at
    /// the printer; here it is told at the door.
    #[test]
    fn a_job_still_sending_the_retired_html_field_is_refused() {
        let err = serde_json::from_value::<NewPrintJob>(json!({
            "jobId": "j1",
            "role": "receipt",
            "html": "<p>ticket</p>",
        }))
        .expect_err("the old shape is not a job any more");
        assert!(
            err.to_string().contains("html"),
            "the refusal names the field that no longer exists: {err}"
        );
    }

    /// The cap is a limit, not an off-by-one: a document of **exactly** the maximum is a document.
    /// Without this, moving the comparison one notch would go unnoticed and a ticket right on the
    /// boundary would stop printing for no reason anybody could explain.
    #[tokio::test]
    async fn a_document_of_exactly_the_size_cap_is_accepted() {
        let db = queue_db().await;
        // Pad the ticket id until the serialised document weighs exactly the cap.
        let skeleton = json!({ "receipt_id": "" }).to_string().len();
        let exact = NewPrintJob {
            job_id: "j1".into(),
            role: "receipt".into(),
            document_type: "receipt".into(),
            document: json!({ "receipt_id": "x".repeat(MAX_DOCUMENT_BYTES - skeleton) }),
            format: FORMAT_RECEIPT.into(),
        };
        assert_eq!(exact.document.to_string().len(), MAX_DOCUMENT_BYTES);

        assert_eq!(
            enqueue(&db, "h1", &exact).await.unwrap(),
            EnqueueOutcome::Queued,
            "judged by what it weighs, and the cap is a weight it may reach"
        );
    }

    /// **The cap is pinned from both ends**, because neither number follows from the other:
    ///
    ///  - **big enough for a real ticket**: an invoice with two hundred lines and notes on half of
    ///    them is still only text. A cap that refused one would stop a legitimate sale from
    ///    printing, which is worse than anything it is defending against;
    ///  - **still a bound**: this lands in the hub's database and **any session can post to it**, so
    ///    it has to stay visibly nowhere near a file upload.
    ///
    /// Pinned in absolute numbers on purpose. Expressed against the constant, this test would move
    /// with it — and a cap silently reduced to 1.5 KiB would pass everything.
    #[test]
    fn the_document_cap_fits_a_real_ticket_and_is_still_a_bound() {
        assert!(
            MAX_DOCUMENT_BYTES >= 64 * 1024,
            "a long invoice must never be too big to print"
        );
        assert!(
            MAX_DOCUMENT_BYTES <= 1024 * 1024,
            "the print queue is not an upload endpoint"
        );
    }

    /// **A ticket omits `format`**, because 80mm paper is what a ticket is; only an invoice has to
    /// say otherwise. The default is part of the producer contract (`PrintRequest` in the shell
    /// leaves it out), so it is deserialised here rather than assumed.
    #[tokio::test]
    async fn a_job_that_does_not_say_its_paper_defaults_to_a_ticket() {
        let db = queue_db().await;
        let job: NewPrintJob = serde_json::from_value(json!({
            "jobId": "j1",
            "role": "receipt",
            "documentType": "receipt",
            "document": { "receipt_id": "T-1" },
        }))
        .expect("a job without `format` is a complete job");
        assert_eq!(job.format, FORMAT_RECEIPT);

        enqueue(&db, "h1", &job)
            .await
            .expect("and it queues: the default has to be a format the queue accepts");
        assert_eq!(all(&db, "h1").await[0].format, FORMAT_RECEIPT);
    }

    /// An unknown paper format is rejected: the print host would not know what to render.
    #[tokio::test]
    async fn an_unknown_paper_format_is_rejected() {
        let db = queue_db().await;
        let bad = NewPrintJob {
            job_id: "j1".into(),
            role: "receipt".into(),
            document_type: "receipt".into(),
            document: json!({ "receipt_id": "T-1" }),
            format: "a3".into(),
        };
        assert!(enqueue(&db, "h1", &bad).await.is_err());
        assert!(all(&db, "h1").await.is_empty());
    }

    // ── Stations as rows (hub#457) ─────────────────────────────────────────────────────────────

    /// **The bug this issue is about.** `kitchn` is not a case variant of anything, so no amount of
    /// `to_lowercase` would have caught it: it used to open a queue of its own that no host could
    /// ever drain, and the plate went missing. Resolved against the station table it is simply not
    /// a destination, and the refusal — a 422, like the sibling `documentType` guard right above —
    /// names the ones that are.
    #[tokio::test]
    async fn a_job_for_a_station_this_hub_does_not_have_is_refused_naming_the_real_ones() {
        let db = queue_db().await;
        let err = enqueue(&db, "h1", &job("j1", "kitchn", "K-1"))
            .await
            .unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("kitchn"), "it says what was rejected: {msg}");
        assert!(
            msg.contains("kitchen"),
            "and what this hub really has, so the typo is visible: {msg}"
        );
        assert!(
            all(&db, "h1").await.is_empty(),
            "a ticket nobody can print must not be queued at all"
        );
    }

    /// **`Kitchen` and `kitchen` are ONE queue now.** The case tolerance stays at the door and the
    /// row is stored against the station, so a job enqueued with stray case is handed to the host
    /// registered with the canonical spelling — which before was the second of the three ways to
    /// open an orphan queue.
    #[tokio::test]
    async fn a_job_enqueued_with_stray_case_lands_in_the_canonical_station() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j1", "  Kitchen ", "K-1"))
            .await
            .unwrap();

        let jobs = all(&db, "h1").await;
        assert_eq!(
            jobs[0].role, "kitchen",
            "what is stored is the STATION's key, never the string that was typed"
        );

        let station = crate::print_stations::resolve(&db, "h1", "kitchen")
            .await
            .unwrap();
        let claimed = claim_next(&db, "h1", &station.id, "host-a", DEFAULT_LEASE_SECONDS)
            .await
            .unwrap()
            .expect("the host of the kitchen station takes it");
        assert_eq!(claimed.job_id, "j1");
    }

    /// The hand-out is by **station id**, not by a word. Two stations of one hub never see each
    /// other's work, and the filter cannot be defeated by how anybody spells anything.
    #[tokio::test]
    async fn claiming_is_scoped_to_the_station_and_never_to_a_spelling() {
        let db = queue_db().await;
        enqueue(&db, "h1", &job("j-bar", "bar", "B-1")).await.unwrap();
        let kitchen = crate::print_stations::resolve(&db, "h1", "kitchen")
            .await
            .unwrap();

        assert!(
            claim_next(&db, "h1", &kitchen.id, "host-a", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .is_none(),
            "the kitchen does not take the bar's ticket"
        );
        let bar = crate::print_stations::resolve(&db, "h1", "bar").await.unwrap();
        assert_eq!(
            claim_next(&db, "h1", &bar.id, "host-b", DEFAULT_LEASE_SECONDS)
                .await
                .unwrap()
                .expect("the bar does")
                .job_id,
            "j-bar"
        );
    }
}
