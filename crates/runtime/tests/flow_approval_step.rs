//! **The generic `approval` step** (hub#950 — ADR-0283 §5), the eighth and last kind.
//!
//! The kernel already knew how to stop and wait for a person, but only as a side effect of an `ai`
//! step: the row in `_flow_approvals` was always a WRITE a model proposed, and the only way to ask
//! «shall I carry on?» was to pay for a language model to ask it. This step is the same pause
//! without the model — a question, an answer, and a run that resumes.
//!
//! The shape comes from the market (decision published on the issue, 2026-08-15): the **object**
//! of Power Automate's *Start and wait for an approval* — a row with a life of its own, so a
//! decision hours later still means something — corrected by the **explicit due date** of Business
//! Central, which is the half Power Automate is documented to do badly (the run dies at 30 days and
//! the approval is orphaned in the Action Center with nothing waiting on it).
//!
//! v1 is LINEAR, so the three branches the original contract asked for are **policies of outcome**,
//! not branches — n8n's `Limit Wait Time` rather than Salesforce's approval process:
//!
//! - `approved` → the next step;
//! - `rejected` → `on_reject`: `cancel` (the default, and what a rejection does today) or `continue`;
//! - `expired`  → `on_expire`: `reject` | `cancel` | `continue`, swept by hub#979.
//!
//! With `continue` plus a `condition`, the three branches compose out of frozen primitives — the
//! same move the `query` step of hub#954 made.
use std::path::PathBuf;

use erplora_db::{testutil::TestDb, Params};
use erplora_runtime::flows::approvals::{self, ExpiryPolicy, RejectPolicy};
use erplora_runtime::flows::grants::{GrantKind, GrantSpec};
use erplora_runtime::flows::{store, NewFlow};
use erplora_runtime::hub_users::NewHubUser;
use erplora_runtime::Runtime;
use serde_json::{json, Value};

const HUB: &str = "hub-approval-step";
const OWNER: &str = "hub_user:owner";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_flows")
        .join(name)
}

async fn runtime_on(db: erplora_db::PgAdapter, hub_id: &str) -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("crm")).await.unwrap();
    rt
}

async fn runtime() -> Runtime {
    runtime_on(TestDb::new().await.adapter().await, HUB).await
}

/// «Pide permiso, y solo entonces escribe» — the case the issue is written about, minus the
/// purchase vocabulary the kernel must never learn.
fn definition(approval: Value) -> Value {
    json!({
        "schema_version": 1,
        "steps": [approval, {
            "id": "after", "kind": "command", "command": "crm.note.add",
            "params": { "text": "the write that waited" }
        }]
    })
}

fn ask(extra: Value) -> Value {
    let mut step = json!({
        "id": "approve", "kind": "approval",
        "title": "Aprobar compra a {{input.supplier}}",
        "summary": "Importe {{input.total}} €"
    });
    let map = step.as_object_mut().unwrap();
    for (k, v) in extra.as_object().unwrap() {
        map.insert(k.clone(), v.clone());
    }
    step
}

/// Creates the flow, grants it the write that comes AFTER the approval, and starts one run.
async fn parked(rt: &Runtime, approval: Value) -> (String, String) {
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Compras".into(),
                enabled: true,
                definition: definition(approval),
            },
            OWNER,
        )
        .await
        .unwrap()
        .id;
    rt.replace_flow_grants(
        &flow_id,
        &[GrantSpec::pair(GrantKind::Command, "crm.note.add")],
        OWNER,
    )
    .await
    .unwrap();
    let run_id = rt
        .start_flow_run(
            &flow_id,
            &json!({ "supplier": "Frutas Paco", "total": "812,40" }),
            OWNER,
        )
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    (flow_id, run_id)
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

async fn run_status(rt: &Runtime, run_id: &str) -> String {
    rt.get_flow_run(run_id).await.unwrap().0.status
}

/// What the step left in `steps.<id>` for the steps written after it.
async fn decision_output(rt: &Runtime, run_id: &str) -> Value {
    rt.get_flow_run(run_id)
        .await
        .unwrap()
        .1
        .into_iter()
        .find(|s| s.step_id == "approve")
        .expect("the approval step has a row")
        .output
}

async fn only_pending(rt: &Runtime) -> approvals::Approval {
    let mut tray = rt
        .list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
        .await
        .unwrap();
    assert_eq!(tray.len(), 1, "exactly one question is waiting: {tray:?}");
    tray.remove(0)
}

