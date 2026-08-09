//! erplora-vector — vector store abstraction for hub RAG.
//!
//! The RAG corpus (agent/tool descriptions embedded for routing, ARQUITECTURA.md §9.4)
//! lives behind the [`VectorStore`] trait. Cosine similarity is computed by **brute
//! force** in Rust ([`cosine_similarity`]); a hub's corpus is small (hundreds of chunks),
//! so a linear scan is fast enough and needs no native index.
//!
//! The former SQLite-backed local store was **removed** with ADR-0154 (the hub is now
//! Postgres-only; there is no local SQLite database). The reference/test implementation
//! is [`MemoryVectorStore`], a pure in-memory store with **no** database dependency.
//!
//! The production store is a **Postgres/pgvector** implementation (`embedding vector(1536)`
//! + HNSW index, ARQUITECTURA.md §9.4) tracked as a follow-up (hub#204 / pm#29). It will
//! sit behind this same [`VectorStore`] trait and reuse [`VectorError::Db`] as its error
//! contract.

use async_trait::async_trait;
use erplora_db::DbError;
use std::sync::Mutex;
use thiserror::Error;

mod pg;
pub use pg::{PgVectorStore, DEFAULT_DIMS};

#[derive(Debug, Error)]
pub enum VectorError {
    /// Reserved for the Postgres/pgvector store (hub#204 / pm#29): the error contract for
    /// the future `PgVectorStore`. `MemoryVectorStore` never fails, so it is unused today.
    #[allow(dead_code)]
    #[error("db error: {0}")]
    Db(#[from] DbError),
    #[error("serialization error: {0}")]
    Serde(String),
    #[error("invalid stored embedding: {0}")]
    Embedding(String),
}

pub type Result<T> = std::result::Result<T, VectorError>;

/// A single knowledge chunk with its embedding.
///
/// Mirrors the `knowledge_chunk` table of the current hub: scoped per-hub and
/// per-version (§9.4).
#[derive(Debug, Clone, PartialEq)]
pub struct Chunk {
    pub id: String,
    pub hub_id: String,
    pub ref_id: String,
    pub version: String,
    pub lang: String,
    pub source: String,
    pub content: String,
    pub embedding: Vec<f32>,
}

/// A chunk paired with its cosine-similarity score against a query embedding.
#[derive(Debug, Clone, PartialEq)]
pub struct ScoredChunk {
    pub chunk: Chunk,
    pub score: f32,
}

/// Storage + retrieval interface for knowledge-chunk embeddings.
///
/// Async, matching [`erplora_db::DatabaseAdapter`] (sqlx-backed).
#[async_trait]
pub trait VectorStore {
    /// Create the backing schema if it does not exist.
    async fn ensure_schema(&self) -> Result<()>;
    /// Insert or replace a chunk (by primary key `id`).
    async fn upsert(&self, chunk: &Chunk) -> Result<()>;
    /// Return the `top_k` chunks of `hub_id` most similar to `query_embedding`,
    /// ordered by cosine similarity descending. If `ref_ids` is `Some`, only
    /// chunks whose `ref_id` is in that set are considered.
    async fn search(
        &self,
        hub_id: &str,
        query_embedding: &[f32],
        top_k: usize,
        ref_ids: Option<&[String]>,
    ) -> Result<Vec<ScoredChunk>>;
    /// Delete every chunk of `hub_id` with the given `ref_id`; returns rows removed.
    async fn delete_by_ref(&self, hub_id: &str, ref_id: &str) -> Result<usize>;
}

/// In-memory [`VectorStore`] — the reference/test implementation.
///
/// Backed by a `Mutex<Vec<Chunk>>` with **no** database dependency. Retrieval is a
/// brute-force cosine scan, honouring the same hub/ref filtering and scoring semantics
/// the production pgvector store (hub#204 / pm#29) must reproduce.
#[derive(Default)]
pub struct MemoryVectorStore {
    chunks: Mutex<Vec<Chunk>>,
}

impl MemoryVectorStore {
    /// Build an empty in-memory store.
    pub fn new() -> Self {
        Self::default()
    }
}

#[async_trait]
impl VectorStore for MemoryVectorStore {
    async fn ensure_schema(&self) -> Result<()> {
        // No backing schema for an in-memory store.
        Ok(())
    }

    async fn upsert(&self, chunk: &Chunk) -> Result<()> {
        let mut chunks = self.chunks.lock().unwrap();
        match chunks.iter_mut().find(|c| c.id == chunk.id) {
            Some(existing) => *existing = chunk.clone(),
            None => chunks.push(chunk.clone()),
        }
        Ok(())
    }

    async fn search(
        &self,
        hub_id: &str,
        query_embedding: &[f32],
        top_k: usize,
        ref_ids: Option<&[String]>,
    ) -> Result<Vec<ScoredChunk>> {
        // An empty allow-list matches nothing.
        if let Some(refs) = ref_ids {
            if refs.is_empty() {
                return Ok(Vec::new());
            }
        }

        let chunks = self.chunks.lock().unwrap();
        let mut scored: Vec<ScoredChunk> = chunks
            .iter()
            .filter(|c| c.hub_id == hub_id)
            .filter(|c| match ref_ids {
                Some(refs) => refs.iter().any(|r| r == &c.ref_id),
                None => true,
            })
            .map(|c| ScoredChunk {
                score: cosine_similarity(query_embedding, &c.embedding),
                chunk: c.clone(),
            })
            .collect();

        // Order by score descending; total_cmp gives a total order over f32.
        scored.sort_by(|a, b| b.score.total_cmp(&a.score));
        scored.truncate(top_k);
        Ok(scored)
    }

