//! Parseo de `module.json` (el contrato declarativo del módulo). Espejo del JSON Schema
//! en `schemas/module.schema.json`. ARQUITECTURA.md §5.2.
use std::collections::HashMap;
use std::path::Path;

use crate::errors::{Result, RuntimeError};

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Manifest {
    pub id: String,
    pub name: String,
    pub version: String,
    #[serde(default)]
    pub depends_on: Vec<String>,
    #[serde(default)]
    pub permissions: Vec<String>,
    #[serde(default)]
    pub role_permissions: HashMap<String, Vec<String>>,
    #[serde(default)]
    pub navigation: Vec<Nav>,
    #[serde(default)]
    pub migrations: Migrations,
    #[serde(default)]
    pub queries: HashMap<String, QueryDef>,
    #[serde(default)]
    pub commands: HashMap<String, CommandDef>,
    #[serde(default)]
    pub events: Events,
    /// Tablas sincronizables local↔cloud (ADR-0031). Vacío = el módulo no sincroniza.
    #[serde(default)]
    pub sync: Vec<SyncTableDef>,
    /// Resumen del módulo para el routing del asistente (nivel 1). ARQUITECTURA.md §9.2b.
    #[serde(default)]
    pub agent: Option<Agent>,
    /// Conocimiento del módulo para RAG (§9.4) — aparcado/en diseño. Se captura tal cual.
    #[serde(default)]
    pub ai_context: Option<serde_json::Value>,
}

/// Una tabla declarada como sincronizable (bloque `sync` del manifest, ADR-0031). Espejo del
/// JSON Schema. El runtime la convierte en `erplora_datasync::SyncTable`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct SyncTableDef {
    /// Nombre de la tabla (debe existir en ambos lados; lo crean las migraciones).
    pub table: String,
    /// Columnas que forman el conflict-target del UPSERT (la PK lógica).
    pub pk: Vec<String>,
    /// Si lleva `hub_id`, se filtra por hub en push/pull (tenancy, §2.5). Por defecto `true`.
    #[serde(default = "default_hub_scoped")]
    pub hub_scoped: bool,
    /// Columna de versión para LWW (ISO-8601 TEXT). Por defecto `updated_at`.
    #[serde(default = "default_updated_at")]
    pub updated_at: String,
}

fn default_hub_scoped() -> bool {
    true
}

fn default_updated_at() -> String {
    "updated_at".to_string()
}

/// Bloque `agent` del manifest: descripción del módulo (en inglés) para el routing del
/// asistente y palabras clave opcionales para pre-filtro léxico. ARQUITECTURA.md §9.2b.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct Agent {
    pub description: String,
    #[serde(default)]
    pub keywords: Vec<String>,
}

#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Migrations {
    #[serde(default)]
    pub sqlite: Vec<String>,
    #[serde(default)]
    pub postgres: Vec<String>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Nav {
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub icon: Option<String>,
    pub component: String,
    /// Acciones de topbar de esta pestaña: el shell las pinta en `slot="end"` y al pulsar
    /// reenvía `module-action` al Web Component montado. El manifest declara el botón;
    /// el comportamiento vive en el componente del módulo.
    #[serde(default)]
    pub actions: Vec<NavAction>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct NavAction {
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub icon: Option<String>,
    /// Botón destacado (color primario).
    #[serde(default)]
    pub primary: bool,
    /// Permiso para MOSTRAR el botón (show/hide de UI; Rust revalida siempre el command real).
    #[serde(default)]
    pub permission: Option<String>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct QueryDef {
    pub permission: String,
    pub sql: String,
    #[serde(default)]
    pub schema: Option<String>,
    /// Si está presente, la query es **paginada/lista**: el runtime envuelve el SELECT base
    /// como subconsulta y compone búsqueda + filtro por columna + orden (whitelist) +
    /// LIMIT/OFFSET, devolviendo `{rows,total,limit,offset}`. ARQUITECTURA.md §4, §8.2.
    #[serde(default)]
    pub list: Option<ListSpec>,
    /// Si está presente, expone esta query al asistente como tool (nivel 2). El permiso y el
    /// schema se heredan de la propia query, no se redeclaran. ARQUITECTURA.md §9.2.
    #[serde(default)]
    pub ai: Option<AiTool>,
}

/// Contrato declarativo de una query de lista (`list` en `module.json`). Espejo de
/// `$defs/listSpec` en `schemas/module.schema.json`. El runtime lo consume en `queries.rs`
/// para componer el SQL paginado. ARQUITECTURA.md §4, §8.2.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ListSpec {
    /// Columnas sobre las que aplica el buscador global (LIKE).
    #[serde(default)]
    pub search: Vec<String>,
    /// Whitelist de columnas ordenables (anti-inyección: solo estas se interpolan en ORDER BY).
    #[serde(default)]
    pub sort: Vec<String>,
    /// Columna de orden por defecto (debe estar en `sort`).
    #[serde(default)]
    pub default_sort: Option<String>,
    /// Dirección por defecto (`asc`/`desc`).
    #[serde(default)]
    pub default_dir: Option<String>,
    /// Filtros por columna (orden determinista para SQL estable → `BTreeMap`).
    #[serde(default)]
    pub filters: std::collections::BTreeMap<String, FilterSpec>,
    /// Tamaño de página por defecto si el llamador no envía `limit`.
    #[serde(default = "default_page_size")]
    pub page_size: u64,
}

fn default_page_size() -> u64 {
    50
}

/// Operador de un filtro por columna.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct FilterSpec {
    pub op: FilterOp,
}

