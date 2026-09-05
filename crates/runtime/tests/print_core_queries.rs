//! hub#1107 — the print queue becomes READABLE by a module, through the reserved `hub.` namespace.
//!
//! The runtime has known what the queue is doing since hub#800 (`print_hosts::coverage`) and
//! hub#341 (`print_queue::list`), and it served both over HTTP. A **module** could reach neither:
//! the contract is WC → SDK → dispatcher (ADR-0192) and the SDK has no way to call a core route,
//! on purpose. So the one screen that shows a stuck ticket belonged to the shell, in a settings tab
//! nobody opens mid-service, while `printing`'s own Printers screen could not draw the queue at all.
//!
//! Two core queries close it, dispatched before the registry like every other `hub.*` name:
//!
//!  - `hub.print.coverage` — per station: how much is waiting, how many hosts are live, how long
//!    the oldest job has waited, and whether the runtime calls that **stuck**.
//!  - `hub.print.jobs` — the queue itself as a **status view**: what is waiting, what is printing,
//!    what died and why. Never the document.
//!
//! The gate is the namespace's own (`hub.users.view`, any local session and no API key) and NOT
//! admin, which is the audience hub#987 already decided for the same facts over HTTP: a queue
//! nobody is draining needs whoever is standing at the counter, not whoever can administer the hub.
use erplora_db::{
    testutil::{fresh_db, two_adapters_sharing_a_schema},
    Params,
};
use erplora_runtime::print_queue::NewPrintJob;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

/// The `hub.` namespace gate: every principal with a LOCAL session carries it, an API key never does.
const SESSION: &str = "hub.users.view";

async fn runtime(hub_id: &str) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

fn ctx(hub_id: &str, permissions: &[&str]) -> RequestContext {
    RequestContext::new(hub_id, "u1", permissions.iter().map(|p| p.to_string()))
}

/// Queues one job for `role`, the way the till does.
async fn enqueue(rt: &Runtime, job_id: &str, role: &str, document_type: &str) {
    let job: NewPrintJob = serde_json::from_value(json!({
        "jobId": job_id,
        "role": role,
        "documentType": document_type,
        "document": { "lines": [] },
    }))
    .unwrap();
    rt.enqueue_print_job(&job).await.expect("the job queues");
}

async fn query(rt: &Runtime, name: &str, params: Params, ctx: &RequestContext) -> Vec<Json> {
    rt.execute_query(name, &params, ctx)
        .await
        .unwrap_or_else(|e| panic!("`{name}` must answer: {e}"))
}

/// The read a module needs to say "nobody is printing the kitchen's tickets": the same facts the
/// HTTP coverage report carries, `undrained` included — RESOLVED by the runtime, so no screen
/// re-derives the threshold.
#[tokio::test]
async fn a_module_reads_the_coverage_of_every_station() {
    let rt = runtime("hub-cov").await;
    enqueue(&rt, "j1", "kitchen", "kitchen_order").await;

    let rows = query(
        &rt,
        "hub.print.coverage",
        Params::new(),
        &ctx("hub-cov", &[SESSION]),
    )
    .await;

    let kitchen = rows
        .iter()
        .find(|r| r["role"] == "kitchen")
        .unwrap_or_else(|| panic!("the kitchen must be reported: {rows:?}"));
    assert_eq!(kitchen["waiting"], 1);
    assert_eq!(kitchen["liveHosts"], 0, "nobody registered to drain it");
    assert!(
        kitchen["waitingSeconds"].is_i64(),
        "how LONG it has waited is half the alarm (hub#987): {kitchen:?}"
    );
    assert!(
        kitchen["undrained"].is_boolean(),
        "the runtime resolves `stuck`, the screen never re-derives it: {kitchen:?}"
    );
}

