//! `PgVectorStore` against a REAL Postgres with pgvector (hub#204 / pm#29).
//!
//! These are the tests `MemoryVectorStore` cannot give: the reference impl computes cosine in
//! Rust over a `Vec`, while production computes it in Postgres via the `<=>` operator over an
//! HNSW index. Same trait, two engines — so the contract is pinned here against the engine that
//! actually ships, not against the one that is easy to run.
//!
//! Needs a Postgres **with the `vector` extension available**:
//!
//! ```sh
//! docker run -d --name erplora-pgvector -e POSTGRES_PASSWORD=test -p 5434:5432 pgvector/pgvector:pg18
//! DATABASE_URL=postgres://postgres:test@localhost:5434/hub_test cargo test -p erplora-vector
//! ```

use erplora_db::testutil::fresh_db;
use erplora_vector::{Chunk, PgVectorStore, VectorStore};
use std::sync::Arc;

/// Embeddings are 1536-dim in production (the dimension the Cloud's embedding model returns).
/// The tests use the same width so the column type, the index and the operator are exercised
/// exactly as deployed — a 3-dim toy would pass while `vector(1536)` failed.
const DIMS: usize = 1536;

/// A unit vector pointing along axis `axis`, in the production dimension.
fn unit(axis: usize) -> Vec<f32> {
    let mut v = vec![0.0; DIMS];
    v[axis] = 1.0;
    v
}

/// A vector mostly along `axis` but tilted, to get a score strictly between the others.
fn tilted(axis: usize) -> Vec<f32> {
    let mut v = vec![0.0; DIMS];
    v[axis] = 0.9;
    v[axis + 1] = 0.1;
    v
}

fn chunk(id: &str, hub: &str, ref_id: &str, emb: Vec<f32>) -> Chunk {
    Chunk {
        id: id.into(),
        hub_id: hub.into(),
        ref_id: ref_id.into(),
        version: "1.0.0".into(),
        lang: "en".into(),
        source: "agent".into(),
        content: format!("content of {id}"),
        embedding: emb,
    }
}

async fn store() -> PgVectorStore {
    let db = Arc::new(fresh_db().await);
    let s = PgVectorStore::new(db, DIMS);
    s.ensure_schema().await.expect("ensure_schema must create extension, table and index");
    s
}

/// `ensure_schema` runs on every boot, so it has to be safe to run on a hub that already has the
/// table. If it were not, the second start of every hub would fail.
#[tokio::test]
async fn ensure_schema_is_idempotent() {
    let s = store().await;
    s.ensure_schema().await.expect("second call must be a no-op, not an error");
    s.ensure_schema().await.expect("third call too");
}

/// The ordering contract, computed by Postgres rather than by Rust: nearest first, by cosine.
#[tokio::test]
async fn search_returns_nearest_first() {
    let s = store().await;
    s.upsert(&chunk("a", "h1", "inventory", unit(0))).await.unwrap();
    s.upsert(&chunk("b", "h1", "sales", unit(500))).await.unwrap();
    s.upsert(&chunk("c", "h1", "kitchen", tilted(0))).await.unwrap();

    let hits = s.search("h1", &unit(0), 3, None).await.unwrap();
    assert_eq!(hits.len(), 3);
    assert_eq!(hits[0].chunk.id, "a", "identical vector must rank first");
    assert_eq!(hits[1].chunk.id, "c", "the tilted one is closer than the orthogonal one");
    assert_eq!(hits[2].chunk.id, "b");
    assert!(hits[0].score >= hits[1].score && hits[1].score >= hits[2].score);
    // Cosine similarity of a vector with itself is 1.0 — the score must be a similarity, not a
    // distance, because the router compares it as "higher is better".
    assert!((hits[0].score - 1.0).abs() < 1e-4, "score was {}", hits[0].score);
    // The payload survives the round trip; the router reads `ref_id` to pick modules.
    assert_eq!(hits[0].chunk.ref_id, "inventory");
    assert_eq!(hits[0].chunk.content, "content of a");
    assert_eq!(hits[0].chunk.version, "1.0.0");
}

