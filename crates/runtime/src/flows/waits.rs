//! **The other exits of a wait** (hub#951): the events that cancel a sleeping run, and the events
//! that move it.
//!
//! Until this module existed a `delay` had exactly ONE way out — its own clock. Nothing could wake
//! a sleeping run early, so a reminder armed «24 h before the appointment» went out even when the
//! appointment had been cancelled the day before. That is not a hypothetical: the Square Community
//! thread the market study cites is merchants watching reminders go out for cancelled bookings, in
//! a first-line product.
//!
//! ## The shape, and why it is not a lock
//!
//! The market's answer is NetSuite SuiteFlow's, and it is the reason the criterion «the timer and
//! the cancellation race, and never both win» costs nothing here: **the wait is a STATE with
//! several exits**, and every exit is the SAME conditional `UPDATE`:
//!
//! ```sql
//! UPDATE _flow_runs SET … WHERE id = :run AND status = 'sleeping' AND current_step = :index
//! ```
//!
//! The timer ([`crate::flows::executor::wake_sleeping`]) writes it, a cancellation writes it, a
//! reschedule writes it. Whoever gets there first moves the row out from under the condition and
//! everybody else affects **zero rows** and stops. There is no lock, no ordering and no window: one
//! transition wins by construction, and «zero rows» is not an error — it is the answer.
//!
//! ## Idempotence
//!
//! The relay is at-least-once, so the same event WILL come back. The marker is the one that already
//! exists: a row in `_event_delivery` under a **synthetic listener** `_flow_wait:<wait_id>`, the
//! exact pattern [`crate::flows::triggers::synthetic_listener`] uses for `_flow:<trigger_id>`. No
//! new table, no second mechanism, and `_event_delivery` has carried `hub_id` since v46.
//!
//! ## What is NOT here
//!
//! **The re-check.** A `cancel_on` can be missed — the event was never emitted, the module was
//! uninstalled, the hub was off — and the market's belt-and-braces (Klaviyo's flow filters, and the
//! workaround every Zapier/Power Automate forum converges on) is to LOOK AGAIN before acting. That
//! is deliberately not a field: it composes out of primitives that already exist, `delay → query`
//! (hub#954) `→ condition`. A fourth key promising it would be a second engine beside this one.
//!
//! **The payload.** A wait row keeps the event name and the correlated **id**, and nothing else.
//! Retention (flows.md §13.7) is the reason: a table of armed waits holding copies of event
//! payloads would be customer data outliving the run that explains it.
use serde_json::{json, Map, Value as Json};

use erplora_db::{DatabaseAdapter, Params};

use crate::errors::{Result, RuntimeError};
use crate::flows::def::{
    self, Condition, DelayStep, ErrorPolicy, PastDuePolicy, WaitKind, ERR_DELAY_HORIZON,
    ERR_MAX_RESCHEDULES, MAX_RESCHEDULES,
};
use crate::flows::executor;
use crate::flows::store;
use crate::registry::{new_id, now_rfc3339};

/// A wait that is armed and has not fired yet.
pub const STATUS_ARMED: &str = "armed";
/// A `cancel` wait that took its run out of the wait. Terminal.
pub const STATUS_FIRED: &str = "fired";
/// A wait whose run left the wait some other way: the timer won, a sibling won, the flow was
/// deleted. Terminal, and soft-deleted in the same gesture so it leaves the partial index.
pub const STATUS_DISARMED: &str = "disarmed";

/// The most armed waits one delivered event will look at. The partial index makes the lookup cheap;
/// this is the guard against a hub that armed thousands of waits on the same event name, so that a
/// pathological flow costs a bounded amount of the relay's time instead of the whole tick.
const MAX_CANDIDATES: i64 = 200;

/// The most distinct scalar values of an event payload used to narrow the index lookup. Beyond it
/// the narrowing is dropped and the two-column prefix of the index does the work — a wide event is
/// not a reason to build a 500-term `IN`.
const MAX_NARROWING_VALUES: usize = 48;

