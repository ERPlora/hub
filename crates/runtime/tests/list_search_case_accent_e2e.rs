//! **hub#2096** — the list engine's `search` (and the `like` column filter) compared with a
//! plain `LIKE`, which in Postgres is case- AND accent-sensitive: a front desk typing «garcía»
//! got an empty list while «Marta García» was right there, and only the exact capitalisation
//! found her. Every search box in the market (Square, Shopify, Toast, Odoo with `unaccent`)
//! matches regardless of case, and for a Spanish-speaking till regardless of accents too —
//! nobody types «García» with its tilde at a bar counter.
//!
//! Real Postgres, ephemeral schema per test — see `crates/db/src/testutil.rs`. (The runtime is
//! Postgres-only since the local SQLite layer was removed; there is no second dialect to pin.)
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_listsearch2096")
        .join("searchfix")
}

async fn hub() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture())
        .await
        .expect("install searchfix");
    rt
}

fn ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn ids_for(rt: &Runtime, key: &str, value: &str) -> Vec<String> {
    let mut p = Params::new();
    p.insert(key.into(), json!(value));
    let page = rt
        .execute_query_page("searchfix.customers.list", &p, &ctx())
        .await
        .unwrap_or_else(|e| panic!("{key}={value:?} must run: {e:?}"));
    page.rows
        .iter()
        .map(|r| r["id"].as_str().unwrap().to_string())
        .collect()
}

/// The bug, pinned: the stored spelling is «Marta García»; lower case, upper case and the exact
/// spelling must all find her — and only her (the other hub's «Otra García» never leaks in).
#[tokio::test]
async fn search_ignores_case() {
    let rt = hub().await;
    for q in ["García", "garcía", "GARCÍA", "marta"] {
        assert_eq!(
            ids_for(&rt, "search", q).await,
            vec!["marta"],
            "search={q:?}"
        );
    }
}

/// Market decision (hub#2096): «garcia» without the tilde finds «García», and the fold goes
/// both ways — a stored upper-case accented name («IVÁN NÚÑEZ») is found typing «ivan nunez»,
/// and typing the accent still finds it.
#[tokio::test]
async fn search_ignores_accents() {
    let rt = hub().await;
    assert_eq!(ids_for(&rt, "search", "garcia").await, vec!["marta"]);
    assert_eq!(ids_for(&rt, "search", "ivan nunez").await, vec!["ivan"]);
    assert_eq!(ids_for(&rt, "search", "Iván Núñez").await, vec!["ivan"]);
    assert_eq!(ids_for(&rt, "search", "LOPEZ").await, vec!["pedro"]);
}

/// Control: the fold widens matching, it does not turn the search into «match anything». A term
/// nobody has still returns nothing, and a numeric column is still searchable by its digits.
#[tokio::test]
async fn search_still_narrows_and_reaches_non_text_columns() {
    let rt = hub().await;
    assert!(ids_for(&rt, "search", "gonzalez").await.is_empty());
    assert_eq!(ids_for(&rt, "search", "333444").await, vec!["ivan"]);
}

/// The `like` column filter is the same «contains» a person types into a column header, and it
/// had the same `LIKE`: it folds case and accents too.
#[tokio::test]
async fn like_filter_ignores_case_and_accents() {
    let rt = hub().await;
    assert_eq!(ids_for(&rt, "f_city", "malaga").await, vec!["marta"]);
    assert_eq!(ids_for(&rt, "f_city", "ÁVILA").await, vec!["ivan"]);
    assert!(ids_for(&rt, "f_city", "sevilla").await.is_empty());
}
