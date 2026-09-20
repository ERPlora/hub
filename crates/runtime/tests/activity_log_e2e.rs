//! **The buffer of business activity survives the process** (saas#2129).
//!
//! The data these events carry cannot be reconstructed afterwards — what October does not record
//! is lost — and with `order: start-first` (ADR-0269) every update kills a task. So the contract
//! under test is not "the function works": it is that a sale recorded at 11:02 still reaches the
//! Cloud after a deploy at 11:03, that a heartbeat that never arrives does not take it with it,
//! and that a hub cut off from the Cloud for months does not fill its own disk trying.

use erplora_db::testutil::fresh_db;
use erplora_runtime::activity_log::{self, Kind};
use erplora_runtime::Runtime;

const HUB: &str = "hub-activity";

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn record(rt: &Runtime, hub_id: &str, kind: Kind, actor: &str, at: &str) {
    activity_log::record(rt.db(), hub_id, kind, actor, at)
        .await
        .unwrap();
}

#[tokio::test]
async fn an_event_waits_in_the_database_until_the_cloud_confirms_it() {
    let rt = runtime(HUB).await;

    record(&rt, HUB, Kind::CashOpen, "ana", "2026-10-01T09:00:00Z").await;
    record(&rt, HUB, Kind::Sale, "ana", "2026-10-01T09:05:00Z").await;

    let pending = activity_log::pending(rt.db(), HUB, 10).await.unwrap();
    assert_eq!(pending.len(), 2);
    assert_eq!(pending[0].kind, "cash_open", "oldest first");
    assert_eq!(pending[0].actor, "ana");
    assert_eq!(pending[0].occurred_at, "2026-10-01T09:00:00Z");
    assert!(!pending[0].id.is_empty(), "the hub mints the dedup key");
    assert_ne!(pending[0].id, pending[1].id, "one id per event");

    // Reading is not confirming: a beat that never arrives must leave them where they are.
    let again = activity_log::pending(rt.db(), HUB, 10).await.unwrap();
    assert_eq!(again.len(), 2, "a read does not consume");

    let ids: Vec<String> = pending.iter().map(|e| e.id.clone()).collect();
    assert_eq!(activity_log::confirm(rt.db(), HUB, &ids).await.unwrap(), 2);
    assert!(activity_log::pending(rt.db(), HUB, 10)
        .await
        .unwrap()
        .is_empty());
}

/// The reason this is a table and not an atomic: `order: start-first` kills a task on every
/// update, and a sale between the last beat and the deploy would otherwise never be reported.
#[tokio::test]
async fn what_the_previous_process_recorded_is_still_there_after_a_restart() {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let first = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB);
    first.ensure_system_tables().await.unwrap();
    record(&first, HUB, Kind::Sale, "ana", "2026-10-01T11:02:00Z").await;
    drop(first);

    let second = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB);
    second.ensure_system_tables().await.unwrap();

    let pending = activity_log::pending(second.db(), HUB, 10).await.unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].kind, "sale");
}

#[tokio::test]
async fn a_beat_takes_a_bounded_bite_and_the_rest_waits_its_turn() {
    let rt = runtime(HUB).await;
    for minute in 0..5 {
        record(
            &rt,
            HUB,
            Kind::Sale,
            "ana",
            &format!("2026-10-01T09:{minute:02}:00Z"),
        )
        .await;
    }

    let first = activity_log::pending(rt.db(), HUB, 2).await.unwrap();
    assert_eq!(first.len(), 2);
    assert_eq!(first[0].occurred_at, "2026-10-01T09:00:00Z");

    let ids: Vec<String> = first.iter().map(|e| e.id.clone()).collect();
    activity_log::confirm(rt.db(), HUB, &ids).await.unwrap();

    let next = activity_log::pending(rt.db(), HUB, 2).await.unwrap();
    assert_eq!(next[0].occurred_at, "2026-10-01T09:02:00Z", "carries on");
}

/// Tenancy. A legacy shared database holds more than one hub, and a hub reporting the business
/// next door's work as its own would answer the question wrongly for both.
#[tokio::test]
async fn one_hub_never_reports_another_hubs_work() {
    let rt = runtime("hub-a").await;

    record(&rt, "hub-a", Kind::Sale, "ana", "2026-10-01T09:00:00Z").await;
    record(&rt, "hub-b", Kind::Sale, "bea", "2026-10-01T09:01:00Z").await;

    let mine = activity_log::pending(rt.db(), "hub-a", 10).await.unwrap();
    assert_eq!(mine.len(), 1);
    assert_eq!(mine[0].actor, "ana");

    // And confirming mine leaves the neighbour's alone.
    let ids: Vec<String> = mine.iter().map(|e| e.id.clone()).collect();
    activity_log::confirm(rt.db(), "hub-a", &ids).await.unwrap();
    assert_eq!(
        activity_log::pending(rt.db(), "hub-b", 10)
            .await
            .unwrap()
            .len(),
        1
    );
}

