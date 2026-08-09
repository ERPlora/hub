//! Embeddings al instalar/desinstalar un módulo (ARQUITECTURA.md §9.6 + §9.2b).
//!
//! Al instalar un módulo recogemos su texto "agéntico" ([`ingest::collect_chunks`]) — la
//! `agent.description` (routing nivel 1, §9.2b) y cada `ai.description` de sus queries/commands —,
//! lo **embebemos vía el proxy del Cloud** (§9.3 — el Hub NUNCA llama a un proveedor de embeddings
//! directamente) y registramos los vectores en el índice local [`erplora_vector::VectorStore`].
//! Al desinstalar, se borran (`delete_by_ref`).
//!
//! El I/O de red (la llamada al endpoint de embeddings del Cloud) se inyecta tras el trait
//! [`Embedder`] para poder testear esta lógica con un mock, sin red (regla del prompt). La
//! implementación real ([`CloudEmbedder`]) firma la petición con [`cloud_client::CloudClient`] y la
//! ejecuta con `reqwest`.

use async_trait::async_trait;
use cloud_client::{Auth, CloudClient, EmbeddingsRequest, EmbeddingsResponse};
use erplora_vector::{Chunk, VectorStore};

use crate::ingest::PendingChunk;

/// Error de la ingestión de embeddings.
#[derive(Debug, thiserror::Error)]
pub enum EmbedError {
    #[error("cloud embeddings: {0}")]
    Cloud(String),
    #[error("el Cloud devolvió {got} vectores para {expected} textos")]
    CountMismatch { expected: usize, got: usize },
    #[error("vector store: {0}")]
    Vector(#[from] erplora_vector::VectorError),
}

/// Obtiene embeddings vía el proxy del Cloud (§9.3). Inyectable → testeable sin red.
#[async_trait]
pub trait Embedder: Send + Sync {
    /// Devuelve un vector por cada texto (mismo orden). El modelo lo elige el Cloud.
    async fn embed(&self, texts: &[String]) -> std::result::Result<Vec<Vec<f32>>, EmbedError>;
}

/// [`Embedder`] real: pega al endpoint de embeddings del Cloud con la credencial dada
/// (típicamente la de **máquina** del hub en el lifecycle de install — sin usuario, §9.6).
pub struct CloudEmbedder {
    http: reqwest::Client,
    cloud: CloudClient,
    auth: Auth,
}

impl CloudEmbedder {
    pub fn new(http: reqwest::Client, cloud_base_url: &str, auth: Auth) -> Self {
        Self {
            http,
            cloud: CloudClient::new(cloud_base_url),
            auth,
        }
    }
}

#[async_trait]
impl Embedder for CloudEmbedder {
    async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, EmbedError> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }
        let req = self.cloud.embeddings(&self.auth);
        let body = EmbeddingsRequest::new(texts.to_vec());
        let mut r = self.http.post(&req.url).json(&body);
        for (k, v) in &req.headers {
            r = r.header(*k, v);
        }
        let resp = r
            .send()
            .await
            .map_err(|e| EmbedError::Cloud(e.to_string()))?;
        let resp = resp
            .error_for_status()
            .map_err(|e| EmbedError::Cloud(e.to_string()))?;
        let text = resp
            .text()
            .await
            .map_err(|e| EmbedError::Cloud(e.to_string()))?;
        let parsed = EmbeddingsResponse::parse(&text)
            .map_err(|e| EmbedError::Cloud(format!("respuesta inválida: {e}")))?;
        Ok(parsed.embeddings)
    }
}

/// Construye el `id` estable de un chunk en el índice: `{hub}:{module}:{source}`. Estable entre
/// reinstalaciones → `upsert` (INSERT OR REPLACE) re-indexa en vez de duplicar (§9.6, dedup).
fn chunk_id(hub_id: &str, module_id: &str, source: &str) -> String {
    format!("{hub_id}:{module_id}:{source}")
}

