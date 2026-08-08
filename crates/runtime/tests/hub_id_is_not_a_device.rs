//! **The hub's own id is not a device** (hub#454).
//!
//! Until this, a browser presented the `hub_id` as its `X-Device-Id`, so every browser in the world
//! was one single device: one row in `hub_trusted_device` covered all of them, marking the owner's
//! laptop `personal` took the pinpad off the till at the counter (hub#358), and the long session
//! that comes with `personal` was handed to whoever asked. The web now mints an identity per
//! browser — but that leaves this side with two jobs the client cannot do for it:
//!
//!  1. **The rows already out there.** Deployed hubs carry a `hub_trusted_device` row keyed on
//!     their own id, possibly marked `personal`. That id is *published*: `GET /api/hub/context`
//!     takes no session. A trusted, lax row keyed on a value anyone can fetch is the escalation
//!     this issue is about, and it does not go away by fixing the client.
//!  2. **The clients still out there.** A browser holding a cached build keeps presenting the old
//!     value after the deploy, so the row would simply be written again on the next online login.
//!
//! Hence the invariant, enforced here and not merely migrated once: an id that names the hub names
//! no device. It is refused on the way in, answered strictly on the way out, and swept from the
//! table on every boot — which also covers a database restored from a backup taken before today.
//!
//! What this is NOT: a claim that device ids are credentials. They are not, before or after. This
//! only removes the one id that was *shared and public*.
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::device_mode::DeviceMode;
use erplora_runtime::Runtime;

/// The id of the hub under test. Public knowledge: the shell reads it from `/api/hub/context`.
const HUB_ID: &str = "e5f1c0de-0000-4000-8000-000000000042";

/// The stable rejection code of a refused write, or the raw message when it was something else.
fn code_of(error: &erplora_runtime::RuntimeError) -> String {
    match error {
        erplora_runtime::RuntimeError::Domain { code, .. } => code.clone(),
        other => other.to_string(),
    }
}

/// Rows of `hub_trusted_device` as `(hub_id, device_id, label, mode)`, ordered — the whole table,
/// across every tenant in the database, so a test can assert both what went and what stayed.
///
/// The owning hub is part of the tuple since hub#489 gave the table its tenant column: the sweep
/// below is scoped by it, and a test that could not see it could not tell "A swept its own row"
/// from "A swept every row that named A's id".
async fn devices(db: &dyn DatabaseAdapter) -> Vec<(String, String, String, String)> {
    let res = db
        .query(
            "SELECT hub_id, device_id, label, mode FROM hub_trusted_device \
              ORDER BY hub_id, device_id",
            &Params::new(),
        )
        .await
        .unwrap();
    res.rows
        .iter()
        .map(|r| {
            (
                r["hub_id"].as_str().unwrap_or_default().to_string(),
                r["device_id"].as_str().unwrap_or_default().to_string(),
                r["label"].as_str().unwrap_or_default().to_string(),
                r["mode"].as_str().unwrap_or_default().to_string(),
            )
        })
        .collect()
}

/// The state a hub deployed before hub#454 is actually in: a real till that earned its trust and
/// its mode, plus the row the shared browser identity left behind — keyed on the hub's own id and
/// marked `personal`, which is what took the pinpad off everything at once.
async fn a_hub_deployed_before_this_fix(db: &dyn DatabaseAdapter) {
    db.execute_batch(&format!(
        "INSERT INTO hub_trusted_device (hub_id, device_id, label, trusted_at, mode, mode_set_at, mode_set_by) \
           VALUES ('{HUB_ID}', 'till-1', 'Counter till', '2026-08-01T09:00:00Z', 'shared', '', '');\
         INSERT INTO hub_trusted_device (hub_id, device_id, label, trusted_at, mode, mode_set_at, mode_set_by) \
           VALUES ('{HUB_ID}', '{HUB_ID}', 'Marta Ruiz', '2026-08-02T10:00:00Z', 'personal', \
                   '2026-08-02T11:00:00Z', 'hub_user:admin');"
    ))
    .await
    .unwrap();
}

#[tokio::test]
async fn booting_sweeps_the_row_the_shared_identity_left_behind_and_touches_nothing_else() {
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let db = test_db.adapter().await;
    a_hub_deployed_before_this_fix(&db).await;

    // The redeploy that carries this change.
    rt.ensure_system_tables().await.unwrap();

    assert_eq!(
        devices(&db).await,
        vec![(
            HUB_ID.to_string(),
            "till-1".to_string(),
            "Counter till".to_string(),
            "shared".to_string()
        )],
        "the hub's own id is gone; the real till — alive, trusted, with its own mode — is untouched"
    );
}