/// hub#1527 — the coverage a module reads NAMES the devices that are printing.
///
/// The count is the alarm; the names are the healthy state, which is the one the owner opens every
/// day. This is the door the Printers screen reads through, so if the names do not cross HERE the
/// screen can only ever say "2 devices active" and the owner has to go and try which till it is.
#[tokio::test]
async fn a_module_reads_which_devices_are_printing_and_not_only_how_many() {
    let rt = runtime("hub-cov-names").await;
    rt.register_print_host("till-1", "kitchen", "Counter till", "u1")
        .await
        .expect("the till registers as the kitchen's host");
    rt.register_print_host("tablet-1", "kitchen", "Floor tablet", "u1")
        .await
        .expect("and so does the tablet");

    let rows = query(
        &rt,
        "hub.print.coverage",
        Params::new(),
        &ctx("hub-cov-names", &[SESSION]),
    )
    .await;

    let kitchen = rows
        .iter()
        .find(|r| r["role"] == "kitchen")
        .unwrap_or_else(|| panic!("a covered station is reported too: {rows:?}"));
    assert_eq!(kitchen["liveHosts"], 2);
    assert_eq!(
        kitchen["liveHostLabels"],
        json!(["Counter till", "Floor tablet"]),
        "the module can name them: {kitchen:?}"
    );
}

/// The queue itself, in hand-out order, as a STATUS view.
#[tokio::test]
async fn a_module_reads_the_queue_in_hand_out_order() {
    let rt = runtime("hub-jobs").await;
    enqueue(&rt, "first", "receipt", "receipt").await;
    enqueue(&rt, "second", "receipt", "receipt").await;

    let rows = query(
        &rt,
        "hub.print.jobs",
        Params::new(),
        &ctx("hub-jobs", &[SESSION]),
    )
    .await;

    assert_eq!(rows.len(), 2, "both jobs are visible: {rows:?}");
    assert_eq!(rows[0]["jobId"], "first", "delivery order, oldest first");
    assert_eq!(rows[1]["jobId"], "second");
    assert_eq!(rows[0]["role"], "receipt");
    assert_eq!(rows[0]["documentType"], "receipt");
    assert_eq!(rows[0]["format"], "receipt");
    assert_eq!(rows[0]["status"], "pending");
    assert_eq!(rows[0]["attempts"], 0);
    assert_eq!(rows[0]["lastError"], "");
    assert!(
        rows[0]["createdAt"].as_str().is_some_and(|s| !s.is_empty()),
        "the age of a stuck ticket is the point: {rows:?}"
    );
}

/// **The document never travels through this door.** It is a state view; the ticket itself goes to
/// the print host that claims the job (hub#343), past both of the drain's guards — never to a
/// module polling the queue.
#[tokio::test]
async fn the_document_never_leaves_through_the_status_view() {
    let rt = runtime("hub-doc").await;
    let job: NewPrintJob = serde_json::from_value(json!({
        "jobId": "secret",
        "role": "receipt",
        "documentType": "receipt",
        "document": { "customer": "Ana Pérez", "total": "42,50" },
    }))
    .unwrap();
    rt.enqueue_print_job(&job).await.unwrap();

    let rows = query(
        &rt,
        "hub.print.jobs",
        Params::new(),
        &ctx("hub-doc", &[SESSION]),
    )
    .await;

    assert_eq!(rows.len(), 1);
    assert!(
        rows[0].get("document").is_none(),
        "the ticket's contents must not come back with the status: {rows:?}"
    );
    assert!(
        !serde_json::to_string(&rows[0])
            .unwrap()
            .contains("Ana Pérez"),
        "nothing of the document may leak into the view: {rows:?}"
    );
}

/// `role` and `status` filter, which is what turns the screen from a dump into "what is stuck".
#[tokio::test]
async fn the_queue_filters_by_station_and_by_status() {
    let rt = runtime("hub-filter").await;
    enqueue(&rt, "r1", "receipt", "receipt").await;
    enqueue(&rt, "k1", "kitchen", "kitchen_order").await;

    let mut by_role = Params::new();
    by_role.insert("role".into(), json!("kitchen"));
    let rows = query(
        &rt,
        "hub.print.jobs",
        by_role,
        &ctx("hub-filter", &[SESSION]),
    )
    .await;
    assert_eq!(rows.len(), 1, "only the kitchen's: {rows:?}");
    assert_eq!(rows[0]["jobId"], "k1");

    let mut by_status = Params::new();
    by_status.insert("status".into(), json!("dead"));
    let rows = query(
        &rt,
        "hub.print.jobs",
        by_status,
        &ctx("hub-filter", &[SESSION]),
    )
    .await;
    assert!(rows.is_empty(), "nothing died yet: {rows:?}");
}

