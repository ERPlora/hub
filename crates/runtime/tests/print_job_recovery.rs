//! hub#1108 — a stuck print job can be **put back** or **closed**, and neither gesture is a delete.
//!
//! Until now `_print_queue` had no way out. `enqueue` · `claim_next` · `mark_done` · `mark_failed` ·
//! `reclaim_expired` · `list` · `role_of` are all the machine has, and none of them re-humanises a
//! `dead` row or retires one nobody is ever going to print. A job that ran out of hand-outs stayed
//! `dead` for good and a job from a QA session or a badly written flow occupied the queue forever:
//! the only ways out were draining it or waiting.
//!
//! The shape is the outbox's (hub#660, exposed by hub#953), because it is the same problem and this
//! codebase already answered it:
//!
//!  - **requeue** — back to `pending` with `attempts` reset. Resetting is the whole point:
//!    `MAX_ATTEMPTS` is what sent it to `dead`, so a retry that kept the count would die on its
//!    first hand-out. It cannot be "enqueue it again": the PK is `(hub_id, job_id)` with
//!    `ON CONFLICT DO NOTHING`, so re-enqueueing the same id is a no-op **by construction**.
//!  - **discard** — status `discarded` plus who, when and why. **Never a `DELETE`**: the row is the
//!    only proof the ticket existed, and ADR-0196's own reading of `dead` ("diagnosis, not
//!    deletion") applies harder to a decision a person took.
use erplora_db::testutil::{fresh_db, two_adapters_sharing_a_schema};
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::print_queue::{
    self, DiscardOutcome, NewPrintJob, RequeueOutcome, MAX_ATTEMPTS, STATUS_DEAD, STATUS_DISCARDED,
    STATUS_PENDING,
};
use erplora_runtime::{print_stations, Runtime};
use serde_json::json;

const WHO: &str = "hub_user:admin-1";
/// The module the gesture came THROUGH (hub#1532) — resolved at the door from `X-Erplora-Module`
/// and already checked against the `printer` grant before it reaches the runtime.
const THROUGH: &str = "printing";
/// …and what the runtime is handed when nobody but the person acted: the shell, `curl`.
const NO_MODULE: &str = "";

async fn runtime(hub_id: &str) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn enqueue(rt: &Runtime, job_id: &str) {
    let job: NewPrintJob = serde_json::from_value(json!({
        "jobId": job_id,
        "role": "kitchen",
        "documentType": "kitchen_order",
        "document": { "lines": [] },
    }))
    .unwrap();
    rt.enqueue_print_job(&job).await.unwrap();
}

/// Drives a job to `dead` the way the machine really does: hand it out `MAX_ATTEMPTS` times and let
/// the host report a failure each time. Seeding `status='dead'` by hand would prove nothing about
/// the state the queue actually produces.
async fn kill(rt: &Runtime, job_id: &str) {
    for _ in 0..MAX_ATTEMPTS {
        claim(rt, "till-1")
            .await
            .expect("there is a job to hand out");
        print_queue::mark_failed(rt.db_for_test(), rt.hub_id(), job_id, "printer offline")
            .await
            .unwrap();
    }
    assert_eq!(
        status_of(rt, job_id).await,
        STATUS_DEAD,
        "the job must be dead"
    );
}

/// Hands out the kitchen's next job to `device`, the way a print host draining the queue would.
async fn claim(rt: &Runtime, device: &str) -> Option<print_queue::PrintJob> {
    let station = print_stations::resolve(rt.db_for_test(), rt.hub_id(), "kitchen")
        .await
        .unwrap();
    print_queue::claim_next(rt.db_for_test(), rt.hub_id(), &station.id, device, 90)
        .await
        .unwrap()
}

async fn status_of(rt: &Runtime, job_id: &str) -> String {
    rt.print_queue(None, None, 500)
        .await
        .unwrap()
        .into_iter()
        .find(|j| j.job_id == job_id)
        .map(|j| j.status)
        .unwrap_or_default()
}

/// One row of `_print_queue`, read raw — the discard stamp is not part of the status view.
async fn row(db: &dyn DatabaseAdapter, hub_id: &str, job_id: &str) -> serde_json::Value {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("job_id".into(), json!(job_id));
    db.query(
        "SELECT status, attempts, last_error, discarded_at, discarded_by, discarded_by_module, \
                discard_reason, retried_at, retried_by, retried_by_module \
         FROM _print_queue WHERE hub_id = :hub_id AND job_id = :job_id",
        &p,
    )
    .await
    .unwrap()
    .rows
    .first()
    .cloned()
    .unwrap_or(serde_json::Value::Null)
}

