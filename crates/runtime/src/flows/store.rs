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
use crate::flows::def::{FlowDefinition, TriggerDef, TriggerKind};
use crate::flows::grants;
use crate::registry::{new_id, now_rfc3339};
use crate::scheduler::cron;

pub const ERR_FLOW_NOT_FOUND: &str = "flow.not_found";

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

/// Run statuses. `sleeping` is a `delay` waiting on `wake_at`; `waiting_io` is the state an I/O
/// step will park in once hub#662 lands (claim → I/O → complete) and nothing produces it today.
pub const STATUS_PENDING: &str = "pending";
pub const STATUS_RUNNING: &str = "running";
pub const STATUS_SLEEPING: &str = "sleeping";
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

pub async fn create(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    new: &NewFlow,
    by: &str,
) -> Result<Flow> {
    // Parse BEFORE writing: a stored document that does not parse is a flow that fails at 3 AM
    // instead of at the screen where it was written.
    let def = FlowDefinition::parse(&new.definition)?;
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
    new: &NewFlow,
    by: &str,
) -> Result<Flow> {
    let def = FlowDefinition::parse(&new.definition)?;
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

/// Soft-deletes a flow, disarms its triggers and **revokes its grants**. The three go together:
/// leaving a live grant behind would be an authorisation whose owner no longer exists, and a live
/// trigger would keep creating runs for a flow the owner believes is gone.
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
    let mut keys: Vec<String> = Vec::new();

    for trigger in &def.triggers {
        let key = trigger_key(trigger);
        keys.push(key.clone());

        // Only the clock kinds carry a `next_run`. `at` is one-shot: its instant IS its due date,
        // and firing disables it.
        let next_run = match trigger.kind {
            TriggerKind::Cron => cron::next_after(&trigger.cron, &now),
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
        p.insert("now".into(), json!(now));
        // The upsert deliberately does NOT touch `next_run`: re-saving a flow must not reschedule
        // a nightly job to now (`seed_module_tasks`, hub#570).
        db.execute(
            "INSERT INTO _flow_triggers \
               (id, hub_id, flow_id, trigger_key, kind, event_name, filter, input_map, cron, \
                run_at, enabled, next_run, created_at, updated_at) \
             VALUES (:id, :hub_id, :flow_id, :key, :kind, :event_name, :filter, :input_map, :cron, \
                     :run_at, :enabled, :next_run, :now, :now) \
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
        p.insert("now".into(), json!(now));
        db.execute(
            "UPDATE _flow_triggers SET deleted_at = :now, enabled = 0, updated_at = :now \
             WHERE id = :id",
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

pub async fn list_runs(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    limit: i64,
) -> Result<Vec<FlowRun>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("limit".into(), json!(limit.clamp(1, 200)));
    let res = db
        .query(
            "SELECT id, flow_id, trigger_kind, parent_event_id, status, current_step, input, \
                    depth, attempts, last_error, wake_at, started_at, finished_at, created_at \
             FROM _flow_runs \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL \
             ORDER BY created_at DESC, id DESC LIMIT :limit",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(run_row).collect())
}

/// One run with its steps — the shape `GET /api/hub/flows/runs/{run_id}` returns.
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
    Ok((run, steps.rows.iter().map(step_row).collect()))
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
        let mut registry = crate::registry::Registry::new();
        registry.status.insert("sales".into(), crate::registry::ModuleStatus::Active);
        registry.commands.insert(
            "sales.sale.create".into(),
            test_support::command("sales", "sales.add_sale", "SELECT 1;", vec![]),
        );
        let flow = create(
            &db,
            HUB,
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
            &registry,
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

    #[tokio::test]
    async fn a_flow_of_another_hub_is_not_visible_here() {
        let db = db().await;
        test_support::ensure_schema(&db, "hub-other").await;
        let flow = create(
            &db,
            "hub-other",
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

    #[tokio::test]
    async fn a_definition_that_does_not_parse_is_never_stored() {
        let db = db().await;
        let err = create(
            &db,
            HUB,
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