/// A hub that cannot reach the Cloud for months must not fill its own disk with telemetry. The
/// OLDEST go, because the recent days are the ones the question is about.
#[tokio::test]
async fn a_buffer_that_never_drains_is_capped_from_the_old_end() {
    let rt = runtime(HUB).await;
    for minute in 0..6 {
        record(
            &rt,
            HUB,
            Kind::Sale,
            "ana",
            &format!("2026-10-01T09:{minute:02}:00Z"),
        )
        .await;
    }

    assert_eq!(activity_log::trim(rt.db(), HUB, 3).await.unwrap(), 3);

    let left = activity_log::pending(rt.db(), HUB, 10).await.unwrap();
    assert_eq!(left.len(), 3);
    assert_eq!(
        left[0].occurred_at, "2026-10-01T09:03:00Z",
        "the three most recent survive"
    );
}

/// Confirming is exact: the Cloud may acknowledge a bite while a later sale is already buffered,
/// and that sale has to still be there on the next beat.
#[tokio::test]
async fn confirming_deletes_only_what_was_named() {
    let rt = runtime(HUB).await;
    record(&rt, HUB, Kind::Login, "ana", "2026-10-01T08:00:00Z").await;
    record(&rt, HUB, Kind::Sale, "ana", "2026-10-01T09:00:00Z").await;

    let first = activity_log::pending(rt.db(), HUB, 1).await.unwrap();
    activity_log::confirm(rt.db(), HUB, &[first[0].id.clone()])
        .await
        .unwrap();

    let left = activity_log::pending(rt.db(), HUB, 10).await.unwrap();
    assert_eq!(left.len(), 1);
    assert_eq!(left[0].kind, "sale");
}

// ── The dispatcher hook ───────────────────────────────────────────────────────────────────────
//
// The mapping table is unit-tested next to itself; what these pin is that the dispatcher ACTUALLY
// calls it. Without them, deleting the hook from `execute_command` leaves every other test in the
// suite green — and the hub stops recording the thing this whole feature exists for, silently.

use erplora_db::Params;
use erplora_runtime::RequestContext;

/// A stand-in for the real `sales` module: same command names, no business logic. What is under
/// test is the dispatcher, not the till.
async fn hub_with_a_sales_module() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.ensure_system_tables().await.unwrap();

    let dir = std::env::temp_dir().join(format!("erplora-activity-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(dir.join("commands")).unwrap();
    std::fs::write(
        dir.join("commands/noop.sql"),
        "INSERT INTO sales_marker (hub_id, id) VALUES (:hub_id, :id)",
    )
    .unwrap();
    std::fs::create_dir_all(dir.join("migrations/postgres")).unwrap();
    std::fs::write(
        dir.join("migrations/postgres/001_init.sql"),
        "CREATE TABLE IF NOT EXISTS sales_marker (hub_id TEXT NOT NULL, id TEXT NOT NULL);",
    )
    .unwrap();
    std::fs::write(
        dir.join("module.json"),
        r#"{
  "id": "sales",
  "name": "Sales",
  "version": "1.0.0",
  "permissions": ["sales.take_payment"],
  "role_permissions": { "admin": ["*"], "employee": ["sales.take_payment"] },
  "navigation": [],
  "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
  "queries": {},
  "commands": {
    "sales.complete_sale": { "permission": "sales.take_payment", "transaction": true, "sql": ["commands/noop.sql"] },
    "sales._insert_sale": { "permission": "sales.take_payment", "transaction": true, "sql": ["commands/noop.sql"] },
    "sales.order.add_line": { "permission": "sales.take_payment", "transaction": true, "sql": ["commands/noop.sql"] }
  }
}"#,
    )
    .unwrap();
    rt.install_from_dir(&dir).await.expect("sales installs");
    std::fs::remove_dir_all(dir).unwrap();
    rt
}

fn cashier() -> RequestContext {
    RequestContext::new("h1", "pin-42", ["sales.take_payment".to_string()])
}