/// Moves a question's deadline into the past, the way three days of silence would.
async fn age(rt: &Runtime, id: &str) {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_approvals SET expires_at = '2020-01-01T00:00:00+00:00' WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
}

// ── the pause ─────────────────────────────────────────────────────────────────────────────────

/// The whole step in one test: the run stops, the tray carries a question a person can read, and
/// **nothing after it has happened**.
#[tokio::test]
async fn a_flow_stops_on_its_approval_step_and_the_tray_carries_the_question() {
    let rt = runtime().await;
    let (flow_id, run_id) = parked(&rt, ask(json!({}))).await;

    assert_eq!(
        run_status(&rt, &run_id).await,
        store::STATUS_WAITING_APPROVAL,
        "the run leaves the queue; no amount of ticking smuggles the next step through"
    );
    assert!(notes(&rt).await.is_empty(), "the write is what is waiting");

    let question = only_pending(&rt).await;
    assert_eq!(question.kind, approvals::KIND_DECISION);
    assert_eq!(question.flow_id, flow_id);
    assert_eq!(question.run_id, run_id);
    assert_eq!(question.step_id, "approve");
    assert_eq!(
        question.title, "Aprobar compra a Frutas Paco",
        "templated against the run, so what a person reads is about THIS purchase"
    );
    assert_eq!(question.summary, "Importe 812,40 €");
    assert_eq!(
        question.command, "",
        "the step executes nothing: it produces a decision, and the next step does the work"
    );
    assert_eq!(question.on_expire, approvals::ON_EXPIRE_REJECT);
    assert_eq!(question.on_reject, approvals::ON_REJECT_CANCEL);
    assert!(
        question.expires_at.is_some(),
        "a question is never open-ended"
    );

    // And it stays stopped: ticking again neither runs the write nor asks a second time.
    rt.process_flows().await.unwrap();
    assert!(notes(&rt).await.is_empty());
    only_pending(&rt).await;
}

/// **No model, no cost, no non-determinism.** The point of the issue: the pause exists without an
/// `ai` step, so a hub with the assistant switched off can still ask its owner.
#[tokio::test]
async fn the_pause_needs_no_grant_and_no_language_model() {
    let rt = runtime().await;
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Solo preguntar".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [{ "id": "approve", "kind": "approval", "title": "¿Seguimos?" }]
                }),
            },
            OWNER,
        )
        .await
        .unwrap()
        .id;
    // Deliberately no grants at all: asking a person is not reaching for a capability.
    let run_id = rt
        .start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(
        run_status(&rt, &run_id).await,
        store::STATUS_WAITING_APPROVAL
    );
    assert_eq!(only_pending(&rt).await.title, "¿Seguimos?");
}

/// A tick that died between writing the question and parking the run gets its lease reclaimed and
/// re-executes the step. The person must not find the same question twice — the idempotency key is
/// the run and the step, exactly as the issue asks.
#[tokio::test]
async fn a_replayed_step_finds_the_question_it_already_asked_instead_of_asking_twice() {
    let rt = runtime().await;
    let (_, run_id) = parked(&rt, ask(json!({}))).await;
    let first = only_pending(&rt).await;

    // The crash window: the row is written, the run never got parked.
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_runs SET status = 'pending', claim_expires_at = NULL WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(
        only_pending(&rt).await.id,
        first.id,
        "the same question, not a second one nobody would ever close"
    );
    assert_eq!(
        run_status(&rt, &run_id).await,
        store::STATUS_WAITING_APPROVAL
    );
}