/// The `_event_delivery` listener a wait books its idempotence under. Not a command — nothing can
/// call it — which is exactly why it cannot collide with a module's listener.
pub fn synthetic_listener(wait_id: &str) -> String {
    format!("_flow_wait:{wait_id}")
}

// ── Arming ────────────────────────────────────────────────────────────────────────────────────

/// The `INSERT`s that arm every hook of a `delay`, **without executing them**, so the caller can
/// put them in the same transaction as the `UPDATE` that puts the run to sleep.
///
/// That atomicity is the point and not tidiness. Arming BEFORE the run is `sleeping` would leave a
/// window where a cancelling event finds an armed wait whose run is still `running`: the
/// conditional update affects zero rows, the event is marked delivered, and the cancellation is
/// lost for good. Arming AFTER would leave the opposite window, where the run sleeps with no way
/// out but its clock. In one transaction there is no window.
///
/// The run side of each `correlate` is resolved HERE, once, against the run — so the row carries
/// «appointment 42» and not a path that would have to be re-resolved against a run that has moved
/// on. A path that resolves to nothing is an error and not an empty string: a wait correlated on
/// `""` would match every event whose field is also missing.
#[allow(clippy::too_many_arguments)]
pub fn arm_ops(
    hub_id: &str,
    flow_id: &str,
    run_id: &str,
    step_id: &str,
    step_index: i64,
    delay: &DelayStep,
    scope: &Json,
    now: &str,
) -> Result<Vec<(String, Params)>> {
    let mut ops = Vec::new();
    for (kind, hook) in delay.hooks() {
        let mut resolved = Map::new();
        for (event_path, run_path) in &hook.correlate {
            let value = def::resolve_path(run_path, scope).unwrap_or(Json::Null);
            let Some(text) = as_text(&value) else {
                return Err(RuntimeError::Domain {
                    code: def::ERR_INVALID_DEFINITION.to_string(),
                    message: format!(
                        "step `{step_id}`: `{}_on` for `{}` correlates on `{run_path}`, which this \
                         run resolves to {value}. The wait is not armed on an empty key — it would \
                         match every event whose `{event_path}` is missing too.",
                        kind.as_str(),
                        hook.event
                    ),
                });
            };
            resolved.insert(event_path.clone(), json!(text));
        }
        // The pair the partial index is keyed on. `BTreeMap` order makes «the first» deterministic
        // across runtimes; the others are compared in Rust after the lookup.
        let (first_key, first_value) = resolved
            .iter()
            .next()
            .map(|(k, v)| (k.clone(), v.as_str().unwrap_or_default().to_string()))
            .unwrap_or_default();

        let mut p = Params::new();
        p.insert("id".into(), json!(new_id()));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("run_id".into(), json!(run_id));
        p.insert("flow_id".into(), json!(flow_id));
        p.insert("step_id".into(), json!(step_id));
        p.insert("step_index".into(), json!(step_index));
        p.insert("kind".into(), json!(kind.as_str()));
        p.insert("event_name".into(), json!(hook.event));
        p.insert("filter".into(), json!(hook.filter.to_json().to_string()));
        p.insert(
            "correlate".into(),
            json!(Json::Object(resolved).to_string()),
        );
        p.insert("correlate_key".into(), json!(first_key));
        p.insert("correlate_value".into(), json!(first_value));
        p.insert(
            "until_path".into(),
            json!(hook.until.clone().unwrap_or_default()),
        );
        p.insert("offset_seconds".into(), json!(delay.offset_seconds));
        p.insert("max_wait".into(), json!(delay.max_wait));
        p.insert("past_due_policy".into(), json!(delay.past_due.as_str()));
        p.insert("now".into(), json!(now));
        ops.push((
            "INSERT INTO _flow_run_waits \
               (id, hub_id, run_id, flow_id, step_id, step_index, kind, event_name, filter, \
                correlate, correlate_key, correlate_value, until_path, offset_seconds, max_wait, \
                past_due_policy, reschedules, status, created_at, updated_at) \
             VALUES (:id, :hub_id, :run_id, :flow_id, :step_id, :step_index, :kind, :event_name, \
                :filter, :correlate, :correlate_key, :correlate_value, :until_path, \
                :offset_seconds, :max_wait, :past_due_policy, 0, 'armed', :now, :now)"
                .to_string(),
            p,
        ));
    }
    Ok(ops)
}

