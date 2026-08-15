//! **What happens to a proposal nobody answered** (hub#972 — ADR-0283 D3).
//!
//! The TTL of an approval was checked only on the way IN: `claim_pending` refused an expired row,
//! and nothing else in the hub ever looked at `expires_at` again. That left the one state a person
//! cannot get out of — the row can no longer be approved *or* rejected, so there is no action left
//! to take, and its run sits in `waiting_approval` for ever. Retention exempts that status on
//! purpose (a real approval legitimately waits for days), so the `payload` — stored VERBATIM, and
//! it can carry a customer's name, phone or address — was kept indefinitely by a hub whose whole
//! retention policy exists to stop exactly that.
//!
//! What this file pins down is the way out, and every half of it matters:
//!
//! - the sweep **decides** the row (`expired`) instead of leaving it undecidable;
//! - it applies the row's **own** expiry policy — a column, not a constant, so the generic
//!   `approval` step of hub#950 sets `on_expire` per document without a second sweep;
//! - the DEFAULT is the conservative one: an unanswered proposal is treated as a refusal, because
//!   the steps written after it assumed the write happened;
//! - **nothing runs**. An expiry is the opposite of an approval;
//! - the run reaches a terminal status, so the 90-day prune finally takes it **and its proposal**.
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::flows::approvals;
use erplora_runtime::flows::grants::GrantKind;
use erplora_runtime::flows::{store, NewFlow};
use erplora_runtime::registry::{EventSink, EventSource};
use erplora_runtime::{retention, Runtime};
use serde_json::{json, Value};

const HUB: &str = "hub-approval-expiry";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_flows")
        .join(name)
}

/// The WS observer, so the test can assert on the fact the core emits rather than on a screen.
#[derive(Default, Debug)]
struct Sink {
    events: Mutex<Vec<(String, Value)>>,
}
impl EventSink for Sink {
    fn emit(&self, _source: EventSource<'_>, name: &str, payload: &Value) {
        self.events.lock().unwrap().push((name.into(), payload.clone()));
    }
}
impl Sink {
    fn named(&self, name: &str) -> Vec<Value> {
        self.events
            .lock()
            .unwrap()
            .iter()
            .filter(|(n, _)| n == name)
            .map(|(_, p)| p.clone())
            .collect()
    }
}

async fn runtime() -> (Runtime, Arc<Sink>) {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("crm")).await.unwrap();
    (rt, sink)
}

/// An agent step followed by a step that assumed it acted — the shape that makes «expired» a
/// decision and not a shrug.
fn definition() -> Value {
    json!({
        "schema_version": 1,
        "steps": [
            { "id": "agent", "kind": "ai", "prompt": "book it",
              "tools": { "commands": ["crm.note.add"] } },
            { "id": "after", "kind": "command", "command": "crm.note.add",
              "params": { "text": "follow-up" } }
        ]
    })
}

async fn notes(rt: &Runtime) -> Vec<String> {
    rt.db_for_test()
        .query("SELECT text FROM crm_note ORDER BY text", &Params::new())
        .await
        .unwrap()
        .rows
        .iter()
        .map(|r| r["text"].as_str().unwrap_or_default().to_string())
        .collect()
}

async fn run_of(rt: &Runtime, flow_id: &str) -> store::FlowRun {
    rt.list_flow_runs(flow_id, 10, None).await.unwrap().remove(0)
}

/// A run parked on an approval, exactly as a 3 AM turn leaves it.
async fn parked_proposal(rt: &Runtime) -> (String, approvals::Approval) {
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Agent".into(),
                enabled: true,
                definition: definition(),
            },
            "hub_user:owner",
        )
        .await
        .unwrap()
        .id;
    rt.replace_flow_grants(
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
        "hub_user:owner",
    )
    .await
    .unwrap();
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:owner")
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    let run = run_of(rt, &flow_id).await;
    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: "crm.note.add".into(),
            payload: json!({ "text": "the proposed note" }),
            reason: "the assistant proposed this at 3 AM".into(),
            partial_output: json!({ "text": "I will book it" }),
        })
        .await
        .unwrap();
    (flow_id, approval)
}

/// Moves a proposal's deadline into the past, the way three days of silence would.
async fn age(rt: &Runtime, id: &str, when: &str) {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("when".into(), json!(when));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_approvals SET expires_at = :when WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
}

// ── the dead end, opened ───────────────────────────────────────────────────────────────────────

