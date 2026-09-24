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
use crate::flows::def::{self, ErrorPolicy, FlowDefinition, PastDuePolicy, StepDef, StepSpec};
use crate::flows::http::HttpRequest;
use crate::flows::{approvals, grants, http, notify, query, store, triggers, waits};
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
    let parent_event_id = run["parent_event_id"]
        .as_str()
        .unwrap_or_default()
        .to_string();
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
            return finish(db, hub_id, &run_id, store::STATUS_DONE, "")
                .await
                .map(|()| None);
        };
        // The clock travels with the run's own facts (hub#1694): read once per step, so every
        // clause of one `condition` — and the `{{now.iso}}` of the notify right after it — judge
        // the same instant instead of landing either side of a tick.
        let scope = json!({
            "input": input,
            "steps": vars.get("steps").cloned().unwrap_or(json!({})),
            "now": def::clock(),
        });

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
                return finish(db, hub_id, &run_id, store::STATUS_DONE, "")
                    .await
                    .map(|()| None)
            }
            Outcome::Sleep { wake_at, arm } => {
                return sleep_until(db, hub_id, &run_id, &wake_at, &arm)
                    .await
                    .map(|()| None)
            }
            // **What a failure costs is the STEP's answer, not this loop's** (hub#1635). The
            // default is still `stop` — a linear document whose write did not happen has no
            // business carrying on as if it had — and a document that says `on_error: "continue"`
            // gets exactly one thing more: the NEXT step, with how this one ended readable at
            // `steps.<id>`. Nothing is re-run; ADR-0283 §1 stands, and `retry` is not in the
            // vocabulary.
            Outcome::Failed { error } => match step.on_error {
                ErrorPolicy::Stop => {
                    return finish(db, hub_id, &run_id, store::STATUS_FAILED, &error)
                        .await
                        .map(|()| None);
                }
                ErrorPolicy::Continue => {
                    // The step row is already `failed` with its reason (every arm of `run_step`
                    // writes it before returning `Failed`), and it STAYS failed: `continue` is
                    // about the run, and a history that called it done would be a lie the tray
                    // reads.
                    set_step_output(&mut vars, &step.id, failure_output(json!({}), &error));
                    index += 1;
                    persist_vars(db, hub_id, &run_id, index, &vars).await?;
                }
            },
            // The question is asked; the run leaves the queue until somebody answers it. It goes
            // out through `complete_io` — the same door the `ai` step's proposal parks through —
            // so `waiting_approval` is written in exactly one place, and the resume path
            // (`decide_flow_approval`, the expiry sweep) is the same one for both kinds.
            Outcome::AwaitApproval => {
                return complete_io(
                    db,
                    hub_id,
                    &run_id,
                    &step.id,
                    IoResult::AwaitingApproval(json!({})),
                )
                .await
                .map(|()| None)
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
    Continue {
        output: Json,
    },
    /// The step's work happens outside the lock (`http` and `ai`). The tick hands it to the server
    /// and this run pauses exactly here, claimed, until it comes back.
    Io {
        pending: PendingIo,
    },
    /// A `condition` said no. The run is complete, not failed: a guard that does not pass is the
    /// flow working exactly as written.
    Stopped,
    /// The run parks as a row. `arm` is the wait's OTHER exits (hub#951), inserted in the same
    /// transaction as the sleep so there is no window in which one of them exists without the other.
    Sleep {
        wake_at: String,
        arm: Vec<(String, Params)>,
    },
    Failed {
        error: String,
    },
    /// **The pause** (hub#950). The question is already written to `_flow_approvals` and the step
    /// row is `running`; what is left is to park the run, and that is done through the seam the
    /// `ai` step has parked through since hub#665 rather than beside it. One place decides what
    /// «this run is waiting for a person» means, and a second one would drift.
    AwaitApproval,
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
            write_step(
                db,
                hub_id,
                run_id,
                index,
                step,
                status,
                &json!({}),
                &output,
                "",
                &now,
            )
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
                        db,
                        hub_id,
                        run_id,
                        index,
                        step,
                        STEP_DONE,
                        &recorded_input,
                        &output,
                        "",
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
                        db,
                        hub_id,
                        run_id,
                        index,
                        step,
                        STEP_FAILED,
                        &json!({}),
                        &json!({}),
                        &error,
                        &now,
                    )
                    .await?;
                    Ok(Outcome::Failed { error })
                }
            }
        }

        StepSpec::Delay(delay) => {
            // A step that fails says why AT the step, so the history explains the run.
            macro_rules! refuse {
                ($error:expr) => {{
                    let error = $error;
                    write_step(
                        db,
                        hub_id,
                        run_id,
                        index,
                        step,
                        STEP_FAILED,
                        &json!({}),
                        &json!({}),
                        &error,
                        &now,
                    )
                    .await?;
                    return Ok(Outcome::Failed { error });
                }};
            }

            let clock = chrono::Utc::now();
            let instant = match (&delay.seconds, &delay.until) {
                (Some(s), _) => clock + chrono::Duration::seconds(*s),
                (None, Some(path)) => {
                    let value = def::resolve(&json!(path), scope);
                    let Some(parsed) = value
                        .as_str()
                        .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
                    else {
                        refuse!(format!(
                            "step `{}`: `until` resolved to {value}, which is not an RFC-3339 \
                             instant",
                            step.id
                        ));
                    };
                    // **The offset of Salesforce's Scheduled Paths** (hub#951): «24 h before the
                    // appointment» is the instant of the thing, shifted. Seconds and not calendar
                    // units, so a −24 h across a DST change lands an hour off on the wall clock —
                    // the price of not having calendar arithmetic, and it is said on the screen.
                    parsed.with_timezone(&chrono::Utc)
                        + chrono::Duration::seconds(delay.offset_seconds)
                }
                (None, None) => unreachable!("parse refuses a delay with neither"),
            };

            // **The horizon** (hub#951). There was no ceiling: an `until` resolving to the year
            // 3000 slept as a row every retention rule exempts. Refused and not shortened, for the
            // same reason `limit` is refused above its ceiling — a wait nobody meant is worse than
            // a run that says why it stopped.
            let horizon = delay.horizon_seconds();
            if instant > clock + chrono::Duration::seconds(horizon) {
                refuse!(format!(
                    "{}: step `{}` would wait until {}, past the {horizon} s this wait may cover",
                    def::ERR_DELAY_HORIZON,
                    step.id,
                    instant.to_rfc3339()
                ));
            }

            // **The instant has already gone by.** Salesforce runs the scheduled path immediately;
            // the default here is the restrictive one, because the literal case is a reminder whose
            // hour went by and sending it late is worse than not sending it.
            if instant <= clock {
                match delay.past_due {
                    PastDuePolicy::Skip => {
                        let output = json!({ "past_due": true, "skipped": true });
                        write_step(
                            db,
                            hub_id,
                            run_id,
                            index,
                            step,
                            STEP_STOPPED,
                            &json!({}),
                            &output,
                            "",
                            &now,
                        )
                        .await?;
                        return Ok(Outcome::Stopped);
                    }
                    PastDuePolicy::Fail => {
                        refuse!(format!(
                            "{}: step `{}` resolved to {}, which had already passed",
                            def::ERR_DELAY_PAST_DUE,
                            step.id,
                            instant.to_rfc3339()
                        ));
                    }
                    PastDuePolicy::ContinueNow => {
                        let output = json!({ "past_due": true, "wake_at": Json::Null });
                        write_step(
                            db,
                            hub_id,
                            run_id,
                            index,
                            step,
                            STEP_DONE,
                            &json!({}),
                            &output,
                            "",
                            &now,
                        )
                        .await?;
                        return Ok(Outcome::Continue { output });
                    }
                }
            }

            // **Normalised to UTC before it is persisted** (hub#970): `wake_sleeping` compares this
            // against `:now` as TEXT, so an instant that keeps the offset it was written in sorts
            // by its wall clock instead of by when it happens — two hours late in Spanish summer,
            // and EARLY with a negative offset.
            let wake_at = instant.to_rfc3339();

            // The waits are built BEFORE anything is written, so a hook whose correlation this run
            // cannot resolve stops the step instead of arming half of them.
            let arm = match waits::arm_ops(
                hub_id,
                flow_id,
                run_id,
                &step.id,
                // The index the run will be parked ON: the step counter advances with the sleep
                // (waking resumes AFTER the delay), and the conditional update every exit of this
                // wait uses names that number.
                index + 1,
                delay,
                scope,
                &now,
            ) {
                Ok(arm) => arm,
                Err(e) => refuse!(format!("step `{}`: {}", step.id, error_text(&e))),
            };

            let output = json!({ "wake_at": wake_at, "waits": arm.len() });
            write_step(
                db,
                hub_id,
                run_id,
                index,
                step,
                STEP_SLEEPING,
                &json!({}),
                &output,
                "",
                &now,
            )
            .await?;
            // The step index advances with the sleep: waking up resumes AFTER the delay, not on it.
            persist_step_index(db, hub_id, run_id, index + 1).await?;
            Ok(Outcome::Sleep { wake_at, arm })
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
                    hub_id,
                    run_id,
                    index,
                    step,
                    STEP_COMMITTED,
                    &resolved_json,
                    &json!({}),
                    "",
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
                        db,
                        hub_id,
                        run_id,
                        index,
                        step,
                        STEP_FAILED,
                        &resolved_json,
                        &json!({}),
                        &error,
                        &now,
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
                        db,
                        hub_id,
                        run_id,
                        index,
                        step,
                        STEP_FAILED,
                        &json!({}),
                        &json!({}),
                        &error,
                        &now,
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
                db,
                hub_id,
                run_id,
                index,
                step,
                STEP_RUNNING,
                &json!({}),
                &json!({}),
                "",
                &now,
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
                db,
                registry,
                hub_id,
                flow_id,
                run_id,
                parent_event_id,
                depth,
                step,
                scope,
                &authority,
            )
            .await
            {
                Ok(notify::Prepared {
                    queue_op: Some(queue_op),
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
                // **Nothing to offer** (hub#1651): the list the message promised is there and has
                // no rows. Meta refuses a list without rows, so queuing it would end in the proxy's
                // refusal hours later; the run stops here instead — like a `condition` that did not
                // match, a halt and not a failure: «no free slots today» is a state of the business,
                // not a broken flow. The step keeps what it would have asked and why it did not.
                Ok(notify::Prepared {
                    queue_op: None,
                    recorded_input,
                    output,
                }) => {
                    write_step(
                        db,
                        hub_id,
                        run_id,
                        index,
                        step,
                        STEP_STOPPED,
                        &recorded_input,
                        &output,
                        "",
                        &now,
                    )
                    .await?;
                    Ok(Outcome::Stopped)
                }
                Err(e) => {
                    // Denied, nobody to write to, or a column that is not an address: NOTHING was
                    // queued, and the run says why — at the step, not eight retries later in a
                    // dead-letter.
                    let error = format!("step `{}`: {}", step.id, error_text(&e));
                    write_step(
                        db,
                        hub_id,
                        run_id,
                        index,
                        step,
                        STEP_FAILED,
                        &json!({}),
                        &json!({}),
                        &error,
                        &now,
                    )
                    .await?;
                    Ok(Outcome::Failed { error })
                }
            }
        }

        // **The pause** (hub#950). It does no I/O, so it never crosses the claim → I/O → complete
        // seam: everything happens here, under the lock, and what leaves the tick is a run that has
        // stopped and a row a person can answer.
        //
        // Two properties are the whole step, and both live in this arm:
        //
        // 1. **The question is rendered NOW and stored.** `title`/`summary` are templated against
        //    this run and written to the row, exactly like the `payload` of a model's proposal —
        //    so editing (or deleting) the flow afterwards cannot change what the person in front
        //    of the tray is agreeing to. That is the acceptance criterion «editing the flow does
        //    not mutate requests already created», and it costs nothing extra.
        // 2. **It asks once per run and step.** A tick that wrote the row and died before the run
        //    was parked gets its lease reclaimed and comes back through here; without the lookup
        //    the person would find the same question twice, and answering one would leave the
        //    other hanging until the sweep.
        StepSpec::Approval(spec) => {
            let title = def::render(&spec.title, scope);
            let summary = def::render(&spec.summary, scope);
            let recorded_input = json!({
                "title": title,
                "summary": summary,
                "assignee_role": spec.assignee_role,
                "expires_in": spec.expires_in_seconds,
                "on_expire": spec.on_expire.as_str(),
                "on_reject": spec.on_reject.as_str(),
            });

            let already_asked = approvals::pending_for_step(db, hub_id, run_id, &step.id).await?;
            let newly_asked = match already_asked {
                Some(_) => None,
                None => Some(
                    approvals::create_decision(
                        db,
                        hub_id,
                        &approvals::NewDecision {
                            run_id: run_id.to_string(),
                            flow_id: flow_id.to_string(),
                            step_id: step.id.clone(),
                            title: title.clone(),
                            summary: summary.clone(),
                            assignee_role: spec.assignee_role.clone(),
                            expires_in_seconds: spec.expires_in_seconds,
                            on_expire: spec.on_expire,
                            on_reject: spec.on_reject,
                        },
                    )
                    .await?,
                ),
            };

            // `running` and not `waiting_approval`: the park is `complete_io`'s job, and it only
            // accepts a result for a step the run is actually waiting on.
            write_step(
                db,
                hub_id,
                run_id,
                index,
                step,
                STEP_RUNNING,
                &recorded_input,
                &json!({}),
                "",
                &now,
            )
            .await?;

            // Ephemeral, WS-only — the same fact a model's proposal emits, so the tray lights up
            // without polling. The SCREEN is the module `flows`'s job (ADR-0283 §7).
            //
            // **Only for a question that is actually new.** A replay of this step (the crash
            // window above) is not a new question, and re-announcing it would light up the tray a
            // second time for a row that has been sitting in it since Tuesday.
            if let Some(asked) = newly_asked {
                let mut payload = Params::new();
                payload.insert("approval_id".into(), json!(asked.id));
                payload.insert("flow_id".into(), json!(asked.flow_id));
                payload.insert("run_id".into(), json!(asked.run_id));
                payload.insert("kind".into(), json!(asked.kind));
                payload.insert("title".into(), json!(asked.title));
                payload.insert("summary".into(), json!(asked.summary));
                payload.insert("assignee_role".into(), json!(asked.assignee_role));
                crate::events::notify_sink(
                    registry,
                    crate::registry::EventSource::Core,
                    approvals::EVENT_APPROVAL_CREATED,
                    &payload,
                );
            }

            Ok(Outcome::AwaitApproval)
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
    let (sql, p) = write_step_op(
        hub_id, run_id, index, step, status, input, output, error, now,
    );
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

/// Puts the run to sleep **and arms the wait's other exits in the same transaction** (hub#951).
///
/// The atomicity is the whole point. Arming before the row says `sleeping` would leave a window
/// where a cancelling event finds an armed wait whose run is still `running`: the conditional
/// update affects zero rows, the event is marked delivered, and the cancellation is lost for good.
/// Arming after would leave the opposite window, a run asleep with no way out but its clock. In one
/// transaction there is no window — and a `delay` with no hooks is exactly the statement it always
/// was.
async fn sleep_until(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    wake_at: &str,
    arm: &[(String, Params)],
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("wake_at".into(), json!(wake_at));
    p.insert("now".into(), json!(now_rfc3339()));
    let sleep = (
        "UPDATE _flow_runs SET status = 'sleeping', wake_at = :wake_at, \
                               claim_expires_at = NULL, updated_at = :now \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL"
            .to_string(),
        p,
    );
    if arm.is_empty() {
        db.execute(&sleep.0, &sleep.1).await?;
        return Ok(());
    }
    let mut ops = vec![sleep];
    ops.extend_from_slice(arm);
    db.execute_tx(&ops).await?;
    Ok(())
}

/// A run reaches a terminal status — and every wait it had armed stops being armed with it
/// (hub#951). A wait outliving its run would be looked at on every delivery of its event, forever,
/// to affect zero rows each time.
async fn finish(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    status: &str,
    error: &str,
) -> Result<()> {
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(status));
    p.insert("error".into(), json!(error));
    p.insert("now".into(), json!(now.clone()));
    db.execute_tx(&[
        (
            "UPDATE _flow_runs SET status = :status, last_error = :error, finished_at = :now, \
                                   claim_expires_at = NULL, updated_at = :now \
             WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL"
                .to_string(),
            p,
        ),
        waits::disarm_run_op(hub_id, run_id, &now),
    ])
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

pub(crate) fn parse_json(raw: &str) -> Json {
    serde_json::from_str(raw).unwrap_or_else(|_| json!({}))
}

/// The `on_error` of the step at `index`, read from the DOCUMENT at the moment a failure that
/// happened outside the tick is answered (hub#1635).
///
/// **From the document and not from a row**, which is where it differs from `on_reject`/`on_expire`
/// (hub#950, hub#1622) — and the difference is WHO answers. Those two are answered by a person
/// hours later, or by her silence, so what governs has to be the document that was in force when
/// she was ASKED, and it travels on the proposal: editing the flow while somebody is looking at the
/// tray must not change what her refusal costs. `on_error` is answered by the RUN itself, at the
/// same instant every other step of that run reads the document — `advance_run` re-parses
/// `flow.definition` on EVERY tick, and the step this policy sends the run to is parsed from the
/// version that is current then. Freezing this one key would be the inconsistency, not the
/// safeguard.
///
/// Anything unreadable — a flow deleted or disabled mid-call, a document this binary can no longer
/// parse, an index past the end — is [`ErrorPolicy::Stop`]. Fail CLOSED: it is the answer this path
/// has always given, and «carry on past a failure whose instructions I cannot read» is not one a
/// kernel may guess.
pub(crate) async fn step_error_policy(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    index: i64,
) -> ErrorPolicy {
    let Ok(flow) = store::get(db, hub_id, flow_id).await else {
        return ErrorPolicy::Stop;
    };
    let Ok(def) = FlowDefinition::parse(&flow.definition) else {
        return ErrorPolicy::Stop;
    };
    def.steps
        .get(index as usize)
        .map(|s| s.on_error)
        .unwrap_or(ErrorPolicy::Stop)
}

/// What a step that FAILED leaves in `steps.<id>` when the document said `on_error: "continue"`
/// (hub#1635).
///
/// Two keys, whichever kind failed and whichever side of the seam it failed on: `status` — the same
/// word the step row now carries, so the step written after it reads ONE key however the one before
/// went — and `error`, the reason, because a message that cannot say WHY is not worth sending.
///
/// They are written OVER whatever the step had already produced, which is the half that makes the
/// `ai` step work: the turn parked when it stopped to ask is still there under them, exactly as
/// `on_reject: "continue"` hands it over (hub#1622). Without that, `{{steps.<id>.text}}` renders
/// empty in the very message this primitive exists to send.
pub(crate) fn failure_output(parked: Json, error: &str) -> Json {
    let mut output = if parked.is_object() {
        parked
    } else {
        json!({})
    };
    let map = output.as_object_mut().expect("just made an object");
    map.insert("status".to_string(), json!(STEP_FAILED));
    map.insert("error".to_string(), json!(error));
    output
}

pub(crate) fn set_step_output(vars: &mut Json, step_id: &str, output: Json) {
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
            "SELECT current_step, vars, status, flow_id FROM _flow_runs \
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
    let flow_id = run["flow_id"].as_str().unwrap_or_default().to_string();

    // The step this run is waiting on, and its status. Anything else means the answer is stale.
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(run_id));
    p.insert("step_index".into(), json!(index));
    let step_row = db
        .query(
            "SELECT step_id, status, output FROM _flow_run_steps \
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
            // What the turn had already produced, read BEFORE the row is overwritten: for an `ai`
            // step this is the answer parked when it stopped to ask, and the message this run is
            // about to send renders it with `{{steps.<id>.text}}`.
            let parked = parse_json(
                step_row
                    .rows
                    .first()
                    .and_then(|r| r["output"].as_str())
                    .unwrap_or("{}"),
            );
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
            // **The same question the tick asks** (hub#1635), on the far side of the seam: what a
            // failure costs the run is the STEP's answer. The default — and the answer whenever the
            // document cannot be read, which is where a deleted or rolled-back flow lands — is the
            // one this arm has always given: the run fails here.
            match step_error_policy(db, hub_id, &flow_id, index).await {
                ErrorPolicy::Stop => {
                    finish(db, hub_id, run_id, store::STATUS_FAILED, &error).await?;
                }
                ErrorPolicy::Continue => {
                    set_step_output(&mut vars, step_id, failure_output(parked, &error));
                    persist_vars(db, hub_id, run_id, index + 1, &vars).await?;
                    // Back in the queue with the lease released, exactly like a call that WORKED:
                    // the next tick runs the step that tells whoever was waiting.
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
            }
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
    use crate::flows::grants::{GrantKind, GrantSpec};
    use crate::flows::store::NewFlow;
    use crate::flows::test_support;
    use crate::registry::ModuleStatus;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-exec";

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db.execute_batch(
            "CREATE TABLE IF NOT EXISTS note (id TEXT PRIMARY KEY, text TEXT NOT NULL);",
        )
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
            &[GrantSpec::pair(GrantKind::Command, command.to_string())],
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
        store::list_runs(db, HUB, flow_id, 10, None)
            .await
            .unwrap()
            .remove(0)
    }

    async fn http_grant(db: &dyn DatabaseAdapter, flow_id: &str, pattern: &str) {
        grants::replace(
            db,
            HUB,
            flow_id,
            &registry(),
            &[GrantSpec::pair(GrantKind::Http, pattern.to_string())],
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

        store::start_run(
            &db,
            HUB,
            &flow_id,
            "",
            "manual",
            "",
            &json!({ "total": "9.90" }),
            0,
            "t",
        )
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

    /// hub#1694 — the run knows what time it is, so a guard can be about a WINDOW.
    ///
    /// The case it was added for is Meta's: a WhatsApp conversation may be written to for free
    /// only while the customer's last message is under 24 h old. Before this, the flow had no way
    /// to ask — it sent, Meta refused, and the only trace was a failed step in a history nobody
    /// reads.
    #[tokio::test]
    async fn a_guard_can_ask_whether_a_timestamp_is_still_inside_its_window_hub1694() {
        let day_ago = |seconds: i64| {
            (chrono::Utc::now() - chrono::Duration::seconds(seconds)).to_rfc3339()
        };
        for (last_message_at, should_write, why) in [
            (day_ago(3600), true, "an hour old: inside Meta's 24 h"),
            (day_ago(90_000), false, "25 h old: outside it"),
        ] {
            let db = db().await;
            let flow_id = flow(
                &db,
                json!({
                    "schema_version": 1,
                    "steps": [
                        { "id": "still_open", "kind": "condition",
                          "when": { "input.last_message_at": { "within_last": 86400 } } },
                        { "id": "write", "kind": "command", "command": "notes.note.add",
                          "params": { "text": "reply" } }
                    ]
                }),
            )
            .await;
            grant(&db, &flow_id, "notes.note.add").await;

            store::start_run(
                &db,
                HUB,
                &flow_id,
                "",
                "manual",
                "",
                &json!({ "last_message_at": last_message_at }),
                0,
                "t",
            )
            .await
            .unwrap();
            tick(&db, &registry(), HUB).await.unwrap();

            assert_eq!(!notes(&db).await.is_empty(), should_write, "{why}");
            assert_eq!(
                run_of(&db, &flow_id).await.status,
                store::STATUS_DONE,
                "{why}: a guard that says no is the flow working, not failing"
            );
        }
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
        assert!(
            steps[0].output.get("ok").is_some(),
            "the output is kept: {:?}",
            steps[0].output
        );
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
                GrantSpec::pair(GrantKind::Command, "notes.note.add"),
                GrantSpec::pair(GrantKind::Query, "notes.note.find"),
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
                GrantSpec::pair(GrantKind::Command, "notes.note.add"),
                GrantSpec::pair(GrantKind::Query, "notes.note.find"),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();

        store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        assert!(
            notes(&db).await.is_empty(),
            "the guard stopped it, the read did not"
        );
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
        let run_id = store::start_run(&db, HUB, &flow_id, "", "manual", "", &json!({}), 0, "t")
            .await
            .unwrap();

        tick(&db, &reg, HUB).await.unwrap();
        assert_eq!(notes(&db).await, vec!["one"], "the first step ran");

        // The owner revokes while the run sleeps. This is the guarantee: effective at the NEXT
        // step, not at some restart.
        grants::replace(&db, HUB, &flow_id, &reg, &[], "hub_user:2")
            .await
            .unwrap();
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
        assert!(
            run.last_error.contains(grants::ERR_GRANT_DENIED),
            "{}",
            run.last_error
        );
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

        assert!(
            notes(&db).await.is_empty(),
            "a hub does not act on a withdrawn instruction"
        );
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
        assert!(
            run.last_error.contains(ERR_STEP_OUTPUT_LOST),
            "{}",
            run.last_error
        );
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
            &[GrantSpec::pair(GrantKind::Command, "notes.audited.add")],
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
        assert_eq!(
            rows[0]["hub_id"],
            json!(HUB),
            "the tenant is never negotiable"
        );
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
        start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1")
            .await
            .unwrap();

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
        let flow_id = flow(
            &db,
            http_flow("https://api.example.com/v1/ping?who={{input.who}}"),
        )
        .await;
        http_grant(&db, &flow_id, "https://api.example.com/v1/*").await;
        start_manual_run(&db, HUB, &flow_id, &json!({ "who": "marta" }), "hub_user:1")
            .await
            .unwrap();

        let report = tick(&db, &registry(), HUB).await.unwrap();

        assert_eq!(report.pending_io.len(), 1, "one step, one request");
        let PendingIo::Http {
            step_id, request, ..
        } = &report.pending_io[0]
        else {
            panic!("an http step becomes an http PendingIo");
        };
        assert_eq!(step_id, "call");
        assert_eq!(
            request.url.as_str(),
            "https://api.example.com/v1/ping?who=marta"
        );
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
                GrantSpec::pair(GrantKind::Http, "https://api.example.com/v1/*"),
                GrantSpec::pair(GrantKind::Command, "notes.note.add"),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1")
            .await
            .unwrap();

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
                GrantSpec::pair(GrantKind::Http, "https://api.example.com/v1/*"),
                GrantSpec::pair(GrantKind::Command, "notes.note.add"),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1")
            .await
            .unwrap();
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

        // This document says nothing about failure, so the default `on_error: stop` applies.
        let run = run_of(&db, &flow_id).await;
        assert_eq!(run.status, store::STATUS_FAILED);
        assert!(
            run.last_error.contains("http_timeout"),
            "{}",
            run.last_error
        );
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

        start_manual_run(&db, HUB, &calling, &json!({}), "hub_user:1")
            .await
            .unwrap();
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
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1")
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        complete_io(
            &db,
            HUB,
            &run_id,
            "call",
            IoResult::Done(json!({ "status": 200 })),
        )
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
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1")
            .await
            .unwrap();

        let report = tick(&db, &registry(), HUB).await.unwrap();
        // It really did go out with the credential…
        let PendingIo::Http { request, .. } = &report.pending_io[0] else {
            panic!()
        };
        assert!(request
            .headers
            .iter()
            .any(|(_, v)| v.contains("sk-live-42")));

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
            db.query("SELECT * FROM _flow_run_steps", &Params::new())
                .await
                .unwrap()
                .rows,
            db.query("SELECT * FROM _flow_runs", &Params::new())
                .await
                .unwrap()
                .rows,
            report.pending_io,
        );
        assert!(
            !dump.contains("sk-live-42"),
            "the credential is nowhere: {dump}"
        );
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
            &[GrantSpec::pair(GrantKind::Command, "notes.note.add")],
            "hub_user:9",
        )
        .await
        .unwrap();
        let their_run = store::start_run(
            &db,
            OTHER,
            &their_flow,
            "",
            "manual",
            "",
            &json!({}),
            0,
            "t",
        )
        .await
        .unwrap();
        tick(&db, &reg, OTHER).await.unwrap();
        let their_run_before = raw_run(&db, &their_run).await;
        let their_steps_before = raw_steps(&db, &their_run).await;
        assert_eq!(
            their_steps_before.len(),
            1,
            "the neighbour really did run a step"
        );

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
        finish(&db, OTHER, &run_id, store::STATUS_FAILED, "not yours")
            .await
            .unwrap();
        sleep_until(&db, OTHER, &run_id, "2020-01-01T00:00:00+00:00", &[])
            .await
            .unwrap();
        persist_vars(&db, OTHER, &run_id, 99, &json!({ "steps": { "x": 1 } }))
            .await
            .unwrap();
        persist_step_index(&db, OTHER, &run_id, 98).await.unwrap();
        complete_step(
            &db,
            OTHER,
            &run_id,
            0,
            &json!({ "stolen": true }),
            "2020-01-01T00:00:00+00:00",
        )
        .await
        .unwrap();
        assert_eq!(
            interrupted_step(&db, OTHER, &run_id).await.unwrap(),
            None,
            "and it cannot read our steps either"
        );

        assert_eq!(raw_run(&db, &run_id).await, before, "our run is untouched");
        assert_eq!(
            raw_steps(&db, &run_id).await,
            steps_before,
            "our steps are untouched"
        );
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
        let run_id = start_manual_run(&db, HUB, &flow_id, &json!({}), "hub_user:1")
            .await
            .unwrap();
        tick(&db, &registry(), HUB).await.unwrap();

        let before = raw_run(&db, &run_id).await;
        let steps_before = raw_steps(&db, &run_id).await;
        let err = complete_io(
            &db,
            OTHER,
            &run_id,
            "call",
            IoResult::Done(json!({ "status": 200 })),
        )
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
    ///
    /// `past_due_policy` is explicit because hub#951 made the DEFAULT `skip`: an instant that has
    /// already gone by ends the run instead of sleeping, so these guards — which are about what a
    /// SLEEPING run compares against — have to say which of the three answers they are testing.
    fn wait_until_flow(past_due: &str) -> Json {
        json!({
            "schema_version": 1,
            "steps": [
                { "id": "wait", "kind": "delay", "until": "input.when",
                  "past_due_policy": past_due },
                { "id": "write", "kind": "command", "command": "notes.note.add",
                  "params": { "text": "later" } }
            ]
        })
    }

    async fn park_until(db: &dyn DatabaseAdapter, when: &str) -> (String, String) {
        park_until_with(db, when, "continue_now").await
    }

    async fn park_until_with(
        db: &dyn DatabaseAdapter,
        when: &str,
        past_due: &str,
    ) -> (String, String) {
        let flow_id = flow(db, wait_until_flow(past_due)).await;
        grant(db, &flow_id, "notes.note.add").await;
        let run_id = start_manual_run(db, HUB, &flow_id, &json!({ "when": when }), "hub_user:1")
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

    /// A moment already past, written with a POSITIVE offset. Its TEXT sorts after `now`, which is
    /// what used to keep the run asleep for the length of the offset.
    ///
    /// Since hub#951 this case never reaches the SQL comparison at all: «has this instant passed?»
    /// is answered in Rust, over `DateTime`, before anything is stored — so the offset cannot get a
    /// vote. What the run does next is now the author's choice, and `continue_now` is the one that
    /// asks the same question this test always asked.
    #[tokio::test]
    async fn a_delay_until_a_past_instant_written_in_another_zone_does_not_oversleep() {
        let db = db().await;
        let due = at_offset(chrono::Utc::now() - chrono::Duration::minutes(1), 2);
        let (flow_id, run_id) = park_until(&db, &due).await;

        assert_eq!(
            notes(&db).await,
            vec!["later"],
            "the instant passed a minute ago: the run carries on, it does not sleep +02:00 hours"
        );
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_DONE);
        assert_eq!(
            raw_run(&db, &run_id).await["wake_at"],
            Json::Null,
            "and it never parked: an instant already gone by is decided, not stored"
        );
    }

    /// And the restrictive default, which is the other half of the same decision (hub#951): the
    /// same past instant, with nobody writing a policy, does NOT send the reminder.
    #[tokio::test]
    async fn the_same_past_instant_is_skipped_when_the_document_says_nothing() {
        let db = db().await;
        let due = at_offset(chrono::Utc::now() - chrono::Duration::minutes(1), 2);
        let (flow_id, _) = park_until_with(&db, &due, def::PastDuePolicy::default().as_str()).await;

        assert!(
            notes(&db).await.is_empty(),
            "a reminder whose hour went by is not sent"
        );
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_DONE);
    }

    /// **The storage half of hub#970, which is the one that survives.** A run that really does
    /// sleep must store an instant the clock can compare, not the text it was given: `wake_sleeping`
    /// compares `wake_at <= :now` over TEXT, and that is only the same question while every string
    /// in the column is UTC.
    ///
    /// Both signs, because one control can be right by accident: `+02:00` sorted two hours LATE
    /// (the run overslept) and `-05:00` sorted five hours EARLY (a reminder before the thing it
    /// reminds of). The second assertion is the bug itself, reproduced as a comparison.
    #[tokio::test]
    async fn a_sleeping_run_stores_its_instant_in_utc_whatever_zone_it_arrived_in() {
        for hours in [2, -5] {
            let db = db().await;
            let later = at_offset(chrono::Utc::now() + chrono::Duration::hours(6), hours);
            let (flow_id, run_id) = park_until(&db, &later).await;
            assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_SLEEPING);

            let stored = raw_run(&db, &run_id).await["wake_at"]
                .as_str()
                .unwrap()
                .to_string();
            assert!(
                stored.ends_with("+00:00"),
                "stored with an offset of its own: {stored}"
            );

            // The question `wake_sleeping` asks, at a moment safely after the instant. The stored
            // text answers it; the text as it arrived does not — that IS hub#970.
            let after = (chrono::Utc::now() + chrono::Duration::hours(7)).to_rfc3339();
            assert!(stored <= after, "{stored} vs {after}");
            if hours > 0 {
                assert!(
                    later > after,
                    "the raw `{later}` sorts late: the run would oversleep"
                );
            }

            tick(&db, &registry(), HUB).await.unwrap();
            assert!(
                notes(&db).await.is_empty(),
                "the instant has not arrived yet"
            );
            assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_SLEEPING);
        }
    }

    /// The runs that were parked BEFORE this fix are still in the table with their offset, and
    /// nothing would ever re-write them: a sleeping run is only read by the comparison that the
    /// offset breaks. The boot repair is what reaches them (`store::normalize_wake_at`).
    #[tokio::test]
    async fn a_run_parked_before_the_fix_is_repaired_at_boot_and_then_wakes() {
        let db = db().await;
        // Parked on a FUTURE instant, because that is the only way a run sleeps at all now
        // (hub#951) — and then rewound by hand to the shape the old code wrote for a delay that
        // was already due: the instant, with its origin offset.
        let later = at_offset(chrono::Utc::now() + chrono::Duration::hours(6), 2);
        let (flow_id, run_id) = park_until(&db, &later).await;
        assert_eq!(run_of(&db, &flow_id).await.status, store::STATUS_SLEEPING);

        let due = at_offset(chrono::Utc::now() - chrono::Duration::minutes(1), 2);
        let mut p = Params::new();
        p.insert("id".into(), json!(run_id));
        p.insert("wake_at".into(), json!(due));
        db.execute(
            "UPDATE _flow_runs SET wake_at = :wake_at WHERE id = :id",
            &p,
        )
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