/// hub#1623 — **the tray is not a way round the pin.** A `command` proposal waits hours between
/// being written by a model and being executed by a person pressing «approve», and the payload it
/// carries is the one the model wrote. If the grant FIXES part of that payload, the check has to
/// happen on this door too, with the payload that will really run — otherwise the containment holds
/// on the direct path and leaks on the one that goes through a person.
#[tokio::test]
async fn approving_a_proposal_that_contradicts_the_pin_refuses_it_and_writes_nothing() {
    let rt = runtime().await;
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Asistente".into(),
                enabled: true,
                definition: definition(ask(json!({}))),
            },
            OWNER,
        )
        .await
        .unwrap()
        .id;
    let mut pin = Params::new();
    pin.insert("text".into(), json!("the write that waited"));
    rt.replace_flow_grants(&flow_id, &[GrantSpec::pinned("crm.note.add", pin)], OWNER)
        .await
        .unwrap();
    let run_id = rt
        .start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    // The model proposes a write whose payload is NOT the one the owner fixed.
    let proposal = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run_id.clone(),
            flow_id: flow_id.clone(),
            step_id: "approve".into(),
            command: "crm.note.add".into(),
            payload: json!({ "text": "whatever the message asked for" }),
            reason: "el asistente lo propuso".into(),
            partial_output: json!({}),
            on_expire: ExpiryPolicy::Reject,
            on_reject: RejectPolicy::Cancel,
        })
        .await
        .unwrap();

    let err = rt
        .decide_flow_approval(&proposal.id, true, OWNER, "")
        .await
        .expect_err("approving does not widen what the flow was granted");
    assert!(
        matches!(&err, erplora_runtime::RuntimeError::Domain { code, .. }
            if code == erplora_runtime::flows::grants::ERR_GRANT_PAYLOAD_DENIED),
        "the same CODE the direct path returns — the half the UI programs against: {err:?}"
    );
    assert!(
        notes(&rt).await.is_empty(),
        "refused BEFORE the command ran: zero writes, exactly like the gate upstream"
    );
    // And the proposal is still PENDING: refused before the door, so nobody is recorded as having
    // decided something that never ran, and the person keeps her one clean exit (reject). This is
    // the assertion that tells THIS door's check from the dispatcher's: without the check here the
    // gate downstream refuses just the same — but only after stamping the row `approved` with an
    // error, which is the record of a person authorising an action that never happened.
    let still = rt.get_flow_approval(&proposal.id).await.unwrap();
    assert_eq!(
        still.status,
        approvals::STATUS_PENDING,
        "refused at the door, not after it: the proposal is still decidable"
    );
}

/// 🔴 The other half of the same door, and the one that actually ties it: what MATCHES the pin has
/// to go THROUGH, and the write has to happen.
///
/// Without this case the negative one above passes for the wrong reason. A gate handed an EMPTY
/// payload instead of the proposal's refuses just the same — the pinned field simply comes back as
/// omitted, which is denied too — so «refused» proves nothing about the payload having been read.
/// The positive is the only assertion the empty payload cannot satisfy.
#[tokio::test]
async fn approving_a_proposal_that_matches_the_pin_lets_it_through_and_writes() {
    let rt = runtime().await;
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Asistente".into(),
                enabled: true,
                definition: definition(ask(json!({}))),
            },
            OWNER,
        )
        .await
        .unwrap()
        .id;
    let mut pin = Params::new();
    pin.insert("text".into(), json!("the write that waited"));
    rt.replace_flow_grants(&flow_id, &[GrantSpec::pinned("crm.note.add", pin)], OWNER)
        .await
        .unwrap();
    let run_id = rt
        .start_flow_run(&flow_id, &json!({}), OWNER)
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    // The model proposes exactly what the owner fixed.
    let proposal = rt
        .request_flow_approval(&approvals::NewApproval {
            run_id: run_id.clone(),
            flow_id: flow_id.clone(),
            step_id: "approve".into(),
            command: "crm.note.add".into(),
            payload: json!({ "text": "the write that waited" }),
            reason: "el asistente lo propuso".into(),
            partial_output: json!({}),
            on_expire: ExpiryPolicy::Reject,
            on_reject: RejectPolicy::Cancel,
        })
        .await
        .unwrap();

    let decided = rt
        .decide_flow_approval(&proposal.id, true, OWNER, "")
        .await
        .expect("a proposal that honours the pin is approved, not refused as if it were empty");

    assert_eq!(decided.status, approvals::STATUS_APPROVED);
    assert_eq!(
        notes(&rt).await,
        vec!["the write that waited".to_string()],
        "the proposal the owner approved is the one that RAN, with its own payload"
    );
}

// ── approved ──────────────────────────────────────────────────────────────────────────────────

