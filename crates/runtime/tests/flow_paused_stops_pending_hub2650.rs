//! **Pausing an automation stops what it left pending** (hub#2650 — HUB-F87, HUB-F100).
//!
//! Pausing already stopped new starts and cancelled the runs that were ready to move on, but two
//! things the automation had already left behind ignored the switch:
//!
//! - **a proposal waiting in the tray**: approving it ran the command anyway — the owner pauses the
//!   assistant because it is booking the wrong slots, somebody approves one of its proposals from
//!   before the pause, and the booking is written;
//! - **a message waiting in the outbox**: the WhatsApp or email went out to the customer.
//!
//! Now approving a paused automation's proposal is refused with `flow.disabled`, nothing runs and
//! the proposal stays pending (it can be approved once the automation is back on, or rejected, or
//! left to expire). A queued message of a paused automation is not sent: it ends in «Eventos
//! caídos» saying the automation is paused, and it can be resent from there by hand. Turning the
//! automation back on does NOT send it on its own — a reminder that waited out a pause may be
//! about something that is already over.
//!
//! Everything runs against the real runtime and a real Postgres.
use std::path::PathBuf;
use std::time::Duration;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::flows::approvals;
use erplora_runtime::flows::grants::{GrantKind, GrantSpec};
use erplora_runtime::flows::{store, NewFlow};
use erplora_runtime::host_notify::MockTransport;
use erplora_runtime::outbox::RetryOutcome;
use erplora_runtime::{Runtime, RuntimeError};
use serde_json::{json, Value};

const HUB: &str = "hub-paused-2650";
const OWNER: &str = "hub_user:owner";
const PHONE: &str = "+34600111222";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_flows")
        .join(name)
}

fn code_of(err: &RuntimeError) -> Option<&str> {
    match err {
        RuntimeError::Domain { code, .. } => Some(code.as_str()),
        _ => None,
    }
}

/// Flips the automation's switch the way the editor does: the same document, `enabled` changed.
async fn set_enabled(rt: &Runtime, flow_id: &str, enabled: bool) {
    let flow = rt.get_flow(flow_id).await.unwrap();
    rt.update_flow(
        flow_id,
        &NewFlow {
            name: flow.name,
            enabled,
            definition: flow.definition,
        },
        OWNER,
    )
    .await
    .unwrap();
}

async fn rows(rt: &Runtime, sql: &str) -> Vec<Value> {
    rt.db_for_test()
        .query(sql, &Params::new())
        .await
        .unwrap()
        .rows
}

// ── a proposal in the tray ────────────────────────────────────────────────────────────────────

/// The `race` fixture: one command that books (slowly, inside its own transaction) and one table.
async fn approvals_runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("approval_race"))
        .await
        .unwrap();
    rt
}

async fn bookings(rt: &Runtime) -> Vec<String> {
    rows(rt, "SELECT text FROM race_booking ORDER BY text")
        .await
        .iter()
        .map(|r| r["text"].as_str().unwrap_or_default().to_string())
        .collect()
}

async fn run_status(rt: &Runtime, flow_id: &str) -> String {
    rt.list_flow_runs(flow_id, 10, None)
        .await
        .unwrap()
        .remove(0)
        .status
}

/// A run parked on the assistant's proposal to book, as a turn before the pause leaves it.
async fn parked_proposal(rt: &Runtime) -> (String, approvals::Approval) {
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Agent".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [
                        { "id": "agent", "kind": "ai", "prompt": "book it",
                          "tools": { "commands": ["race.booking.add"] } }
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
        &[GrantSpec::pair(GrantKind::Command, "race.booking.add")],
        OWNER,
    )
    .await
    .unwrap();
    rt.start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    let run = rt
        .list_flow_runs(&flow_id, 10, None)
        .await
        .unwrap()
        .remove(0);
    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: "race.booking.add".into(),
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