/// Embebe los `chunks` recolectados de un módulo (vía Cloud) y los registra en `store`
/// (ARQUITECTURA.md §9.6). Idempotente: re-instalar un módulo re-embebe y reemplaza sus filas.
///
/// `version`/`lang` viajan a cada [`Chunk`] (per-version, §9.4). Si `chunks` está vacío
/// (módulo sin bloque `ai`/`agent`), no se llama al Cloud y no se indexa nada.
pub async fn index_chunks<S: VectorStore + ?Sized>(
    embedder: &dyn Embedder,
    store: &S,
    hub_id: &str,
    version: &str,
    chunks: &[PendingChunk],
) -> Result<usize, EmbedError> {
    if chunks.is_empty() {
        return Ok(0);
    }
    let texts: Vec<String> = chunks.iter().map(|c| c.content.clone()).collect();
    let vectors = embedder.embed(&texts).await?;
    if vectors.len() != texts.len() {
        return Err(EmbedError::CountMismatch {
            expected: texts.len(),
            got: vectors.len(),
        });
    }

    let mut n = 0usize;
    for (chunk, embedding) in chunks.iter().zip(vectors) {
        let row = Chunk {
            id: chunk_id(hub_id, &chunk.module_id, &chunk.source),
            hub_id: hub_id.to_string(),
            // `ref_id = module_id`: el router (§9.2b) mapea un hit de vuelta a su módulo, y al
            // desinstalar se borran todos los chunks del módulo con `delete_by_ref(hub, module)`.
            ref_id: chunk.module_id.clone(),
            version: version.to_string(),
            lang: "en".to_string(), // agent/ai.description van SIEMPRE en inglés (§9.2).
            source: chunk.source.clone(),
            content: chunk.content.clone(),
            embedding,
        };
        store.upsert(&row).await?;
        n += 1;
    }
    Ok(n)
}

/// Borra del índice todos los chunks de un módulo (uninstall, §9.6). Devuelve filas borradas.
pub async fn drop_module<S: VectorStore + ?Sized>(
    store: &S,
    hub_id: &str,
    module_id: &str,
) -> Result<usize, EmbedError> {
    Ok(store.delete_by_ref(hub_id, module_id).await?)
}