/// The run carries on, and what the decision was is readable by every step written after it —
/// which is what makes `approval` compose with the primitives that are already frozen.
#[tokio::test]
async fn approving_carries_the_run_on_and_leaves_the_decision_for_the_next_steps() {
    let rt = runtime().await;
    let (_, run_id) = parked(&rt, ask(json!({}))).await;
    let question = only_pending(&rt).await;

    let decided = rt
        .decide_flow_approval(&question.id, true, "hub_user:marta", "conforme")
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(decided.status, approvals::STATUS_APPROVED);
    assert_eq!(decided.decided_by, "hub_user:marta");
    assert_eq!(decided.comment, "conforme");
    assert_eq!(
        notes(&rt).await,
        vec!["the write that waited".to_string()],
        "the step after the approval is what does the work"
    );
    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_DONE);

    let output = decision_output(&rt, &run_id).await;
    assert_eq!(output["decision"], json!("approved"));
    assert_eq!(
        output["decided_by"],
        json!("hub_user:marta"),
        "the attribution comes from the resolved session and never from a body"
    );
    assert_eq!(output["comment"], json!("conforme"));
    assert!(
        output["decided_at"]
            .as_str()
            .is_some_and(|s| s.contains('T')),
        "when it was decided is part of what the flow can read: {output}"
    );
}

/// Two admins on the same screen, or one double click. The write happens once and the second press
/// is refused by name, so the tray can tell «somebody beat you to it» from a real failure.
#[tokio::test]
async fn deciding_twice_writes_once_and_the_second_press_is_refused_by_name() {
    let rt = runtime().await;
    let (_, run_id) = parked(&rt, ask(json!({}))).await;
    let question = only_pending(&rt).await;

    rt.decide_flow_approval(&question.id, true, OWNER, "")
        .await
        .unwrap();
    let err = rt
        .decide_flow_approval(&question.id, true, OWNER, "")
        .await
        .expect_err("the second press must not authorise a second write");
    assert!(format!("{err}").contains(OWNER), "{err}");

    rt.process_flows().await.unwrap();
    assert_eq!(
        notes(&rt).await.len(),
        1,
        "exactly one note, whatever the tray did"
    );
    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_DONE);
}

// ── rejected ──────────────────────────────────────────────────────────────────────────────────

/// The default, and what a rejection means today: the steps written after an approval assumed it
/// was granted, so the run ends rather than carrying on without it. `cancelled`, not `failed` — a
/// person stopping the hub is the design working.
#[tokio::test]
async fn rejecting_ends_the_run_and_the_steps_after_it_never_run() {
    let rt = runtime().await;
    let (_, run_id) = parked(&rt, ask(json!({}))).await;
    let question = only_pending(&rt).await;

    let decided = rt
        .decide_flow_approval(&question.id, false, "hub_user:marta", "no hay albarán")
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(decided.status, approvals::STATUS_REJECTED);
    assert_eq!(decided.comment, "no hay albarán");
    assert!(notes(&rt).await.is_empty(), "a refusal executes NOTHING");
    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_CANCELLED);
}

/// `on_reject: continue` is what makes the three branches of the original contract composable out
/// of a LINEAR document: the run carries on with `steps.approve.decision == "rejected"`, and a
/// `condition` written after it is the «rejected» branch.
#[tokio::test]
async fn rejecting_with_on_reject_continue_carries_the_run_on_saying_it_was_rejected() {
    let rt = runtime().await;
    let (_, run_id) = parked(&rt, ask(json!({ "on_reject": "continue" }))).await;
    let question = only_pending(&rt).await;
    assert_eq!(question.on_reject, approvals::ON_REJECT_CONTINUE);

    rt.decide_flow_approval(&question.id, false, "hub_user:marta", "sin presupuesto")
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_DONE);
    let output = decision_output(&rt, &run_id).await;
    assert_eq!(output["decision"], json!("rejected"));
    assert_eq!(output["decided_by"], json!("hub_user:marta"));
    assert_eq!(output["comment"], json!("sin presupuesto"));
    assert_eq!(
        notes(&rt).await,
        vec!["the write that waited".to_string()],
        "`continue` means the document decides what a refusal costs, not the kernel"
    );
    // **A question's answer is FOUR fields and nothing else** (hub#1622). When the `ai` step
    // learned to say `on_reject: "continue"` it also learned to hand back the turn it had parked,
    // and the two kinds share this one method: a `decision` must not start growing `status`,
    // `approval_id` or a `command` it never had. The `condition` written after an `approval` reads
    // `decision`, and the shape it reads is the shape the approve path leaves.
    let mut keys: Vec<String> = output
        .as_object()
        .expect("the output of a question is an object")
        .keys()
        .cloned()
        .collect();
    keys.sort();
    assert_eq!(
        keys,
        vec!["comment", "decided_at", "decided_by", "decision"],
        "an `approval` step has no parked turn to hand over, so its refusal answers exactly what \
         its approval answers"
    );
}

