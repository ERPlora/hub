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
pub mod identity;
pub mod installer;
pub mod loader;
pub mod manifest;
pub mod migrations;
pub mod native;
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

    /// Instala todos los módulos de las subcarpetas de `root` (las que tienen `module.json`),
    /// **resolviendo el orden de `depends_on` por topo-sort** (hub#16): una dependencia se instala
    /// antes que quien la declara, sin depender del orden del sistema de ficheros. Devuelve los ids
    /// instalados en el orden aplicado.
    ///
    /// **Tolerante** (como el arranque original): un módulo cuyo manifest no carga o cuya
    /// instalación falla se **omite con log** y NO tumba a los demás (un módulo de terceros roto no
    /// debe brickear el hub al arrancar). Solo abortan: un `read_dir` fallido (Err) o un **ciclo**
    /// de `depends_on` (error estructural del conjunto, se reporta y no se instala nada del lote).
    pub async fn install_all_from_dir(&mut self, root: &Path) -> Result<Vec<String>> {
        // 1) Carga manifests; un manifest inválido se omite (log), no aborta el lote.
        let mut found: Vec<(std::path::PathBuf, crate::manifest::Manifest)> = Vec::new();
        for entry in std::fs::read_dir(root)? {
            let path = entry?.path();
            if !path.join("module.json").exists() {
                continue;
            }
            match crate::manifest::Manifest::load(&path) {
                Ok(manifest) => found.push((path, manifest)),
                Err(e) => eprintln!("✗ módulo {}: {e}", path.display()),
            }
        }
        // 2) Orden topológico por depends_on (un ciclo sí aborta: error de diseño del conjunto).
        let pairs: Vec<(String, Vec<String>)> =
            found.iter().map(|(_, m)| (m.id.clone(), m.depends_on.clone())).collect();
        let order = installer::install_order(&pairs)?;
        // 3) Instala en orden; un módulo que falle se omite (log) sin tumbar a los demás.
        let mut installed = Vec::with_capacity(order.len());
        for i in order {
            match self.install_from_dir(&found[i].0).await {
                Ok(id) => {
                    eprintln!("✓ módulo instalado: {id}");
                    installed.push(id);
                }
                Err(e) => eprintln!("✗ módulo {}: {e}", found[i].0.display()),
            }
        }
        Ok(installed)
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

    /// Registra un **plugin nativo first-party** (ADR-0009) para `module_id`. Los commands
    /// del módulo con `handler.type == "native"` se resuelven contra este motor. Lo llama
    /// el host (server / shell Tauri) al arrancar; no forma parte de la instalación.
    pub fn register_native(&mut self, module_id: &str, handler: Arc<dyn native::NativeHandler>) {
        self.registry.native.insert(module_id.to_string(), handler);
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

    /// Crea las tablas de sistema del runtime (outbox de eventos + identidad de usuarios/sesiones).
    /// Idempotente; el server la llama al arrancar para cubrir el caso de hub vacío (sin módulos).
    pub async fn ensure_system_tables(&self) -> Result<()> {
        outbox::ensure_tables(self.db.as_ref()).await?;
        identity::ensure_tables(self.db.as_ref()).await
    }

    // ── Identidad local (usuarios/PIN/sesiones; §2.9). La autoridad de permisos es local. ──

    /// Crea un usuario local (`pin` vacío = sin PIN). Devuelve su id.
    pub async fn create_user(&self, name: &str, pin: &str, role: &str, cloud_user_id: Option<&str>) -> Result<String> {
        identity::create_user(self.db.as_ref(), name, pin, role, cloud_user_id).await
    }

    /// Verifica el PIN de un usuario por nombre. `Some(user)` si encaja.
    pub async fn verify_pin(&self, name: &str, pin: &str) -> Result<Option<identity::HubUser>> {
        identity::verify_pin(self.db.as_ref(), name, pin).await
    }

    /// Resuelve (o provisiona) el `hub_user` vinculado a una identidad cloud (mapeo del JWT).
    pub async fn get_or_link_cloud_user(&self, cloud_user_id: &str, default_name: &str, default_role: &str) -> Result<identity::HubUser> {
        identity::get_or_link_cloud_user(self.db.as_ref(), cloud_user_id, default_name, default_role).await
    }

    /// Fija (o cambia) el PIN de un usuario existente por id (alta de PIN tras login cloud).
    pub async fn set_pin(&self, user_id: &str, pin: &str) -> Result<()> {
        identity::set_pin(self.db.as_ref(), user_id, pin).await
    }

    /// Abre una sesión server-side para `user_id`; devuelve el token opaco.
    pub async fn create_session(&self, user_id: &str, ttl_secs: i64) -> Result<String> {
        identity::create_session(self.db.as_ref(), user_id, ttl_secs).await
    }

    /// Resuelve una sesión válida a su `hub_user` activo (o `None`).
    pub async fn resolve_session(&self, token: &str) -> Result<Option<identity::HubUser>> {
        identity::resolve_session(self.db.as_ref(), token).await
    }

    /// Cierra una sesión (logout).
    pub async fn delete_session(&self, token: &str) -> Result<()> {
        identity::delete_session(self.db.as_ref(), token).await
    }

    /// Permisos efectivos del `role` (unión de `role_permissions` de los módulos activos).
    pub fn permissions_for_role(&self, role: &str) -> std::collections::HashSet<String> {
        identity::permissions_for_role(&self.registry, role)
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

    /// Ejecuta un ciclo de sync local↔cloud (ADR-0031, **primer borrador**). Reúne las tablas
    /// sincronizables de los módulos activos, las convierte en `SyncTable` y delega en el motor
    /// genérico (`erplora-datasync`). `remote` es el backend cloud (Aurora) que aporta el host
    /// (server) desde `HUB_CLOUD_DB_URL`; el local (SQLite) es la autoridad. Columna del humano:
    /// el schedule / detección de conectividad / origen del DSN per-tier los decide el humano.
    pub async fn run_sync(
        &self,
        remote: &dyn DatabaseAdapter,
        hub_id: &str,
    ) -> Result<erplora_datasync::SyncReport> {
        let tables: Vec<erplora_datasync::SyncTable> = self
            .registry
            .active_sync_tables()
            .iter()
            .map(|d| {
                let pk: Vec<&str> = d.pk.iter().map(String::as_str).collect();
                let mut t = erplora_datasync::SyncTable::new(&d.table, &pk);
                t.hub_scoped = d.hub_scoped;
                t.updated_at = d.updated_at.clone();
                t
            })
            .collect();
        erplora_datasync::SyncEngine::new(self.db.as_ref(), remote, tables)
            .sync(hub_id)
            .await
            .map_err(|e| crate::errors::RuntimeError::Sync(e.to_string()))
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