/// The gesture the issue exists for: a dead ticket goes back in front of the print hosts, with its
/// full budget of hand-outs back.
#[tokio::test]
async fn a_dead_job_goes_back_to_the_queue_with_its_attempts_reset() {
    let rt = runtime("hub-requeue").await;
    enqueue(&rt, "j1").await;
    kill(&rt, "j1").await;

    let outcome = rt.retry_print_job("j1", WHO, NO_MODULE).await.unwrap();

    assert!(matches!(outcome, RequeueOutcome::Requeued(_)), "{outcome:?}");
    let row = row(rt.db_for_test(), "hub-requeue", "j1").await;
    assert_eq!(row["status"], STATUS_PENDING);
    assert_eq!(
        row["attempts"], 0,
        "MAX_ATTEMPTS is what killed it: a retry that kept the count dies on its first hand-out"
    );
    assert_eq!(row["last_error"], "", "the old reason is not the new one");

    // …and it is really claimable again: the requeue is not a cosmetic status change.
    let handed = claim(&rt, "till-2").await;
    assert_eq!(handed.map(|j| j.job_id).as_deref(), Some("j1"));
}

/// `requeue` is not a general "change this job's status": every state that is not `dead` is refused
/// **naming the state**, so a screen can say why instead of reporting a move that never happened.
#[tokio::test]
async fn only_a_dead_job_can_be_requeued() {
    let rt = runtime("hub-requeue-guard").await;
    enqueue(&rt, "waiting").await;

    let outcome = rt
        .retry_print_job("waiting", WHO, NO_MODULE)
        .await
        .unwrap();
    assert_eq!(
        outcome,
        RequeueOutcome::NotRequeueable {
            status: STATUS_PENDING.to_string()
        },
        "a job that is already waiting has nothing to retry"
    );
    assert_eq!(status_of(&rt, "waiting").await, STATUS_PENDING);

    // An id this hub never heard of is NOT FOUND — never a silent success.
    assert_eq!(
        rt.retry_print_job("never-existed", WHO, NO_MODULE)
            .await
            .unwrap(),
        RequeueOutcome::NotFound
    );
}

/// Discard closes the row and leaves the evidence: who, when and — the only half the hub cannot
/// know — why. The relay of hand-outs never sees it again because `claim_next` only claims
/// `pending`.
#[tokio::test]
async fn discard_stamps_the_row_and_never_deletes_it() {
    let rt = runtime("hub-discard").await;
    enqueue(&rt, "ghost").await;

    let outcome = rt
        .discard_print_job("ghost", WHO, NO_MODULE, "  de una sesión de QA  ")
        .await
        .unwrap();

    let DiscardOutcome::Discarded(stamp) = outcome else {
        panic!("a waiting job can be retired: {outcome:?}");
    };
    assert_eq!(stamp.job_id, "ghost");
    assert_eq!(
        stamp.discarded_by, WHO,
        "the identity comes from the session, never the body"
    );
    assert_eq!(
        stamp.discard_reason, "de una sesión de QA",
        "the reason is stored trimmed, and what comes back is what was STORED"
    );
    assert!(!stamp.discarded_at.is_empty());

    let row = row(rt.db_for_test(), "hub-discard", "ghost").await;
    assert!(
        !row.is_null(),
        "the row is the only proof the ticket existed: it STAYS"
    );
    assert_eq!(row["status"], STATUS_DISCARDED);
    assert_eq!(row["discarded_by"], WHO);
    assert_eq!(row["discard_reason"], "de una sesión de QA");

    // And no print host will ever be handed it again.
    let handed = claim(&rt, "till-1").await;
    assert!(
        handed.is_none(),
        "a discarded job is not claimable: {handed:?}"
    );
}

/// A dead job is the other thing a person retires — the row that will never come out and is sitting
/// in the operator's list.
#[tokio::test]
async fn a_dead_job_can_be_retired_too() {
    let rt = runtime("hub-discard-dead").await;
    enqueue(&rt, "j1").await;
    kill(&rt, "j1").await;

    let outcome = rt
        .discard_print_job("j1", WHO, NO_MODULE, "")
        .await
        .unwrap();

    assert!(
        matches!(outcome, DiscardOutcome::Discarded(_)),
        "{outcome:?}"
    );
    assert_eq!(status_of(&rt, "j1").await, STATUS_DISCARDED);
}