// ── expired ───────────────────────────────────────────────────────────────────────────────────

/// The half Power Automate does badly, and the reason hub#979 exists: silence is an ANSWER, and by
/// default it is a refusal — the conservative reading, because the steps after the approval assumed
/// it was granted.
#[tokio::test]
async fn a_question_nobody_answered_expires_and_by_default_the_run_ends() {
    let rt = runtime().await;
    let (_, run_id) = parked(&rt, ask(json!({ "expires_in": 3600 }))).await;
    let question = only_pending(&rt).await;
    age(&rt, &question.id).await;

    let report = rt.sweep_expired_flow_approvals().await.unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(report.expired, 1);
    assert_eq!(report.runs_stopped, 1);
    let swept = rt.get_flow_approval(&question.id).await.unwrap();
    assert_eq!(swept.status, approvals::STATUS_EXPIRED);
    assert_eq!(swept.decided_by, approvals::DECIDED_BY_EXPIRY);
    assert!(notes(&rt).await.is_empty(), "an expiry executes nothing");
    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_CANCELLED);
}

/// n8n's `Limit Wait Time` with its «no answer» path, written as a policy instead of a branch: the
/// run carries on and says the decision was `expired`, so a `condition` after it is that path.
#[tokio::test]
async fn an_expired_question_with_on_expire_continue_carries_the_run_on_saying_so() {
    let rt = runtime().await;
    let (_, run_id) = parked(&rt, ask(json!({ "on_expire": "continue" }))).await;
    let question = only_pending(&rt).await;
    age(&rt, &question.id).await;

    let report = rt.sweep_expired_flow_approvals().await.unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(report.runs_resumed, 1, "{report:?}");
    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_DONE);
    let output = decision_output(&rt, &run_id).await;
    assert_eq!(output["decision"], json!("expired"));
    assert_eq!(
        output["decided_by"],
        json!(approvals::DECIDED_BY_EXPIRY),
        "nobody decided this, and the record names the clock rather than a person"
    );
    assert_eq!(notes(&rt).await, vec!["the write that waited".to_string()]);
}

/// `on_expire: cancel` and `on_expire: reject` both end the run today, and they are NOT synonyms:
/// the row says which one the author meant, which is what lets the tray explain itself.
#[tokio::test]
async fn the_expiry_policy_travels_in_the_row_the_step_wrote() {
    for (policy, parsed) in [
        ("cancel", ExpiryPolicy::Cancel),
        ("reject", ExpiryPolicy::Reject),
        ("continue", ExpiryPolicy::Continue),
    ] {
        let rt = runtime().await;
        parked(&rt, ask(json!({ "on_expire": policy }))).await;
        let question = only_pending(&rt).await;
        assert_eq!(
            question.on_expire, policy,
            "written where the sweep reads it"
        );
        assert_eq!(ExpiryPolicy::parse(&question.on_expire), parsed);
    }
}

// ── the question is a snapshot ────────────────────────────────────────────────────────────────

/// **Editing the flow does not mutate a question already in the tray.** It comes for free because
/// the title and the summary are templated when the question is ASKED and stored on the row — the
/// same property `payload` has, and the reason §13.3 did not need a snapshot in `vars`.
#[tokio::test]
async fn editing_the_flow_does_not_change_a_question_already_in_the_tray() {
    let rt = runtime().await;
    let (flow_id, run_id) = parked(&rt, ask(json!({}))).await;
    let asked = only_pending(&rt).await;

    rt.update_flow(
        &flow_id,
        &NewFlow {
            name: "Compras".into(),
            enabled: true,
            definition: definition(json!({
                "id": "approve", "kind": "approval",
                "title": "OTRA PREGUNTA", "summary": "otro resumen",
                "on_reject": "continue"
            })),
        },
        OWNER,
    )
    .await
    .unwrap();

    let still = rt.get_flow_approval(&asked.id).await.unwrap();
    assert_eq!(still.title, "Aprobar compra a Frutas Paco");
    assert_eq!(still.summary, "Importe 812,40 €");
    assert_eq!(
        still.on_reject,
        approvals::ON_REJECT_CANCEL,
        "the policy the person is deciding under is the one that was asked, not the one edited in"
    );

    // …and the edit does not change what her refusal costs either.
    rt.decide_flow_approval(&asked.id, false, OWNER, "")
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_CANCELLED);
    assert!(notes(&rt).await.is_empty());
}

