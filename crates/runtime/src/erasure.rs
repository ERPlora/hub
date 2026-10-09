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
//! "Names that id" reaches further than the id itself (hub#2477, hub#2474): the hub also looks for
//! the rows that the emitter and the apps that LISTEN to the erasure keep about her — her WhatsApp
//! thread, then its messages ([`reach`]) — and, when one of those events was caused by a kernel
//! entry (an inbound WhatsApp message: no emitter, no run, no cause), for that entry and every
//! event that descends from it. That is what the person SAID, and none of it repeats her id.
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
//!   already pseudonymised when this runs. The hub follows ids through the apps' rows, never a
//!   phone number or a name: a message the inbox did not store (over its quota) has no row to
//!   follow and keeps its copy until `retention`. A person with no sheet is erased by the app that
//!   holds her: the inbox names its own thread (`whatsapp_inbox.conversation.anonymized`).
//! - **The kernel does not know the customers module.** The trigger is the naming convention
//!   (`<subject>.anonymized` + `<subject>_id`), the same kind of contract as `.reminder.due` and
//!   `.print.due`. Today `customer.anonymized` and `whatsapp_inbox.conversation.anonymized`
//!   follow it.
//! - **Only the owner erases (hub#2485).** The id must have the shape the hub generates (a
//!   canonical uuid) and be a row of one of the EMITTER's tables in this hub. Anything else is
//!   refused with a code (`erasure.invalid_subject_id`, `erasure.subject_not_owned`): nothing is
//!   emptied and the row is not marked delivered — it retries and ends in the dead letters, where
//!   a human sees it. The gate guards this history, not the delivery: the apps that listen to the
//!   event still get it, once each.
//!
//! **Cost.** There is no index on payload content: one erasure reads the hub's terminal history
//! once (at most ninety days of it, thanks to `retention`), extracting the ids each payload holds
//! and matching them against the set it looks for, plus one query per linked table and hop.
//! Erasures are rare, manual and idempotent — an already-emptied row no longer contains the ids,
//! so a redelivery finds nothing.

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

/// How many links the hub follows from the subject through the rows of the apps that hold it
/// (customer → conversation → message is two). A bound, not a tuning knob: every hop is one query
/// per table that has the column.
const MAX_HOPS: usize = 3;

/// The `<entity>_id` columns of this hub's row tables (see [`ROW_TABLES`]).
const ID_COLUMNS: &str = "\
SELECT c.table_name AS tbl, c.column_name AS col FROM information_schema.columns c \
 WHERE c.table_schema = current_schema() AND c.column_name LIKE '%\\_id' \
   AND c.column_name <> 'hub_id' AND c.table_name IN (\
     SELECT table_name FROM information_schema.columns \
      WHERE table_schema = current_schema() AND column_name IN ('id', 'hub_id') \
      GROUP BY table_name HAVING COUNT(*) = 2)";