/// The whole issue in one test. Before the sweep every one of these four assertions failed: the
/// row stayed `pending` for ever, the run stayed `waiting_approval` for ever, and the only way out
/// was a hand-written `UPDATE` against the customer's database.
#[tokio::test]
async fn a_proposal_past_its_ttl_is_swept_the_run_ends_and_nothing_is_executed() {
    let (rt, sink) = runtime().await;
    let (flow_id, approval) = parked_proposal(&rt).await;
    age(&rt, &approval.id, "2020-01-01T00:00:00+00:00").await;

    let report = rt.sweep_expired_flow_approvals().await.unwrap();

    assert_eq!(report.expired, 1, "the sweep counts what it decided: {report:?}");
    assert_eq!(report.runs_stopped, 1);
    let swept = rt.get_flow_approval(&approval.id).await.unwrap();
    assert_eq!(swept.status, approvals::STATUS_EXPIRED);
    assert_eq!(
        swept.decided_by,
        approvals::DECIDED_BY_EXPIRY,
        "nobody decided this; the hub closed it, and the record says so instead of naming a person"
    );
    assert!(swept.decided_at.is_some(), "when it was closed is part of the record");

    assert!(
        notes(&rt).await.is_empty(),
        "an expiry is the opposite of an approval: it executes NOTHING"
    );
    assert_eq!(
        run_of(&rt, &flow_id).await.status,
        store::STATUS_CANCELLED,
        "the run leaves waiting_approval for a TERMINAL status; that is the whole point"
    );

    // And the steps written after the agent's do not run either — the tick must not pick the run
    // back up now that it is out of `waiting_approval`.
    rt.process_flows().await.unwrap();
    assert!(notes(&rt).await.is_empty(), "a cancelled run stays cancelled");

    let emitted = sink.named(approvals::EVENT_APPROVAL_EXPIRED);
    assert_eq!(emitted.len(), 1, "the tray hears about it without polling");
    assert_eq!(emitted[0]["approval_id"], json!(approval.id));
    assert_eq!(emitted[0]["run_id"], json!(swept.run_id));
    assert_eq!(emitted[0]["on_expire"], json!(approvals::ON_EXPIRE_REJECT));
}

/// A sweep runs every hour for the life of the hub, so «it did the right thing once» is not the
/// property that matters: the second pass must find nothing, decide nothing and emit nothing.
#[tokio::test]
async fn a_second_sweep_finds_nothing_and_re_decides_nothing() {
    let (rt, sink) = runtime().await;
    let (_flow_id, approval) = parked_proposal(&rt).await;
    age(&rt, &approval.id, "2020-01-01T00:00:00+00:00").await;

    rt.sweep_expired_flow_approvals().await.unwrap();
    let after_first = rt.get_flow_approval(&approval.id).await.unwrap();

    let second = rt.sweep_expired_flow_approvals().await.unwrap();

    assert!(second.is_empty(), "nothing left to sweep: {second:?}");
    assert_eq!(
        rt.get_flow_approval(&approval.id).await.unwrap().decided_at,
        after_first.decided_at,
        "the closing moment is written once and never rewritten"
    );
    assert_eq!(
        sink.named(approvals::EVENT_APPROVAL_EXPIRED).len(),
        1,
        "and the tray is not told the same thing every hour"
    );
}

/// A proposal still inside its window is a question somebody can still answer. The sweep is a
/// deadline, not a cleaner.
#[tokio::test]
async fn a_proposal_inside_its_window_is_left_alone_and_can_still_be_decided() {
    let (rt, _sink) = runtime().await;
    let (flow_id, approval) = parked_proposal(&rt).await;

    let report = rt.sweep_expired_flow_approvals().await.unwrap();

    assert!(report.is_empty(), "72 h have not passed: {report:?}");
    assert_eq!(
        rt.get_flow_approval(&approval.id).await.unwrap().status,
        approvals::STATUS_PENDING
    );
    assert_eq!(
        run_of(&rt, &flow_id).await.status,
        store::STATUS_WAITING_APPROVAL
    );
    rt.decide_flow_approval(&approval.id, true, "hub_user:owner", "")
        .await
        .expect("the sweep did not burn a decidable proposal");
    assert_eq!(notes(&rt).await, vec!["the proposed note"]);
}

