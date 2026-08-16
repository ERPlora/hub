//! **The kernel half of the agent step** (hub#665 — ADR-0283 K5/D3): what the runtime owes the
//! server-side agent runner, tested without a single line of network code.
//!
//! The runner itself lives in `crates/server` (it needs `cloud-client`, and the runtime has no
//! network by design). What lives HERE is everything the runner is not allowed to decide for
//! itself, and it is exactly the part that is dangerous:
//!
//! - an `ai` step **parks** its run outside the tick's lock (`PendingIo::Ai`) instead of being
//!   executed inside it — a 60 s LLM turn under the global lock freezes every till in the hub;
//! - a command the model proposes under `policy:"manual"` becomes a **row waiting for a person**,
//!   and the business database is not touched until that person says yes;
//! - approving executes **exactly** what was proposed, re-checking the grant at that moment,
//!   and **never re-enters the LLM**;
//! - rejecting executes nothing at all.
//!
//! The default is `manual` (ADR-0283 D3). The whole point of this issue is that a hub can act
//! alone at 3 AM; the whole point of the approval is that "act alone" stops at the writes its
//! owner did not pre-authorise.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::flows::approvals;
use erplora_runtime::flows::executor::PendingIo;
use erplora_runtime::flows::grants::GrantKind;
use erplora_runtime::flows::{store, NewFlow};
use erplora_runtime::{Runtime, RuntimeError};
use serde_json::{json, Value};

const HUB: &str = "hub-agent-step";

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
    rt.install_from_dir(&fixture("crm")).await.unwrap();
    rt
}

/// A one-step flow whose only step is the agent turn.
fn agent_definition(policy: &str) -> Value {
    json!({
        "schema_version": 1,
        "triggers": [{ "kind": "manual" }],
        "steps": [{
            "id": "agent",
            "kind": "ai",
            "prompt": "Book whatever {{input.who}} asked for",
            "tools": { "queries": [], "commands": ["crm.note.add"] },
            "policy": policy
        }]
    })
}

async fn flow_with(rt: &Runtime, definition: Value) -> String {
    rt.create_flow(
        &NewFlow {
            name: "Agent".into(),
            enabled: true,
            definition,
        },
        "hub_user:owner",
    )
    .await
    .unwrap()
    .id
}

async fn grant(rt: &Runtime, flow_id: &str, pairs: &[(GrantKind, String)]) {
    rt.replace_flow_grants(flow_id, pairs, "hub_user:owner")
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
    rt.list_flow_runs(flow_id, 10, None).await.unwrap().remove(0)
}

/// Starts the flow and ticks once, returning the `PendingIo` the tick handed back.
async fn start_and_tick(rt: &Runtime, flow_id: &str, input: Value) -> Vec<PendingIo> {
    rt.start_flow_run(flow_id, &input, "hub_user:owner")
        .await
        .unwrap();
    rt.process_flows().await.unwrap().pending_io
}

// ── the step parks; it does not run inside the lock ────────────────────────────────────────────

/// The keystone of the claim → I/O → complete contract. Before hub#665 an `ai` step was refused at
/// save time; now it saves, and what the tick does with it is **hand it over**, not perform it.
/// A run in `waiting_io` is deliberately not claimable, so the same turn is never started twice by
/// the next tick a second later.
#[tokio::test]
async fn an_ai_step_is_handed_to_the_server_instead_of_being_run_inside_the_tick() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, agent_definition("manual")).await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
    )
    .await;

    let pending = start_and_tick(&rt, &flow_id, json!({ "who": "Marta" })).await;

    let run = run_of(&rt, &flow_id).await;
    assert_eq!(
        pending,
        vec![PendingIo::Ai {
            run_id: run.id.clone(),
            step_id: "agent".to_string()
        }],
        "the tick prepares the turn and returns it; the server performs it outside the lock"
    );
    assert_eq!(
        run.status,
        store::STATUS_RUNNING,
        "the run keeps its CLAIM while the turn is in flight (hub#662's seam): the lease is what \
         makes the next tick skip it, so the turn starts exactly once"
    );

    // And a second tick must not hand the same turn out again.
    assert!(
        rt.process_flows().await.unwrap().pending_io.is_empty(),
        "a parked run is not re-offered every second"
    );
}

