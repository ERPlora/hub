//! KCS · migrate — `expand` / `contract`, and the promise that a module's `DROP` destroys nothing.
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! The kernel's migration promise has two halves. The declared `kind` must match what the SQL does
//! — an `expand` adds, a `backfill` rewrites rows and never the schema, a `contract` retires — and
//! inside a `contract` a `DROP` is TRANSLATED into a rename: the rows stay, the retirement is
//! reversible, and a module author who writes `DROP TABLE` over a customer's database gets a
//! `_deprecated_` table rather than an empty one. A refused migration is one stable code,
//! `hub.module_migration_rejected`, whose detail names the file and the verb.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{Runtime, RuntimeError};
use kernel_fixture::{admin, broken_copy, dir_at, install_fixture_at, MODULE_ID, PREVIOUS};
use serde_json::json;

/// The stable code every refused module migration travels under.
const REJECTED: &str = "hub.module_migration_rejected";

/// The refusal, or a panic naming what came back instead.
fn rejected(err: RuntimeError) -> String {
    match err {
        RuntimeError::Domain { code, message } => {
            assert_eq!(code, REJECTED, "a refused migration is one stable code");
            message
        }
        other => panic!("expected the stable migration refusal, got {other:?}"),
    }
}

async fn create(rt: &Runtime, name: &str) {
    let mut p = Params::new();
    p.insert("name".into(), json!(name));
    rt.execute_command("kfx.item.create", &p, &admin())
        .await
        .expect("create");
}

/// Which migration files this hub recorded as applied, in order.
async fn applied(rt: &Runtime) -> Vec<String> {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(MODULE_ID));
    rt.db_for_test()
        .query(
            "SELECT filename FROM _hub_migrations WHERE module_id = :module_id ORDER BY filename",
            &p,
        )
        .await
        .expect("read the migration ledger")
        .rows
        .into_iter()
        .map(|r| r["filename"].as_str().unwrap().to_string())
        .collect()
}

/// `SELECT`s a table, returning `Err` when it does not exist under that name.
async fn read(rt: &Runtime, table: &str) -> Result<Vec<serde_json::Value>, String> {
    rt.db_for_test()
        .query(&format!("SELECT * FROM {table}"), &Params::new())
        .await
        .map(|r| r.rows)
        .map_err(|e| e.to_string())
}

#[tokio::test]
async fn every_migration_runs_once_and_in_order_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture_at(&mut rt, kernel_fixture::CURRENT).await;

    assert_eq!(
        applied(&rt).await,
        vec![
            "migrations/postgres/001_init.sql".to_string(),
            "migrations/postgres/002_retire_legacy.sql".to_string(),
            "migrations/postgres/003_trim_names.sql".to_string(),
        ]
    );
    assert!(
        read(&rt, "kfx_item").await.is_ok(),
        "the expand migration ran"
    );
}

/// 🔑 The one that matters: a `contract` retires the table WITHOUT destroying its rows.
#[tokio::test]
async fn a_contract_migration_sets_the_table_aside_instead_of_dropping_it_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture_at(&mut rt, PREVIOUS).await;

    let mut seed = Params::new();
    seed.insert("id".into(), json!("legacy-1"));
    seed.insert("hub_id".into(), json!(rt.hub_id()));
    seed.insert("note".into(), json!("keep me"));
    rt.db_for_test()
        .execute(
            "INSERT INTO kfx_legacy (id, hub_id, note) VALUES (:id, :hub_id, :note)",
            &seed,
        )
        .await
        .expect("seed the row the retirement must not destroy");

    install_fixture_at(&mut rt, kernel_fixture::CURRENT).await;

    assert!(
        read(&rt, "kfx_legacy").await.is_err(),
        "the live name is gone: a `contract` really does retire"
    );
    let kept = read(&rt, "_deprecated_kfx_legacy")
        .await
        .expect("the rows moved aside under `_deprecated_`, they were not destroyed");
    assert_eq!(kept.len(), 1);
    assert_eq!(kept[0]["note"], json!("keep me"));
}

