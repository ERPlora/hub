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
//!   NOT reachable from here: that needs the module to say what identified her (hub#2475).
//! - **The kernel does not know the customers module.** The trigger is the naming convention
//!   (`<subject>.anonymized` + `<subject>_id`), the same kind of contract as `.reminder.due` and
//!   `.print.due`. Today only `customer.anonymized` follows it.
//!
//! **Cost.** There is no index on payload content: one erasure reads the hub's terminal history
//! once (at most ninety days of it, thanks to `retention`). Erasures are rare, manual and
//! idempotent — an already-emptied row no longer contains the id, so a redelivery finds nothing.

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::Result;

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

/// Everything named in the module header, in ONE statement so the erasure is atomic and every
/// sub-statement sees the same snapshot (each table is written exactly once).
///
/// `:needle` is the id JSON-encoded (`"<id>"`, quotes included), so it matches the id as a string
/// VALUE and never as a fragment of a longer one. `hub_id` filters every read and every write:
/// the same id in another hub belongs to another hub. The `<> '{}'` guards make the counts say
/// what was actually emptied, so a redelivery reports zero.
const ERASE: &str = "\
WITH hit AS (\
  SELECT id FROM _event_outbox \
   WHERE hub_id = :hub_id AND status IN ('delivered', 'discarded') \
     AND strpos(payload, :needle) > 0\
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
    hub_id: &str,
    event_name: &str,
    payload: &Params,
) -> Result<ErasureReport> {
    let Some(id) = subject_id(event_name, payload) else {
        return Ok(ErasureReport::default());
    };
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
    use crate::registry::Registry;
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
        let delivered = if e.status == "delivered" { ":at" } else { "NULL" };
        let discarded = if e.status == "discarded" { ":at" } else { "NULL" };
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

    async fn step(db: &PgAdapter, id: &str, hub: &str, run_id: &str, idx: i64, input: Json, output: Json) {
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

    async fn approval(db: &PgAdapter, id: &str, hub: &str, run_id: &str, status: &str, payload: Json) {
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
        cell(db, "SELECT payload AS v FROM _event_outbox WHERE id = :id", id).await
    }

    async fn run_memory(db: &PgAdapter, id: &str) -> String {
        cell(db, "SELECT input || '|' || vars AS v FROM _flow_runs WHERE id = :id", id).await
    }

    async fn step_memory(db: &PgAdapter, id: &str) -> String {
        cell(db, "SELECT input || '|' || output AS v FROM _flow_run_steps WHERE id = :id", id).await
    }

    async fn approval_payload(db: &PgAdapter, id: &str) -> String {
        cell(db, "SELECT payload AS v FROM _flow_approvals WHERE id = :id", id).await
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
        event(db, Ev {
            id: &format!("{prefix}ev-upd"),
            hub,
            status: "delivered",
            name: "customer.updated",
            payload: json!({"id": ANA, "name": "Ana Pérez", "phone": "+34600111222"}),
            run_id: "",
        })
        .await;
        event(db, Ev {
            id: &format!("{prefix}ev-sale"),
            hub,
            status: "discarded",
            name: "sale.completed",
            payload: json!({"sale_id": "s1", "customer_id": ANA, "total": 1200}),
            run_id: "",
        })
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
        event(db, Ev {
            id: &format!("{prefix}ev-reminder"),
            hub,
            status: "delivered",
            name: "flows.reminder.due",
            payload: json!({"channel": "whatsapp", "to": "+34600111222"}),
            run_id: &format!("{prefix}run"),
        })
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

        let report = on_event(&db, HUB, "customer.anonymized", &anonymized(json!(ANA)))
            .await
            .unwrap();

        assert_eq!(event_payload(&db, "ev-upd").await, EMPTY, "the event that names her");
        assert_eq!(event_payload(&db, "ev-sale").await, EMPTY, "a discarded event that links her");
        assert_eq!(run_memory(&db, "run").await, EMPTY_RUN, "the run it triggered");
        assert_eq!(step_memory(&db, "step").await, EMPTY_RUN, "a step of that run");
        assert_eq!(approval_payload(&db, "appr").await, EMPTY, "the proposal of that run");
        assert_eq!(
            event_payload(&db, "ev-reminder").await,
            EMPTY,
            "what that run queued carries her phone without her id"
        );
        assert_eq!(
            report,
            ErasureReport { events: 3, runs: 1, run_steps: 1, approvals: 1 }
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

        on_event(&db, HUB, "customer.anonymized", &anonymized(json!(ANA)))
            .await
            .unwrap();

        assert!(event_payload(&db, "b-ev-upd").await.contains("Ana Pérez"));
        assert!(event_payload(&db, "b-ev-sale").await.contains(ANA));
        assert!(event_payload(&db, "b-ev-reminder").await.contains("+34600111222"));
        assert!(run_memory(&db, "b-run").await.contains("Ana Pérez"));
        assert!(step_memory(&db, "b-step").await.contains("+34600111222"));
        assert!(approval_payload(&db, "b-appr").await.contains("Hola Ana"));
        // …and hub A was erased in the same database, so the filter is what saved B.
        assert_eq!(event_payload(&db, "ev-upd").await, EMPTY);
    }

    /// Another customer of the SAME hub keeps her history.
    #[tokio::test]
    async fn another_customers_history_is_untouched() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(&db, Ev {
            id: "ev-bea",
            hub: HUB,
            status: "delivered",
            name: "customer.updated",
            payload: json!({"id": BEA, "name": "Bea"}),
            run_id: "",
        })
        .await;
        run(&db, "run-bea", HUB, "done", "ev-bea", json!({"customer_id": BEA}), json!({})).await;
        step(&db, "step-bea", HUB, "run-bea", 0, json!({}), json!({"name": "Bea"})).await;

        on_event(&db, HUB, "customer.anonymized", &anonymized(json!(ANA)))
            .await
            .unwrap();

        assert!(event_payload(&db, "ev-bea").await.contains("Bea"));
        assert!(run_memory(&db, "run-bea").await.contains(BEA));
        assert!(step_memory(&db, "step-bea").await.contains("Bea"));
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
            event(&db, Ev {
                id,
                hub: HUB,
                status,
                name: "sale.completed",
                payload: json!({"customer_id": ANA}),
                run_id: "",
            })
            .await;
        }
        for status in ["running", "sleeping", "waiting_approval"] {
            let id = format!("run-{status}");
            run(&db, &id, HUB, status, "", json!({"customer_id": ANA}), json!({})).await;
            step(&db, &format!("{id}-s"), HUB, &id, 0, json!({"customer_id": ANA}), json!({})).await;
        }
        approval(&db, "appr-pending", HUB, "run-waiting_approval", "pending", json!({"customer_id": ANA}))
            .await;

        let report = on_event(&db, HUB, "customer.anonymized", &anonymized(json!(ANA)))
            .await
            .unwrap();

        assert_eq!(report, ErasureReport::default());
        assert!(event_payload(&db, "ev-pending").await.contains(ANA));
        assert!(event_payload(&db, "ev-dead").await.contains(ANA));
        for status in ["running", "sleeping", "waiting_approval"] {
            assert!(run_memory(&db, &format!("run-{status}")).await.contains(ANA), "{status}");
            assert!(step_memory(&db, &format!("run-{status}-s")).await.contains(ANA), "{status}");
        }
        assert!(approval_payload(&db, "appr-pending").await.contains(ANA));
    }

    /// An event without a usable id erases NOTHING. The dangerous one is the empty string: as a
    /// needle, `""` is in every payload that has an empty value, which is most of them.
    #[tokio::test]
    async fn an_event_without_a_usable_subject_id_erases_nothing() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(&db, Ev {
            id: "ev-blank",
            hub: HUB,
            status: "delivered",
            name: "customer.updated",
            payload: json!({"id": "", "name": "Carla", "customer_id": 42}),
            run_id: "",
        })
        .await;

        let mut missing = Params::new();
        missing.insert("reason".into(), json!("x"));
        for payload in [anonymized(json!("")), anonymized(json!(42)), anonymized(Json::Null), missing] {
            let report = on_event(&db, HUB, "customer.anonymized", &payload).await.unwrap();
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
            let report = on_event(&db, HUB, name, &anonymized(json!(ANA))).await.unwrap();
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

        let first = on_event(&db, HUB, "customer.anonymized", &anonymized(json!(ANA)))
            .await
            .unwrap();
        let second = on_event(&db, HUB, "customer.anonymized", &anonymized(json!(ANA)))
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
        event(&db, Ev {
            id: "ev-anon",
            hub: HUB,
            status: "pending",
            name: "customer.anonymized",
            payload: json!({"customer_id": ANA, "reason": "gdpr request"}),
            run_id: "",
        })
        .await;

        crate::outbox::drain(&db, &Registry::new()).await.unwrap();

        assert_eq!(event_payload(&db, "ev-upd").await, EMPTY);
        assert_eq!(run_memory(&db, "run").await, EMPTY_RUN);
        assert_eq!(step_memory(&db, "step").await, EMPTY_RUN);
        assert_eq!(
            cell(&db, "SELECT status AS v FROM _event_outbox WHERE id = :id", "ev-anon").await,
            "delivered"
        );
    }
}
