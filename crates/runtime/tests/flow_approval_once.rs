//! **An approval executes its command once, whoever else is deciding at the same moment**
//! (hub#2502 — HUB-F100, HUB-F101).
//!
//! Approving used to be three separate gestures: read the row and check it is still `pending`,
//! run the command, and only then write `approved` with `WHERE status = 'pending'`. Nothing tied
//! the first to the last. Two people pressing *approve* on the same proposal both read `pending`,
//! both ran the command — two bookings for one customer — and the second `UPDATE` matched zero
//! rows without anybody noticing. The hourly expiry sweep could slip into the same gap: it closed
//! the row as `expired` and cancelled the run while the command was already running, and the
//! command committed anyway.
//!
//! The command in the fixture sleeps inside its own transaction, so every race below is
//! deterministic: the second decider always arrives while the first is still running. Everything
//! runs against a real Postgres pool (5 connections), which is what makes the deciders concurrent.
use std::path::PathBuf;
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Duration;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry, ErrorSink};
use erplora_runtime::flows::approvals;
use erplora_runtime::flows::grants::{GrantKind, GrantSpec};
use erplora_runtime::flows::{store, NewFlow};
use erplora_runtime::{Runtime, RuntimeError};
use serde_json::json;

const HUB: &str = "hub-approval-once";
const OWNER: &str = "hub_user:owner";
const MARTA: &str = "hub_user:marta";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_flows")
        .join(name)
}

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("approval_race"))
        .await
        .unwrap();
    rt
}

async fn bookings(rt: &Runtime) -> Vec<String> {
    rt.db_for_test()
        .query(
            "SELECT text FROM race_booking ORDER BY text",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows
        .iter()
        .map(|r| r["text"].as_str().unwrap_or_default().to_string())
        .collect()
}

async fn run_of(rt: &Runtime, flow_id: &str) -> store::FlowRun {
    rt.list_flow_runs(flow_id, 10, None)
        .await
        .unwrap()
        .remove(0)
}

/// A run parked on the assistant's proposal to book, exactly as a 3 AM turn leaves it.
async fn parked_proposal(rt: &Runtime) -> (String, approvals::Approval) {
    parked_proposal_of(rt, "race.booking.add").await
}

async fn parked_proposal_of(rt: &Runtime, command: &str) -> (String, approvals::Approval) {
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Agent".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [
                        { "id": "agent", "kind": "ai", "prompt": "book it",
                          "tools": { "commands": [command] } }
                    ]
                }),
            },
            OWNER,
        )
        .await
        .unwrap()
        .id;
    rt.replace_flow_grants(
        &flow_id,
        &[GrantSpec::pair(GrantKind::Command, command)],
        OWNER,
    )
    .await
    .unwrap();
    rt.start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    let run = run_of(rt, &flow_id).await;
    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: command.into(),
            payload: json!({ "text": "Marta, Tuesday 10:00" }),
            reason: String::new(),
            partial_output: json!({}),
            on_expire: approvals::ExpiryPolicy::Reject,
            on_reject: approvals::RejectPolicy::Cancel,
        })
        .await
        .unwrap();
    (flow_id, approval)
}

/// What the hub would forward to erplora.com as «a module's command broke».
#[derive(Default)]
struct Reports(Mutex<Vec<ErrorEvent>>);
impl ErrorSink for Reports {
    fn submit(&self, event: ErrorEvent) {
        self.0.lock().unwrap().push(event);
    }
}

/// The registry is one per process and keeps the first sink installed, so every test of this file
/// shares this one and reads only the reports about ITS command.
fn reports() -> &'static Arc<Reports> {
    static REPORTS: OnceLock<Arc<Reports>> = OnceLock::new();
    REPORTS.get_or_init(|| {
        let sink = Arc::new(Reports::default());
        ErrorRegistry::install(sink.clone());
        sink
    })
}

fn reports_about(command: &str) -> Vec<String> {
    reports()
        .0
        .lock()
        .unwrap()
        .iter()
        .filter(|e| e.context.get("command").and_then(|c| c.as_str()) == Some(command))
        .map(|e| format!("{} {}", e.error_code, e.message))
        .collect()
}

