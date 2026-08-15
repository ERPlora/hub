//! Reading and writing flows, their triggers and their runs — the layer the REST contract of
//! ADR-0283 §9 sits directly on top of.
//!
//! Two decisions live here rather than in the HTTP layer, because they are about the data and not
//! about the wire:
//!
//! - **Saving a flow re-materialises its triggers** (`seed_triggers`), idempotently and
//!   **preserving `next_run`**. The pattern is `scheduler::seed_module_tasks`, and for the same
//!   reason: renaming a flow must not silently reschedule its nightly job to right now. A trigger
//!   is identified inside its flow by what makes it fire (`event:sale.completed`, `cron:0 9 * * *`),
//!   so reordering the list in the editor moves nothing.
//! - **Deleting a flow revokes its grants.** A soft-deleted flow that kept live grants would be a
//!   set of permissions with no owner — and the row is the only thing that says who could do what.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::flows::def::{FlowDefinition, StepSpec, TriggerDef, TriggerKind};
use crate::flows::grants;
use crate::registry::{new_id, now_rfc3339, Registry};
use crate::scheduler::cron;

pub const ERR_FLOW_NOT_FOUND: &str = "flow.not_found";

/// The reason stamped on a run that was still in flight when its flow was deleted (hub#771). The
/// executor's [`crate::flows::executor::ERR_FLOW_GONE`] is the same idea discovered later — by a
/// tick that wakes a sleeping run and finds the definition missing — and this is the door that
/// shuts before the delay ever comes due.
pub const ERR_FLOW_DELETED: &str = "flow.flow_deleted";

/// A flow as the API shows it. `definition` travels as the parsed document, not as a string: the
/// caller sent JSON and gets JSON back.
#[derive(Debug, Clone, serde::Serialize)]
pub struct Flow {
    pub id: String,
    pub name: String,
    pub enabled: bool,
    pub schema_version: i64,
    pub definition: Json,
    pub created_at: String,
    pub created_by: String,
    pub updated_at: String,
    pub updated_by: String,
}

/// What a `POST`/`PUT` carries. The definition is validated before anything touches the database.
#[derive(Debug, Clone)]
pub struct NewFlow {
    pub name: String,
    pub enabled: bool,
    pub definition: Json,
}

/// One execution.
#[derive(Debug, Clone, serde::Serialize)]
pub struct FlowRun {
    pub id: String,
    pub flow_id: String,
    pub trigger_kind: String,
    pub parent_event_id: String,
    pub status: String,
    pub current_step: i64,
    pub input: Json,
    pub depth: i64,
    pub attempts: i64,
    pub last_error: String,
    pub wake_at: Option<String>,
    pub started_at: Option<String>,
    pub finished_at: Option<String>,
    pub created_at: String,
}

/// One step of one execution, with the output later steps read as `steps.<step_id>.<field>`.
#[derive(Debug, Clone, serde::Serialize)]
pub struct FlowRunStep {
    pub step_index: i64,
    pub step_id: String,
    pub kind: String,
    pub status: String,
    pub input: Json,
    pub output: Json,
    pub error: String,
    pub started_at: Option<String>,
    pub finished_at: Option<String>,
}

/// Run statuses. `sleeping` is a `delay` waiting on `wake_at`; `waiting_approval` is a write a
/// model proposed and a person has not decided yet (hub#665).
///
/// An I/O step in flight has NO status of its own: the run stays `running` and **keeps its lease**
/// (hub#662's seam), which is what makes the next tick skip it and start the turn exactly once.
/// `waiting_approval` is different because it lasts until a person acts, which can be hours — a
/// held lease would expire and the run would be reclaimed with its proposal still in the tray. It
/// is deliberately not a status [`crate::flows::executor::tick`] claims, so no amount of ticking
/// smuggles an unapproved write through.
pub const STATUS_PENDING: &str = "pending";
pub const STATUS_RUNNING: &str = "running";
pub const STATUS_SLEEPING: &str = "sleeping";
pub const STATUS_WAITING_APPROVAL: &str = "waiting_approval";
pub const STATUS_DONE: &str = "done";
pub const STATUS_FAILED: &str = "failed";
pub const STATUS_CANCELLED: &str = "cancelled";

fn not_found(id: &str) -> RuntimeError {
    RuntimeError::Domain {
        code: ERR_FLOW_NOT_FOUND.to_string(),
        message: format!("no flow `{id}` in this hub"),
    }
}

// ── flows ─────────────────────────────────────────────────────────────────────────────────────

/// Every command a document NAMES: the `command` steps, and the writes an `ai` step declares as
/// tools. Both are places where an author says «this flow may call that», and both are judged by
/// the same rule (hub#824).
fn commands_named_by(def: &FlowDefinition) -> Vec<&str> {
    def.steps
        .iter()
        .flat_map(|step| match &step.spec {
            StepSpec::Command { command, .. } => vec![command.as_str()],
            StepSpec::Ai(ai) => ai.commands.iter().map(String::as_str).collect(),
            _ => Vec::new(),
        })
        .collect()
}

/// **The save-time half of hub#824.** A document naming an INTERNAL command is a flow this hub can
/// never execute — `execute_at` bars internals to `Origin::Automation` as it does to `External`
/// (flows.md §2) — so it is refused here, which is what §13.2 already demands of everything else the
/// hub cannot run: refused at save, not stored to stall forever.
///
/// It shares [`grants::refuse_internal_command`] with the grants door on purpose, and inherits its
/// silence about UNKNOWN commands: a flow may name a module that is not installed yet.
fn check_commands(registry: &Registry, def: &FlowDefinition) -> Result<()> {
    for command in commands_named_by(def) {
        grants::refuse_internal_command(registry, command)?;
    }
    Ok(())
}

pub async fn create(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    registry: &Registry,
    new: &NewFlow,
    by: &str,
) -> Result<Flow> {
    // Parse BEFORE writing: a stored document that does not parse is a flow that fails at 3 AM
    // instead of at the screen where it was written.
    let def = FlowDefinition::parse(&new.definition)?;
    check_commands(registry, &def)?;
    let id = new_id();
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(new.name));
    p.insert("enabled".into(), json!(i64::from(new.enabled)));
    p.insert("schema_version".into(), json!(def.schema_version));
    p.insert("definition".into(), json!(new.definition.to_string()));
    p.insert("now".into(), json!(now));
    p.insert("by".into(), json!(by));
    db.execute(
        "INSERT INTO _flow (id, hub_id, name, enabled, schema_version, definition, \
                            created_at, created_by, updated_at, updated_by) \
         VALUES (:id, :hub_id, :name, :enabled, :schema_version, :definition, \
                 :now, :by, :now, :by)",
        &p,
    )
    .await?;
    seed_triggers(db, hub_id, &id, &def, new.enabled).await?;
    get(db, hub_id, &id).await
}

pub async fn update(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    registry: &Registry,
    new: &NewFlow,
    by: &str,
) -> Result<Flow> {
    let def = FlowDefinition::parse(&new.definition)?;
    check_commands(registry, &def)?;
    get(db, hub_id, id).await?; // 404 before mutating, and scoped to this hub.
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(new.name));
    p.insert("enabled".into(), json!(i64::from(new.enabled)));
    p.insert("schema_version".into(), json!(def.schema_version));
    p.insert("definition".into(), json!(new.definition.to_string()));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("by".into(), json!(by));
    db.execute(
        "UPDATE _flow SET name = :name, enabled = :enabled, schema_version = :schema_version, \
                          definition = :definition, updated_at = :now, updated_by = :by \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    seed_triggers(db, hub_id, id, &def, new.enabled).await?;
    get(db, hub_id, id).await
}

