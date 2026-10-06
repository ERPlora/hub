//! Erasure: when a person's data is erased, the hub's own history forgets them too (hub#2467).
//!
//! `customers.anonymize` is the platform's GDPR erasure (art. 17). It rewrites the customer's sheet
//! and publishes `customer.anonymized`, and every module that keeps personal data reacts to it in
//! its own tables. What no module can reach is the KERNEL's history (ADR-0127): `_event_outbox`
//! keeps every event verbatim, and `_flow_runs` / `_flow_run_steps` / `_flow_approvals` keep what
//! each automation received and produced. Until hub#2467 those copies — her name, her phone, what
//! she wrote — stayed there until `retention` pruned them, ninety days later.
//!
//! # The rule
//!
//! When the relay delivers an event named `<subject>.anonymized` carrying `<subject>_id`, the
//! runtime EMPTIES (`'{}'`) — in that hub, in one statement — every TERMINAL history row that names
//! that id, and everything an automation derived from it:
//!
//! - **events** (`delivered`/`discarded`) whose payload holds the id as a JSON string value;
//! - **runs** (`done`/`failed`/`cancelled`) that touched her: the id in their input, vars, a step
//!   or a proposal, or triggered by one of those events — `input` and `vars` emptied;
//! - **all the steps and proposals** of those runs, whose outputs carry what was looked up about
//!   her (a phone) without necessarily repeating her id;
//! - **the events those runs queued** (`run_id`), for the same reason: a reminder carries the phone.
//!
//! # The lines this draws
//!
//! - **Empty, never delete.** The row is the trace (`/api/hub/events/{id}/trace`, the run history
//!   behind a sale); what identifies the person is the payload. `retention` still deletes the row
//!   on its own clock.
//! - **Terminal only, the same line `retention` draws.** A `pending` event is not delivered yet; a
//!   `dead` one waits for a human and may be the sale whose invoice still has to reach the AEAT;
//!   a live run needs its memory to finish. Emptying any of them is data loss, not erasure.
//! - **By id, not by guesswork.** The event brings the id and nothing else; the sheet it names is
//!   already pseudonymised when this runs. A copy that holds her number but neither her id nor a
//!   link to a run that touched her (a raw inbound WhatsApp message, before any sheet is linked) is
//!   NOT reachable from here: that needs the module to say what identified her (hub#2477).
//! - **The kernel does not know the customers module.** The trigger is the naming convention
//!   (`<subject>.anonymized` + `<subject>_id`), the same kind of contract as `.reminder.due` and
//!   `.print.due`. Today only `customer.anonymized` follows it.
//! - **Only the owner erases (hub#2485).** The id must have the shape the hub generates (a
//!   canonical uuid) and be a row of one of the EMITTER's tables in this hub. Anything else is
//!   refused with a code (`erasure.invalid_subject_id`, `erasure.subject_not_owned`): the event is
//!   not delivered, retries and ends in the dead letters, where a human sees it.
//!
//! **Cost.** There is no index on payload content: one erasure reads the hub's terminal history
//! once (at most ninety days of it, thanks to `retention`). Erasures are rare, manual and
//! idempotent — an already-emptied row no longer contains the id, so a redelivery finds nothing.

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::registry::Registry;

/// The suffix of the events that erase their subject from the kernel's history.
pub const ANONYMIZED_SUFFIX: &str = ".anonymized";

/// What one erasure emptied, per table. Returned rather than logged, like `retention::PruneReport`.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct ErasureReport {
    /// `_event_outbox` payloads emptied.
    pub events: u64,
    /// `_flow_runs` whose `input`/`vars` were emptied.
    pub runs: u64,
    /// `_flow_run_steps` whose `input`/`output` were emptied.
    pub run_steps: u64,
    /// `_flow_approvals` payloads emptied.
    pub approvals: u64,
}

impl ErasureReport {
    /// Every row this erasure emptied.
    pub fn total(&self) -> u64 {
        self.events + self.runs + self.run_steps + self.approvals
    }
}

/// The id an erasure event names, or `None` when `event_name` is not an erasure or the id is not a
/// usable string. An empty id is refused on purpose: as a needle, `""` is in nearly every payload.
pub fn subject_id(event_name: &str, payload: &Params) -> Option<String> {
    let subject = event_name.strip_suffix(ANONYMIZED_SUFFIX)?;
    let subject = subject.rsplit('.').next().filter(|s| !s.is_empty())?;
    match payload.get(&format!("{subject}_id")) {
        Some(Json::String(id)) if !id.is_empty() => Some(id.clone()),
        _ => None,
    }
}

/// Whether `id` has the shape of the ids the hub hands out: the canonical hyphenated uuid of
/// `registry::new_id` (36 characters). Anything else — a word, a number, the braced or compact
/// spellings `uuid` would also parse — is refused as a needle: `"id"` is a KEY of nearly every
/// payload, so naming it would empty the whole history (hub#2485).
pub(crate) fn is_generated_id(id: &str) -> bool {
    id.len() == 36 && uuid::Uuid::try_parse(id).is_ok()
}

/// A refused erasure, with its stable code first in the message so the dead-letter row says it.
fn refused(code: &str, detail: String) -> RuntimeError {
    RuntimeError::Domain {
        code: code.to_string(),
        message: format!("{code}: {detail}"),
    }
}

