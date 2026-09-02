//! A `contract` migration sets its tables ASIDE — **even when the file opens with prose** (hub#1137).
//!
//! The contract of hub#542 is that a `DROP` written by a module author never destroys anything: the
//! runtime translates it into `RENAME … TO _deprecated_…`, so the rows are still there and the
//! retirement is reversible. This test is the proof against a real Postgres, through the real door
//! (`install_from_dir` → `migrations::apply` → `migration_guard::check`), that the translation does
//! not depend on the STYLE of the file.
//!
//! It reproduces the loss: `split_statements` deliberately keeps a comment inside the statement that
//! follows it (hub#1027), and the translator used to match `DROP TABLE ` at the START of the
//! statement text — so a header comment above the first `DROP` slipped a REAL, irreversible
//! `DROP TABLE` past the guard, in silence, over a customer's database.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::Runtime;
use serde_json::json;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_contract1137")
        .join(name)
}

async fn rows_in(rt: &Runtime, table: &str) -> Result<Vec<serde_json::Value>, String> {
    rt.db_for_test()
        .query(
            &format!("SELECT name FROM {table} ORDER BY name"),
            &Params::new(),
        )
        .await
        .map(|res| res.rows)
        .map_err(|e| e.to_string())
}

/// 🔴 The data-loss reproduction: the seeded row must still be readable after the retirement.
#[tokio::test]
async fn a_header_comment_does_not_turn_the_contract_into_a_real_drop() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));

    rt.install_from_dir(&fixture("base"))
        .await
        .expect("instalar la versión 1.0.0");

    let mut seed = Params::new();
    seed.insert("id".into(), json!("a1"));
    seed.insert("hub_id".into(), json!("h1"));
    seed.insert("name".into(), json!("keep me"));
    rt.db_for_test()
        .execute(
            "INSERT INTO contract1137_addon (id, hub_id, name) VALUES (:id, :hub_id, :name)",
            &seed,
        )
        .await
        .expect("sembrar la fila que la retirada NO puede destruir");

    // La 1.1.0 retira la tabla con un `contract` cuyo fichero abre con prosa — la forma que tienen
    // las 123 migraciones publicadas, porque el repo la pide.
    rt.install_from_dir(&fixture("retire"))
        .await
        .expect("instalar la versión 1.1.0");

    assert!(
        rows_in(&rt, "contract1137_addon").await.is_err(),
        "la tabla original tiene que haber dejado de existir con su nombre vivo: un `contract` \
         retira de verdad, solo que apartando en vez de destruyendo"
    );

    let kept = rows_in(&rt, "_deprecated_contract1137_addon")
        .await
        .unwrap_or_else(|e| {
            panic!(
            "🔴 PÉRDIDA DE DATOS: el `DROP TABLE` se ejecutó DE VERDAD y la fila sembrada ya no \
             existe. Un `contract` tiene que apartar la tabla a `_deprecated_*`, no destruirla — \
             y no puede depender de que el fichero no lleve un comentario de cabecera: {e}"
        )
        });
    assert_eq!(
        kept.len(),
        1,
        "la fila sembrada sigue ahí, apartada y recuperable: {kept:?}"
    );
    assert_eq!(kept[0]["name"], json!("keep me"));
}
