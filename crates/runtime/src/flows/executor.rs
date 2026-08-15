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
//! [`PendingIo`] is that seam, and `crates/server/src/flow_io.rs` is the far side of it. `http`
//! crossed with hub#662 and `ai` with hub#665. `notify` (hub#821) deliberately does not: it
//! resolves its recipient with a local read and QUEUES a host-notify event, and the outbox relay —
//! which has had the retries, the backoff, the dead-letter and the transport since ADR-0012 — is
//! what talks to the network.
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
use crate::flows::http::HttpRequest;
use crate::flows::{grants, http, notify, query, store, triggers};
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

pub const ERR_IO_STEP_GONE: &str = "flow.io_step_gone";

/// Step statuses inside a run.
const STEP_COMMITTED: &str = "committed";
/// An I/O step that has left the runtime and not come back yet (hub#662).
const STEP_RUNNING: &str = "running";
const STEP_DONE: &str = "done";
const STEP_FAILED: &str = "failed";
const STEP_SLEEPING: &str = "sleeping";
const STEP_STOPPED: &str = "stopped";
/// hub#665 — an agent step whose proposed write is waiting for a person to decide.
const STEP_WAITING_APPROVAL: &str = "waiting_approval";

/// **The claim → I/O → complete seam.** The tick produces one of these instead of performing the
/// call; the server performs it outside the lock and hands the result back with
/// [`complete_io`].
///
/// It is deliberately an enum of the two I/O kinds that cross it and not a generic "do this HTTP
/// thing": each one has different limits, a different allow-list and a different grant, and
/// flattening them would make the agent runner (hub#665) look like an HTTP call with a longer
/// timeout, which is exactly what it is not. `notify` is NOT one of them (hub#821): it queues a
/// host-notify event and the outbox relay — which already retries, backs off and dead-letters — is
/// what reaches the network.
///
/// **The run stays claimed while its I/O is in flight** — status `running`, lease held — so the
/// next tick skips it and advances everybody else. If the process dies mid-call the lease expires,
/// the run is reclaimed and the step is re-issued: an `http` step is **at-least-once**, like every
/// other outbound thing in this hub (the outbox, the print queue). A step that must not happen
/// twice is a step whose endpoint takes an idempotency key, and the flow author puts it in the
/// document.
#[derive(Debug, Clone, PartialEq)]
pub enum PendingIo {
    /// hub#662 — `http`, already allow-listed and with its secrets substituted.
    Http {
        run_id: String,
        step_id: String,
        request: HttpRequest,
    },
    /// hub#665 — the server-side agent runner.
    Ai { run_id: String, step_id: String },
}

impl PendingIo {
    /// The run this I/O belongs to, for a caller that only needs to route it.
    pub fn run_id(&self) -> &str {
        match self {
            PendingIo::Http { run_id, .. } | PendingIo::Ai { run_id, .. } => run_id,
        }
    }

    pub fn step_id(&self) -> &str {
        match self {
            PendingIo::Http { step_id, .. } | PendingIo::Ai { step_id, .. } => step_id,
        }
    }
}

/// What the server hands back once the I/O is over. The runtime does not know (or care) whether it
/// was an HTTP call or an agent turn: it gets an output to feed the next step, or a reason the run
/// stopped.
#[derive(Debug, Clone, PartialEq)]
pub enum IoResult {
    Done(Json),
    Failed(String),
    /// hub#665 — the agent proposed a WRITE and `policy` says a person decides (ADR-0283 D3). The
    /// step keeps what the turn produced so far and the run leaves the queue until the approval is
    /// decided; the payload it will run lives in `_flow_approvals`, not here.
    ///
    /// A third answer and not a `Failed`, because nothing went wrong and the run is not over.
    AwaitingApproval(Json),
    /// hub#665 — a person REJECTED the proposal. Nothing ran, and the run stops: the steps written
    /// after an agent step assumed it acted. `cancelled` and not `failed` — a person stopping the
    /// hub is the design working.
    Cancelled(String),
}

/// What one tick did, so the caller can log it without a second query.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct TickReport {
    /// Runs started by a clock trigger this tick.
    pub started: usize,
    /// Runs advanced (claimed and moved at least one step).
    pub advanced: usize,
    /// I/O the server should perform outside the lock, then complete with [`complete_io`].
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
        match advance_run(db, registry, hub_id, &run).await {
            Ok(Some(pending)) => report.pending_io.push(pending),
            Ok(None) => {}
            Err(e) => eprintln!("flows: run {}: {e}", run["id"].as_str().unwrap_or("?")),
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
               RETURNING id, flow_id, current_step, input, vars, depth, attempts, parent_event_id";
    let res = db.query(sql, &p).await?;
    Ok(res.rows.into_iter().next())
}

