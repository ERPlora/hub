//! **What a failed step costs the RUN** (hub#1635) — the `on_error` primitive.
//!
//! Until now a step that failed ended the run, full stop: `on_error` was hard-wired to `stop` and
//! said so in three comments and in the schema. That is the right DEFAULT and it stays the default
//! — a linear document whose write did not happen has no business carrying on as if it had. What
//! was missing is the OPT-IN, and its absence has a cost somebody pays:
//!
//! > The salon approves at nine in the morning the appointment a customer asked for at three, and
//! > the booking fails — somebody else took the slot in between. The salon sees the failure in its
//! > tray. **The customer sees nothing**, because the step that tells her is the step after the one
//! > that broke, and the run died before it.
//!
//! So a step may now say `on_error: "continue"`: it still FAILS — the step row is `failed` and the
//! reason is recorded — and the run carries on to the next step with `steps.<id>.status ==
//! "failed"` and `steps.<id>.error` holding the reason. That is exactly the shape `on_reject:
//! "continue"` already has (hub#1622): the turn the step had parked is handed over, plus a `status`
//! the step written after it reads with `{{steps.<id>.status}}`.
//!
//! 🔴 **Continuing is not retrying.** The vocabulary is closed at `stop | continue`: there is no
//! `retry`, and there will not be one here. ADR-0283 §1 is not being reversed — re-running a
//! business command on the kernel's own initiative is how a sale gets charged twice. Carrying on
//! to the NEXT step runs nothing again; it lets the document say what to do about a failure it
//! already knows happened.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::flows::approvals;
use erplora_runtime::flows::grants::{GrantKind, GrantSpec};
use erplora_runtime::flows::{store, IoResult, NewFlow};
use erplora_runtime::Runtime;
use serde_json::{json, Value};

const HUB: &str = "hub-step-failure";
const OWNER: &str = "hub_user:owner";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_flows")
        .join(name)
}

async fn runtime() -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("crm")).await.unwrap();
    rt
}

async fn flow_with(rt: &Runtime, definition: Value) -> String {
    rt.create_flow(
        &NewFlow {
            name: "Citas".into(),
            enabled: true,
            definition,
        },
        OWNER,
    )
    .await
    .unwrap()
    .id
}

async fn grant(rt: &Runtime, flow_id: &str, commands: &[&str]) {
    let pairs: Vec<GrantSpec> = commands
        .iter()
        .map(|c| GrantSpec::pair(GrantKind::Command, *c))
        .collect();
    rt.replace_flow_grants(flow_id, &pairs, OWNER)
        .await
        .unwrap();
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
    rt.list_flow_runs(flow_id, 10, None)
        .await
        .unwrap()
        .remove(0)
}

/// `crm.receipt.stamp` binds `:business_tax_id` and this hub has no fiscal identity configured, so
/// the command fails at EXECUTION time — the honest shape of the bug, and not a payload the runner
/// would have refused before ever proposing it.
fn breaking_step(id: &str, on_error: Option<&str>) -> Value {
    let mut step =
        json!({ "id": id, "kind": "command", "command": "crm.receipt.stamp", "params": {} });
    if let Some(policy) = on_error {
        step.as_object_mut()
            .unwrap()
            .insert("on_error".into(), json!(policy));
    }
    step
}

/// The step that tells the person who was waiting. It reads how the step before it ended, which is
/// the whole contract: a message that cannot say WHY is not worth sending.
fn telling_step(about: &str) -> Value {
    json!({
        "id": "tell", "kind": "command", "command": "crm.note.add",
        "params": { "text": format!("no pudo ser ({{{{steps.{about}.status}}}}): {{{{steps.{about}.error}}}}") }
    })
}

// ── the default did not move ───────────────────────────────────────────────────────────────────

/// The regression guard for what `on_error` must NOT change. A document that says nothing about
/// failure behaves exactly as it did before this primitive existed: the run fails and the steps
/// after it never run.
#[tokio::test]
async fn a_document_that_says_nothing_about_failure_still_stops_the_run() {
    let rt = runtime().await;
    let flow_id = flow_with(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [breaking_step("book", None), telling_step("book")]
        }),
    )
    .await;
    grant(&rt, &flow_id, &["crm.receipt.stamp", "crm.note.add"]).await;
    rt.start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    let run = run_of(&rt, &flow_id).await;
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("business_tax_id"),
        "{}",
        run.last_error
    );
    assert!(
        notes(&rt).await.is_empty(),
        "the step after the failure never ran — that is the DEFAULT, and it stays"
    );
}

