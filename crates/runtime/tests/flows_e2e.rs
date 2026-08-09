//! **The whole chain of the automation kernel, end to end** (hub#661 — ADR-0283 K1+K2+K7).
//!
//! ```text
//!  sales.sale.complete (a cashier)  →  emits `sale.completed`  →  _event_outbox
//!         ↓ relay: manifest listeners first, THEN the flow triggers (insert only)
//!  _flow_runs row  →  flows_tick  →  crm.note.add  under Origin::Automation + _flow_grants
//!         ↓ the command's own emit
//!  crm.note.added  →  _event_outbox  →  crm.note.count (listener, permissions derived from grants)
//! ```
//!
//! Everything here goes through the REAL path — modules installed from disk, the real dispatcher,
//! the real relay — because the properties being pinned are precisely the ones a unit test can
//! fake away:
//!
//! - **A flow does what a manifest listener may not.** Since hub#659 a listener may only fire a
//!   command of its OWN module, so `sales` cannot reach into `crm`. That reaction, with a
//!   transformation, is what flows are for (ADR-0283 §7) — and it costs an explicit grant.
//! - **The grant is the gate, and nothing else is.** No grant, no command; a revoked grant stops
//!   the next step; an internal command is refused as it is for any external caller.
//! - **A flow inherits the fiscal gates ÍNTEGROS.** Going through `execute_at` is the whole reason
//!   ADR-0283 D2 puts the automation gate there instead of giving flows a dispatcher of their own.
//! - **The cascade survives.** A command a flow runs emits its own events, and their listeners
//!   actually run. Today that holds because the flow's context carries the permissions of the
//!   commands it was granted; once hub#686 / ADR-0288 lands it will hold because a listener runs
//!   with the authority of its OWN module. The assertion is deliberately written against the
//!   OUTCOME (the listener ran, nothing is in dead-letter) and not against either mechanism, so it
//!   stays honest across that change instead of pinning a detail that is about to move.
//! - **A flow that triggers itself stops; the hub does not.**
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::flows::grants::GrantKind;
use erplora_runtime::flows::{store, NewFlow};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value};

const HUB: &str = "hub-flows-e2e";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_flows")
        .join(name)
}

/// The cashier at the till: a real user with the permissions of their own module and **not** the
/// ones the flow will need. That asymmetry is the point of the whole design.
fn cashier() -> RequestContext {
    RequestContext::new(HUB, "cashier-1", ["sales.add_sale".to_string()])
}

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("sales")).await.unwrap();
    rt.install_from_dir(&fixture("crm")).await.unwrap();
    rt
}

async fn count(rt: &Runtime, sql: &str) -> i64 {
    rt.db_for_test()
        .query(sql, &Params::new())
        .await
        .unwrap()
        .rows
        .first()
        .and_then(|r| r["c"].as_i64().or_else(|| r["c"].as_f64().map(|f| f as i64)))
        .unwrap_or(-1)
}

async fn rows(rt: &Runtime, sql: &str) -> Vec<Value> {
    rt.db_for_test()
        .query(sql, &Params::new())
        .await
        .unwrap()
        .rows
}

/// The flow of the story: «when a sale over 100 € closes, leave a note on that customer».
fn welcome_definition() -> Value {
    json!({
        "schema_version": 1,
        "triggers": [{
            "kind": "event",
            "event": "sale.completed",
            "filter": { "event.total": { "gte": "100" } },
            "input": { "customer_id": "event.customer_id", "total": "event.total" }
        }],
        "steps": [{
            "id": "note",
            "kind": "command",
            "command": "crm.note.add",
            "params": {
                "customer_id": "input.customer_id",
                "text": "thanks for the {{input.total}} order"
            }
        }]
    })
}

async fn create_flow(rt: &Runtime, definition: Value) -> String {
    rt.create_flow(
        &NewFlow {
            name: "Welcome".into(),
            enabled: true,
            definition,
        },
        "hub_user:owner",
    )
    .await
    .unwrap()
    .id
}

async fn grant(rt: &Runtime, flow_id: &str, command: &str) {
    rt.replace_flow_grants(
        flow_id,
        &[(GrantKind::Command, command.to_string())],
        "hub_user:owner",
    )
    .await
    .unwrap();
}

