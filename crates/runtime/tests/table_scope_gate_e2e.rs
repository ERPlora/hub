//! hub#633 (ADR-0283 D4 fase B) — the installer refuses a module whose COMMAND/SEED SQL writes
//! tables outside its own prefix.
//!
//! "A module only touches its own tables" had exactly one runtime door: migrations, guarded by
//! `migration_guard` (hub#542). The other half had nothing — `installer::install` never looked
//! at the tables the SQL of `commands`/`seed` writes, so a third-party `module.json` could ship
//! `UPDATE inventory_product …` and only the human review and the marketplace signature stood in
//! the way. This gate closes that half; migrations stay with their own guard.
//!
//! The gate measured against the REAL catalogue before choosing its hardness (2026-08-13, all 25
//! published manifests): **zero** command/seed files write another module's tables or any `_*`
//! name. 25/25 pass, so the gate is born a HARD ERROR.
//!
//! Deliberately WRITE-only: reads of another module's tables are also against the composition
//! contract (ADR-0127 — cross-module goes through public namespaced queries), but a lexical
//! scanner cannot tell a foreign table from a CTE name without an AST parser, and a false refusal
//! bricks a legit module. Left noted for a future AST-based validator.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_table_scope")
        .join(name)
}

/// A module that writes ONLY its own tables installs — including an `ON CONFLICT … DO UPDATE`
/// clause, which must not read as an UPDATE of a table called `set` (that false positive would
/// have flagged 19 of the 25 published modules).
#[tokio::test]
async fn a_module_writing_its_own_tables_installs() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture("scoped_ok"))
        .await
        .expect("own-prefix writes and DO UPDATE clauses are legitimate");
}

/// The hole of hub#633: a command whose SQL writes ANOTHER module's table. Refused at install,
/// before any side effect, naming the module, the table and the file.
#[tokio::test]
async fn a_command_writing_a_foreign_table_is_refused() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let err = rt
        .install_from_dir(&fixture("foreign_write"))
        .await
        .expect_err("`UPDATE inventory_product` in a `foreign_write` manifest must not install")
        .to_string();
    for fact in ["foreign_write", "inventory_product", "raid.sql"] {
        assert!(
            err.contains(fact),
            "the refusal must name `{fact}`, got: {err}"
        );
    }
}

/// The floor under every scope (ADR-0273 D8): `_hub_*` system tables are out of reach of every
/// module — the fiscal profile is the identity of the installation, not module vocabulary.
#[tokio::test]
async fn a_command_writing_a_system_table_is_refused() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let err = rt
        .install_from_dir(&fixture("system_write"))
        .await
        .expect_err("a command inserting into `_hub_fiscal_profile` must not install");
    // The refusal must come from the GATE (before any side effect), not from the SQL happening
    // to fail at dispatch time: it names the system table AND says why.
    assert!(
        matches!(
            &err,
            RuntimeError::ManifestRejected { code, at, .. }
                if code == "system_table_write" && at.contains("_hub_fiscal_profile")
        ),
        "the gate's refusal names the system table and the reason, got: {err}"
    );
}

// ── hub#2475: `MERGE INTO` is a write like the others ───────────────────────────────────────────
//
// The scanner had arms for INSERT/UPDATE/DELETE/DDL/TRUNCATE and none for `MERGE INTO`
// (Postgres ≥ 15; the hub pins 18): a MERGE that deleted another module's rows, or inserted into
// `_hub_*`, produced ZERO write targets and installed. Its `THEN UPDATE SET` action, meanwhile,
// read as an UPDATE of a table called `set`, refusing a legitimate MERGE on the module's own table.

/// A MERGE whose target is another module's table is refused like any foreign write.
#[tokio::test]
async fn a_merge_into_a_foreign_table_is_refused() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let err = rt
        .install_from_dir(&fixture("merge_foreign_write"))
        .await
        .expect_err("`MERGE INTO inventory_product … THEN DELETE` must not install");
    assert!(
        matches!(
            &err,
            RuntimeError::ManifestRejected { code, at, .. }
                if code == "foreign_table_write"
                    && at.contains("inventory_product")
                    && at.contains("raid.sql")
        ),
        "got: {err}"
    );
}