/// Disarms every armed wait of a run, **without executing it**. Used wherever a run reaches a
/// terminal status: a wait outliving its run would be matched against every delivery of its event
/// for as long as the row lives, affecting zero rows each time.
pub fn disarm_run_op(hub_id: &str, run_id: &str, now: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(run_id));
    p.insert("now".into(), json!(now));
    (
        "UPDATE _flow_run_waits SET status = 'disarmed', deleted_at = :now, updated_at = :now \
         WHERE hub_id = :hub_id AND run_id = :run_id AND status = 'armed'"
            .to_string(),
        p,
    )
}

/// The same, for every run of a flow that is being deleted (`store::delete`).
pub async fn disarm_flow(db: &dyn DatabaseAdapter, hub_id: &str, flow_id: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _flow_run_waits SET status = 'disarmed', deleted_at = :now, updated_at = :now \
         WHERE hub_id = :hub_id AND flow_id = :flow_id AND status = 'armed'",
        &p,
    )
    .await?;
    Ok(())
}

// ── Matching ──────────────────────────────────────────────────────────────────────────────────

/// Matches one delivered event against the armed waits of this hub and attempts at most one
/// transition per wait. Returns how many waits it acted on — **attempted**, not won: a transition
/// that affects zero rows because the timer or a sibling got there first is counted here too, and
/// distinguishing them would mean reading back a row to learn something nothing does anything
/// with.
///
/// The sibling of [`crate::flows::triggers::on_event`], called from the same place in the relay.
/// Where that one can only INSERT a run, this one is the only thing in the kernel that can move a
/// run that is already alive.
pub async fn on_event(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_id: &str,
    event_name: &str,
    payload: &Params,
) -> Result<usize> {
    let scope = json!({ "event": Json::Object(payload.clone()) });
    let candidates = candidates(db, hub_id, event_name, &scope).await?;
    let mut fired = 0usize;

    for row in &candidates {
        let wait_id = text(row, "id");
        let listener = synthetic_listener(&wait_id);
        // Already handled in a previous attempt of this same event.
        if delivery_exists(db, hub_id, event_id, &listener).await? {
            continue;
        }

        // A "no" is a decision, not a pending job — the same reasoning as a trigger's filter: book
        // it so the next attempt of the same event does not re-evaluate an answer already given.
        if !matches(row, &scope) {
            mark_delivered(db, hub_id, event_id, &listener).await?;
            continue;
        }

        let ops = match WaitKind::parse(&text(row, "kind")) {
            Some(WaitKind::Cancel) => cancel_ops(hub_id, row),
            Some(WaitKind::Reschedule) => match reschedule_ops(hub_id, row, &scope) {
                Reschedule::Ops(ops) => ops,
                Reschedule::Failed(reason) => failure_ops(db, hub_id, row, &reason).await?,
            },
            None => {
                // A kind this binary does not know: a rollback below the version that wrote it.
                // Disarming beats guessing — the run keeps its clock and nothing silently fires.
                vec![disarm_wait_op(hub_id, &wait_id)]
            }
        };
        let mut ops = ops;
        ops.push(crate::outbox::delivery_op(hub_id, event_id, &listener));
        db.execute_tx(&ops).await?;
        fired += 1;
    }
    Ok(fired)
}

