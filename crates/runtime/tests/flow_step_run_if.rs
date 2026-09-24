//! **A step that runs only when it applies** (hub#2066) — the `run_if` guard.
//!
//! The engine is linear, and a `condition` that does not match ENDS the run. That is the right
//! answer for «carry on only if…», and the wrong one for «do this ONE thing only if…»: a document
//! could not say «tell the customer we will call her back, but only when the assistant failed»,
//! because the guard that skipped the apology also ended the run before the confirmation.
//!
//! > A customer writes «I want an appointment tomorrow» on WhatsApp and is told «one moment». The
//! > assistant's quota is spent and the `ai` step fails. The run stops there. **She never hears
//! > another word** (whatsapp_inbox#122).
//!
//! `run_if` is the step-level guard GitHub Actions calls `if:` and Power Automate calls «run after:
//! has failed»: when it does not match, THIS step does not run and the run carries on with the
//! next one. The spine stays linear — nothing branches, nothing jumps — so ADR-0283's v1 stands.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::flows::grants::{GrantKind, GrantSpec};
use erplora_runtime::flows::{store, FlowDefinition, IoResult, NewFlow};
use erplora_runtime::{Runtime, RuntimeError};
use serde_json::{json, Value};

const HUB: &str = "hub-step-run-if";
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

async fn flow_with(rt: &Runtime, steps: Value, grants: &[GrantSpec]) -> String {
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Citas".into(),
                enabled: true,
                definition: json!({ "schema_version": 1, "steps": steps }),
            },
            OWNER,
        )
        .await
        .unwrap()
        .id;
    rt.replace_flow_grants(&flow_id, grants, OWNER)
        .await
        .unwrap();
    flow_id
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

fn note(id: &str, text: &str) -> Value {
    json!({ "id": id, "kind": "command", "command": "crm.note.add", "params": { "text": text } })
}

fn failed(step: &str) -> Value {
    json!({ format!("steps.{step}.status"): { "eq": "failed" } })
}

fn not_failed(step: &str) -> Value {
    json!({ format!("steps.{step}.status"): { "neq": "failed" } })
}

/// The shape the WhatsApp recipes need: the assistant step may fail and carry on; the apology runs
/// only when it did; a `condition` ends the run there if it did; the confirmation follows.
fn recipe(assistant: Value) -> Value {
    let mut apology = note("apology", "we will call you back");
    apology["run_if"] = failed("assistant");
    json!([
        note("acknowledge", "one moment"),
        assistant,
        apology,
        { "id": "assistant_answered", "kind": "condition", "when": not_failed("assistant") },
        note("confirm", "confirmed: {{steps.assistant.text}}")
    ])
}

fn ai_step() -> Value {
    json!({ "id": "assistant", "kind": "ai", "prompt": "book it", "policy": "auto",
            "on_error": "continue" })
}

fn grants() -> Vec<GrantSpec> {
    vec![GrantSpec::pair(GrantKind::Command, "crm.note.add")]
}

/// **The case the issue is written about.** The assistant fails OUTSIDE the tick (the server's
/// upstream said «quota exceeded»); the customer still gets a message, and it is the apology, not
/// an empty confirmation.
#[tokio::test]
async fn when_the_assistant_fails_the_customer_gets_the_fallback_and_nothing_else() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, recipe(ai_step()), &grants()).await;
    rt.start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    let pending = rt.process_flows().await.unwrap().pending_io;
    assert_eq!(pending.len(), 1, "the assistant turn left the lock");

    rt.complete_flow_io(
        pending[0].run_id(),
        pending[0].step_id(),
        IoResult::Failed("assistant.quota_exceeded: quota exceeded".into()),
    )
    .await
    .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(
        notes(&rt).await,
        vec!["one moment".to_string(), "we will call you back".to_string()],
        "she was told something after «one moment», and it was not an empty confirmation"
    );
    let run = run_of(&rt, &flow_id).await;
    assert_eq!(
        run.status,
        store::STATUS_DONE,
        "the document said what to do about the failure, and did it"
    );
    let steps = rt.get_flow_run(&run.id).await.unwrap().1;
    let assistant = steps.iter().find(|s| s.step_id == "assistant").unwrap();
    assert_eq!(
        assistant.status, "failed",
        "the assistant step still FAILED in the history: the owner reads why"
    );
    assert!(
        steps.iter().any(|s| s.step_id == "apology" && s.status == "done"),
        "…and the history shows the customer was told: {steps:?}"
    );
}

/// The other half, and the one a guard that always fires would break: when the assistant answers,
/// the apology does NOT run, and the run carries on to the confirmation instead of ending.
#[tokio::test]
async fn when_the_assistant_answers_the_fallback_is_skipped_and_the_run_carries_on() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, recipe(ai_step()), &grants()).await;
    rt.start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    let pending = rt.process_flows().await.unwrap().pending_io;
    rt.complete_flow_io(
        pending[0].run_id(),
        pending[0].step_id(),
        IoResult::Done(json!({ "text": "Tuesday at 10:00" })),
    )
    .await
    .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(
        notes(&rt).await,
        vec![
            "confirmed: Tuesday at 10:00".to_string(),
            "one moment".to_string()
        ],
        "no apology when nothing failed, and the step after the skipped one still ran"
    );
    let run = run_of(&rt, &flow_id).await;
    assert_eq!(run.status, store::STATUS_DONE);
    let steps = rt.get_flow_run(&run.id).await.unwrap().1;
    assert!(
        !steps.iter().any(|s| s.step_id == "apology"),
        "a skipped step did not run, so the history does not list it as something the hub did: \
         {steps:?}"
    );
}