pub async fn get(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<Flow> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, name, enabled, schema_version, definition, created_at, created_by, \
                    updated_at, updated_by \
             FROM _flow WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
            &p,
        )
        .await?;
    res.rows.first().map(flow_row).ok_or_else(|| not_found(id))
}

pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<Flow>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, name, enabled, schema_version, definition, created_at, created_by, \
                    updated_at, updated_by \
             FROM _flow WHERE hub_id = :hub_id AND deleted_at IS NULL ORDER BY created_at, id",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(flow_row).collect())
}

/// Soft-deletes a flow, disarms its triggers, **cancels its not-yet-finished runs** and
/// **revokes its grants**. These go together: leaving a live grant behind would be an
/// authorisation whose owner no longer exists; a live trigger would keep creating runs for a flow
/// the owner believes is gone; and a run left `sleeping` on a `delay` (or `pending` in the queue)
/// would keep lying in the history — «waiting» about a flow that no longer exists — until the
/// delay came due and the tick woke it to find the definition missing (hub#771).
pub async fn delete(db: &dyn DatabaseAdapter, hub_id: &str, id: &str, by: &str) -> Result<()> {
    get(db, hub_id, id).await?;
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    p.insert("by".into(), json!(by));
    db.execute(
        "UPDATE _flow SET deleted_at = :now, deleted_by = :by, updated_at = :now, updated_by = :by \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    db.execute(
        "UPDATE _flow_triggers SET deleted_at = :now, enabled = 0, updated_at = :now \
         WHERE flow_id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    // Cancel the runs that have NOT finished yet, in the same gesture as the delete. A run parked
    // on a `delay` (`sleeping`, `wake_at` in the future) is the bug this closes (hub#771): before,
    // it survived the delete and only changed to `cancelled` when the delay came due and the tick
    // woke it to find a definition that was no longer there — days late, with a history that lied
    // in the meantime. `pending` is the same honesty for a run that never got its first tick.
    //
    // Only `sleeping` and `pending` are touched: `done`/`failed`/`cancelled` are HISTORY (the run
    // happened, and the row is the record of it), and a run that is genuinely `running` — claimed
    // by a tick, or holding a lease while its I/O is in flight — is left to the seam that already
    // knows what to do with a flow that disappears mid-flight: the executor's `definition_gone`
    // door and `complete_io`'s «a run whose flow is gone must not resume just because a server
    // answered». Cancelling an in-flight run here would race that seam for no gain — the lease and
    // the re-read are already the control.
    //
    // `wake_at` is cleared so a cancelled run is not also «waiting to wake», and `finished_at` is
    // set so it reads as over, the same shape `executor::finish` gives a run that stops itself.
    db.execute(
        "UPDATE _flow_runs \
            SET status = 'cancelled', \
                last_error = :reason, \
                wake_at = NULL, claim_expires_at = NULL, finished_at = :now, updated_at = :now \
          WHERE flow_id = :id AND hub_id = :hub_id \
            AND status IN ('sleeping', 'pending') \
            AND deleted_at IS NULL",
        &{
            // The `last_error` carries the stable code (hub#139) so the half a caller programs
            // against is the same shape as the one the executor stamps on the late discovery
            // (`flow.definition_gone`), not just the prose.
            let mut q = Params::new();
            q.insert("id".into(), json!(id));
            q.insert("hub_id".into(), json!(hub_id));
            q.insert("now".into(), json!(now));
            q.insert(
                "reason".into(),
                json!(format!(
                    "{ERR_FLOW_DELETED}: the flow was deleted while this run was still in flight"
                )),
            );
            q
        },
    )
    .await?;
    grants::revoke_all(db, hub_id, id, by).await
}

fn flow_row(row: &Json) -> Flow {
    let text = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    Flow {
        id: text("id"),
        name: text("name"),
        enabled: truthy(&row["enabled"]),
        schema_version: row["schema_version"].as_i64().unwrap_or(1),
        definition: serde_json::from_str(&text("definition")).unwrap_or(Json::Null),
        created_at: text("created_at"),
        created_by: text("created_by"),
        updated_at: text("updated_at"),
        updated_by: text("updated_by"),
    }
}

/// `INTEGER` booleans come back as a number on Postgres and as a bool on nothing here, but the
/// adapter has changed shape before — reading both is cheaper than a wrong `false`.
fn truthy(v: &Json) -> bool {
    v.as_bool()
        .unwrap_or_else(|| v.as_i64().map(|n| n != 0).unwrap_or(false))
}

// ── triggers ──────────────────────────────────────────────────────────────────────────────────

/// The identity of a trigger inside its flow: what makes it fire. Deriving it from the content
/// (and not from the position in the array) is what lets the editor reorder triggers without
/// resetting a cron's clock.
fn trigger_key(t: &TriggerDef) -> String {
    let discriminator = match t.kind {
        TriggerKind::Event => t.event.as_str(),
        TriggerKind::Cron => t.cron.as_str(),
        TriggerKind::At => t.at.as_str(),
        TriggerKind::Manual => "",
    };
    format!("{}:{}", t.kind.as_str(), discriminator)
}

/// Materialises the triggers of a definition into `_flow_triggers`. Idempotent: an existing
/// trigger keeps its `next_run`/`last_run` and only refreshes what the document says; a trigger
/// that left the document is soft-deleted (the capability was withdrawn).
pub async fn seed_triggers(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    def: &FlowDefinition,
    flow_enabled: bool,
) -> Result<()> {
    let now = now_rfc3339();
    // The clock a `cron` trigger is read on: the BUSINESS one (hub#731). It is resolved once per
    // save, from the hub's settings — not stored in the document — so that correcting the hub's
    // country fixes every flow at once instead of asking the owner to re-save each of them.
    let tz = crate::settings::timezone_of(db, hub_id).await?;
    let mut keys: Vec<String> = Vec::new();

    for trigger in &def.triggers {
        let key = trigger_key(trigger);
        keys.push(key.clone());

        // Only the clock kinds carry a `next_run`. `at` is one-shot: its instant IS its due date,
        // and firing disables it. (`at` needs no zone: the author wrote a full instant, offset
        // included — that is what makes it RFC-3339 and why the gate now demands it.)
        let next_run = match trigger.kind {
            TriggerKind::Cron => cron::next_after_in_tz(&trigger.cron, &now, tz),
            TriggerKind::At => Some(trigger.at.clone()),
            _ => None,
        };

        let mut p = Params::new();
        p.insert("id".into(), json!(new_id()));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("flow_id".into(), json!(flow_id));
        p.insert("key".into(), json!(key));
        p.insert("kind".into(), json!(trigger.kind.as_str()));
        p.insert("event_name".into(), json!(trigger.event));
        p.insert("filter".into(), json!(trigger.filter.to_json().to_string()));
        p.insert(
            "input_map".into(),
            json!(Json::Object(trigger.input.clone()).to_string()),
        );
        p.insert("cron".into(), json!(trigger.cron));
        p.insert("run_at".into(), json!(trigger.at));
        p.insert("enabled".into(), json!(i64::from(flow_enabled)));
        p.insert("next_run".into(), json!(next_run));
        p.insert(
            "tz".into(),
            json!(if trigger.kind == TriggerKind::Cron { tz.name() } else { "" }),
        );
        p.insert("now".into(), json!(now));
        // The upsert deliberately does NOT touch `next_run` (nor the `tz` it was computed under):
        // re-saving a flow must not reschedule a nightly job to now (`seed_module_tasks`, hub#570).
        db.execute(
            "INSERT INTO _flow_triggers \
               (id, hub_id, flow_id, trigger_key, kind, event_name, filter, input_map, cron, \
                run_at, enabled, next_run, tz, created_at, updated_at) \
             VALUES (:id, :hub_id, :flow_id, :key, :kind, :event_name, :filter, :input_map, :cron, \
                     :run_at, :enabled, :next_run, :tz, :now, :now) \
             ON CONFLICT (hub_id, flow_id, trigger_key) WHERE deleted_at IS NULL DO UPDATE SET \
               kind = :kind, event_name = :event_name, filter = :filter, input_map = :input_map, \
               cron = :cron, run_at = :run_at, enabled = :enabled, updated_at = :now",
            &p,
        )
        .await?;
    }

    // Anything no longer in the document stops existing: a trigger the author deleted must stop
    // creating runs, not keep firing because nobody swept it.
    let mut q = Params::new();
    q.insert("hub_id".into(), json!(hub_id));
    q.insert("flow_id".into(), json!(flow_id));
    let existing = db
        .query(
            "SELECT id, trigger_key FROM _flow_triggers \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL",
            &q,
        )
        .await?;
    for row in &existing.rows {
        let key = row["trigger_key"].as_str().unwrap_or_default().to_string();
        if keys.contains(&key) {
            continue;
        }
        let mut p = Params::new();
        p.insert("id".into(), json!(row["id"].as_str().unwrap_or_default()));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("now".into(), json!(now));
        db.execute(
            "UPDATE _flow_triggers SET deleted_at = :now, enabled = 0, updated_at = :now \
             WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
            &p,
        )
        .await?;
    }
    Ok(())
}

// ── runs ──────────────────────────────────────────────────────────────────────────────────────

/// Builds the `INSERT` of a run without executing it, so a caller can put it in **its own**
/// transaction. That is the whole contract of the on-event trigger (ADR-0283 §3): the relay
/// inserts the run and the delivery marker atomically, and the tick — never the relay — executes
/// it. A relay that ran flows inline would hold the global lock for as long as the flow takes.
pub fn insert_run_op(
    hub_id: &str,
    flow_id: &str,
    trigger_id: &str,
    trigger_kind: &str,
    parent_event_id: &str,
    input: &Json,
    depth: i64,
    created_by: &str,
) -> (String, Params) {
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(new_id()));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("trigger_id".into(), json!(trigger_id));
    p.insert("trigger_kind".into(), json!(trigger_kind));
    p.insert("parent_event_id".into(), json!(parent_event_id));
    p.insert("input".into(), json!(input.to_string()));
    p.insert("depth".into(), json!(depth));
    p.insert("now".into(), json!(now));
    p.insert("by".into(), json!(created_by));
    let sql = "INSERT INTO _flow_runs \
        (id, hub_id, flow_id, trigger_id, trigger_kind, parent_event_id, status, current_step, \
         input, vars, depth, attempts, last_error, created_at, created_by, updated_at) \
        VALUES (:id, :hub_id, :flow_id, :trigger_id, :trigger_kind, :parent_event_id, 'pending', \
                0, :input, '{}', :depth, 0, '', :now, :by, :now)";
    (sql.to_string(), p)
}

