//! A list's column types are asked of the database ONCE per installed version, not on every
//! request — **hub#2359**.
//!
//! The list engine asks the server what type each column of the base SELECT has (hub#1542) so it
//! can place a `range` bound against it. The answer is a property of the SCHEMA, which only
//! changes when a module migrates: asking it again on every page load is a round trip (an
//! `acquire` from the pool plus a describe) that buys nothing.
//!
//! What remembering it must NOT do, and what most of this file pins:
//!
//!  * outlive a migration — v2 of the fixture adds a column behind the SAME `SELECT *` text, so a
//!    shape remembered from v1 does not know the new column (update, uninstall + reinstall, and a
//!    first install under another module's list that reads the table);
//!  * cross a hub or a database — two hubs never share an answer;
//!  * remember a failure — a describe that failed is asked again on the next request.
//!
//! Real Postgres, ephemeral schema per test — see `crates/db/src/testutil.rs`.
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn fixture(version: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_list_shape_2359")
        .join(version)
        .join("listshape")
}

const LIST: &str = "listshape.items.list";

/// A real Postgres hub that counts how many times the list engine asks for column types. With
/// `blind`, that question fails (asked of the real database, so the error has production's shape)
/// while everything else keeps running for real.
struct CountingDescribes {
    db: erplora_db::PgAdapter,
    describes: Arc<AtomicUsize>,
    blind: bool,
}

#[async_trait::async_trait]
impl erplora_db::DatabaseAdapter for CountingDescribes {
    async fn execute(
        &self,
        sql: &str,
        params: &Params,
    ) -> Result<erplora_db::CommandResult, erplora_db::DbError> {
        self.db.execute(sql, params).await
    }

    async fn execute_tx(
        &self,
        ops: &[(String, Params)],
    ) -> Result<erplora_db::CommandResult, erplora_db::DbError> {
        self.db.execute_tx(ops).await
    }

    async fn execute_tx_gated(
        &self,
        ops: &[(String, Params)],
        gates: &[erplora_db::RowGate],
    ) -> Result<erplora_db::TxGatedOutcome, erplora_db::DbError> {
        self.db.execute_tx_gated(ops, gates).await
    }

    async fn query(
        &self,
        sql: &str,
        params: &Params,
    ) -> Result<erplora_db::QueryResult, erplora_db::DbError> {
        self.db.query(sql, params).await
    }

    async fn execute_batch(&self, sql: &str) -> Result<(), erplora_db::DbError> {
        self.db.execute_batch(sql).await
    }

    async fn column_kinds(
        &self,
        sql: &str,
    ) -> Result<std::collections::BTreeMap<String, erplora_db::ColumnKind>, erplora_db::DbError>
    {
        self.describes.fetch_add(1, Ordering::SeqCst);
        if self.blind {
            return self.db.column_kinds("SELECT ! FROM nowhere").await;
        }
        self.db.column_kinds(sql).await
    }
}

async fn counting_hub(version: &str, blind: bool) -> (Runtime, Arc<AtomicUsize>) {
    counting_hub_on(fresh_db().await, version, blind).await
}

async fn counting_hub_on(
    pg: erplora_db::PgAdapter,
    version: &str,
    blind: bool,
) -> (Runtime, Arc<AtomicUsize>) {
    let describes = Arc::new(AtomicUsize::new(0));
    let db = CountingDescribes {
        db: pg,
        describes: describes.clone(),
        blind,
    };
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture(version))
        .await
        .expect("install listshape");
    (rt, describes)
}

fn ctx(hub_id: &str) -> RequestContext {
    RequestContext::new(hub_id, "u1", ["*".to_string()])
}

fn params(pairs: &[(&str, serde_json::Value)]) -> Params {
    let mut p = Params::new();
    for (k, v) in pairs {
        p.insert((*k).into(), v.clone());
    }
    p
}

/// A TEXT bound over the INTEGER `priority` column: the request that needs the column types.
fn priority_from_text() -> Params {
    params(&[("f_priority_from", json!("10"))])
}

async fn ids(rt: &Runtime, p: &Params, hub_id: &str) -> Vec<String> {
    ids_of(rt, LIST, p, hub_id).await
}

async fn ids_of(rt: &Runtime, list: &str, p: &Params, hub_id: &str) -> Vec<String> {
    let page = rt
        .execute_query_page(list, p, &ctx(hub_id))
        .await
        .unwrap_or_else(|e| panic!("the list must answer: {e}"));
    page.rows
        .iter()
        .map(|r| r["id"].as_str().unwrap().to_string())
        .collect()
}

/// The issue, measured: two requests in a row to the same list ask the database for its column
/// types ONCE. Before hub#2359 every request asked again (2 here, one per page load).
#[tokio::test]
async fn two_requests_to_the_same_list_describe_it_once() {
    let (rt, describes) = counting_hub("v1", false).await;

    let first = ids(&rt, &priority_from_text(), "h1").await;
    let second = ids(&rt, &priority_from_text(), "h1").await;

    assert_eq!(first, vec!["high".to_string(), "mid".to_string()]);
    assert_eq!(
        second, first,
        "the remembered shape must filter exactly like the asked one"
    );
    assert_eq!(
        describes.load(Ordering::SeqCst),
        1,
        "the column types of a list do not change between two requests"
    );
}

/// A list that needs no column type still asks nothing — remembering must not turn a lazy
/// question into an eager one.
#[tokio::test]
async fn a_list_without_a_range_bound_does_not_describe() {
    let (rt, describes) = counting_hub("v1", false).await;

    ids(&rt, &Params::new(), "h1").await;

    assert_eq!(describes.load(Ordering::SeqCst), 0);
}

