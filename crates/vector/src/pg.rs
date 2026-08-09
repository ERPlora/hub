//! [`PgVectorStore`] — the production [`VectorStore`]: Postgres + pgvector (hub#204 / pm#29).
//!
//! Cosine similarity is computed by **Postgres**, with the `<=>` operator over an **HNSW** index,
//! not by a linear scan in Rust like [`MemoryVectorStore`](crate::MemoryVectorStore). HNSW is the
//! right index here rather than IVFFlat: IVFFlat's centroids are built from the data that exists
//! when the index is created, so it must be rebuilt after loading and its recall degrades in
//! silence as modules are installed and uninstalled — a fresh hub would build it over an empty
//! table. HNSW needs no rebuild and is the recommended default below ~1M rows, which every hub is
//! by a wide margin (a full 24-module catalogue is ~400 chunks).
//!
//! **Schema creation lives here, NOT in a system migration** — deliberately. A failing system
//! migration propagates out of `ensure_system_tables` and the hub does not boot
//! (`system_migrations::apply` → `execute_tx(...)?`). `CREATE EXTENSION vector` needs privileges
//! the hub's own role may not hold (ADR-0201 gives each hub its own database and role), and the
//! extension may simply not be installed in the image. Putting it in a migration would mean one
//! missing extension takes down every hub's startup. Here, a failure is just "no index": the
//! caller keeps `None` and the assistant degrades to offering every tool (§9.5), which is the
//! behaviour that shipped before this store existed.

use async_trait::async_trait;
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;
use std::sync::Arc;

use crate::{Chunk, Result, ScoredChunk, VectorError, VectorStore};

/// Embedding width of the Cloud's embedding model. The column is `vector(N)`, so this is part of
/// the stored schema: changing it needs a migration, not just a different constant.
pub const DEFAULT_DIMS: usize = 1536;

/// The knowledge index of a hub, in its own Postgres database.
pub struct PgVectorStore {
    db: Arc<dyn DatabaseAdapter>,
    dims: usize,
}

impl PgVectorStore {
    /// Build a store over `db`. Nothing touches the database until [`VectorStore::ensure_schema`].
    pub fn new(db: Arc<dyn DatabaseAdapter>, dims: usize) -> Self {
        Self { db, dims }
    }

    /// Is pgvector actually usable on this database? Callers use it to decide between wiring the
    /// store and degrading to `None`, without having to interpret a schema error.
    pub async fn is_available(db: &dyn DatabaseAdapter) -> bool {
        db.query(
            "SELECT 1 AS ok FROM pg_available_extensions WHERE name = 'vector'",
            &Params::new(),
        )
        .await
        .map(|r| !r.rows.is_empty())
        .unwrap_or(false)
    }

    /// pgvector's wire format for a vector literal is `[1,2,3]`; the adapter binds a JSON string
    /// as text, and the SQL casts it with `::vector`. Formatting it here (rather than leaning on
    /// `serde_json`'s float rendering) keeps `1.0` from ever arriving as `1.0e0`.
    fn encode(v: &[f32]) -> String {
        let mut s = String::with_capacity(v.len() * 8 + 2);
        s.push('[');
        for (i, x) in v.iter().enumerate() {
            if i > 0 {
                s.push(',');
            }
            s.push_str(&format!("{x}"));
        }
        s.push(']');
        s
    }

    /// Parse `[1,2,3]` back into a vector. The SELECT casts the column with `::text`, because the
    /// `vector` type has its own OID that the generic row decoder does not know.
    fn decode(s: &str) -> Result<Vec<f32>> {
        s.trim()
            .trim_start_matches('[')
            .trim_end_matches(']')
            .split(',')
            .filter(|p| !p.trim().is_empty())
            .map(|p| {
                p.trim()
                    .parse::<f32>()
                    .map_err(|e| VectorError::Embedding(format!("{p:?}: {e}")))
            })
            .collect()
    }
}

#[async_trait]
impl VectorStore for PgVectorStore {
    /// Idempotent — it runs on **every** boot, so `IF NOT EXISTS` everywhere is load-bearing, not
    /// tidiness: without it the second start of a hub would fail.
    async fn ensure_schema(&self) -> Result<()> {
        // `CREATE EXTENSION` is separate from the rest: on a database where the hub's role cannot
        // create it but an operator already did, this statement fails while the table and index
        // are perfectly creatable. Running it on its own lets that case succeed.
        let _ = self
            .db
            .execute(
                "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public",
                &Params::new(),
            )
            .await;

        self.db
            .execute_batch(&format!(
                "CREATE TABLE IF NOT EXISTS hub_knowledge_chunk (\
                   id TEXT PRIMARY KEY,\
                   hub_id TEXT NOT NULL,\
                   ref_id TEXT NOT NULL,\
                   version TEXT NOT NULL,\
                   lang TEXT NOT NULL,\
                   source TEXT NOT NULL,\
                   content TEXT NOT NULL,\
                   embedding public.vector({dims}) NOT NULL\
                 );\
                 CREATE INDEX IF NOT EXISTS hub_knowledge_chunk_scope \
                   ON hub_knowledge_chunk (hub_id, ref_id);\
                 CREATE INDEX IF NOT EXISTS hub_knowledge_chunk_hnsw \
                   ON hub_knowledge_chunk USING hnsw (embedding public.vector_cosine_ops);",
                dims = self.dims
            ))
            .await?;
        Ok(())
    }