async fn complete_sale(rt: &Runtime, total: &str) {
    let mut p = Params::new();
    p.insert("total".into(), json!(total));
    p.insert("customer_id".into(), json!("c-1"));
    rt.execute_command("sales.sale.complete", &p, &cashier())
        .await
        .unwrap();
}

// ── the whole chain ───────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_sale_triggers_a_flow_that_writes_in_another_module_and_its_cascade_survives() {
    let rt = runtime().await;
    let flow_id = create_flow(&rt, welcome_definition()).await;
    grant(&rt, &flow_id, "crm.note.add").await;

    complete_sale(&rt, "120.50").await;

    // The relay delivers. It creates the RUN and nothing else: executing a flow inline would hold
    // the runtime's global lock for the length of the flow, delays included.
    rt.drain_outbox().await.unwrap();
    let runs = rt.list_flow_runs(&flow_id, 10).await.unwrap();
    assert_eq!(runs.len(), 1, "the event started exactly one run");
    assert_eq!(runs[0].status, store::STATUS_PENDING);
    assert_eq!(runs[0].trigger_kind, "event");
    assert!(
        !runs[0].parent_event_id.is_empty(),
        "the run remembers the event that caused it"
    );
    assert_eq!(
        runs[0].input,
        json!({ "customer_id": "c-1", "total": "120.50" }),
        "the input_map shaped the event into the run's input"
    );
    assert_eq!(count(&rt, "SELECT COUNT(*) AS c FROM crm_note").await, 0);

    // The tick executes the step: a command of ANOTHER module, which no manifest listener of
    // `sales` could ever reach (hub#659).
    rt.process_flows().await.unwrap();

    let notes = rows(&rt, "SELECT hub_id, created_by, customer_id, text FROM crm_note").await;
    assert_eq!(notes.len(), 1);
    assert_eq!(notes[0]["customer_id"], json!("c-1"));
    assert_eq!(
        notes[0]["text"],
        json!("thanks for the 120.50 order"),
        "the template was rendered against the run's input"
    );
    assert_eq!(
        notes[0]["hub_id"],
        json!(HUB),
        "the tenant is never negotiable, whoever is acting"
    );
    assert_eq!(
        notes[0]["created_by"],
        json!(format!("flow:{flow_id}")),
        "the audit says a flow wrote this, and which one"
    );

    let run = rt.list_flow_runs(&flow_id, 10).await.unwrap().remove(0);
    assert_eq!(run.status, store::STATUS_DONE);
    let (_, steps) = rt.get_flow_run(&run.id).await.unwrap();
    assert_eq!(steps.len(), 1);
    assert_eq!(steps[0].status, "done");
    assert_eq!(steps[0].input["customer_id"], json!("c-1"));

    // The command a flow runs emits its own events, transactionally, like any other command.
    assert_eq!(
        count(
            &rt,
            "SELECT COUNT(*) AS c FROM _event_outbox WHERE event_name = 'crm.note.added'"
        )
        .await,
        1,
        "a flow's command feeds the outbox exactly like a human's"
    );

    // And that cascade DELIVERS. Its listener demands `crm.change_customer`, which the cashier who
    // closed the sale does not have — the exact shape of the P0 in hub#686. It runs because the
    // flow's context carries the permissions of the commands it was granted (ADR-0283 §2, as
    // amended by ADR-0288).
    rt.drain_outbox().await.unwrap();
    assert_eq!(
        count(&rt, "SELECT n AS c FROM crm_counter WHERE name = 'notes'").await,
        1,
        "the listener of the flow's own event ran instead of dying in dead-letter"
    );
    assert_eq!(
        count(
            &rt,
            "SELECT COUNT(*) AS c FROM _event_outbox WHERE status = 'dead'"
        )
        .await,
        0
    );
}

#[tokio::test]
async fn the_filter_is_what_decides_and_a_sale_below_it_starts_nothing() {
    let rt = runtime().await;
    let flow_id = create_flow(&rt, welcome_definition()).await;
    grant(&rt, &flow_id, "crm.note.add").await;

    complete_sale(&rt, "9.90").await;
    rt.drain_outbox().await.unwrap();
    rt.process_flows().await.unwrap();

    assert!(rt.list_flow_runs(&flow_id, 10).await.unwrap().is_empty());
    assert_eq!(count(&rt, "SELECT COUNT(*) AS c FROM crm_note").await, 0);
}