fn code_of(err: &RuntimeError) -> Option<&str> {
    match err {
        RuntimeError::Domain { code, .. } => Some(code.as_str()),
        _ => None,
    }
}

/// The headline of the issue: two people approve the same proposal at the same moment. One of
/// them wins and books; the other is told somebody already answered, and books nothing.
#[tokio::test]
async fn two_simultaneous_approvals_of_one_proposal_book_once_hub2502() {
    reports();
    let rt = runtime().await;
    let (flow_id, approval) = parked_proposal(&rt).await;

    let (first, second) = tokio::join!(
        rt.decide_flow_approval(&approval.id, true, OWNER, ""),
        rt.decide_flow_approval(&approval.id, true, MARTA, ""),
    );

    assert_eq!(
        bookings(&rt).await,
        vec!["Marta, Tuesday 10:00"],
        "two approvals of one proposal must run its command exactly once"
    );
    let (won, lost) = match (first, second) {
        (Ok(won), Err(lost)) | (Err(lost), Ok(won)) => (won, lost),
        (a, b) => panic!("exactly one approval must win: {a:?} / {b:?}"),
    };
    assert_eq!(won.status, approvals::STATUS_APPROVED);
    assert_eq!(
        code_of(&lost),
        Some(approvals::ERR_APPROVAL_ALREADY_DECIDED),
        "the loser is told somebody else answered: {lost}"
    );
    // Losing is the guard working, not the module's command breaking: nothing about it may reach
    // erplora.com as an error of the module.
    let race_reports = reports_about("race.booking.add");
    assert!(race_reports.is_empty(), "{race_reports:?}");
    let row = rt.get_flow_approval(&approval.id).await.unwrap();
    assert_eq!(row.status, approvals::STATUS_APPROVED);
    assert_eq!(
        row.decided_by, won.decided_by,
        "the row names the person whose approval actually ran"
    );
    // The approval hands the run back to the tick, which finishes it — once.
    rt.process_flows().await.unwrap();
    assert_eq!(run_of(&rt, &flow_id).await.status, store::STATUS_DONE);
    assert_eq!(bookings(&rt).await.len(), 1);
}

/// The sweep closes the proposal while an approval pressed BEFORE the deadline is still running
/// its command. Only one of them may decide the row, and the run they leave behind must agree
/// with it: the row says `expired` and the run is cancelled, so nothing may have been booked.
#[tokio::test]
async fn an_approval_overtaken_by_the_expiry_sweep_books_nothing_hub2502() {
    let rt = runtime().await;
    let (flow_id, approval) = parked_proposal(&rt).await;
    // A deadline a moment away: still open when the person presses, past by the time the sweep
    // runs — which is while the (slow) command is still inside its transaction.
    let deadline = (chrono::Utc::now() + chrono::Duration::milliseconds(250)).to_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(approval.id));
    p.insert("at".into(), json!(deadline));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_approvals SET expires_at = :at WHERE id = :id",
            &p,
        )
        .await
        .unwrap();

    let (decided, swept) = tokio::join!(
        rt.decide_flow_approval(&approval.id, true, OWNER, ""),
        async {
            tokio::time::sleep(Duration::from_millis(450)).await;
            rt.sweep_expired_flow_approvals().await
        },
    );

    assert_eq!(
        swept.unwrap().expired,
        1,
        "the sweep closed the overdue proposal"
    );
    assert!(
        bookings(&rt).await.is_empty(),
        "a proposal the sweep closed as expired must not have booked anything"
    );
    let err = decided.expect_err("the approval lost to the sweep");
    assert_eq!(
        code_of(&err),
        Some(approvals::ERR_APPROVAL_EXPIRED),
        "the person is told the proposal expired: {err}"
    );
    let row = rt.get_flow_approval(&approval.id).await.unwrap();
    assert_eq!(row.status, approvals::STATUS_EXPIRED);
    assert_eq!(run_of(&rt, &flow_id).await.status, store::STATUS_CANCELLED);
}