/// Tenancy (ADR-0201): a hub never sees another hub's chunks. This is the same invariant the
/// runtime enforces on every business table, and the knowledge index is no exception.
#[tokio::test]
async fn isolated_by_hub_id() {
    let s = store().await;
    s.upsert(&chunk("mine", "h1", "inventory", unit(0))).await.unwrap();
    s.upsert(&chunk("theirs", "h2", "inventory", unit(0))).await.unwrap();

    let hits = s.search("h1", &unit(0), 10, None).await.unwrap();
    assert_eq!(hits.len(), 1, "a neighbour's chunk must not be reachable");
    assert_eq!(hits[0].chunk.id, "mine");
}

/// `top_k` is what keeps the prompt small — it is the whole point of the router.
#[tokio::test]
async fn top_k_limits_results() {
    let s = store().await;
    for i in 0..5 {
        s.upsert(&chunk(&format!("c{i}"), "h1", "m", unit(i))).await.unwrap();
    }
    assert_eq!(s.search("h1", &unit(0), 2, None).await.unwrap().len(), 2);
}

/// The allow-list narrows a search to given modules; an EMPTY list means "no module", never "all".
#[tokio::test]
async fn filters_by_ref_ids() {
    let s = store().await;
    s.upsert(&chunk("a", "h1", "inventory", unit(0))).await.unwrap();
    s.upsert(&chunk("b", "h1", "sales", tilted(0))).await.unwrap();
    s.upsert(&chunk("c", "h1", "kitchen", unit(500))).await.unwrap();

    let refs = vec!["sales".to_string(), "kitchen".to_string()];
    let hits = s.search("h1", &unit(0), 10, Some(&refs)).await.unwrap();
    let ids: Vec<&str> = hits.iter().map(|h| h.chunk.ref_id.as_str()).collect();
    assert_eq!(hits.len(), 2);
    assert!(ids.contains(&"sales") && ids.contains(&"kitchen"));
    assert!(!ids.contains(&"inventory"));

    let none = s.search("h1", &unit(0), 10, Some(&[])).await.unwrap();
    assert!(none.is_empty(), "an empty allow-list matches nothing");
}

/// Re-indexing a module must not double its chunks: the id is the identity, and install →
/// update → install is a normal lifecycle.
#[tokio::test]
async fn upsert_replaces_by_id() {
    let s = store().await;
    s.upsert(&chunk("same", "h1", "inventory", unit(0))).await.unwrap();
    let mut updated = chunk("same", "h1", "inventory", unit(500));
    updated.content = "rewritten".into();
    updated.version = "2.0.0".into();
    s.upsert(&updated).await.unwrap();

    let hits = s.search("h1", &unit(500), 10, None).await.unwrap();
    assert_eq!(hits.len(), 1, "upsert must replace, not append");
    assert_eq!(hits[0].chunk.content, "rewritten");
    assert_eq!(hits[0].chunk.version, "2.0.0");
}

/// Uninstalling a module drops its knowledge — and only its own, and only in this hub.
#[tokio::test]
async fn delete_by_ref_is_scoped_to_hub_and_ref() {
    let s = store().await;
    s.upsert(&chunk("a", "h1", "inventory", unit(0))).await.unwrap();
    s.upsert(&chunk("b", "h1", "inventory", unit(1))).await.unwrap();
    s.upsert(&chunk("c", "h1", "sales", unit(2))).await.unwrap();
    s.upsert(&chunk("d", "h2", "inventory", unit(3))).await.unwrap();

    let removed = s.delete_by_ref("h1", "inventory").await.unwrap();
    assert_eq!(removed, 2);

    let left = s.search("h1", &unit(0), 10, None).await.unwrap();
    assert_eq!(left.len(), 1, "only `sales` remains in h1");
    assert_eq!(left[0].chunk.ref_id, "sales");
    // The neighbour's identically-named module is untouched.
    assert_eq!(s.search("h2", &unit(3), 10, None).await.unwrap().len(), 1);
}

/// An empty index is not an error — it is a hub that has not indexed yet, and the router reads
/// "no hits" as "do not route", degrading to the full tool catalogue.
#[tokio::test]
async fn search_on_empty_index_returns_no_rows() {
    let s = store().await;
    assert!(s.search("h1", &unit(0), 10, None).await.unwrap().is_empty());
}