/// Tenancy (ADR-0201): the queue a module reads is **this hub's**, and there is no parameter that
/// could name another one — `hub_id` comes from the request context the deployment stamps.
#[tokio::test]
async fn the_queue_of_another_hub_is_not_visible() {
    let (a, b) = two_adapters_sharing_a_schema().await;
    let mine = Runtime::with_hub_id(Box::new(a), "hub-mine");
    mine.ensure_system_tables().await.unwrap();
    let theirs = Runtime::with_hub_id(Box::new(b), "hub-theirs");
    theirs.ensure_system_tables().await.unwrap();
    enqueue(&theirs, "not-yours", "receipt", "receipt").await;

    let rows = query(
        &mine,
        "hub.print.jobs",
        Params::new(),
        &ctx("hub-mine", &[SESSION]),
    )
    .await;
    assert!(
        rows.is_empty(),
        "another hub's tickets are not mine: {rows:?}"
    );

    // …and a payload that tries to name the other tenant changes nothing: `hub_id` is not a filter.
    let mut spoof = Params::new();
    spoof.insert("hub_id".into(), json!("hub-theirs"));
    let rows = query(&mine, "hub.print.jobs", spoof, &ctx("hub-mine", &[SESSION])).await;
    assert!(
        rows.is_empty(),
        "the payload cannot pick the tenant: {rows:?}"
    );
}

/// The audience decision of hub#987, applied to the door: **the cashier reads it**. Restricting the
/// queue to admins would hide the alarm from the only person standing next to the printer.
#[tokio::test]
async fn the_cashier_reads_the_queue_without_administering_the_hub() {
    let rt = runtime("hub-cashier").await;
    enqueue(&rt, "j1", "receipt", "receipt").await;

    let rows = query(
        &rt,
        "hub.print.jobs",
        Params::new(),
        &ctx("hub-cashier", &[SESSION]),
    )
    .await;
    assert_eq!(rows.len(), 1);
    let rows = query(
        &rt,
        "hub.print.coverage",
        Params::new(),
        &ctx("hub-cashier", &[SESSION]),
    )
    .await;
    assert!(!rows.is_empty());
}

/// …and a principal with no local session (an API key) still does not get into the namespace.
#[tokio::test]
async fn a_principal_without_a_local_session_is_refused() {
    let rt = runtime("hub-key").await;

    for name in ["hub.print.coverage", "hub.print.jobs"] {
        let err = rt
            .execute_query(name, &Params::new(), &ctx("hub-key", &[]))
            .await
            .expect_err("no local session, no core namespace");
        assert!(
            err.to_string().contains(SESSION),
            "the refusal must name the permission it wanted: {err}"
        );
    }
}

/// A neighbouring name in the namespace is a BROKEN CONTRACT, not an absent module: it blows up
/// instead of coming back empty, because `queryOptional` forgives an absent module and would
/// swallow a typo forever.
#[tokio::test]
async fn a_neighbouring_name_in_the_namespace_is_still_not_found() {
    let rt = runtime("hub-typo").await;

    let err = rt
        .execute_query(
            "hub.print.queue",
            &Params::new(),
            &ctx("hub-typo", &[SESSION]),
        )
        .await
        .expect_err("`hub.print.queue` does not exist");
    assert!(
        err.to_string().contains("hub.print.queue"),
        "the error must name the query that does not exist: {err}"
    );
}

// ── Reading back the stamp a person left on a job (hub#1565) ──────────────────────────────────
//
// hub#1108 and hub#1532 made the hub WRITE who retired a ticket, when, why and through which
// module. Nothing read it back: the stamp reached the person who had just made the gesture (it
// comes back in the response of the discard/retry itself) and nobody else. The question a stuck
// queue actually raises the NEXT day — «who binned my ticket?», «why did this order print twice?»
// — had no answer outside `psql`.
//
// **The audience is the admin's, and that is a market decision, not a shortcut** (the research is
// in the issue): every mature POS keeps «voided by X, because Y» in the back office —
// Square's comp&void report needs the `reports` permission, Toast's Voided Orders lives in Toast
// Web, Lightspeed's Cancellations report in the Back Office, Odoo's cancelled-orders report in the
// PoS Manager group. The reason is the same everywhere and it is not privacy for its own sake: the
// report exists to spot till fraud, so it cannot be readable by the population it is watching.
//
// It does NOT move the gate hub#987 decided: the queue itself stays open to the counter, because
// the alarm belongs to whoever is standing next to the printer. What is admin-only is the stamp,
// so the two facts travel through one door with two audiences instead of two doors that drift.