/// **A job a host is holding is not retired under its hands.** The lease already covers the host
/// that died (`reclaim_expired` returns it to `pending`, and THEN it can be discarded); binning it
/// while a real host is rendering it would be the silent loss this queue exists to prevent.
#[tokio::test]
async fn a_job_a_host_is_printing_is_not_retired_under_its_hands() {
    let rt = runtime("hub-discard-live").await;
    enqueue(&rt, "in-flight").await;
    claim(&rt, "till-1").await.expect("the host takes it");

    let outcome = rt
        .discard_print_job("in-flight", WHO, NO_MODULE, "")
        .await
        .unwrap();

    assert_eq!(
        outcome,
        DiscardOutcome::NotDiscardable {
            status: "printing".to_string()
        }
    );
    assert_eq!(status_of(&rt, "in-flight").await, "printing");
}

/// Discarding something that is not in this hub's queue is `NotFound`, not a `200` that pretends.
#[tokio::test]
async fn discarding_an_unknown_job_is_not_a_silent_success() {
    let rt = runtime("hub-discard-404").await;
    assert_eq!(
        rt.discard_print_job("never-existed", WHO, NO_MODULE, "")
            .await
            .unwrap(),
        DiscardOutcome::NotFound
    );
}

/// Tenancy (ADR-0201): both gestures act on **this hub's** queue and cannot reach across, even with
/// the exact `jobId` of the other tenant — which is the one id an attacker would have, because
/// `jobId` is chosen by the producer and the same string is a legitimate job in both hubs.
#[tokio::test]
async fn neither_gesture_reaches_another_hubs_queue() {
    let (a, b) = two_adapters_sharing_a_schema().await;
    let mine = Runtime::with_hub_id(Box::new(a), "hub-mine");
    mine.ensure_system_tables().await.unwrap();
    let theirs = Runtime::with_hub_id(Box::new(b), "hub-theirs");
    theirs.ensure_system_tables().await.unwrap();
    enqueue(&theirs, "shared-id").await;
    kill(&theirs, "shared-id").await;

    assert_eq!(
        mine.retry_print_job("shared-id", WHO, NO_MODULE)
            .await
            .unwrap(),
        RequeueOutcome::NotFound,
        "another tenant's job is simply not a job here"
    );
    assert_eq!(
        mine.discard_print_job("shared-id", WHO, NO_MODULE, "")
            .await
            .unwrap(),
        DiscardOutcome::NotFound
    );
    assert_eq!(
        status_of(&theirs, "shared-id").await,
        STATUS_DEAD,
        "and the neighbour's row did not move"
    );
}

/// The reason is free text from a request body that lands in a row: it is trimmed and capped, the
/// same rule and the same implementation the outbox's discard already applies.
#[tokio::test]
async fn the_discard_reason_is_capped_like_the_outboxs() {
    let rt = runtime("hub-reason").await;
    enqueue(&rt, "j1").await;

    let huge = "é".repeat(2_000);
    let outcome = rt
        .discard_print_job("j1", WHO, NO_MODULE, &huge)
        .await
        .unwrap();

    let DiscardOutcome::Discarded(stamp) = outcome else {
        panic!("it discards: {outcome:?}");
    };
    assert_eq!(
        stamp.discard_reason.chars().count(),
        erplora_runtime::outbox::MAX_DISCARD_REASON,
        "cut on a CHARACTER boundary — half an `é` is a panic in Rust and mojibake everywhere else"
    );
}

// ── hub#1532 — the row says WHICH MODULE acted, not only which person ─────────────────────────
//
// Both gestures sit behind an admin session AND, when the caller names a module, the `printer`
// capability the owner granted it. The door resolved that name to check the grant and then dropped
// it, so a hub with two modules holding `printer` could only ever answer «Ana retired it» — about a
// ticket Ana never touched. The name is written down now, next to the person and never instead of
// them.

