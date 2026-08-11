//! **What starts a run**: an event in the outbox, a clock, or a person pressing a button.
//!
//! The on-event path is the delicate one, and its rule is a single sentence from ADR-0283 §3: the
//! relay **only inserts the run**. It does not execute it. The relay holds the runtime's global
//! lock while it delivers, so a flow that runs inline would freeze every command in the hub for as
//! long as the flow takes — the same reasoning that puts I/O steps outside the lock.
//!
//! Idempotence reuses what already exists instead of inventing a second mechanism: the run
//! insertion and a row in `_event_delivery` under a **synthetic listener** `_flow:<trigger_id>`
//! go in ONE transaction. So the marker that stops a listener from running twice stops a trigger
//! from creating two runs for the same event, with no new table and no new failure mode.
//!
//! ## The two anti-loop guards, and why one is not enough
//!
//! A flow whose command emits the very event that triggers it is not a hypothetical — it is the
//! first mistake anybody writes in a visual editor.
//!
//! 1. **Depth.** A run inherits the depth of the event that started it and passes it to
//!    `execute_at`, so the events its commands emit are born one level deeper, and the chain dies
//!    at [`MAX_EVENT_DEPTH`]. This is why `_flow_runs.depth` exists (an addition to flows.md §3,
//!    which relied on the event depth alone): without carrying it, every flow-emitted event would
//!    restart at depth 1 and the ceiling would be one nothing ever reaches.
//! 2. **Rate.** Depth does not bound a flow that re-triggers itself through a path that resets it
//!    (a manual run, a cron), so a flow is also capped at [`MAX_RUNS_PER_MINUTE`]. Over the cap
//!    the event is marked delivered and dropped, deliberately: retrying it forever is the same
//!    runaway with extra steps. The hub stays up; the flow stops.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::commands::MAX_EVENT_DEPTH;
use crate::errors::Result;
use crate::flows::def::{self, Condition};
use crate::flows::store;
use crate::registry::now_rfc3339;
use crate::scheduler::cron;

/// How many runs one flow may start per minute before the kernel stops it. Generous for anything
/// a business does on purpose (a busy till closes far fewer sales than this), small enough that a
/// runaway costs a bounded number of rows.
pub const MAX_RUNS_PER_MINUTE: i64 = 30;

/// How long a claimed clock trigger stays invisible to another runtime. Same value as the outbox
/// and the scheduler: start-first deploys (ADR-0269) mean two runtimes share this table.
const LEASE_SECONDS: i64 = 300;

/// The `_event_delivery` listener name a trigger books its idempotence under. It is not a command
/// — nothing can call it — which is exactly why it cannot collide with a module's listener.
pub fn synthetic_listener(trigger_id: &str) -> String {
    format!("_flow:{trigger_id}")
}

