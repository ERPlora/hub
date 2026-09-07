//! **What the server-side agent runner is allowed to ask for** (hub#665, ADR-0283 K5/D3).
//!
//! The runner itself lives in `crates/server/src/agent_runner.rs`, because it needs `cloud-client`
//! and the runtime has no network by design. This module is the runtime half of that split: the
//! read that hands over a parked `ai` step, and nothing else.
//!
//! It is the counterpart of [`crate::flows::http`], with one deliberate difference. `http::prepare`
//! resolves everything under the lock and puts a finished request inside `PendingIo::Http`, because
//! the decision of *whether the call may happen* — allow-list, secrets, the templated URL — belongs
//! to the runtime. An agent turn cannot be prepared that way: what the model may be OFFERED comes
//! from `assistant::assemble_tools`, which lives in the server. So `PendingIo::Ai` carries only the
//! run and the step, and the server reads the rest back through [`prepare`].
//!
//! That is not a loophole. The tool catalogue only decides what is offered; **what is allowed is
//! re-checked by the runtime at the moment of the call** ([`crate::Runtime::execute_flow_query`],
//! [`crate::Runtime::execute_flow_command`]), because a gate the caller can skip is not a gate.
use erplora_db::DatabaseAdapter;
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::flows::approvals::RejectPolicy;
use crate::flows::def::{self, AiPolicy, FlowDefinition, StepSpec};
use crate::flows::store;

pub const ERR_NOT_IN_FLIGHT: &str = "flow.agent_step_not_in_flight";

/// Everything a turn needs, read ONCE under the lock, with the prompt already resolved against the
/// run: the runner must not have to re-read the flow document to know what it was asked to do, and
/// a second read would be a second answer if the document changed in between.
#[derive(Debug, Clone, PartialEq)]
pub struct AiRequest {
    pub run_id: String,
    pub flow_id: String,
    pub step_id: String,
    /// Event depth the run inherited — handed to `execute_at` so the anti-loop guard keeps counting
    /// through an agent turn (`_flow_runs.depth`, flows.md §3).
    pub depth: i64,
    pub prompt: String,
    /// Reads the step declared. Still intersected with the grants before anything is offered.
    pub queries: Vec<String>,
    /// Writes the step declared. Same intersection, plus [`AiRequest::policy`].
    pub commands: Vec<String>,
    pub policy: AiPolicy,
    pub max_iters: i64,
    /// What the step said a «no» costs the run (hub#1622). Carried here for the same reason the
    /// prompt is: the runner must not re-read the document to know what it was asked to do, and a
    /// second read would be a second answer if the flow changed in between.
    pub on_reject: RejectPolicy,
}