/// The headline: the owner pauses the automation, somebody approves a proposal it left before the
/// pause. Nothing is booked, the person is told why, and the proposal is still there — the same
/// proposal books exactly once when the automation is back on.
#[tokio::test]
async fn approving_a_proposal_of_a_paused_automation_is_refused_and_books_nothing_hub2650() {
    let rt = approvals_runtime().await;
    let (flow_id, approval) = parked_proposal(&rt).await;
    set_enabled(&rt, &flow_id, false).await;

    let err = rt
        .decide_flow_approval(&approval.id, true, OWNER, "")
        .await
        .expect_err("a paused automation's proposal must not run");

    assert_eq!(code_of(&err), Some("flow.disabled"), "{err}");
    assert!(
        bookings(&rt).await.is_empty(),
        "approving a paused automation's proposal must not book"
    );
    let row = rt.get_flow_approval(&approval.id).await.unwrap();
    assert_eq!(
        row.status,
        approvals::STATUS_PENDING,
        "nobody decided it: the proposal stays in the tray"
    );
    assert!(row.decided_by.is_empty(), "{row:?}");
    assert!(row.error.is_empty(), "nothing broke, nothing ran: {row:?}");
    assert_eq!(
        run_status(&rt, &flow_id).await,
        store::STATUS_WAITING_APPROVAL,
        "the run still waits for the answer"
    );

    // The positive twin: back on, the very same proposal books — once.
    set_enabled(&rt, &flow_id, true).await;
    let decided = rt
        .decide_flow_approval(&approval.id, true, OWNER, "")
        .await
        .unwrap();
    assert_eq!(decided.status, approvals::STATUS_APPROVED);
    assert_eq!(bookings(&rt).await, vec!["Marta, Tuesday 10:00"]);
}

/// The pause lands while the approval is already running its (slow) command. The pause committed
/// first, so the decision — written in the command's own transaction — must not commit: the
/// booking is rolled back with it and the proposal stays pending.
#[tokio::test]
async fn a_pause_that_lands_while_the_approval_runs_its_command_books_nothing_hub2650() {
    let rt = approvals_runtime().await;
    let (flow_id, approval) = parked_proposal(&rt).await;

    let (decided, ()) = tokio::join!(
        rt.decide_flow_approval(&approval.id, true, OWNER, ""),
        async {
            tokio::time::sleep(Duration::from_millis(300)).await;
            set_enabled(&rt, &flow_id, false).await;
        },
    );

    let err = decided.expect_err("the pause committed before the approval did");
    assert_eq!(code_of(&err), Some("flow.disabled"), "{err}");
    assert!(
        bookings(&rt).await.is_empty(),
        "a booking the pause overtook is rolled back"
    );
    let row = rt.get_flow_approval(&approval.id).await.unwrap();
    assert_eq!(row.status, approvals::STATUS_PENDING, "{row:?}");
    assert!(row.error.is_empty(), "{row:?}");
    assert_eq!(
        run_status(&rt, &flow_id).await,
        store::STATUS_WAITING_APPROVAL
    );
}

/// The same guard covers a DELETION that lands while the approval runs its command: the deletion
/// committed first, so nothing may be booked and nobody decided the proposal (HUB-F88 keeps it in
/// the tray until it is rejected or expires).
#[tokio::test]
async fn a_deletion_that_lands_while_the_approval_runs_its_command_books_nothing_hub2650() {
    let rt = approvals_runtime().await;
    let (flow_id, approval) = parked_proposal(&rt).await;

    let (decided, ()) = tokio::join!(
        rt.decide_flow_approval(&approval.id, true, OWNER, ""),
        async {
            tokio::time::sleep(Duration::from_millis(300)).await;
            rt.delete_flow(&flow_id, OWNER).await.unwrap();
        },
    );

    decided.expect_err("the deletion committed before the approval did");
    assert!(
        bookings(&rt).await.is_empty(),
        "a booking the deletion overtook is rolled back"
    );
    let row = rt.get_flow_approval(&approval.id).await.unwrap();
    assert_eq!(row.status, approvals::STATUS_PENDING, "{row:?}");
}

// ── a message in the outbox ───────────────────────────────────────────────────────────────────

/// The `crm` fixture with one customer, and a transport that records instead of sending.
async fn notify_runtime() -> (Runtime, MockTransport) {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("crm")).await.unwrap();
    let transport = MockTransport::new();
    rt.set_notify_transport(std::sync::Arc::new(transport.clone()));
    let mut p = Params::new();
    p.insert("hub".into(), json!(HUB));
    p.insert("phone".into(), json!(PHONE));
    rt.db_for_test()
        .execute(
            "INSERT INTO crm_customer (id, hub_id, email, phone) \
             VALUES ('c-1', :hub, 'marta@example.com', :phone)",
            &p,
        )
        .await
        .unwrap();
    (rt, transport)
}