/// The armed waits this event could possibly move.
///
/// The partial index is `(hub_id, event_name, correlate_value) WHERE status = 'armed'`. The first
/// two columns come from the event itself; the third is narrowed with an `IN` built from the
/// scalar values the payload actually carries — the correlated value is by definition one of them,
/// so the list is a superset filter that is free to be approximate. With a very wide payload the
/// narrowing is dropped and the two-column prefix carries the lookup.
async fn candidates(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_name: &str,
    scope: &Json,
) -> Result<Vec<Json>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("event_name".into(), json!(event_name));
    p.insert("lim".into(), json!(MAX_CANDIDATES));

    let values = scalar_values(&scope["event"]);
    let narrowing = if values.is_empty() || values.len() > MAX_NARROWING_VALUES {
        String::new()
    } else {
        let terms: Vec<String> = values
            .iter()
            .enumerate()
            .map(|(i, v)| {
                p.insert(format!("cv{i}"), json!(v));
                format!(":cv{i}")
            })
            .collect();
        format!(" AND w.correlate_value IN ({})", terms.join(", "))
    };

    let sql = format!(
        "SELECT w.id, w.run_id, w.flow_id, w.step_id, w.step_index, w.kind, w.filter, \
                w.correlate, w.until_path, w.offset_seconds, w.max_wait, w.past_due_policy, \
                w.reschedules \
           FROM _flow_run_waits w \
          WHERE w.hub_id = :hub_id AND w.event_name = :event_name AND w.status = 'armed' \
            AND w.deleted_at IS NULL{narrowing} \
          ORDER BY w.created_at, w.id LIMIT :lim"
    );
    Ok(db.query(&sql, &p).await?.rows)
}

/// Does this wait's filter pass AND does every correlated pair agree?
///
/// Both halves are evaluated here rather than in SQL for the same reason the trigger's filter is:
/// the condition language is the kernel's, and re-expressing nine operators as SQL would be a
/// second implementation to keep in step with the first.
fn matches(row: &Json, scope: &Json) -> bool {
    let filter = serde_json::from_str::<Json>(&text(row, "filter"))
        .ok()
        .and_then(|v| Condition::parse(&v).ok())
        .unwrap_or_default();
    if !filter.matches(scope) {
        return false;
    }
    let Ok(Json::Object(correlate)) = serde_json::from_str::<Json>(&text(row, "correlate")) else {
        // A row whose correlation cannot be read must not match everything.
        return false;
    };
    if correlate.is_empty() {
        return false;
    }
    correlate.iter().all(|(event_path, expected)| {
        def::resolve_path(event_path, scope)
            .as_ref()
            .and_then(as_text)
            .is_some_and(|found| Some(found) == expected.as_str().map(|s| s.to_string()))
    })
}

// ── The transitions ───────────────────────────────────────────────────────────────────────────

/// **Cancel.** One statement: the run leaves the wait, its siblings are disarmed and this wait is
/// recorded as the one that fired — all of it conditional on the run still being asleep at exactly
/// this step. Zero rows there means the timer or a sibling already won, and then the CTEs below it
/// touch nothing: the whole transition is a no-op, which is the correct answer and not a failure.
fn cancel_ops(hub_id: &str, row: &Json) -> Vec<(String, Params)> {
    let mut p = base_params(hub_id, row);
    p.insert(
        "reason".into(),
        json!(format!(
            "flow.wait_cancelled: an event cancelled this wait before its instant arrived (step \
             `{}`)",
            text(row, "step_id")
        )),
    );
    vec![(
        "WITH won AS (\
           UPDATE _flow_runs SET status = 'cancelled', last_error = :reason, wake_at = NULL, \
                  claim_expires_at = NULL, finished_at = :now, updated_at = :now \
            WHERE id = :run_id AND hub_id = :hub_id AND status = 'sleeping' \
              AND current_step = :step_index AND deleted_at IS NULL \
           RETURNING id\
         ), siblings AS (\
           UPDATE _flow_run_waits SET status = 'disarmed', deleted_at = :now, updated_at = :now \
            WHERE hub_id = :hub_id AND run_id = :run_id AND status = 'armed' AND id <> :wait_id \
              AND EXISTS (SELECT 1 FROM won) \
           RETURNING id\
         ) \
         UPDATE _flow_run_waits SET status = 'fired', updated_at = :now \
          WHERE id = :wait_id AND hub_id = :hub_id AND EXISTS (SELECT 1 FROM won)"
            .to_string(),
        p,
    )]
}

