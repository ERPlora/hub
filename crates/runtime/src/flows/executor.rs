//! **`flows_tick`** — the half-second of work that moves runs forward, folded into the 1 s tick
//! that already runs the outbox relay and the scheduler (`crates/server/src/lib.rs`).
//!
//! It shares the runtime's global lock with those two, and that single fact shapes everything
//! here (ADR-0283 §1, risk 1 of flows.md §12): the tick may only do work whose duration it can
//! bound. So it advances a **bounded** number of runs, a **bounded** number of steps each, and
//! the steps it executes are the ones with no I/O — `command` (a local transaction), `condition`
//! (arithmetic) and `delay` (a row update). A 30 s HTTP call or a 60 s agent turn inside this lock
//! would freeze every till in the hub, which is why those follow a different contract entirely:
//!
//! ```text
//!   claim (locked, cheap)  →  I/O (unlocked, in crates/server)  →  complete (locked, cheap)
//! ```
//!
//! [`PendingIo`] is that seam. It is defined and returned here, and NOTHING consumes it yet: the
//! `http`, `ai` and `notify` steps land with hub#662/#665/#663, and until then a document that
//! uses them is refused at save time rather than parked forever (`FlowDefinition::parse`).
//!
//! ## Where a crash leaves a run
//!
//! A command step commits its effects, its step row and the run's advance in ONE transaction (the
//! `extra_ops` of `execute_at`, the same trick `scheduler::run_task` uses). So a runtime that dies
//! mid-step never re-runs a command that already committed — the alternative, advancing after the
//! command, duplicates sales.
//!
//! What that transaction cannot carry is the command's **output**, which only exists once it
//! returns. The step is therefore written `committed` inside the transaction and completed with
//! its output right after. If the process dies in between, the next claim finds a `committed`
//! step and **fails the run** naming it ([`ERR_STEP_OUTPUT_LOST`]) instead of continuing with a
//! `steps.<id>` that silently reads as null — a wrong invoice is worse than a stopped flow.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Map, Value as Json};

use crate::commands::{self, Origin};
use crate::errors::{Result, RuntimeError};
use crate::flows::def::{self, FlowDefinition, StepDef, StepSpec};
use crate::flows::{grants, store, triggers};
use crate::registry::{new_id, now_rfc3339, AutomationCtx, Registry, RequestContext};

/// How many runs one tick advances. The tick happens every second, so this is a throughput knob,
/// not a limit on how many flows a hub may have.
const MAX_RUNS_PER_TICK: usize = 20;

/// How many steps one run advances per tick. Without a cap, a 200-step flow would hold the global
/// lock for its entire length; with it, a long flow simply takes more ticks.
const MAX_STEPS_PER_TICK: usize = 8;

/// How long a claimed run stays invisible to another runtime. Same value as the outbox, the
/// scheduler and the print queue: start-first deploys mean two runtimes share this table.
const LEASE_SECONDS: i64 = 300;

pub const ERR_STEP_OUTPUT_LOST: &str = "flow.step_output_lost";
pub const ERR_FLOW_GONE: &str = "flow.definition_gone";

/// Step statuses inside a run.
const STEP_COMMITTED: &str = "committed";
const STEP_DONE: &str = "done";
const STEP_FAILED: &str = "failed";
const STEP_SLEEPING: &str = "sleeping";
const STEP_STOPPED: &str = "stopped";

/// **The claim → I/O → complete seam.** The tick produces one of these instead of performing the
/// call; the server performs it outside the lock and hands the result back.
///
/// It is deliberately an enum of the three reserved kinds and not a generic "do this HTTP thing":
/// each one has different limits, a different allow-list and a different grant, and flattening
/// them would be inventing the contract of hub#662 here.
#[derive(Debug, Clone, PartialEq)]
pub enum PendingIo {
    /// hub#662 — `http` with a URL allow-list and `_flow_secrets`.
    Http { run_id: String, step_id: String },
    /// hub#665 — the server-side agent runner.
    Ai { run_id: String, step_id: String },
    /// hub#663 part 2 — `notify` with `recipient_query`.
    Notify { run_id: String, step_id: String },
}