fn payload() -> Params {
    let mut p = Params::new();
    p.insert(
        "id".into(),
        serde_json::json!(uuid::Uuid::new_v4().to_string()),
    );
    p
}

#[tokio::test]
async fn completing_a_sale_records_who_sold_it() {
    let rt = hub_with_a_sales_module().await;

    rt.execute_command("sales.complete_sale", &payload(), &cashier())
        .await
        .expect("the sale goes through");

    let events = activity_log::pending(rt.db(), "h1", 10).await.unwrap();
    assert_eq!(events.len(), 1, "one sale, one event: {events:?}");
    assert_eq!(events[0].kind, "sale");
    assert_eq!(
        events[0].actor, "pin-42",
        "the hub's own id for the cashier"
    );
}

/// The count is the answer this feature gives, so counting one sale as several would be worse
/// than not counting it. The internal relays of a sale run inside the very same operation.
#[tokio::test]
async fn the_internal_relay_of_a_sale_is_not_a_second_sale() {
    let rt = hub_with_a_sales_module().await;

    rt.execute_command_internal("sales._insert_sale", &payload(), &cashier())
        .await
        .expect("the relay runs");
    rt.execute_command("sales.order.add_line", &payload(), &cashier())
        .await
        .expect("adding a line runs");

    assert!(
        activity_log::pending(rt.db(), "h1", 10)
            .await
            .unwrap()
            .is_empty(),
        "neither a relay nor an ordinary command is business activity"
    );
}

/// A refused sale is not a sale. Recording the attempt would report a busy day to a hub whose
/// till was rejecting everything — the opposite of the truth being asked for.
#[tokio::test]
async fn a_command_that_was_refused_records_nothing() {
    let rt = hub_with_a_sales_module().await;
    let nobody = RequestContext::new("h1", "pin-42", []);

    let refused = rt
        .execute_command("sales.complete_sale", &payload(), &nobody)
        .await;

    assert!(refused.is_err(), "no permission, no sale");
    assert!(activity_log::pending(rt.db(), "h1", 10)
        .await
        .unwrap()
        .is_empty());
}

// ── Signing in and out ────────────────────────────────────────────────────────────────────────
//
// Hooked at `create_session_with_credential` / `delete_session`, the one funnel every door goes
// through (PIN, badge, cloud, courier). Same reasoning as the single `track_user_activity`
// middleware: hanging it off each door desynchronises the moment somebody adds the next one.

#[tokio::test]
async fn signing_in_and_out_is_recorded_against_the_person_who_did_it() {
    let rt = runtime(HUB).await;

    let token = rt
        .create_session("pin-42", 3600, Some("till-1"))
        .await
        .unwrap();
    rt.delete_session(&token).await.unwrap();

    let events = activity_log::pending(rt.db(), HUB, 10).await.unwrap();
    assert_eq!(
        events.iter().map(|e| e.kind.as_str()).collect::<Vec<_>>(),
        ["login", "logout"],
        "{events:?}"
    );
    assert!(events.iter().all(|e| e.actor == "pin-42"), "{events:?}");
}

/// The logout has to read WHO is leaving before the session row goes: afterwards there is nothing
/// left to attribute it to, and the Cloud drops an event with no actor.
#[tokio::test]
async fn logging_out_a_token_nobody_holds_records_nothing() {
    let rt = runtime(HUB).await;

    rt.delete_session("a-token-that-never-existed")
        .await
        .unwrap();

    assert!(activity_log::pending(rt.db(), HUB, 10)
        .await
        .unwrap()
        .is_empty());
}

/// A login is recorded only once the session EXISTS (review of saas#2129).
///
/// Recorded before the insert, a failed insert left behind a login that never happened — and the
/// Cloud would count that hub as used by somebody who never got in. The failure is injected the
/// only honest way: take the table away and watch `create_session` fail for real.
#[tokio::test]
async fn a_login_whose_session_could_not_be_opened_is_not_recorded() {
    let rt = runtime(HUB).await;
    rt.db()
        .execute("DROP TABLE hub_session", &Params::new())
        .await
        .expect("la tabla existía");

    let opened = rt.create_session("pin-42", 3600, Some("till-1")).await;

    assert!(opened.is_err(), "sin tabla no hay sesión que abrir");
    assert!(
        activity_log::pending(rt.db(), HUB, 10)
            .await
            .unwrap()
            .is_empty(),
        "un login que no llegó a ocurrir no se registra"
    );
}
