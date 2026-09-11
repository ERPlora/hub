//! **The refusal of an unreadable automation filter actually leaves the kernel** (ERPlora/hub#1714).
//!
//! hub#1714 made a stored filter this core cannot read narrow to NOTHING instead of to everything.
//! Refusing is only half of it: the owner's recipe simply stops firing, the editor still shows the
//! filter as they wrote it, and nothing in the product connects the two. The report is the only
//! thread joining «the automation went quiet» to «this row has to be saved again» — and the state
//! is reachable in one direction only, by the READER moving (hub#1713 started refusing a `now.…` on
//! the right of an operator, so a filter an older hub stored with one stopped parsing here).
//!
//! The unit tests next to the code pin the CONTENT of that report by calling its builder, which is
//! the `failed_install_event` pattern (hub#1477). What no unit test can reach is the WIRING, because
//! the refusal reports to the process-global [`ErrorRegistry`] and a `OnceLock` sink cannot be
//! swapped per test. Measured on this branch, that gap let three mutants live with the whole
//! `--lib flows` suite green:
//!
//!   * deleting the `report(event)` call from `read_stored_filter` outright;
//!   * naming the wrong column in the trigger's `FilterOwner` (`row["flow_id"]` as the `id`), so the
//!     report points at a row nobody can open;
//!   * naming the wrong column in the wait's (`run_id` as the `id`), same consequence.
//!
//! Both call sites are exercised in ONE test on purpose: `ErrorRegistry::install` is a `OnceLock`,
//! so a second `#[tokio::test]` in this binary would race the sink of the first.
use std::sync::{Arc, Mutex};

use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params};
use erplora_runtime::flows::{def, triggers, waits};
use erplora_runtime::{ErrorEvent, ErrorRegistry, ErrorSink};
use serde_json::json;

const HUB: &str = "hub-filter-report";
const FLOW: &str = "flow-1";
/// The ids are the whole point of the report, so the test FIXES them instead of reading them back:
/// an assertion against whatever the row happens to hold would pass just as happily on a report
/// that names a different column.
const TRIGGER_ID: &str = "trigger-unreadable-1";
const WAIT_ID: &str = "wait-unreadable-1";
const RUN_ID: &str = "run-1";

/// The shape hub#1713 turned into an unreadable one: stored fine by an older hub, refused by
/// `Condition::parse` since that PR.
const STALE_FILTER: &str = r#"{"steps.t.at": {"gte": "now.iso"}}"#;

struct CaptureSink(Mutex<Vec<ErrorEvent>>);

impl ErrorSink for CaptureSink {
    fn submit(&self, event: ErrorEvent) {
        self.0.lock().unwrap().push(event);
    }
}

/// The v0 baseline the real boot lays down (`Runtime::ensure_system_tables`) plus the versioned
/// migrations on top — the same bootstrap `flow_grant_unreadable_pin_report.rs` uses, and for the
/// reason written there: the migrations at or below v30 ALTER those baseline tables, so applying
/// them over an empty schema fails on `hub_module` long before reaching the flow tables.
async fn apply_system_schema(db: &dyn DatabaseAdapter) {
    erplora_runtime::installer::ensure_hub_module_table(db)
        .await
        .expect("the v0 baseline the real boot lays down");
    erplora_runtime::identity::ensure_tables(db)
        .await
        .expect("the v0 baseline the real boot lays down");
    erplora_runtime::system_migrations::apply(db, HUB)
        .await
        .expect("the system schema is what holds the flow tables");
}