// ── who decides ───────────────────────────────────────────────────────────────────────────────

/// **A role, resolved server-side at the moment of deciding** (Odoo's `Allowed Group`). Naming a
/// person in a document breaks the day they leave, which is the hole Business Central had to invent
/// a "substitute" for.
///
/// Whoever administers the hub always counts, and that is deliberate: the alternative is a question
/// that becomes undecidable the day its role has nobody left in it — the orphaned-approval failure
/// the forums are full of, which hub#979 exists to stop.
#[tokio::test]
async fn only_the_role_the_document_named_may_decide_and_an_administrator_always_can() {
    let rt = runtime().await;
    let manager = rt
        .create_hub_user(&NewHubUser {
            name: "Encargada".into(),
            role: "manager".into(),
            pin: "4731".into(),
            local: true,
            ..Default::default()
        }, 0)
        .await
        .unwrap();
    let cashier = rt
        .create_hub_user(&NewHubUser {
            name: "Cajero".into(),
            role: "employee".into(),
            pin: "5182".into(),
            local: true,
            ..Default::default()
        }, 0)
        .await
        .unwrap();
    // An account user, not a local one: administering this hub comes from an ERPlora account and
    // never from a PIN (`hub.users.local_cannot_administer`).
    let admin = rt
        .create_hub_user(&NewHubUser {
            name: "Dueña".into(),
            role: "admin".into(),
            email: "duena@ejemplo.com".into(),
            ..Default::default()
        }, 0)
        .await
        .unwrap();

    let (_, run_id) = parked(&rt, ask(json!({ "assignee": { "role": "manager" } }))).await;
    let question = only_pending(&rt).await;
    assert_eq!(question.assignee_role, "manager");

    let err = rt
        .decide_flow_approval(&question.id, true, &format!("hub_user:{cashier}"), "")
        .await
        .expect_err("a cashier is not who the document named");
    assert!(
        matches!(&err, erplora_runtime::errors::RuntimeError::Domain { code, .. }
                 if code == approvals::ERR_APPROVAL_NOT_YOURS),
        "{err}"
    );
    assert!(
        notes(&rt).await.is_empty(),
        "a refused decider changes nothing"
    );
    assert_eq!(
        rt.get_flow_approval(&question.id).await.unwrap().status,
        approvals::STATUS_PENDING,
        "the question is still there for whoever may answer it"
    );

    // The administrator always can — otherwise a role with nobody in it strands the run.
    let escape_hatch = rt
        .decide_flow_approval(&question.id, false, &format!("hub_user:{admin}"), "")
        .await;
    assert!(escape_hatch.is_ok(), "{escape_hatch:?}");

    // …and so may the role that was named. A second run proves it rather than a second press.
    let (_, second_run) = parked(&rt, ask(json!({ "assignee": { "role": "manager" } }))).await;
    let second = only_pending(&rt).await;
    rt.decide_flow_approval(&second.id, true, &format!("hub_user:{manager}"), "visto")
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    assert_eq!(run_status(&rt, &second_run).await, store::STATUS_DONE);
    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_CANCELLED);
    assert_eq!(
        decision_output(&rt, &second_run).await["decided_by"],
        json!(format!("hub_user:{manager}"))
    );
}

/// A question with no role named is decided by whoever administers the hub — today's gate, which
/// is what the `ai` tray has always used. Nothing narrows, so nothing breaks.
#[tokio::test]
async fn a_question_with_no_role_is_decided_by_whoever_administers_the_hub() {
    let rt = runtime().await;
    let (_, run_id) = parked(&rt, ask(json!({}))).await;
    let question = only_pending(&rt).await;
    assert_eq!(question.assignee_role, "");

    rt.decide_flow_approval(&question.id, true, OWNER, "")
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_DONE);
}

// ── the tenant ────────────────────────────────────────────────────────────────────────────────

