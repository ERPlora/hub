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
    /// Resumen del módulo para el routing del asistente (nivel 1). ARQUITECTURA.md §9.2b.
    #[serde(default)]
    pub agent: Option<Agent>,
    /// Conocimiento del módulo para RAG (§9.4) — aparcado/en diseño. Se captura tal cual.
    #[serde(default)]
    pub ai_context: Option<serde_json::Value>,
    /// Tareas programadas del módulo (ADR-0011). Cada una ejecuta un command del **propio
    /// módulo** cuando vence su `cron`, sin usuario (contexto de sistema). Se vuelcan a la tabla
    /// de sistema `_scheduled_tasks` al instalar (idempotente). Ver `scheduler.rs`.
    #[serde(default)]
    pub scheduled_tasks: Vec<ScheduledTaskDef>,
    /// Capacidad `host.notify` de alto nivel (ADR-0012): qué canales de notificación
    /// (`email`/`sms`/`whatsapp`) declara necesitar el módulo. El host resuelve DÓNDE viven
    /// los secretos/cuota por canal y por `tier`; el módulo solo declara qué canal usa.
    #[serde(default)]
    pub notify: Option<NotifyCapability>,
    /// Capacidad `http.fetch` mediada (ADR-0012, campo `network` ya en el schema): allowlist de
    /// hosts y secretos que el host inyecta. El WASM no tiene red; el runtime hace la llamada.
    #[serde(default)]
    pub network: Option<NetworkCapability>,
}

/// Una tarea programada declarada en el manifest (ADR-0011). Espejo de `$defs/scheduledTask`
/// en `schemas/module.schema.json`. El `command` debe pertenecer al **propio módulo** (mismo
/// aislamiento que el handler WASM); se valida al volcar la tarea a `_scheduled_tasks`.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ScheduledTaskDef {
    /// Nombre único de la tarea **dentro del módulo** (clave de idempotencia con `module_id`).
    pub name: String,
    /// Command del propio módulo a ejecutar al vencer el cron (sin usuario).
    pub command: String,
    /// Expresión cron de 5 campos (`min hora dom mes dow`) o atajo (`@daily`, `@hourly`…).
    /// Ver `scheduler::cron` para la gramática soportada.
    pub cron: String,
    /// Payload fijo que recibe el command en cada ejecución (opcional).
    #[serde(default)]
    pub payload: Option<serde_json::Value>,
    /// Comportamiento de catch-up tras un apagado (ADR-0011): `collapse` (por defecto) ejecuta
    /// **una sola vez** el backlog al arrancar; `skip` no ejecuta nada vencido durante el apagado
    /// y solo reprograma. (No hay modo "run-all": el ADR fija collapse para tareas idempotentes.)
    #[serde(default)]
    pub catch_up: CatchUp,
}

/// Política de catch-up de una scheduled task tras un periodo apagado (ADR-0011).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum CatchUp {
    /// Ejecuta una sola vez si había backlog vencido (idempotente). Por defecto.
    #[default]
    Collapse,
    /// No ejecuta el backlog; solo reprograma al siguiente vencimiento.
    Skip,
}

/// Bloque `notify` del manifest (ADR-0012): los canales de alto nivel que usa el módulo.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct NotifyCapability {
    /// Canales declarados (`email`/`sms`/`whatsapp`).
    #[serde(default)]
    pub channels: Vec<String>,
}

/// Bloque `network` del manifest (ADR-0012, §5.5): allowlist de `http.fetch` mediado.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct NetworkCapability {
    /// Hosts/patrones permitidos para las llamadas salientes mediadas por el host.
    #[serde(default)]
    pub allow: Vec<String>,
    /// Nombres de secretos del hub que el host inyecta en las llamadas (no su valor).
    #[serde(default)]
    pub secrets: Vec<String>,
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
