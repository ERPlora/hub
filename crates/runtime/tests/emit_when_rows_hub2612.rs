//! **hub#2612** — a scheduled sweep announced every pass, even the ones that changed nothing.
//!
//! The periodic tasks of the catalogue (`tables.tables.expire_holds`,
//! `reservations.reservations.release_unconfirmed`, `services.packages.expire_holds`, the
//! attendance review) are set-based UPDATEs that most passes find NOTHING to do. Their `emit`
//! wrote one `_event_outbox` row per EXECUTION, so an automation hooked to that event fired every
//! 5–15 minutes for nothing (with the «cash closed → create a task» recipe: a new task every five
//! minutes).
//!
//! The two row gates the manifest already had (`min_affected_rows`, `expect_rows`) are not a way
//! out: they ROLL BACK and answer an error. In a scheduled task that means `next_run` never
//! advances, the 300 s lease parks the task and it retries every five minutes forever, and the
//! `?` of the sweep cuts the rest of the due tasks of that tick (HUB-F62).
//!
//! `emit[].when_rows` names one of the command's own statements: the event is written only when
//! THAT statement affected at least one row, inside the same transaction. Zero rows is the normal
//! "nothing to do" — the command answers `ok`, its other effects (and the scheduler's `next_run`)
//! commit, and no event is queued nor pushed live. The plain string form keeps its historical
//! once-per-execution behaviour (opt-in, no change for published modules).
//!
//! Real Postgres, ephemeral schema per test.
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{EventSink, EventSource, RequestContext, Runtime};
use serde_json::{json, Value as Json};

const HUB: &str = "h1";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_2612")
        .join(name)
}

#[derive(Default, Debug)]
struct Sink {
    events: Mutex<Vec<String>>,
}

impl EventSink for Sink {
    fn emit(&self, _source: EventSource<'_>, name: &str, _payload: &Json) {
        self.events.lock().unwrap().push(name.to_string());
    }
}

impl Sink {
    fn count(&self, event: &str) -> usize {
        self.events
            .lock()
            .unwrap()
            .iter()
            .filter(|e| e.as_str() == event)
            .count()
    }
}

async fn hub() -> (Runtime, Arc<Sink>) {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("sweep"))
        .await
        .expect("install w2612");
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    (rt, sink)
}

fn ctx() -> RequestContext {
    RequestContext::new(HUB, "u1", ["*".to_string()])
}

async fn create_hold(rt: &Runtime) {
    rt.execute_command("w2612.holds.create", &Params::new(), &ctx())
        .await
        .expect("create a hold");
}

async fn outbox_count(rt: &Runtime, event_name: &str) -> i64 {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("event_name".into(), json!(event_name));
    let rows = rt
        .db()
        .query(
            "SELECT COUNT(*) AS n FROM _event_outbox WHERE hub_id = :hub_id AND event_name = :event_name",
            &p,
        )
        .await
        .expect("count the outbox")
        .rows;
    rows[0]["n"]
        .as_i64()
        .unwrap_or_else(|| panic!("COUNT returned something odd: {rows:?}"))
}

/// Puts the fixture's task back in the past so the next sweep runs it (the cron is every minute,
/// the test cannot wait for the clock).
async fn make_task_due(rt: &Runtime) {
    rt.db()
        .execute(
            "UPDATE _scheduled_tasks SET next_run = '2000-01-01T00:00:00+00:00' \
             WHERE module_id = 'w2612' AND name = 'expire_holds'",
            &Params::new(),
        )
        .await
        .expect("make the task due");
}

async fn task_row(rt: &Runtime) -> Json {
    rt.db()
        .query(
            "SELECT next_run, last_run, claim_expires_at FROM _scheduled_tasks \
             WHERE module_id = 'w2612' AND name = 'expire_holds'",
            &Params::new(),
        )
        .await
        .expect("read the task")
        .rows
        .into_iter()
        .next()
        .expect("the task is registered")
}