/// Administering the hub — the permission that decides the audience of the stamp, on both doors.
const ADMIN: &str = "hub.administer";

/// Drives a queued job to `dead` the way the machine really does, so a retry has a legal subject.
async fn seed_dead(rt: &Runtime, hub_id: &str, job_id: &str, role: &str) {
    use erplora_runtime::print_queue::{self, MAX_ATTEMPTS};
    let station = erplora_runtime::print_stations::resolve(rt.db_for_test(), hub_id, role)
        .await
        .unwrap();
    for _ in 0..MAX_ATTEMPTS {
        print_queue::claim_next(rt.db_for_test(), hub_id, &station.id, "till-1", 90)
            .await
            .unwrap()
            .expect("there is a job to hand out");
        print_queue::mark_failed(rt.db_for_test(), hub_id, job_id, "printer offline")
            .await
            .unwrap();
    }
}

/// The whole point of hub#1565: the stamp survives the gesture and can be read back later.
#[tokio::test]
async fn an_admin_reads_who_retired_a_ticket_and_why() {
    let rt = runtime("hub-stamp").await;
    enqueue(&rt, "binned", "receipt", "receipt").await;
    rt.discard_print_job("binned", "hub_user:u9", "printing", "duplicado del ticket 42")
        .await
        .expect("the job is retired");

    let rows = query(
        &rt,
        "hub.print.jobs",
        Params::new(),
        &ctx("hub-stamp", &[SESSION, ADMIN]),
    )
    .await;

    assert_eq!(rows.len(), 1, "a retired job is still listed: {rows:?}");
    assert_eq!(rows[0]["status"], "discarded");
    assert_eq!(
        rows[0]["discardedBy"], "hub_user:u9",
        "«who binned my ticket?» has an answer: {rows:?}"
    );
    assert_eq!(
        rows[0]["discardedByModule"], "printing",
        "and «WHAT binned it» too (hub#1532): {rows:?}"
    );
    assert_eq!(
        rows[0]["discardReason"], "duplicado del ticket 42",
        "the half only the person knew: {rows:?}"
    );
    assert!(
        rows[0]["discardedAt"].as_str().is_some_and(|s| !s.is_empty()),
        "when it happened is what makes it an answer and not an anecdote: {rows:?}"
    );
}

/// The other half of the stamp: a job that came out of the printer a SECOND time.
#[tokio::test]
async fn an_admin_reads_who_re_fired_a_ticket() {
    let rt = runtime("hub-refire").await;
    enqueue(&rt, "twice", "kitchen", "kitchen_order").await;
    seed_dead(&rt, "hub-refire", "twice", "kitchen").await;
    rt.retry_print_job("twice", "hub_user:u9", "printing")
        .await
        .expect("a dead job is re-fired");

    let rows = query(
        &rt,
        "hub.print.jobs",
        Params::new(),
        &ctx("hub-refire", &[SESSION, ADMIN]),
    )
    .await;

    assert_eq!(rows.len(), 1);
    assert_eq!(
        rows[0]["status"], "pending",
        "a re-fired job is back in the queue, and the stamp travels with it: {rows:?}"
    );
    assert_eq!(rows[0]["retriedBy"], "hub_user:u9");
    assert_eq!(rows[0]["retriedByModule"], "printing");
    assert!(
        rows[0]["retriedAt"].as_str().is_some_and(|s| !s.is_empty()),
        "«why did this order print twice?» is a question about a moment: {rows:?}"
    );
}