/// One database, two hubs, and the neighbour is **alive and parked on its own question** — a
/// scoping test whose other tenant has nothing to lose proves nothing.
#[tokio::test]
async fn the_question_of_one_hub_is_invisible_and_undecidable_from_its_neighbour() {
    let shared = TestDb::new().await;
    let mine = runtime_on(shared.adapter().await, HUB).await;
    let theirs = runtime_on(shared.adapter().await, "hub-next-door").await;

    let (_, my_run) = parked(&mine, ask(json!({}))).await;
    let (_, their_run) = parked(&theirs, ask(json!({}))).await;
    let my_question = only_pending(&mine).await;
    let their_question = only_pending(&theirs).await;
    assert_ne!(my_question.id, their_question.id);

    assert!(
        theirs.get_flow_approval(&my_question.id).await.is_err(),
        "the neighbour cannot even read it"
    );
    assert!(
        theirs
            .decide_flow_approval(&my_question.id, true, "hub_user:intruder", "")
            .await
            .is_err(),
        "and cannot decide it either"
    );

    // The neighbour's own sweep does not close my question, and mine stays exactly as it was.
    theirs.sweep_expired_flow_approvals().await.unwrap();
    assert_eq!(
        mine.get_flow_approval(&my_question.id)
            .await
            .unwrap()
            .status,
        approvals::STATUS_PENDING
    );
    assert_eq!(
        run_status(&mine, &my_run).await,
        store::STATUS_WAITING_APPROVAL
    );
    assert_eq!(
        run_status(&theirs, &their_run).await,
        store::STATUS_WAITING_APPROVAL
    );
    assert_eq!(only_pending(&mine).await.id, my_question.id);
}

/// The reject policy of a question is read from the ROW, so a hub cannot be talked into carrying a
/// run past a refusal by a value written by a newer version — or by hand.
#[tokio::test]
async fn an_unrecognised_reject_policy_in_the_row_ends_the_run() {
    let rt = runtime().await;
    let (_, run_id) = parked(&rt, ask(json!({ "on_reject": "continue" }))).await;
    let question = only_pending(&rt).await;
    let mut p = Params::new();
    p.insert("id".into(), json!(question.id));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_approvals SET on_reject = 'nonsense-from-v2' WHERE id = :id",
            &p,
        )
        .await
        .unwrap();

    rt.decide_flow_approval(&question.id, false, OWNER, "")
        .await
        .unwrap();
    rt.process_flows().await.unwrap();

    assert_eq!(
        RejectPolicy::parse("nonsense-from-v2"),
        RejectPolicy::Cancel
    );
    assert_eq!(run_status(&rt, &run_id).await, store::STATUS_CANCELLED);
    assert!(notes(&rt).await.is_empty());
}

/// The tray lights up without polling, exactly like a proposal from a model: the core emits the
/// fact and the SCREEN is the module `flows`'s job (ADR-0283 §7).
#[tokio::test]
async fn asking_emits_the_same_ephemeral_fact_a_model_s_proposal_does() {
    use erplora_runtime::registry::{EventSink, EventSource};
    use std::sync::{Arc, Mutex};

    #[derive(Default, Debug)]
    struct Sink(Mutex<Vec<(String, Value)>>);
    impl EventSink for Sink {
        fn emit(&self, _source: EventSource<'_>, name: &str, payload: &Value) {
            self.0.lock().unwrap().push((name.into(), payload.clone()));
        }
    }

    let mut rt = Runtime::with_hub_id(Box::new(TestDb::new().await.adapter().await), HUB);
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("crm")).await.unwrap();

    let (_, run_id) = parked(&rt, ask(json!({}))).await;

    let created = |sink: &Sink| -> Vec<Value> {
        sink.0
            .lock()
            .unwrap()
            .iter()
            .filter(|(n, _)| n == approvals::EVENT_APPROVAL_CREATED)
            .map(|(_, p)| p.clone())
            .collect()
    };
    let emitted = created(&sink);
    assert_eq!(emitted.len(), 1, "one question asked, one fact emitted");
    assert_eq!(emitted[0]["approval_id"], json!(only_pending(&rt).await.id));
    assert_eq!(emitted[0]["title"], json!("Aprobar compra a Frutas Paco"));
    assert_eq!(emitted[0]["kind"], json!(approvals::KIND_DECISION));

    // A REPLAY of the step is not a new question. Announcing it again would light up the tray for
    // a row that has been sitting in it since Tuesday.
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_runs SET status = 'pending', claim_expires_at = NULL WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    assert_eq!(
        created(&sink).len(),
        1,
        "still one: the same question, asked once"
    );
}