/// Starts a run outside any transaction (manual runs, the cron sweep). Returns its id.
pub async fn start_run(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    trigger_id: &str,
    trigger_kind: &str,
    parent_event_id: &str,
    input: &Json,
    depth: i64,
    created_by: &str,
) -> Result<String> {
    let (sql, p) = insert_run_op(
        hub_id,
        flow_id,
        trigger_id,
        trigger_kind,
        parent_event_id,
        input,
        depth,
        created_by,
    );
    let id = p["id"].as_str().unwrap_or_default().to_string();
    db.execute(&sql, &p).await?;
    Ok(id)
}

/// The largest page of runs one request may take. The rows carry each run's input, so a listing
/// nobody bounded is a screen that stops loading on the first hub that uses flows in earnest.
pub const MAX_RUNS_PAGE: i64 = 200;

/// The history of one flow, **newest first**, paged by cursor.
///
/// `before` is the id of the last run of the previous page — «older than this one». It is a cursor
/// and not an `OFFSET` because runs keep arriving at the head while somebody is reading: with an
/// offset, every new run shifts the page under them and a row is served twice or skipped. An
/// unknown `before` yields nothing rather than silently restarting from the top, which would be the
/// same duplicate with a friendlier face.
///
/// Reads `ix_flow_run_flow (hub_id, flow_id, created_at)`, which is why the order is by
/// `created_at` and the tie-break is the id.
pub async fn list_runs(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    limit: i64,
    before: Option<&str>,
) -> Result<Vec<FlowRun>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("limit".into(), json!(limit.clamp(1, MAX_RUNS_PAGE)));

    let anchor = match before {
        Some(id) if !id.is_empty() => match cursor_of(db, hub_id, id).await? {
            Some(created_at) => Some(created_at),
            // A cursor this hub does not have: an empty page. Falling back to the first page would
            // hand the caller rows they have already seen and call it pagination.
            None => return Ok(Vec::new()),
        },
        _ => None,
    };
    let keyset = match &anchor {
        Some(created_at) => {
            p.insert("before_at".into(), json!(created_at));
            p.insert("before_id".into(), json!(before.unwrap_or_default()));
            " AND (created_at, id) < (:before_at, :before_id)"
        }
        None => "",
    };

    let sql = format!(
        "SELECT id, flow_id, trigger_kind, parent_event_id, status, current_step, input, \
                depth, attempts, last_error, wake_at, started_at, finished_at, created_at \
         FROM _flow_runs \
         WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL{keyset} \
         ORDER BY created_at DESC, id DESC LIMIT :limit"
    );
    let res = db.query(&sql, &p).await?;
    Ok(res.rows.iter().map(run_row).collect())
}

/// The `created_at` of a run of THIS hub, so a cursor from another tenant resolves to nothing.
async fn cursor_of(db: &dyn DatabaseAdapter, hub_id: &str, run_id: &str) -> Result<Option<String>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(run_id));
    let res = db
        .query(
            "SELECT created_at FROM _flow_runs WHERE id = :id AND hub_id = :hub_id \
             AND deleted_at IS NULL",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["created_at"].as_str().map(|s| s.to_string())))
}

/// Arms the indexes the flow tables need but their creating migration did not know about.
///
/// **Idempotent, run at every boot, and deliberately NOT a numbered system migration** — the same
/// reasoning that puts `run_id`/`parent_event_id` in the outbox's `ENSURE_TABLES` and
/// `identity::forget_hub_id_as_device` on the boot path: an index is not a change to the shape of
/// the data, and a `CREATE INDEX IF NOT EXISTS` that costs nothing on the second boot does not need
/// a version. It also keeps additive work clear of the number races between parallel branches.
///
/// `ix_flow_run_parent` backs `runs_of_event` (the trace, hub#666), which v34 could not anticipate:
/// v34 indexed what the tick reads (`ix_flow_run_due`) and what the history reads
/// (`ix_flow_run_flow`). It is **partial** because most runs — every manual one, every cron one —
/// have no originating event, and an index over their empty string is paid for on every insert to
/// serve lookups nobody makes.
///
/// `ix_flow_run_prune` backs the retention sweep (hub#699, `crate::retention`), which looks for
/// runs by the age of their TERMINAL moment — a dimension neither `ix_flow_run_due` (live work,
/// keyed on `wake_at`) nor `ix_flow_run_flow` (history of one flow) offers. Partial over the three
/// terminal statuses for the same reason as above: a live run never enters it, so the tick that
/// claims runs pays nothing, and the sweep's repeated bounded passes are index scans.
///
/// Called AFTER `system_migrations::apply`: the tables have to exist first.
pub async fn ensure_indexes(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(
        "CREATE INDEX IF NOT EXISTS ix_flow_run_parent \
           ON _flow_runs (hub_id, parent_event_id) \
           WHERE parent_event_id <> '' AND deleted_at IS NULL;\
         CREATE INDEX IF NOT EXISTS ix_flow_run_prune \
           ON _flow_runs (hub_id, COALESCE(finished_at, created_at)) \
           WHERE status IN ('done', 'failed', 'cancelled');",
    )
    .await?;
    Ok(())
}