/// The market's rule, enforced: the counter reads the QUEUE (hub#987) and not the stamp.
///
/// The keys are ABSENT, never present-and-empty. `""` already means something in this stamp — «no
/// module named itself» — so answering `""` to a cashier would be the hub saying «nobody binned
/// it», which is a lie, instead of «you are not being told».
#[tokio::test]
async fn the_counter_reads_the_queue_but_not_who_retired_a_ticket() {
    let rt = runtime("hub-counter-stamp").await;
    enqueue(&rt, "binned", "receipt", "receipt").await;
    rt.discard_print_job("binned", "hub_user:u9", "printing", "duplicado")
        .await
        .unwrap();

    let rows = query(
        &rt,
        "hub.print.jobs",
        Params::new(),
        &ctx("hub-counter-stamp", &[SESSION]),
    )
    .await;

    assert_eq!(rows.len(), 1, "the cashier still sees the queue: {rows:?}");
    assert_eq!(rows[0]["status"], "discarded", "…and its state: {rows:?}");
    for key in [
        "discardedBy",
        "discardedByModule",
        "discardReason",
        "discardedAt",
        "retriedBy",
        "retriedByModule",
        "retriedAt",
    ] {
        assert!(
            rows[0].get(key).is_none(),
            "`{key}` is back-office data and must be ABSENT for the counter: {rows:?}"
        );
    }
    assert!(
        !serde_json::to_string(&rows[0]).unwrap().contains("u9"),
        "and nothing of the stamp may leak by another name: {rows:?}"
    );
}

/// A job nobody touched carries no stamp — not even for an admin. An empty `discardedBy` on a
/// `pending` job would make every screen render "retired by ―" on a ticket that is simply waiting.
#[tokio::test]
async fn a_job_nobody_touched_carries_no_stamp() {
    let rt = runtime("hub-untouched").await;
    enqueue(&rt, "waiting", "receipt", "receipt").await;

    let rows = query(
        &rt,
        "hub.print.jobs",
        Params::new(),
        &ctx("hub-untouched", &[SESSION, ADMIN]),
    )
    .await;

    assert_eq!(rows[0]["status"], "pending");
    for key in ["discardedBy", "discardedAt", "retriedBy", "retriedAt"] {
        assert!(
            rows[0].get(key).is_none(),
            "nothing happened to this job, so `{key}` has nothing to say: {rows:?}"
        );
    }
}

/// A CLOSED bucket is read from the other end, and without this the stamp is unreachable in
/// practice (hub#1565).
///
/// `LIMIT` over `ORDER BY seq` hands back the OLDEST rows. For `pending`/`printing`/`dead` that is
/// the right end — the ticket that has waited longest is the one on fire. For `discarded` it is the
/// wrong one by exactly the same reasoning: those rows never leave, so a hub with a year of
/// retired tickets would page forever through its first hundred and never show the one somebody is
/// asking about, which is always today's.
#[tokio::test]
async fn the_retired_bucket_is_read_newest_first() {
    let rt = runtime("hub-order").await;
    for job_id in ["old", "middle", "recent"] {
        enqueue(&rt, job_id, "receipt", "receipt").await;
        rt.discard_print_job(job_id, "hub_user:u9", "", "")
            .await
            .expect("the job is retired");
    }

    let mut discarded = Params::new();
    discarded.insert("status".into(), json!("discarded"));
    discarded.insert("limit".into(), json!(2));
    let rows = query(
        &rt,
        "hub.print.jobs",
        discarded,
        &ctx("hub-order", &[SESSION, ADMIN]),
    )
    .await;

    assert_eq!(rows.len(), 2, "the page is capped as asked: {rows:?}");
    assert_eq!(
        rows.iter().map(|r| r["jobId"].clone()).collect::<Vec<_>>(),
        vec![json!("recent"), json!("middle")],
        "the LAST tickets retired are the ones somebody is asking about: {rows:?}"
    );

    // …and the live bucket keeps reading from the end it always did: oldest first is the alarm.
    enqueue(&rt, "waiting-first", "receipt", "receipt").await;
    enqueue(&rt, "waiting-second", "receipt", "receipt").await;
    let mut pending = Params::new();
    pending.insert("status".into(), json!("pending"));
    let rows = query(
        &rt,
        "hub.print.jobs",
        pending,
        &ctx("hub-order", &[SESSION, ADMIN]),
    )
    .await;
    assert_eq!(
        rows.iter().map(|r| r["jobId"].clone()).collect::<Vec<_>>(),
        vec![json!("waiting-first"), json!("waiting-second")],
        "a queue is still served in hand-out order: {rows:?}"
    );
}