/// The discard stamp carries the module, in the returned stamp AND in the row — the two cannot
/// drift, because the stamp is read back from what was written.
#[tokio::test]
async fn hub1532_discard_records_the_module_that_asked_for_it() {
    let rt = runtime("hub-discard-module").await;
    enqueue(&rt, "ghost").await;

    let outcome = rt
        .discard_print_job("ghost", WHO, THROUGH, "")
        .await
        .unwrap();

    let DiscardOutcome::Discarded(stamp) = outcome else {
        panic!("a waiting job can be retired: {outcome:?}");
    };
    assert_eq!(stamp.discarded_by, WHO, "the person is still stamped");
    assert_eq!(
        stamp.discarded_by_module, THROUGH,
        "and now the question «which module binned it?» has an answer"
    );
    let row = row(rt.db_for_test(), "hub-discard-module", "ghost").await;
    assert_eq!(
        row["discarded_by_module"], THROUGH,
        "the stamp has to BE the row, not a value the caller was told: {row}"
    );
    assert_eq!(row["discarded_by"], WHO);
}

/// The retry stamp is the other half (`retry_job` had no stamp at all), and it is a real row write:
/// a job re-fired by a module is exactly the one somebody asks about when a ticket comes out twice.
#[tokio::test]
async fn hub1532_retry_records_who_re_fired_the_job_and_through_what() {
    let rt = runtime("hub-retry-module").await;
    enqueue(&rt, "j1").await;
    kill(&rt, "j1").await;

    let outcome = rt.retry_print_job("j1", WHO, THROUGH).await.unwrap();

    let RequeueOutcome::Requeued(stamp) = outcome else {
        panic!("a dead job goes back to the queue: {outcome:?}");
    };
    assert_eq!(stamp.job_id, "j1");
    assert_eq!(stamp.retried_by, WHO);
    assert_eq!(stamp.retried_by_module, THROUGH);
    assert!(!stamp.retried_at.is_empty());

    let row = row(rt.db_for_test(), "hub-retry-module", "j1").await;
    assert_eq!(row["retried_by"], WHO);
    assert_eq!(row["retried_by_module"], THROUGH);
    assert_eq!(row["status"], STATUS_PENDING, "and it really went back");
    assert_eq!(
        row["attempts"], 0,
        "the stamp is written by the SAME update that resets the budget, not a second one that \
         could land without it"
    );
}

/// A gesture nobody's module asked for stores `""` — one spelling of "no module", never a `NULL`
/// that a reader has to guess at and never the word of a module that did not act.
#[tokio::test]
async fn hub1532_a_gesture_with_no_module_stores_the_empty_string() {
    let rt = runtime("hub-no-module").await;
    // `kill` claims whatever is at the FRONT of the queue, so the job it is meant to kill has to be
    // the only pending one while it runs; the second is enqueued after.
    enqueue(&rt, "refired").await;
    kill(&rt, "refired").await;
    enqueue(&rt, "by-hand").await;

    rt.discard_print_job("by-hand", WHO, NO_MODULE, "")
        .await
        .unwrap();
    rt.retry_print_job("refired", WHO, NO_MODULE).await.unwrap();

    let discarded = row(rt.db_for_test(), "hub-no-module", "by-hand").await;
    assert_eq!(discarded["discarded_by_module"], json!(""));
    let refired = row(rt.db_for_test(), "hub-no-module", "refired").await;
    assert_eq!(refired["retried_by_module"], json!(""));
}

/// **A refused gesture stamps nothing.** The write that carries the stamp is the same one guarded by
/// `status = :dead` / `status = :status`, so a job in the wrong state cannot come back with a
/// module's name on it — which would be a row claiming a module did something it was refused.
#[tokio::test]
async fn hub1532_a_refused_gesture_leaves_no_stamp_behind() {
    let rt = runtime("hub-refused-stamp").await;
    enqueue(&rt, "waiting").await;

    // `pending` is not `dead`: the retry is refused NAMING the state.
    let outcome = rt.retry_print_job("waiting", WHO, THROUGH).await.unwrap();
    assert_eq!(
        outcome,
        RequeueOutcome::NotRequeueable {
            status: STATUS_PENDING.to_string()
        }
    );

    let row = row(rt.db_for_test(), "hub-refused-stamp", "waiting").await;
    assert_eq!(
        row["retried_by_module"],
        json!(""),
        "a refusal must not leave the module's name on a job it never moved: {row}"
    );
    assert!(
        row["retried_by"].is_null() || row["retried_by"] == json!(""),
        "nor the person's: {row}"
    );
}