/// **What else names her (hub#2477, hub#2474).** History keeps copies that never repeat the
/// subject's id: an inbound WhatsApp message names the row the inbox wrote for it, and that row
/// points at the thread, and the thread at her sheet. Those links live only in the apps' tables, so
/// the hub follows them there and adds every row it reaches to the ids it looks for:
///
/// - **Whose rows:** the emitter's and those of the apps that LISTEN to this erasure — the apps
///   that took on erasing her. An app that merely keeps a `customer_id` lends nothing.
/// - **Which links:** first the rows whose `<subject>_id` is the subject; from a row of
///   `<app>_<entity>`, the rows whose `<entity>_id` is that row. At most [`MAX_HOPS`] links.
/// - **Where:** only in this hub. Only ids of the shape the hub generates can match a payload
///   ([`NAMED_ID`]), so following another shape adds nothing to erase.
///
/// The subject comes first; the result has no repeats.
async fn reach(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    emitter: &str,
    event_name: &str,
    subject_id: &str,
) -> Result<Vec<String>> {
    let mut apps = vec![emitter.to_string()];
    for command in registry.listeners.get(event_name).into_iter().flatten() {
        if let Some(c) = registry.commands.get(command) {
            if !apps.contains(&c.module_id) {
                apps.push(c.module_id.clone());
            }
        }
    }
    let installed: Vec<String> = registry.installed.iter().map(|m| m.id.clone()).collect();
    // (table, entity, its `_id` columns), for the apps that lend their rows.
    let mut tables: Vec<(String, String, Vec<String>)> = Vec::new();
    for row in db.query(ID_COLUMNS, &Params::new()).await?.rows {
        let (Some(table), Some(col)) = (row["tbl"].as_str(), row["col"].as_str()) else {
            continue;
        };
        if !crate::export::safe_ident(table) || !crate::export::safe_ident(col) {
            continue;
        }
        let Some(owner) = crate::export::table_owner(table, &installed) else {
            continue;
        };
        if !apps.contains(&owner) {
            continue;
        }
        match tables.iter_mut().find(|t| t.0 == table) {
            Some(t) => t.2.push(col.to_string()),
            None => {
                let entity = table
                    .strip_prefix(&format!("{owner}_"))
                    .unwrap_or(table)
                    .to_string();
                tables.push((table.to_string(), entity, vec![col.to_string()]));
            }
        }
    }

    let subject = event_name
        .strip_suffix(ANONYMIZED_SUFFIX)
        .and_then(|s| s.rsplit('.').next())
        .unwrap_or_default();
    let mut found = vec![subject_id.to_string()];
    // Each step: the column that points at these ids, and the ids.
    let mut frontier: Vec<(String, Vec<String>)> =
        vec![(format!("{subject}_id"), vec![subject_id.to_string()])];
    for _ in 0..MAX_HOPS {
        let mut next = Vec::new();
        for (col, ids) in &frontier {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!(hub_id));
            p.insert("ids".into(), json!(Json::from(ids.clone()).to_string()));
            for (table, entity, cols) in &tables {
                if !cols.contains(col) {
                    continue;
                }
                let rows = db
                    .query(
                        &format!(
                            "SELECT CAST(id AS TEXT) AS id FROM \"{table}\" \
                             WHERE hub_id = :hub_id AND CAST(\"{col}\" AS TEXT) IN \
                               (SELECT jsonb_array_elements_text(CAST(:ids AS jsonb)))"
                        ),
                        &p,
                    )
                    .await?;
                let fresh: Vec<String> = rows
                    .rows
                    .iter()
                    .filter_map(|r| r["id"].as_str())
                    .filter(|id| !found.iter().any(|f| f == id))
                    .map(str::to_string)
                    .collect();
                if !fresh.is_empty() {
                    found.extend(fresh.iter().cloned());
                    next.push((format!("{entity}_id"), fresh));
                }
            }
        }
        if next.is_empty() {
            break;
        }
        frontier = next;
    }
    Ok(found)
}

/// The ids a payload names: every string of the shape the hub generates, keys included. Matching
/// whole quoted strings keeps an id from matching as a fragment of a longer one.
const NAMED_ID: &str = "\"([0-9A-Fa-f-]{36})\"";