/// The vocabulary is closed, and the value that is deliberately not in it is `retry`. A document
/// asking the kernel to re-run a business command by itself is refused at save time, naming what it
/// may say instead.
#[tokio::test]
async fn a_failure_policy_the_hub_does_not_know_is_refused_at_save_time() {
    let rt = runtime().await;
    let err = rt
        .create_flow(
            &NewFlow {
                name: "Citas".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [breaking_step("book", Some("retry"))]
                }),
            },
            OWNER,
        )
        .await
        .expect_err("`retry` is not a policy this kernel has");
    let text = format!("{err}");
    assert!(
        text.contains("stop") && text.contains("continue"),
        "the refusal names the vocabulary: {text}"
    );
}

// ── the opt-in ────────────────────────────────────────────────────────────────────────────────

/// The primitive itself: the step still fails, and the run carries on with the reason readable by
/// the step written after it.
#[tokio::test]
async fn a_step_that_says_continue_lets_the_run_carry_on_and_says_why() {
    let rt = runtime().await;
    let flow_id = flow_with(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [breaking_step("book", Some("continue")), telling_step("book")]
        }),
    )
    .await;
    grant(&rt, &flow_id, &["crm.receipt.stamp", "crm.note.add"]).await;
    rt.start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    let told = notes(&rt).await;
    assert_eq!(
        told.len(),
        1,
        "the person who was waiting was told: {told:?}"
    );
    assert!(
        told[0].starts_with("no pudo ser (failed):"),
        "the step after it reads `steps.<id>.status`: {}",
        told[0]
    );
    assert!(
        told[0].contains("business_tax_id"),
        "…and the REASON, or the message cannot say what happened: {}",
        told[0]
    );

    let run = run_of(&rt, &flow_id).await;
    assert_eq!(
        run.status,
        store::STATUS_DONE,
        "the run reached its end: continuing is the document's answer, not a failure of it"
    );

    let steps = rt.get_flow_run(&run.id).await.unwrap().1;
    let broken = steps.iter().find(|s| s.step_id == "book").unwrap();
    assert_eq!(
        broken.status, "failed",
        "the STEP still failed — `continue` is about the run, and the history must not lie"
    );
    assert!(broken.error.contains("business_tax_id"), "{}", broken.error);
}

/// The other half of the same seam: a step whose work happens OUTSIDE the tick (`http`, `ai`) fails
/// through `complete_io`, hours or seconds later, and has to obey the same policy. Without this the
/// primitive would cover the cheap half of the kernel and miss the one the customer waits on.
#[tokio::test]
async fn a_step_that_fails_outside_the_tick_obeys_the_same_policy() {
    let rt = runtime().await;
    let flow_id = flow_with(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [
                { "id": "call", "kind": "http", "method": "GET",
                  "url": "https://api.example.com/slots", "on_error": "continue" },
                telling_step("call")
            ]
        }),
    )
    .await;
    grant(&rt, &flow_id, &["crm.note.add"]).await;
    rt.replace_flow_grants(
        &flow_id,
        &[
            GrantSpec::pair(GrantKind::Command, "crm.note.add"),
            GrantSpec::pair(GrantKind::Http, "https://api.example.com/slots"),
        ],
        OWNER,
    )
    .await
    .unwrap();
    rt.start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    let pending = rt.process_flows().await.unwrap().pending_io;
    assert_eq!(pending.len(), 1, "the call left the lock");

    rt.complete_flow_io(
        pending[0].run_id(),
        pending[0].step_id(),
        IoResult::Failed("flow.http_timeout: no answer in 10 s".into()),
    )
    .await
    .unwrap();
    rt.process_flows().await.unwrap();

    let told = notes(&rt).await;
    assert_eq!(
        told.len(),
        1,
        "the run carried on past the dead call: {told:?}"
    );
    assert!(told[0].contains("http_timeout"), "{}", told[0]);
    assert_eq!(run_of(&rt, &flow_id).await.status, store::STATUS_DONE);
}