/// What the server is handed is the step ALREADY RESOLVED against the run: the prompt with its
/// templates filled in, the tools the document declared, and the policy. The runner must not have
/// to re-read the flow document to know what it was asked to do.
#[tokio::test]
async fn the_request_carries_the_resolved_prompt_the_tools_and_the_policy() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, agent_definition("manual")).await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
    )
    .await;
    start_and_tick(&rt, &flow_id, json!({ "who": "Marta" })).await;
    let run = run_of(&rt, &flow_id).await;

    let request = rt.load_flow_ai_request(&run.id, "agent").await.unwrap();
    assert_eq!(
        request.prompt, "Book whatever Marta asked for",
        "the prompt reaches the model already resolved against the run"
    );
    assert_eq!(request.commands, vec!["crm.note.add".to_string()]);
    assert!(request.queries.is_empty());
    assert_eq!(request.step_id, "agent");
    assert_eq!(request.flow_id, flow_id);
    assert_eq!(
        request.max_iters, 6,
        "the default the document did not state"
    );
    assert!(
        !request.policy.is_auto(),
        "`manual` is the DEFAULT and this document asked for it explicitly (ADR-0283 D3)"
    );
}

// ── manual: the write waits for a person ──────────────────────────────────────────────────────

/// The heart of the issue. A command proposed under `policy:"manual"` writes ONE row — the
/// approval — and nothing else. The business table is untouched, and it stays untouched however
/// many ticks go by.
#[tokio::test]
async fn a_manual_proposal_creates_an_approval_and_writes_nothing_to_the_business_database() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, agent_definition("manual")).await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
    )
    .await;
    start_and_tick(&rt, &flow_id, json!({ "who": "Marta" })).await;
    let run = run_of(&rt, &flow_id).await;

    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: "crm.note.add".into(),
            payload: json!({ "text": "3 AM booking" }),
            reason: "the assistant proposed this".into(),
            partial_output: json!({ "text": "I will book it" }),
        })
        .await
        .unwrap();

    assert_eq!(approval.status, approvals::STATUS_PENDING);
    assert!(notes(&rt).await.is_empty(), "nothing was written yet");
    assert_eq!(
        run_of(&rt, &flow_id).await.status,
        store::STATUS_WAITING_APPROVAL,
        "the run waits for a person, and the tick leaves it alone"
    );

    // Ticking does not smuggle it through: the run is not claimable while it waits.
    rt.process_flows().await.unwrap();
    rt.process_flows().await.unwrap();
    assert!(
        notes(&rt).await.is_empty(),
        "no amount of ticking executes an unapproved write"
    );
}

/// Approving executes EXACTLY what was proposed and the run moves on. The command runs under
/// `Origin::Automation` — the same door the kernel's own `command` steps use — so it is the flow's
/// grant that opens it, and the row it writes is attributed to the flow.
#[tokio::test]
async fn approving_executes_exactly_the_proposed_command_and_the_run_continues() {
    let rt = runtime().await;
    let flow_id = flow_with(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [
                { "id": "agent", "kind": "ai", "prompt": "book it",
                  "tools": { "commands": ["crm.note.add"] } },
                { "id": "after", "kind": "command", "command": "crm.note.add",
                  "params": { "text": "zzz follow-up" } }
            ]
        }),
    )
    .await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
    )
    .await;
    start_and_tick(&rt, &flow_id, json!({})).await;
    let run = run_of(&rt, &flow_id).await;
    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: "crm.note.add".into(),
            payload: json!({ "text": "aaa the proposed note" }),
            reason: String::new(),
            partial_output: json!({}),
        })
        .await
        .unwrap();

    let decided = rt
        .decide_flow_approval(&approval.id, true, "hub_user:owner", "")
        .await
        .unwrap();

    assert_eq!(decided.status, approvals::STATUS_APPROVED);
    assert_eq!(
        decided.decided_by, "hub_user:owner",
        "who decided comes from the session, never from the body"
    );
    assert_eq!(
        notes(&rt).await,
        vec!["aaa the proposed note"],
        "exactly the proposed command, with exactly the proposed payload"
    );

    // The run resumes where it was: the tick takes it from the step after the agent's.
    rt.process_flows().await.unwrap();
    assert_eq!(
        notes(&rt).await,
        vec!["aaa the proposed note", "zzz follow-up"],
        "the flow continues after the approval, without re-entering the model"
    );
    assert_eq!(run_of(&rt, &flow_id).await.status, store::STATUS_DONE);
}

