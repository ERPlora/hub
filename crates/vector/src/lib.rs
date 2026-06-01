//! erplora-vector — embedded vector store for hub-next RAG.
//!
//! In cloud the RAG corpus lives in Postgres/Aurora with pgvector (`embedding
//! vector(1536)` + HNSW index, see ARQUITECTURA.md §9.4). Locally the hub runs on
//! SQLite, which has no pgvector extension, so this crate implements **Option A**
//! from §9.5: an embedded vector index in Rust.
//!
//! Embeddings are persisted in a plain SQLite table (one row per knowledge chunk,
//! per-hub and per-version) and cosine similarity is computed by **brute force** in
//! Rust. The corpus per hub is small (hundreds of chunks), so a linear scan is fast
//! enough and avoids any native index dependency.
//!
//! The intent (§9.5) is two implementations behind the [`VectorStore`] trait:
//! [`SqliteVectorStore`] here for local, and a `PgVectorStore` in cloud — mirroring
//! how [`erplora_db::DatabaseAdapter`] abstracts SQLite vs Postgres.
//!
//! ## Storage note
//!
//! [`erplora_db::DatabaseAdapter`] only binds JSON-compatible SQL values
//! (text / number / null); it does **not** bind raw `BLOB` bytes (`json_to_sql`
//! turns arrays/objects into JSON strings). To stay compatible with the adapter
//! as-is, the embedding `Vec<f32>` is serialized as a **JSON array of numbers
//! stored in a `TEXT` column**, not a little-endian f32 BLOB. In cloud/pgvector
//! this same column would be a native `vector(N)`.