// ── the grant is the gate ─────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn without_a_grant_the_flow_runs_and_writes_nothing() {
    let rt = runtime().await;
    let flow_id = create_flow(&rt, welcome_definition()).await;
    // No grant. The owner wrote the flow; they did not say it may write in `crm`.

    complete_sale(&rt, "120.50").await;
    rt.drain_outbox().await.unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(count(&rt, "SELECT COUNT(*) AS c FROM crm_note").await, 0);
    let run = rt.list_flow_runs(&flow_id, 10).await.unwrap().remove(0);
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("flow.grant_denied"),
        "the failure carries the stable code the UI offers «grant it» from: {}",
        run.last_error
    );
}

#[tokio::test]
async fn a_grant_for_one_command_does_not_open_its_neighbour() {
    let rt = runtime().await;
    let mut definition = welcome_definition();
    definition["steps"][0]["command"] = json!("crm.note.count");
    let flow_id = create_flow(&rt, definition).await;
    // Granted: `crm.note.add`. Executed by the flow: `crm.note.count` — same module, same
    // permission, different command. The gate names COMMANDS, not permissions, on purpose.
    grant(&rt, &flow_id, "crm.note.add").await;

    complete_sale(&rt, "120.50").await;
    rt.drain_outbox().await.unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(count(&rt, "SELECT COUNT(*) AS c FROM crm_counter").await, 0);
    let run = rt.list_flow_runs(&flow_id, 10).await.unwrap().remove(0);
    assert_eq!(run.status, store::STATUS_FAILED);
}

#[tokio::test]
async fn an_internal_command_is_as_closed_to_a_flow_as_it_is_to_the_outside_world() {
    let rt = runtime().await;
    let mut definition = welcome_definition();
    definition["steps"][0]["command"] = json!("crm._purge_notes");
    let flow_id = create_flow(&rt, definition).await;
    // Even WITH the grant: an `_`-prefixed command is a module's own implementation, and the
    // public command that normally fires it is where its orchestration lives.
    grant(&rt, &flow_id, "crm._purge_notes").await;

    complete_sale(&rt, "120.50").await;
    rt.drain_outbox().await.unwrap();
    rt.process_flows().await.unwrap();

    let run = rt.list_flow_runs(&flow_id, 10).await.unwrap().remove(0);
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("crm._purge_notes"),
        "the refusal names the command: {}",
        run.last_error
    );
}

#[tokio::test]
async fn revoking_a_grant_stops_the_run_at_its_next_step() {
    let rt = runtime().await;
    let mut definition = welcome_definition();
    // Two writes with a pause in between: the window in which an owner changes their mind.
    definition["steps"] = json!([
        { "id": "first", "kind": "command", "command": "crm.note.add",
          "params": { "text": "first" } },
        { "id": "wait", "kind": "delay", "seconds": 3600 },
        { "id": "second", "kind": "command", "command": "crm.note.add",
          "params": { "text": "second" } }
    ]);
    let flow_id = create_flow(&rt, definition).await;
    grant(&rt, &flow_id, "crm.note.add").await;

    complete_sale(&rt, "120.50").await;
    rt.drain_outbox().await.unwrap();
    rt.process_flows().await.unwrap();
    assert_eq!(count(&rt, "SELECT COUNT(*) AS c FROM crm_note").await, 1);

    // Revoked mid-flight — `PUT …/grants` with an empty list.
    rt.replace_flow_grants(&flow_id, &[], "hub_user:owner")
        .await
        .unwrap();
    let run_id = rt.list_flow_runs(&flow_id, 10).await.unwrap().remove(0).id;
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_runs SET wake_at = '2020-01-01T00:00:00+00:00' WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(
        count(&rt, "SELECT COUNT(*) AS c FROM crm_note").await,
        1,
        "the second write never happened"
    );
    let run = rt.list_flow_runs(&flow_id, 10).await.unwrap().remove(0);
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(run.last_error.contains("flow.grant_denied"), "{}", run.last_error);
}

// ── the gates a flow inherits by going through `execute_at` ───────────────────────────────────

