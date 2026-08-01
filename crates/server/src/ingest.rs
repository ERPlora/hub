//! Ingestión de descripciones del asistente al instalar un módulo (ARQUITECTURA.md §9).
//!
//! Al instalar un módulo recogemos su texto "agéntico" — la `agent.description` (routing de
//! nivel 1) y cada bloque `ai.description` de sus queries/commands (tools de nivel 2) — y lo
//! preparamos para el índice vectorial local (`erplora-vector`).
//!
//! El embedding se obtiene SIEMPRE vía el proxy del Cloud (§9.3 — el Hub nunca llama a un
//! proveedor directamente). [`crate::embed::index_chunks`] consume esta recolección, obtiene el
//! batch de vectores del Cloud y reemplaza el índice persistente del módulo.

use erplora_runtime::Registry;

/// Un fragmento de conocimiento del módulo listo para indexar (sin el vector todavía).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PendingChunk {
    /// `ref_id` para el `VectorStore`: el id del módulo (§9.4, scope per-hub+module).
    pub module_id: String,
    /// `source`: de dónde sale el texto (`agent`, `query:<name>`, `command:<name>`).
    pub source: String,
    /// Texto en inglés que se embedirá vía el proxy del Cloud.
    pub content: String,
}

/// Recoge los textos del asistente del módulo recién instalado.
///
/// Se queda con la `agent.description` del manifest y las `ai.description` de las queries y
/// commands que aportó ese módulo. El server pide después un vector por `content` y persiste el
/// conjunto mediante `VectorStore::upsert`.
pub fn collect_chunks(registry: &Registry, module_id: &str) -> Vec<PendingChunk> {
    let mut out = Vec::new();

    if let Some(m) = registry.installed.iter().find(|m| m.id == module_id) {
        if let Some(agent) = &m.agent {
            out.push(PendingChunk {
                module_id: module_id.to_string(),
                source: "agent".to_string(),
                content: agent.description.clone(),
            });
        }
    }

    for (name, q) in registry
        .queries
        .iter()
        .filter(|(_, q)| q.module_id == module_id)
    {
        if let Some(ai) = &q.def.ai {
            out.push(PendingChunk {
                module_id: module_id.to_string(),
                source: format!("query:{name}"),
                content: ai.description.clone(),
            });
        }
    }

    for (name, c) in registry
        .commands
        .iter()
        .filter(|(_, c)| c.module_id == module_id)
    {
        if let Some(ai) = &c.def.ai {
            out.push(PendingChunk {
                module_id: module_id.to_string(),
                source: format!("command:{name}"),
                content: ai.description.clone(),
            });
        }
    }

    out
}
