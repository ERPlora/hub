//! **The fiscal mode reaches the boot and the dispatcher** — ADR-0259 D2/D4, hub#550.
//!
//! The state machine itself is unit-tested in `fiscal_profile.rs`, where a `Registry` can be built
//! by hand. What this fixes is the part that only shows up assembled: that a real hub, booting the
//! way the server boots one, ends up with a mode — and that the mode a hub with nothing installed
//! is in is the one that says so.
//!
//! Nothing here rejects anything: that is hub#556.
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::fiscal_profile::{BlockedReason, FiscalMode, FiscalStatus};
use erplora_runtime::Runtime;
use serde_json::json;

async fn hub(hub_id: &str, country: &str) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("value".into(), json!(country));
    p.insert("now".into(), json!("2026-08-08T10:00:00Z"));
    rt.db()
        .execute(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at) \
             VALUES (:hub_id, 'country_code', :value, :now) \
             ON CONFLICT (hub_id, key) DO UPDATE SET value = EXCLUDED.value",
            &p,
        )
        .await
        .unwrap();
    rt
}

/// Forces the stored status, the way the go-live command (hub#551) will.
async fn force_status(rt: &Runtime, hub_id: &str, status: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(status));
    rt.db()
        .execute(
            "UPDATE _hub_fiscal_profile SET status = :status WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
}

/// A Spanish hub with nothing installed owes VeriFactu and is **not configured**. It is not
/// blocked: it never went live, so there is nothing to protect yet.
#[tokio::test]
async fn a_spanish_hub_with_nothing_installed_is_unconfigured() {
    let rt = hub("hub-es", "ES").await;
    assert_eq!(rt.fiscal_mode().await.unwrap(), FiscalMode::Unconfigured);
}

/// A hub in a country with no regime owes nothing — and that is the default, so Spain is never
/// shipped to a hub that does not owe it.
#[tokio::test]
async fn a_hub_with_no_regime_is_not_required() {
    let rt = hub("hub-pt", "PT").await;
    assert_eq!(rt.fiscal_mode().await.unwrap(), FiscalMode::NotRequired);
}

/// 🔴 **The core case of the whole ADR.** The hub went live and then the provider went away — it
/// was uninstalled, or failed to mount after a restore, or a bug left it inactive. The stored
/// status still says `ACTIVE` and must not be believed: with nobody left to generate the record,
/// the hub reads `BLOCKED`.
///
/// R2 (hub#314) does not cover this. It only looks at the pending queue, and an empty queue lets
/// the module leave without a word.
#[tokio::test]
async fn an_active_hub_with_no_provider_mounted_reads_blocked() {
    let rt = hub("hub-es", "ES").await;
    force_status(&rt, "hub-es", "ACTIVE").await;

    assert_eq!(
        rt.fiscal_mode().await.unwrap(),
        FiscalMode::Blocked(BlockedReason::ProviderMissing),
        "ACTIVE with nobody complying is not ACTIVE"
    );
}

/// **`BLOCKED` is never written down.** The row still says `ACTIVE`; only the reading is blocked.
/// That is what makes it repairable by fixing the fact instead of by editing a row — and what stops
/// a bad state from outliving the bug that produced it.
#[tokio::test]
async fn blocked_is_derived_and_never_persisted() {
    let rt = hub("hub-es", "ES").await;
    force_status(&rt, "hub-es", "ACTIVE").await;
    assert!(matches!(
        rt.fiscal_mode().await.unwrap(),
        FiscalMode::Blocked(_)
    ));

    assert_eq!(
        rt.fiscal_profile().await.unwrap().unwrap().status,
        FiscalStatus::Active,
        "the row keeps saying ACTIVE: BLOCKED is a reading, not something anybody wrote"
    );
    let rows = rt
        .db()
        .query(
            "SELECT status FROM _hub_fiscal_profile WHERE status = 'BLOCKED'",
            &Params::new(),
        )
        .await
        .unwrap();
    assert!(rows.rows.is_empty(), "`BLOCKED` is not a storable status");
}

/// The mode reaches the boot: `refresh_fiscal_profile` is what the server calls once the registry
/// has been rehydrated, and it is idempotent — it runs on every start and every redeploy.
#[tokio::test]
async fn refreshing_on_boot_is_idempotent() {
    let rt = hub("hub-es", "ES").await;

    let first = rt.refresh_fiscal_profile().await.unwrap();
    let second = rt.refresh_fiscal_profile().await.unwrap();

    assert_eq!(first, second);
    assert_eq!(first, FiscalMode::Unconfigured);
}
