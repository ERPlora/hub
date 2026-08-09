//! **A hub is born knowing what it owes** — ADR-0273 D1/D6, hub#549.
//!
//! The unit tests in `fiscal_profile.rs` fix what the resolution *is*. This one fixes the part
//! that makes it matter: that it happens **at boot**, on the same path every hub takes, without
//! anybody having to install, enable or configure anything first.
//!
//! That is the whole rule in one assertion. If the profile only appeared once the VeriFactu module
//! was installed, the obligation would still be a consequence of having a module — and
//! uninstalling it would still be the way to make the obligation go away.
use erplora_db::testutil::{fresh_db, TestDb};
use erplora_runtime::fiscal_profile::FiscalStatus;
use erplora_runtime::Runtime;

/// A hub with nothing installed already owes VeriFactu, because it is Spanish.
#[tokio::test]
async fn a_hub_that_has_never_installed_anything_already_owes_verifactu() {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "hub-boot");
    rt.ensure_system_tables().await.unwrap();

    let profile = rt
        .fiscal_profile()
        .await
        .unwrap()
        .expect("booting a hub resolves its fiscal profile");

    assert_eq!(profile.fiscal_system, "verifactu");
    assert_eq!(profile.status, FiscalStatus::Unconfigured);
    assert_eq!(
        profile.system_id, "hub-boot",
        "NumeroInstalacion = hub_id (ADR-0202), written down at birth"
    );
}

/// Booting twice does not produce a second profile, nor lose the first — `ensure_system_tables`
/// runs on every start and every redeploy.
#[tokio::test]
async fn rebooting_keeps_the_same_profile() {
    // Two adapters over the same schema is how this suite simulates a process restart.
    let db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(db.adapter().await), "hub-boot");
    rt.ensure_system_tables().await.unwrap();
    let first = rt.fiscal_profile().await.unwrap().unwrap();

    let restarted = Runtime::with_hub_id(Box::new(db.adapter().await), "hub-boot");
    restarted.ensure_system_tables().await.unwrap();
    let second = restarted.fiscal_profile().await.unwrap().unwrap();

    assert_eq!(first, second);
}