/// What one tick did, so the caller can log it without a second query.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct TickReport {
    /// Runs started by a clock trigger this tick.
    pub started: usize,
    /// Runs advanced (claimed and moved at least one step).
    pub advanced: usize,
    /// I/O the server should perform outside the lock. Always empty until hub#662.
    pub pending_io: Vec<PendingIo>,
}

/// One cycle of the flows kernel: fire what the clock owes, wake what finished sleeping, and
/// advance what is ready. Called from the same 1 s loop as the outbox relay and the scheduler.
pub async fn tick(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
) -> Result<TickReport> {
    let mut report = TickReport {
        started: triggers::sweep_schedules(db, hub_id).await?,
        ..Default::default()
    };
    wake_sleeping(db, hub_id).await?;

    for _ in 0..MAX_RUNS_PER_TICK {
        let Some(run) = claim_next_run(db, hub_id).await? else {
            break;
        };
        // A failure advancing ONE run never stops the others (the lesson of hub#142 in the
        // outbox): the run is left claimed, its lease expires, and it is retried.
        if let Err(e) = advance_run(db, registry, hub_id, &run).await {
            eprintln!(
                "flows: run {}: {e}",
                run["id"].as_str().unwrap_or("?")
            );
        }
        report.advanced += 1;
    }
    Ok(report)
}