#[tokio::test]
async fn the_fiscal_precondition_refuses_a_flow_exactly_as_it_refuses_a_person() {
    let rt = runtime().await;
    let mut definition = welcome_definition();
    // `crm.receipt.stamp` binds `:business_tax_id`, so it stamps the fiscal identity of the
    // business — and this hub has none configured.
    definition["steps"][0]["command"] = json!("crm.receipt.stamp");
    definition["steps"][0]["params"] = json!({});
    let flow_id = create_flow(&rt, definition).await;
    grant(&rt, &flow_id, "crm.receipt.stamp").await;

    complete_sale(&rt, "120.50").await;
    rt.drain_outbox().await.unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(
        count(&rt, "SELECT COUNT(*) AS c FROM crm_receipt").await,
        0,
        "a grant authorises WHAT a flow may run, never WHETHER the hub may issue"
    );
    let run = rt.list_flow_runs(&flow_id, 10).await.unwrap().remove(0);
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("business_tax_id"),
        "the fiscal gate answered, naming what is missing: {}",
        run.last_error
    );
}

// ── the hub survives its own users ────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_flow_that_emits_the_event_that_triggers_it_is_cut_off_and_the_hub_keeps_working() {
    let rt = runtime().await;
    // `crm.note.echo` writes a note AND emits `sale.completed` — the first mistake anybody makes
    // in a visual editor, and the one that would otherwise spin until the database fills up.
    let mut definition = welcome_definition();
    definition["steps"][0]["command"] = json!("crm.note.echo");
    definition["triggers"][0]["filter"] = json!({});
    definition["triggers"][0]["input"] = json!({});
    let flow_id = create_flow(&rt, definition).await;
    grant(&rt, &flow_id, "crm.note.echo").await;

    complete_sale(&rt, "120.50").await;

    // Drive the loop the way the server does: relay, then tick, over and over. If nothing stopped
    // the cascade this would never settle.
    for _ in 0..60 {
        rt.drain_outbox().await.unwrap();
        rt.process_flows().await.unwrap();
    }

    // 17 = depths 0..=16: `MAX_EVENT_DEPTH` is what stops it, NOT the rate guard (which only
    // trips at 30 runs/min). Asserting the tighter number is what tells the two guards apart —
    // with a loose bound this test would still pass if the depth guard were deleted.
    let runs = rt.list_flow_runs(&flow_id, 200).await.unwrap();
    assert!(
        runs.len() <= 17,
        "the DEPTH guard bounds the cascade; {} runs means it is not the one stopping this",
        runs.len()
    );
    assert!(
        runs.iter().any(|r| r.depth > 0),
        "the runs climbed in depth instead of restarting at zero, which is what makes the ceiling \
         reachable at all"
    );
    // And the hub is still perfectly able to work: a fresh sale still closes.
    complete_sale(&rt, "10.00").await;
    assert_eq!(count(&rt, "SELECT COUNT(*) AS c FROM sales_sale").await, 2);
}

#[tokio::test]
async fn a_flow_of_another_hub_never_sees_this_hubs_events() {
    let rt = runtime().await;
    let flow_id = create_flow(&rt, welcome_definition()).await;
    grant(&rt, &flow_id, "crm.note.add").await;

    // An event of a different tenant, sitting in the same table (the row contract survives even
    // though ADR-0201 gives each hub its own database).
    let mut p = Params::new();
    p.insert("now".into(), json!("2026-08-09T10:00:00+00:00"));
    rt.db_for_test()
        .execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, module_id, payload, depth, status, \
              attempts, next_attempt_at, last_error, created_at) \
             VALUES ('evt-other', 'hub-someone-else', 'u', '[]', 'sale.completed', 'sales', \
                     '{\"total\":\"999.00\",\"customer_id\":\"c-9\"}', 0, 'pending', 0, :now, '', :now)",
            &p,
        )
        .await
        .unwrap();

    rt.drain_outbox().await.unwrap();
    rt.process_flows().await.unwrap();

    assert!(
        rt.list_flow_runs(&flow_id, 10).await.unwrap().is_empty(),
        "a flow reacts to its own hub and to nothing else"
    );
    assert_eq!(count(&rt, "SELECT COUNT(*) AS c FROM crm_note").await, 0);
}
