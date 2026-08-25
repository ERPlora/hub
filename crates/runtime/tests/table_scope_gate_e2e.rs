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

use erplora_db::testutil::fresh_db;
use erplora_runtime::{Runtime, RuntimeError};

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
        assert!(err.contains(fact), "the refusal must name `{fact}`, got: {err}");
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