/// A skipped step still answers `steps.<id>`: a later step can ask whether it ran, instead of
/// reading a null it cannot tell apart from «this step never existed».
#[tokio::test]
async fn a_skipped_step_says_so_to_the_steps_after_it() {
    let rt = runtime().await;
    let mut skipped = note("maybe", "never written");
    skipped["run_if"] = json!({ "input.vip": { "eq": true } });
    let flow_id = flow_with(
        &rt,
        json!([skipped, note("after", "skipped={{steps.maybe.skipped}}")]),
        &grants(),
    )
    .await;
    rt.start_flow_run(&flow_id, &json!({ "vip": false }), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(notes(&rt).await, vec!["skipped=true".to_string()]);
    assert_eq!(run_of(&rt, &flow_id).await.status, store::STATUS_DONE);
}

/// A guard that matches runs the step exactly as if it had no guard.
#[tokio::test]
async fn a_guard_that_matches_runs_the_step() {
    let rt = runtime().await;
    let mut guarded = note("maybe", "written");
    guarded["run_if"] = json!({ "input.vip": { "eq": true } });
    let flow_id = flow_with(&rt, json!([guarded]), &grants()).await;
    rt.start_flow_run(&flow_id, &json!({ "vip": true }), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(notes(&rt).await, vec!["written".to_string()]);
}

// ── what is refused at SAVE time ─────────────────────────────────────────────────────────────────

fn parse(steps: Value) -> Result<FlowDefinition, String> {
    // The CODE is the contract (ADR-0055); the message only rides along for the failure output.
    FlowDefinition::parse(&json!({ "schema_version": 1, "steps": steps })).map_err(|e| match e {
        RuntimeError::Domain { code, message } => format!("{code}: {message}"),
        other => format!("{other}"),
    })
}

/// Every kind that DOES something may carry a guard.
#[test]
fn every_kind_that_does_something_accepts_a_guard() {
    let guard = json!({ "input.x": { "eq": 1 } });
    for step in [
        json!({ "id": "s", "kind": "command", "command": "crm.note.add" }),
        json!({ "id": "s", "kind": "query", "query": "crm.note.list" }),
        json!({ "id": "s", "kind": "delay", "seconds": 60 }),
        json!({ "id": "s", "kind": "http", "url": "https://x.example/y" }),
        json!({ "id": "s", "kind": "ai", "prompt": "book it" }),
        json!({ "id": "s", "kind": "notify", "channel": "email", "template": "t",
                "to": { "query": "crm.customer.get", "field": "email" } }),
        json!({ "id": "s", "kind": "approval", "title": "¿Seguimos?" }),
    ] {
        let kind = step["kind"].as_str().unwrap().to_string();
        let mut step = step;
        step["run_if"] = guard.clone();
        let def = parse(json!([step])).unwrap_or_else(|e| panic!("`{kind}` may be guarded: {e}"));
        assert!(def.steps[0].run_if.is_some(), "`{kind}` kept its guard");
    }
}

/// A `condition` IS a guard; a second one on it would be two ways to say one thing, and which of
/// them stops the run would be a question nobody should have to ask.
#[test]
fn a_condition_refuses_a_guard_of_its_own() {
    let err = parse(json!([{ "id": "c", "kind": "condition", "when": {},
                             "run_if": { "input.x": { "eq": 1 } } }]))
    .expect_err("a condition must refuse `run_if`");
    assert!(err.contains("unknown key `run_if`"), "{err}");
}

/// A guard is read at save time like any condition: a malformed one is refused there, not
/// discovered at 3 AM.
#[test]
fn a_malformed_guard_is_refused_at_save_time() {
    let err = parse(json!([{ "id": "s", "kind": "command", "command": "crm.note.add",
                             "run_if": { "input.x": { "near": 1 } } }]))
    .expect_err("an unknown operator in a guard must be refused");
    assert!(
        err.starts_with("flow.unknown_operator:"),
        "the same code a `condition` gets for the same mistake: {err}"
    );

    let err = parse(json!([{ "id": "s", "kind": "command", "command": "crm.note.add",
                             "run_if": "input.x" }]))
    .expect_err("a guard is an object of clauses");
    assert!(err.contains("flow.invalid_definition"), "{err}");
}

/// A guard is a comparison, and a comparison against a credential is how it gets guessed byte by
/// byte — refused on EVERY kind, `http` included: the `http` step may read a secret in its call,
/// never in whether to make it.
#[test]
fn a_guard_can_never_read_a_flow_secret() {
    for step in [
        json!({ "id": "s", "kind": "command", "command": "crm.note.add" }),
        json!({ "id": "s", "kind": "http", "url": "https://x.example/y" }),
    ] {
        let kind = step["kind"].as_str().unwrap().to_string();
        let mut step = step;
        step["run_if"] = json!({ "input.x": { "eq": "{{secret.API_KEY}}" } });
        let err = parse(json!([step]))
            .expect_err(&format!("a `{kind}` guard naming a secret must be refused"));
        assert!(err.contains("flow.secret_not_available"), "{kind}: {err}");
    }
}