/// The policy is a **column**, not a constant: hub#950's generic `approval` step writes
/// `on_expire` per document, and this sweep is the one piece that reads it. `continue` is the
/// opt-in that says the steps after this one do NOT depend on the write.
#[tokio::test]
async fn the_policy_comes_from_the_row_so_continue_resumes_the_run() {
    let (rt, _sink) = runtime().await;
    let (flow_id, approval) = parked_proposal(&rt).await;
    let mut p = Params::new();
    p.insert("id".into(), json!(approval.id));
    p.insert("policy".into(), json!(approvals::ON_EXPIRE_CONTINUE));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_approvals SET on_expire = :policy, \
             expires_at = '2020-01-01T00:00:00+00:00' WHERE id = :id",
            &p,
        )
        .await
        .unwrap();

    let report = rt.sweep_expired_flow_approvals().await.unwrap();

    assert_eq!(report.expired, 1);
    assert_eq!(report.runs_resumed, 1, "this one carries on: {report:?}");
    assert_eq!(report.runs_stopped, 0);
    assert_eq!(
        rt.get_flow_approval(&approval.id).await.unwrap().status,
        approvals::STATUS_EXPIRED,
        "the proposal expired either way; what differs is what the RUN does next"
    );
    assert!(
        notes(&rt).await.is_empty(),
        "`continue` continues the flow — it does not execute the proposal"
    );

    rt.process_flows().await.unwrap();
    assert_eq!(
        notes(&rt).await,
        vec!["follow-up"],
        "the step after the agent's runs, and only that one"
    );
    assert_eq!(run_of(&rt, &flow_id).await.status, store::STATUS_DONE);
}

/// After the sweep the row is no longer `pending`, and the refusal a person sees has to keep its
/// NAME. `already_decided` would be a lie — nobody decided it — and the screen shows a different
/// message for each code.
#[tokio::test]
async fn a_swept_proposal_is_still_refused_as_expired_and_not_as_already_decided() {
    let (rt, _sink) = runtime().await;
    let (_flow_id, approval) = parked_proposal(&rt).await;
    age(&rt, &approval.id, "2020-01-01T00:00:00+00:00").await;
    rt.sweep_expired_flow_approvals().await.unwrap();

    for approve in [true, false] {
        let err = rt
            .decide_flow_approval(&approval.id, approve, "hub_user:owner", "")
            .await
            .expect_err("an expired proposal is not decidable");
        match err {
            erplora_runtime::RuntimeError::Domain { code, .. } => assert_eq!(
                code,
                approvals::ERR_APPROVAL_EXPIRED,
                "approve={approve}: the code is the half the tray programs against"
            ),
            other => panic!("expected a domain refusal, got {other}"),
        }
    }
    assert!(notes(&rt).await.is_empty());
}

/// The reason this is a P1 and not a tidy-up: the run was **exempt from the 90-day prune** while it
/// waited, and the proposal it points at holds the payload verbatim. Terminal status alone is not
/// enough — the proposal has to go WITH its run, or the personal data outlives the history that
/// explains it.
#[tokio::test]
async fn once_swept_the_run_and_its_proposal_finally_enter_the_ninety_day_prune() {
    let (rt, _sink) = runtime().await;
    let (_flow_id, approval) = parked_proposal(&rt).await;
    age(&rt, &approval.id, "2020-01-01T00:00:00+00:00").await;

    // Before the sweep: a run in `waiting_approval` is live work at ANY age, so an ancient one is
    // untouchable and its payload with it.
    let ancient = (chrono::Utc::now() - chrono::Duration::days(400)).to_rfc3339();
    let mut p = Params::new();
    p.insert("at".into(), json!(ancient));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_runs SET created_at = :at, updated_at = :at",
            &p,
        )
        .await
        .unwrap();
    let cutoff = (chrono::Utc::now() - chrono::Duration::days(retention::RETENTION_DAYS))
        .to_rfc3339();
    let before = retention::prune_once(rt.db_for_test(), HUB, &cutoff)
        .await
        .unwrap();
    assert_eq!(before.runs, 0, "this is the hole: {before:?}");

    rt.sweep_expired_flow_approvals().await.unwrap();
    // `finish` stamps `finished_at` with NOW, so age that too: what the prune measures is the
    // TERMINAL moment, not the birth.
    rt.db_for_test()
        .execute("UPDATE _flow_runs SET finished_at = :at", &p)
        .await
        .unwrap();

    let after = retention::prune_once(rt.db_for_test(), HUB, &cutoff)
        .await
        .unwrap();

    assert_eq!(after.runs, 1, "terminal at last, and past the window");
    assert_eq!(
        after.approvals, 1,
        "and the proposal goes with it: the payload is the personal data"
    );
    assert!(
        rt.get_flow_approval(&approval.id).await.is_err(),
        "nothing is left holding the customer's details"
    );
}
