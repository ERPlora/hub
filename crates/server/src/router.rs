//! Router de tools por vectores — nivel 1 (ARQUITECTURA.md §9.2b).
//!
//! Con muchos módulos instalados, mandar TODOS los tools `ai` al LLM en cada petición no escala
//! (prompt enorme, caro). El router elige dinámicamente **qué módulos cargar** según la petición:
//!
//!   1. embebe lo que pide el usuario (vía el proxy del Cloud, [`crate::embed::Embedder`] — el Hub
//!      nunca llama a un proveedor de embeddings directamente, §9.3),
//!   2. busca en el índice vectorial de routing ([`erplora_vector::VectorStore`], poblado al
//!      instalar por [`crate::embed::index_chunks`]) los chunks más cercanos,
//!   3. deduplica sus `ref_id` → el conjunto de **módulos relevantes** (top-K módulos),
//!   4. [`crate::assistant::assemble_tools`] empaqueta SOLO los tools `ai` de esos módulos que el
//!      usuario puede ejecutar (el gate de permiso es el mismo de la UI, §9.2).
//!
//! **Degradación (§9.5/§9.2b):** el router es un *prefiltro*, no un gate de seguridad. Si no hay
//! red para embeber, si el índice está vacío, o si hay pocos módulos, [`route_modules`] devuelve
//! `None` y el llamador ensambla **todos** los tools (comportamiento actual, correcto pero más
//! caro). El permiso siempre lo revalida el runtime; el router solo recorta el prompt.

use erplora_vector::VectorStore;
use serde_json::Value;

use crate::embed::Embedder;

/// Política del router. `top_k` = nº de chunks a recuperar; `min_modules_to_route` = umbral por
/// debajo del cual NO se enruta (con pocos módulos sale más barato mandarlos todos, §9.2b).
#[derive(Debug, Clone, Copy)]
pub struct RouterConfig {
    pub top_k: usize,
    pub min_modules_to_route: usize,
}

impl Default for RouterConfig {
    fn default() -> Self {
        // Umbral conservador: con <8 módulos el coste del embedding por petición no compensa
        // (§9.2b "el vector gana a escala"). top_k holgado para no perder un módulo relevante.
        Self { top_k: 24, min_modules_to_route: 8 }
    }
}

/// Calcula el conjunto de **módulos relevantes** para `query` por búsqueda vectorial.
///
/// Devuelve:
///  - `Ok(Some(modules))` — la lista (deduplicada, preservando el orden por score) de `module_id`
///    a cargar. Puede ser vacía si nada supera el corte (el llamador debe tratar `Some(vec![])`
///    como "ningún módulo" y no como "todos").
///  - `Ok(None)` — **no enrutar** (pocos módulos instalados / sin índice): el llamador ensambla
///    todos los tools. Es la degradación esperada, no un error.
///  - `Err` — fallo de red/embedding o del store; el llamador decide (típicamente: degradar a
///    "todos los tools" para no romper el asistente por un fallo del prefiltro).
///
/// `installed_module_count` lo pasa el llamador (= nº de módulos activos) para aplicar el umbral
/// sin acoplar el router al `Registry`.
pub async fn route_modules<S: VectorStore + ?Sized>(
    embedder: &dyn Embedder,
    store: &S,
    hub_id: &str,
    query: &str,
    installed_module_count: usize,
    cfg: RouterConfig,
) -> Result<Option<Vec<String>>, RouterError> {
    let query = query.trim();
    if query.is_empty() || installed_module_count < cfg.min_modules_to_route {
        return Ok(None);
    }

    let mut vectors = embedder.embed(std::slice::from_ref(&query.to_string())).await?;
    let query_vec = match vectors.pop() {
        Some(v) if !v.is_empty() => v,
        _ => return Ok(None), // el Cloud no devolvió embedding → degradar a "todos".
    };

    let hits = store.search(hub_id, &query_vec, cfg.top_k, None).await?;
    if hits.is_empty() {
        // Índice vacío (nada indexado todavía) → degradar a "todos" en vez de "ninguno".
        return Ok(None);
    }

    // Deduplica `ref_id` (= module_id) preservando el orden por score descendente.
    let mut seen = std::collections::HashSet::new();
    let mut modules = Vec::new();
    for h in hits {
        if seen.insert(h.chunk.ref_id.clone()) {
            modules.push(h.chunk.ref_id);
        }
    }
    Ok(Some(modules))
}

