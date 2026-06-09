//! erplora-runtime — host genérico de módulos (ARQUITECTURA.md §4).
//!
//! Rust NO tiene lógica de negocio hardcodeada. Despachador genérico:
//!   `execute_command("pos.sale.create", payload)` / `execute_query("inventory.products.list", params)`
//!
//! Ciclo de vida (hot-plug): instalar → activar/desactivar → desinstalar. Solo los módulos
//! ACTIVOS exponen menú, queries, commands y listeners. Estado persistido en `hub_module`.

use std::path::Path;
use std::sync::Arc;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::Value as Json;

pub mod commands;
pub mod errors;
pub mod events;
pub mod installer;
pub mod loader;
pub mod manifest;
pub mod migrations;
pub mod outbox;
pub mod permissions;
pub mod queries;
pub mod registry;
pub mod ui;
pub mod wasm;

pub use errors::{Result, RuntimeError};
pub use manifest::Manifest;
pub use registry::{EventSink, ModuleStatus, NavEntry, Registry, RequestContext};

/// Descripción de un módulo instalado (para `/api/modules`).
#[derive(Debug, Clone, serde::Serialize)]
pub struct ModuleInfo {
    pub id: String,
    pub name: String,
    pub version: String,
    pub status: ModuleStatus,
}

/// El runtime: une el adaptador de BD con el registro de módulos y ejecuta queries/commands.
pub struct Runtime {
    db: Box<dyn DatabaseAdapter>,
    registry: Registry,
}

impl Runtime {
    pub fn new(db: Box<dyn DatabaseAdapter>) -> Self {
        Self { db, registry: Registry::new() }
    }

    /// Instala un módulo ya extraído en `dir` (lee `module.json`, migra, registra, activa).
    pub async fn install_from_dir(&mut self, dir: &Path) -> Result<String> {
        installer::install(self.db.as_ref(), &mut self.registry, dir).await
    }

    /// Activa un módulo instalado (sus capacidades vuelven a estar disponibles).
    pub async fn activate(&mut self, module_id: &str) -> Result<()> {
        installer::set_status(self.db.as_ref(), &mut self.registry, module_id, ModuleStatus::Active).await
    }

    /// Desactiva un módulo instalado (oculta su menú y bloquea sus queries/commands).
    pub async fn deactivate(&mut self, module_id: &str) -> Result<()> {
        installer::set_status(self.db.as_ref(), &mut self.registry, module_id, ModuleStatus::Inactive).await
    }

    /// Desinstala un módulo (quita sus capacidades; no borra sus datos).
    pub async fn uninstall(&mut self, module_id: &str) -> Result<()> {
        installer::uninstall(self.db.as_ref(), &mut self.registry, module_id).await
    }

    /// Lista de módulos instalados con su estado (para el dashboard / `/api/modules`).
    pub fn modules(&self) -> Vec<ModuleInfo> {
        self.registry
            .installed
            .iter()
            .map(|m| ModuleInfo {
                id: m.id.clone(),
                name: m.name.clone(),
                version: m.version.clone(),
                status: *self.registry.status.get(&m.id).unwrap_or(&ModuleStatus::Inactive),
            })
            .collect()
    }

    /// Registra un observador de eventos (el server lo usa para reenviar por WS).
    pub fn set_event_sink(&mut self, sink: Arc<dyn EventSink>) {
        self.registry.event_sink = Some(sink);
    }

    /// Ejecuta una query declarativa (solo si su módulo está activo) y devuelve filas JSON.
    /// Para queries de lista devuelve solo las filas de la página (compat); usa
    /// [`Runtime::execute_query_page`] si necesitas el total para paginar.
    pub async fn execute_query(&self, name: &str, params: &Params, ctx: &RequestContext) -> Result<Vec<Json>> {
        queries::execute(self.db.as_ref(), &self.registry, name, params, ctx).await
    }

    /// Ejecuta una query devolviendo la página completa (`rows` + `total` + `limit`/`offset`).
    /// Lo usa el server para queries de lista; el total alimenta el pager del `<data-table>`.
    pub async fn execute_query_page(
        &self,
        name: &str,
        params: &Params,
        ctx: &RequestContext,
    ) -> Result<queries::QueryPage> {
        queries::execute_page(self.db.as_ref(), &self.registry, name, params, ctx).await
    }

    /// ¿La query (de un módulo activo) declara bloque `list` (es paginada)? Lo usa el server
    /// para decidir la forma del `data` que devuelve por el wire.
    pub fn is_list_query(&self, name: &str) -> bool {
        self.registry.get_query(name).map(|q| q.def.list.is_some()).unwrap_or(false)
    }

    /// Ejecuta un command declarativo (solo si su módulo está activo). Los eventos emitidos se
    /// persisten en el outbox en la misma transacción; sus listeners los entrega el relay (§5.4).
    pub async fn execute_command(&self, name: &str, payload: &Params, ctx: &RequestContext) -> Result<Json> {
        commands::execute(self.db.as_ref(), &self.registry, name, payload, ctx).await
    }

    /// Crea las tablas de sistema del runtime (outbox de eventos). Idempotente; el server la llama
    /// al arrancar para cubrir el caso de hub vacío (sin módulos aún).
    pub async fn ensure_system_tables(&self) -> Result<()> {
        outbox::ensure_tables(self.db.as_ref()).await
    }

    /// Un ciclo del relay de eventos: entrega los eventos vencidos del outbox a sus listeners.
    /// Lo llama el bucle de background del server. Devuelve cuántas filas tomó (0 = nada vencido).
    pub async fn process_outbox(&self) -> Result<usize> {
        outbox::process_once(self.db.as_ref(), &self.registry).await
    }

    /// Drena el outbox hasta vaciarlo (cascada incluida). Útil al arrancar y en tests.
    pub async fn drain_outbox(&self) -> Result<usize> {
        outbox::drain(self.db.as_ref(), &self.registry).await
    }

    /// Menú dinámico de los módulos **activos** (lo consume el shell). ARQUITECTURA.md §7.7.
    pub fn navigation(&self) -> Vec<NavEntry> {
        self.registry.active_navigation().into_iter().cloned().collect()
    }

    /// Acceso de solo lectura al registro (introspección / tests).
    pub fn registry(&self) -> &Registry {
        &self.registry
    }
}

/// Inyecta los parámetros del sistema en el payload del llamador: `hub_id`, `current_user_id`,
/// `now` y `new_id`. Siempre disponibles para el SQL del módulo y no falsificables desde la UI
/// (ARQUITECTURA.md §2.5, §2.9).
pub(crate) fn system_params(base: &Params, ctx: &RequestContext) -> Params {
    let mut p = base.clone();
    p.insert("hub_id".into(), Json::String(ctx.hub_id.clone()));
    p.insert("current_user_id".into(), Json::String(ctx.user_id.clone()));
    p.insert("now".into(), Json::String(registry::now_rfc3339()));
    p.insert("new_id".into(), Json::String(registry::new_id()));
    p
}
