//! hub#326 wire contract, exercised against the REAL verifactu engine — moved out of
//! `daily_usage.rs` by hub#1406: that module no longer knows any engine by name, so the
//! tests that deliberately name one live here. The seam they prove is the one the
//! registry uses in production: engine answer → wire report → heartbeat fields.

use erplora_runtime::native::PendingObligation;
use erplora_server::daily_usage::collect_daily_usage;
use erplora_db::testutil::fresh_db;
use erplora_db::DatabaseAdapter;
use serde_json::json;

/// The REAL engine, asked through the same trait door the registry uses
/// ([`erplora_runtime::native::NativeHandler::pending_obligations`]) — so these
/// tests keep proving the count against real tables, not a copy of the SQL.
async fn ask_verifactu_engine(
    db: &erplora_db::PgAdapter,
) -> erplora_runtime::Result<Option<PendingObligation>> {
    use erplora_runtime::native::NativeHandler;
    erplora_verifactu::VerifactuEngine
        .pending_obligations(
            "hub-a",
            &erplora_runtime::native::DbHost {
                db,
                storage: None,
                hub_id: "hub-a",
                module_id: "verifactu",
                static_folder: None,
            },
        )
        .await
}

async fn db_with_verifactu_records(records: &str) -> erplora_db::PgAdapter {
    let db = fresh_db().await;
    db.execute_batch(&format!(
        "CREATE TABLE sales_sale (\
           id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, status TEXT NOT NULL, \
           is_deleted BIGINT NOT NULL DEFAULT 0, created_at TEXT NOT NULL\
         );\
         CREATE TABLE hub_session (\
           token TEXT PRIMARY KEY, hub_id TEXT NOT NULL, device_id TEXT, expires_at TEXT NOT NULL\
         );\
         CREATE TABLE verifactu_record (\
           id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, status TEXT NOT NULL, \
           is_deleted BIGINT NOT NULL DEFAULT 0, created_at TEXT NOT NULL\
         );{records}"
    ))
    .await
    .unwrap();
    db
}

/// **The whole point of hub#326.** A hub that stopped remitting looks perfectly healthy from
/// the SaaS today: nothing in the heartbeat says how many records the AEAT is still missing,
/// nor for how long. Both travel now — the depth, and WHEN the oldest one got queued, which
/// is what separates a busy lunch service from a hub whose certificate expired last week.
#[tokio::test]
async fn the_heartbeat_carries_the_contingency_queue_depth_and_its_oldest_entry() {
    let db = db_with_verifactu_records(
        "INSERT INTO verifactu_record VALUES\
           ('r1', 'hub-a', 'pending', 0, '2026-08-01T09:00:00Z'),\
           ('r2', 'hub-a', 'retry', 0, '2026-08-03T10:00:00Z'),\
           ('r3', 'hub-a', 'error', 0, '2026-08-04T10:00:00Z'),\
           ('r4', 'hub-a', 'rejected', 0, '2026-08-05T10:00:00Z'),\
           ('sent', 'hub-a', 'accepted', 0, '2026-07-01T10:00:00Z'),\
           ('gone', 'hub-a', 'pending', 1, '2026-07-02T10:00:00Z'),\
           ('next-door', 'hub-b', 'pending', 0, '2026-06-01T10:00:00Z');",
    )
    .await;

    // The count comes from the ENGINE (the same query that blocks an uninstall,
    // hub#314), through the seam the registry uses: engine answer → wire report.
    let answer = ask_verifactu_engine(&db).await.expect("queue readable");
    let usage =
        collect_daily_usage(&db, "hub-a", "2026-08-08T10:00:00Z", &[("verifactu".into(), answer)])
            .await;
    let body = serde_json::to_value(&usage).unwrap();

    assert_eq!(
        body["verifactu_pending_depth"],
        json!(4),
        "the four states short of `accepted` are records the AEAT does not have; the accepted \
         one, the soft-deleted one and the neighbour hub's are not this hub's queue: {body}"
    );
    assert_eq!(
        body["verifactu_oldest_pending_at"],
        json!("2026-08-01T09:00:00Z"),
        "the SaaS decides what «stuck» means; the hub reports the wait it can measure: {body}"
    );
}

/// **An empty queue is an explicit `0`.** Same contract as `cert_version`: absent means «I
/// could not count it». If a drained hub simply said nothing, the fleet panel could not tell
/// it apart from one whose database it cannot read — which is the alert this issue exists for.
#[tokio::test]
async fn a_hub_that_owes_the_aeat_nothing_reports_an_explicit_zero() {
    let db = db_with_verifactu_records(
        "INSERT INTO verifactu_record VALUES\
           ('sent', 'hub-a', 'accepted', 0, '2026-07-01T10:00:00Z');",
    )
    .await;

    let answer = ask_verifactu_engine(&db).await.expect("queue readable");
    assert!(answer.is_none(), "an engine that owes nothing SAYS so (Ok(None))");
    let usage =
        collect_daily_usage(&db, "hub-a", "2026-08-08T10:00:00Z", &[("verifactu".into(), answer)])
            .await;
    let body = serde_json::to_value(&usage).unwrap();

    assert_eq!(body["verifactu_pending_depth"], json!(0));
    assert!(
        body.get("verifactu_oldest_pending_at").is_none(),
        "an empty queue has no oldest entry — a date here would be a wait nobody is doing: {body}"
    );
}

/// **No module, no number.** A hub without `verifactu` installed has no such table, and a
/// read that cannot happen is silence — never a fabricated `0`, which would tell the SaaS
/// that a queue it has never seen is under control.
#[tokio::test]
async fn a_hub_without_the_verifactu_module_says_nothing_instead_of_zero() {
    let db = fresh_db().await;
    db.execute_batch(
        "CREATE TABLE hub_session (\
           token TEXT PRIMARY KEY, hub_id TEXT NOT NULL, device_id TEXT, expires_at TEXT NOT NULL\
         );",
    )
    .await
    .unwrap();

    // Without the module its table does not exist: the ENGINE errs, so the registry
    // reports no entry at all — and an engine with no entry sends NOTHING.
    assert!(ask_verifactu_engine(&db).await.is_err(), "no table = no answer");
    let usage = collect_daily_usage(&db, "hub-a", "2026-08-08T10:00:00Z", &[]).await;
    let body = serde_json::to_value(&usage).unwrap();

    assert!(body.get("verifactu_pending_depth").is_none(), "{body}");
    assert!(body.get("verifactu_oldest_pending_at").is_none(), "{body}");
}