/// Matches one delivered event against the enabled `event` triggers of this hub and inserts a run
/// per match. Returns how many runs it created.
///
/// Called by the outbox relay AFTER the manifest listeners, so a flow reacting to an event never
/// changes when that event's own listeners run.
pub async fn on_event(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_id: &str,
    event_name: &str,
    payload: &Params,
    depth: u32,
) -> Result<usize> {
    // Guard 1: a cascade that already went this deep does not get to start new work.
    if depth >= MAX_EVENT_DEPTH {
        return Ok(0);
    }

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("event_name".into(), json!(event_name));
    // Only triggers of a flow that is alive AND enabled: disabling a flow in the UI has to stop
    // it from reacting, and the trigger row alone cannot say that after a `PUT /flows/{id}`.
    let candidates = db
        .query(
            "SELECT t.id, t.flow_id, t.filter, t.input_map FROM _flow_triggers t \
             JOIN _flow f ON f.id = t.flow_id AND f.hub_id = t.hub_id AND f.deleted_at IS NULL \
             WHERE t.hub_id = :hub_id AND t.kind = 'event' AND t.event_name = :event_name \
               AND t.enabled = 1 AND t.deleted_at IS NULL AND f.enabled = 1 \
             ORDER BY t.created_at, t.id",
            &p,
        )
        .await?;

    let scope = json!({ "event": Json::Object(payload.clone()) });
    let mut started = 0usize;

    for row in &candidates.rows {
        let trigger_id = row["id"].as_str().unwrap_or_default().to_string();
        let flow_id = row["flow_id"].as_str().unwrap_or_default().to_string();
        let listener = synthetic_listener(&trigger_id);

        // Already handled in a previous attempt of this same event (the relay is at-least-once).
        if delivery_exists(db, event_id, &listener).await? {
            continue;
        }

        // The declarative filter, over `event.<field>` paths. A trigger with no filter matches
        // every occurrence of its event — explicit, because no filter written means none meant.
        let filter = parse_condition(row["filter"].as_str().unwrap_or("{}"));
        if !filter.matches(&scope) {
            // Not a match is a decision, not a pending job: book it so the next attempt of the
            // same event does not re-evaluate a filter that already said no.
            mark_delivered(db, event_id, &listener).await?;
            continue;
        }

        // Guard 2: a flow that is already running away does not get another run.
        if runs_in_last_minute(db, hub_id, &flow_id).await? >= MAX_RUNS_PER_MINUTE {
            eprintln!(
                "flows: flow {flow_id} exceeded {MAX_RUNS_PER_MINUTE} runs/min (event \
                 {event_name}); the event is dropped to keep the hub up"
            );
            mark_delivered(db, event_id, &listener).await?;
            continue;
        }

        let input = input_from(row["input_map"].as_str().unwrap_or("{}"), &scope, payload);
        let (sql, params) = store::insert_run_op(
            hub_id,
            &flow_id,
            &trigger_id,
            "event",
            event_id,
            &input,
            i64::from(depth),
            &format!("flow:{flow_id}"),
        );
        // The run and its idempotence marker commit together, or neither does.
        db.execute_tx(&[(sql, params), delivery_op(event_id, &listener)])
            .await?;
        started += 1;
    }
    Ok(started)
}