/// The tables of this hub's database that carry both `id` and `hub_id`: the row contract every
/// module table follows, and the only ones an owner check can ask.
const ROW_TABLES: &str = "\
SELECT table_name AS name FROM information_schema.columns \
 WHERE table_schema = current_schema() AND column_name IN ('id', 'hub_id') \
 GROUP BY table_name HAVING COUNT(*) = 2";

/// **The owner gate (hub#2485).** An app may only erase a subject that is its own data: `id` must
/// be a row of one of the EMITTER's tables, in THIS hub. Ownership is the longest installed prefix
/// (`export::table_owner`, the rule export and reset use), so the kernel (no emitter), an app that
/// is not installed and an app naming another app's row are all refused — the same way
/// `.reminder.due` and `.print.due` only open their host door to the app that declared it.
async fn authorize(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    emitter: &str,
    id: &str,
) -> Result<()> {
    if !is_generated_id(id) {
        return Err(refused(
            "erasure.invalid_subject_id",
            format!("`{emitter}` named `{id}`, which is not an id the hub generates"),
        ));
    }
    let installed: Vec<String> = registry.installed.iter().map(|m| m.id.clone()).collect();
    let tables = db.query(ROW_TABLES, &Params::new()).await?;
    let own = tables
        .rows
        .iter()
        .filter_map(|r| r["name"].as_str())
        .filter(|t| crate::export::safe_ident(t))
        // No installed id is empty, so the kernel (`emitter == ""`) owns no table.
        .filter(|t| crate::export::table_owner(t, &installed).as_deref() == Some(emitter));
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(id));
    for table in own {
        let hit = db
            .query(
                &format!(
                    "SELECT 1 AS hit FROM \"{table}\" \
                     WHERE hub_id = :hub_id AND CAST(id AS TEXT) = :id LIMIT 1"
                ),
                &p,
            )
            .await?;
        if !hit.rows.is_empty() {
            return Ok(());
        }
    }
    Err(refused(
        "erasure.subject_not_owned",
        format!("`{id}` is not a row of `{emitter}` in this hub, so `{emitter}` cannot erase it"),
    ))
}

/// Everything named in the module header, in ONE statement so the erasure is atomic and every
/// sub-statement sees the same snapshot (each table is written exactly once).
///
/// `hit` is every event that names her, live or not: a run is history even when the event that
/// triggered it is still `dead`. Whether an EVENT may be emptied is decided once, at its write.
///
/// `:needle` is the id JSON-encoded (`"<id>"`, quotes included), so it matches the id as a string
/// VALUE and never as a fragment of a longer one. `hub_id` filters every read and every write:
/// the same id in another hub belongs to another hub. The `<> '{}'` guards make the counts say
/// what was actually emptied, so a redelivery reports zero.
const ERASE: &str = "\
WITH hit AS (\
  SELECT id FROM _event_outbox \
   WHERE hub_id = :hub_id AND strpos(payload, :needle) > 0\
), touched AS (\
  SELECT r.id FROM _flow_runs r \
   WHERE r.hub_id = :hub_id AND r.status IN ('done', 'failed', 'cancelled') \
     AND (strpos(r.input, :needle) > 0 OR strpos(r.vars, :needle) > 0 \
          OR r.parent_event_id IN (SELECT id FROM hit) \
          OR EXISTS (SELECT 1 FROM _flow_run_steps s \
                      WHERE s.hub_id = :hub_id AND s.run_id = r.id \
                        AND (strpos(s.input, :needle) > 0 OR strpos(s.output, :needle) > 0)) \
          OR EXISTS (SELECT 1 FROM _flow_approvals a \
                      WHERE a.hub_id = :hub_id AND a.run_id = r.id \
                        AND strpos(a.payload, :needle) > 0))\
), events AS (\
  UPDATE _event_outbox SET payload = '{}' \
   WHERE hub_id = :hub_id AND status IN ('delivered', 'discarded') AND payload <> '{}' \
     AND (id IN (SELECT id FROM hit) OR (run_id <> '' AND run_id IN (SELECT id FROM touched))) \
  RETURNING id\
), runs AS (\
  UPDATE _flow_runs SET input = '{}', vars = '{}' \
   WHERE hub_id = :hub_id AND id IN (SELECT id FROM touched) \
     AND (input <> '{}' OR vars <> '{}') \
  RETURNING id\
), steps AS (\
  UPDATE _flow_run_steps SET input = '{}', output = '{}' \
   WHERE hub_id = :hub_id AND run_id IN (SELECT id FROM touched) \
     AND (input <> '{}' OR output <> '{}') \
  RETURNING id\
), approvals AS (\
  UPDATE _flow_approvals SET payload = '{}' \
   WHERE hub_id = :hub_id AND run_id IN (SELECT id FROM touched) AND payload <> '{}' \
  RETURNING id\
) SELECT (SELECT COUNT(*) FROM events) AS events, (SELECT COUNT(*) FROM runs) AS runs, \
         (SELECT COUNT(*) FROM steps) AS steps, (SELECT COUNT(*) FROM approvals) AS approvals";