/// Tipos de filtro soportados. `eq`: igualdad. `like`: subcadena. `range`: rango (from/to).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FilterOp {
    Eq,
    Like,
    Range,
}

/// Bloque `ai` inline de una operación: la descripción legible (en inglés) que ve el LLM.
/// `permission`/`schema`/`sql` se heredan de la operación. ARQUITECTURA.md §9.2.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct AiTool {
    pub description: String,
    /// Nombre opcional que ve el LLM (por defecto, el nombre de la operación).
    #[serde(default)]
    pub name: Option<String>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct CommandDef {
    pub permission: String,
    #[serde(default)]
    pub transaction: bool,
    #[serde(default)]
    pub sql: Vec<String>,
    /// Ruta (relativa a la carpeta del módulo) del JSON Schema del payload. Si está
    /// presente, el runtime valida el payload del llamador contra él ANTES de ejecutar
    /// (se compila una vez al instalar y se cachea en el `Registry`). §5.2, hub#27.
    #[serde(default)]
    pub schema: Option<String>,
    #[serde(default)]
    pub emit: Vec<String>,
    /// Handler de lógica: Tier 2 (WASM sandbox) o **plugin nativo first-party**
    /// (ADR-0009, crate horneado en el runtime). Si está presente, el command ejecuta
    /// el handler en vez de su `sql` directo. ARQUITECTURA.md §5.3.
    #[serde(default)]
    pub handler: Option<HandlerRef>,
    /// Si está presente, expone este command al asistente como tool (nivel 2). El permiso y el
    /// schema se heredan del propio command, no se redeclaran. ARQUITECTURA.md §9.2.
    #[serde(default)]
    pub ai: Option<AiTool>,
    /// **BORRADOR (Worker D, sin enforcement).** Política offline del comando — ver
    /// `architecture/hub/sync-hard-cases.md`. Solo se DECLARA aquí; el runtime **no la aplica
    /// todavía** (el mecanismo lo decide el humano: ledger de stock / decremento server-autoritativo).
    /// `queue` (por defecto) = append que se encola y sincroniza al volver la red; `forbid` =
    /// online-only (fiscal/VeriFactu, decrementos de stock críticos).
    #[serde(default)]
    pub offline: OfflinePolicy,
}

/// **BORRADOR (Worker D).** Política offline declarada por comando. Sin enforcement hoy.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OfflinePolicy {
    /// Se permite offline: se encola y sincroniza al recuperar la red (append). Por defecto.
    #[default]
    Queue,
    /// No se permite offline: el comando exige red (fiscal/VeriFactu, stock crítico).
    Forbid,
}

/// Referencia al handler de un command. ARQUITECTURA.md §5.3, §9.2.
///
/// - `type: "wasm"` — Tier 2: fichero `.wasm` del módulo (`file`) + función exportada.
/// - `type: "native"` — plugin nativo first-party (ADR-0009): la función vive en un
///   crate Rust horneado en el runtime, registrado por `module_id` vía
///   [`crate::Runtime::register_native`]. No lleva `file`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct HandlerRef {
    /// Tipo de handler: `"wasm"` | `"native"`.
    #[serde(rename = "type")]
    pub kind: String,
    /// Ruta (relativa a la carpeta del módulo) del `.wasm`. Solo para `type: "wasm"`.
    #[serde(default)]
    pub file: Option<String>,
    /// Función del handler a invocar (exportada del guest WASM o del plugin nativo).
    pub function: String,
}

#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Events {
    #[serde(default)]
    pub listen: HashMap<String, Listener>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Listener {
    pub command: String,
}

impl Manifest {
    /// Lee y parsea `<dir>/module.json`.
    pub fn load(dir: &Path) -> Result<Manifest> {
        let path = dir.join("module.json");
        let text = std::fs::read_to_string(&path)?;
        serde_json::from_str(&text).map_err(|source| RuntimeError::Manifest {
            path: path.display().to_string(),
            source,
        })
    }
}