/// Advances one claimed run by up to [`MAX_STEPS_PER_TICK`] steps, and stops early when it reaches
/// a step whose work belongs outside the lock — returning it as a [`PendingIo`].
async fn advance_run(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    run: &Json,
) -> Result<Option<PendingIo>> {
    let run_id = run["id"].as_str().unwrap_or_default().to_string();
    let flow_id = run["flow_id"].as_str().unwrap_or_default().to_string();
    let depth = run["depth"].as_i64().unwrap_or(0);
    // The event this run was born from. It travels into every command the run executes so the
    // events THOSE emit can name it too (hub#666): without it the chain breaks in the middle, at
    // precisely the point where the flow did something to somebody else's module.
    let parent_event_id = run["parent_event_id"].as_str().unwrap_or_default().to_string();
    let mut index = run["current_step"].as_i64().unwrap_or(0);
    let input: Json = parse_json(run["input"].as_str().unwrap_or("{}"));
    let mut vars: Json = parse_json(run["vars"].as_str().unwrap_or("{}"));

    // A step that committed but never recorded its output: the process died between the two
    // writes. Continuing would read `steps.<id>` as null in every later step.
    if let Some(step_id) = interrupted_step(db, hub_id, &run_id).await? {
        return finish(
            db,
            hub_id,
            &run_id,
            store::STATUS_FAILED,
            &format!(
                "{ERR_STEP_OUTPUT_LOST}: step `{step_id}` committed its effects but its output was \
                 lost to a restart; the run is stopped rather than continued with a null it would \
                 read as a value"
            ),
        )
        .await
        .map(|()| None);
    }

    // The definition is read fresh, and a flow that was disabled or deleted mid-run stops here.
    // A run outliving its flow would be a hub acting on an instruction its owner withdrew.
    let flow = match store::get(db, hub_id, &flow_id).await {
        Ok(flow) if flow.enabled => flow,
        Ok(_) => {
            return finish(
                db,
                hub_id,
                &run_id,
                store::STATUS_CANCELLED,
                "the flow was disabled while this run was in flight",
            )
            .await
            .map(|()| None)
        }
        Err(_) => {
            return finish(
                db,
                hub_id,
                &run_id,
                store::STATUS_CANCELLED,
                &format!("{ERR_FLOW_GONE}: the flow was deleted while this run was in flight"),
            )
            .await
            .map(|()| None)
        }
    };
    // The document is validated before it is ever stored, so this only fires when the stored one
    // stopped being readable BY THIS BINARY — a rollback below the `schema_version` that wrote it.
    // Failing the run beats propagating: an error here would leave the run `running`, reclaimed
    // every time its lease expires, forever.
    let def = match FlowDefinition::parse(&flow.definition) {
        Ok(def) => def,
        Err(e) => {
            return finish(db, hub_id, &run_id, store::STATUS_FAILED, &format!("{e}"))
                .await
                .map(|()| None)
        }
    };

    for _ in 0..MAX_STEPS_PER_TICK {
        let Some(step) = def.steps.get(index as usize) else {
            return finish(db, hub_id, &run_id, store::STATUS_DONE, "").await.map(|()| None);
        };
        let scope = json!({ "input": input, "steps": vars.get("steps").cloned().unwrap_or(json!({})) });

        match run_step(
            db,
            registry,
            hub_id,
            &flow_id,
            &run_id,
            &parent_event_id,
            depth,
            index,
            step,
            &scope,
        )
        .await?
        {
            Outcome::Continue { output } => {
                set_step_output(&mut vars, &step.id, output);
                index += 1;
                persist_vars(db, hub_id, &run_id, index, &vars).await?;
            }
            Outcome::Io { pending } => {
                // The run keeps its lease: it is invisible to the next tick until the server
                // completes it, and every OTHER run carries on being advanced meanwhile.
                return Ok(Some(pending));
            }
            Outcome::Stopped => {
                return finish(db, hub_id, &run_id, store::STATUS_DONE, "").await.map(|()| None)
            }
            Outcome::Sleep { wake_at } => {
                return sleep_until(db, hub_id, &run_id, &wake_at).await.map(|()| None)
            }
            Outcome::Failed { error } => {
                // v1 is `on_error: "stop"` (ADR-0283 §1): a linear flow has nowhere else to go,
                // and retrying a business command by itself is how a sale gets charged twice.
                return finish(db, hub_id, &run_id, store::STATUS_FAILED, &error).await.map(|()| None);
            }
        }
    }

    // Budget spent with steps left: back in the queue, lease released, resumes next tick.
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _flow_runs SET status = 'pending', claim_expires_at = NULL, updated_at = :now \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(None)
}

enum Outcome {
    Continue { output: Json },
    /// The step's work happens outside the lock (`http` and `ai`). The tick hands it to the server
    /// and this run pauses exactly here, claimed, until it comes back.
    Io { pending: PendingIo },
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
    parent_event_id: &str,
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

        // **A read the flow performs itself** (hub#954). Like `condition`, it does no I/O and does
        // not cross the `PendingIo` seam: it is a local `SELECT` with the flow's own context, and
        // the ceiling on its rows is what keeps it a step the tick can afford under the global
        // lock.
        //
        // It writes NOTHING, and that is why it needs no `committed` window the way a `command`
        // does: a run reclaimed after an expired lease simply reads again, which is safe by
        // construction (flows.md §13.4 is about writes).
        StepSpec::Query(_) => {
            match query::run(db, registry, hub_id, flow_id, run_id, step, scope).await {
                Ok(query::Read {
                    recorded_input,
                    output,
                }) => {
                    write_step(
                        db, hub_id, run_id, index, step, STEP_DONE, &recorded_input, &output, "",
                        &now,
                    )
                    .await?;
                    Ok(Outcome::Continue { output })
                }
                Err(e) => {
                    // Denied, or a read that failed. Nothing was written by it either way, and
                    // the run says why at the step instead of carrying a null forward.
                    let error = format!("step `{}`: {}", step.id, error_text(&e));
                    write_step(
                        db, hub_id, run_id, index, step, STEP_FAILED, &json!({}), &json!({}),
                        &error, &now,
                    )
                    .await?;
                    Ok(Outcome::Failed { error })
                }
            }
        }