/// The reported scenario, end to end through the real scheduler: a pass that releases a hold
/// announces it once; the next pass finds nothing and announces NOTHING — and it still counts as
/// a successful pass (the task advances, no lease left behind). A later pass with work announces
/// again: the field filters empty passes, it is not "at most once".
#[tokio::test]
async fn a_scheduled_pass_that_changes_nothing_announces_nothing_hub2612() {
    let (rt, sink) = hub().await;

    create_hold(&rt).await;
    make_task_due(&rt).await;
    assert_eq!(rt.process_scheduler(HUB).await.expect("first pass"), 1);
    assert_eq!(
        outbox_count(&rt, "w2612.hold.released").await,
        1,
        "the pass that released a hold announces it"
    );
    assert_eq!(sink.count("w2612.hold.released"), 1);

    make_task_due(&rt).await;
    assert_eq!(
        rt.process_scheduler(HUB)
            .await
            .expect("an empty pass is not an error"),
        1,
        "the empty pass still RAN"
    );
    assert_eq!(
        outbox_count(&rt, "w2612.hold.released").await,
        1,
        "hub#2612: a pass that changed nothing must not queue the event"
    );
    assert_eq!(
        sink.count("w2612.hold.released"),
        1,
        "nor push it to the live screens"
    );
    let task = task_row(&rt).await;
    assert!(
        task["claim_expires_at"].is_null(),
        "the empty pass resolved the task (no lease left to park it): {task}"
    );
    assert!(
        task["next_run"].as_str().unwrap_or_default() > "2001",
        "the empty pass advanced next_run: {task}"
    );

    create_hold(&rt).await;
    make_task_due(&rt).await;
    rt.process_scheduler(HUB).await.expect("third pass");
    assert_eq!(
        outbox_count(&rt, "w2612.hold.released").await,
        2,
        "a later pass with work announces again"
    );
}