/// One sweep of the `cron`/`at` triggers: claims what is due, starts its run and moves the clock
/// forward. `at` is one-shot — it disables itself after firing, which is what gives flows their
/// "in three days, send X".
pub async fn sweep_schedules(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<usize> {
    let now = now_rfc3339();
    let tz = crate::settings::timezone_of(db, hub_id).await?;
    // Before claiming anything: re-arm whatever was armed on a different clock (hub#731).
    retime_to_current_zone(db, hub_id, &now, tz).await?;

    let mut started = 0usize;
    // Bounded per tick for the same reason the outbox batches: this runs inside the runtime's
    // global lock, and a backlog must not hold it.
    for _ in 0..20 {
        let Some(row) = claim_due_schedule(db, hub_id, &now).await? else {
            break;
        };
        let trigger_id = row["id"].as_str().unwrap_or_default().to_string();
        let flow_id = row["flow_id"].as_str().unwrap_or_default().to_string();
        let kind = row["kind"].as_str().unwrap_or_default().to_string();
        let expr = row["cron"].as_str().unwrap_or_default().to_string();

        if runs_in_last_minute(db, hub_id, &flow_id).await? >= MAX_RUNS_PER_MINUTE {
            eprintln!("flows: flow {flow_id} exceeded {MAX_RUNS_PER_MINUTE} runs/min (schedule)");
            advance_schedule(db, &trigger_id, &kind, &expr, &now, tz).await?;
            continue;
        }

        let input = input_from(
            row["input_map"].as_str().unwrap_or("{}"),
            &json!({}),
            &Params::new(),
        );
        let (sql, params) = store::insert_run_op(
            hub_id,
            &flow_id,
            &trigger_id,
            &kind,
            "",
            &input,
            0,
            &format!("flow:{flow_id}"),
        );
        // Firing and moving the clock commit together: if the insert fails the trigger stays due,
        // and if it succeeds the trigger cannot fire twice for the same instant.
        let advance = advance_schedule_op(&trigger_id, &kind, &expr, &now, tz);
        db.execute_tx(&[(sql, params), advance]).await?;
        started += 1;
    }
    Ok(started)
}

/// Re-arms the `cron` triggers whose `next_run` was computed on a clock that is no longer the
/// hub's (hub#731). One statement's worth of work in the normal case (nothing matches), and it is
/// what answers the two questions the change opens:
///
/// - **The triggers that already existed, read in UTC.** They migrate on the first tick after the
///   upgrade instead of firing once at the old hour — for a nightly flow that is one wrong run,
///   for an annual one it is half a year.
/// - **A business that changes zone** (moves, or just fixes its `country_code`). Its flows follow
///   without anybody re-saving them one by one, which is what the owner assumes happened.
///
/// It cannot loop: it only touches rows whose stored zone differs, and it writes that zone.
async fn retime_to_current_zone(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    now: &str,
    tz: cron::Tz,
) -> Result<()> {
    let mut q = Params::new();
    q.insert("hub_id".into(), json!(hub_id));
    q.insert("tz".into(), json!(tz.name()));
    let stale = db
        .query(
            "SELECT id, cron FROM _flow_triggers \
             WHERE hub_id = :hub_id AND kind = 'cron' AND deleted_at IS NULL AND tz <> :tz \
             LIMIT 100",
            &q,
        )
        .await?;
    for row in &stale.rows {
        let id = row["id"].as_str().unwrap_or_default().to_string();
        let expr = row["cron"].as_str().unwrap_or_default();
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("tz".into(), json!(tz.name()));
        p.insert("now".into(), json!(now));
        p.insert("next_run".into(), json!(cron::next_after_in_tz(expr, now, tz)));
        db.execute(
            "UPDATE _flow_triggers SET next_run = :next_run, tz = :tz, updated_at = :now \
             WHERE id = :id",
            &p,
        )
        .await?;
    }
    Ok(())
}

/// Claims one due clock trigger atomically (`FOR UPDATE SKIP LOCKED` + lease), the same shape as
/// `scheduler::claim_next_due`: two runtimes of the same hub take different rows.
async fn claim_due_schedule(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    now: &str,
) -> Result<Option<Json>> {
    let lease = (chrono::Utc::now() + chrono::Duration::seconds(LEASE_SECONDS)).to_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    p.insert("lease".into(), json!(lease));
    let sql = "UPDATE _flow_triggers SET claim_expires_at = :lease \
               WHERE id = ( \
                 SELECT t.id FROM _flow_triggers t \
                 JOIN _flow f ON f.id = t.flow_id AND f.hub_id = t.hub_id \
                                 AND f.deleted_at IS NULL AND f.enabled = 1 \
                 WHERE t.hub_id = :hub_id AND t.kind IN ('cron','at') AND t.enabled = 1 \
                   AND t.deleted_at IS NULL AND t.next_run IS NOT NULL AND t.next_run <= :now \
                   AND (t.claim_expires_at IS NULL OR t.claim_expires_at <= :now) \
                 ORDER BY t.next_run LIMIT 1 FOR UPDATE SKIP LOCKED) \
               RETURNING id, flow_id, kind, cron, input_map";
    let res = db.query(sql, &p).await?;
    Ok(res.rows.into_iter().next())
}

/// Moves a fired trigger's clock: a `cron` to its next occurrence strictly after now **on the
/// business clock** (collapsing a backlog, like the scheduler), an `at` to never (`enabled = 0` —
/// it was one-shot).
fn advance_schedule_op(
    trigger_id: &str,
    kind: &str,
    expr: &str,
    now: &str,
    tz: cron::Tz,
) -> (String, Params) {
    let mut p = Params::new();
    p.insert("id".into(), json!(trigger_id));
    p.insert("now".into(), json!(now));
    let sql = if kind == "cron" {
        // hub#730: the fallback used to be `now`, which means "due again on the very next tick" —
        // a runaway held back only by `MAX_RUNS_PER_MINUTE`. It is unreachable now (the API gate
        // refuses what does not parse, and an unreachable date like 29 February is refused too),
        // so if it ever happens the row stops instead of spinning, and says so.
        let next = cron::next_after_in_tz(expr, now, tz);
        if next.is_none() {
            eprintln!(
                "flows: trigger {trigger_id}: `{expr}` has no next occurrence on {}; the trigger \
                 is disarmed instead of firing every tick",
                tz.name()
            );
        }
        p.insert("next_run".into(), json!(next));
        p.insert("tz".into(), json!(tz.name()));
        "UPDATE _flow_triggers SET next_run = :next_run, tz = :tz, last_run = :now, \
         claim_expires_at = NULL, updated_at = :now WHERE id = :id"
    } else {
        "UPDATE _flow_triggers SET enabled = 0, next_run = NULL, last_run = :now, \
         claim_expires_at = NULL, updated_at = :now WHERE id = :id"
    };
    (sql.to_string(), p)
}

async fn advance_schedule(
    db: &dyn DatabaseAdapter,
    trigger_id: &str,
    kind: &str,
    expr: &str,
    now: &str,
    tz: cron::Tz,
) -> Result<()> {
    let (sql, p) = advance_schedule_op(trigger_id, kind, expr, now, tz);
    db.execute(&sql, &p).await?;
    Ok(())
}

/// How many runs this flow started in the last minute — the rate guard's only question.
async fn runs_in_last_minute(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
) -> Result<i64> {
    let since = (chrono::Utc::now() - chrono::Duration::seconds(60)).to_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("since".into(), json!(since));
    let res = db
        .query(
            "SELECT COUNT(*) AS c FROM _flow_runs \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND created_at >= :since",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["c"].as_i64().or_else(|| r["c"].as_f64().map(|f| f as i64)))
        .unwrap_or(0))
}