/// **Re-writes the `wake_at` of runs parked with a non-UTC offset** (hub#970).
///
/// `wake_sleeping` asks the database `wake_at <= :now`, and the column is TEXT: the comparison is
/// lexicographic, so it only answers «has this instant arrived?» while every string in it is UTC.
/// `delay.until` used to store the instant with the offset it was written in — `trigger.at`
/// documents that the offset IS part of the instant — so `…T09:00:00+02:00` sorted two hours late
/// and a `-05:00` sorted five hours early. The write side is fixed at the source
/// (`executor::run_step`), but the runs already asleep would never be touched again: the only
/// thing that reads a sleeping run is the comparison the offset breaks.
///
/// Not a numbered migration, on purpose — same criterion as [`ensure_indexes`] and
/// `identity::forget_hub_id_as_device`: it repairs an INVARIANT over data, not the shape of the
/// schema, so it must also reach a database restored from a backup taken before the fix, and
/// running it twice is a no-op (a `wake_at` already in UTC re-writes to itself).
///
/// Bounded by construction: only `sleeping` runs of this hub have a `wake_at` at all, and a hub
/// has as many of those as it has delays in flight.
pub async fn normalize_wake_at(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let parked = db
        .query(
            "SELECT id, wake_at FROM _flow_runs \
             WHERE hub_id = :hub_id AND status = :status AND wake_at IS NOT NULL \
               AND deleted_at IS NULL AND wake_at NOT LIKE '%+00:00'",
            &{
                let mut q = p.clone();
                q.insert("status".into(), json!(STATUS_SLEEPING));
                q
            },
        )
        .await?;
    for row in &parked.rows {
        let raw = row["wake_at"].as_str().unwrap_or_default();
        // Anything that is not an instant is left exactly as it is: this repairs a zone, it does
        // not invent a wake-up time for a row nobody can read.
        let Ok(instant) = chrono::DateTime::parse_from_rfc3339(raw) else {
            continue;
        };
        let mut q = Params::new();
        q.insert("id".into(), json!(row["id"].as_str().unwrap_or_default()));
        q.insert("hub_id".into(), json!(hub_id));
        q.insert("wake_at".into(), json!(to_utc_rfc3339(&instant)));
        db.execute(
            "UPDATE _flow_runs SET wake_at = :wake_at \
             WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
            &q,
        )
        .await?;
    }
    Ok(())
}

/// **An instant, as this kernel writes instants: UTC** (flows.md §3.2 — "UTC inside, the business
/// clock on screen"). The one place that turns a `DateTime<FixedOffset>` into a `wake_at`, so the
/// write path and the boot repair cannot disagree about what the column holds.
pub(crate) fn to_utc_rfc3339(instant: &chrono::DateTime<chrono::FixedOffset>) -> String {
    instant.with_timezone(&chrono::Utc).to_rfc3339()
}

/// The runs one event started — the forward half of «this sale set off these steps».
pub async fn runs_of_event(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_id: &str,
) -> Result<Vec<FlowRun>> {
    if event_id.is_empty() {
        return Ok(Vec::new());
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("event_id".into(), json!(event_id));
    p.insert("limit".into(), json!(MAX_RUNS_PAGE));
    let res = db
        .query(
            "SELECT id, flow_id, trigger_kind, parent_event_id, status, current_step, input, \
                    depth, attempts, last_error, wake_at, started_at, finished_at, created_at \
             FROM _flow_runs \
             WHERE hub_id = :hub_id AND parent_event_id = :event_id AND deleted_at IS NULL \
             ORDER BY created_at, id LIMIT :limit",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(run_row).collect())
}

/// One run with its steps — the shape `GET /api/hub/flows/runs/{run_id}` returns.
///
/// The steps come back **redacted against the flow's own definition** ([`redact_step`]): this is a
/// second door onto rows a step wrote, and a door that trusts the other one is the one that leaks.
pub async fn get_run(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
) -> Result<(FlowRun, Vec<FlowRunStep>)> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(run_id));
    let res = db
        .query(
            "SELECT id, flow_id, trigger_kind, parent_event_id, status, current_step, input, \
                    depth, attempts, last_error, wake_at, started_at, finished_at, created_at \
             FROM _flow_runs WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
            &p,
        )
        .await?;
    let run = res.rows.first().map(run_row).ok_or_else(|| not_found(run_id))?;
    let steps = db
        .query(
            "SELECT step_index, step_id, kind, status, input, output, error, started_at, finished_at \
             FROM _flow_run_steps \
             WHERE run_id = :id AND hub_id = :hub_id AND deleted_at IS NULL ORDER BY step_index",
            &p,
        )
        .await?;
    // The definition is read here, not carried on the run, because it is what says which fields of
    // a step hold a secret. **Deliberately through `definition_of` and not `get`**: `delete` is a
    // SOFT delete and the runs outlive it, so reading it through the ordinary door — which filters
    // `deleted_at IS NULL` — would make «press delete, then open the history» the way to read
    // every secret the flow ever sent.
    let definition = definition_of(db, hub_id, &run.flow_id).await?;
    Ok((
        run,
        steps
            .rows
            .iter()
            .map(|row| redact_step(&definition, step_row(row)))
            .collect(),
    ))
}

/// The stored document of a flow **including a soft-deleted one**, for redacting its history.
///
/// It is the one read in this file that ignores `deleted_at`, and only because of what it is for:
/// a deleted flow's runs survive it, and their steps must stay redacted afterwards. Nothing else
/// may use it to resurrect a flow — it returns the raw document, never a [`Flow`], so a caller
/// cannot mistake it for «the flow is still here». A missing flow yields `Null`, which redacts
/// nothing, which is right: no definition means no field was ever declared as a secret.
async fn definition_of(db: &dyn DatabaseAdapter, hub_id: &str, flow_id: &str) -> Result<Json> {
    let mut p = Params::new();
    p.insert("id".into(), json!(flow_id));
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT definition FROM _flow WHERE id = :id AND hub_id = :hub_id",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["definition"].as_str())
        .and_then(|raw| serde_json::from_str(raw).ok())
        .unwrap_or(Json::Null))
}

// ── keeping secrets out of the history (ADR-0283 §4) ──────────────────────────────────────────

/// What a redacted field shows instead of its value. Not removal: an operator looking at a `401`
/// has to see that the header **was** sent, and a missing key looks like a bug in the flow.
pub const REDACTED: &str = "«secret»";

/// Blanks every field of a step whose **definition** templates a `{{secret.…}}`.
///
/// The first line of defence is that a resolved secret is never persisted at all (flows.md §4: they
/// are resolved when the `PendingIo` is built and never written to `_flow_run_steps`). This is the
/// second: the read door does not depend on the write door having been careful. Both step kinds
/// that can carry something private are written now — `http` (hub#662) and `notify` (hub#821) — and
/// "we will remember" was never a control anyway.
///
/// The rule is by **key name**, learnt from the step's own definition and applied at any depth: a
/// key that holds a secret in the document holds one in the row. Two keys sharing a name inside one
/// step redact both, which is the direction to be wrong in.
///
/// ⚠️ **What this canNOT cover, and whoever writes the I/O steps has to**: `error` is free-form
/// prose, so a message that interpolated a credential (`request to https://x?key=sk-live failed`)
/// is not something a key-name rule can find — catching it would need the secret's VALUE, which
/// this layer deliberately does not have. The rule stands for both of them: a step never writes a
/// resolved secret ANYWHERE, its own error message included — and, since hub#821, a resolved
/// RECIPIENT is treated the same way, because a customer's phone number is not the hub's to leave
/// lying in a run's history.
fn redact_step(definition: &Json, mut step: FlowRunStep) -> FlowRunStep {
    let secret_keys = secret_keys_of(definition, &step.step_id);
    if secret_keys.is_empty() {
        return step;
    }
    blank(&mut step.input, &secret_keys);
    blank(&mut step.output, &secret_keys);
    step
}