/// The anchor is what counts, not the batch: an unconditional sibling (a «last swept» upsert that
/// always affects one row) must not make an empty pass announce. And the empty pass answers `ok`
/// with its other effects committed — `when_rows` filters the event, it never turns «nothing to
/// do» into an error.
#[tokio::test]
async fn only_the_anchored_statement_decides_and_the_rest_commits_hub2612() {
    let (rt, sink) = hub().await;

    let empty = rt
        .execute_command("w2612.holds.expire_and_stamp", &Params::new(), &ctx())
        .await
        .expect("nothing to expire is not an error");
    assert_eq!(empty["ok"], json!(true));
    assert_eq!(
        outbox_count(&rt, "w2612.hold.stamped_release").await,
        0,
        "the sibling's row must not open the anchored gate"
    );
    assert_eq!(sink.count("w2612.hold.stamped_release"), 0);
    let stamped = rt
        .db()
        .query(
            "SELECT COUNT(*) AS n FROM w2612_sweeps WHERE hub_id = 'h1'",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows;
    assert_eq!(
        stamped[0]["n"],
        json!(1),
        "the rest of the command committed: nothing rolled back"
    );

    create_hold(&rt).await;
    rt.execute_command("w2612.holds.expire_and_stamp", &Params::new(), &ctx())
        .await
        .expect("expire one hold");
    assert_eq!(outbox_count(&rt, "w2612.hold.stamped_release").await, 1);
    assert_eq!(sink.count("w2612.hold.stamped_release"), 1);
}

/// Opt-in: the plain string form keeps announcing once per EXECUTION, as every published module
/// relies on today.
#[tokio::test]
async fn the_plain_string_form_still_announces_every_execution_hub2612() {
    let (rt, _sink) = hub().await;
    for _ in 0..2 {
        rt.execute_command("w2612.holds.expire_legacy", &Params::new(), &ctx())
            .await
            .expect("legacy sweep");
    }
    assert_eq!(
        outbox_count(&rt, "w2612.hold.legacy_released").await,
        2,
        "without `when_rows` nothing changes for a module that has not adopted it"
    );
}

/// An anchor that names no statement of the command would read as «announces only on change»
/// while doing something else: refused at install, naming the anchor and the command.
#[tokio::test]
async fn install_refuses_a_when_rows_anchor_that_names_no_statement_hub2612() {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let err = rt
        .install_from_dir(&fixture("dangling_anchor"))
        .await
        .expect_err("a dangling `when_rows` must not install");
    let msg = err.to_string();
    assert!(
        msg.contains("when_rows")
            && msg.contains("no_such_statement.sql")
            && msg.contains("w2612d.holds.expire"),
        "the refusal names the field, the anchor and the command: {msg}"
    );
}

/// A command resolved by a handler does not run its `sql` list as written, so there is no
/// statement count to anchor to: refused at install instead of silently announcing every time.
#[tokio::test]
async fn install_refuses_when_rows_on_a_handler_command_hub2612() {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let err = rt
        .install_from_dir(&fixture("handler_anchor"))
        .await
        .expect_err("`when_rows` on a handler command must not install");
    let msg = err.to_string();
    assert!(
        msg.contains("when_rows") && msg.contains("w2612h.holds.expire") && msg.contains("handler"),
        "the refusal names the field, the command and why: {msg}"
    );
}

// ── The authoring contract (`schemas/module.schema.json`) ────────────────────────────────────
//
// A field only the runtime understands is a field authors cannot write: `erplora validate` vendors
// this schema byte for byte, so it has to accept exactly what the runtime reads and refuse the
// same garbage (same pattern as `emit_schema_contract_hub1076.rs`).

fn schema() -> jsonschema::Validator {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../schemas/module.schema.json")
        .canonicalize()
        .expect("schemas/module.schema.json ships with the hub");
    let raw: Json = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    jsonschema::validator_for(&raw).expect("the manifest schema compiles")
}

fn manifest_with_emit(emit: Json) -> Json {
    json!({
        "id": "demo", "name": "Demo", "version": "1.0.0",
        "commands": {
            "demo.holds.expire": {
                "permission": "demo.manage",
                "sql": ["commands/holds_expire.sql"],
                "emit": emit
            }
        }
    })
}

#[test]
fn the_schema_accepts_when_rows_hub2612() {
    let schema = schema();
    for emit in [
        json!([{ "event": "demo.hold.released", "when_rows": "commands/holds_expire.sql" }]),
        json!([{
            "event": "demo.hold.released",
            "when_rows": "commands/holds_expire.sql",
            "dedup_key": "hold_id"
        }]),
        json!(["demo.hold.legacy", { "event": "demo.hold.released", "when_rows": "commands/holds_expire.sql" }]),
    ] {
        assert!(
            schema.is_valid(&manifest_with_emit(emit.clone())),
            "the runtime reads this `emit`, so the schema must accept it: {emit}"
        );
    }
}

#[test]
fn the_schema_refuses_what_the_runtime_would_not_read_hub2612() {
    let schema = schema();
    for (emit, why) in [
        (
            json!([{ "event": "demo.hold.released", "when_rows": true }]),
            "`when_rows` names a statement (its `sql` path), not a flag",
        ),
        (
            json!([{ "event": "demo.hold.released", "when_rows": "" }]),
            "an empty anchor names nothing",
        ),
        (
            json!([{ "event": "demo.hold.released" }]),
            "an object with neither `dedup_key` nor `when_rows` is still a misspelt string",
        ),
        (
            json!([{ "when_rows": "commands/holds_expire.sql" }]),
            "an object without `event` names no event",
        ),
    ] {
        assert!(
            !schema.is_valid(&manifest_with_emit(emit.clone())),
            "{why}: {emit}"
        );
    }
}

// ── What else rides on «the event was written» ─────────────────────────────────────────────────

async fn first_record_at(rt: &Runtime) -> String {
    rt.fiscal_profile()
        .await
        .expect("read the fiscal profile")
        .expect("the hub has a fiscal profile")
        .first_record_at
}

/// The dispatcher seals the fiscal go-live when a committed command EMITS one of the events that
/// start a fiscal chain (ADR-0273 D3). An entry that `when_rows` skipped was never written, so it
/// must not close the way back to testing for a record that does not exist.
#[tokio::test]
async fn an_event_that_was_not_written_does_not_seal_the_fiscal_go_live_hub2612() {
    let (mut rt, _sink) = hub().await;
    // A provider of the hub's regime: what makes the hub owe VeriFactu at all (the runtime is
    // business-free; a stand-in with the SHAPE of `verifactu` is all the fiscal gates read).
    rt.install_from_dir(&fixture("fiscal_provider"))
        .await
        .expect("install the fiscal provider stand-in");
    rt.refresh_fiscal_profile().await.expect("profile row");
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    rt.db()
        .execute(
            "UPDATE _hub_fiscal_profile SET status = 'ACTIVE', environment = 'production', \
               fiscal_trigger_events = '[\"w2612.hold.stamped_release\"]' WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .expect("a hub filing for real");
    rt.db()
        .execute(
            "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES (:hub_id, 'own', 'v1:ciphertext', 'v1:ciphertext', '2026-10-08T09:00:00Z', 'x')",
            &p,
        )
        .await
        .expect("with a road to the AEAT");
    rt.refresh_fiscal_profile().await.expect("refresh");

    rt.execute_command("w2612.holds.expire_and_stamp", &Params::new(), &ctx())
        .await
        .expect("an empty pass on a live hub");
    assert_eq!(
        first_record_at(&rt).await,
        "",
        "nothing was written, nothing is sealed"
    );

    create_hold(&rt).await;
    rt.execute_command("w2612.holds.expire_and_stamp", &Params::new(), &ctx())
        .await
        .expect("a pass that writes the event");
    assert!(
        !first_record_at(&rt).await.is_empty(),
        "positive control: the written event does seal"
    );
}