use erplora_db::{DatabaseAdapter, DbError, Params};
use serde_json::Value;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum VectorError {
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
/// Mirrors the `hub_knowledge_chunk` table of the current hub: scoped per-hub and
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
/// Synchronous, matching [`erplora_db::DatabaseAdapter`].
pub trait VectorStore {
    /// Create the backing schema if it does not exist.
    fn ensure_schema(&self) -> Result<()>;
    /// Insert or replace a chunk (by primary key `id`).
    fn upsert(&self, chunk: &Chunk) -> Result<()>;
    /// Return the `top_k` chunks of `hub_id` most similar to `query_embedding`,
    /// ordered by cosine similarity descending. If `ref_ids` is `Some`, only
    /// chunks whose `ref_id` is in that set are considered.
    fn search(
        &self,
        hub_id: &str,
        query_embedding: &[f32],
        top_k: usize,
        ref_ids: Option<&[String]>,
    ) -> Result<Vec<ScoredChunk>>;
    /// Delete every chunk of `hub_id` with the given `ref_id`; returns rows removed.
    fn delete_by_ref(&self, hub_id: &str, ref_id: &str) -> Result<usize>;
}

// Re-export so callers can name the adapter trait without depending on erplora-db.
pub use erplora_db::DatabaseAdapter as DbAdapter;

/// SQLite-backed [`VectorStore`] (Option A, local/brute-force).
///
/// Generic over any [`DatabaseAdapter`] so tests can use an in-memory adapter and
/// callers can pass an owned `SqliteAdapter`.
pub struct SqliteVectorStore<A: DatabaseAdapter> {
    db: A,
}

impl<A: DatabaseAdapter> SqliteVectorStore<A> {
    /// Build a store over the given adapter.
    pub fn new(db: A) -> Self {
        Self { db }
    }

    /// Borrow the underlying adapter.
    pub fn adapter(&self) -> &A {
        &self.db
    }
}

impl<A: DatabaseAdapter> VectorStore for SqliteVectorStore<A> {
    fn ensure_schema(&self) -> Result<()> {
        self.db.execute_batch(
            "CREATE TABLE IF NOT EXISTS knowledge_chunk (
                id        TEXT PRIMARY KEY,
                hub_id    TEXT NOT NULL,
                ref_id    TEXT NOT NULL,
                version   TEXT NOT NULL,
                lang      TEXT NOT NULL,
                source    TEXT NOT NULL,
                content   TEXT NOT NULL,
                embedding TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_hub
                ON knowledge_chunk (hub_id);
            CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_hub_ref
                ON knowledge_chunk (hub_id, ref_id);",
        )?;
        Ok(())
    }

    fn upsert(&self, chunk: &Chunk) -> Result<()> {
        let embedding = serialize_embedding(&chunk.embedding)?;
        let mut params = Params::new();
        params.insert("id".into(), Value::String(chunk.id.clone()));
        params.insert("hub_id".into(), Value::String(chunk.hub_id.clone()));
        params.insert("ref_id".into(), Value::String(chunk.ref_id.clone()));
        params.insert("version".into(), Value::String(chunk.version.clone()));
        params.insert("lang".into(), Value::String(chunk.lang.clone()));
        params.insert("source".into(), Value::String(chunk.source.clone()));
        params.insert("content".into(), Value::String(chunk.content.clone()));
        params.insert("embedding".into(), Value::String(embedding));
        self.db.execute(
            "INSERT OR REPLACE INTO knowledge_chunk
                (id, hub_id, ref_id, version, lang, source, content, embedding)
             VALUES
                (:id, :hub_id, :ref_id, :version, :lang, :source, :content, :embedding)",
            &params,
        )?;
        Ok(())
    }

    fn search(
        &self,
        hub_id: &str,
        query_embedding: &[f32],
        top_k: usize,
        ref_ids: Option<&[String]>,
    ) -> Result<Vec<ScoredChunk>> {
        let mut params = Params::new();
        params.insert("hub_id".into(), Value::String(hub_id.to_string()));

        // Build an optional `ref_id IN (...)` filter with named params.
        let mut sql = String::from(
            "SELECT id, hub_id, ref_id, version, lang, source, content, embedding
             FROM knowledge_chunk WHERE hub_id = :hub_id",
        );
        if let Some(refs) = ref_ids {
            if refs.is_empty() {
                // An empty allow-list matches nothing.
                return Ok(Vec::new());
            }
            let placeholders: Vec<String> =
                refs.iter().enumerate().map(|(i, _)| format!(":ref{i}")).collect();
            sql.push_str(&format!(" AND ref_id IN ({})", placeholders.join(", ")));
            for (i, r) in refs.iter().enumerate() {
                params.insert(format!("ref{i}"), Value::String(r.clone()));
            }
        }

        let rows = self.db.query(&sql, &params)?;

        let mut scored: Vec<ScoredChunk> = Vec::with_capacity(rows.len());
        for row in &rows {
            let obj = row
                .as_object()
                .ok_or_else(|| VectorError::Embedding("row is not an object".into()))?;
            let chunk = row_to_chunk(obj)?;
            let score = cosine_similarity(query_embedding, &chunk.embedding);
            scored.push(ScoredChunk { chunk, score });
        }

        // Order by score descending; total_cmp gives a total order over f32.
        scored.sort_by(|a, b| b.score.total_cmp(&a.score));
        scored.truncate(top_k);
        Ok(scored)
    }

    fn delete_by_ref(&self, hub_id: &str, ref_id: &str) -> Result<usize> {
        let mut params = Params::new();
        params.insert("hub_id".into(), Value::String(hub_id.to_string()));
        params.insert("ref_id".into(), Value::String(ref_id.to_string()));
        let n = self.db.execute(
            "DELETE FROM knowledge_chunk WHERE hub_id = :hub_id AND ref_id = :ref_id",
            &params,
        )?;
        Ok(n as usize)
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

/// Serialize an embedding as a JSON array of numbers (stored in a TEXT column).
fn serialize_embedding(embedding: &[f32]) -> Result<String> {
    serde_json::to_string(embedding).map_err(|e| VectorError::Serde(e.to_string()))
}

/// Parse an embedding from its JSON-array TEXT representation.
fn deserialize_embedding(text: &str) -> Result<Vec<f32>> {
    serde_json::from_str(text).map_err(|e| VectorError::Embedding(e.to_string()))
}

fn str_field(row: &serde_json::Map<String, Value>, key: &str) -> Result<String> {
    match row.get(key) {
        Some(Value::String(s)) => Ok(s.clone()),
        Some(Value::Null) | None => {
            Err(VectorError::Embedding(format!("missing column `{key}`")))
        }
        Some(other) => Ok(other.to_string()),
    }
}

fn row_to_chunk(row: &serde_json::Map<String, Value>) -> Result<Chunk> {
    let embedding = deserialize_embedding(&str_field(row, "embedding")?)?;
    Ok(Chunk {
        id: str_field(row, "id")?,
        hub_id: str_field(row, "hub_id")?,
        ref_id: str_field(row, "ref_id")?,
        version: str_field(row, "version")?,
        lang: str_field(row, "lang")?,
        source: str_field(row, "source")?,
        content: str_field(row, "content")?,
        embedding,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::SqliteAdapter;

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

    fn store() -> SqliteVectorStore<SqliteAdapter> {
        let db = SqliteAdapter::open_in_memory().expect("open in memory");
        let s = SqliteVectorStore::new(db);
        s.ensure_schema().expect("schema");
        s
    }

    #[test]
    fn search_returns_nearest_first() {
        let s = store();
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0, 0.0])).unwrap();
        s.upsert(&chunk("b", "h1", "r2", vec![0.0, 1.0, 0.0])).unwrap();
        s.upsert(&chunk("c", "h1", "r3", vec![0.9, 0.1, 0.0])).unwrap();

        let res = s.search("h1", &[1.0, 0.0, 0.0], 3, None).unwrap();
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

    #[test]
    fn top_k_limits_results() {
        let s = store();
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).unwrap();
        s.upsert(&chunk("b", "h1", "r2", vec![0.0, 1.0])).unwrap();
        let res = s.search("h1", &[1.0, 0.0], 1, None).unwrap();
        assert_eq!(res.len(), 1);
        assert_eq!(res[0].chunk.id, "a");
    }

    #[test]
    fn isolated_by_hub_id() {
        let s = store();
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).unwrap();
        s.upsert(&chunk("b", "h2", "r1", vec![1.0, 0.0])).unwrap();

        let res = s.search("h1", &[1.0, 0.0], 10, None).unwrap();
        assert_eq!(res.len(), 1);
        assert_eq!(res[0].chunk.id, "a");
        assert_eq!(res[0].chunk.hub_id, "h1");
    }

    #[test]
    fn filters_by_ref_ids() {
        let s = store();
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).unwrap();
        s.upsert(&chunk("b", "h1", "r2", vec![0.9, 0.1])).unwrap();
        s.upsert(&chunk("c", "h1", "r3", vec![0.0, 1.0])).unwrap();

        let refs = vec!["r2".to_string(), "r3".to_string()];
        let res = s.search("h1", &[1.0, 0.0], 10, Some(&refs)).unwrap();
        let ids: Vec<&str> = res.iter().map(|r| r.chunk.id.as_str()).collect();
        assert_eq!(res.len(), 2);
        assert!(ids.contains(&"b"));
        assert!(ids.contains(&"c"));
        assert!(!ids.contains(&"a"));

        // Empty allow-list matches nothing.
        let none = s.search("h1", &[1.0, 0.0], 10, Some(&[])).unwrap();
        assert!(none.is_empty());
    }

    #[test]
    fn delete_by_ref_removes_rows() {
        let s = store();
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).unwrap();
        s.upsert(&chunk("b", "h1", "r1", vec![0.5, 0.5])).unwrap();
        s.upsert(&chunk("c", "h1", "r2", vec![0.0, 1.0])).unwrap();

        let removed = s.delete_by_ref("h1", "r1").unwrap();
        assert_eq!(removed, 2);

        let res = s.search("h1", &[1.0, 0.0], 10, None).unwrap();
        assert_eq!(res.len(), 1);
        assert_eq!(res[0].chunk.id, "c");
    }

    #[test]
    fn upsert_replaces_existing() {
        let s = store();
        s.upsert(&chunk("a", "h1", "r1", vec![1.0, 0.0])).unwrap();
        let mut updated = chunk("a", "h1", "r1", vec![0.0, 1.0]);
        updated.content = "updated".into();
        s.upsert(&updated).unwrap();

        let res = s.search("h1", &[0.0, 1.0], 10, None).unwrap();
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