/// What a reschedule decided, so that **who prices a failure** is not this function's business.
///
/// A broken wait is a step that FAILED, and what a failure costs the run is the step's `on_error`
/// (hub#1635) — the same question the tick and `complete_io` each ask at their own seam. Answering
/// it needs the DOCUMENT, and reading the document needs the database, so the pure op-builder says
/// what broke and [`failure_ops`] says what it costs.
enum Reschedule {
    /// The wait moves, or the run ends for a reason that is NOT a failure (`past_due_policy:
    /// "skip"` finishes it `done`, and a `done` run has nothing to carry on to).
    Ops(Vec<(String, Params)>),
    /// The wait broke, and this is why, in the words the run's `last_error` would have carried.
    Failed(String),
}

/// **What a broken wait costs the run** (hub#1635) — the THIRD seam, after the tick and
/// `complete_io`, and the one that had been missed: `delay` accepts `on_error` and the schema
/// promises it by name, so four of its five exits were honouring a key nobody read.
///
/// Same question and same answer as the other two, deliberately: the policy comes from the
/// DOCUMENT (via [`executor::step_error_policy`], which is fail-CLOSED when it cannot be read),
/// `stop` is the default, and `continue` NEVER re-runs anything — it moves to the step after this
/// one so that whoever was waiting gets told.
async fn failure_ops(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    row: &Json,
    reason: &str,
) -> Result<Vec<(String, Params)>> {
    // 🔴 **The wait is parked one step PAST the `delay` that armed it.** The step counter advances
    // with the sleep (`executor`: «waking resumes AFTER the delay»), so `step_index` on this row is
    // where the run will RESUME, and the step whose `on_error` governs is the one before it. Asking
    // the wrong index reads the policy of the step that has not run yet — which is exactly how this
    // key becomes a silent no-op, the bug being fixed here.
    let Some(delay_index) = row["step_index"].as_i64().and_then(|i| i.checked_sub(1)) else {
        return Ok(vec![finish_ops(hub_id, row, store::STATUS_FAILED, reason)]);
    };
    match executor::step_error_policy(db, hub_id, &text(row, "flow_id"), delay_index).await {
        ErrorPolicy::Stop => Ok(vec![finish_ops(hub_id, row, store::STATUS_FAILED, reason)]),
        ErrorPolicy::Continue => Ok(vec![
            continue_op(db, hub_id, row, delay_index, reason).await?,
        ]),
    }
}

/// The `continue` half: the run leaves the wait for the step AFTER it, with how this one ended
/// readable at `steps.<id>` — the same two keys (`status`, `error`) the other two seams write, so
/// the step that tells somebody reads ONE shape however the failure happened.
///
/// It keeps the conditional-`UPDATE` shape of [`finish_ops`] for the same reason: the condition
/// that decides the race also decides the disarm. `status = 'pending'` (not `sleeping`) with
/// `wake_at` cleared is what puts it back in the queue; the index moves BEFORE anything else, so
/// there is no reading of this row that could run the broken wait a second time — carrying on is
/// not retrying.
async fn continue_op(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    row: &Json,
    delay_index: i64,
    reason: &str,
) -> Result<(String, Params)> {
    let mut q = Params::new();
    q.insert("run_id".into(), json!(text(row, "run_id")));
    q.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT vars FROM _flow_runs \
              WHERE id = :run_id AND hub_id = :hub_id AND deleted_at IS NULL",
            &q,
        )
        .await?;
    let mut vars = executor::parse_json(
        res.rows
            .first()
            .and_then(|r| r["vars"].as_str())
            .unwrap_or("{}"),
    );
    executor::set_step_output(
        &mut vars,
        &text(row, "step_id"),
        executor::failure_output(json!({}), reason),
    );

    let mut p = base_params(hub_id, row);
    p.insert("delay_index".into(), json!(delay_index));
    p.insert("vars".into(), json!(vars.to_string()));
    p.insert("reason".into(), json!(reason));
    // **The index is NOT moved here — it already moved.** It advanced when the run went to sleep,
    // so `current_step` is the step AFTER the delay and carrying on is `status = 'pending'` with
    // the clock cleared. Moving it again would SKIP the step that tells somebody, which is the very
    // step this primitive exists to reach. Nothing is re-run either way: continuing is not retrying.
    Ok((
        "WITH won AS (\
           UPDATE _flow_runs SET status = 'pending', vars = :vars, wake_at = NULL, \
                  claim_expires_at = NULL, updated_at = :now \
            WHERE id = :run_id AND hub_id = :hub_id AND status = 'sleeping' \
              AND current_step = :step_index AND deleted_at IS NULL \
           RETURNING id\
         ), stepped AS (\
           UPDATE _flow_run_steps SET status = 'failed', error = :reason, finished_at = :now \
            WHERE hub_id = :hub_id AND run_id = :run_id AND step_index = :delay_index \
              AND deleted_at IS NULL AND EXISTS (SELECT 1 FROM won)\
         ) \
         UPDATE _flow_run_waits SET status = 'disarmed', deleted_at = :now, updated_at = :now \
          WHERE hub_id = :hub_id AND run_id = :run_id AND status = 'armed' \
            AND EXISTS (SELECT 1 FROM won)"
            .to_string(),
        p,
    ))
}