/// A `delay` that has come due goes back in the queue. One statement, no rows read into memory.
async fn wake_sleeping(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<()> {
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    db.execute(
        "UPDATE _flow_runs SET status = 'pending', wake_at = NULL, updated_at = :now \
         WHERE hub_id = :hub_id AND status = 'sleeping' AND wake_at IS NOT NULL \
           AND wake_at <= :now AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

/// Claims one runnable run atomically. `running` rows whose lease expired are reclaimed too —
/// that is orphan recovery, and without it a runtime killed mid-tick would strand its runs.
async fn claim_next_run(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<Json>> {
    let now = now_rfc3339();
    let lease = (chrono::Utc::now() + chrono::Duration::seconds(LEASE_SECONDS)).to_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    p.insert("lease".into(), json!(lease));
    let sql = "UPDATE _flow_runs \
               SET status = 'running', claim_expires_at = :lease, updated_at = :now, \
                   started_at = COALESCE(started_at, :now) \
               WHERE id = ( \
                 SELECT id FROM _flow_runs \
                 WHERE hub_id = :hub_id AND deleted_at IS NULL \
                   AND status IN ('pending','running') \
                   AND (claim_expires_at IS NULL OR claim_expires_at <= :now) \
                 ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED) \
               RETURNING id, flow_id, current_step, input, vars, depth, attempts";
    let res = db.query(sql, &p).await?;
    Ok(res.rows.into_iter().next())
}

/// Advances one claimed run by up to [`MAX_STEPS_PER_TICK`] steps.
async fn advance_run(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    run: &Json,
) -> Result<()> {
    let run_id = run["id"].as_str().unwrap_or_default().to_string();
    let flow_id = run["flow_id"].as_str().unwrap_or_default().to_string();
    let depth = run["depth"].as_i64().unwrap_or(0);
    let mut index = run["current_step"].as_i64().unwrap_or(0);
    let input: Json = parse_json(run["input"].as_str().unwrap_or("{}"));
    let mut vars: Json = parse_json(run["vars"].as_str().unwrap_or("{}"));

    // A step that committed but never recorded its output: the process died between the two
    // writes. Continuing would read `steps.<id>` as null in every later step.
    if let Some(step_id) = interrupted_step(db, &run_id).await? {
        return finish(
            db,
            &run_id,
            store::STATUS_FAILED,
            &format!(
                "{ERR_STEP_OUTPUT_LOST}: step `{step_id}` committed its effects but its output was \
                 lost to a restart; the run is stopped rather than continued with a null it would \
                 read as a value"
            ),
        )
        .await;
    }

    // The definition is read fresh, and a flow that was disabled or deleted mid-run stops here.
    // A run outliving its flow would be a hub acting on an instruction its owner withdrew.
    let flow = match store::get(db, hub_id, &flow_id).await {
        Ok(flow) if flow.enabled => flow,
        Ok(_) => {
            return finish(
                db,
                &run_id,
                store::STATUS_CANCELLED,
                "the flow was disabled while this run was in flight",
            )
            .await
        }
        Err(_) => {
            return finish(
                db,
                &run_id,
                store::STATUS_CANCELLED,
                &format!("{ERR_FLOW_GONE}: the flow was deleted while this run was in flight"),
            )
            .await
        }
    };
    // The document is validated before it is ever stored, so this only fires when the stored one
    // stopped being readable BY THIS BINARY — a rollback below the `schema_version` that wrote it.
    // Failing the run beats propagating: an error here would leave the run `running`, reclaimed
    // every time its lease expires, forever.
    let def = match FlowDefinition::parse(&flow.definition) {
        Ok(def) => def,
        Err(e) => return finish(db, &run_id, store::STATUS_FAILED, &format!("{e}")).await,
    };

    for _ in 0..MAX_STEPS_PER_TICK {
        let Some(step) = def.steps.get(index as usize) else {
            return finish(db, &run_id, store::STATUS_DONE, "").await;
        };
        let scope = json!({ "input": input, "steps": vars.get("steps").cloned().unwrap_or(json!({})) });

        match run_step(db, registry, hub_id, &flow_id, &run_id, depth, index, step, &scope).await? {
            Outcome::Continue { output } => {
                set_step_output(&mut vars, &step.id, output);
                index += 1;
                persist_vars(db, &run_id, index, &vars).await?;
            }
            Outcome::Stopped => return finish(db, &run_id, store::STATUS_DONE, "").await,
            Outcome::Sleep { wake_at } => return sleep_until(db, &run_id, &wake_at).await,
            Outcome::Failed { error } => {
                // v1 is `on_error: "stop"` (ADR-0283 §1): a linear flow has nowhere else to go,
                // and retrying a business command by itself is how a sale gets charged twice.
                return finish(db, &run_id, store::STATUS_FAILED, &error).await;
            }
        }
    }

    // Budget spent with steps left: back in the queue, lease released, resumes next tick.
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _flow_runs SET status = 'pending', claim_expires_at = NULL, updated_at = :now \
         WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

enum Outcome {
    Continue { output: Json },
    /// A `condition` said no. The run is complete, not failed: a guard that does not pass is the
    /// flow working exactly as written.
    Stopped,
    Sleep { wake_at: String },
    Failed { error: String },
}

#[allow(clippy::too_many_arguments)] // one step's worth of context; splitting it hides the seam
async fn run_step(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    flow_id: &str,
    run_id: &str,
    depth: i64,
    index: i64,
    step: &StepDef,
    scope: &Json,
) -> Result<Outcome> {
    let now = now_rfc3339();
    match &step.spec {
        StepSpec::Condition { when } => {
            let matched = when.matches(scope);
            let output = json!({ "matched": matched });
            let status = if matched { STEP_DONE } else { STEP_STOPPED };
            write_step(db, hub_id, run_id, index, step, status, &json!({}), &output, "", &now)
                .await?;
            Ok(if matched {
                Outcome::Continue { output }
            } else {
                Outcome::Stopped
            })
        }

        StepSpec::Delay { seconds, until } => {
            let wake_at = match (seconds, until) {
                (Some(s), _) => (chrono::Utc::now() + chrono::Duration::seconds(*s)).to_rfc3339(),
                (None, Some(path)) => {
                    let value = def::resolve(&json!(path), scope);
                    match value.as_str().and_then(|s| {
                        chrono::DateTime::parse_from_rfc3339(s).ok().map(|d| d.to_rfc3339())
                    }) {
                        Some(instant) => instant,
                        None => {
                            let error = format!(
                                "step `{}`: `until` resolved to {value}, which is not an RFC-3339 \
                                 instant",
                                step.id
                            );
                            write_step(
                                db, hub_id, run_id, index, step, STEP_FAILED, &json!({}),
                                &json!({}), &error, &now,
                            )
                            .await?;
                            return Ok(Outcome::Failed { error });
                        }
                    }
                }
                (None, None) => unreachable!("parse refuses a delay with neither"),
            };
            let output = json!({ "wake_at": wake_at });
            write_step(db, hub_id, run_id, index, step, STEP_SLEEPING, &json!({}), &output, "", &now)
                .await?;
            // The step index advances with the sleep: waking up resumes AFTER the delay, not on it.
            persist_step_index(db, run_id, index + 1).await?;
            Ok(Outcome::Sleep { wake_at })
        }

        StepSpec::Command { command, params } => {
            let resolved = def::resolve_map(params, scope);
            let resolved_json = Json::Object(resolved.clone());

            // The context the command runs under. `user_id = flow:<id>` is what lands in
            // `created_by`, so the row a flow writes says a flow wrote it. The permissions are the
            // union of the granted commands — NOT what opens the gate (that is the grant itself,
            // re-read inside `execute_at`), but what keeps the listeners this command triggers
            // from dying in dead-letter (ADR-0283 §2).
            let authority = grants::authority(db, hub_id, flow_id).await?;
            let ctx = RequestContext::new(
                hub_id.to_string(),
                format!("flow:{flow_id}"),
                authority.permissions(registry),
            )
            // A flow is a machine: it can never be offered a manager's PIN (hub#361).
            .as_machine()
            .with_automation(AutomationCtx {
                flow_id: flow_id.to_string(),
                run_id: run_id.to_string(),
            });

            // The step row and the run's advance ride in the command's transaction: effects and
            // bookkeeping commit together, so a crash never re-runs a command that already ran.
            let extra = [
                write_step_op(
                    hub_id, run_id, index, step, STEP_COMMITTED, &resolved_json, &json!({}), "",
                    &now,
                ),
                advance_index_op(run_id, index + 1, &now),
            ];

            match commands::execute_at(
                db,
                registry,
                command,
                &resolved,
                &ctx,
                depth as u32,
                &extra,
                Origin::Automation,
                // No approval to spend: an elevation is a person authorising an action at the
                // counter, and there is nobody at the counter (hub#361).
                None,
            )
            .await
            {
                Ok(output) => {
                    complete_step(db, run_id, index, &output, &now).await?;
                    Ok(Outcome::Continue { output })
                }
                Err(e) => {
                    // The transaction rolled back, so the step row above never existed: write the
                    // failure on its own.
                    let error = step_error(command, &e);
                    write_step(
                        db, hub_id, run_id, index, step, STEP_FAILED, &resolved_json, &json!({}),
                        &error, &now,
                    )
                    .await?;
                    Ok(Outcome::Failed { error })
                }
            }
        }

        // Reserved for the I/O kinds. `FlowDefinition::parse` refuses to store a document that
        // reaches here, so this arm is the seam and not a live path: when hub#662 fills it in, it
        // returns the run to the tick as a `PendingIo` and the server performs the call outside
        // the lock.
        StepSpec::Reserved => {
            let error = format!(
                "step `{}` is of kind `{}`: the claim → I/O → complete path is not implemented \
                 yet (http: hub#662, ai: hub#665, notify: hub#663)",
                step.id,
                step.kind.as_str()
            );
            write_step(
                db, hub_id, run_id, index, step, STEP_FAILED, &json!({}), &json!({}), &error, &now,
            )
            .await?;
            Ok(Outcome::Failed { error })
        }
    }
}

/// The id of a step this run committed without recording its output, if any.
async fn interrupted_step(db: &dyn DatabaseAdapter, run_id: &str) -> Result<Option<String>> {
    let mut p = Params::new();
    p.insert("run_id".into(), json!(run_id));
    let res = db
        .query(
            "SELECT step_id FROM _flow_run_steps \
             WHERE run_id = :run_id AND status = 'committed' AND deleted_at IS NULL \
             ORDER BY step_index LIMIT 1",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["step_id"].as_str().map(|s| s.to_string())))
}

#[allow(clippy::too_many_arguments)]
fn write_step_op(
    hub_id: &str,
    run_id: &str,
    index: i64,
    step: &StepDef,
    status: &str,
    input: &Json,
    output: &Json,
    error: &str,
    now: &str,
) -> (String, Params) {
    let mut p = Params::new();
    p.insert("id".into(), json!(new_id()));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(run_id));
    p.insert("step_index".into(), json!(index));
    p.insert("step_id".into(), json!(step.id));
    p.insert("kind".into(), json!(step.kind.as_str()));
    p.insert("status".into(), json!(status));
    p.insert("input".into(), json!(input.to_string()));
    p.insert("output".into(), json!(output.to_string()));
    p.insert("error".into(), json!(error));
    p.insert("now".into(), json!(now));
    // Re-attempting a step after an expired lease updates its row instead of colliding.
    let sql = "INSERT INTO _flow_run_steps \
        (id, hub_id, run_id, step_index, step_id, kind, status, input, output, error, \
         started_at, finished_at, created_at) \
        VALUES (:id, :hub_id, :run_id, :step_index, :step_id, :kind, :status, :input, :output, \
                :error, :now, :now, :now) \
        ON CONFLICT (run_id, step_index) WHERE deleted_at IS NULL DO UPDATE SET \
          step_id = :step_id, kind = :kind, status = :status, input = :input, output = :output, \
          error = :error, finished_at = :now";
    (sql.to_string(), p)
}

#[allow(clippy::too_many_arguments)]
async fn write_step(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    index: i64,
    step: &StepDef,
    status: &str,
    input: &Json,
    output: &Json,
    error: &str,
    now: &str,
) -> Result<()> {
    let (sql, p) = write_step_op(hub_id, run_id, index, step, status, input, output, error, now);
    db.execute(&sql, &p).await?;
    Ok(())
}

/// Writes the output a `committed` step produced, closing the window described at the top.
async fn complete_step(
    db: &dyn DatabaseAdapter,
    run_id: &str,
    index: i64,
    output: &Json,
    now: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("run_id".into(), json!(run_id));
    p.insert("step_index".into(), json!(index));
    p.insert("output".into(), json!(output.to_string()));
    p.insert("now".into(), json!(now));
    db.execute(
        "UPDATE _flow_run_steps SET status = 'done', output = :output, finished_at = :now \
         WHERE run_id = :run_id AND step_index = :step_index AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

fn advance_index_op(run_id: &str, next_index: i64, now: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("step".into(), json!(next_index));
    p.insert("now".into(), json!(now));
    (
        "UPDATE _flow_runs SET current_step = :step, updated_at = :now WHERE id = :id".to_string(),
        p,
    )
}

async fn persist_step_index(db: &dyn DatabaseAdapter, run_id: &str, next: i64) -> Result<()> {
    let (sql, p) = advance_index_op(run_id, next, &now_rfc3339());
    db.execute(&sql, &p).await?;
    Ok(())
}

async fn persist_vars(
    db: &dyn DatabaseAdapter,
    run_id: &str,
    next_index: i64,
    vars: &Json,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("step".into(), json!(next_index));
    p.insert("vars".into(), json!(vars.to_string()));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _flow_runs SET current_step = :step, vars = :vars, updated_at = :now \
         WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

async fn sleep_until(db: &dyn DatabaseAdapter, run_id: &str, wake_at: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("wake_at".into(), json!(wake_at));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _flow_runs SET status = 'sleeping', wake_at = :wake_at, \
                               claim_expires_at = NULL, updated_at = :now WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

async fn finish(
    db: &dyn DatabaseAdapter,
    run_id: &str,
    status: &str,
    error: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("status".into(), json!(status));
    p.insert("error".into(), json!(error));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _flow_runs SET status = :status, last_error = :error, finished_at = :now, \
                               claim_expires_at = NULL, updated_at = :now WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

/// How a step failure is written into the run.
///
/// A [`RuntimeError::Domain`] shows only its `message`, but its stable **code** (hub#139) is the
/// half a caller can program against — `flow.grant_denied` tells the module `flows` to offer «grant
/// it», where the prose does not. `last_error` is read hours later by somebody who was not there,
/// so both halves are stamped here.
fn step_error(command: &str, error: &RuntimeError) -> String {
    match error {
        RuntimeError::Domain { code, message } => format!("{command}: {code}: {message}"),
        other => format!("{command}: {other}"),
    }
}

fn parse_json(raw: &str) -> Json {
    serde_json::from_str(raw).unwrap_or_else(|_| json!({}))
}

fn set_step_output(vars: &mut Json, step_id: &str, output: Json) {
    if !vars.is_object() {
        *vars = json!({});
    }
    let root = vars.as_object_mut().expect("just made an object");
    let steps = root
        .entry("steps".to_string())
        .or_insert_with(|| Json::Object(Map::new()));
    if !steps.is_object() {
        *steps = Json::Object(Map::new());
    }
    steps
        .as_object_mut()
        .expect("just made an object")
        .insert(step_id.to_string(), output);
}

/// Starts a run by hand (`POST /api/hub/flows/{id}/run`, ADR-0283 §3 `manual`). Refuses a flow
/// that is disabled: the button must not do what the switch says it will not.
pub async fn start_manual_run(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    input: &Json,
    started_by: &str,
) -> Result<String> {
    let flow = store::get(db, hub_id, flow_id).await?;
    if !flow.enabled {
        return Err(RuntimeError::Domain {
            code: "flow.disabled".to_string(),
            message: format!("flow `{flow_id}` is disabled"),
        });
    }
    // Parsing here means a broken document is reported to the person pressing the button.
    FlowDefinition::parse(&flow.definition)?;
    store::start_run(db, hub_id, flow_id, "", "manual", "", input, 0, started_by).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::grants::GrantKind;
    use crate::flows::store::NewFlow;
    use crate::flows::test_support;
    use crate::registry::ModuleStatus;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-exec";

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db.execute_batch("CREATE TABLE IF NOT EXISTS note (id TEXT PRIMARY KEY, text TEXT NOT NULL);")
            .await
            .unwrap();
        db
    }

    /// A module with one declarative command that writes a row and returns nothing surprising.
    fn registry() -> Registry {
        let mut reg = Registry::new();
        reg.status.insert("notes".into(), ModuleStatus::Active);
        reg.commands.insert(
            "notes.note.add".into(),
            test_support::command(
                "notes",
                "notes.add_note",
                "INSERT INTO note (id, text) VALUES (:new_id, :text);",
                vec![],
            ),
        );
        reg
    }

    async fn flow(db: &dyn DatabaseAdapter, definition: Json) -> String {
        store::create(
            db,
            HUB,
            &NewFlow {
                name: "F".into(),
                enabled: true,
                definition,
            },
            "hub_user:1",
        )
        .await
        .unwrap()
        .id
    }

    async fn grant(db: &dyn DatabaseAdapter, flow_id: &str, command: &str) {
        grants::replace(
            db,
            HUB,
            flow_id,
            &registry(),
            &[(GrantKind::Command, command.to_string())],
            "hub_user:1",
        )
        .await
        .unwrap();
    }

    async fn notes(db: &dyn DatabaseAdapter) -> Vec<String> {
        db.query("SELECT text FROM note ORDER BY text", &Params::new())
            .await
            .unwrap()
            .rows
            .iter()
            .map(|r| r["text"].as_str().unwrap_or_default().to_string())
            .collect()
    }

    async fn run_of(db: &dyn DatabaseAdapter, flow_id: &str) -> store::FlowRun {
        store::list_runs(db, HUB, flow_id, 10).await.unwrap().remove(0)
    }

    fn one_command_flow() -> Json {
        json!({
            "schema_version": 1,
            "triggers": [{ "kind": "manual" }],
            "steps": [{
                "id": "write", "kind": "command", "command": "notes.note.add",
                "params": { "text": "hello {{input.who}}" }
            }]
        })
    }

    #[tokio::test]
    async fn a_manual_run_executes_its_command_with_the_mapped_params() {
        let db = db().await;
        let reg = registry();
        let flow_id = flow(&db, one_command_flow()).await;
        grant(&db, &flow_id, "notes.note.add").await;

        start_manual_run(&db, HUB, &flow_id, &json!({ "who": "Marta" }), "hub_user:1")
            .await
            .unwrap();
        tick(&db, &reg, HUB).await.unwrap();

        assert_eq!(notes(&db).await, vec!["hello Marta"]);
        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_DONE);
        assert_eq!(run.current_step, 1);
    }

    #[tokio::test]
    async fn without_a_grant_the_command_does_not_run_and_the_run_fails_saying_so() {
        let db = db().await;
        let flow_id = flow(&db, one_command_flow()).await;
        // No grant at all — the default answer.
        start_manual_run(&db, HUB, &flow_id, &json!({ "who": "Marta" }), "hub_user:1")
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        assert!(notes(&db).await.is_empty(), "nothing was written");
        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_FAILED);
        assert!(
            run.last_error.contains(grants::ERR_GRANT_DENIED),
            "the failure names the missing grant: {}",
            run.last_error
        );
    }

    #[tokio::test]
    async fn a_condition_that_does_not_pass_ends_the_run_without_failing_it() {
        let db = db().await;
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "guard", "kind": "condition", "when": { "input.total": { "gte": "100" } } },
                    { "id": "write", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "big sale" } }
                ]
            }),
        )
        .await;
        grant(&db, &flow_id, "notes.note.add").await;

        store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({ "total": "9.90" }), 0, "t")
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        assert!(notes(&db).await.is_empty(), "the guard stopped the flow");
        let run = run_of(&db, &flow_id).await;
        assert_eq!(
            run.status,
            store::STATUS_DONE,
            "a guard that does not pass is the flow working, not failing"
        );
    }

    #[tokio::test]
    async fn a_later_step_reads_the_output_of_an_earlier_one() {
        let db = db().await;
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "first", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "one" } },
                    { "id": "echo", "kind": "condition",
                      "when": { "steps.first.ok": { "eq": true } } },
                    { "id": "second", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "two" } }
                ]
            }),
        )
        .await;
        grant(&db, &flow_id, "notes.note.add").await;

        store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        // The declarative command answers `{ok:true}`; the guard reads it back through the scope.
        assert_eq!(notes(&db).await, vec!["one", "two"]);
        let (_, steps) = store::get_run(&db, HUB, &run_of(&db, &flow_id).await.id)
            .await
            .unwrap();
        assert_eq!(steps.len(), 3);
        assert_eq!(steps[0].status, "done");
        assert!(steps[0].output.get("ok").is_some(), "the output is kept: {:?}", steps[0].output);
    }

    #[tokio::test]
    async fn a_delay_parks_the_run_as_a_row_and_resumes_after_it() {
        let db = db().await;
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "wait", "kind": "delay", "seconds": 3600 },
                    { "id": "write", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "later" } }
                ]
            }),
        )
        .await;
        grant(&db, &flow_id, "notes.note.add").await;
        store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();

        tick(&db, &registry(), HUB).await.unwrap();
        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_SLEEPING);
        assert!(run.wake_at.is_some());
        assert!(notes(&db).await.is_empty(), "the next step has not run");

        // Time passes: the wake instant is the only thing standing in the way.
        let mut p = Params::new();
        p.insert("id".into(), json!(run.id));
        db.execute(
            "UPDATE _flow_runs SET wake_at = '2020-01-01T00:00:00+00:00' WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        assert_eq!(notes(&db).await, vec!["later"]);
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_DONE);
    }

    #[tokio::test]
    async fn revoking_a_grant_mid_run_stops_the_next_step() {
        let db = db().await;
        let reg = registry();
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "one", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "one" } },
                    { "id": "wait", "kind": "delay", "seconds": 1 },
                    { "id": "two", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "two" } }
                ]
            }),
        )
        .await;
        grant(&db, &flow_id, "notes.note.add").await;
        let run_id =
            store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
                .await
                .unwrap();

        tick(&db, &reg, HUB).await.unwrap();
        assert_eq!(notes(&db).await, vec!["one"], "the first step ran");

        // The owner revokes while the run sleeps. This is the guarantee: effective at the NEXT
        // step, not at some restart.
        grants::replace(&db, HUB, &flow_id, &reg, &[], "hub_user:2").await.unwrap();
        let mut p = Params::new();
        p.insert("id".into(), json!(run_id));
        db.execute(
            "UPDATE _flow_runs SET wake_at = '2020-01-01T00:00:00+00:00' WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
        tick(&db, &reg, HUB).await.unwrap();

        assert_eq!(notes(&db).await, vec!["one"], "the second step never ran");
        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_FAILED);
        assert!(run.last_error.contains(grants::ERR_GRANT_DENIED), "{}", run.last_error);
    }

    #[tokio::test]
    async fn a_run_whose_flow_was_disabled_mid_flight_is_cancelled() {
        let db = db().await;
        let flow_id = flow(&db, one_command_flow()).await;
        grant(&db, &flow_id, "notes.note.add").await;
        store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();

        store::update(
            &db,
            HUB,
            &flow_id,
            &NewFlow {
                name: "F".into(),
                enabled: false,
                definition: one_command_flow(),
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        assert!(notes(&db).await.is_empty(), "a hub does not act on a withdrawn instruction");
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_CANCELLED);
    }

    #[tokio::test]
    async fn a_step_that_committed_but_lost_its_output_stops_the_run_instead_of_reading_null() {
        let db = db().await;
        let flow_id = flow(&db, one_command_flow()).await;
        grant(&db, &flow_id, "notes.note.add").await;
        let run_id = store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();
        // Exactly the state a kill between the command's transaction and the output write leaves.
        let mut p = Params::new();
        p.insert("id".into(), json!(new_id()));
        p.insert("hub".into(), json!(HUB));
        p.insert("run".into(), json!(run_id));
        p.insert("now".into(), json!(now_rfc3339()));
        db.execute(
            "INSERT INTO _flow_run_steps (id, hub_id, run_id, step_index, step_id, kind, status, \
                                          input, output, error, created_at) \
             VALUES (:id, :hub, :run, 0, 'write', 'command', 'committed', '{}', '{}', '', :now)",
            &p,
        )
        .await
        .unwrap();

        tick(&db, &registry(), HUB).await.unwrap();

        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_FAILED);
        assert!(run.last_error.contains(ERR_STEP_OUTPUT_LOST), "{}", run.last_error);
    }

    #[tokio::test]
    async fn the_row_a_flow_writes_is_scoped_to_its_hub_and_attributed_to_the_flow() {
        let db = db().await;
        db.execute_batch(
            "CREATE TABLE IF NOT EXISTS audited (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, \
             created_by TEXT NOT NULL);",
        )
        .await
        .unwrap();
        let mut reg = registry();
        reg.commands.insert(
            "notes.audited.add".into(),
            test_support::command(
                "notes",
                "notes.add_note",
                "INSERT INTO audited (id, hub_id, created_by) \
                 VALUES (:new_id, :hub_id, :current_user_id);",
                vec![],
            ),
        );
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [{ "id": "w", "kind": "command", "command": "notes.audited.add" }]
            }),
        )
        .await;
        grants::replace(
            &db,
            HUB,
            &flow_id,
            &reg,
            &[(GrantKind::Command, "notes.audited.add".into())],
            "hub_user:1",
        )
        .await
        .unwrap();

        store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();
        tick(&db, &reg, HUB).await.unwrap();

        let rows = db
            .query("SELECT hub_id, created_by FROM audited", &Params::new())
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["hub_id"], json!(HUB), "the tenant is never negotiable");
        assert_eq!(
            rows[0]["created_by"],
            json!(format!("flow:{flow_id}")),
            "the audit says a flow did this, and which one"
        );
    }
}
