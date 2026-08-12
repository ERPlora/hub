//! **A paginated query handed to a handler delivered only its FIRST page, in silence** (hub#650).
//!
//! `queries::execute` was documented as «compat: lista ⇒ filas de la página» and returned
//! `execute_page(...).rows` — one page. Every caller that wants a whole set goes through it:
//!
//!   - `commands::preload_reads` — the `reads` block of a command. `sales.complete_sale` preloads
//!     `taxes.rules.list`, which declares `page_size: 50`: a hub with more than 50 tax rules (the
//!     EU-27 seed alone gets close) computed its taxes against a TRUNCATED catalogue and said
//!     nothing. A wrong tax on a real invoice is not a display bug.
//!   - the `guard_query` of a command — a guard that only sees the first 50 rows is a guard with a
//!     hole in it.
//!   - the `recipient_query` of `host.notify` — the people past row 50 are simply never told.
//!
//! And the workaround the issue suggested does not work either: a `params` literal is inserted as a
//! JSON **string** (`manifest.rs`, `resolve_params_from_map`), so `as_u64()` gives `None` and the
//! declared `page_size` wins anyway.
//!
//! The contract these tests pin is the one the client SDK already had (`queryAll`): **everything,
//! unless the caller sets an explicit `limit`, and then the caller wins.**
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;
use std::path::PathBuf;

const HUB: &str = "hub-650";

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests").join("fixture_paging")
}

fn ctx() -> RequestContext {
    RequestContext::new(HUB, "u1", ["*".to_string()])
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

/// A hub with `rows` rows in a catalogue whose query declares `page_size: 2`.
async fn hub_with(rows: u32) -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.install_from_dir(&fixture()).await.expect("instalar el fixture");
    for n in 0..rows {
        rt.execute_command("paging.rows.create", &params(json!({ "n": n })), &ctx())
            .await
            .unwrap_or_else(|e| panic!("crear fila {n}: {e}"));
    }
    rt
}

/// 🔴 The whole catalogue, not the first page. Five rows, `page_size: 2`.
#[tokio::test]
async fn a_query_read_whole_delivers_every_row_not_just_the_first_page() {
    let rt = hub_with(5).await;

    let rows = rt.execute_query("paging.rows.list", &Params::new(), &ctx()).await.unwrap();

    assert_eq!(
        rows.len(),
        5,
        "se entregaron {} filas de 5: el resto se perdió EN SILENCIO",
        rows.len()
    );
}

/// …and they are the right ones, not the first page repeated. Without this, a loop that never
/// advances its offset would pass the count assertion above with five copies of row 0.
#[tokio::test]
async fn every_row_comes_back_exactly_once() {
    let rt = hub_with(5).await;

    let rows = rt.execute_query("paging.rows.list", &Params::new(), &ctx()).await.unwrap();

    let mut seen: Vec<i64> = rows.iter().filter_map(|r| r["n"].as_i64()).collect();
    seen.sort_unstable();
    assert_eq!(seen, vec![0, 1, 2, 3, 4], "filas duplicadas o saltadas: {rows:?}");
}

/// An explicit `limit` is the CALLER's cap and still wins — same rule the client SDK's `queryAll`
/// already follows. Without it, «give me everything» would have no opposite.
#[tokio::test]
async fn an_explicit_limit_is_still_honoured() {
    let rt = hub_with(5).await;

    let rows = rt
        .execute_query("paging.rows.list", &params(json!({ "limit": 2 })), &ctx())
        .await
        .unwrap();

    assert_eq!(rows.len(), 2, "el llamador pidió 2: manda él");
}

/// A catalogue that fits in one page is unchanged — the fix must not turn one round trip into two
/// for the common case.
#[tokio::test]
async fn a_catalogue_smaller_than_a_page_is_untouched() {
    let rt = hub_with(1).await;

    let rows = rt.execute_query("paging.rows.list", &Params::new(), &ctx()).await.unwrap();

    assert_eq!(rows.len(), 1);
}

/// An empty catalogue answers empty, and terminates. A paging loop that treats «no rows» as «keep
/// going» would hang here rather than fail, which is why this case gets its own test.
#[tokio::test]
async fn an_empty_catalogue_terminates() {
    let rt = hub_with(0).await;

    let rows = rt.execute_query("paging.rows.list", &Params::new(), &ctx()).await.unwrap();

    assert!(rows.is_empty(), "{rows:?}");
}

/// 🔴 A query with a STRICT payload schema (`additionalProperties: false`) and **no `list` block**
/// must never be handed an `offset` it does not declare.
///
/// This is the regression of the first attempt at this fix, and it is here because of WHERE it
/// broke. Injecting `offset` into every call made such a query fail its own schema, and one of its
/// callers is the `settings_query` of a `protects` guard — whose failure path is «guard skipped
/// (open)». So the fix for a silent truncation was, for one commit, silently OPENING a guard that
/// should have refused. The single-page path must therefore pass the caller's params untouched.
#[tokio::test]
async fn a_strict_schema_query_is_never_handed_an_offset_it_does_not_declare() {
    let rt = hub_with(3).await;

    let rows = rt
        .execute_query("paging.strict.get", &Params::new(), &ctx())
        .await
        .expect("una query de schema estricto no puede recibir un `offset` inventado");

    assert_eq!(rows.len(), 3, "y sigue devolviendo lo suyo: {rows:?}");
}