/// **Reschedule.** The new instant comes from the ARRIVING event, with the step's own
/// `offset_seconds` re-applied — «24 h before» stays «24 h before» when the appointment moves.
///
/// There is no old timer to cancel, and that is a property of the design rather than a claim: a
/// sleeping run has ONE `wake_at`, not a queue of scheduled jobs, so moving the wait is writing a
/// column. Whatever else this run's waits are, they keep pointing at the same row.
fn reschedule_ops(hub_id: &str, row: &Json, scope: &Json) -> Reschedule {
    let step_id = text(row, "step_id");
    let policy = PastDuePolicy::parse(&text(row, "past_due_policy")).unwrap_or_default();
    let done = row["reschedules"].as_i64().unwrap_or(0);

    // The runaway guard. An event that keeps arriving would push the same wait forward forever and
    // the run would never end — the same shape as `MAX_RUNS_PER_MINUTE`, one level down.
    if done + 1 > MAX_RESCHEDULES {
        return Reschedule::Failed(format!(
            "{ERR_MAX_RESCHEDULES}: step `{step_id}` was moved {MAX_RESCHEDULES} times and \
             stopped being moved. A wait that keeps being pushed forward is a run that never ends."
        ));
    }

    let until_path = text(row, "until_path");
    let resolved = def::resolve_path(&until_path, scope).unwrap_or(Json::Null);
    let Some(instant) = resolved
        .as_str()
        .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
    else {
        return Reschedule::Failed(format!(
            "step `{step_id}`: the event that should have moved this wait resolves \
             `{until_path}` to {resolved}, which is not an RFC-3339 instant"
        ));
    };

    let offset = row["offset_seconds"].as_i64().unwrap_or(0);
    let now = chrono::Utc::now();
    let wake_at = instant.with_timezone(&chrono::Utc) + chrono::Duration::seconds(offset);
    let horizon = row["max_wait"].as_i64().unwrap_or(def::MAX_DELAY_HORIZON);

    if wake_at > now + chrono::Duration::seconds(horizon) {
        return Reschedule::Failed(format!(
            "{ERR_DELAY_HORIZON}: step `{step_id}` was moved to {}, past the {horizon} s this \
             wait may cover",
            wake_at.to_rfc3339()
        ));
    }

    // The instant it was moved TO has already gone by. The same three answers as entering the step
    // with a past instant, decided by the same document key — one meaning for `past_due_policy`,
    // not two.
    if wake_at <= now {
        match policy {
            PastDuePolicy::Skip => {
                return Reschedule::Ops(vec![finish_ops(
                    hub_id,
                    row,
                    store::STATUS_DONE,
                    &format!(
                        "step `{step_id}`: the wait was moved to an instant that had already \
                         passed and `past_due_policy` is `skip`"
                    ),
                )])
            }
            PastDuePolicy::Fail => {
                return Reschedule::Failed(format!(
                    "{}: step `{step_id}` was moved to {}, which had already passed",
                    def::ERR_DELAY_PAST_DUE,
                    wake_at.to_rfc3339()
                ))
            }
            // `continue_now` needs nothing special: a `wake_at` in the past is what the timer is
            // for, and the next tick picks the run up.
            PastDuePolicy::ContinueNow => {}
        }
    }

    let mut p = base_params(hub_id, row);
    p.insert("wake_at".into(), json!(wake_at.to_rfc3339()));
    Reschedule::Ops(vec![(
        "WITH won AS (\
           UPDATE _flow_runs SET wake_at = :wake_at, updated_at = :now \
            WHERE id = :run_id AND hub_id = :hub_id AND status = 'sleeping' \
              AND current_step = :step_index AND deleted_at IS NULL \
           RETURNING id\
         ) \
         UPDATE _flow_run_waits SET reschedules = reschedules + 1, updated_at = :now \
          WHERE hub_id = :hub_id AND run_id = :run_id AND status = 'armed' \
            AND EXISTS (SELECT 1 FROM won)"
            .to_string(),
        p,
    )])
}