/// A MERGE into `_hub_*` meets the same floor as an INSERT (ADR-0273 D8).
#[tokio::test]
async fn a_merge_into_a_system_table_is_refused() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let err = rt
        .install_from_dir(&fixture("merge_system_write"))
        .await
        .expect_err("`MERGE INTO ONLY _hub_fiscal_profile` must not install");
    assert!(
        matches!(
            &err,
            RuntimeError::ManifestRejected { code, at, .. }
                if code == "system_table_write" && at.contains("_hub_fiscal_profile")
        ),
        "got: {err}"
    );
}

/// A MERGE on the module's OWN table installs and runs through the dispatcher — all three
/// actions, in the caller's hub only (the payload's `hub_id` is overridden by the injected one).
#[tokio::test]
async fn a_merge_into_an_own_table_installs_and_runs_in_the_callers_hub() {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&fixture("merge_scoped_ok"))
        .await
        .expect("a MERGE on the module's own table, with an UPDATE SET action, is legitimate");

    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
    let mut p = Params::new();
    p.insert("item_id".into(), json!("a"));
    p.insert("hub_id".into(), json!("h2"));
    let n = |rows: Vec<serde_json::Value>| -> Vec<(serde_json::Value, serde_json::Value)> {
        rows.iter()
            .map(|r| (r["hub_id"].clone(), r["n"].clone()))
            .collect()
    };
    let rows = || async {
        rt.db_for_test()
            .query(
                "SELECT hub_id, n FROM merge_scoped_ok_item ORDER BY hub_id",
                &Params::new(),
            )
            .await
            .expect("read the module's table")
            .rows
    };

    rt.execute_command("merge_scoped_ok.bump", &p, &ctx)
        .await
        .expect("NOT MATCHED → INSERT");
    assert_eq!(n(rows().await), vec![(json!("h1"), json!(1))]);
    rt.execute_command("merge_scoped_ok.bump", &p, &ctx)
        .await
        .expect("MATCHED → UPDATE");
    assert_eq!(n(rows().await), vec![(json!("h1"), json!(2))]);
    rt.execute_command("merge_scoped_ok.bump", &p, &ctx)
        .await
        .expect("MATCHED AND n >= 2 → DELETE");
    assert!(rows().await.is_empty());
}

// ── hub#2461: the module's OWN set-aside tables ─────────────────────────────────────────────────
//
// A `contract` that retires a table does not drop it: the runtime renames it to
// `_deprecated_<table>` (hub#542). The rows are still the module's data — and, for a table that
// held personal data, still what a GDPR erasure has to reach. The prefix rule above did not know
// about the runtime's own rename, so the module could not erase them (whatsapp_inbox#262/#264).

async fn seed_request(rt: &Runtime, hub: &str, id: &str, customer: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub));
    p.insert("id".into(), json!(id));
    p.insert("customer_id".into(), json!(customer));
    p.insert(
        "data".into(),
        json!(format!("{customer} asked for a haircut")),
    );
    rt.db_for_test()
        .execute(
            "INSERT INTO set_aside_request (hub_id, id, customer_id, data) \
             VALUES (:hub_id, :id, :customer_id, :data)",
            &p,
        )
        .await
        .expect("seed a request on the live table, before it is set aside");
}

async fn set_aside_rows(rt: &Runtime) -> Vec<serde_json::Value> {
    rt.db_for_test()
        .query(
            "SELECT hub_id, id, data, deleted_at FROM _deprecated_set_aside_request ORDER BY hub_id, id",
            &Params::new(),
        )
        .await
        .expect("the retired table is set aside, not dropped")
        .rows
}

/// Installs 1.0.0, seeds the same customer id in two hubs plus a second customer, and upgrades
/// to 1.1.0, whose `contract` sets the table aside and whose commands erase from it.
async fn hub_with_a_set_aside_table() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&fixture("set_aside_base"))
        .await
        .expect("install 1.0.0");
    seed_request(&rt, "h1", "r1", "ana").await;
    seed_request(&rt, "h1", "r2", "bea").await;
    seed_request(&rt, "h2", "r1", "ana").await;
    rt.install_from_dir(&fixture("set_aside_retire"))
        .await
        .expect("a module whose commands erase from its OWN set-aside table must install");
    rt
}

fn erase_payload(spoofed_hub: &str) -> Params {
    let mut p = Params::new();
    p.insert("customer_id".into(), json!("ana"));
    // The payload cannot choose the tenant: `:hub_id` is the caller's, injected by the dispatcher.
    p.insert("hub_id".into(), json!(spoofed_hub));
    p
}