/// Rejecting is the other half, and it has to be worth as much as approving: nothing runs, and the
/// run stops rather than continuing as if the write had happened. The steps after an agent step
/// were written believing it acted.
#[tokio::test]
async fn rejecting_executes_nothing_and_stops_the_run() {
    let rt = runtime().await;
    let flow_id = flow_with(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [
                { "id": "agent", "kind": "ai", "prompt": "book it",
                  "tools": { "commands": ["crm.note.add"] } },
                { "id": "after", "kind": "command", "command": "crm.note.add",
                  "params": { "text": "follow-up" } }
            ]
        }),
    )
    .await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
    )
    .await;
    start_and_tick(&rt, &flow_id, json!({})).await;
    let run = run_of(&rt, &flow_id).await;
    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: "crm.note.add".into(),
            payload: json!({ "text": "the proposed note" }),
            reason: String::new(),
            partial_output: json!({}),
        })
        .await
        .unwrap();

    let decided = rt
        .decide_flow_approval(&approval.id, false, "hub_user:owner", "")
        .await
        .unwrap();

    assert_eq!(decided.status, approvals::STATUS_REJECTED);
    assert!(notes(&rt).await.is_empty(), "a rejection writes nothing");
    rt.process_flows().await.unwrap();
    assert!(
        notes(&rt).await.is_empty(),
        "and the steps written on the assumption it acted do not run either"
    );
    assert_eq!(
        run_of(&rt, &flow_id).await.status,
        store::STATUS_CANCELLED,
        "a person stopped this run; that is a cancellation, not a failure of the flow"
    );
}

/// The window this closes: the model proposes at 3 AM, the owner reads the tray at 9 AM, and in
/// between somebody revoked the grant. The proposal is not a standing authorisation — the gate is
/// re-read **at the moment of approving**, exactly as it is re-read at every step of a run.
#[tokio::test]
async fn a_grant_revoked_between_the_proposal_and_the_approval_refuses_the_approval() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, agent_definition("manual")).await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
    )
    .await;
    start_and_tick(&rt, &flow_id, json!({ "who": "Marta" })).await;
    let run = run_of(&rt, &flow_id).await;
    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: "crm.note.add".into(),
            payload: json!({ "text": "the proposed note" }),
            reason: String::new(),
            partial_output: json!({}),
        })
        .await
        .unwrap();

    // The owner changes their mind about what this flow may do at all.
    grant(&rt, &flow_id, &[]).await;

    let err = rt
        .decide_flow_approval(&approval.id, true, "hub_user:owner", "")
        .await
        .expect_err("an approval is not a stored permission that outlives its grant");
    assert!(
        format!("{err}").contains("crm.note.add"),
        "the refusal names the command: {err}"
    );
    assert!(notes(&rt).await.is_empty(), "nothing ran");
    // The row stays PENDING on purpose: re-granting and approving again is a working remedy,
    // whereas a burnt approval would force the owner to re-run the whole flow.
    assert_eq!(
        rt.get_flow_approval(&approval.id).await.unwrap().status,
        approvals::STATUS_PENDING
    );
}