/// The key names that hold a secret in the definition of step `step_id`.
///
/// It walks the RAW document rather than the parsed [`FlowDefinition`], on purpose: a parsed step
/// of a kind this binary cannot execute yet keeps none of its fields (`StepSpec::Reserved`), and
/// those are exactly the steps that will carry the credentials.
fn secret_keys_of(definition: &Json, step_id: &str) -> Vec<String> {
    let Some(step) = definition
        .get("steps")
        .and_then(|s| s.as_array())
        .and_then(|steps| {
            steps
                .iter()
                .find(|s| s.get("id").and_then(|v| v.as_str()) == Some(step_id))
        })
    else {
        return Vec::new();
    };
    let mut keys = Vec::new();
    collect_secret_keys(step, &mut keys);
    keys
}

fn collect_secret_keys(value: &Json, out: &mut Vec<String>) {
    match value {
        Json::Object(map) => {
            for (key, child) in map {
                if mentions_secret(child) && !out.contains(key) {
                    out.push(key.clone());
                }
                collect_secret_keys(child, out);
            }
        }
        Json::Array(items) => items.iter().for_each(|v| collect_secret_keys(v, out)),
        _ => {}
    }
}

/// Does this expression read a secret, directly (`secret.API_KEY`) or through a template
/// (`"Bearer {{secret.API_KEY}}"`)? Both forms are the mapping language of flows.md §1.
fn mentions_secret(value: &Json) -> bool {
    match value {
        Json::String(s) => s.starts_with("secret.") || s.contains("{{secret."),
        _ => false,
    }
}

fn blank(value: &mut Json, keys: &[String]) {
    match value {
        Json::Object(map) => {
            for (key, child) in map.iter_mut() {
                if keys.contains(key) {
                    *child = json!(REDACTED);
                } else {
                    blank(child, keys);
                }
            }
        }
        Json::Array(items) => items.iter_mut().for_each(|v| blank(v, keys)),
        _ => {}
    }
}

fn run_row(row: &Json) -> FlowRun {
    let text = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    let opt = |k: &str| row[k].as_str().map(|s| s.to_string());
    FlowRun {
        id: text("id"),
        flow_id: text("flow_id"),
        trigger_kind: text("trigger_kind"),
        parent_event_id: text("parent_event_id"),
        status: text("status"),
        current_step: row["current_step"].as_i64().unwrap_or(0),
        input: serde_json::from_str(&text("input")).unwrap_or(Json::Null),
        depth: row["depth"].as_i64().unwrap_or(0),
        attempts: row["attempts"].as_i64().unwrap_or(0),
        last_error: text("last_error"),
        wake_at: opt("wake_at"),
        started_at: opt("started_at"),
        finished_at: opt("finished_at"),
        created_at: text("created_at"),
    }
}