    /// Insert or replace by `id`. Re-indexing a module on every install/update is the normal
    /// lifecycle, so this must not accumulate duplicates.
    async fn upsert(&self, chunk: &Chunk) -> Result<()> {
        let mut p = Params::new();
        p.insert("id".into(), json!(chunk.id));
        p.insert("hub_id".into(), json!(chunk.hub_id));
        p.insert("ref_id".into(), json!(chunk.ref_id));
        p.insert("version".into(), json!(chunk.version));
        p.insert("lang".into(), json!(chunk.lang));
        p.insert("source".into(), json!(chunk.source));
        p.insert("content".into(), json!(chunk.content));
        p.insert("embedding".into(), json!(Self::encode(&chunk.embedding)));

        self.db
            .execute(
                "INSERT INTO hub_knowledge_chunk \
                   (id, hub_id, ref_id, version, lang, source, content, embedding) \
                 VALUES (:id, :hub_id, :ref_id, :version, :lang, :source, :content, :embedding::public.vector) \
                 ON CONFLICT (id) DO UPDATE SET \
                   hub_id = EXCLUDED.hub_id, ref_id = EXCLUDED.ref_id, version = EXCLUDED.version, \
                   lang = EXCLUDED.lang, source = EXCLUDED.source, content = EXCLUDED.content, \
                   embedding = EXCLUDED.embedding",
                &p,
            )
            .await?;
        Ok(())
    }

    /// Nearest `top_k` by cosine, scoped to `hub_id` (ADR-0201: a hub never reads a neighbour's
    /// rows) and optionally narrowed to a set of modules.
    ///
    /// `<=>` is cosine **distance**, so the score is `1 - distance`: the router treats the score as
    /// a similarity where higher is better, and handing it a distance would rank the catalogue
    /// backwards — the worst possible failure, because it would still look like it worked.
    async fn search(
        &self,
        hub_id: &str,
        query_embedding: &[f32],
        top_k: usize,
        ref_ids: Option<&[String]>,
    ) -> Result<Vec<ScoredChunk>> {
        // An empty allow-list means "no module", never "every module" — the same semantics the
        // in-memory store guarantees, and the router relies on the difference.
        if ref_ids.is_some_and(<[String]>::is_empty) {
            return Ok(Vec::new());
        }

        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("q".into(), json!(Self::encode(query_embedding)));
        p.insert("k".into(), json!(top_k as i64));

        // The allow-list is expanded into named binds rather than interpolated: `ref_id` is a
        // module id and never user input, but a query that concatenates values is a habit that
        // outlives the case that made it safe.
        let filter = match ref_ids {
            Some(refs) => {
                let names: Vec<String> = refs
                    .iter()
                    .enumerate()
                    .map(|(i, r)| {
                        let key = format!("ref{i}");
                        p.insert(key.clone(), json!(r));
                        format!(":{key}")
                    })
                    .collect();
                format!(" AND ref_id IN ({})", names.join(", "))
            }
            None => String::new(),
        };

        let res = self
            .db
            .query(
                &format!(
                    "SELECT id, hub_id, ref_id, version, lang, source, content, \
                            embedding::text AS embedding, \
                            1 - (embedding OPERATOR(public.<=>) :q::public.vector) AS score \
                     FROM hub_knowledge_chunk \
                     WHERE hub_id = :hub_id{filter} \
                     ORDER BY embedding OPERATOR(public.<=>) :q::public.vector \
                     LIMIT :k"
                ),
                &p,
            )
            .await?;

        let text = |row: &serde_json::Value, key: &str| {
            row.get(key)
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
                .to_string()
        };

        res.rows
            .iter()
            .map(|row| {
                Ok(ScoredChunk {
                    score: row
                        .get("score")
                        .and_then(serde_json::Value::as_f64)
                        .unwrap_or(0.0) as f32,
                    chunk: Chunk {
                        id: text(row, "id"),
                        hub_id: text(row, "hub_id"),
                        ref_id: text(row, "ref_id"),
                        version: text(row, "version"),
                        lang: text(row, "lang"),
                        source: text(row, "source"),
                        content: text(row, "content"),
                        embedding: Self::decode(&text(row, "embedding"))?,
                    },
                })
            })
            .collect()
    }

    /// Drop every chunk a module contributed to THIS hub. Called when a module is uninstalled:
    /// its knowledge must not outlive it, or the assistant keeps describing a capability the
    /// dispatcher no longer has.
    async fn delete_by_ref(&self, hub_id: &str, ref_id: &str) -> Result<usize> {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("ref_id".into(), json!(ref_id));
        let res = self
            .db
            .execute(
                "DELETE FROM hub_knowledge_chunk WHERE hub_id = :hub_id AND ref_id = :ref_id",
                &p,
            )
            .await?;
        Ok(res.affected as usize)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The wire format is pgvector's, not serde's. A vector that renders as `1e0` or `[1.0, 2.0]`
    /// (with spaces) is a cast error at insert time, so the encoding is pinned.
    #[test]
    fn encode_matches_pgvector_literal_format() {
        assert_eq!(PgVectorStore::encode(&[1.0, 0.0, -0.5]), "[1,0,-0.5]");
        assert_eq!(PgVectorStore::encode(&[]), "[]");
    }

    /// Round trip: what Postgres gives back through `::text` must parse into what went in.
    #[test]
    fn decode_reverses_encode() {
        let v = vec![1.0_f32, 0.0, -0.5, 0.25];
        assert_eq!(PgVectorStore::decode(&PgVectorStore::encode(&v)).unwrap(), v);
        assert_eq!(PgVectorStore::decode("[]").unwrap(), Vec::<f32>::new());
    }

    /// A malformed stored embedding is reported, never silently read as zeros — a zero vector
    /// scores 0 against everything and would quietly empty the router's results.
    #[test]
    fn decode_rejects_garbage() {
        assert!(PgVectorStore::decode("[1,nope,3]").is_err());
    }
}