/// Ends the run and disarms every wait it has, conditional on it still being asleep at this step.
/// The shape `executor::finish` gives a run that stops itself, written as one statement so the
/// condition that decides the race also decides the disarm.
fn finish_ops(hub_id: &str, row: &Json, status: &str, reason: &str) -> (String, Params) {
    let mut p = base_params(hub_id, row);
    p.insert("status".into(), json!(status));
    p.insert("reason".into(), json!(reason));
    (
        "WITH won AS (\
           UPDATE _flow_runs SET status = :status, last_error = :reason, wake_at = NULL, \
                  claim_expires_at = NULL, finished_at = :now, updated_at = :now \
            WHERE id = :run_id AND hub_id = :hub_id AND status = 'sleeping' \
              AND current_step = :step_index AND deleted_at IS NULL \
           RETURNING id\
         ) \
         UPDATE _flow_run_waits SET status = 'disarmed', deleted_at = :now, updated_at = :now \
          WHERE hub_id = :hub_id AND run_id = :run_id AND status = 'armed' \
            AND EXISTS (SELECT 1 FROM won)"
            .to_string(),
        p,
    )
}

fn disarm_wait_op(hub_id: &str, wait_id: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("wait_id".into(), json!(wait_id));
    p.insert("now".into(), json!(now_rfc3339()));
    (
        "UPDATE _flow_run_waits SET status = 'disarmed', deleted_at = :now, updated_at = :now \
         WHERE id = :wait_id AND hub_id = :hub_id"
            .to_string(),
        p,
    )
}

fn base_params(hub_id: &str, row: &Json) -> Params {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("wait_id".into(), json!(text(row, "id")));
    p.insert("run_id".into(), json!(text(row, "run_id")));
    p.insert(
        "step_index".into(),
        json!(row["step_index"].as_i64().unwrap_or(0)),
    );
    p.insert("now".into(), json!(now_rfc3339()));
    p
}

// ── Small shared helpers ──────────────────────────────────────────────────────────────────────

fn text(row: &Json, key: &str) -> String {
    row[key].as_str().unwrap_or_default().to_string()
}

/// A JSON value as the TEXT a correlation compares. Numbers included, because an id travels as a
/// number in one module's payload and as a string in another's, and «appointment 42» is the same
/// appointment either way. Objects and arrays are not keys and answer `None`.
fn as_text(v: &Json) -> Option<String> {
    match v {
        Json::String(s) => Some(s.clone()),
        Json::Number(n) => Some(n.to_string()),
        Json::Bool(b) => Some(b.to_string()),
        _ => None,
    }
}

/// Every scalar an event payload carries, as text, deduplicated. Walks two levels down, which is
/// as deep as the path language can reach into a payload anyway.
fn scalar_values(payload: &Json) -> Vec<String> {
    fn walk(v: &Json, depth: usize, out: &mut Vec<String>) {
        if out.len() > MAX_NARROWING_VALUES {
            return;
        }
        match v {
            Json::Object(map) if depth < 3 => {
                for value in map.values() {
                    walk(value, depth + 1, out);
                }
            }
            Json::Array(items) if depth < 3 => {
                for value in items {
                    walk(value, depth + 1, out);
                }
            }
            other => {
                if let Some(t) = as_text(other) {
                    if !out.contains(&t) {
                        out.push(t);
                    }
                }
            }
        }
    }
    let mut out = Vec::new();
    walk(payload, 0, &mut out);
    out
}