/// **The case the issue is written about** (hub#1635). The model proposed a booking at three in the
/// morning, the salon approved it at nine, and the command broke in between — somebody else took
/// the slot. Before this, the run died in `decide_flow_approval` and the customer was never told.
///
/// It also proves the halves compose: the turn the `ai` step had PARKED is still there
/// (`steps.<id>.text`), exactly as `on_reject: "continue"` hands it over (hub#1622), with `status`
/// and `error` written over it.
#[tokio::test]
async fn approving_a_proposal_whose_command_breaks_still_reaches_the_person_who_was_waiting() {
    let rt = runtime().await;
    let flow_id = flow_with(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [
                { "id": "agent", "kind": "ai", "prompt": "book what she asked for",
                  "tools": { "commands": ["crm.receipt.stamp"] }, "on_error": "continue" },
                { "id": "tell", "kind": "command", "command": "crm.note.add",
                  "params": { "text": "{{steps.agent.text}} — {{steps.agent.status}}" } }
            ]
        }),
    )
    .await;
    grant(&rt, &flow_id, &["crm.receipt.stamp", "crm.note.add"]).await;
    rt.start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    let run = run_of(&rt, &flow_id).await;

    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: "crm.receipt.stamp".into(),
            payload: json!({}),
            reason: "la clienta pidió cita a las 3".into(),
            partial_output: json!({ "text": "te confirmo la cita" }),
            on_expire: approvals::ExpiryPolicy::Reject,
            on_reject: approvals::RejectPolicy::Cancel,
        })
        .await
        .unwrap();

    // The salon says yes and the command breaks. The tray still learns it failed — that is what
    // the returned error is for — and the RUN is what changes: it carries on.
    rt.decide_flow_approval(&approval.id, true, OWNER, "")
        .await
        .expect_err("the command broke, and the tray must show a failure and not a green tick");

    rt.process_flows().await.unwrap();
    let told = notes(&rt).await;
    assert_eq!(
        told,
        vec!["te confirmo la cita — failed"],
        "the customer is told, and the turn the step had parked is still there"
    );
    assert_eq!(run_of(&rt, &flow_id).await.status, store::STATUS_DONE);
}

/// **Fail CLOSED when the instructions cannot be read.** The policy is answered from the DOCUMENT
/// at the moment the failure lands, so there is a window where the document is gone: the flow is
/// deleted (or rolled back to a version this binary cannot parse) while its request is still in
/// flight. `store::delete` deliberately leaves a run that holds a lease alone, so the answer to
/// «does this run carry on?» is decided right here.
///
/// It must be «no». `continue` is an OPT-IN a document makes; a document nobody can read has not
/// opted into anything, and inventing consent to carry on past a failure — running the steps after
/// it, sending the messages they send — is the one answer a kernel may never guess.
#[tokio::test]
async fn a_failure_whose_document_is_gone_stops_the_run_instead_of_guessing_continue() {
    let rt = runtime().await;
    let flow_id = flow_with(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [
                { "id": "call", "kind": "http", "method": "GET",
                  "url": "https://api.example.com/slots", "on_error": "continue" },
                telling_step("call")
            ]
        }),
    )
    .await;
    rt.replace_flow_grants(
        &flow_id,
        &[
            GrantSpec::pair(GrantKind::Command, "crm.note.add"),
            GrantSpec::pair(GrantKind::Http, "https://api.example.com/slots"),
        ],
        OWNER,
    )
    .await
    .unwrap();
    rt.start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    let pending = rt.process_flows().await.unwrap().pending_io;
    assert_eq!(pending.len(), 1, "the call left the lock");

    // The document disappears while the request is out. The run keeps its lease — `store::delete`
    // leaves an in-flight run to this seam on purpose — so the failure below still lands here.
    rt.delete_flow(&flow_id, OWNER).await.unwrap();

    rt.complete_flow_io(
        pending[0].run_id(),
        pending[0].step_id(),
        IoResult::Failed("flow.http_timeout: no answer in 10 s".into()),
    )
    .await
    .unwrap();

    assert_eq!(
        run_of(&rt, &flow_id).await.status,
        store::STATUS_FAILED,
        "an unreadable document is `stop`, never a guessed `continue`"
    );
    assert!(
        notes(&rt).await.is_empty(),
        "the step after the dead call never ran"
    );
}