/// A failed describe is not an answer: nothing is remembered and the next request asks again.
/// Remembering the failure would pin the degraded path (bounds left as written) until the next
/// install, long after the database came back.
#[tokio::test]
async fn a_failed_describe_is_asked_again_on_the_next_request() {
    let (rt, describes) = counting_hub("v1", true).await;
    let numeric = params(&[("f_priority_from", json!(10))]);

    ids(&rt, &numeric, "h1").await;
    ids(&rt, &numeric, "h1").await;

    assert_eq!(describes.load(Ordering::SeqCst), 2);
}

/// UPDATE: v2 adds `score` with a migration and keeps the query text byte for byte. A shape
/// remembered from v1 would not know `score`, the TEXT bound would stay text and Postgres would
/// refuse `integer >= text` — the list would fail right after the update.
#[tokio::test]
async fn an_update_that_migrates_the_table_is_seen_by_the_next_request() {
    let (mut rt, describes) = counting_hub("v1", false).await;
    ids(&rt, &priority_from_text(), "h1").await;

    rt.update_from_dir(&fixture("v2"))
        .await
        .expect("update to v2");

    let got = ids(&rt, &params(&[("f_score_from", json!("50"))]), "h1").await;
    assert_eq!(
        got,
        vec!["high".to_string(), "low".to_string()],
        "a TEXT bound over the column v2 added must compare as a number"
    );
    assert_eq!(
        describes.load(Ordering::SeqCst),
        2,
        "one describe per installed version"
    );
}

/// The same update on ONE pinned connection. sqlx keeps a per-connection cache of prepared
/// statements keyed by their text (hub#1348), and the describe goes through it: on the connection
/// that described v1, the same text would answer v1's columns again. Forgetting our own memory is
/// not enough if the layer below still remembers.
#[tokio::test]
async fn an_update_is_seen_even_on_the_connection_that_described_the_old_shape() {
    let pinned = erplora_db::testutil::TestDb::new()
        .await
        .adapter_with_max_connections(1)
        .await;
    let (mut rt, _describes) = counting_hub_on(pinned, "v1", false).await;
    ids(&rt, &priority_from_text(), "h1").await;

    rt.update_from_dir(&fixture("v2"))
        .await
        .expect("update to v2");

    let got = ids(&rt, &params(&[("f_score_from", json!("50"))]), "h1").await;
    assert_eq!(got, vec!["high".to_string(), "low".to_string()]);
}

/// UNINSTALL + INSTALL: the same, through the other door that brings a new version in.
#[tokio::test]
async fn a_reinstall_that_migrates_the_table_is_seen_by_the_next_request() {
    let (mut rt, _describes) = counting_hub("v1", false).await;
    ids(&rt, &priority_from_text(), "h1").await;

    rt.uninstall("listshape").await.expect("uninstall v1");
    rt.install_from_dir(&fixture("v2"))
        .await
        .expect("install v2");

    let got = ids(&rt, &params(&[("f_score_from", json!("50"))]), "h1").await;
    assert_eq!(got, vec!["high".to_string(), "low".to_string()]);
}

/// FIRST INSTALL under another module's list. `listreader` lists `listshape`'s table without
/// owning it. With `listshape` uninstalled its table stays (expand-only, ADR-0269), so the reader's
/// list keeps answering and remembers the v1 shape. Installing v2 is then a FIRST install — no
/// previous version to remove — and its migration still changes the shape the reader remembered:
/// the installer forgets before migrating, whatever the door.
#[tokio::test]
async fn a_first_install_that_migrates_a_table_another_list_reads_is_seen_by_that_list() {
    const READER: &str = "listreader.items.list";
    let (mut rt, _describes) = counting_hub("v1", false).await;
    rt.install_from_dir(
        &PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixture_list_shape_2359/reader/listreader"),
    )
    .await
    .expect("install listreader");
    rt.uninstall("listshape").await.expect("uninstall v1");
    ids_of(&rt, READER, &priority_from_text(), "h1").await;

    rt.install_from_dir(&fixture("v2"))
        .await
        .expect("install v2");

    let got = ids_of(&rt, READER, &params(&[("f_score_from", json!("50"))]), "h1").await;
    assert_eq!(got, vec!["high".to_string(), "low".to_string()]);
}

/// TENANCY, database: two hubs, each with its own database, each asks its own. A memory shared by
/// the process would answer the second hub with the first one's schema.
#[tokio::test]
async fn two_hubs_on_two_databases_never_share_the_answer() {
    let (a, describes_a) = counting_hub("v1", false).await;
    let (b, describes_b) = counting_hub("v1", false).await;

    ids(&a, &priority_from_text(), "h1").await;
    ids(&b, &priority_from_text(), "h1").await;

    assert_eq!(describes_a.load(Ordering::SeqCst), 1);
    assert_eq!(
        describes_b.load(Ordering::SeqCst),
        1,
        "the second hub must ask its own database, not reuse the first one's answer"
    );
}

/// TENANCY, hub: the remembered answer is keyed by the hub that asked, so a request from another
/// `hub_id` on the same runtime is never served from it.
#[tokio::test]
async fn another_hub_id_is_never_served_from_this_hubs_answer() {
    let (rt, describes) = counting_hub("v1", false).await;

    ids(&rt, &priority_from_text(), "h1").await;
    let other = ids(&rt, &priority_from_text(), "h2").await;

    assert!(other.is_empty(), "hub h2 has no rows of its own");
    assert_eq!(describes.load(Ordering::SeqCst), 2);
}