/// Everything named in the module header, in ONE statement so the erasure is atomic and every
/// sub-statement sees the same snapshot (each table is written exactly once).
///
/// `named` is every event that names one of the ids, live or not: a run is history even when the
/// event that triggered it is still `dead`. Whether an EVENT may be emptied is decided once, at
/// its write.
///
/// **What the person said (hub#2477).** An inbound WhatsApp message enters as a KERNEL event —
/// no emitter, no run, no cause (`module_id`, `run_id` and `parent_event_id` all empty) — with the
/// number and the text and no id of any row. When an event that names her was caused by such an
/// entry, the entry is hers too, and so is everything that descends from it (`parent_event_id`):
/// the inbox's copy, what reacted to it. A completed copy of the same message is another kernel
/// entry whose id is the first one's plus `~<digest>` (hub#2102); it is the same message.
///
/// `:needles` is the JSON array of ids, `:named_id` the pattern above. `hub_id` filters every read
/// and every write: the same id in another hub belongs to another hub. The `<> '{}'` guards make
/// the counts say what was actually emptied, so a redelivery reports zero.
const ERASE: &str = "\
WITH RECURSIVE needle AS (\
  SELECT jsonb_array_elements_text(CAST(:needles AS jsonb)) AS id\
), named AS (\
  SELECT DISTINCT e.id, e.parent_event_id FROM _event_outbox e \
   CROSS JOIN LATERAL regexp_matches(e.payload, :named_id, 'g') m \
   WHERE e.hub_id = :hub_id AND m[1] IN (SELECT id FROM needle)\
), entry AS (\
  SELECT k.id FROM _event_outbox k \
   WHERE k.hub_id = :hub_id AND split_part(k.id, '~', 1) IN (\
       SELECT split_part(n.id, '~', 1) FROM _event_outbox n \
        WHERE n.hub_id = :hub_id AND n.module_id = '' AND n.run_id = '' AND n.parent_event_id = '' \
          AND (n.id IN (SELECT id FROM named) OR n.id IN (SELECT parent_event_id FROM named)))\
), descends(id) AS (\
  SELECT id FROM entry \
  UNION \
  SELECT c.id FROM _event_outbox c JOIN descends d ON c.parent_event_id = d.id \
   WHERE c.hub_id = :hub_id\
), hit AS (\
  SELECT id FROM named UNION SELECT id FROM descends\
), touched AS (\
  SELECT r.id FROM _flow_runs r \
   WHERE r.hub_id = :hub_id AND r.status IN ('done', 'failed', 'cancelled') \
     AND (r.parent_event_id IN (SELECT id FROM hit) \
          OR EXISTS (SELECT 1 FROM regexp_matches(r.input || ' ' || r.vars, :named_id, 'g') m \
                      WHERE m[1] IN (SELECT id FROM needle)) \
          OR EXISTS (SELECT 1 FROM _flow_run_steps s \
                      CROSS JOIN LATERAL regexp_matches(s.input || ' ' || s.output, :named_id, 'g') m \
                      WHERE s.hub_id = :hub_id AND s.run_id = r.id \
                        AND m[1] IN (SELECT id FROM needle)) \
          OR EXISTS (SELECT 1 FROM _flow_approvals a \
                      CROSS JOIN LATERAL regexp_matches(a.payload, :named_id, 'g') m \
                      WHERE a.hub_id = :hub_id AND a.run_id = r.id \
                        AND m[1] IN (SELECT id FROM needle)))\
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
    let needles = reach(db, registry, hub_id, emitter, event_name, &id).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("needles".into(), json!(Json::from(needles).to_string()));
    p.insert("named_id".into(), json!(NAMED_ID));
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

    // ── What she wrote on WhatsApp (hub#2477, hub#2474) ────────────────────────────────────────
    //
    // An inbound message lands in history as a chain that never names her sheet: the kernel's
    // `hub.whatsapp.message_received` (number + text), the inbox's `whatsapp_inbox.message.received`
    // (the same, plus the id of the message row it wrote) and whatever reacted to that. The only
    // link to her is in the inbox's own tables: conversation → customer, message → conversation.

    const WHATSAPP: &str = "whatsapp_inbox";
    const CONV_ANA: &str = "1b2c3d4e-5f60-4a1b-8c2d-3e4f5a6b7c8d";
    const MSG_ANA: &str = "2c3d4e5f-6071-4b2c-9d3e-4f5a6b7c8d9e";
    const CONV_BEA: &str = "3d4e5f60-7182-4c3d-8e4f-5a6b7c8d9e0f";
    const MSG_BEA: &str = "4e5f6071-8293-4d4e-9f50-6b7c8d9e0f1a";

    /// The installed apps of [`registry`] plus the inbox; `listens` says whether the inbox
    /// subscribes to `customer.anonymized` (it does in production).
    fn registry_with_inbox(listens: bool) -> Registry {
        let mut reg = registry();
        reg.installed.push(
            serde_json::from_str(&format!(
                r#"{{"id":"{WHATSAPP}","name":"{WHATSAPP}","version":"1.0.0"}}"#
            ))
            .unwrap(),
        );
        if listens {
            let command = "whatsapp_inbox._on_customer_anonymized";
            reg.commands.insert(
                command.into(),
                crate::registry::RegisteredCommand {
                    module_id: WHATSAPP.into(),
                    def: serde_json::from_value(json!({"permission": ""})).unwrap(),
                    sql: Vec::new(),
                    wasm: None,
                    schema: None,
                },
            );
            reg.listeners
                .insert("customer.anonymized".into(), vec![command.into()]);
        }
        reg
    }

    async fn inbox_tables(db: &PgAdapter) {
        db.execute_batch(
            "CREATE TABLE whatsapp_inbox_conversation (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, \
                                                       customer_id TEXT NOT NULL DEFAULT ''); \
             CREATE TABLE whatsapp_inbox_message (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, \
                                                  conversation_id TEXT);",
        )
        .await
        .unwrap();
    }

    async fn inbox_row(db: &PgAdapter, sql: &str, id: &str, link: &str) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(HUB));
        p.insert("link".into(), json!(link));
        db.execute(sql, &p).await.unwrap();
    }

    /// One conversation of `customer` with one message, as the inbox stores it.
    async fn inbox_thread(db: &PgAdapter, customer: &str, conv: &str, msg: &str) {
        inbox_row(
            db,
            "INSERT INTO whatsapp_inbox_conversation (id, hub_id, customer_id) \
             VALUES (:id, :hub_id, :link)",
            conv,
            customer,
        )
        .await;
        inbox_row(
            db,
            "INSERT INTO whatsapp_inbox_message (id, hub_id, conversation_id) \
             VALUES (:id, :hub_id, :link)",
            msg,
            conv,
        )
        .await;
    }

    /// A history row with the columns the relay writes for a chain: who emitted it and which
    /// event caused it.
    #[allow(clippy::too_many_arguments)]
    async fn chained(
        db: &PgAdapter,
        id: &str,
        hub: &str,
        module: &str,
        name: &str,
        status: &str,
        parent: &str,
        payload: Json,
    ) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub));
        p.insert("module".into(), json!(module));
        p.insert("name".into(), json!(name));
        p.insert("status".into(), json!(status));
        p.insert("parent".into(), json!(parent));
        p.insert("payload".into(), json!(payload.to_string()));
        p.insert("at".into(), json!(now()));
        db.execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, payload, status, next_attempt_at, \
              created_at, delivered_at, module_id, parent_event_id) \
             VALUES (:id, :hub_id, 'u1', '[\"*\"]', :name, :payload, :status, :at, :at, \
                     CASE WHEN :status = 'delivered' THEN :at END, :module, :parent)",
            &p,
        )
        .await
        .unwrap();
    }

    /// What one inbound message leaves in `hub`'s history, ids prefixed by `p`: the kernel's event,
    /// a completed copy of it (`~<digest>`, hub#2102), the inbox's event naming the message row
    /// `msg`, the inbox's event for the copy (its fresh `new_id` is no row: the copy updated the
    /// first one), what reacted to the inbox's event, a flow the kernel's event started and the
    /// auto-reply that flow queued. All of it holds `phone` and `text`; none of it her sheet's id.
    async fn wa_message(db: &PgAdapter, hub: &str, p: &str, msg: &str, phone: &str, text: &str) {
        let said = json!({"from": phone, "contact": phone, "text": text});
        let with_row = |id: &str| {
            let mut v = said.clone();
            v["new_id"] = json!(id);
            v
        };
        let core = format!("{p}wa-wamid.1");
        let copy = format!("{core}~0a1b2c3d");
        let done = "delivered";
        let kernel = "hub.whatsapp.message_received";
        let received = "whatsapp_inbox.message.received";
        chained(db, &core, hub, "", kernel, done, "", said.clone()).await;
        chained(db, &copy, hub, "", kernel, done, "", said.clone()).await;
        let inbox = format!("{p}ev-received");
        chained(
            db,
            &inbox,
            hub,
            WHATSAPP,
            received,
            done,
            &core,
            with_row(msg),
        )
        .await;
        let copy_inbox = format!("{p}ev-received-copy");
        let fresh = crate::registry::new_id();
        chained(
            db,
            &copy_inbox,
            hub,
            WHATSAPP,
            received,
            done,
            &copy,
            with_row(&fresh),
        )
        .await;
        let link = "whatsapp_inbox.conversation.link_pending";
        let fresh = crate::registry::new_id();
        let reacted = format!("{p}ev-link");
        chained(
            db,
            &reacted,
            hub,
            WHATSAPP,
            link,
            done,
            &inbox,
            with_row(&fresh),
        )
        .await;
        let flow = format!("{p}run-wa");
        run(db, &flow, hub, "done", &core, said.clone(), json!({})).await;
        event(
            db,
            Ev {
                id: &format!("{p}ev-autoreply"),
                hub,
                status: "delivered",
                name: "flow.reminder.due",
                payload: json!({"to": phone, "body": "Gracias"}),
                run_id: &flow,
            },
        )
        .await;
    }

    /// Every row [`wa_message`] wrote with prefix `p`.
    fn wa_rows(p: &str) -> Vec<String> {
        [
            "wa-wamid.1",
            "wa-wamid.1~0a1b2c3d",
            "ev-received",
            "ev-received-copy",
            "ev-link",
            "ev-autoreply",
        ]
        .iter()
        .map(|id| format!("{p}{id}"))
        .collect()
    }

    async fn assert_wa_emptied(db: &PgAdapter, p: &str) {
        for id in wa_rows(p) {
            assert_eq!(event_payload(db, &id).await, EMPTY, "{id}");
        }
        assert_eq!(run_memory(db, &format!("{p}run-wa")).await, EMPTY_RUN);
    }

    async fn assert_wa_intact(db: &PgAdapter, p: &str, phone: &str) {
        for id in wa_rows(p) {
            assert!(event_payload(db, &id).await.contains(phone), "{id}");
        }
        assert!(run_memory(db, &format!("{p}run-wa")).await.contains(phone));
    }

    /// Ana and Bea both wrote; Ana's thread is linked to her sheet, Bea's to hers; the same
    /// message id also appears in another hub's history.
    async fn two_whatsapp_customers(db: &PgAdapter) {
        system_schema(db).await;
        inbox_tables(db).await;
        inbox_thread(db, ANA, CONV_ANA, MSG_ANA).await;
        inbox_thread(db, BEA, CONV_BEA, MSG_BEA).await;
        wa_message(db, HUB, "ana-", MSG_ANA, "+34600111222", "Hola, soy Ana").await;
        wa_message(db, HUB, "bea-", MSG_BEA, "+34600333444", "Hola, soy Bea").await;
        wa_message(
            db,
            OTHER_HUB,
            "h2-",
            MSG_ANA,
            "+34600111222",
            "Hola, soy Ana",
        )
        .await;
    }

    /// hub#2477: erasing Ana's sheet empties what she wrote on WhatsApp — the kernel's copy, the
    /// inbox's, what reacted to it and the flow it started — reached through the inbox, which
    /// listens to the erasure and links her sheet to her thread. Bea's messages and the other hub's
    /// copies stay.
    #[tokio::test]
    async fn erasing_a_customer_empties_what_she_wrote_on_whatsapp() {
        let db = fresh_db().await;
        two_whatsapp_customers(&db).await;

        on_event(
            &db,
            &registry_with_inbox(true),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert_wa_emptied(&db, "ana-").await;
        assert_wa_intact(&db, "bea-", "+34600333444").await;
        assert_wa_intact(&db, "h2-", "+34600111222").await;
    }

    /// hub#2474: «Erase this number's data» on a thread with no sheet. The inbox names its own
    /// conversation in `whatsapp_inbox.conversation.anonymized`; the hub follows it to the
    /// messages of that thread and empties the same chain. Bea's thread stays.
    #[tokio::test]
    async fn erasing_a_whatsapp_number_empties_what_it_wrote() {
        let db = fresh_db().await;
        two_whatsapp_customers(&db).await;
        let mut payload = Params::new();
        payload.insert("conversation_id".into(), json!(CONV_ANA));

        on_event(
            &db,
            &registry_with_inbox(true),
            HUB,
            WHATSAPP,
            "whatsapp_inbox.conversation.anonymized",
            &payload,
        )
        .await
        .unwrap();

        assert_wa_emptied(&db, "ana-").await;
        assert_wa_intact(&db, "bea-", "+34600333444").await;
        assert_wa_intact(&db, "h2-", "+34600111222").await;
    }

    /// The reach is bounded by consent: only the emitter and the apps that LISTEN to the erasure
    /// lend their rows. An app that keeps a `customer_id` but does not subscribe is not followed.
    #[tokio::test]
    async fn an_app_that_does_not_listen_to_the_erasure_is_not_followed() {
        let db = fresh_db().await;
        two_whatsapp_customers(&db).await;

        on_event(
            &db,
            &registry_with_inbox(false),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert_wa_intact(&db, "ana-", "+34600111222").await;
    }

    /// A message still in flight keeps its payload: the terminal rule of the module header holds
    /// for the rows reached through the inbox too.
    /// Tenancy of the reach: another hub's rows and events are never followed, not even when
    /// they point at this hub's ids. Every `x-` row below is of THIS hub and is not Ana's; each one
    /// would be reached through another hub's row:
    ///
    /// - `x-by-row` names a message of another hub's thread, and that thread names Ana's id;
    /// - `x-by-chain` descends from another hub's event, which descends from Ana's message;
    /// - `x-by-cause` caused another hub's event that names Ana's message;
    /// - `x-h2-cause~1a2b3c4d` is a copy of another hub's entry, which caused an event here that
    ///   names Ana's message (that event is hers and is emptied);
    /// - `x-under-h2-copy` descends from another hub's copy of Ana's message.
    #[tokio::test]
    async fn another_hubs_rows_and_events_are_not_followed() {
        const CONV_H2: &str = "5f607182-93a4-4e5f-8061-7c8d9e0f1a2b";
        const MSG_H2: &str = "60718293-a4b5-4f60-9172-8d9e0f1a2b3c";
        let db = fresh_db().await;
        two_whatsapp_customers(&db).await;
        let conv = "INSERT INTO whatsapp_inbox_conversation (id, hub_id, customer_id) \
                    VALUES (:id, 'h2', :link)";
        inbox_row(&db, conv, CONV_H2, ANA).await;
        let msg = "INSERT INTO whatsapp_inbox_message (id, hub_id, conversation_id) \
                   VALUES (:id, 'h2', :link)";
        inbox_row(&db, msg, MSG_H2, CONV_H2).await;

        let kept = json!({"text": "not hers", "new_id": MSG_H2});
        let names_her = json!({"new_id": MSG_ANA});
        let kernel = "hub.whatsapp.message_received";
        let inbox = "whatsapp_inbox.message.received";
        // (id, hub, emitter, event, cause, payload)
        let rows: [(&str, &str, &str, &str, &str, &Json); 9] = [
            ("x-by-row", HUB, WHATSAPP, inbox, "", &kept),
            ("x-h2", OTHER_HUB, WHATSAPP, inbox, "ana-wa-wamid.1", &kept),
            ("x-by-chain", HUB, WHATSAPP, inbox, "x-h2", &kept),
            ("x-by-cause", HUB, "", kernel, "", &kept),
            (
                "x-h2-names",
                OTHER_HUB,
                WHATSAPP,
                inbox,
                "x-by-cause",
                &names_her,
            ),
            ("x-h2-cause", OTHER_HUB, "", kernel, "", &kept),
            ("x-h2-cause~1a2b3c4d", HUB, "", kernel, "", &kept),
            (
                "x-names-her",
                HUB,
                WHATSAPP,
                inbox,
                "x-h2-cause",
                &names_her,
            ),
            ("ana-wa-wamid.1~5e6f7a8b", OTHER_HUB, "", kernel, "", &kept),
        ];
        for (id, hub, module, name, cause, payload) in rows {
            chained(
                &db,
                id,
                hub,
                module,
                name,
                "delivered",
                cause,
                payload.clone(),
            )
            .await;
        }
        let under = "x-under-h2-copy";
        let copy = "ana-wa-wamid.1~5e6f7a8b";
        chained(
            &db,
            under,
            HUB,
            WHATSAPP,
            inbox,
            "delivered",
            copy,
            kept.clone(),
        )
        .await;

        on_event(
            &db,
            &registry_with_inbox(true),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert_wa_emptied(&db, "ana-").await;
        assert_eq!(event_payload(&db, "x-names-her").await, EMPTY);
        for id in [
            "x-by-row",
            "x-by-chain",
            "x-by-cause",
            "x-h2-cause~1a2b3c4d",
            "x-under-h2-copy",
        ] {
            assert!(event_payload(&db, id).await.contains("not hers"), "{id}");
        }
    }

    /// Only what entered through the kernel brings its descendants along: an APP event that names
    /// her is emptied, but what it caused (a sale, an invoice) is someone else's record and does
    /// not name her.
    #[tokio::test]
    async fn what_an_app_event_about_her_caused_is_not_hers() {
        let db = fresh_db().await;
        two_whatsapp_customers(&db).await;
        let named = json!({"customer_id": ANA});
        let sale = json!({"sale_id": "s-1", "total": 1250});
        let done = "delivered";
        chained(
            &db,
            "x-updated",
            HUB,
            CUSTOMERS,
            "customer.updated",
            done,
            "",
            named,
        )
        .await;
        chained(
            &db,
            "x-sale",
            HUB,
            "sales",
            "sale.completed",
            done,
            "x-updated",
            sale,
        )
        .await;

        on_event(
            &db,
            &registry_with_inbox(true),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert_eq!(event_payload(&db, "x-updated").await, EMPTY);
        assert!(event_payload(&db, "x-sale").await.contains("1250"));
    }

    #[tokio::test]
    async fn a_whatsapp_message_still_in_flight_keeps_its_payload() {
        let db = fresh_db().await;
        two_whatsapp_customers(&db).await;
        db.execute(
            "UPDATE _event_outbox SET status = 'pending', delivered_at = NULL \
              WHERE id = 'ana-ev-link'",
            &Params::new(),
        )
        .await
        .unwrap();

        on_event(
            &db,
            &registry_with_inbox(true),
            HUB,
            CUSTOMERS,
            "customer.anonymized",
            &anonymized(json!(ANA)),
        )
        .await
        .unwrap();

        assert!(event_payload(&db, "ana-ev-link")
            .await
            .contains("+34600111222"));
        assert_eq!(event_payload(&db, "ana-ev-received").await, EMPTY);
    }
}