/// The run's `input`. An empty `input_map` passes the event payload through whole: the common case
/// is "react to this event", and forcing everybody to write an identity mapping would be ceremony.
fn input_from(input_map: &str, scope: &Json, payload: &Params) -> Json {
    let mapping: Json = serde_json::from_str(input_map).unwrap_or(Json::Null);
    match mapping {
        Json::Object(map) if !map.is_empty() => Json::Object(def::resolve_map(&map, scope)),
        _ => Json::Object(payload.clone()),
    }
}

fn parse_condition(raw: &str) -> Condition {
    serde_json::from_str::<Json>(raw)
        .ok()
        .and_then(|v| Condition::parse(&v).ok())
        .unwrap_or_default()
}

fn delivery_op(event_id: &str, listener: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("event_id".into(), json!(event_id));
    p.insert("listener_command".into(), json!(listener));
    p.insert("delivered_at".into(), json!(now_rfc3339()));
    (
        "INSERT INTO _event_delivery (event_id, listener_command, delivered_at) \
         VALUES (:event_id, :listener_command, :delivered_at)"
            .to_string(),
        p,
    )
}

async fn mark_delivered(db: &dyn DatabaseAdapter, event_id: &str, listener: &str) -> Result<()> {
    let (sql, p) = delivery_op(event_id, listener);
    db.execute(&sql, &p).await?;
    Ok(())
}