/// 🔴 Proof the guard catches the positive: the SAME `DROP`, declared `expand`, is refused naming
/// the verb — the kernel checks the SQL against the `kind` its author declared.
#[tokio::test]
async fn a_drop_declared_expand_is_refused_naming_the_verb_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let broken = broken_copy("kind-mismatch", |m| {
        m["migrations"]["postgres"][1]["kind"] = json!("expand");
    });

    let detail = rejected(
        rt.install_from_dir(broken.path())
            .await
            .expect_err("a DROP is not an expand"),
    );
    assert!(
        detail.contains("002_retire_legacy.sql")
            && detail.contains("DROP TABLE")
            && detail.contains("contract"),
        "the refusal names the file, the verb it found and the kind it should carry: {detail}"
    );
}

/// 🔴 Proof the guard catches the positive: a `backfill` that changes the SCHEMA is refused naming
/// the verb — a backfill rewrites rows, and DDL belongs in an `expand` or a `contract`.
#[tokio::test]
async fn a_backfill_that_changes_the_schema_is_refused_naming_the_verb_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let broken = broken_copy("backfill-ddl", |_| {});
    std::fs::write(
        broken.path().join("migrations/postgres/003_trim_names.sql"),
        "-- Kernel fixture · a backfill that grows the table instead of rewriting rows.\nALTER TABLE kfx_item ADD COLUMN extra TEXT;\n",
    )
    .unwrap();

    let detail = rejected(
        rt.install_from_dir(broken.path())
            .await
            .expect_err("DDL is not a backfill"),
    );
    assert!(
        detail.contains("003_trim_names.sql") && detail.contains("ALTER"),
        "the refusal names the file and the verb: {detail}"
    );
}

/// A `backfill` is the migration that rewrites what the PREVIOUS version left behind: rows written
/// under 1.0.0 come out of the 1.1.0 update rewritten in place, and nothing else changed.
#[tokio::test]
async fn a_backfill_rewrites_the_rows_the_previous_version_left_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture_at(&mut rt, PREVIOUS).await;
    create(&rt, "  padded  ").await;
    create(&rt, "clean").await;

    install_fixture_at(&mut rt, kernel_fixture::CURRENT).await;

    assert!(
        applied(&rt)
            .await
            .contains(&"migrations/postgres/003_trim_names.sql".to_string()),
        "the backfill ran as part of the update"
    );
    let rows = rt
        .execute_query("kfx.items.list", &Params::new(), &admin())
        .await
        .expect("list");
    let names: Vec<&str> = rows.iter().map(|r| r["name"].as_str().unwrap()).collect();
    assert_eq!(
        names,
        vec!["clean", "padded"],
        "the row 1.0.0 wrote was rewritten in place; the clean one was left alone"
    );
}

/// 🔴 Proof the guard catches the positive: a `contract` that destroys ROWS has no translation, so
/// it is refused outright — `DELETE` belongs in a `backfill`.
#[tokio::test]
async fn a_contract_that_destroys_rows_is_refused_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let broken = broken_copy("row-destruction", |_| {});
    std::fs::write(
        broken.path().join("migrations/postgres/002_retire_legacy.sql"),
        "-- Kernel fixture · a retirement that deletes rows instead of setting them aside.\nDELETE FROM kfx_legacy;\n",
    )
    .unwrap();

    let detail = rejected(
        rt.install_from_dir(broken.path())
            .await
            .expect_err("a contract retires structure, never rows"),
    );
    assert!(
        detail.contains("002_retire_legacy.sql") && detail.to_uppercase().contains("DELETE"),
        "the refusal names the file and the destructive verb: {detail}"
    );
}

/// Reinstalling the same version applies nothing twice: the ledger dedupes by filename.
#[tokio::test]
async fn migrations_are_not_applied_twice_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture_at(&mut rt, kernel_fixture::CURRENT).await;
    let first = applied(&rt).await;
    rt.install_from_dir(&dir_at(kernel_fixture::CURRENT))
        .await
        .expect("reinstall");
    assert_eq!(applied(&rt).await, first);
}