/// Error del router (red/embedding o store). Se mantiene separado de `EmbedError` para que el
/// llamador distinga "no pude enrutar" (degrada) de un fallo de ingestión.
#[derive(Debug, thiserror::Error)]
pub enum RouterError {
    #[error("embedding: {0}")]
    Embed(#[from] crate::embed::EmbedError),
    #[error("vector store: {0}")]
    Vector(#[from] erplora_vector::VectorError),
}

/// Filtra una lista de tools ensamblada por [`assistant::assemble_tools`] dejando solo las de los
/// módulos en `allowed`. Cada tool lleva su `module_id` (lo añade [`assistant::tool_def`]). Si
/// `allowed` es `None` → no se filtra (degradación: todas las tools).
pub fn filter_tools_by_modules(tools: Vec<Value>, allowed: Option<&[String]>) -> Vec<Value> {
    let Some(allowed) = allowed else { return tools };
    let set: std::collections::HashSet<&str> = allowed.iter().map(String::as_str).collect();
    tools
        .into_iter()
        .filter(|t| t.get("module_id").and_then(Value::as_str).is_some_and(|m| set.contains(m)))
        .collect()
}

/// Conveniencia: ejecuta el router y devuelve directamente las tools ya prefiltradas, partiendo de
/// la lista completa que produce [`assistant::assemble_tools`]. Ante cualquier error del prefiltro
/// (red/embedding/store) **degrada a todas las tools** (§9.2b/§9.5): el asistente nunca se cae por
/// un fallo del router; el permiso lo revalida igual el runtime.
pub async fn assemble_routed_tools<S: VectorStore + ?Sized>(
    embedder: &dyn Embedder,
    store: &S,
    hub_id: &str,
    query: &str,
    all_tools: Vec<Value>,
    installed_module_count: usize,
    cfg: RouterConfig,
) -> Vec<Value> {
    match route_modules(embedder, store, hub_id, query, installed_module_count, cfg).await {
        Ok(allowed) => filter_tools_by_modules(all_tools, allowed.as_deref()),
        Err(e) => {
            tracing::warn!(error = %e, "router vectorial falló; degradando a todas las tools");
            all_tools
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::embed::{index_chunks, EmbedError};
    use crate::ingest::PendingChunk;
    use async_trait::async_trait;
    use erplora_db::SqliteAdapter;
    use erplora_vector::SqliteVectorStore;
    use serde_json::json;

    /// Embedder de juguete: mapea texto → vector por palabras-clave, determinista y sin red. Cada
    /// dimensión = nº de apariciones de una palabra clave (inventory/sales/customers).
    struct KeywordEmbedder;
    fn vectorize(text: &str) -> Vec<f32> {
        let t = text.to_lowercase();
        vec![
            t.matches("product").count() as f32 + t.matches("stock").count() as f32,
            t.matches("sale").count() as f32 + t.matches("sell").count() as f32,
            t.matches("customer").count() as f32 + t.matches("client").count() as f32,
        ]
    }
    #[async_trait]
    impl Embedder for KeywordEmbedder {
        async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, EmbedError> {
            Ok(texts.iter().map(|t| vectorize(t)).collect())
        }
    }

    async fn indexed_store() -> SqliteVectorStore<SqliteAdapter> {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        let s = SqliteVectorStore::new(db);
        s.ensure_schema().await.unwrap();
        let modules = [
            ("inventory", "Manage products and stock levels"),
            ("sales", "Create sales and sell products at the point of sale"),
            ("customers", "Manage customers and clients"),
        ];
        for (id, desc) in modules {
            let chunks = vec![PendingChunk {
                module_id: id.into(),
                source: "agent".into(),
                content: desc.into(),
            }];
            index_chunks(&KeywordEmbedder, &s, "h1", "1.0.0", &chunks).await.unwrap();
        }
        s
    }

    #[tokio::test]
    async fn routes_to_relevant_module() {
        let s = indexed_store().await;
        let cfg = RouterConfig { top_k: 1, min_modules_to_route: 1 };
        let modules = route_modules(&KeywordEmbedder, &s, "h1", "how much stock of this product?", 3, cfg)
            .await
            .unwrap()
            .unwrap();
        assert_eq!(modules.first().map(String::as_str), Some("inventory"));
    }

    #[tokio::test]
    async fn below_threshold_does_not_route() {
        let s = indexed_store().await;
        // 3 módulos < umbral 8 → None (mandar todos, no enrutar).
        let cfg = RouterConfig::default();
        let r = route_modules(&KeywordEmbedder, &s, "h1", "stock?", 3, cfg).await.unwrap();
        assert!(r.is_none());
    }

    #[tokio::test]
    async fn empty_query_does_not_route() {
        let s = indexed_store().await;
        let cfg = RouterConfig { top_k: 5, min_modules_to_route: 1 };
        assert!(route_modules(&KeywordEmbedder, &s, "h1", "   ", 99, cfg).await.unwrap().is_none());
    }

    #[tokio::test]
    async fn empty_index_degrades_to_none() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        let s = SqliteVectorStore::new(db);
        s.ensure_schema().await.unwrap();
        let cfg = RouterConfig { top_k: 5, min_modules_to_route: 1 };
        // Muchos módulos "instalados" pero índice vacío → None (degrada a todos), no [].
        assert!(route_modules(&KeywordEmbedder, &s, "h1", "stock?", 50, cfg).await.unwrap().is_none());
    }

    #[test]
    fn filter_keeps_only_allowed_modules() {
        let tools = vec![
            json!({"name": "inventory.products.list", "module_id": "inventory"}),
            json!({"name": "sales.sale.create", "module_id": "sales"}),
            json!({"name": "customers.customer.list", "module_id": "customers"}),
        ];
        let allowed = vec!["inventory".to_string(), "sales".to_string()];
        let filtered = filter_tools_by_modules(tools.clone(), Some(&allowed));
        let names: Vec<&str> = filtered.iter().filter_map(|t| t["name"].as_str()).collect();
        assert_eq!(names, vec!["inventory.products.list", "sales.sale.create"]);

        // None → no filtra (degradación a todas).
        assert_eq!(filter_tools_by_modules(tools.clone(), None).len(), 3);
        // Some(vec![]) → ninguna.
        assert!(filter_tools_by_modules(tools, Some(&[])).is_empty());
    }

    #[tokio::test]
    async fn assemble_routed_filters_to_relevant() {
        let s = indexed_store().await;
        let all = vec![
            json!({"name": "inventory.products.list", "module_id": "inventory"}),
            json!({"name": "sales.sale.create", "module_id": "sales"}),
            json!({"name": "customers.customer.list", "module_id": "customers"}),
        ];
        let cfg = RouterConfig { top_k: 1, min_modules_to_route: 1 };
        let routed = assemble_routed_tools(&KeywordEmbedder, &s, "h1", "stock of product", all, 3, cfg).await;
        assert_eq!(routed.len(), 1);
        assert_eq!(routed[0]["module_id"], "inventory");
    }
}