/// Writes the rows this guard exists for, by SQL and on purpose: the write door refuses anything
/// `Condition::parse` rejects, so a row only gets into this state the way the issue describes — a
/// hub that accepted the shape when it saved it, and this one that no longer does.
async fn seed_unreadable_filters(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("flow_id".into(), json!(FLOW));
    p.insert("trigger_id".into(), json!(TRIGGER_ID));
    p.insert("wait_id".into(), json!(WAIT_ID));
    p.insert("run_id".into(), json!(RUN_ID));
    p.insert("filter".into(), json!(STALE_FILTER));

    db.execute(
        "INSERT INTO _flow (id, hub_id, name, enabled, definition, created_at, updated_at) \
         VALUES (:flow_id, :hub_id, 'recordatorio por WhatsApp', 1, '{}', \
                 '2026-09-10T00:00:00Z', '2026-09-10T00:00:00Z')",
        &p,
    )
    .await
    .expect("the fixture writes the flow the trigger hangs from");

    db.execute(
        "INSERT INTO _flow_triggers \
           (id, hub_id, flow_id, trigger_key, kind, event_name, filter, created_at, updated_at) \
         VALUES (:trigger_id, :hub_id, :flow_id, 'k1', 'event', 'sale.completed', :filter, \
                 '2026-09-10T00:00:00Z', '2026-09-10T00:00:00Z')",
        &p,
    )
    .await
    .expect("the fixture writes the trigger this guard exists for");

    db.execute(
        "INSERT INTO _flow_run_waits \
           (id, hub_id, run_id, flow_id, step_id, step_index, kind, event_name, filter, \
            correlate, correlate_value, status, created_at, updated_at) \
         VALUES (:wait_id, :hub_id, :run_id, :flow_id, 'wait', 0, 'cancel', 'sale.completed', \
                 :filter, '{\"event.id\": \"42\"}', '42', 'armed', \
                 '2026-09-10T00:00:00Z', '2026-09-10T00:00:00Z')",
        &p,
    )
    .await
    .expect("the fixture writes the wait this guard exists for");
}

fn payload() -> Params {
    let mut p = Params::new();
    p.insert("id".into(), json!("42"));
    p.insert("total".into(), json!("120.50"));
    p
}

async fn run_count(db: &dyn DatabaseAdapter) -> i64 {
    let mut p = Params::new();
    p.insert("f".into(), json!(FLOW));
    db.query(
        "SELECT COUNT(*) AS c FROM _flow_runs WHERE flow_id = :f",
        &p,
    )
    .await
    .unwrap()
    .rows[0]["c"]
        .as_i64()
        .unwrap_or(-1)
}

/// hub#1714 — the refusal is REPORTED on BOTH paths, each naming the row somebody has to open, and
/// it says so through the registry the host really drains (`CloudErrorSink`), not only through a
/// line on stderr that dies inside the container.
#[tokio::test]
async fn an_unreadable_filter_is_reported_naming_the_row_to_save_again() {
    let db = fresh_db().await;
    apply_system_schema(&db).await;
    seed_unreadable_filters(&db).await;

    let sink = Arc::new(CaptureSink(Mutex::new(Vec::new())));
    ErrorRegistry::install(sink.clone());

    // The real relay reads, not hand-built events: what is being pinned is that THESE calls report.
    let started = triggers::on_event(&db, HUB, "evt-1", "sale.completed", &payload(), 0)
        .await
        .expect("an unreadable filter is a trigger that does not fire, never a failed relay");
    let fired = waits::on_event(&db, HUB, "evt-1", "sale.completed", &payload())
        .await
        .expect("an unreadable filter is a wait that does not move, never a failed relay");

    assert_eq!(started, 0, "the trigger's filter cannot be read: no run");
    assert_eq!(fired, 0, "the wait's filter cannot be read: no transition");
    assert_eq!(
        run_count(&db).await,
        0,
        "the premise of both reports is that nothing fired"
    );

    let events = sink.0.lock().unwrap();
    let reports: Vec<&ErrorEvent> = events
        .iter()
        .filter(|e| e.error_code == def::ERR_UNREADABLE_FILTER_EVENT)
        .collect();

    for (kind, id) in [("trigger", TRIGGER_ID), ("wait", WAIT_ID)] {
        let report = reports
            .iter()
            .find(|e| e.context["kind"] == json!(kind))
            .unwrap_or_else(|| {
                panic!(
                    "the {kind}'s filter was refused WITHOUT reporting it: the owner is left with \
                     an automation that went quiet and an editor that still shows the filter. \
                     Got {events:?}"
                )
            });
        assert_eq!(
            report.context["id"],
            json!(id),
            "the {kind}'s report has to name ITS OWN row; any other id sends whoever reads it to a \
             row they cannot act on"
        );
        assert_eq!(report.context["flow_id"], json!(FLOW));
    }
}