async fn delivery_exists(db: &dyn DatabaseAdapter, event_id: &str, listener: &str) -> Result<bool> {
    let mut p = Params::new();
    p.insert("event_id".into(), json!(event_id));
    p.insert("listener_command".into(), json!(listener));
    let res = db
        .query(
            "SELECT 1 AS ok FROM _event_delivery \
             WHERE event_id = :event_id AND listener_command = :listener_command",
            &p,
        )
        .await?;
    Ok(!res.rows.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::store::{self, NewFlow};
    use crate::flows::test_support;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-triggers";

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db
    }

    async fn flow_with(db: &dyn DatabaseAdapter, definition: Json) -> String {
        store::create(
            db,
            HUB,
            &crate::registry::Registry::new(),
            &NewFlow {
                name: "T".into(),
                enabled: true,
                definition,
            },
            "hub_user:1",
        )
        .await
        .unwrap()
        .id
    }

    fn payload(pairs: &[(&str, Json)]) -> Params {
        let mut p = Params::new();
        for (k, v) in pairs {
            p.insert((*k).into(), v.clone());
        }
        p
    }

    fn on_sale(filter: Json) -> Json {
        json!({
            "schema_version": 1,
            "triggers": [{ "kind": "event", "event": "sale.completed", "filter": filter }],
            "steps": [{ "id": "wait", "kind": "delay", "seconds": 1 }]
        })
    }

    async fn run_count(db: &dyn DatabaseAdapter, flow_id: &str) -> i64 {
        let mut p = Params::new();
        p.insert("f".into(), json!(flow_id));
        db.query("SELECT COUNT(*) AS c FROM _flow_runs WHERE flow_id = :f", &p)
            .await
            .unwrap()
            .rows[0]["c"]
            .as_i64()
            .unwrap_or(-1)
    }

    #[tokio::test]
    async fn a_matching_event_inserts_exactly_one_run_however_many_times_it_is_delivered() {
        let db = db().await;
        let flow = flow_with(&db, on_sale(json!({}))).await;

        let p = payload(&[("total", json!("120.50"))]);
        assert_eq!(
            on_event(&db, HUB, "evt-1", "sale.completed", &p, 0).await.unwrap(),
            1
        );
        // The relay is at-least-once: the same event WILL come back after a failed sibling
        // listener, and it must not start a second run.
        assert_eq!(
            on_event(&db, HUB, "evt-1", "sale.completed", &p, 0).await.unwrap(),
            0
        );
        assert_eq!(run_count(&db, &flow).await, 1);
    }

    #[tokio::test]
    async fn the_filter_decides_and_a_no_is_remembered() {
        let db = db().await;
        let flow = flow_with(&db, on_sale(json!({ "event.total": { "gte": "100" } }))).await;

        on_event(&db, HUB, "evt-small", "sale.completed", &payload(&[("total", json!("9.90"))]), 0)
            .await
            .unwrap();
        assert_eq!(run_count(&db, &flow).await, 0, "below the threshold: no run");

        on_event(&db, HUB, "evt-big", "sale.completed", &payload(&[("total", json!("120.50"))]), 0)
            .await
            .unwrap();
        assert_eq!(run_count(&db, &flow).await, 1);
    }

    #[tokio::test]
    async fn the_input_map_shapes_the_run_input_and_an_empty_one_passes_the_event_through() {
        let db = db().await;
        let mapped = flow_with(
            &db,
            json!({
                "schema_version": 1,
                "triggers": [{
                    "kind": "event", "event": "sale.completed",
                    "input": { "who": "event.customer_id", "note": "sale {{event.id}}" }
                }],
                "steps": [{ "id": "wait", "kind": "delay", "seconds": 1 }]
            }),
        )
        .await;
        let plain = flow_with(&db, on_sale(json!({}))).await;

        let p = payload(&[("customer_id", json!("c-1")), ("id", json!("s-9"))]);
        on_event(&db, HUB, "evt-1", "sale.completed", &p, 0).await.unwrap();

        let runs = store::list_runs(&db, HUB, &mapped, 10, None).await.unwrap();
        assert_eq!(runs[0].input, json!({ "who": "c-1", "note": "sale s-9" }));

        let runs = store::list_runs(&db, HUB, &plain, 10, None).await.unwrap();
        assert_eq!(
            runs[0].input,
            json!({ "customer_id": "c-1", "id": "s-9" }),
            "no mapping written means the whole event, not an empty input"
        );
    }

    #[tokio::test]
    async fn a_disabled_or_deleted_flow_reacts_to_nothing() {
        let db = db().await;
        let flow = flow_with(&db, on_sale(json!({}))).await;
        store::update(
            &db,
            HUB,
            &flow,
            &crate::registry::Registry::new(),
            &NewFlow {
                name: "T".into(),
                enabled: false,
                definition: on_sale(json!({})),
            },
            "hub_user:1",
        )
        .await
        .unwrap();

        on_event(&db, HUB, "evt-1", "sale.completed", &payload(&[]), 0).await.unwrap();
        assert_eq!(run_count(&db, &flow).await, 0);

        let other = flow_with(&db, on_sale(json!({}))).await;
        store::delete(&db, HUB, &other, "hub_user:1").await.unwrap();
        on_event(&db, HUB, "evt-2", "sale.completed", &payload(&[]), 0).await.unwrap();
        assert_eq!(run_count(&db, &other).await, 0);
    }

    #[tokio::test]
    async fn an_event_from_another_hub_never_starts_a_run_here() {
        let db = db().await;
        let flow = flow_with(&db, on_sale(json!({}))).await;
        on_event(&db, "hub-other", "evt-1", "sale.completed", &payload(&[]), 0)
            .await
            .unwrap();
        assert_eq!(run_count(&db, &flow).await, 0);
    }

    #[tokio::test]
    async fn a_cascade_that_went_deep_enough_stops_starting_flows() {
        let db = db().await;
        let flow = flow_with(&db, on_sale(json!({}))).await;
        let started = on_event(
            &db,
            HUB,
            "evt-deep",
            "sale.completed",
            &payload(&[]),
            MAX_EVENT_DEPTH,
        )
        .await
        .unwrap();
        assert_eq!(started, 0, "guard 1: depth");
        assert_eq!(run_count(&db, &flow).await, 0);
    }

    #[tokio::test]
    async fn a_flow_that_triggers_itself_is_capped_instead_of_taking_the_hub_down() {
        let db = db().await;
        let flow = flow_with(&db, on_sale(json!({}))).await;
        // Every event is a different id, so idempotence does not save us here — only the rate
        // guard does. This is the shape of a flow whose own command emits its own trigger.
        for i in 0..(MAX_RUNS_PER_MINUTE + 10) {
            on_event(&db, HUB, &format!("evt-{i}"), "sale.completed", &payload(&[]), 0)
                .await
                .unwrap();
        }
        assert_eq!(
            run_count(&db, &flow).await,
            MAX_RUNS_PER_MINUTE,
            "guard 2: the flow stops, the hub keeps working"
        );
    }

    #[tokio::test]
    async fn an_at_trigger_fires_once_and_disarms_itself() {
        let db = db().await;
        let flow = flow_with(
            &db,
            json!({
                "schema_version": 1,
                "triggers": [{ "kind": "at", "at": "2020-01-01T00:00:00+00:00" }],
                "steps": [{ "id": "wait", "kind": "delay", "seconds": 1 }]
            }),
        )
        .await;

        assert_eq!(sweep_schedules(&db, HUB).await.unwrap(), 1);
        assert_eq!(sweep_schedules(&db, HUB).await.unwrap(), 0, "one-shot");
        assert_eq!(run_count(&db, &flow).await, 1);
    }

    #[tokio::test]
    async fn a_cron_trigger_fires_and_moves_to_its_next_occurrence() {
        let db = db().await;
        let flow = flow_with(
            &db,
            json!({
                "schema_version": 1,
                "triggers": [{ "kind": "cron", "cron": "*/5 * * * *" }],
                "steps": [{ "id": "wait", "kind": "delay", "seconds": 1 }]
            }),
        )
        .await;
        // Pull the clock back so the trigger is due right now, the way a hub that was off is.
        let mut p = Params::new();
        p.insert("f".into(), json!(flow));
        db.execute(
            "UPDATE _flow_triggers SET next_run = '2020-01-01T00:00:00+00:00' WHERE flow_id = :f",
            &p,
        )
        .await
        .unwrap();

        assert_eq!(sweep_schedules(&db, HUB).await.unwrap(), 1);
        assert_eq!(sweep_schedules(&db, HUB).await.unwrap(), 0, "no double fire");

        let next = db
            .query("SELECT next_run FROM _flow_triggers WHERE flow_id = :f", &p)
            .await
            .unwrap()
            .rows[0]["next_run"]
            .as_str()
            .unwrap()
            .to_string();
        assert!(
            next > now_rfc3339(),
            "the backlog collapses forward, it does not replay: {next}"
        );
    }

    // ── The business clock (hub#731) ──────────────────────────────────────────────────────────
    //
    // `Asia/Kolkata` (+05:30, no DST ever) is the fixture on purpose: the assertion is the same
    // whatever day the suite runs, and the half hour makes an accidental "it was UTC all along"
    // impossible to mistake for a rounding.

    async fn trigger_row(db: &dyn DatabaseAdapter, flow: &str, col: &str) -> String {
        let mut p = Params::new();
        p.insert("f".into(), json!(flow));
        db.query(
            &format!("SELECT {col} AS v FROM _flow_triggers WHERE flow_id = :f"),
            &p,
        )
        .await
        .unwrap()
        .rows[0]["v"]
            .as_str()
            .unwrap_or_default()
            .to_string()
    }

    async fn set_zone(db: &dyn DatabaseAdapter, zone: &str) {
        let mut updates = serde_json::Map::new();
        updates.insert("timezone".into(), json!(zone));
        crate::settings::set_many(db, HUB, &updates, "hub_user:1", false)
            .await
            .unwrap();
    }

    #[tokio::test]
    async fn a_cron_trigger_is_armed_on_the_business_clock_not_on_utc() {
        let db = db().await;
        set_zone(&db, "Asia/Kolkata").await;
        let flow = flow_with(
            &db,
            json!({
                "schema_version": 1,
                "triggers": [{ "kind": "cron", "cron": "0 9 * * *" }],
                "steps": [{ "id": "wait", "kind": "delay", "seconds": 1 }]
            }),
        )
        .await;
        // 09:00 in the shop is 03:30 UTC. Stored UTC, because `next_run <= :now` is a TEXT
        // comparison and an offset in the string would sort as a different instant.
        let next = trigger_row(&db, &flow, "next_run").await;
        assert!(next.ends_with("T03:30:00+00:00"), "got {next}");
        assert_eq!(trigger_row(&db, &flow, "tz").await, "Asia/Kolkata");
    }

    #[tokio::test]
    async fn moving_the_business_to_another_zone_retimes_what_is_already_armed() {
        let db = db().await;
        let flow = flow_with(
            &db,
            json!({
                "schema_version": 1,
                "triggers": [{ "kind": "cron", "cron": "0 9 * * *" }],
                "steps": [{ "id": "wait", "kind": "delay", "seconds": 1 }]
            }),
        )
        .await;
        // Armed as a Spanish hub (the default `country_code`), so 09:00 Madrid.
        let before = trigger_row(&db, &flow, "next_run").await;
        assert!(
            before.ends_with("T07:00:00+00:00") || before.ends_with("T08:00:00+00:00"),
            "09:00 in Madrid is 07:00Z (CEST) or 08:00Z (CET): {before}"
        );

        set_zone(&db, "Asia/Kolkata").await;
        // The sweep is self-healing: a trigger whose `next_run` was computed under another zone
        // is re-armed on the next tick. Nobody has to re-save the flow, and this is also what
        // migrates the triggers that were armed in UTC before this fix.
        sweep_schedules(&db, HUB).await.unwrap();
        let after = trigger_row(&db, &flow, "next_run").await;
        assert!(after.ends_with("T03:30:00+00:00"), "got {after}");

        // …and it is a ONE-OFF: a second sweep must not keep moving the clock forward.
        sweep_schedules(&db, HUB).await.unwrap();
        assert_eq!(trigger_row(&db, &flow, "next_run").await, after);
    }

    #[tokio::test]
    async fn firing_advances_on_the_business_clock_too() {
        let db = db().await;
        set_zone(&db, "Asia/Kolkata").await;
        let flow = flow_with(
            &db,
            json!({
                "schema_version": 1,
                "triggers": [{ "kind": "cron", "cron": "0 9 * * *" }],
                "steps": [{ "id": "wait", "kind": "delay", "seconds": 1 }]
            }),
        )
        .await;
        let mut p = Params::new();
        p.insert("f".into(), json!(flow));
        db.execute(
            "UPDATE _flow_triggers SET next_run = '2020-01-01T00:00:00+00:00' WHERE flow_id = :f",
            &p,
        )
        .await
        .unwrap();

        assert_eq!(sweep_schedules(&db, HUB).await.unwrap(), 1);
        let next = trigger_row(&db, &flow, "next_run").await;
        assert!(next.ends_with("T03:30:00+00:00"), "advancing keeps the zone: {next}");
    }
}
