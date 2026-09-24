//! **hub#2079 — «Production» only exists through the core's go-live.**
//!
//! The VeriFactu screen wrote `production` into the module's own `verifactu_config.environment`,
//! and the engine read its environment from there: real invoices reached the AEAT without passing
//! through `fiscal_profile::go_live` (the signed grant, the demo pin, the expired certificate), and
//! the core profile stayed in `testing`, so every till guard keyed on it stayed off.
//!
//! What this file pins, against a real Postgres:
//!  - the native host answers the engine's «which AEAT?» with the CORE profile's environment, before
//!    and after the go-live;
//!  - the one-off adoption of a hub that ALREADY went live through the old select: its profile is
//!    promoted to `production` (its records already reach the real AEAT, so leaving it in `testing`
//!    would send the next real invoices to the test agency), exactly once;
//!  - the adoption never promotes a demo, a closed hub, a hub whose module says `testing`, or a hub
//!    without the module's table — and a stand-down after it is not undone on the next boot.
#![cfg(not(target_os = "android"))]

use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::fiscal_profile::{self, FiscalStatus, ENV_PRODUCTION, ENV_TESTING};
use erplora_runtime::native::{DbHost, NativeHost};
use erplora_runtime::Runtime;
use serde_json::json;

const HUB: &str = "hub-2079";

async fn hub() -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    fiscal_profile::ensure(rt.db(), HUB).await.unwrap();
    rt
}

fn params() -> Params {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p
}

async fn exec(db: &dyn DatabaseAdapter, sql: &str) {
    db.execute(sql, &params()).await.unwrap();
}

/// The module's config row as the old select left it. The table is the module's; only the two
/// columns the adoption reads are needed here.
async fn module_config_saying(db: &dyn DatabaseAdapter, environment: &str) {
    exec(
        db,
        "CREATE TABLE IF NOT EXISTS verifactu_config (hub_id TEXT PRIMARY KEY, \
         environment TEXT NOT NULL DEFAULT 'testing', is_deleted INTEGER NOT NULL DEFAULT 0)",
    )
    .await;
    let mut p = params();
    p.insert("environment".into(), json!(environment));
    db.execute(
        "INSERT INTO verifactu_config (hub_id, environment) VALUES (:hub_id, :environment)",
        &p,
    )
    .await
    .unwrap();
}

async fn profile(db: &dyn DatabaseAdapter) -> fiscal_profile::FiscalProfile {
    fiscal_profile::ensure(db, HUB).await.unwrap()
}

fn host(db: &dyn DatabaseAdapter) -> DbHost<'_> {
    DbHost {
        db,
        storage: None,
        hub_id: HUB,
        module_id: "verifactu",
        static_folder: None,
    }
}

/// The engine's question, answered by the core: `testing` on a fresh hub, `production` once the
/// profile is live — whatever the module's row says.
#[tokio::test]
async fn the_native_host_answers_the_core_profile_environment() {
    let rt = hub().await;
    module_config_saying(rt.db(), ENV_PRODUCTION).await;

    assert_eq!(
        host(rt.db()).fiscal_environment(HUB).await.unwrap().as_deref(),
        Some(ENV_TESTING),
        "the module's row said production; the core never went live"
    );

    exec(
        rt.db(),
        "UPDATE _hub_fiscal_profile SET environment = 'production', status = 'ACTIVE' \
         WHERE hub_id = :hub_id",
    )
    .await;
    assert_eq!(
        host(rt.db()).fiscal_environment(HUB).await.unwrap().as_deref(),
        Some(ENV_PRODUCTION)
    );
}

/// 🔴 A hub that went live through the OLD select already files for real. Its profile is promoted
/// — otherwise the engine, now reading the core, would send its next real invoices to the test
/// agency: the generated-but-never-remitted orphan ADR-0189 forbids.
#[tokio::test]
async fn a_hub_that_went_live_through_the_module_select_is_adopted_as_live() {
    let rt = hub().await;
    let mut identity = serde_json::Map::new();
    identity.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    identity.insert("business_tax_id".into(), json!("B12345674"));
    rt.set_settings(&identity, "u1").await.expect("fiscal identity");
    module_config_saying(rt.db(), ENV_PRODUCTION).await;

    assert!(rt.adopt_module_fiscal_environment().await.unwrap());

    let after = profile(rt.db()).await;
    assert_eq!(after.environment, ENV_PRODUCTION);
    assert_eq!(after.status, FiscalStatus::Active);
    assert!(!after.activated_at.is_empty(), "the go-live instant is stamped");
    assert_eq!(after.taxpayer_id, "B12345674", "the identity is frozen as in go_live");
}

/// Exactly once: after the owner stands down (nothing filed yet), the next boot does not push the
/// hub back to production because the module's mirror still says so.
#[tokio::test]
async fn the_adoption_runs_once_and_a_later_stand_down_sticks() {
    let rt = hub().await;
    module_config_saying(rt.db(), ENV_PRODUCTION).await;
    assert!(rt.adopt_module_fiscal_environment().await.unwrap());

    rt.fiscal_stand_down().await.unwrap();
    assert_eq!(profile(rt.db()).await.environment, ENV_TESTING);

    assert!(!rt.adopt_module_fiscal_environment().await.unwrap());
    assert_eq!(profile(rt.db()).await.environment, ENV_TESTING);
}

/// A demo is pinned to `testing` for life (hub#552): the adoption does not open the door the
/// go-live keeps shut.
#[tokio::test]
async fn a_demo_is_never_adopted_as_live() {
    let rt = hub().await;
    exec(
        rt.db(),
        "UPDATE _hub_fiscal_profile SET can_go_live = 0 WHERE hub_id = :hub_id",
    )
    .await;
    module_config_saying(rt.db(), ENV_PRODUCTION).await;

    assert!(!rt.adopt_module_fiscal_environment().await.unwrap());
    assert_eq!(profile(rt.db()).await.environment, ENV_TESTING);
}

/// A ceased business does not start issuing again (hub#557), whatever the module row says.
#[tokio::test]
async fn a_closed_hub_is_never_adopted_as_live() {
    let rt = hub().await;
    exec(
        rt.db(),
        "UPDATE _hub_fiscal_profile SET status = 'CLOSED' WHERE hub_id = :hub_id",
    )
    .await;
    module_config_saying(rt.db(), ENV_PRODUCTION).await;

    assert!(!rt.adopt_module_fiscal_environment().await.unwrap());
    let after = profile(rt.db()).await;
    assert_eq!(after.environment, ENV_TESTING);
    assert_eq!(after.status, FiscalStatus::Closed);
}

/// The positive control's twin: a module row in `testing` promotes nothing.
#[tokio::test]
async fn a_module_row_in_testing_is_not_adopted() {
    let rt = hub().await;
    module_config_saying(rt.db(), ENV_TESTING).await;

    assert!(!rt.adopt_module_fiscal_environment().await.unwrap());
    assert_eq!(profile(rt.db()).await.environment, ENV_TESTING);
}

/// A hub that never installed VeriFactu has no table: nothing to adopt, and no error at boot.
#[tokio::test]
async fn a_hub_without_the_module_table_adopts_nothing() {
    let rt = hub().await;

    assert!(!rt.adopt_module_fiscal_environment().await.unwrap());
    assert_eq!(profile(rt.db()).await.environment, ENV_TESTING);
}