#[tokio::test]
async fn one_hub_sweeping_its_own_id_does_not_touch_another_hub_sharing_the_database() {
    // `hub_trusted_device` is keyed by `device_id` alone, so in a database shared by several hubs
    // (the pre-ADR-0201 shape, still out there) the table is common ground. Hub A booting must
    // remove exactly one row: its own. Hub B's legacy row is B's to sweep when B boots.
    let test_db = TestDb::new().await;
    let hub_a = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-a");
    hub_a.ensure_system_tables().await.unwrap();
    let db = test_db.adapter().await;
    db.execute_batch(
        "INSERT INTO hub_trusted_device (hub_id, device_id, label, trusted_at, mode, mode_set_at, mode_set_by) \
           VALUES ('hub-a', 'hub-a', 'Legacy of A', '2026-08-01T09:00:00Z', 'personal', '', '');\
         INSERT INTO hub_trusted_device (hub_id, device_id, label, trusted_at, mode, mode_set_at, mode_set_by) \
           VALUES ('hub-b', 'hub-b', 'Legacy of B', '2026-08-01T09:00:00Z', 'personal', '', '');\
         INSERT INTO hub_trusted_device (hub_id, device_id, label, trusted_at, mode, mode_set_at, mode_set_by) \
           VALUES ('hub-b', 'till-of-b', 'Till of B', '2026-08-01T09:00:00Z', 'personal', '', '');",
    )
    .await
    .unwrap();

    hub_a.ensure_system_tables().await.unwrap();

    assert_eq!(
        devices(&db).await,
        vec![
            ("hub-b".to_string(), "hub-b".to_string(), "Legacy of B".to_string(), "personal".to_string()),
            ("hub-b".to_string(), "till-of-b".to_string(), "Till of B".to_string(), "personal".to_string()),
        ],
        "A swept A's row and nothing of B's — not its legacy row, not its personal till"
    );
}

#[tokio::test]
async fn a_stale_client_presenting_the_hub_id_never_becomes_a_trusted_device() {
    // A browser with a cached build keeps sending the old value after the deploy, and every
    // successful online login re-marks the device it names. If that wrote the row again, the sweep
    // above would be undone by the first person to sign in.
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let db = test_db.adapter().await;
    rt.trust_device("till-1", "Counter till").await.unwrap();

    rt.trust_device(HUB_ID, "Marta Ruiz").await.unwrap();

    assert!(
        !rt.is_device_trusted(HUB_ID).await.unwrap(),
        "naming the hub does not name a device, so there is nothing to trust"
    );
    assert!(
        rt.is_device_trusted("till-1").await.unwrap(),
        "and the real device the same call shape trusts is unaffected"
    );
    assert_eq!(
        devices(&db).await,
        vec![(
            HUB_ID.to_string(),
            "till-1".to_string(),
            "Counter till".to_string(),
            "shared".to_string()
        )],
        "no row was written for the hub's own id"
    );
}

#[tokio::test]
async fn a_legacy_row_still_standing_grants_neither_the_lax_mode_nor_the_long_session() {
    // The database restored from a backup taken before today, or read between the write and the
    // next boot. The row says `personal`; the answer is the strict mode all the same, because what
    // decides is that the id names the hub — not what some row happens to hold.
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let db = test_db.adapter().await;
    a_hub_deployed_before_this_fix(&db).await;

    assert_eq!(
        rt.device_mode(HUB_ID).await.unwrap(),
        DeviceMode::Shared,
        "the pinpad stays: a row keyed on a public value must not take it off"
    );
    assert!(!rt.is_device_trusted(HUB_ID).await.unwrap());
    assert_eq!(
        rt.session_ttl_for_device(HUB_ID).await.unwrap(),
        DeviceMode::Shared.session_ttl_secs(),
        "and the session is the short one: the long one is what `personal` was buying"
    );
}

#[tokio::test]
async fn an_administrator_cannot_mark_the_hub_itself_personal() {
    // The gesture is «this device is mine», sent from the device itself. A client that names the
    // hub is describing no device, and the answer is the one the admin can act on: sign in on it
    // once. Nothing is written — least of all to a row a stale client may still be presenting.
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let db = test_db.adapter().await;
    a_hub_deployed_before_this_fix(&db).await;

    let refused = rt
        .set_device_mode(HUB_ID, DeviceMode::Shared, "hub_user:admin")
        .await
        .expect_err("the hub is not one of its own devices");

    assert_eq!(code_of(&refused), "hub.device.unknown_device");
    assert_eq!(
        devices(&db).await,
        vec![
            (HUB_ID.to_string(), HUB_ID.to_string(), "Marta Ruiz".to_string(), "personal".to_string()),
            (HUB_ID.to_string(), "till-1".to_string(), "Counter till".to_string(), "shared".to_string()),
        ],
        "a refused write changes nothing — not even the row it was aimed at"
    );
}
