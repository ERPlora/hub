//! Persistent vector store for the Postgres-only Hub (ADR-0154).
//!
//! The level-1 routing corpus is small (hundreds of chunks, §9.5), so embeddings are stored as
//! JSONB and ranked with the same deterministic brute-force cosine scan as the memory store. This
//! needs no optional database extension and still gives the install/update/uninstall lifecycle a
//! durable index. Embeddings themselves continue to come exclusively from the Cloud proxy (§9.3).

use async_trait::async_trait;
use erplora_db::{DatabaseAdapter, Params};
use serde_json::Value as Json;

use crate::{cosine_similarity, Chunk, Result, ScoredChunk, VectorError, VectorStore};

/// PostgreSQL-backed vector store. The adapter normally shares the runtime's `PgPool`.
pub struct PgVectorStore {
    db: Box<dyn DatabaseAdapter>,
}

impl PgVectorStore {
    pub fn new(db: Box<dyn DatabaseAdapter>) -> Self {
        Self { db }
    }
}

#[async_trait]
impl VectorStore for PgVectorStore {
    async fn ensure_schema(&self) -> Result<()> {
        self.db
            .execute_batch(
                "CREATE TABLE IF NOT EXISTS knowledge_chunk (
                id TEXT PRIMARY KEY,
                hub_id TEXT NOT NULL,
                ref_id TEXT NOT NULL,
                version TEXT NOT NULL,
                lang TEXT NOT NULL,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding_json JSONB NOT NULL
             );
             CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_hub
                ON knowledge_chunk(hub_id);
             CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_hub_ref
                ON knowledge_chunk(hub_id, ref_id);",
            )
            .await?;
        Ok(())
    }

    async fn upsert(&self, chunk: &Chunk) -> Result<()> {
        let embedding = serde_json::to_string(&chunk.embedding)
            .map_err(|e| VectorError::Serde(e.to_string()))?;
        let mut params = Params::new();
        params.insert("id".into(), Json::String(chunk.id.clone()));
        params.insert("hub_id".into(), Json::String(chunk.hub_id.clone()));
        params.insert("ref_id".into(), Json::String(chunk.ref_id.clone()));
        params.insert("version".into(), Json::String(chunk.version.clone()));
        params.insert("lang".into(), Json::String(chunk.lang.clone()));
        params.insert("source".into(), Json::String(chunk.source.clone()));
        params.insert("content".into(), Json::String(chunk.content.clone()));
        params.insert("embedding".into(), Json::String(embedding));
        self.db
            .execute(
                "INSERT INTO knowledge_chunk
                (id, hub_id, ref_id, version, lang, source, content, embedding_json)
             VALUES
                (:id, :hub_id, :ref_id, :version, :lang, :source, :content,
                 CAST(:embedding AS JSONB))
             ON CONFLICT (id) DO UPDATE SET
                hub_id = EXCLUDED.hub_id, ref_id = EXCLUDED.ref_id,
                version = EXCLUDED.version, lang = EXCLUDED.lang,
                source = EXCLUDED.source, content = EXCLUDED.content,
                embedding_json = EXCLUDED.embedding_json",
                &params,
            )
            .await?;
        Ok(())
    }

    async fn search(
        &self,
        hub_id: &str,
        query_embedding: &[f32],
        top_k: usize,
        ref_ids: Option<&[String]>,
    ) -> Result<Vec<ScoredChunk>> {
        if top_k == 0 || ref_ids.is_some_and(|refs| refs.is_empty()) {
            return Ok(Vec::new());
        }
        let mut params = Params::new();
        params.insert("hub_id".into(), Json::String(hub_id.to_string()));
        let rows = self
            .db
            .query(
                "SELECT id, hub_id, ref_id, version, lang, source, content,
                    embedding_json::text AS embedding
             FROM knowledge_chunk WHERE hub_id = :hub_id",
                &params,
            )
            .await?
            .rows;

        let mut scored = Vec::with_capacity(rows.len());
        for row in rows {
            let chunk = chunk_from_row(&row)?;
            if ref_ids.is_some_and(|refs| !refs.iter().any(|id| id == &chunk.ref_id)) {
                continue;
            }
            scored.push(ScoredChunk {
                score: cosine_similarity(query_embedding, &chunk.embedding),
                chunk,
            });
        }
        scored.sort_by(|a, b| b.score.total_cmp(&a.score));
        scored.truncate(top_k);
        Ok(scored)
    }

    async fn delete_by_ref(&self, hub_id: &str, ref_id: &str) -> Result<usize> {
        let mut params = Params::new();
        params.insert("hub_id".into(), Json::String(hub_id.to_string()));
        params.insert("ref_id".into(), Json::String(ref_id.to_string()));
        let removed = self
            .db
            .execute(
                "DELETE FROM knowledge_chunk WHERE hub_id = :hub_id AND ref_id = :ref_id",
                &params,
            )
            .await?
            .affected;
        Ok(removed as usize)
    }
}

fn chunk_from_row(row: &Json) -> Result<Chunk> {
    let string = |key: &str| {
        row.get(key)
            .and_then(Json::as_str)
            .map(str::to_owned)
            .ok_or_else(|| VectorError::Embedding(format!("knowledge_chunk.{key} ausente")))
    };
    let embedding_json = string("embedding")?;
    let embedding = serde_json::from_str::<Vec<f32>>(&embedding_json)
        .map_err(|e| VectorError::Embedding(format!("embedding JSON inválido: {e}")))?;
    Ok(Chunk {
        id: string("id")?,
        hub_id: string("hub_id")?,
        ref_id: string("ref_id")?,
        version: string("version")?,
        lang: string("lang")?,
        source: string("source")?,
        content: string("content")?,
        embedding,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunk(id: &str, hub_id: &str, ref_id: &str, embedding: Vec<f32>) -> Chunk {
        Chunk {
            id: id.into(),
            hub_id: hub_id.into(),
            ref_id: ref_id.into(),
            version: "1.0.0".into(),
            lang: "en".into(),
            source: "agent".into(),
            content: format!("content {id}"),
            embedding,
        }
    }

    #[tokio::test]
    async fn persists_and_matches_search_contract() {
        let db = erplora_db::testutil::fresh_db().await;
        let store = PgVectorStore::new(Box::new(db));
        store.ensure_schema().await.unwrap();
        store
            .upsert(&chunk("a", "h1", "inventory", vec![1.0, 0.0]))
            .await
            .unwrap();
        store
            .upsert(&chunk("b", "h1", "sales", vec![0.0, 1.0]))
            .await
            .unwrap();
        store
            .upsert(&chunk("other", "h2", "inventory", vec![1.0, 0.0]))
            .await
            .unwrap();

        let hits = store.search("h1", &[1.0, 0.0], 10, None).await.unwrap();
        assert_eq!(
            hits.iter().map(|h| h.chunk.id.as_str()).collect::<Vec<_>>(),
            vec!["a", "b"]
        );
        assert!((hits[0].score - 1.0).abs() < 1e-6);

        let refs = vec!["sales".to_string()];
        let filtered = store
            .search("h1", &[1.0, 0.0], 10, Some(&refs))
            .await
            .unwrap();
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].chunk.id, "b");
        assert_eq!(store.delete_by_ref("h1", "inventory").await.unwrap(), 1);
        assert_eq!(
            store
                .search("h1", &[1.0, 0.0], 10, None)
                .await
                .unwrap()
                .len(),
            1
        );
    }
}