/// Reads the `ai` step a run is currently stopped on.
///
/// Refuses anything else by name. The runner is an ordinary caller, and a caller that could resume
/// an arbitrary run would be a way around the claim — and the claim is what makes an agent turn
/// start exactly once instead of the hub answering the same customer twice.
pub async fn prepare(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    step_id: &str,
) -> Result<AiRequest> {
    let (run, steps) = store::get_run(db, hub_id, run_id).await?;
    let index = run.current_step;

    // The step row the tick wrote before handing the work over. `running` is the in-flight marker
    // of the claim → I/O → complete seam (hub#662); anything else means this turn is not the one
    // the run is waiting for.
    let in_flight = steps
        .iter()
        .find(|s| s.step_index == index && s.step_id == step_id && s.status == "running");
    if in_flight.is_none() {
        return Err(RuntimeError::Domain {
            code: ERR_NOT_IN_FLIGHT.to_string(),
            message: format!(
                "run `{run_id}` is not waiting on step `{step_id}`; only the step the tick claimed \
                 may be performed"
            ),
        });
    }

    let flow = store::get(db, hub_id, &run.flow_id).await?;
    let def = FlowDefinition::parse(&flow.definition)?;
    let step = def
        .steps
        .get(index as usize)
        .filter(|s| s.id == step_id)
        .ok_or_else(|| RuntimeError::Domain {
            code: ERR_NOT_IN_FLIGHT.to_string(),
            message: format!("step `{step_id}` is no longer step {index} of its flow"),
        })?;
    let StepSpec::Ai(ai) = &step.spec else {
        return Err(RuntimeError::Domain {
            code: ERR_NOT_IN_FLIGHT.to_string(),
            message: format!("step `{step_id}` is `{}`, not `ai`", step.kind.as_str()),
        });
    };

    // The same scope every other mapping is resolved against.
    let done: serde_json::Map<String, Json> = steps
        .iter()
        .filter(|s| s.status == "done")
        .map(|s| (s.step_id.clone(), s.output.clone()))
        .collect();
    let scope = json!({ "input": run.input, "steps": Json::Object(done) });
    let prompt = def::resolve(&json!(ai.prompt), &scope)
        .as_str()
        .unwrap_or(&ai.prompt)
        .to_string();

    Ok(AiRequest {
        run_id: run.id,
        flow_id: run.flow_id,
        step_id: step.id.clone(),
        depth: run.depth,
        prompt,
        queries: ai.queries.clone(),
        commands: ai.commands.clone(),
        policy: ai.policy,
        max_iters: ai.max_iters,
        on_reject: ai.on_reject,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::executor;
    use crate::flows::store::NewFlow;
    use crate::flows::test_support;
    use crate::registry::Registry;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-flow-agent";

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db
    }

    fn definition() -> Json {
        json!({
            "schema_version": 1,
            "steps": [
                { "id": "agent", "kind": "ai", "prompt": "answer {{input.who}}",
                  "tools": { "queries": ["crm.note.list"] } },
                { "id": "wait", "kind": "delay", "seconds": 3600 }
            ]
        })
    }

    /// Parks a run on its `ai` step, exactly as the tick does, and returns its id.
    async fn parked(db: &dyn DatabaseAdapter) -> String {
        parked_with(db, definition()).await
    }

    /// Same, for a document the test writes itself.
    async fn parked_with(db: &dyn DatabaseAdapter, definition: Json) -> String {
        let flow = store::create(
            db,
            HUB,
            &crate::registry::Registry::new(),
            &NewFlow {
                name: "A".into(),
                enabled: true,
                definition,
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        store::start_run(
            db,
            HUB,
            &flow.id,
            "",
            "manual",
            "",
            &json!({ "who": "Marta" }),
            0,
            "t",
        )
        .await
        .unwrap();
        let report = executor::tick(db, &Registry::new(), HUB).await.unwrap();
        assert_eq!(report.pending_io.len(), 1, "the tick hands the turn over");
        report.pending_io[0].run_id().to_string()
    }

    #[tokio::test]
    async fn the_request_is_read_once_with_its_prompt_already_resolved() {
        let db = db().await;
        let run_id = parked(&db).await;
        let request = prepare(&db, HUB, &run_id, "agent").await.unwrap();
        assert_eq!(request.prompt, "answer Marta");
        assert_eq!(request.queries, vec!["crm.note.list".to_string()]);
        assert_eq!(
            request.policy,
            AiPolicy::Manual,
            "the default (ADR-0283 D3)"
        );
        assert_eq!(request.max_iters, def::DEFAULT_MAX_ITERS);
    }

    /// **What the step said a refusal costs travels with the request** (hub#1622). The runner
    /// copies `AiRequest::on_reject` into the approval row without re-reading the document, so
    /// this is the ONLY place the document's answer can be lost: a request that always said
    /// `cancel` would leave every template's `on_reject: "continue"` a dead letter, with every
    /// other test green.
    #[tokio::test]
    async fn the_request_carries_what_the_step_said_a_refusal_costs() {
        let db = db().await;
        let run_id = parked_with(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "agent", "kind": "ai", "prompt": "book {{input.who}}",
                      "tools": { "commands": ["crm.note.add"] }, "on_reject": "continue" }
                ]
            }),
        )
        .await;
        let request = prepare(&db, HUB, &run_id, "agent").await.unwrap();
        assert_eq!(
            request.on_reject,
            RejectPolicy::Continue,
            "the document said a «no» lets the run carry on, and the request has to say the same"
        );

        let default = prepare(&db, HUB, &parked(&db).await, "agent")
            .await
            .unwrap();
        assert_eq!(
            default.on_reject,
            RejectPolicy::Cancel,
            "a document that says nothing still ends the run on a refusal"
        );
    }

    /// A caller that could resume an arbitrary run would be a way around the claim, and the claim
    /// is what makes an agent turn start exactly once.
    #[tokio::test]
    async fn a_step_that_is_not_in_flight_cannot_be_performed() {
        let db = db().await;
        let run_id = parked(&db).await;

        // Another step of the same run, and a run that already moved on.
        assert!(prepare(&db, HUB, &run_id, "wait").await.is_err());
        executor::complete_io(
            &db,
            HUB,
            &run_id,
            "agent",
            executor::IoResult::Done(json!({ "text": "done" })),
        )
        .await
        .unwrap();

        let err = prepare(&db, HUB, &run_id, "agent")
            .await
            .expect_err("the step was already completed");
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_NOT_IN_FLIGHT),
            "{err}"
        );
    }

    /// The tenant is never negotiable: a neighbouring hub cannot read this hub's parked turn.
    #[tokio::test]
    async fn a_run_of_another_hub_is_not_readable_here() {
        let db = db().await;
        test_support::ensure_schema(&db, "hub-next-door").await;
        let run_id = parked(&db).await;
        assert!(prepare(&db, "hub-next-door", &run_id, "agent")
            .await
            .is_err());
    }
}
