//! A `contract` that retires a column with `DROP COLUMN IF EXISTS` really applies (hub#2108).
//!
//! The runtime translates a `DROP COLUMN` into `RENAME COLUMN … TO _deprecated_…` (hub#542). With
//! `IF EXISTS` the translation used to emit `RENAME COLUMN IF EXISTS`, which Postgres does not
//! have: `syntax error at or near "EXISTS"`, and the module update failed on every hub. The unit
//! test in `migration_guard` only looked at the TEXT of the rewrite, so this one EXECUTES it,
//! through the real door (`install_from_dir` → `migrations::apply` → `migration_guard::check`),
//! against a real Postgres.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::Runtime;
use serde_json::json;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_contract2108")
        .join(name)
}

#[tokio::test]
async fn drop_column_if_exists_sets_the_column_aside_and_skips_a_missing_one() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));

    rt.install_from_dir(&fixture("base"))
        .await
        .expect("install 1.0.0");

    let mut seed = Params::new();
    seed.insert("id".into(), json!("s1"));
    seed.insert("hub_id".into(), json!("h1"));
    seed.insert("legacy_mode".into(), json!("keep me"));
    rt.db_for_test()
        .execute(
            "INSERT INTO contract2108_settings (id, hub_id, legacy_mode) \
             VALUES (:id, :hub_id, :legacy_mode)",
            &seed,
        )
        .await
        .expect("seed the value the retirement must not destroy");

    rt.install_from_dir(&fixture("retire"))
        .await
        .expect("a contract written with DROP COLUMN IF EXISTS must apply on Postgres");

    assert!(
        rt.db_for_test()
            .query(
                "SELECT legacy_mode FROM contract2108_settings",
                &Params::new()
            )
            .await
            .is_err(),
        "the live column name must be gone after the retirement"
    );

    let kept = rt
        .db_for_test()
        .query(
            "SELECT _deprecated_legacy_mode AS v FROM contract2108_settings",
            &Params::new(),
        )
        .await
        .expect("the column is set aside as _deprecated_legacy_mode, not destroyed");
    assert_eq!(kept.rows.len(), 1, "{:?}", kept.rows);
    assert_eq!(kept.rows[0]["v"], json!("keep me"));
}