        StepSpec::Delay { seconds, until } => {
            let wake_at = match (seconds, until) {
                (Some(s), _) => (chrono::Utc::now() + chrono::Duration::seconds(*s)).to_rfc3339(),
                (None, Some(path)) => {
                    let value = def::resolve(&json!(path), scope);
                    // **Normalised to UTC before it is persisted** (hub#970): `wake_sleeping`
                    // compares this against `:now` as TEXT, so an instant that keeps the offset it
                    // was written in sorts by its wall clock instead of by when it happens — two
                    // hours late in Spanish summer, and EARLY with a negative offset.
                    match value.as_str().and_then(|s| {
                        chrono::DateTime::parse_from_rfc3339(s)
                            .ok()
                            .map(|d| store::to_utc_rfc3339(&d))
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
            persist_step_index(db, hub_id, run_id, index + 1).await?;
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
            })
            // Correlation (hub#666): every event this command emits is sealed with the run that
            // caused it AND with the event the run was born from, so «why does this row exist?»
            // ends at the sale instead of at «a flow did it».
            .caused_by_event(parent_event_id);

            // The step row and the run's advance ride in the command's transaction: effects and
            // bookkeeping commit together, so a crash never re-runs a command that already ran.
            let extra = [
                write_step_op(
                    hub_id, run_id, index, step, STEP_COMMITTED, &resolved_json, &json!({}), "",
                    &now,
                ),
                advance_index_op(hub_id, run_id, index + 1, &now),
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
                    complete_step(db, hub_id, run_id, index, &output, &now).await?;
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

        // **The claim half of claim → I/O → complete** (hub#662). Everything that decides WHETHER
        // this call may happen — the allow-list, the secrets, the URL — happens here, under the
        // lock, against the state of this instant. What crosses the seam is a request with nothing
        // left to decide.
        StepSpec::Http { .. } => {
            let authority = grants::authority(db, hub_id, flow_id).await?;
            match http::prepare(db, hub_id, flow_id, step, scope, &authority).await {
                Ok(prepared) => {
                    // The step is written BEFORE the call leaves, with the redacted request: if
                    // this hub dies mid-call, the run history still says what it was doing.
                    write_step(
                        db,
                        hub_id,
                        run_id,
                        index,
                        step,
                        STEP_RUNNING,
                        &prepared.recorded_input,
                        &json!({}),
                        "",
                        &now,
                    )
                    .await?;
                    Ok(Outcome::Io {
                        pending: PendingIo::Http {
                            run_id: run_id.to_string(),
                            step_id: step.id.clone(),
                            request: prepared.request,
                        },
                    })
                }
                Err(e) => {
                    // Denied, un-callable or missing a secret: nothing left the hub, and the run
                    // says why. The message is already redacted by `http::prepare`.
                    let error = format!("step `{}`: {}", step.id, error_text(&e));
                    write_step(
                        db, hub_id, run_id, index, step, STEP_FAILED, &json!({}), &json!({}),
                        &error, &now,
                    )
                    .await?;
                    Ok(Outcome::Failed { error })
                }
            }
        }

        // **The claim half, for an agent turn** (hub#665). Nothing is called from here: the step
        // is written `running`, the run keeps its lease so the next tick skips it, and the work
        // goes back to the server, which performs it with NO lock held. A 60 s LLM turn inside
        // this lock would freeze every till in the hub.
        //
        // Unlike `http`, nothing is PREPARED here: what the model may be offered comes from
        // `assistant::assemble_tools`, which lives in `crates/server` — the runtime has no network
        // and no assistant. The server reads the step back through `flows::agent::prepare`.
        StepSpec::Ai(_) => {
            write_step(
                db, hub_id, run_id, index, step, STEP_RUNNING, &json!({}), &json!({}), "", &now,
            )
            .await?;
            Ok(Outcome::Io {
                pending: PendingIo::Ai {
                    run_id: run_id.to_string(),
                    step_id: step.id.clone(),
                },
            })
        }

        // **The message to a customer** (hub#821). The only I/O step that does NOT cross the
        // `PendingIo` seam: it resolves the recipient with a local read and QUEUES a host-notify
        // event, and the outbox relay — retries, backoff, dead-letter, transport — is what talks to
        // the network. Reaching it from here would mean building all of that again beside it.
        //
        // The queue row, the step and the run's advance commit in ONE transaction, exactly like a
        // `command` step: a runtime that dies mid-step never sends the same reminder twice. The
        // step is written `committed` inside it and completed with its output right after, so the
        // crash window between the two is the one `interrupted_step` already fails the run on.
        StepSpec::Notify(_) => {
            let authority = grants::authority(db, hub_id, flow_id).await?;
            match notify::prepare(
                db, registry, hub_id, flow_id, run_id, parent_event_id, depth, step, scope,
                &authority,
            )
            .await
            {
                Ok(notify::Prepared {
                    queue_op,
                    recorded_input,
                    output,
                }) => {
                    let ops = [
                        queue_op,
                        write_step_op(
                            hub_id,
                            run_id,
                            index,
                            step,
                            STEP_COMMITTED,
                            &recorded_input,
                            &json!({}),
                            "",
                            &now,
                        ),
                        advance_index_op(hub_id, run_id, index + 1, &now),
                    ];
                    db.execute_tx(&ops).await?;
                    complete_step(db, hub_id, run_id, index, &output, &now).await?;
                    Ok(Outcome::Continue { output })
                }
                Err(e) => {
                    // Denied, nobody to write to, or a column that is not an address: NOTHING was
                    // queued, and the run says why — at the step, not eight retries later in a
                    // dead-letter.
                    let error = format!("step `{}`: {}", step.id, error_text(&e));
                    write_step(
                        db, hub_id, run_id, index, step, STEP_FAILED, &json!({}), &json!({}),
                        &error, &now,
                    )
                    .await?;
                    Ok(Outcome::Failed { error })
                }
            }
        }
    }
}

/// The id of a step this run committed without recording its output, if any.
async fn interrupted_step(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
) -> Result<Option<String>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(run_id));
    let res = db
        .query(
            "SELECT step_id FROM _flow_run_steps \
             WHERE run_id = :run_id AND hub_id = :hub_id AND status = 'committed' \
               AND deleted_at IS NULL \
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
    hub_id: &str,
    run_id: &str,
    index: i64,
    output: &Json,
    now: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(run_id));
    p.insert("step_index".into(), json!(index));
    p.insert("output".into(), json!(output.to_string()));
    p.insert("now".into(), json!(now));
    db.execute(
        "UPDATE _flow_run_steps SET status = 'done', output = :output, finished_at = :now \
         WHERE run_id = :run_id AND hub_id = :hub_id AND step_index = :step_index \
           AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

fn advance_index_op(hub_id: &str, run_id: &str, next_index: i64, now: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("step".into(), json!(next_index));
    p.insert("now".into(), json!(now));
    (
        "UPDATE _flow_runs SET current_step = :step, updated_at = :now \
          WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL"
            .to_string(),
        p,
    )
}

async fn persist_step_index(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    next: i64,
) -> Result<()> {
    let (sql, p) = advance_index_op(hub_id, run_id, next, &now_rfc3339());
    db.execute(&sql, &p).await?;
    Ok(())
}

async fn persist_vars(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    next_index: i64,
    vars: &Json,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("step".into(), json!(next_index));
    p.insert("vars".into(), json!(vars.to_string()));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _flow_runs SET current_step = :step, vars = :vars, updated_at = :now \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

async fn sleep_until(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    wake_at: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("wake_at".into(), json!(wake_at));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _flow_runs SET status = 'sleeping', wake_at = :wake_at, \
                               claim_expires_at = NULL, updated_at = :now \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

async fn finish(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    status: &str,
    error: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(status));
    p.insert("error".into(), json!(error));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _flow_runs SET status = :status, last_error = :error, finished_at = :now, \
                               claim_expires_at = NULL, updated_at = :now \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
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
    format!("{command}: {}", error_text(error))
}

/// A runtime error as a run records it: the stable code AND the prose, for the same reason.
fn error_text(error: &RuntimeError) -> String {
    match error {
        RuntimeError::Domain { code, message } => format!("{code}: {message}"),
        other => format!("{other}"),
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

/// **The complete half of claim → I/O → complete** (hub#662): the server hands back what the call
/// produced and the run carries on — or stops.
///
/// Cheap and locked, like the claim half. What it does NOT do is trust the caller: it re-reads the
/// run and only accepts a result for the step the run is actually waiting on. Two things make that
/// necessary, and both of them happen:
///
/// - the lease can expire mid-call (a slow endpoint, a paused container), the run gets reclaimed
///   and the step re-issued — so a late answer to the FIRST attempt must not overwrite the second;
/// - the flow can be deleted or disabled while its request is in flight, and a run whose flow is
///   gone must not resume just because a server answered.
///
/// In both cases the result is dropped with a log line, which is the honest outcome: the call did
/// happen (it is at-least-once, `PendingIo` says so), but nothing depends on its output any more.
pub async fn complete_io(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    step_id: &str,
    result: IoResult,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT current_step, vars, status FROM _flow_runs \
             WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
            &p,
        )
        .await?;
    let Some(run) = res.rows.first() else {
        return Err(RuntimeError::Domain {
            code: ERR_IO_STEP_GONE.to_string(),
            message: format!("run `{run_id}` no longer exists; its I/O result is dropped"),
        });
    };
    let index = run["current_step"].as_i64().unwrap_or(0);
    let mut vars: Json = parse_json(run["vars"].as_str().unwrap_or("{}"));

    // The step this run is waiting on, and its status. Anything else means the answer is stale.
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(run_id));
    p.insert("step_index".into(), json!(index));
    let step_row = db
        .query(
            "SELECT step_id, status FROM _flow_run_steps \
             WHERE run_id = :run_id AND hub_id = :hub_id AND step_index = :step_index \
               AND deleted_at IS NULL",
            &p,
        )
        .await?;
    // In flight, or parked for a person (hub#665) — the approval path completes this very step
    // hours later, and it is still the step the run is waiting on.
    let waiting_on = step_row.rows.first().filter(|r| {
        r["step_id"].as_str() == Some(step_id)
            && matches!(
                r["status"].as_str(),
                Some(STEP_RUNNING) | Some(STEP_WAITING_APPROVAL)
            )
    });
    if waiting_on.is_none() {
        eprintln!(
            "flows: run {run_id}: a result for step `{step_id}` arrived late (the run has moved \
             on); it is dropped rather than applied"
        );
        return Ok(());
    }

    let now = now_rfc3339();
    match result {
        IoResult::Done(output) => {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!(hub_id));
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

            set_step_output(&mut vars, step_id, output);
            persist_vars(db, hub_id, run_id, index + 1, &vars).await?;
            // Back in the queue with the lease released: the next tick picks it up and runs the
            // rest of the flow under the lock, where it belongs.
            let mut p = Params::new();
            p.insert("id".into(), json!(run_id));
            p.insert("hub_id".into(), json!(hub_id));
            p.insert("now".into(), json!(now));
            db.execute(
                "UPDATE _flow_runs SET status = 'pending', claim_expires_at = NULL, \
                                       updated_at = :now \
                 WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
                &p,
            )
            .await?;
        }
        IoResult::Failed(error) => {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!(hub_id));
            p.insert("run_id".into(), json!(run_id));
            p.insert("step_index".into(), json!(index));
            p.insert("error".into(), json!(error));
            p.insert("now".into(), json!(now));
            db.execute(
                "UPDATE _flow_run_steps SET status = 'failed', error = :error, finished_at = :now \
                 WHERE run_id = :run_id AND hub_id = :hub_id AND step_index = :step_index \
                   AND deleted_at IS NULL",
                &p,
            )
            .await?;
            // v1 is `on_error: "stop"` — the same answer a failed command gets.
            finish(db, hub_id, run_id, store::STATUS_FAILED, &error).await?;
        }
        // The turn stopped on a write a person has to authorise. What it produced so far is kept
        // on the step, so a decision taken hours later completes the WHOLE turn and not just its
        // ending; and the run leaves the queue — `waiting_approval` is not a status
        // `claim_next_run` selects, so no amount of ticking smuggles the write through.
        IoResult::AwaitingApproval(partial) => {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!(hub_id));
            p.insert("run_id".into(), json!(run_id));
            p.insert("step_index".into(), json!(index));
            p.insert("output".into(), json!(partial.to_string()));
            p.insert("status".into(), json!(STEP_WAITING_APPROVAL));
            db.execute(
                "UPDATE _flow_run_steps SET status = :status, output = :output \
                 WHERE run_id = :run_id AND hub_id = :hub_id AND step_index = :step_index \
                   AND deleted_at IS NULL",
                &p,
            )
            .await?;
            let mut p = Params::new();
            p.insert("id".into(), json!(run_id));
            p.insert("hub_id".into(), json!(hub_id));
            p.insert("status".into(), json!(store::STATUS_WAITING_APPROVAL));
            p.insert("now".into(), json!(now));
            db.execute(
                "UPDATE _flow_runs SET status = :status, claim_expires_at = NULL, \
                                       updated_at = :now \
                 WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
                &p,
            )
            .await?;
        }
        IoResult::Cancelled(reason) => {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!(hub_id));
            p.insert("run_id".into(), json!(run_id));
            p.insert("step_index".into(), json!(index));
            p.insert("now".into(), json!(now));
            db.execute(
                "UPDATE _flow_run_steps SET status = 'stopped', finished_at = :now \
                 WHERE run_id = :run_id AND hub_id = :hub_id AND step_index = :step_index \
                   AND deleted_at IS NULL",
                &p,
            )
            .await?;
            finish(db, hub_id, run_id, store::STATUS_CANCELLED, &reason).await?;
        }
    }
    Ok(())
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
        // The read a `query` step performs (hub#954). Same module, same permission: what opens it
        // for a flow is the grant, not the role of whoever wrote the flow.
        reg.queries.insert(
            "notes.note.find".into(),
            test_support::query(
                "notes",
                "notes.view_note",
                "SELECT id, text FROM note WHERE text = :text ORDER BY id",
            ),
        );
        reg
    }

    async fn flow(db: &dyn DatabaseAdapter, definition: Json) -> String {
        store::create(
            db,
            HUB,
            &registry(),
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
        store::list_runs(db, HUB, flow_id, 10, None).await.unwrap().remove(0)
    }

    async fn http_grant(db: &dyn DatabaseAdapter, flow_id: &str, pattern: &str) {
        grants::replace(
            db,
            HUB,
            flow_id,
            &registry(),
            &[(GrantKind::Http, pattern.to_string())],
            "hub_user:1",
        )
        .await
        .unwrap();
    }

    /// One `http` step, nothing else — the smallest flow that tries to leave the hub.
    fn http_flow(url: &str) -> Json {
        json!({
            "schema_version": 1,
            "steps": [{ "id": "call", "kind": "http", "url": url }]
        })
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

    // ── the `query` step, end to end (hub#954) ────────────────────────────────────────────────

    /// The whole point of the step: a later step maps a value the flow READ, with no model in the
    /// middle. The read is a field at the root of `steps.<id>` because that is the only shape the
    /// mapping language can walk.
    #[tokio::test]
    async fn a_query_step_reads_and_the_next_step_maps_what_it_found() {
        let db = db().await;
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "write", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "one" } },
                    { "id": "look", "kind": "query", "query": "notes.note.find",
                      "params": { "text": "one" } },
                    { "id": "guard", "kind": "condition",
                      "when": { "steps.look.found": { "eq": true } } },
                    { "id": "echo", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "seen {{steps.look.text}} x{{steps.look.count}}" } }
                ]
            }),
        )
        .await;
        grants::replace(
            &db,
            HUB,
            &flow_id,
            &registry(),
            &[
                (GrantKind::Command, "notes.note.add".to_string()),
                (GrantKind::Query, "notes.note.find".to_string()),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();

        store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        assert_eq!(notes(&db).await, vec!["one", "seen one x1"]);
        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_DONE, "{}", run.last_error);
        let (_, steps) = store::get_run(&db, HUB, &run.id).await.unwrap();
        assert_eq!(steps[1].kind, "query");
        assert_eq!(steps[1].status, "done");
        assert_eq!(steps[1].output["found"], json!(true));
        assert_eq!(steps[1].output["count"], json!(1));
        assert_eq!(
            steps[1].input["query"],
            json!("notes.note.find"),
            "the history says which read was performed: {:?}",
            steps[1].input
        );
    }

    /// A read nobody granted does not happen, and the run stops there saying so — the same default
    /// answer a `command` step gets. The grant is re-read at the instant of the read, so revoking
    /// it mid-run is what stops the next step.
    #[tokio::test]
    async fn without_a_query_grant_nothing_is_read_and_the_run_fails_naming_it() {
        let db = db().await;
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "look", "kind": "query", "query": "notes.note.find",
                      "params": { "text": "one" } },
                    { "id": "echo", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "should not happen" } }
                ]
            }),
        )
        .await;
        // The COMMAND is granted and the read is not: the refusal is about the read.
        grant(&db, &flow_id, "notes.note.add").await;

        store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        assert!(notes(&db).await.is_empty(), "the run stopped at the read");
        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_FAILED);
        assert!(
            run.last_error.contains(grants::ERR_GRANT_DENIED)
                && run.last_error.contains("notes.note.find"),
            "the failure names the missing grant: {}",
            run.last_error
        );
    }

    /// Zero rows is a fact, not a failure: the run carries on and a `condition` decides. That is
    /// what makes «avísame SI hay stock bajo» writable — Zapier resolves the same case with a
    /// Filter, and the step that failed on empty would make the sentence impossible.
    #[tokio::test]
    async fn a_read_that_finds_nothing_lets_a_condition_decide_instead_of_failing() {
        let db = db().await;
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "look", "kind": "query", "query": "notes.note.find",
                      "params": { "text": "nobody" }, "result": "count" },
                    { "id": "guard", "kind": "condition",
                      "when": { "steps.look.found": { "eq": true } } },
                    { "id": "echo", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "found something" } }
                ]
            }),
        )
        .await;
        grants::replace(
            &db,
            HUB,
            &flow_id,
            &registry(),
            &[
                (GrantKind::Command, "notes.note.add".to_string()),
                (GrantKind::Query, "notes.note.find".to_string()),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();

        store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        assert!(notes(&db).await.is_empty(), "the guard stopped it, the read did not");
        let run = run_of(&db, &flow_id).await;
        assert_eq!(
            run.status,
            store::STATUS_DONE,
            "an empty read is the flow working: {}",
            run.last_error
        );
        let (_, steps) = store::get_run(&db, HUB, &run.id).await.unwrap();
        assert_eq!(steps[0].output, json!({ "count": 0, "found": false }));
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
            &registry(),
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

    // ── the `http` step: claim → I/O → complete (hub#662) ─────────────────────────────────────

    #[tokio::test]
    async fn without_a_grant_an_http_step_never_becomes_a_request() {
        let db = db().await;
        let flow_id = flow(&db, http_flow("https://api.example.com/v1/ping")).await;
        start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1").await.unwrap();

        let report = tick(&db, &registry(), HUB).await.unwrap();

        assert!(
            report.pending_io.is_empty(),
            "nothing crossed the seam, so the server has nothing to send"
        );
        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_FAILED);
        assert!(
            run.last_error.contains(grants::ERR_GRANT_DENIED),
            "the run says which permission was missing: {}",
            run.last_error
        );
    }

    /// The twin of the test above, and the reason its zero means anything: the SAME flow, the same
    /// tick, one grant more — and exactly one request comes out.
    #[tokio::test]
    async fn with_the_grant_the_tick_hands_over_exactly_one_request_with_the_url_templated() {
        let db = db().await;
        let flow_id = flow(&db, http_flow("https://api.example.com/v1/ping?who={{input.who}}")).await;
        http_grant(&db, &flow_id, "https://api.example.com/v1/*").await;
        start_manual_run(&db, HUB, &flow_id, &json!({ "who": "marta" }), "hub_user:1")
            .await
            .unwrap();

        let report = tick(&db, &registry(), HUB).await.unwrap();

        assert_eq!(report.pending_io.len(), 1, "one step, one request");
        let PendingIo::Http { step_id, request, .. } = &report.pending_io[0] else {
            panic!("an http step becomes an http PendingIo");
        };
        assert_eq!(step_id, "call");
        assert_eq!(request.url.as_str(), "https://api.example.com/v1/ping?who=marta");
        assert_eq!(request.method, "GET");

        // While it is out there the run is invisible: a second tick does not issue it again.
        let again = tick(&db, &registry(), HUB).await.unwrap();
        assert!(
            again.pending_io.is_empty(),
            "the lease is held for the length of the call, so nothing is sent twice"
        );
    }

    #[tokio::test]
    async fn the_result_of_a_call_is_readable_by_the_steps_after_it() {
        let db = db().await;
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "call", "kind": "http", "url": "https://api.example.com/v1/who" },
                    { "id": "write", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "hello {{steps.call.body_json.name}} ({{steps.call.status}})" } }
                ]
            }),
        )
        .await;
        http_grant(&db, &flow_id, "https://api.example.com/v1/*").await;
        grants::replace(
            &db,
            HUB,
            &flow_id,
            &registry(),
            &[
                (GrantKind::Http, "https://api.example.com/v1/*".into()),
                (GrantKind::Command, "notes.note.add".into()),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1").await.unwrap();

        tick(&db, &registry(), HUB).await.unwrap();
        complete_io(
            &db,
            HUB,
            &run_id,
            "call",
            IoResult::Done(json!({ "status": 200, "body_json": { "name": "Marta" } })),
        )
        .await
        .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        assert_eq!(notes(&db).await, vec!["hello Marta (200)"]);
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_DONE);
    }

    #[tokio::test]
    async fn a_call_that_failed_stops_the_run_and_the_steps_after_it_never_happen() {
        let db = db().await;
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [
                    { "id": "call", "kind": "http", "url": "https://api.example.com/v1/who" },
                    { "id": "write", "kind": "command", "command": "notes.note.add",
                      "params": { "text": "never" } }
                ]
            }),
        )
        .await;
        grants::replace(
            &db,
            HUB,
            &flow_id,
            &registry(),
            &[
                (GrantKind::Http, "https://api.example.com/v1/*".into()),
                (GrantKind::Command, "notes.note.add".into()),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1").await.unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        complete_io(
            &db,
            HUB,
            &run_id,
            "call",
            IoResult::Failed("flow.http_timeout: no answer in 10 s".into()),
        )
        .await
        .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        // v1 is `on_error: stop`.
        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_FAILED);
        assert!(run.last_error.contains("http_timeout"), "{}", run.last_error);
        assert!(notes(&db).await.is_empty(), "the step after it never ran");
    }

    #[tokio::test]
    async fn a_run_waiting_on_a_call_does_not_hold_up_the_others() {
        // This is the whole reason for claim → I/O → complete: the tick shares the runtime's global
        // lock with the outbox relay and the scheduler, so a run that is out on the network must
        // cost the others nothing.
        let db = db().await;
        let calling = flow(&db, http_flow("https://api.example.com/v1/slow")).await;
        http_grant(&db, &calling, "https://api.example.com/v1/*").await;
        let writing = flow(&db, one_command_flow()).await;
        grant(&db, &writing, "notes.note.add").await;

        start_manual_run(&db, HUB, &calling, &json!({}), "hub_user:1").await.unwrap();
        start_manual_run(&db, HUB, &writing, &json!({ "who": "Marta" }), "hub_user:1")
            .await
            .unwrap();

        // ONE tick.
        let report = tick(&db, &registry(), HUB).await.unwrap();

        assert_eq!(report.pending_io.len(), 1, "the call is on its way");
        assert_eq!(
            notes(&db).await,
            vec!["hello Marta"],
            "and the other run finished in the same tick, without waiting for it"
        );
        assert_eq!(run_of(&db, &writing).await.status, store::STATUS_DONE);
    }

    #[tokio::test]
    async fn a_result_for_a_step_the_run_has_already_moved_past_is_dropped() {
        // The lease can expire mid-call and the step be re-issued; a late answer to the first
        // attempt must not overwrite what the second one did.
        let db = db().await;
        let flow_id = flow(&db, http_flow("https://api.example.com/v1/ping")).await;
        http_grant(&db, &flow_id, "https://api.example.com/v1/*").await;
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1").await.unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        complete_io(&db, HUB, &run_id, "call", IoResult::Done(json!({ "status": 200 })))
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_DONE);

        // The late one.
        complete_io(
            &db,
            HUB,
            &run_id,
            "call",
            IoResult::Failed("a timeout that arrived after the fact".into()),
        )
        .await
        .unwrap();
        assert_eq!(
            run_of(&db, &flow_id).await.status,
            store::STATUS_DONE,
            "a finished run is not re-opened by a late answer"
        );
    }

    #[tokio::test]
    async fn the_run_history_of_a_call_never_holds_the_credential_it_carried() {
        let _lock = crate::secret_box::test_support::env_lock();
        let _key = crate::secret_box::test_support::EnvVarGuard::set(
            &crate::secret_box::test_support::test_key_b64(9),
        );
        let db = db().await;
        crate::flows::secrets::put(&db, HUB, "API_KEY", "sk-live-42", "hub_user:1")
            .await
            .unwrap();
        let flow_id = flow(
            &db,
            json!({
                "schema_version": 1,
                "steps": [{
                    "id": "call", "kind": "http", "method": "POST",
                    "url": "https://api.example.com/v1/send",
                    "headers": { "Authorization": "Bearer {{secret.API_KEY}}" },
                    "body": { "token": "{{secret.API_KEY}}" }
                }]
            }),
        )
        .await;
        http_grant(&db, &flow_id, "https://api.example.com/v1/*").await;
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1").await.unwrap();

        let report = tick(&db, &registry(), HUB).await.unwrap();
        // It really did go out with the credential…
        let PendingIo::Http { request, .. } = &report.pending_io[0] else { panic!() };
        assert!(request.headers.iter().any(|(_, v)| v.contains("sk-live-42")));

        // …and nothing that was written down holds it. Not the step, not the run, not a `{:?}`.
        complete_io(
            &db,
            HUB,
            &run_id,
            "call",
            IoResult::Done(json!({ "status": 200, "body_text": "ok" })),
        )
        .await
        .unwrap();
        let dump = format!(
            "{:?}{:?}{:?}",
            db.query("SELECT * FROM _flow_run_steps", &Params::new()).await.unwrap().rows,
            db.query("SELECT * FROM _flow_runs", &Params::new()).await.unwrap().rows,
            report.pending_io,
        );
        assert!(!dump.contains("sk-live-42"), "the credential is nowhere: {dump}");
        assert!(dump.contains("***"), "and its place is marked: {dump}");
    }

    // ── hub#735: every write of this file names the hub it was asked for ──────────────────────
    //
    // The neighbour in these tests is **alive**: it has its own flow, its own run and its own
    // step, all written through the ordinary doors. A scoping test whose neighbour is an empty
    // hub proves nothing — it cannot tell "the statement filtered" from "there was nothing to
    // hit". Here the neighbour is both the caller (it asks for a write on a run that is not its
    // own, and must get nothing) and a bystander (its own rows must come out untouched).

    /// The neighbour hub, sharing this database with [`HUB`] (the row contract, not the deploy).
    const OTHER: &str = "hub-exec-neighbour";

    async fn flow_for(db: &dyn DatabaseAdapter, hub: &str, definition: Json) -> String {
        store::create(
            db,
            hub,
            &registry(),
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

    /// The whole row, straight from the table — no hub filter, so a test can see what a write
    /// ACTUALLY did rather than what a scoped read is willing to show it.
    async fn raw_run(db: &dyn DatabaseAdapter, run_id: &str) -> Json {
        let mut p = Params::new();
        p.insert("id".into(), json!(run_id));
        db.query("SELECT * FROM _flow_runs WHERE id = :id", &p)
            .await
            .unwrap()
            .rows
            .remove(0)
    }

    async fn raw_steps(db: &dyn DatabaseAdapter, run_id: &str) -> Vec<Json> {
        let mut p = Params::new();
        p.insert("run_id".into(), json!(run_id));
        db.query(
            "SELECT * FROM _flow_run_steps WHERE run_id = :run_id ORDER BY step_index",
            &p,
        )
        .await
        .unwrap()
        .rows
    }

    /// Two hubs, one database, both with a run in flight. Every write helper in this file is
    /// asked, by the WRONG hub, to move a run that belongs to the other — and none of them may.
    #[tokio::test]
    async fn a_write_asked_for_by_another_hub_moves_nothing() {
        let db = db().await;
        let reg = registry();

        // The neighbour is real: its own flow, its own run, its own step row.
        let their_flow = flow_for(&db, OTHER, one_command_flow()).await;
        grants::replace(
            &db,
            OTHER,
            &their_flow,
            &reg,
            &[(GrantKind::Command, "notes.note.add".to_string())],
            "hub_user:9",
        )
        .await
        .unwrap();
        let their_run =
            store::start_run(&db, OTHER, &their_flow, "", "manual", "", &json!({}), 0, "t")
                .await
                .unwrap();
        tick(&db, &reg, OTHER).await.unwrap();
        let their_run_before = raw_run(&db, &their_run).await;
        let their_steps_before = raw_steps(&db, &their_run).await;
        assert_eq!(their_steps_before.len(), 1, "the neighbour really did run a step");

        // And this hub has a run parked mid-flight.
        let flow_id = flow(&db, one_command_flow()).await;
        grant(&db, &flow_id, "notes.note.add").await;
        let run_id = store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();
        tick(&db, &reg, HUB).await.unwrap();
        let before = raw_run(&db, &run_id).await;
        let steps_before = raw_steps(&db, &run_id).await;

        // Now the neighbour asks for every write this file performs, naming OUR run.
        finish(&db, OTHER, &run_id, store::STATUS_FAILED, "not yours").await.unwrap();
        sleep_until(&db, OTHER, &run_id, "2020-01-01T00:00:00+00:00").await.unwrap();
        persist_vars(&db, OTHER, &run_id, 99, &json!({ "steps": { "x": 1 } })).await.unwrap();
        persist_step_index(&db, OTHER, &run_id, 98).await.unwrap();
        complete_step(&db, OTHER, &run_id, 0, &json!({ "stolen": true }), "2020-01-01T00:00:00+00:00")
            .await
            .unwrap();
        assert_eq!(
            interrupted_step(&db, OTHER, &run_id).await.unwrap(),
            None,
            "and it cannot read our steps either"
        );

        assert_eq!(raw_run(&db, &run_id).await, before, "our run is untouched");
        assert_eq!(raw_steps(&db, &run_id).await, steps_before, "our steps are untouched");
        assert_eq!(
            raw_run(&db, &their_run).await,
            their_run_before,
            "and the neighbour's own run did not move either"
        );
        assert_eq!(raw_steps(&db, &their_run).await, their_steps_before);
    }

    /// The same guarantee for the far side of the claim → I/O → complete seam: an answer handed
    /// back by the wrong hub is dropped, and neither hub's rows move.
    #[tokio::test]
    async fn an_io_result_from_another_hub_is_refused() {
        let db = db().await;
        let flow_id = flow(&db, http_flow("https://api.example.com/v1/ping")).await;
        http_grant(&db, &flow_id, "https://api.example.com/v1/*").await;
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1").await.unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        let before = raw_run(&db, &run_id).await;
        let steps_before = raw_steps(&db, &run_id).await;
        let err = complete_io(&db, OTHER, &run_id, "call", IoResult::Done(json!({ "status": 200 })))
            .await
            .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_IO_STEP_GONE),
            "{err:?}"
        );
        assert_eq!(raw_run(&db, &run_id).await, before);
        assert_eq!(raw_steps(&db, &run_id).await, steps_before);
    }

    // ── hub#970: `delay.until` sleeps until an INSTANT, not until a piece of text ──────────────
    //
    // `wake_sleeping` compares `wake_at <= :now` in SQL, over TEXT. That is only the same question
    // as «has this instant arrived?» while every string in the column is UTC. An `until` arrives
    // with the offset of wherever it was written (`trigger.at` says so explicitly: the offset is
    // part of the instant), so a `+02:00` sorted two hours late and a `-05:00` sorted five hours
    // early — silently: the run ends `done`, the history says nothing, and the only trace is the
    // hour on the message.

    /// A flow that waits for `input.when` and then writes a note.
    fn wait_until_flow() -> Json {
        json!({
            "schema_version": 1,
            "steps": [
                { "id": "wait", "kind": "delay", "until": "input.when" },
                { "id": "write", "kind": "command", "command": "notes.note.add",
                  "params": { "text": "later" } }
            ]
        })
    }

    async fn park_until(db: &dyn DatabaseAdapter, when: &str) -> (String, String) {
        let flow_id = flow(db, wait_until_flow()).await;
        grant(db, &flow_id, "notes.note.add").await;
        let run_id =
            start_manual_run(db, HUB, &flow_id, &json!({ "when": when }), "hub_user:1")
                .await
                .unwrap();
        tick(db, &registry(), HUB).await.unwrap();
        (flow_id, run_id)
    }

    fn at_offset(instant: chrono::DateTime<chrono::Utc>, hours: i32) -> String {
        instant
            .with_timezone(&chrono::FixedOffset::east_opt(hours * 3600).expect("valid offset"))
            .to_rfc3339()
    }

    /// A moment already past, written with a POSITIVE offset. Its text sorts AFTER `now`, so the
    /// string comparison keeps the run asleep for the length of the offset.
    #[tokio::test]
    async fn a_delay_until_a_past_instant_written_in_another_zone_wakes_on_the_next_tick() {
        let db = db().await;
        let due = at_offset(chrono::Utc::now() - chrono::Duration::minutes(1), 2);
        let (flow_id, run_id) = park_until(&db, &due).await;
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_SLEEPING);

        // What was stored has to be an instant the clock can compare, not the text it was given.
        let stored = raw_run(&db, &run_id).await["wake_at"].as_str().unwrap().to_string();
        assert!(stored.ends_with("+00:00"), "stored with an offset of its own: {stored}");

        tick(&db, &registry(), HUB).await.unwrap();
        assert_eq!(
            notes(&db).await,
            vec!["later"],
            "the instant passed a minute ago: the run resumes"
        );
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_DONE);
    }

    /// The other sign, and the worse one: a future moment written with a NEGATIVE offset sorts
    /// BEFORE `now`, so the run wakes early — a reminder sent before the thing it reminds of.
    /// One control can be right by accident; two with opposite signs cannot.
    #[tokio::test]
    async fn a_delay_until_a_future_instant_in_a_western_zone_does_not_wake_early() {
        let db = db().await;
        let later = at_offset(chrono::Utc::now() + chrono::Duration::hours(1), -5);
        let (flow_id, _) = park_until(&db, &later).await;

        tick(&db, &registry(), HUB).await.unwrap();
        assert!(notes(&db).await.is_empty(), "the instant has not arrived yet");
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_SLEEPING);
    }

    /// The runs that were parked BEFORE this fix are still in the table with their offset, and
    /// nothing would ever re-write them: a sleeping run is only read by the comparison that the
    /// offset breaks. The boot repair is what reaches them (`store::normalize_wake_at`).
    #[tokio::test]
    async fn a_run_parked_before_the_fix_is_repaired_at_boot_and_then_wakes() {
        let db = db().await;
        let due = at_offset(chrono::Utc::now() - chrono::Duration::minutes(1), 2);
        let (flow_id, run_id) = park_until(&db, &due).await;

        // Rewind it to the shape the old code wrote: the instant, with its origin offset.
        let mut p = Params::new();
        p.insert("id".into(), json!(run_id));
        p.insert("wake_at".into(), json!(due));
        db.execute("UPDATE _flow_runs SET wake_at = :wake_at WHERE id = :id", &p)
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();
        assert!(
            notes(&db).await.is_empty(),
            "this is the bug, reproduced: the text sorts late, so the run oversleeps"
        );

        store::normalize_wake_at(&db, HUB).await.unwrap();
        tick(&db, &registry(), HUB).await.unwrap();
        assert_eq!(notes(&db).await, vec!["later"]);
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_DONE);
    }
}