/// An automation that writes a WhatsApp to the customer, with both grants, run once: its message
/// is in the queue and has not gone out yet.
async fn queued_reminder(rt: &Runtime, transport: &MockTransport) -> String {
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Reminder".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [{
                        "id": "remind",
                        "kind": "notify",
                        "channel": "whatsapp",
                        "to": { "query": "crm.customer.get",
                                "params": { "id": "input.customer_id" }, "field": "phone" },
                        "template": "appointment_reminder",
                        "vars": { "text": "Te esperamos el {{input.when}}" }
                    }]
                }),
            },
            OWNER,
        )
        .await
        .unwrap()
        .id;
    rt.replace_flow_grants(
        &flow_id,
        &[
            GrantSpec::pair(GrantKind::Notify, "whatsapp"),
            GrantSpec::pair(GrantKind::RecipientQuery, "crm.customer.get#phone"),
        ],
        OWNER,
    )
    .await
    .unwrap();
    rt.start_flow_run(
        &flow_id,
        &json!({ "customer_id": "c-1", "when": "martes" }),
        OWNER,
    )
    .await
    .unwrap();
    rt.process_flows().await.unwrap();
    let queued = queued_notifications(rt).await;
    assert_eq!(queued.len(), 1, "the message is in the queue");
    assert_eq!(queued[0]["status"], json!("pending"));
    assert!(transport.sent().is_empty(), "nothing has left yet");
    flow_id
}

async fn queued_notifications(rt: &Runtime) -> Vec<Value> {
    rows(
        rt,
        "SELECT id, status, attempts, failure_kind, last_error, payload FROM _event_outbox \
         WHERE event_name LIKE '%.reminder.due' ORDER BY created_at",
    )
    .await
}

/// The other headline: the message was queued, then the owner paused the automation. It does not
/// go out; it lands in «Eventos caídos» on the first pass saying why, with the recipient kept so a
/// hand resend has somebody to write to. Turning the automation back on does not send it by
/// itself; resending it from «Eventos caídos» does — once.
#[tokio::test]
async fn a_queued_message_of_a_paused_automation_is_not_sent_hub2650() {
    let (rt, transport) = notify_runtime().await;
    let flow_id = queued_reminder(&rt, &transport).await;

    set_enabled(&rt, &flow_id, false).await;
    rt.drain_outbox().await.unwrap();

    assert!(
        transport.sent().is_empty(),
        "a paused automation's queued message must not go out"
    );
    let queued = queued_notifications(&rt).await;
    assert_eq!(
        queued[0]["status"],
        json!("dead"),
        "it lands in «Eventos caídos» at once, no ladder: {:?}",
        queued[0]
    );
    assert_eq!(queued[0]["attempts"], json!(0), "{:?}", queued[0]);
    assert!(
        queued[0]["last_error"]
            .as_str()
            .unwrap_or_default()
            .contains("paused"),
        "the queue says why it did not go: {}",
        queued[0]["last_error"]
    );
    assert!(
        queued[0]["payload"]
            .as_str()
            .unwrap_or_default()
            .contains(PHONE),
        "the recipient is kept: a resend by hand needs someone to write to"
    );

    // Back on: nothing goes out by itself.
    set_enabled(&rt, &flow_id, true).await;
    rt.drain_outbox().await.unwrap();
    assert!(
        transport.sent().is_empty(),
        "turning it back on does not send what was held during the pause"
    );

    // Resent by hand from «Eventos caídos»: it goes, once.
    let id = queued[0]["id"].as_str().unwrap().to_string();
    assert!(matches!(
        rt.retry_dead_event(&id).await.unwrap(),
        RetryOutcome::Requeued
    ));
    rt.drain_outbox().await.unwrap();
    assert_eq!(
        transport.sent().len(),
        1,
        "the resend goes out exactly once"
    );
}

/// A resend by hand while the automation is STILL paused does not get the message out either: the
/// door is read at every attempt, not only at the first.
#[tokio::test]
async fn resending_by_hand_while_still_paused_does_not_send_hub2650() {
    let (rt, transport) = notify_runtime().await;
    let flow_id = queued_reminder(&rt, &transport).await;
    set_enabled(&rt, &flow_id, false).await;
    rt.drain_outbox().await.unwrap();
    let id = queued_notifications(&rt).await[0]["id"]
        .as_str()
        .unwrap()
        .to_string();

    assert!(matches!(
        rt.retry_dead_event(&id).await.unwrap(),
        RetryOutcome::Requeued
    ));
    rt.drain_outbox().await.unwrap();

    assert!(transport.sent().is_empty(), "still paused, still not sent");
    assert_eq!(queued_notifications(&rt).await[0]["status"], json!("dead"));
}