/// A rejection lands while an approval of the same proposal is running its command. The rejection
/// committed first and cancelled the run, so the approval must not book.
#[tokio::test]
async fn an_approval_overtaken_by_a_rejection_books_nothing_hub2502() {
    let rt = runtime().await;
    let (flow_id, approval) = parked_proposal(&rt).await;

    let (approved, rejected) = tokio::join!(
        rt.decide_flow_approval(&approval.id, true, OWNER, ""),
        async {
            tokio::time::sleep(Duration::from_millis(300)).await;
            rt.decide_flow_approval(&approval.id, false, MARTA, "we are closed")
                .await
        },
    );

    assert_eq!(rejected.unwrap().status, approvals::STATUS_REJECTED);
    assert!(
        bookings(&rt).await.is_empty(),
        "a rejected proposal must not have booked anything"
    );
    let err = approved.expect_err("the approval lost to the rejection");
    assert_eq!(
        code_of(&err),
        Some(approvals::ERR_APPROVAL_ALREADY_DECIDED),
        "{err}"
    );
    let row = rt.get_flow_approval(&approval.id).await.unwrap();
    assert_eq!(row.status, approvals::STATUS_REJECTED);
    assert_eq!(row.decided_by, MARTA);
    assert_eq!(run_of(&rt, &flow_id).await.status, store::STATUS_CANCELLED);
}

/// The other half of «only one wins»: recording a decision on a row somebody else already decided
/// is a refusal, not a silent zero-row `UPDATE` followed by the caller ending the run as if it had
/// won. This is what keeps a rejection (or an answered question) that loses the race from
/// cancelling a run the winner already moved on.
#[tokio::test]
async fn recording_a_decision_on_a_row_already_decided_is_refused_hub2502() {
    let rt = runtime().await;
    let (_, approval) = parked_proposal(&rt).await;
    rt.decide_flow_approval(&approval.id, true, OWNER, "")
        .await
        .unwrap();

    let err = approvals::mark_decided_with_comment(
        rt.db_for_test(),
        HUB,
        &approval.id,
        approvals::STATUS_REJECTED,
        MARTA,
        "",
        "too late",
    )
    .await
    .expect_err("a decision that lost the race must say so");
    assert_eq!(
        code_of(&err),
        Some(approvals::ERR_APPROVAL_ALREADY_DECIDED),
        "{err}"
    );
    let row = rt.get_flow_approval(&approval.id).await.unwrap();
    assert_eq!(row.status, approvals::STATUS_APPROVED);
    assert_eq!(
        row.decided_by, OWNER,
        "the winner's decision is never overwritten"
    );
}

/// The guard must not swallow a command that really breaks: an approval nobody raced, whose
/// command fails, still records «approved, and the command failed», fails the run, and reports
/// the module's error. The fixture breaks with the same `NOT NULL` violation the guard uses to
/// roll back a loser, so this is also what tells the two apart: the row, not the SQLSTATE.
#[tokio::test]
async fn an_approval_whose_command_really_fails_is_still_recorded_and_reported_hub2502() {
    reports();
    let rt = runtime().await;
    let (flow_id, approval) = parked_proposal_of(&rt, "race.booking.broken").await;

    let err = rt
        .decide_flow_approval(&approval.id, true, OWNER, "")
        .await
        .expect_err("the command breaks");

    assert_ne!(
        code_of(&err),
        Some(approvals::ERR_APPROVAL_ALREADY_DECIDED),
        "nobody else decided: this is the command's own failure, {err}"
    );
    let row = rt.get_flow_approval(&approval.id).await.unwrap();
    assert_eq!(row.status, approvals::STATUS_APPROVED);
    assert_eq!(row.decided_by, OWNER);
    assert!(!row.error.is_empty(), "the row keeps what broke");
    assert_eq!(run_of(&rt, &flow_id).await.status, store::STATUS_FAILED);
    assert_eq!(
        reports_about("race.booking.broken").len(),
        1,
        "a command that really broke is reported once"
    );
}