fn step_row(row: &Json) -> FlowRunStep {
    let text = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    let opt = |k: &str| row[k].as_str().map(|s| s.to_string());
    FlowRunStep {
        step_index: row["step_index"].as_i64().unwrap_or(0),
        step_id: text("step_id"),
        kind: text("kind"),
        status: text("status"),
        input: serde_json::from_str(&text("input")).unwrap_or(Json::Null),
        output: serde_json::from_str(&text("output")).unwrap_or(Json::Null),
        error: text("error"),
        started_at: opt("started_at"),
        finished_at: opt("finished_at"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::test_support;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-store";

    fn definition(cron: &str) -> Json {
        json!({
            "schema_version": 1,
            "triggers": [
                { "kind": "event", "event": "sale.completed" },
                { "kind": "cron", "cron": cron }
            ],
            "steps": [{ "id": "wait", "kind": "delay", "seconds": 5 }]
        })
    }

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db
    }

    /// The catalogue a save is judged against (hub#824): one public command and the two spellings
    /// of «internal» — the legacy `_` on the last segment and the explicit `internal: true`.
    fn registry() -> crate::registry::Registry {
        let mut reg = crate::registry::Registry::new();
        reg.status
            .insert("sales".into(), crate::registry::ModuleStatus::Active);
        reg.commands.insert(
            "sales.sale.create".into(),
            test_support::command("sales", "sales.add_sale", "SELECT 1;", vec![]),
        );
        reg.commands.insert(
            "sales._insert_sale".into(),
            test_support::command("sales", "sales.add_sale", "SELECT 1;", vec![]),
        );
        let mut flagged = test_support::command("sales", "sales.add_sale", "SELECT 1;", vec![]);
        flagged.def.internal = true;
        reg.commands.insert("sales.reindex".into(), flagged);
        reg
    }

    /// When the cron trigger of `flow_id` is next due, straight from the table.
    async fn cron_next_run(db: &dyn DatabaseAdapter, flow_id: &str) -> String {
        let mut p = Params::new();
        p.insert("f".into(), json!(flow_id));
        db.query(
            "SELECT next_run FROM _flow_triggers WHERE flow_id = :f AND kind = 'cron' \
             AND deleted_at IS NULL",
            &p,
        )
        .await
        .unwrap()
        .rows[0]["next_run"]
            .as_str()
            .unwrap()
            .to_string()
    }

    #[tokio::test]
    async fn creating_a_flow_materialises_its_triggers() {
        let db = db().await;
        let flow = create(
            &db,
            HUB,
            &registry(),
            &NewFlow {
                name: "Welcome".into(),
                enabled: true,
                definition: definition("0 9 * * *"),
            },
            "hub_user:1",
        )
        .await
        .unwrap();

        let rows = db
            .query(
                "SELECT kind, event_name, cron, next_run FROM _flow_triggers \
                 WHERE flow_id = :f AND deleted_at IS NULL ORDER BY kind",
                &{
                    let mut p = Params::new();
                    p.insert("f".into(), json!(flow.id));
                    p
                },
            )
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 2, "both triggers of the document are indexed");
        assert_eq!(rows[0]["kind"], json!("cron"));
        assert!(
            rows[0]["next_run"].is_string(),
            "a cron trigger is due at a computed instant, not never"
        );
        assert_eq!(rows[1]["event_name"], json!("sale.completed"));
    }

    #[tokio::test]
    async fn re_saving_a_flow_does_not_reschedule_its_cron() {
        let db = db().await;
        let flow = create(
            &db,
            HUB,
            &registry(),
            &NewFlow {
                name: "Nightly".into(),
                enabled: true,
                definition: definition("0 9 * * *"),
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        let before = cron_next_run(&db, &flow.id).await;

        // Renaming the flow is the most ordinary edit there is; it must not move the clock.
        update(
            &db,
            HUB,
            &flow.id,
            &registry(),
            &NewFlow {
                name: "Nightly (v2)".into(),
                enabled: true,
                definition: definition("0 9 * * *"),
            },
            "hub_user:1",
        )
        .await
        .unwrap();

        assert_eq!(before, cron_next_run(&db, &flow.id).await);
    }

    #[tokio::test]
    async fn a_trigger_removed_from_the_document_stops_existing() {
        let db = db().await;
        let flow = create(
            &db,
            HUB,
            &registry(),
            &NewFlow {
                name: "Two".into(),
                enabled: true,
                definition: definition("0 9 * * *"),
            },
            "hub_user:1",
        )
        .await
        .unwrap();

        update(
            &db,
            HUB,
            &flow.id,
            &registry(),
            &NewFlow {
                name: "One".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "triggers": [{ "kind": "event", "event": "sale.completed" }],
                    "steps": [{ "id": "wait", "kind": "delay", "seconds": 5 }]
                }),
            },
            "hub_user:1",
        )
        .await
        .unwrap();

        let live = db
            .query(
                "SELECT kind FROM _flow_triggers WHERE flow_id = :f AND deleted_at IS NULL",
                &{
                    let mut p = Params::new();
                    p.insert("f".into(), json!(flow.id));
                    p
                },
            )
            .await
            .unwrap()
            .rows;
        assert_eq!(live.len(), 1, "the cron the author deleted stops firing");
        assert_eq!(live[0]["kind"], json!("event"));
    }

    #[tokio::test]
    async fn deleting_a_flow_revokes_its_grants_and_disarms_its_triggers() {
        let db = db().await;
        let reg = registry();
        let flow = create(
            &db,
            HUB,
            &reg,
            &NewFlow {
                name: "Gone".into(),
                enabled: true,
                definition: definition("0 9 * * *"),
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        grants::replace(
            &db,
            HUB,
            &flow.id,
            &reg,
            &[(grants::GrantKind::Command, "sales.sale.create".into())],
            "hub_user:1",
        )
        .await
        .unwrap();

        delete(&db, HUB, &flow.id, "hub_user:1").await.unwrap();

        assert!(get(&db, HUB, &flow.id).await.is_err(), "the flow is gone");
        assert!(
            grants::list(&db, HUB, &flow.id).await.unwrap().is_empty(),
            "a permission whose owner no longer exists is not a permission"
        );
        let live = db
            .query(
                "SELECT id FROM _flow_triggers WHERE flow_id = :f AND deleted_at IS NULL",
                &{
                    let mut p = Params::new();
                    p.insert("f".into(), json!(flow.id));
                    p
                },
            )
            .await
            .unwrap()
            .rows;
        assert!(live.is_empty(), "no trigger keeps creating runs for a deleted flow");
    }

    /// **hub#771** — deleting a flow must cancel the runs it left behind that have not finished yet,
    /// in the SAME gesture as the delete. The bug this closes: a run parked on a `delay`
    /// (`sleeping`, `wake_at` in the future) survived the delete and only changed to `cancelled`
    /// days later, when the delay came due and the tick woke it to discover a flow that no longer
    /// existed. For the whole interval the run history lied — it said «waiting» about a flow whose
    /// owner had withdrawn it.
    ///
    /// The fix cancels `sleeping` and `pending` runs (the not-yet-finished ones) inside `delete`,
    /// so the row reflects reality from the moment the owner presses the button. The neighbour's
    /// sleeping run is untouched: cancellation is scoped to the deleted flow's hub AND flow id.
    #[tokio::test]
    async fn deleting_a_flow_cancels_its_sleeping_runs_in_the_same_gesture() {
        use crate::flows::executor;

        let db = db().await;
        let reg = crate::registry::Registry::new();
        // A long delay: the run parks as `sleeping` and stays there.
        let flow = create(
            &db,
            HUB,
            &registry(),
            &NewFlow {
                name: "Sleepy".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [{ "id": "wait", "kind": "delay", "seconds": 3600 }]
                }),
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        let sleeping_run = start_run(&db, HUB, &flow.id, "", "manual", "", &json!({}), 0, "hub_user:1")
            .await
            .unwrap();
        // Run the tick that parks it on the delay.
        executor::tick(&db, &reg, HUB).await.unwrap();
        let parked = get_run(&db, HUB, &sleeping_run).await.unwrap().0;
        assert_eq!(
            parked.status, STATUS_SLEEPING,
            "precondition: the run reached the delay before the delete"
        );

        // ── neighbour: a sleeping run of ANOTHER hub must survive the delete unchanged ──
        const NEIGHBOUR: &str = "hub-store-neighbour";
        test_support::ensure_schema(&db, NEIGHBOUR).await;
        let neighbour_flow = create(
            &db,
            NEIGHBOUR,
            &registry(),
            &NewFlow {
                name: "Theirs".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [{ "id": "wait", "kind": "delay", "seconds": 3600 }]
                }),
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        let neighbour_run =
            start_run(&db, NEIGHBOUR, &neighbour_flow.id, "", "manual", "", &json!({}), 0, "hub_user:1")
                .await
                .unwrap();
        executor::tick(&db, &reg, NEIGHBOUR).await.unwrap();
        assert_eq!(
            get_run(&db, NEIGHBOUR, &neighbour_run).await.unwrap().0.status,
            STATUS_SLEEPING,
            "precondition: the neighbour is also sleeping"
        );

        // The gesture under test: delete the flow. No clock advance, no second tick — the
        // cancellation has to land here, not days later when the delay comes due.
        delete(&db, HUB, &flow.id, "hub_user:1").await.unwrap();

        let cancelled = get_run(&db, HUB, &sleeping_run).await.unwrap().0;
        assert_eq!(
            cancelled.status, STATUS_CANCELLED,
            "the sleeping run is cancelled by the delete, not left lying about a flow that is gone"
        );
        assert!(
            cancelled.last_error.contains("flow_deleted"),
            "the reason is recorded for whoever reads the history later: {}",
            cancelled.last_error
        );
        assert!(
            cancelled.wake_at.is_none(),
            "a cancelled run is not also waiting to wake: {}",
            cancelled.wake_at.unwrap_or_default()
        );

        // The neighbour slept through it: a delete in one hub never reaches into another.
        let still_theirs = get_run(&db, NEIGHBOUR, &neighbour_run).await.unwrap().0;
        assert_eq!(
            still_theirs.status, STATUS_SLEEPING,
            "the neighbour's sleeping run is untouched by a delete in another hub"
        );
        assert!(still_theirs.wake_at.is_some(), "and still waiting to wake");
    }

    /// A `pending` run (queued, not yet started) is also not-yet-finished, so deleting the flow
    /// cancels it too — the same honesty, for a run that never got its first tick.
    #[tokio::test]
    async fn deleting_a_flow_cancels_its_pending_runs_too() {
        let db = db().await;
        let flow = create(
            &db,
            HUB,
            &registry(),
            &NewFlow {
                name: "Queued".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [{ "id": "wait", "kind": "delay", "seconds": 3600 }]
                }),
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        let pending_run =
            start_run(&db, HUB, &flow.id, "", "manual", "", &json!({}), 0, "hub_user:1")
                .await
                .unwrap();
        assert_eq!(
            get_run(&db, HUB, &pending_run).await.unwrap().0.status,
            STATUS_PENDING,
            "precondition: never ticked, so still queued"
        );

        delete(&db, HUB, &flow.id, "hub_user:1").await.unwrap();

        let cancelled = get_run(&db, HUB, &pending_run).await.unwrap().0;
        assert_eq!(
            cancelled.status, STATUS_CANCELLED,
            "a pending run is cancelled with its flow, not stranded in a queue for a ghost"
        );
        assert!(cancelled.last_error.contains("flow_deleted"));
    }

    /// Finished runs are HISTORY — the delete must not rewrite them. A `done` run stays `done`,
    /// a `failed` run stays `failed`, and a run already `cancelled` keeps its original reason.
    #[tokio::test]
    async fn deleting_a_flow_leaves_its_finished_runs_as_history() {
        let db = db().await;
        let flow = create(
            &db,
            HUB,
            &registry(),
            &NewFlow {
                name: "Done".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [{ "id": "wait", "kind": "delay", "seconds": 3600 }]
                }),
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        let done_run =
            start_run(&db, HUB, &flow.id, "", "manual", "", &json!({}), 0, "hub_user:1")
                .await
                .unwrap();
        // Mark it finished by hand — the run row is what the delete sees, not how it got there.
        let mut p = Params::new();
        p.insert("id".into(), json!(done_run));
        p.insert("now".into(), json!(now_rfc3339()));
        db.execute(
            "UPDATE _flow_runs SET status = 'done', last_error = 'ran fine', finished_at = :now \
             WHERE id = :id",
            &p,
        )
        .await
        .unwrap();

        delete(&db, HUB, &flow.id, "hub_user:1").await.unwrap();

        let still_done = get_run(&db, HUB, &done_run).await.unwrap().0;
        assert_eq!(still_done.status, STATUS_DONE, "history is not rewritten");
        assert_eq!(
            still_done.last_error, "ran fine",
            "and neither is the reason it ended the way it did"
        );
    }

    #[tokio::test]
    async fn a_flow_of_another_hub_is_not_visible_here() {
        let db = db().await;
        test_support::ensure_schema(&db, "hub-other").await;
        let flow = create(
            &db,
            "hub-other",
            &registry(),
            &NewFlow {
                name: "Theirs".into(),
                enabled: true,
                definition: definition("0 9 * * *"),
            },
            "hub_user:1",
        )
        .await
        .unwrap();

        assert!(get(&db, HUB, &flow.id).await.is_err());
        assert!(list(&db, HUB).await.unwrap().is_empty());
    }

    // ── run history (hub#666) ─────────────────────────────────────────────────────────────────

    /// The trace query has an index, and that index is the reason it is allowed to exist.
    ///
    /// `runs_of_event` reads `parent_event_id`, which v34 does not index — it indexes what the tick
    /// and the history read. A hub with live flows makes runs at the rate of its till, so an
    /// unindexed lookup on that column is a sequential scan of a table that only ever grows.
    #[tokio::test]
    async fn the_lookup_by_originating_event_is_indexed_and_arming_it_twice_is_a_no_op() {
        let db = db().await;
        // The boot path arms it once; a second runtime of the same hub (start-first deploys, two
        // processes against one database) arms it again, and it must not care.
        ensure_indexes(&db).await.unwrap();

        let rows = db
            .query(
                // Scoped to THIS test's ephemeral schema: every parallel test has its own
                // `_flow_runs`, and an unscoped `pg_indexes` counts the whole container.
                "SELECT indexdef FROM pg_indexes WHERE tablename = '_flow_runs' \
                 AND indexname = 'ix_flow_run_parent' AND schemaname = current_schema()",
                &Params::new(),
            )
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 1, "nothing indexes the trace query");
        let def = rows[0]["indexdef"].as_str().unwrap();
        assert!(def.contains("parent_event_id"), "{def}");
        assert!(
            def.contains("WHERE"),
            "partial on purpose: most runs (manual, cron) have no originating event, and indexing \
             their empty string is paying for rows nobody ever looks up — {def}"
        );
    }

    /// Starts `n` runs of `flow_id` and returns their ids, oldest first.
    async fn many_runs(db: &dyn DatabaseAdapter, flow_id: &str, n: usize) -> Vec<String> {
        let mut ids = Vec::new();
        for _ in 0..n {
            ids.push(
                start_run(db, HUB, flow_id, "", "manual", "", &json!({}), 0, "hub_user:1")
                    .await
                    .unwrap(),
            );
        }
        ids
    }

    /// A hub with live flows makes runs forever, so the history is paged — and a page that can
    /// repeat or skip a row is worse than no history: the operator counting «this sale fired five
    /// steps» would count four, or six.
    ///
    /// The cursor is `(created_at, id)` and not an offset, because rows keep arriving at the head
    /// while somebody is reading: with `OFFSET` every new run shifts the page under them.
    #[tokio::test]
    async fn the_history_pages_backwards_without_repeating_or_skipping_a_run() {
        let db = db().await;
        let flow = create(
            &db,
            HUB,
            &registry(),
            &NewFlow {
                name: "Busy".into(),
                enabled: true,
                definition: definition("0 9 * * *"),
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        let started = many_runs(&db, &flow.id, 5).await;

        let mut seen: Vec<String> = Vec::new();
        let mut before: Option<String> = None;
        for _ in 0..4 {
            let page = list_runs(&db, HUB, &flow.id, 2, before.as_deref()).await.unwrap();
            if page.is_empty() {
                break;
            }
            before = Some(page.last().unwrap().id.clone());
            seen.extend(page.into_iter().map(|r| r.id));
        }

        assert_eq!(seen.len(), 5, "every run appeared exactly once across the pages");
        let mut unique = seen.clone();
        unique.sort();
        unique.dedup();
        assert_eq!(unique.len(), 5, "no run was served twice: {seen:?}");
        assert_eq!(
            seen[0],
            *started.last().unwrap(),
            "newest first: the run somebody is looking for is the one that just failed"
        );
    }

    /// The history is scoped to its hub in BOTH doors — the list and the detail. The detail is the
    /// one that matters most: it carries the resolved inputs of every step, which is the whole
    /// business of another tenant if the `hub_id` is ever dropped from the `WHERE`.
    #[tokio::test]
    async fn a_run_of_another_hub_is_not_visible_here() {
        let db = db().await;
        test_support::ensure_schema(&db, "hub-other").await;
        let theirs = create(
            &db,
            "hub-other",
            &registry(),
            &NewFlow {
                name: "Theirs".into(),
                enabled: true,
                definition: definition("0 9 * * *"),
            },
            "hub_user:1",
        )
        .await
        .unwrap();
        let their_run = start_run(
            &db,
            "hub-other",
            &theirs.id,
            "",
            "manual",
            "",
            &json!({ "customer_email": "someone@example.com" }),
            0,
            "hub_user:1",
        )
        .await
        .unwrap();

        assert!(
            get_run(&db, HUB, &their_run).await.is_err(),
            "the detail of another tenant's run is not a 404 by luck: it must not be readable"
        );
        assert!(list_runs(&db, HUB, &theirs.id, 50, None).await.unwrap().is_empty());
    }

    /// **The history never shows a secret** (ADR-0283 §4).
    ///
    /// The first defence is that a templated `{{secret.X}}` is never persisted into
    /// `_flow_run_steps` — but that defence lives in the step that resolves it, and this endpoint
    /// is a **second door** onto the same rows. A door that trusts the other one is a door that
    /// leaks the day somebody adds a step kind and forgets.
    ///
    /// The flow row is seeded directly here on purpose: `FlowDefinition::parse` refuses `secret.…`
    /// while `_flow_secrets` does not exist (hub#662), so the shape being defended against cannot
    /// be created through the front door yet. It is coming, and the door is shut before it arrives.
    ///
    /// Returns `(flow_id, run_id)` — an `http` step whose `Authorization` header is templated from
    /// a secret, plus the step row a resolved call would have left behind, credential and all.
    async fn flow_with_a_secret_step(db: &dyn DatabaseAdapter) -> (String, String) {
        let flow_id = "flow-http";
        let definition = json!({
            "schema_version": 1,
            "triggers": [],
            "steps": [{
                "id": "call",
                "kind": "http",
                "url": "https://api.example.com/send",
                "headers": { "Authorization": "Bearer {{secret.API_KEY}}", "X-Trace": "abc" },
                "params": { "note": "{{input.note}}" }
            }]
        });
        let mut p = Params::new();
        p.insert("id".into(), json!(flow_id));
        p.insert("hub".into(), json!(HUB));
        p.insert("def".into(), json!(definition.to_string()));
        p.insert("now".into(), json!(now_rfc3339()));
        db.execute(
            "INSERT INTO _flow (id, hub_id, name, enabled, schema_version, definition, \
                                created_at, created_by, updated_at, updated_by) \
             VALUES (:id, :hub, 'Webhook', 1, 1, :def, :now, 'seed', :now, 'seed')",
            &p,
        )
        .await
        .unwrap();
        let run_id = start_run(db, HUB, flow_id, "", "manual", "", &json!({}), 0, "hub_user:1")
            .await
            .unwrap();

        // What a resolved http step would have written: the header, templated, in the clear.
        let mut s = Params::new();
        s.insert("id".into(), json!("step-1"));
        s.insert("hub".into(), json!(HUB));
        s.insert("run".into(), json!(run_id));
        s.insert(
            "input".into(),
            json!(json!({
                "url": "https://api.example.com/send",
                "headers": { "Authorization": "Bearer sk-live-31337", "X-Trace": "abc" }
            })
            .to_string()),
        );
        s.insert("now".into(), json!(now_rfc3339()));
        db.execute(
            "INSERT INTO _flow_run_steps (id, hub_id, run_id, step_index, step_id, kind, status, \
                                          input, output, error, created_at) \
             VALUES (:id, :hub, :run, 0, 'call', 'http', 'done', :input, '{}', '', :now)",
            &s,
        )
        .await
        .unwrap();
        (flow_id.to_string(), run_id)
    }

    #[tokio::test]
    async fn a_step_whose_definition_names_a_secret_never_shows_its_value() {
        let db = db().await;
        let (_, run_id) = flow_with_a_secret_step(&db).await;

        let (_, steps) = get_run(&db, HUB, &run_id).await.unwrap();
        let shown = serde_json::to_string(&steps[0].input).unwrap();
        assert!(
            !shown.contains("sk-live-31337"),
            "the history handed out a live credential: {shown}"
        );
        assert_eq!(
            steps[0].input["headers"]["Authorization"],
            json!(REDACTED),
            "the field is shown as redacted rather than removed: an operator debugging a 401 has \
             to see that the header WAS sent"
        );
        assert_eq!(
            steps[0].input["headers"]["X-Trace"],
            json!("abc"),
            "only what the definition marks as a secret is hidden; the rest is why this screen exists"
        );
        assert_eq!(steps[0].input["url"], json!("https://api.example.com/send"));
    }

    /// **Deleting the flow must not un-redact its history.** `delete` is a SOFT delete, and the
    /// runs survive it — so if the redaction read the definition through the ordinary `get` (which
    /// filters `deleted_at IS NULL`), the way to see every secret a flow ever sent would be to
    /// press «delete» and then open its history. That is the opposite of what deleting means.
    #[tokio::test]
    async fn deleting_the_flow_does_not_turn_its_history_into_a_way_to_read_its_secrets() {
        let db = db().await;
        let (flow_id, run_id) = flow_with_a_secret_step(&db).await;

        // Soft-delete the flow, exactly as `delete()` does.
        let mut p = Params::new();
        p.insert("id".into(), json!(flow_id));
        p.insert("now".into(), json!(now_rfc3339()));
        db.execute(
            "UPDATE _flow SET deleted_at = :now, deleted_by = 'hub_user:1' WHERE id = :id",
            &p,
        )
        .await
        .unwrap();

        let (_, steps) = get_run(&db, HUB, &run_id).await.unwrap();
        let shown = serde_json::to_string(&steps[0].input).unwrap();
        assert!(
            !shown.contains("sk-live-31337"),
            "pressing delete handed out the credential: {shown}"
        );
        assert_eq!(steps[0].input["headers"]["Authorization"], json!(REDACTED));
    }

    /// **hub#824, the other half of the same hole.** The grants screen is not the only place that
    /// names a command: a `command` step does, and so does the tool list of an `ai` step. A document
    /// that names an INTERNAL one is a flow the hub can never execute — `execute_at` refuses
    /// internals to `Origin::Automation` exactly as it does to `External` (flows.md §2) — so it is
    /// refused AT SAVE, which is what §13.2 already demands of everything else the hub cannot run.
    #[tokio::test]
    async fn a_document_that_names_an_internal_command_is_refused_at_save() {
        let db = db().await;
        let reg = registry();
        let code_of = |err: &RuntimeError| match err {
            RuntimeError::Domain { code, .. } => code.clone(),
            other => panic!("expected a domain refusal, got {other}"),
        };

        for (what, definition) in [
            (
                "a `command` step",
                json!({
                    "schema_version": 1,
                    "triggers": [{ "kind": "manual" }],
                    "steps": [{ "id": "i", "kind": "command", "command": "sales._insert_sale",
                                "params": {} }]
                }),
            ),
            (
                "the tool list of an `ai` step",
                json!({
                    "schema_version": 1,
                    "triggers": [{ "kind": "manual" }],
                    "steps": [{ "id": "think", "kind": "ai", "prompt": "do it",
                                "tools": { "commands": ["sales.reindex"] } }]
                }),
            ),
        ] {
            let err = match create(
                &db,
                HUB,
                &reg,
                &NewFlow {
                    name: "QA internal".into(),
                    enabled: true,
                    definition,
                },
                "hub_user:1",
            )
            .await
            {
                Err(e) => e,
                Ok(_) => panic!("{what} naming an internal command must not be stored"),
            };
            assert_eq!(
                code_of(&err),
                crate::flows::grants::ERR_INTERNAL_COMMAND,
                "{what}: {err}"
            );
        }
        assert!(
            list(&db, HUB).await.unwrap().is_empty(),
            "nothing was stored, so nothing waits to fail at 3 AM"
        );

        // The same shape with a PUBLIC command saves, which is the half that must not regress…
        let saved = create(
            &db,
            HUB,
            &reg,
            &NewFlow {
                name: "QA public".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "triggers": [{ "kind": "manual" }],
                    "steps": [{ "id": "i", "kind": "command", "command": "sales.sale.create",
                                "params": {} }]
                }),
            },
            "hub_user:1",
        )
        .await
        .unwrap();

        // …and the door is the same one on the way back in: an EDIT cannot smuggle it either.
        let err = update(
            &db,
            HUB,
            &saved.id,
            &reg,
            &NewFlow {
                name: "QA public".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "triggers": [{ "kind": "manual" }],
                    "steps": [{ "id": "i", "kind": "command", "command": "sales._insert_sale",
                                "params": {} }]
                }),
            },
            "hub_user:1",
        )
        .await
        .expect_err("editing is the same door as creating");
        assert_eq!(code_of(&err), crate::flows::grants::ERR_INTERNAL_COMMAND);
        assert_eq!(
            get(&db, HUB, &saved.id).await.unwrap().definition["steps"][0]["command"],
            json!("sales.sale.create"),
            "a refused edit leaves the stored document untouched"
        );
    }

    /// A document may legitimately name a command that is not installed **yet** — a blueprint lands
    /// its flows and its modules in whatever order, and refusing here would make importing one a
    /// question of luck. The unknown name is caught where it costs nothing to be strict: the GRANT,
    /// which is what actually opens the door.
    #[tokio::test]
    async fn a_document_may_name_a_command_this_hub_has_not_installed_yet() {
        let db = db().await;
        create(
            &db,
            HUB,
            &registry(),
            &NewFlow {
                name: "Not yet".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "triggers": [{ "kind": "manual" }],
                    "steps": [{ "id": "i", "kind": "command", "command": "loyalty.points.add",
                                "params": {} }]
                }),
            },
            "hub_user:1",
        )
        .await
        .expect("a module that is not installed yet is not a broken document");
    }

    #[tokio::test]
    async fn a_definition_that_does_not_parse_is_never_stored() {
        let db = db().await;
        let err = create(
            &db,
            HUB,
            &registry(),
            &NewFlow {
                name: "Broken".into(),
                enabled: true,
                definition: json!({ "schema_version": 9, "steps": [] }),
            },
            "hub_user:1",
        )
        .await
        .expect_err("a stored document that does not parse fails at 3 AM instead of at the screen");
        assert!(format!("{err}").contains("schema_version"), "{err}");
        assert!(list(&db, HUB).await.unwrap().is_empty());
    }
}