/// The relay's hook: if `event_name` is an erasure, empty this hub's history of its subject.
/// Anything else is a no-op that touches the database not at all.
pub async fn on_event(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    emitter: &str,
    event_name: &str,
    payload: &Params,
) -> Result<ErasureReport> {
    let Some(id) = subject_id(event_name, payload) else {
        return Ok(ErasureReport::default());
    };
    authorize(db, registry, hub_id, emitter, &id).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("needle".into(), json!(Json::String(id).to_string()));
    let res = db.query(ERASE, &p).await?;
    Ok(ErasureReport {
        events: cell(&res, "events"),
        runs: cell(&res, "runs"),
        run_steps: cell(&res, "steps"),
        approvals: cell(&res, "approvals"),
    })
}

/// `COUNT(*)` comes back as an integer, but the JSON bridge can widen it to a float.
fn cell(res: &erplora_db::QueryResult, key: &str) -> u64 {
    res.rows
        .first()
        .and_then(|r| {
            r[key]
                .as_i64()
                .or_else(|| r[key].as_f64().map(|f| f as i64))
        })
        .unwrap_or(0)
        .max(0) as u64
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::fresh_db;
    use erplora_db::PgAdapter;

    const HUB: &str = "h1";
    const OTHER_HUB: &str = "h2";
    const ANA: &str = "6f1c2a7e-0d4b-4f53-9a3e-6c1d2b7e8f90";
    const BEA: &str = "0a9b8c7d-6e5f-4a3b-8c2d-1e0f9a8b7c6d";

    async fn system_schema(db: &PgAdapter) {
        crate::installer::ensure_hub_module_table(db).await.unwrap();
        crate::identity::ensure_tables(db).await.unwrap();
        crate::outbox::ensure_tables(db).await.unwrap();
        crate::system_migrations::apply(db, HUB).await.unwrap();
        crate::flows::store::ensure_indexes(db).await.unwrap();
        // The emitter's own data: the customers app owns Ana and Bea in both hubs, and the
        // intruder owns a row of its own whose id is a common word.
        db.execute_batch(
            "CREATE TABLE customers_customer (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, \
                                              name TEXT NOT NULL DEFAULT ''); \
             CREATE TABLE intruder_item (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);",
        )
        .await
        .unwrap();
        for id in [ANA, BEA] {
            owned_row(db, "customers_customer", id, HUB).await;
        }
        owned_row(db, "intruder_item", "id", HUB).await;
    }

    async fn owned_row(db: &PgAdapter, table: &str, id: &str, hub: &str) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub));
        db.execute(
            &format!("INSERT INTO {table} (id, hub_id) VALUES (:id, :hub_id)"),
            &p,
        )
        .await
        .unwrap();
    }

    const CUSTOMERS: &str = "customers";
    const INTRUDER: &str = "intruder";

    /// The customers app and an intruder, both installed: ownership is decided by the installed
    /// apps' table prefixes (the same rule as export and reset).
    fn registry() -> Registry {
        let mut reg = Registry::new();
        for id in [CUSTOMERS, INTRUDER] {
            reg.installed.push(
                serde_json::from_str(&format!(
                    r#"{{"id":"{id}","name":"{id}","version":"1.0.0"}}"#
                ))
                .unwrap(),
            );
        }
        reg
    }

    fn now() -> String {
        chrono::Utc::now().to_rfc3339()
    }

    struct Ev<'a> {
        id: &'a str,
        hub: &'a str,
        status: &'a str,
        name: &'a str,
        payload: Json,
        run_id: &'a str,
    }

    async fn event(db: &PgAdapter, e: Ev<'_>) {
        let mut p = Params::new();
        p.insert("id".into(), json!(e.id));
        p.insert("hub_id".into(), json!(e.hub));
        p.insert("status".into(), json!(e.status));
        p.insert("name".into(), json!(e.name));
        p.insert("payload".into(), json!(e.payload.to_string()));
        p.insert("run_id".into(), json!(e.run_id));
        p.insert("at".into(), json!(now()));
        let delivered = if e.status == "delivered" {
            ":at"
        } else {
            "NULL"
        };
        let discarded = if e.status == "discarded" {
            ":at"
        } else {
            "NULL"
        };
        db.execute(
            &format!(
                "INSERT INTO _event_outbox \
                 (id, hub_id, user_id, permissions, event_name, payload, status, next_attempt_at, \
                  created_at, delivered_at, discarded_at, module_id, run_id) \
                 VALUES (:id, :hub_id, 'u1', '[\"*\"]', :name, :payload, :status, :at, :at, \
                         {delivered}, {discarded}, 'customers', :run_id)"
            ),
            &p,
        )
        .await
        .unwrap();
    }

    async fn run(
        db: &PgAdapter,
        id: &str,
        hub: &str,
        status: &str,
        parent_event_id: &str,
        input: Json,
        vars: Json,
    ) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub));
        p.insert("status".into(), json!(status));
        p.insert("parent".into(), json!(parent_event_id));
        p.insert("input".into(), json!(input.to_string()));
        p.insert("vars".into(), json!(vars.to_string()));
        p.insert("at".into(), json!(now()));
        db.execute(
            "INSERT INTO _flow_runs \
             (id, hub_id, flow_id, parent_event_id, status, input, vars, created_at, updated_at) \
             VALUES (:id, :hub_id, 'f1', :parent, :status, :input, :vars, :at, :at)",
            &p,
        )
        .await
        .unwrap();
    }

    async fn step(
        db: &PgAdapter,
        id: &str,
        hub: &str,
        run_id: &str,
        idx: i64,
        input: Json,
        output: Json,
    ) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub));
        p.insert("run_id".into(), json!(run_id));
        p.insert("idx".into(), json!(idx));
        p.insert("input".into(), json!(input.to_string()));
        p.insert("output".into(), json!(output.to_string()));
        p.insert("at".into(), json!(now()));
        db.execute(
            "INSERT INTO _flow_run_steps \
             (id, hub_id, run_id, step_index, step_id, kind, status, input, output, created_at) \
             VALUES (:id, :hub_id, :run_id, :idx, 's', 'command', 'done', :input, :output, :at)",
            &p,
        )
        .await
        .unwrap();
    }

    async fn approval(
        db: &PgAdapter,
        id: &str,
        hub: &str,
        run_id: &str,
        status: &str,
        payload: Json,
    ) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub));
        p.insert("run_id".into(), json!(run_id));
        p.insert("status".into(), json!(status));
        p.insert("payload".into(), json!(payload.to_string()));
        p.insert("at".into(), json!(now()));
        db.execute(
            "INSERT INTO _flow_approvals \
             (id, hub_id, run_id, flow_id, step_id, command, payload, status, created_at, updated_at) \
             VALUES (:id, :hub_id, :run_id, 'f1', 's', 'm.c', :payload, :status, :at, :at)",
            &p,
        )
        .await
        .unwrap();
    }

    async fn cell(db: &PgAdapter, sql: &str, id: &str) -> String {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        let r = db.query(sql, &p).await.unwrap();
        assert_eq!(r.rows.len(), 1, "row {id} must still exist ({sql})");
        r.rows[0]["v"].as_str().unwrap_or_default().to_string()
    }

    async fn event_payload(db: &PgAdapter, id: &str) -> String {
        cell(
            db,
            "SELECT payload AS v FROM _event_outbox WHERE id = :id",
            id,
        )
        .await
    }

    async fn run_memory(db: &PgAdapter, id: &str) -> String {
        cell(
            db,
            "SELECT input || '|' || vars AS v FROM _flow_runs WHERE id = :id",
            id,
        )
        .await
    }

    async fn step_memory(db: &PgAdapter, id: &str) -> String {
        cell(
            db,
            "SELECT input || '|' || output AS v FROM _flow_run_steps WHERE id = :id",
            id,
        )
        .await
    }

    async fn approval_payload(db: &PgAdapter, id: &str) -> String {
        cell(
            db,
            "SELECT payload AS v FROM _flow_approvals WHERE id = :id",
            id,
        )
        .await
    }

    fn anonymized(customer_id: Json) -> Params {
        let mut p = Params::new();
        p.insert("customer_id".into(), customer_id);
        p.insert("reason".into(), json!("gdpr request"));
        p
    }

    const EMPTY: &str = "{}";
    const EMPTY_RUN: &str = "{}|{}";

    /// The WhatsApp booking recipe as it lands in history: the customer's update event carries
    /// her name and phone; a flow it triggered copied them into its input, a step looked her up
    /// and wrote the phone into its output, an approval proposed a message to her, and the run
    /// queued a reminder whose payload has the phone but NOT her id.
    async fn ana_history(db: &PgAdapter, hub: &str, prefix: &str) {
        event(
            db,
            Ev {
                id: &format!("{prefix}ev-upd"),
                hub,
                status: "delivered",
                name: "customer.updated",
                payload: json!({"id": ANA, "name": "Ana Pérez", "phone": "+34600111222"}),
                run_id: "",
            },
        )
        .await;
        event(
            db,
            Ev {
                id: &format!("{prefix}ev-sale"),
                hub,
                status: "discarded",
                name: "sale.completed",
                payload: json!({"sale_id": "s1", "customer_id": ANA, "total": 1200}),
                run_id: "",
            },
        )
        .await;
        run(
            db,
            &format!("{prefix}run"),
            hub,
            "done",
            &format!("{prefix}ev-upd"),
            json!({"name": "Ana Pérez"}),
            json!({"phone": "+34600111222"}),
        )
        .await;
        step(
            db,
            &format!("{prefix}step"),
            hub,
            &format!("{prefix}run"),
            0,
            json!({"q": "customers.get"}),
            json!({"phone": "+34600111222", "first_name": "Ana"}),
        )
        .await;
        approval(
            db,
            &format!("{prefix}appr"),
            hub,
            &format!("{prefix}run"),
            "approved",
            json!({"to": "+34600111222", "text": "Hola Ana"}),
        )
        .await;
        // A step that never held anything: emptying it again is not counted.
        step(
            db,
            &format!("{prefix}step-empty"),
            hub,
            &format!("{prefix}run"),
            1,
            json!({}),
            json!({}),
        )
        .await;
        // Four more runs, each linked to her by ONE thing only, so each link is proven on its own.
        run(
            db,
            &format!("{prefix}run-input"),
            hub,
            "failed",
            "",
            json!({"customer_id": ANA}),
            json!({}),
        )
        .await;
        run(
            db,
            &format!("{prefix}run-vars"),
            hub,
            "done",
            "",
            json!({"x": 1}),
            json!({"who": ANA}),
        )
        .await;
        run(
            db,
            &format!("{prefix}run-step"),
            hub,
            "cancelled",
            "",
            json!({"x": 1}),
            json!({}),
        )
        .await;
        step(
            db,
            &format!("{prefix}run-step-s"),
            hub,
            &format!("{prefix}run-step"),
            0,
            json!({}),
            json!({"customer_id": ANA}),
        )
        .await;
        // Its own memory is already empty: emptying it again is not counted.
        run(
            db,
            &format!("{prefix}run-appr"),
            hub,
            "done",
            "",
            json!({}),
            json!({}),
        )
        .await;
        approval(
            db,
            &format!("{prefix}run-appr-a"),
            hub,
            &format!("{prefix}run-appr"),
            "rejected",
            json!({"customer_id": ANA}),
        )
        .await;
        event(
            db,
            Ev {
                id: &format!("{prefix}ev-reminder"),
                hub,
                status: "delivered",
                name: "flows.reminder.due",
                payload: json!({"channel": "whatsapp", "to": "+34600111222"}),
                run_id: &format!("{prefix}run"),
            },
        )
        .await;
    }

    /// The bug itself: after `customer.anonymized`, everything the hub kept that names her — and
    /// everything an automation derived from it — still carried her name and phone. Now every one
    /// of those payloads is EMPTIED, and every row is still there (traceability survives).
    #[tokio::test]
    async fn an_erasure_empties_every_terminal_history_row_that_names_the_customer() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;

        let report = on_event(
            &db,
            &registry(),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert_eq!(
            event_payload(&db, "ev-upd").await,
            EMPTY,
            "the event that names her"
        );
        assert_eq!(
            event_payload(&db, "ev-sale").await,
            EMPTY,
            "a discarded event that links her"
        );
        assert_eq!(
            run_memory(&db, "run").await,
            EMPTY_RUN,
            "the run it triggered"
        );
        assert_eq!(
            step_memory(&db, "step").await,
            EMPTY_RUN,
            "a step of that run"
        );
        assert_eq!(
            approval_payload(&db, "appr").await,
            EMPTY,
            "the proposal of that run"
        );
        assert_eq!(
            event_payload(&db, "ev-reminder").await,
            EMPTY,
            "what that run queued carries her phone without her id"
        );
        for id in ["run-input", "run-vars", "run-step", "run-appr"] {
            assert_eq!(run_memory(&db, id).await, EMPTY_RUN, "{id}");
        }
        assert_eq!(step_memory(&db, "run-step-s").await, EMPTY_RUN);
        assert_eq!(approval_payload(&db, "run-appr-a").await, EMPTY);
        assert_eq!(
            report,
            ErasureReport {
                events: 3,
                runs: 4,
                run_steps: 2,
                approvals: 2
            }
        );
    }

    /// Tenancy: the same id in ANOTHER hub's history is another hub's business. Not one byte of
    /// hub B moves when hub A erases.
    #[tokio::test]
    async fn another_hubs_history_naming_the_same_id_is_untouched() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;
        ana_history(&db, OTHER_HUB, "b-").await;

        on_event(
            &db,
            &registry(),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert!(event_payload(&db, "b-ev-upd").await.contains("Ana Pérez"));
        assert!(event_payload(&db, "b-ev-sale").await.contains(ANA));
        assert!(event_payload(&db, "b-ev-reminder")
            .await
            .contains("+34600111222"));
        assert!(run_memory(&db, "b-run").await.contains("Ana Pérez"));
        assert!(step_memory(&db, "b-step").await.contains("+34600111222"));
        assert!(approval_payload(&db, "b-appr").await.contains("Hola Ana"));
        assert!(run_memory(&db, "b-run-input").await.contains(ANA));
        assert!(run_memory(&db, "b-run-vars").await.contains(ANA));
        assert!(run_memory(&db, "b-run-step").await.contains("\"x\""));
        assert!(step_memory(&db, "b-run-step-s").await.contains(ANA));
        assert!(approval_payload(&db, "b-run-appr-a").await.contains(ANA));
        // …and hub A was erased in the same database, so the filter is what saved B.
        assert_eq!(event_payload(&db, "ev-upd").await, EMPTY);
    }

    /// Another customer of the SAME hub keeps her history.
    #[tokio::test]
    async fn another_customers_history_is_untouched() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(
            &db,
            Ev {
                id: "ev-bea",
                hub: HUB,
                status: "delivered",
                name: "customer.updated",
                payload: json!({"id": BEA, "name": "Bea"}),
                run_id: "",
            },
        )
        .await;
        run(
            &db,
            "run-bea",
            HUB,
            "done",
            "ev-bea",
            json!({"customer_id": BEA}),
            json!({}),
        )
        .await;
        step(
            &db,
            "step-bea",
            HUB,
            "run-bea",
            0,
            json!({}),
            json!({"name": "Bea"}),
        )
        .await;
        // An id that merely STARTS with hers is somebody else.
        let longer = format!("{ANA}0");
        event(
            &db,
            Ev {
                id: "ev-longer",
                hub: HUB,
                status: "delivered",
                name: "customer.updated",
                payload: json!({"id": longer, "name": "Dora"}),
                run_id: "",
            },
        )
        .await;

        on_event(
            &db,
            &registry(),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert!(event_payload(&db, "ev-bea").await.contains("Bea"));
        assert!(run_memory(&db, "run-bea").await.contains(BEA));
        assert!(step_memory(&db, "step-bea").await.contains("Bea"));
        assert!(event_payload(&db, "ev-longer").await.contains("Dora"));
    }

    /// Live work keeps its data: a pending event has not been delivered yet, a dead one waits for
    /// a human (and may carry a fiscal record that must still reach the AEAT), and a running run
    /// or a pending proposal still needs what it holds. Emptying any of them would be data loss,
    /// not erasure — the same line `retention` draws.
    #[tokio::test]
    async fn live_work_keeps_its_payload() {
        let db = fresh_db().await;
        system_schema(&db).await;
        for (id, status) in [("ev-pending", "pending"), ("ev-dead", "dead")] {
            event(
                &db,
                Ev {
                    id,
                    hub: HUB,
                    status,
                    name: "sale.completed",
                    payload: json!({"customer_id": ANA}),
                    run_id: "",
                },
            )
            .await;
        }
        for status in ["running", "sleeping", "waiting_approval"] {
            let id = format!("run-{status}");
            run(
                &db,
                &id,
                HUB,
                status,
                "",
                json!({"customer_id": ANA}),
                json!({}),
            )
            .await;
            step(
                &db,
                &format!("{id}-s"),
                HUB,
                &id,
                0,
                json!({"customer_id": ANA}),
                json!({}),
            )
            .await;
        }
        approval(
            &db,
            "appr-pending",
            HUB,
            "run-waiting_approval",
            "pending",
            json!({"customer_id": ANA}),
        )
        .await;
        // A FINISHED run that touched her is emptied, but the reminder it queued has not gone out
        // yet: it keeps the phone it is about to be sent to.
        run(
            &db,
            "run-finished",
            HUB,
            "done",
            "",
            json!({"customer_id": ANA}),
            json!({}),
        )
        .await;
        event(
            &db,
            Ev {
                id: "ev-queued",
                hub: HUB,
                status: "pending",
                name: "flows.reminder.due",
                payload: json!({"channel": "whatsapp", "to": "+34600111222"}),
                run_id: "run-finished",
            },
        )
        .await;

        let report = on_event(
            &db,
            &registry(),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert_eq!(
            report,
            ErasureReport {
                runs: 1,
                ..ErasureReport::default()
            }
        );
        assert!(event_payload(&db, "ev-queued")
            .await
            .contains("+34600111222"));
        assert!(event_payload(&db, "ev-pending").await.contains(ANA));
        assert!(event_payload(&db, "ev-dead").await.contains(ANA));
        for status in ["running", "sleeping", "waiting_approval"] {
            assert!(
                run_memory(&db, &format!("run-{status}"))
                    .await
                    .contains(ANA),
                "{status}"
            );
            assert!(
                step_memory(&db, &format!("run-{status}-s"))
                    .await
                    .contains(ANA),
                "{status}"
            );
        }
        assert!(approval_payload(&db, "appr-pending").await.contains(ANA));
    }

    /// An event without a usable id erases NOTHING. The dangerous one is the empty string: as a
    /// needle, `""` is in every payload that has an empty value, which is most of them.
    #[tokio::test]
    async fn an_event_without_a_usable_subject_id_erases_nothing() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(
            &db,
            Ev {
                id: "ev-blank",
                hub: HUB,
                status: "delivered",
                name: "customer.updated",
                payload: json!({"id": "", "name": "Carla", "customer_id": 42}),
                run_id: "",
            },
        )
        .await;

        let mut missing = Params::new();
        missing.insert("reason".into(), json!("x"));
        for payload in [
            anonymized(json!("")),
            anonymized(json!(42)),
            anonymized(Json::Null),
            missing,
        ] {
            let report = on_event(
                &db,
                &registry(),
                HUB,
                CUSTOMERS,
                "customer.anonymized",
                &payload,
            )
            .await
            .unwrap();
            assert_eq!(report, ErasureReport::default(), "{payload:?}");
        }
        assert!(event_payload(&db, "ev-blank").await.contains("Carla"));
    }

    /// Only an `.anonymized` event erases: every other event that carries a `customer_id` (a sale,
    /// an update) is ordinary traffic.
    #[tokio::test]
    async fn only_an_anonymized_event_erases() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;

        for name in ["customer.updated", "sale.completed", "customer.deleted"] {
            let report = on_event(
                &db,
                &registry(),
                HUB,
                CUSTOMERS,
                name,
                &anonymized(json!(ANA)),
            )
            .await
            .unwrap();
            assert_eq!(report, ErasureReport::default(), "{name}");
        }
        assert!(event_payload(&db, "ev-upd").await.contains("Ana Pérez"));
    }

    /// The outbox is at-least-once: a second delivery of the same erasure finds nothing left to
    /// empty and says so.
    #[tokio::test]
    async fn a_redelivered_erasure_is_a_no_op() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;

        let first = on_event(
            &db,
            &registry(),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();
        let second = on_event(
            &db,
            &registry(),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert!(first.total() > 0);
        assert_eq!(second, ErasureReport::default());
    }

    /// The wiring: the relay itself runs the erasure when it delivers `customer.anonymized` — no
    /// module listens for it in the kernel's name, and a hub with no listener at all still erases.
    #[tokio::test]
    async fn the_relay_erases_when_it_delivers_customer_anonymized() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;
        event(
            &db,
            Ev {
                id: "ev-anon",
                hub: HUB,
                status: "pending",
                name: "customer.anonymized",
                payload: json!({"customer_id": ANA, "reason": "gdpr request"}),
                run_id: "",
            },
        )
        .await;

        crate::outbox::drain(&db, &registry()).await.unwrap();

        assert_eq!(event_payload(&db, "ev-upd").await, EMPTY);
        assert_eq!(run_memory(&db, "run").await, EMPTY_RUN);
        assert_eq!(step_memory(&db, "step").await, EMPTY_RUN);
        assert_eq!(
            cell(
                &db,
                "SELECT status AS v FROM _event_outbox WHERE id = :id",
                "ev-anon"
            )
            .await,
            "delivered"
        );
    }

    /// A failed erasure is never swallowed: the relay keeps `customer.anonymized` undelivered, names
    /// the erasure as what failed, and the retry finishes the job. Delivering the row anyway would
    /// be a GDPR erasure that silently did not happen.
    #[tokio::test]
    async fn a_failed_erasure_defers_the_event_and_the_retry_completes_it() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;
        event(
            &db,
            Ev {
                id: "ev-anon",
                hub: HUB,
                status: "pending",
                name: "customer.anonymized",
                payload: json!({"customer_id": ANA, "reason": "gdpr request"}),
                run_id: "",
            },
        )
        .await;
        // The statement cannot run while one of the tables it writes is away.
        db.execute(
            "ALTER TABLE _flow_approvals RENAME TO _flow_approvals_away",
            &Params::new(),
        )
        .await
        .unwrap();

        crate::outbox::drain(&db, &registry()).await.unwrap();

        assert_eq!(
            cell(
                &db,
                "SELECT status AS v FROM _event_outbox WHERE id = :id",
                "ev-anon"
            )
            .await,
            "pending"
        );
        // The label of WHAT failed (like `host.notify:`), not the prose of the database error.
        assert!(cell(
            &db,
            "SELECT last_error AS v FROM _event_outbox WHERE id = :id",
            "ev-anon"
        )
        .await
        .starts_with("erasure:"));
        // One statement: a failed erasure leaves nothing half-emptied.
        assert!(event_payload(&db, "ev-upd").await.contains("Ana Pérez"));

        db.execute(
            "ALTER TABLE _flow_approvals_away RENAME TO _flow_approvals",
            &Params::new(),
        )
        .await
        .unwrap();
        db.execute(
            "UPDATE _event_outbox SET next_attempt_at = '2020-01-01T00:00:00+00:00', \
             claim_expires_at = NULL WHERE id = 'ev-anon'",
            &Params::new(),
        )
        .await
        .unwrap();
        crate::outbox::drain(&db, &registry()).await.unwrap();

        assert_eq!(
            cell(
                &db,
                "SELECT status AS v FROM _event_outbox WHERE id = :id",
                "ev-anon"
            )
            .await,
            "delivered"
        );
        assert_eq!(event_payload(&db, "ev-upd").await, EMPTY);
        assert_eq!(approval_payload(&db, "appr").await, EMPTY);
    }

    /// A run whose ONLY link to her is what a step RECEIVED (a command called with her id that
    /// answered without repeating it) is still her history.
    #[tokio::test]
    async fn a_run_linked_only_by_a_steps_input_is_emptied() {
        let db = fresh_db().await;
        system_schema(&db).await;
        run(&db, "run-in", HUB, "done", "", json!({"x": 1}), json!({})).await;
        step(
            &db,
            "run-in-s",
            HUB,
            "run-in",
            0,
            json!({"customer_id": ANA}),
            json!({"ok": true}),
        )
        .await;

        let report = on_event(
            &db,
            &registry(),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert_eq!(run_memory(&db, "run-in").await, EMPTY_RUN);
        assert_eq!(step_memory(&db, "run-in-s").await, EMPTY_RUN);
        assert_eq!(
            report,
            ErasureReport {
                runs: 1,
                run_steps: 1,
                ..ErasureReport::default()
            }
        );
    }

    /// The subject is the LAST segment of the event name: a module-prefixed erasure
    /// (`whatsapp_inbox.conversation.anonymized`) names `conversation_id`, and only that key. A
    /// name with no subject right before the suffix is not an erasure.
    #[test]
    fn the_subject_is_the_last_segment_of_the_event_name() {
        let mut payload = Params::new();
        payload.insert("conversation_id".into(), json!("c-1"));

        assert_eq!(
            subject_id("whatsapp_inbox.conversation.anonymized", &payload),
            Some("c-1".to_string())
        );
        assert_eq!(
            subject_id(
                "whatsapp_inbox.conversation.anonymized",
                &anonymized(json!(ANA))
            ),
            None
        );
        for name in [
            ".anonymized",
            "anonymized",
            "conversation..anonymized",
            "conversation.anonymized.done",
        ] {
            assert_eq!(subject_id(name, &payload), None, "{name}");
        }
    }

    /// The code a refused erasure carries (tests assert on codes, never on prose — ADR-0055).
    fn refusal_code(err: &crate::errors::RuntimeError) -> &str {
        match err {
            crate::errors::RuntimeError::Domain { code, .. } => code,
            other => panic!("expected a coded refusal, got {other:?}"),
        }
    }

    /// Everything of Ana's history in `HUB` still says who she is.
    async fn assert_ana_history_intact(db: &PgAdapter) {
        assert!(event_payload(db, "ev-upd").await.contains("Ana Pérez"));
        assert!(run_memory(db, "run").await.contains("Ana Pérez"));
        assert!(step_memory(db, "step").await.contains("+34600111222"));
        assert!(approval_payload(db, "appr").await.contains("Hola Ana"));
        assert!(event_payload(db, "ev-reminder")
            .await
            .contains("+34600111222"));
    }

    /// hub#2485, the owner gate: an app may only erase a subject that is ITS OWN data. An app that
    /// names Ana — whose sheet belongs to `customers` — is refused, and so is the kernel (no app
    /// behind the event) and an app that is not installed. Not one byte of her history moves.
    #[tokio::test]
    async fn an_app_cannot_erase_a_subject_it_does_not_own() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;
        // A table that holds Ana's id but whose app is not installed owns nothing.
        db.execute_batch("CREATE TABLE ghost_item (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);")
            .await
            .unwrap();
        owned_row(&db, "ghost_item", ANA, HUB).await;

        for emitter in [INTRUDER, "", "ghost"] {
            let err = on_event(
                &db,
                &registry(),
                HUB,
                emitter,
                "customer.anonymized",
                &anonymized(json!(ANA)),
            )
            .await
            .unwrap_err();
            assert_eq!(
                refusal_code(&err),
                "erasure.subject_not_owned",
                "{emitter:?}"
            );
        }
        assert_ana_history_intact(&db).await;
    }

    /// The owner gate goes through `hub_id`: Ana's sheet in ANOTHER hub does not make her this
    /// hub's subject. Without the filter, any id the app owns anywhere would open the door here.
    #[tokio::test]
    async fn owning_the_subject_in_another_hub_does_not_open_this_one() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;
        db.execute(
            "UPDATE customers_customer SET hub_id = 'h2' WHERE id = :id",
            &{
                let mut p = Params::new();
                p.insert("id".into(), json!(ANA));
                p
            },
        )
        .await
        .unwrap();

        let err = on_event(
            &db,
            &registry(),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap_err();

        assert_eq!(refusal_code(&err), "erasure.subject_not_owned");
        assert_ana_history_intact(&db).await;
    }

    /// The vector of hub#2485: an app that OWNS a row whose id is a common word (`"id"`) names it
    /// as the subject. As a needle, `"id"` is a key of nearly every payload, so the erasure would
    /// empty the hub's whole history. The hub only takes ids of the shape it generates itself.
    #[tokio::test]
    async fn an_id_that_is_not_one_the_hub_generates_is_refused_even_from_its_owner() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;

        let mut payload = Params::new();
        payload.insert("item_id".into(), json!("id"));
        let err = on_event(&db, &registry(), HUB, INTRUDER, "item.anonymized", &payload)
            .await
            .unwrap_err();

        assert_eq!(refusal_code(&err), "erasure.invalid_subject_id");
        assert_ana_history_intact(&db).await;
    }

    /// The shape: a canonical hyphenated uuid, the form `registry::new_id` produces. Words,
    /// numbers and the other spellings `uuid` would parse are not ids the hub handed out.
    #[test]
    fn only_a_canonical_uuid_is_an_id_the_hub_generates() {
        assert!(is_generated_id(ANA));
        assert!(is_generated_id(&crate::registry::new_id()));
        for id in [
            "id",
            "1",
            "whatsapp",
            "name",
            "6f1c2a7e0d4b4f539a3e6c1d2b7e8f90",
            "{6f1c2a7e-0d4b-4f53-9a3e-6c1d2b7e8f90}",
            "urn:uuid:6f1c2a7e-0d4b-4f53-9a3e-6c1d2b7e8f90",
            "6f1c2a7e-0d4b-4f53-9a3e-6c1d2b7e8f9",
            "6f1c2a7e-0d4b-4f53-9a3e-6c1d2b7e8f9z",
        ] {
            assert!(!is_generated_id(id), "{id}");
        }
    }

    /// The real path, with a test app: `intruder` emits `customer.anonymized` naming Ana through
    /// the outbox. The relay refuses it — the event is NOT delivered (a refused erasure is never
    /// swallowed), the refusal is labelled as the erasure's with its code, and her history is
    /// intact. The same event from `customers` erases (the wiring test above).
    #[tokio::test]
    async fn the_relay_refuses_an_erasure_from_an_app_that_does_not_own_the_subject() {
        let db = fresh_db().await;
        system_schema(&db).await;
        ana_history(&db, HUB, "").await;
        event(
            &db,
            Ev {
                id: "ev-anon",
                hub: HUB,
                status: "pending",
                name: "customer.anonymized",
                payload: json!({"customer_id": ANA, "reason": "gdpr request"}),
                run_id: "",
            },
        )
        .await;
        db.execute(
            "UPDATE _event_outbox SET module_id = 'intruder' WHERE id = 'ev-anon'",
            &Params::new(),
        )
        .await
        .unwrap();

        crate::outbox::drain(&db, &registry()).await.unwrap();

        assert_eq!(
            cell(
                &db,
                "SELECT status AS v FROM _event_outbox WHERE id = :id",
                "ev-anon"
            )
            .await,
            "pending"
        );
        let last_error = cell(
            &db,
            "SELECT last_error AS v FROM _event_outbox WHERE id = :id",
            "ev-anon",
        )
        .await;
        assert!(last_error.starts_with("erasure:"), "{last_error}");
        assert!(
            last_error.contains("erasure.subject_not_owned"),
            "{last_error}"
        );
        assert_ana_history_intact(&db).await;
    }
}