/// The erasure the GDPR asks for, through the real door: install gate → dispatcher → Postgres.
/// Only the caller's hub and only that customer: the same customer id in another hub is another
/// business's customer, and is untouched.
#[tokio::test]
async fn a_module_erases_its_own_set_aside_rows_in_the_callers_hub_only() {
    let rt = hub_with_a_set_aside_table().await;
    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);

    rt.execute_command("set_aside.erase_customer", &erase_payload("h2"), &ctx)
        .await
        .expect("the module erases from its own set-aside table");

    let rows = set_aside_rows(&rt).await;
    assert_eq!(
        rows.len(),
        3,
        "an erasure blanks, it does not lose rows: {rows:?}"
    );
    let (h1_ana, h1_bea, h2_ana) = (&rows[0], &rows[1], &rows[2]);
    assert_eq!(
        (h1_ana["hub_id"].clone(), h1_ana["id"].clone()),
        (json!("h1"), json!("r1"))
    );
    assert_eq!(
        h1_ana["data"],
        json!(null),
        "her request is blanked: {rows:?}"
    );
    assert_ne!(
        h1_ana["deleted_at"],
        json!(null),
        "and marked deleted: {rows:?}"
    );
    assert_eq!(
        h1_bea["data"],
        json!("bea asked for a haircut"),
        "another customer stays: {rows:?}"
    );
    assert_eq!(h1_bea["deleted_at"], json!(null), "{rows:?}");
    assert_eq!(h2_ana["hub_id"], json!("h2"));
    assert_eq!(
        h2_ana["data"],
        json!("ana asked for a haircut"),
        "the same customer id in ANOTHER hub is another business's data: {rows:?}"
    );
    assert_eq!(h2_ana["deleted_at"], json!(null), "{rows:?}");
}

/// `DELETE FROM` is the other shape of the same erasure, and it obeys the same tenant.
#[tokio::test]
async fn a_module_purges_its_own_set_aside_rows_in_the_callers_hub_only() {
    let rt = hub_with_a_set_aside_table().await;
    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);

    rt.execute_command("set_aside.purge_customer", &erase_payload("h2"), &ctx)
        .await
        .expect("the module purges from its own set-aside table");

    let left: Vec<(serde_json::Value, serde_json::Value)> = set_aside_rows(&rt)
        .await
        .iter()
        .map(|r| (r["hub_id"].clone(), r["id"].clone()))
        .collect();
    assert_eq!(
        left,
        vec![(json!("h1"), json!("r2")), (json!("h2"), json!("r1"))],
        "only the caller's hub loses that customer's rows"
    );
}

/// The exception is the module's OWN set-aside tables, nothing more: another module's retired
/// table is still another module's data.
#[tokio::test]
async fn another_modules_set_aside_table_stays_out_of_reach() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let err = rt
        .install_from_dir(&fixture("set_aside_foreign"))
        .await
        .expect_err(
            "`UPDATE _deprecated_inventory_product` from `set_aside_foreign` must not install",
        );
    assert!(
        matches!(
            &err,
            RuntimeError::ManifestRejected { code, at, .. }
                if code == "foreign_table_write" && at.contains("_deprecated_inventory_product")
        ),
        "got: {err}"
    );
}

/// The set-aside table is what makes the `contract` reversible, and it holds every hub's rows:
/// a command may blank or delete rows in it (UPDATE/DELETE, filtered by tenant), never drop it
/// or truncate it — that would destroy the down migration and every other hub's data at once.
#[tokio::test]
async fn dropping_or_truncating_an_own_set_aside_table_is_refused() {
    for (fixture_name, table) in [
        ("set_aside_drop", "_deprecated_set_aside_drop_request"),
        (
            "set_aside_truncate",
            "_deprecated_set_aside_truncate_request",
        ),
        // hub#2475: a MERGE can INSERT into the table every hub shares — not a row erasure.
        ("set_aside_merge", "_deprecated_set_aside_merge_request"),
    ] {
        let db = fresh_db().await;
        let mut rt = Runtime::new(Box::new(db));
        let err = rt
            .install_from_dir(&fixture(fixture_name))
            .await
            .expect_err("only row-level erasure is allowed on a set-aside table");
        assert!(
            matches!(
                &err,
                RuntimeError::ManifestRejected { code, at, .. }
                    if code == "set_aside_table_write" && at.contains(table)
            ),
            "{fixture_name}: got: {err}"
        );
    }
}
