//! KCS · hot update — installing 1.1.0 over 1.0.0 (hub#516).
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! Updating a module is installing over it: the same verified pipeline, the new manifest replacing
//! the old one in the registry, and only the migrations the new version ADDS. Two promises the
//! kernel makes and the suite pins: the data written under the previous version survives, and an
//! update that fails leaves the PREVIOUS version running — a module left half-installed is worse
//! than a module not updated.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::Runtime;
use kernel_fixture::{admin, install_fixture_at, CURRENT, MODULE_ID, PREVIOUS};
use serde_json::json;

async fn applied(rt: &Runtime) -> Vec<String> {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(MODULE_ID));
    rt.db_for_test()
        .query(
            "SELECT filename FROM _hub_migrations WHERE module_id = :module_id ORDER BY filename",
            &p,
        )
        .await
        .expect("migration ledger")
        .rows
        .into_iter()
        .map(|r| r["filename"].as_str().unwrap().to_string())
        .collect()
}

/// The version this hub records for the module, or `""` when there is no row at all.
async fn recorded_version(rt: &Runtime) -> String {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(rt.hub_id()));
    p.insert("module_id".into(), json!(MODULE_ID));
    rt.db_for_test()
        .query(
            "SELECT version FROM hub_module WHERE hub_id = :hub_id AND module_id = :module_id",
            &p,
        )
        .await
        .map(|r| {
            r.rows
                .first()
                .and_then(|row| row["version"].as_str())
                .unwrap_or_default()
                .to_string()
        })
        .unwrap_or_default()
}

async fn create(rt: &Runtime, name: &str) {
    let mut p = Params::new();
    p.insert("name".into(), json!(name));
    rt.execute_command("kfx.item.create", &p, &admin())
        .await
        .expect("create");
}

/// The whole update path in one test: the rows survive, only the new migration runs, and the new
/// surface (handler, listener, navigation, error catalogue) is live afterwards.
#[tokio::test]
async fn updating_keeps_the_data_and_adds_only_the_new_surface_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture_at(&mut rt, PREVIOUS).await;
    create(&rt, "written under 1.0.0").await;

    assert_eq!(
        applied(&rt).await,
        vec!["migrations/postgres/001_init.sql".to_string()]
    );
    assert!(
        rt.registry().get_command("kfx.items.bulk").is_none(),
        "1.0.0 has no Tier 2 handler"
    );

    install_fixture_at(&mut rt, CURRENT).await;

    assert_eq!(recorded_version(&rt).await, CURRENT);
    assert_eq!(
        applied(&rt).await,
        vec![
            "migrations/postgres/001_init.sql".to_string(),
            "migrations/postgres/002_retire_legacy.sql".to_string(),
        ],
        "only the migration the new version adds ran"
    );

    let rows = rt
        .execute_query("kfx.items.list", &Params::new(), &admin())
        .await
        .expect("list");
    assert_eq!(rows.len(), 1, "the row written under 1.0.0 is still there");
    assert_eq!(rows[0]["name"], json!("written under 1.0.0"));

    let reg = rt.registry();
    assert_eq!(reg.module_version(MODULE_ID), CURRENT);
    assert!(
        reg.get_command("kfx.items.bulk").is_some(),
        "the new command is live"
    );
    assert_eq!(
        reg.listeners_for("kfx.item.created"),
        vec!["kfx._log_created".to_string()],
        "the new listener is wired"
    );
    assert!(
        reg.active_navigation()
            .iter()
            .any(|e| e.module_id == MODULE_ID),
        "the new navigation entry is live"
    );
}

/// 🔴 Proof it catches the positive: an update whose migration blows up leaves the PREVIOUS version
/// running — queries, commands and navigation all still answer.
#[tokio::test]
async fn a_failed_update_leaves_the_previous_version_running_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture_at(&mut rt, PREVIOUS).await;
    create(&rt, "a").await;

    // A copy of 1.1.0 whose new migration cannot run.
    let src = kernel_fixture::dir_at(CURRENT);
    let broken = std::env::temp_dir().join(format!("erplora-kcs-badupd-{}", uuid::Uuid::new_v4()));
    copy_tree(&src, &broken);
    std::fs::write(
        broken.join("migrations/postgres/002_retire_legacy.sql"),
        "-- Kernel fixture · a retirement that cannot run.\nDROP TABLE kfx_does_not_exist;\n",
    )
    .unwrap();

    rt.install_from_dir(&broken)
        .await
        .expect_err("the migration fails");

    assert_eq!(
        recorded_version(&rt).await,
        PREVIOUS,
        "the hub still records the version it is actually running"
    );
    assert_eq!(rt.registry().module_version(MODULE_ID), PREVIOUS);
    let rows = rt
        .execute_query("kfx.items.list", &Params::new(), &admin())
        .await
        .expect("the previous version still answers: no queries were stripped");
    assert_eq!(rows.len(), 1);
    create(&rt, "b").await;

    std::fs::remove_dir_all(broken).unwrap();
}

fn copy_tree(from: &std::path::Path, to: &std::path::Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap().flatten() {
        let target = to.join(entry.file_name());
        if entry.path().is_dir() {
            copy_tree(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), target).unwrap();
        }
    }
}