/// An approval is decided once. A double-click on the tray, or two admins looking at the same
/// screen, must not execute the same booking twice.
#[tokio::test]
async fn an_approval_is_decided_once() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, agent_definition("manual")).await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
    )
    .await;
    start_and_tick(&rt, &flow_id, json!({ "who": "Marta" })).await;
    let run = run_of(&rt, &flow_id).await;
    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: "crm.note.add".into(),
            payload: json!({ "text": "one booking" }),
            reason: String::new(),
            partial_output: json!({}),
        })
        .await
        .unwrap();

    rt.decide_flow_approval(&approval.id, true, "hub_user:owner", "")
        .await
        .unwrap();
    let err = rt
        .decide_flow_approval(&approval.id, true, "hub_user:owner", "")
        .await
        .expect_err("the second press must not book a second appointment");
    // The stable CODE, not the prose: the module `flows` shows a different message for «somebody
    // already did this» than for a real error, and it programs against the code (flows.md §13.8).
    assert!(
        matches!(&err, RuntimeError::Domain { code, .. }
                 if code == approvals::ERR_APPROVAL_ALREADY_DECIDED),
        "{err}"
    );
    assert_eq!(notes(&rt).await, vec!["one booking"]);
}

// ── grants over the tools ─────────────────────────────────────────────────────────────────────

/// A `query` grant becomes creatable with this issue, because otherwise "the tools are intersected
/// with the grants" would be a sentence with nothing behind it for reads. And it is a real gate,
/// not a label: the runtime refuses a query the flow was not granted even if somebody calls it
/// directly.
#[tokio::test]
async fn a_flow_may_only_run_the_queries_it_was_granted() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, agent_definition("manual")).await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Query, "crm.note.list".into())],
    )
    .await;
    start_and_tick(&rt, &flow_id, json!({ "who": "Marta" })).await;
    let run = run_of(&rt, &flow_id).await;

    rt.execute_flow_query(&flow_id, &run.id, "crm.note.list", &Params::new())
        .await
        .expect("the granted query runs");

    let err = rt
        .execute_flow_query(&flow_id, &run.id, "crm.note.recent", &Params::new())
        .await
        .expect_err("a sibling query of the same module is a different question with the same answer");
    assert!(format!("{err}").contains("crm.note.recent"), "{err}");
}

/// The tenant is never negotiable, and neither is the flow: an approval belongs to one run of one
/// flow of one hub, and asking for it from anywhere else is a `404`, not a decision.
#[tokio::test]
async fn an_approval_of_another_hub_is_not_visible_here() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, agent_definition("manual")).await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
    )
    .await;
    start_and_tick(&rt, &flow_id, json!({ "who": "Marta" })).await;
    let run = run_of(&rt, &flow_id).await;
    let approval = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run.id.clone(),
            flow_id: flow_id.clone(),
            step_id: "agent".into(),
            command: "crm.note.add".into(),
            payload: json!({}),
            reason: String::new(),
            partial_output: json!({}),
        })
        .await
        .unwrap();

    let neighbour = {
        let db = fresh_db().await;
        let rt = Runtime::with_hub_id(Box::new(db), "hub-somebody-else");
        rt.ensure_system_tables().await.unwrap();
        rt
    };
    assert!(
        neighbour.get_flow_approval(&approval.id).await.is_err(),
        "a live neighbouring hub cannot see this approval"
    );
    assert!(
        neighbour
            .decide_flow_approval(&approval.id, true, "hub_user:intruder", "")
            .await
            .is_err(),
        "nor decide it"
    );
}

/// The tray is the screen a person reads at 9 AM: it lists what is waiting, newest first, with the
/// command and the payload that will run — not an opaque id.
#[tokio::test]
async fn the_tray_lists_what_is_waiting_with_the_command_and_its_payload() {
    let rt = runtime().await;
    let flow_id = flow_with(&rt, agent_definition("manual")).await;
    grant(
        &rt,
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
    )
    .await;
    start_and_tick(&rt, &flow_id, json!({ "who": "Marta" })).await;
    let run = run_of(&rt, &flow_id).await;
    rt.request_flow_approval(&approvals::NewApproval {
        run_id: run.id.clone(),
        flow_id: flow_id.clone(),
        step_id: "agent".into(),
        command: "crm.note.add".into(),
        payload: json!({ "text": "book Marta at 10:00" }),
        reason: "proposed by the assistant".into(),
        partial_output: json!({}),
    })
    .await
    .unwrap();

    let pending = rt
        .list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
        .await
        .unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].command, "crm.note.add");
    assert_eq!(pending[0].payload["text"], json!("book Marta at 10:00"));
    assert_eq!(pending[0].flow_id, flow_id);
    assert_eq!(pending[0].run_id, run.id);
}