/// **Backfill de arranque** (§9.6): indexa los módulos ACTIVOS que aún no están en el índice.
///
/// La ingesta normal corre en el hook de instalación — que solo dispara al instalar. Un hub que
/// instaló sus módulos antes de que existiera el índice (todos, el día que esto se estrena), o
/// cuya ingesta falló aquel día (best-effort a propósito), arrancaría con el índice vacío para
/// siempre y el router (§9.2b) no se activaría jamás.
///
/// Solo indexa la DIFERENCIA (`indexed_refs`): los embeddings son llamadas al Cloud con coste
/// metered (§9.3), y re-embeber 24 módulos en cada reinicio sería pagar por lo que ya se tiene.
/// Un módulo presente en el índice no se re-embebe aunque su versión cambiara — ese caso lo cubre
/// la ingesta del hook de update, que borra e indexa de nuevo.
///
/// Best-effort por módulo: un fallo en uno no impide indexar los demás (y el router degrada a
/// "todos los tools" mientras tanto). Devuelve `(módulos indexados, chunks totales)`.
pub async fn backfill_index<S: VectorStore + ?Sized>(
    embedder: &dyn Embedder,
    store: &S,
    registry: &erplora_runtime::Registry,
    hub_id: &str,
) -> (usize, usize) {
    let already: std::collections::HashSet<String> = match store.indexed_refs(hub_id).await {
        Ok(refs) => refs.into_iter().collect(),
        Err(e) => {
            tracing::warn!(error = %e, "backfill: no se pudo leer el índice; se omite");
            return (0, 0);
        }
    };

    let (mut modules, mut total) = (0usize, 0usize);
    for manifest in &registry.installed {
        if !registry.is_active(&manifest.id) || already.contains(&manifest.id) {
            continue;
        }
        let chunks = crate::ingest::collect_chunks(registry, &manifest.id);
        if chunks.is_empty() {
            continue; // módulo sin bloque agent/ai: no hay nada que embeber.
        }
        match index_chunks(embedder, store, hub_id, &manifest.version, &chunks).await {
            Ok(n) => {
                modules += 1;
                total += n;
            }
            Err(e) => {
                tracing::warn!(module_id = %manifest.id, error = %e,
                    "backfill: módulo no indexado (no crítico; router degrada)");
            }
        }
    }
    (modules, total)
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_vector::MemoryVectorStore;
    use std::sync::Mutex;

    /// Mock determinista del proxy de embeddings del Cloud: cada texto → un vector fijo derivado
    /// de su longitud (sin red). Registra los textos pedidos para aserciones.
    struct MockEmbedder {
        seen: Mutex<Vec<Vec<String>>>,
    }
    impl MockEmbedder {
        fn new() -> Self {
            Self {
                seen: Mutex::new(Vec::new()),
            }
        }
    }
    #[async_trait]
    impl Embedder for MockEmbedder {
        async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, EmbedError> {
            self.seen.lock().unwrap().push(texts.to_vec());
            Ok(texts
                .iter()
                .map(|t| vec![t.len() as f32, 1.0, 0.0])
                .collect())
        }
    }

    /// Mock que devuelve menos vectores de los pedidos → debe disparar `CountMismatch`.
    struct ShortEmbedder;
    #[async_trait]
    impl Embedder for ShortEmbedder {
        async fn embed(&self, _texts: &[String]) -> Result<Vec<Vec<f32>>, EmbedError> {
            Ok(vec![vec![1.0, 0.0, 0.0]]) // siempre 1, sin importar cuántos textos
        }
    }

    async fn store() -> MemoryVectorStore {
        let s = MemoryVectorStore::new();
        s.ensure_schema().await.unwrap();
        s
    }

    fn chunks() -> Vec<PendingChunk> {
        vec![
            PendingChunk {
                module_id: "inventory".into(),
                source: "agent".into(),
                content: "Manage products and stock".into(),
            },
            PendingChunk {
                module_id: "inventory".into(),
                source: "query:inventory.products.list".into(),
                content: "List products and their current stock".into(),
            },
        ]
    }

    #[tokio::test]
    async fn indexes_chunks_via_embedder() {
        let s = store().await;
        let emb = MockEmbedder::new();
        let n = index_chunks(&emb, &s, "h1", "1.0.0", &chunks())
            .await
            .unwrap();
        assert_eq!(n, 2);

        // Una sola llamada al Cloud, con ambos textos (un batch).
        let seen = emb.seen.lock().unwrap();
        assert_eq!(seen.len(), 1);
        assert_eq!(seen[0].len(), 2);

        // Ambos chunks quedan buscables, mapeados al módulo por `ref_id`.
        let q = vec!["Manage products and stock".len() as f32, 1.0, 0.0];
        let hits = s.search("h1", &q, 10, None).await.unwrap();
        assert_eq!(hits.len(), 2);
        assert!(hits.iter().all(|h| h.chunk.ref_id == "inventory"));
        assert!(hits.iter().all(|h| h.chunk.lang == "en"));
        assert!(hits.iter().all(|h| h.chunk.version == "1.0.0"));
    }

    #[tokio::test]
    async fn reindex_replaces_not_duplicates() {
        let s = store().await;
        let emb = MockEmbedder::new();
        index_chunks(&emb, &s, "h1", "1.0.0", &chunks())
            .await
            .unwrap();
        // Re-instalar la misma versión → mismos ids → reemplaza (sin duplicar).
        index_chunks(&emb, &s, "h1", "1.0.0", &chunks())
            .await
            .unwrap();
        let all = s.search("h1", &[1.0, 1.0, 0.0], 100, None).await.unwrap();
        assert_eq!(
            all.len(),
            2,
            "upsert por id estable, no duplica al reinstalar"
        );
    }

    #[tokio::test]
    async fn empty_chunks_skip_cloud_call() {
        let s = store().await;
        let emb = MockEmbedder::new();
        let n = index_chunks(&emb, &s, "h1", "1.0.0", &[]).await.unwrap();
        assert_eq!(n, 0);
        assert!(
            emb.seen.lock().unwrap().is_empty(),
            "sin textos no se llama al Cloud"
        );
    }

    #[tokio::test]
    async fn count_mismatch_is_error() {
        let s = store().await;
        let err = index_chunks(&ShortEmbedder, &s, "h1", "1.0.0", &chunks())
            .await
            .unwrap_err();
        assert!(matches!(
            err,
            EmbedError::CountMismatch {
                expected: 2,
                got: 1
            }
        ));
    }

    #[tokio::test]
    async fn drop_module_removes_chunks() {
        let s = store().await;
        let emb = MockEmbedder::new();
        index_chunks(&emb, &s, "h1", "1.0.0", &chunks())
            .await
            .unwrap();
        let removed = drop_module(&s, "h1", "inventory").await.unwrap();
        assert_eq!(removed, 2);
        let all = s.search("h1", &[1.0, 1.0, 0.0], 100, None).await.unwrap();
        assert!(all.is_empty());
    }

    /// The backfill fixture: a registry with two ACTIVE modules carrying `agent` text and one
    /// inactive. Built by deserializing manifests — the same parse the installer runs.
    fn backfill_registry() -> erplora_runtime::Registry {
        use erplora_runtime::registry::ModuleStatus;
        let mut reg = erplora_runtime::Registry::new();
        for (id, active) in [("inventory", true), ("sales", true), ("kitchen", false)] {
            let m = serde_json::json!({
                "id": id, "name": id, "version": "1.0.0",
                "agent": { "description": format!("What {id} does") }
            });
            reg.installed.push(serde_json::from_value(m).unwrap());
            reg.status.insert(
                id.to_string(),
                if active { ModuleStatus::Active } else { ModuleStatus::Inactive },
            );
        }
        reg
    }

    /// A hub that installed its modules BEFORE the index existed boots with an empty index and
    /// the install hook will never fire again — the backfill is the only path that fills it.
    /// Inactive modules are not capabilities of the hub and must not be embedded (money, §9.3).
    #[tokio::test]
    async fn backfill_indexes_active_modules_not_yet_in_the_index() {
        let s = store().await;
        let emb = MockEmbedder::new();
        let (modules, chunks) = backfill_index(&emb, &s, &backfill_registry(), "h1").await;
        assert_eq!(modules, 2, "the two active modules");
        assert_eq!(chunks, 2, "one agent chunk each");
        let mut refs = s.indexed_refs("h1").await.unwrap();
        refs.sort();
        assert_eq!(refs, vec!["inventory".to_string(), "sales".to_string()],
            "the inactive module must NOT be embedded");
    }

    /// Only the DIFFERENCE is embedded: embeddings are metered Cloud calls, and re-embedding the
    /// whole catalogue on every restart would pay every boot for what the hub already has.
    #[tokio::test]
    async fn backfill_skips_modules_already_indexed() {
        let s = store().await;
        let emb = MockEmbedder::new();
        let reg = backfill_registry();
        backfill_index(&emb, &s, &reg, "h1").await;
        let calls_after_first = emb.seen.lock().unwrap().len();

        let (modules, chunks) = backfill_index(&emb, &s, &reg, "h1").await;
        assert_eq!((modules, chunks), (0, 0), "second boot: nothing new to index");
        assert_eq!(emb.seen.lock().unwrap().len(), calls_after_first,
            "and crucially, ZERO further calls to the embeddings endpoint");
    }
}