    async fn delete_by_ref(&self, hub_id: &str, ref_id: &str) -> Result<usize> {
        let mut chunks = self.chunks.lock().unwrap();
        let before = chunks.len();
        chunks.retain(|c| !(c.hub_id == hub_id && c.ref_id == ref_id));
        Ok(before - chunks.len())
    }
}

/// Cosine similarity between two vectors. Returns `0.0` if either norm is zero or
/// the lengths differ.
fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() {
        return 0.0;
    }
    let mut dot = 0.0f32;
    let mut na = 0.0f32;
    let mut nb = 0.0f32;
    for i in 0..a.len() {
        dot += a[i] * b[i];
        na += a[i] * a[i];
        nb += b[i] * b[i];
    }
    if na == 0.0 || nb == 0.0 {
        return 0.0;
    }
    dot / (na.sqrt() * nb.sqrt())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunk(id: &str, hub: &str, ref_id: &str, emb: Vec<f32>) -> Chunk {
        Chunk {
            id: id.into(),
            hub_id: hub.into(),
            ref_id: ref_id.into(),
            version: "v1".into(),
            lang: "en".into(),
            source: "doc".into(),
            content: format!("content {id}"),
            embedding: emb,
        }
    }

    async fn store() -> MemoryVectorStore {
        let s = MemoryVectorStore::new();
        s.ensure_schema().await.expect("schema");
        s
    }

    #[tokio::test]
    async fn search_returns_nearest_first() {
        let s = store().await;
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0, 0.0])).await.unwrap();
        s.upsert(&chunk("b", "h1", "r2", vec![0.0, 1.0, 0.0])).await.unwrap();
        s.upsert(&chunk("c", "h1", "r3", vec![0.9, 0.1, 0.0])).await.unwrap();

        let res = s.search("h1", &[1.0, 0.0, 0.0], 3, None).await.unwrap();
        assert_eq!(res.len(), 3);
        // "a" is identical to the query, "c" is close, "b" is orthogonal.
        assert_eq!(res[0].chunk.id, "a");
        assert_eq!(res[1].chunk.id, "c");
        assert_eq!(res[2].chunk.id, "b");
        // Scores must be descending.
        assert!(res[0].score >= res[1].score);
        assert!(res[1].score >= res[2].score);
        assert!((res[0].score - 1.0).abs() < 1e-6);
    }

    #[tokio::test]
    async fn top_k_limits_results() {
        let s = store().await;
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).await.unwrap();
        s.upsert(&chunk("b", "h1", "r2", vec![0.0, 1.0])).await.unwrap();
        let res = s.search("h1", &[1.0, 0.0], 1, None).await.unwrap();
        assert_eq!(res.len(), 1);
        assert_eq!(res[0].chunk.id, "a");
    }

    #[tokio::test]
    async fn isolated_by_hub_id() {
        let s = store().await;
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).await.unwrap();
        s.upsert(&chunk("b", "h2", "r1", vec![1.0, 0.0])).await.unwrap();

        let res = s.search("h1", &[1.0, 0.0], 10, None).await.unwrap();
        assert_eq!(res.len(), 1);
        assert_eq!(res[0].chunk.id, "a");
        assert_eq!(res[0].chunk.hub_id, "h1");
    }

    #[tokio::test]
    async fn filters_by_ref_ids() {
        let s = store().await;
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).await.unwrap();
        s.upsert(&chunk("b", "h1", "r2", vec![0.9, 0.1])).await.unwrap();
        s.upsert(&chunk("c", "h1", "r3", vec![0.0, 1.0])).await.unwrap();

        let refs = vec!["r2".to_string(), "r3".to_string()];
        let res = s.search("h1", &[1.0, 0.0], 10, Some(&refs)).await.unwrap();
        let ids: Vec<&str> = res.iter().map(|r| r.chunk.id.as_str()).collect();
        assert_eq!(res.len(), 2);
        assert!(ids.contains(&"b"));
        assert!(ids.contains(&"c"));
        assert!(!ids.contains(&"a"));

        // Empty allow-list matches nothing.
        let none = s.search("h1", &[1.0, 0.0], 10, Some(&[])).await.unwrap();
        assert!(none.is_empty());
    }

    #[tokio::test]
    async fn delete_by_ref_removes_rows() {
        let s = store().await;
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).await.unwrap();
        s.upsert(&chunk("b", "h1", "r1", vec![0.5, 0.5])).await.unwrap();
        s.upsert(&chunk("c", "h1", "r2", vec![0.0, 1.0])).await.unwrap();

        let removed = s.delete_by_ref("h1", "r1").await.unwrap();
        assert_eq!(removed, 2);

        let res = s.search("h1", &[1.0, 0.0], 10, None).await.unwrap();
        assert_eq!(res.len(), 1);
        assert_eq!(res[0].chunk.id, "c");
    }

    #[tokio::test]
    async fn upsert_replaces_existing() {
        let s = store().await;
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).await.unwrap();
        let mut updated = chunk("a", "h1", "r1", vec![0.0, 1.0]);
        updated.content = "updated".into();
        s.upsert(&updated).await.unwrap();

        let res = s.search("h1", &[0.0, 1.0], 10, None).await.unwrap();
        assert_eq!(res.len(), 1);
        assert_eq!(res[0].chunk.content, "updated");
        assert!((res[0].score - 1.0).abs() < 1e-6);
    }

    #[test]
    fn cosine_zero_norm() {
        assert_eq!(cosine_similarity(&[0.0, 0.0], &[1.0, 1.0]), 0.0);
        assert_eq!(cosine_similarity(&[1.0, 1.0], &[0.0, 0.0]), 0.0);
        assert_eq!(cosine_similarity(&[1.0], &[1.0, 0.0]), 0.0);
    }
}