async fn delivery_exists(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_id: &str,
    listener: &str,
) -> Result<bool> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("event_id".into(), json!(event_id));
    p.insert("listener_command".into(), json!(listener));
    let res = db
        .query(
            "SELECT 1 AS ok FROM _event_delivery \
             WHERE event_id = :event_id AND listener_command = :listener_command \
               AND hub_id = :hub_id",
            &p,
        )
        .await?;
    Ok(!res.rows.is_empty())
}

async fn mark_delivered(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_id: &str,
    listener: &str,
) -> Result<()> {
    let (sql, p) = crate::outbox::delivery_op(hub_id, event_id, listener);
    db.execute(&sql, &p).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_synthetic_listener_cannot_collide_with_a_module_command() {
        // A command name never starts with `_`; that is what makes this namespace safe, and it is
        // the same trick `_flow:<trigger_id>` has used since hub#661.
        let listener = synthetic_listener("abc");
        assert_eq!(listener, "_flow_wait:abc");
        assert!(listener.starts_with('_'));
    }

    #[test]
    fn a_correlation_compares_a_number_and_its_text_as_the_same_id() {
        // An id travels as a number in one module's payload and as a string in another's. A
        // correlation that told them apart would silently never fire.
        let row = json!({
            "filter": "{}",
            "correlate": json!({ "event.id": "42" }).to_string(),
        });
        assert!(matches(&row, &json!({ "event": { "id": 42 } })));
        assert!(matches(&row, &json!({ "event": { "id": "42" } })));
        assert!(!matches(&row, &json!({ "event": { "id": 43 } })));
        // The field missing altogether is NOT a match: that is the empty-key hole.
        assert!(!matches(&row, &json!({ "event": { "other": 1 } })));
    }

    #[test]
    fn every_pair_of_a_composite_correlation_has_to_agree() {
        let row = json!({
            "filter": "{}",
            "correlate": json!({ "event.id": "42", "event.tenant": "acme" }).to_string(),
        });
        assert!(matches(
            &row,
            &json!({ "event": { "id": 42, "tenant": "acme" } })
        ));
        assert!(!matches(
            &row,
            &json!({ "event": { "id": 42, "tenant": "other" } })
        ));
    }

    /// A row whose correlation cannot be read must match NOTHING. The alternative — an empty map
    /// that `all()` answers true for — is a wait that fires on every occurrence of its event.
    #[test]
    fn an_unreadable_or_empty_correlation_matches_nothing() {
        for correlate in ["", "{}", "not json"] {
            let row = json!({ "filter": "{}", "correlate": correlate });
            assert!(
                !matches(&row, &json!({ "event": { "id": 42 } })),
                "{correlate}"
            );
        }
    }

    #[test]
    fn the_filter_is_evaluated_before_the_correlation_and_both_have_to_pass() {
        let row = json!({
            "filter": json!({ "event.status": { "eq": "confirmed" } }).to_string(),
            "correlate": json!({ "event.id": "42" }).to_string(),
        });
        assert!(matches(
            &row,
            &json!({ "event": { "id": 42, "status": "confirmed" } })
        ));
        assert!(!matches(
            &row,
            &json!({ "event": { "id": 42, "status": "draft" } })
        ));
    }

    #[test]
    fn the_narrowing_list_carries_the_values_a_correlation_could_possibly_use() {
        let values = scalar_values(&json!({
            "id": 42, "customer": { "email": "a@b.c" }, "tags": ["x"], "nested": { "deep": { "z": 1 } }
        }));
        assert!(values.contains(&"42".to_string()));
        assert!(values.contains(&"a@b.c".to_string()));
        assert!(values.contains(&"x".to_string()));
    }
}
