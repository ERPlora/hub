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

/// Política del router. `top_k` = nº máximo de módulos a cargar; `min_modules_to_route` =
/// umbral por debajo del cual NO se enruta (con pocos módulos sale más barato mandarlos todos,
/// §9.2b).
#[derive(Debug, Clone, Copy)]
pub struct RouterConfig {
    pub top_k: usize,
    pub min_modules_to_route: usize,
}

impl Default for RouterConfig {
    fn default() -> Self {
        // Umbral conservador: con <8 módulos el coste del embedding por petición no compensa
        // (§9.2b "el vector gana a escala"). top_k limita módulos, no chunks: un módulo puede
        // tener varias descripciones indexadas sin comerse por sí solo todo el resultado.
        Self {
            top_k: 8,
            min_modules_to_route: 8,
        }
    }
}

impl RouterConfig {
    /// Política configurable para despliegues y E2E. Valores ausentes, inválidos o cero (para el
    /// umbral) conservan los defaults seguros; `top_k=0` sigue siendo válido para desactivar todos
    /// los resultados de forma explícita.
    pub fn from_env() -> Self {
        let defaults = Self::default();
        let top_k = std::env::var("HUB_ASSISTANT_ROUTE_TOP_K")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(defaults.top_k);
        let min_modules_to_route = std::env::var("HUB_ASSISTANT_ROUTE_MIN_MODULES")
            .ok()
            .and_then(|v| v.parse::<usize>().ok())
            .filter(|v| *v > 0)
            .unwrap_or(defaults.min_modules_to_route);
        Self {
            top_k,
            min_modules_to_route,
        }
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
/// `candidate_module_ids` procede de las tools que ya sobrevivieron al gate de permisos. Usar el
/// catálogo activo completo aquí permitiría que módulos sin ninguna tool autorizada ocupasen el
/// top-K y dejasen fuera resultados que el usuario sí puede ejecutar (*permission starvation*).
pub async fn route_modules<S: VectorStore + ?Sized>(
    embedder: &dyn Embedder,
    store: &S,
    hub_id: &str,
    query: &str,
    candidate_module_ids: &[String],
    cfg: RouterConfig,
) -> Result<Option<Vec<String>>, RouterError> {
    let query = query.trim();
    if query.is_empty() || candidate_module_ids.len() < cfg.min_modules_to_route {
        return Ok(None);
    }
    if cfg.top_k == 0 {
        return Ok(Some(Vec::new()));
    }

    let mut vectors = embedder
        .embed(std::slice::from_ref(&query.to_string()))
        .await?;
    let query_vec = match vectors.pop() {
        Some(v) if !v.is_empty() => v,
        _ => return Ok(None), // el Cloud no devolvió embedding → degradar a "todos".
    };

    // Recuperamos todos los chunks de los módulos activos y aplicamos top-K DESPUÉS de
    // deduplicar por módulo. Pedir solo K chunks era incorrecto: varias descripciones del primer
    // módulo podían ocupar todas las plazas y devolver menos de K módulos relevantes.
    let hits = store
        .search(hub_id, &query_vec, usize::MAX, Some(candidate_module_ids))
        .await?;
    if hits.is_empty() {
        // Índice vacío (nada indexado todavía) → degradar a "todos" en vez de "ninguno".
        return Ok(None);
    }

    // Conserva el mejor score de cada `ref_id` (= module_id). El desempate por id hace estable el
    // resultado también con Postgres, cuyo orden de filas sin ORDER BY no está definido.
    let mut best_scores = std::collections::HashMap::new();
    for h in hits {
        best_scores.entry(h.chunk.ref_id).or_insert(h.score);
    }
    let mut scored_modules: Vec<(String, f32)> = best_scores.into_iter().collect();
    scored_modules.sort_by(|(id_a, score_a), (id_b, score_b)| {
        score_b.total_cmp(score_a).then_with(|| id_a.cmp(id_b))
    });
    scored_modules.truncate(cfg.top_k);
    Ok(Some(scored_modules.into_iter().map(|(id, _)| id).collect()))
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
        .filter(|t| {
            t.get("module_id")
                .and_then(Value::as_str)
                .is_some_and(|m| set.contains(m))
        })
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
    cfg: RouterConfig,
) -> Vec<Value> {
    // Fuente única de candidatos: el catálogo YA filtrado por `assistant::assemble_tools` según
    // los permisos del usuario. Deduplicamos de forma estable antes de consultar el índice.
    let mut seen = std::collections::HashSet::new();
    let candidate_module_ids: Vec<String> = all_tools
        .iter()
        .filter_map(|tool| tool.get("module_id").and_then(Value::as_str))
        .filter(|module_id| seen.insert((*module_id).to_string()))
        .map(str::to_string)
        .collect();
    match route_modules(embedder, store, hub_id, query, &candidate_module_ids, cfg).await {
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
    use erplora_vector::MemoryVectorStore;
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

    async fn indexed_store() -> MemoryVectorStore {
        let s = MemoryVectorStore::new();
        s.ensure_schema().await.unwrap();
        let modules = [
            ("inventory", "Manage products and stock levels"),
            (
                "sales",
                "Create sales and sell products at the point of sale",
            ),
            ("customers", "Manage customers and clients"),
        ];
        for (id, desc) in modules {
            let chunks = vec![PendingChunk {
                module_id: id.into(),
                source: "agent".into(),
                content: desc.into(),
            }];
            index_chunks(&KeywordEmbedder, &s, "h1", "1.0.0", &chunks)
                .await
                .unwrap();
        }
        s
    }

    fn active(ids: &[&str]) -> Vec<String> {
        ids.iter().map(|id| (*id).to_string()).collect()
    }

    #[tokio::test]
    async fn routes_to_relevant_module() {
        let s = indexed_store().await;
        let cfg = RouterConfig {
            top_k: 1,
            min_modules_to_route: 1,
        };
        let active_modules = active(&["inventory", "sales", "customers"]);
        let modules = route_modules(
            &KeywordEmbedder,
            &s,
            "h1",
            "how much stock of this product?",
            &active_modules,
            cfg,
        )
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
        let active_modules = active(&["inventory", "sales", "customers"]);
        let r = route_modules(&KeywordEmbedder, &s, "h1", "stock?", &active_modules, cfg)
            .await
            .unwrap();
        assert!(r.is_none());
    }

    #[tokio::test]
    async fn empty_query_does_not_route() {
        let s = indexed_store().await;
        let cfg = RouterConfig {
            top_k: 5,
            min_modules_to_route: 1,
        };
        let active_modules = active(&["inventory"]);
        assert!(
            route_modules(&KeywordEmbedder, &s, "h1", "   ", &active_modules, cfg)
                .await
                .unwrap()
                .is_none()
        );
    }

    #[tokio::test]
    async fn empty_index_degrades_to_none() {
        let s = MemoryVectorStore::new();
        s.ensure_schema().await.unwrap();
        let cfg = RouterConfig {
            top_k: 5,
            min_modules_to_route: 1,
        };
        // Hay módulos activos pero el índice está vacío → None (degrada a todos), no [].
        let active_modules = active(&["inventory"]);
        assert!(
            route_modules(&KeywordEmbedder, &s, "h1", "stock?", &active_modules, cfg,)
                .await
                .unwrap()
                .is_none()
        );
    }

    #[tokio::test]
    async fn search_excludes_inactive_module_embeddings() {
        let s = indexed_store().await;
        let cfg = RouterConfig {
            top_k: 2,
            min_modules_to_route: 1,
        };
        let active_modules = active(&["sales", "customers"]);

        let modules = route_modules(
            &KeywordEmbedder,
            &s,
            "h1",
            "stock of a product",
            &active_modules,
            cfg,
        )
        .await
        .unwrap()
        .unwrap();

        assert_eq!(modules.len(), 2);
        assert!(modules.iter().all(|id| active_modules.contains(id)));
        assert!(!modules.iter().any(|id| id == "inventory"));
    }

    #[tokio::test]
    async fn top_k_counts_unique_modules_not_chunks() {
        let s = MemoryVectorStore::new();
        s.ensure_schema().await.unwrap();
        let chunks = vec![
            PendingChunk {
                module_id: "inventory".into(),
                source: "agent".into(),
                content: "products and stock".into(),
            },
            PendingChunk {
                module_id: "inventory".into(),
                source: "query:products.list".into(),
                content: "list products in stock".into(),
            },
            PendingChunk {
                module_id: "inventory".into(),
                source: "command:stock.adjust".into(),
                content: "adjust product stock".into(),
            },
        ];
        index_chunks(&KeywordEmbedder, &s, "h1", "1.0.0", &chunks)
            .await
            .unwrap();
        for (id, content) in [
            ("sales", "create a sale and sell products"),
            ("customers", "manage customers and clients"),
        ] {
            index_chunks(
                &KeywordEmbedder,
                &s,
                "h1",
                "1.0.0",
                &[PendingChunk {
                    module_id: id.into(),
                    source: "agent".into(),
                    content: content.into(),
                }],
            )
            .await
            .unwrap();
        }
        let cfg = RouterConfig {
            top_k: 2,
            min_modules_to_route: 1,
        };
        let active_modules = active(&["inventory", "sales", "customers"]);

        let modules = route_modules(
            &KeywordEmbedder,
            &s,
            "h1",
            "product stock",
            &active_modules,
            cfg,
        )
        .await
        .unwrap()
        .unwrap();

        assert_eq!(modules, vec!["inventory", "sales"]);
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
        let cfg = RouterConfig {
            top_k: 1,
            min_modules_to_route: 1,
        };
        let routed =
            assemble_routed_tools(&KeywordEmbedder, &s, "h1", "stock of product", all, cfg).await;
        assert_eq!(routed.len(), 1);
        assert_eq!(routed[0]["module_id"], "inventory");
    }

    #[tokio::test]
    async fn forbidden_top_hit_cannot_starve_authorized_modules() {
        let s = indexed_store().await;
        let cfg = RouterConfig {
            top_k: 1,
            min_modules_to_route: 1,
        };
        // `inventory` es el hit semántico más fuerte, pero no aparece en `all_tools`: el gate de
        // permisos ya lo retiró. El router debe buscar exclusivamente entre sales/customers.
        let authorized_tools = vec![
            json!({ "module_id": "sales", "name": "sales.list" }),
            json!({ "module_id": "customers", "name": "customers.list" }),
        ];

        let routed = assemble_routed_tools(
            &KeywordEmbedder,
            &s,
            "h1",
            "stock of product",
            authorized_tools,
            cfg,
        )
        .await;

        assert_eq!(routed.len(), 1);
        assert_eq!(routed[0]["module_id"], "sales");
    }
}
