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
pub mod host_backup;
pub mod host_notify;
pub mod identity;
pub mod installer;
pub mod loader;
pub mod manifest;
pub mod migrations;
pub mod money_backfill;
pub mod native;
pub mod outbox;
pub mod permissions;
pub mod queries;
pub mod registry;
pub mod scheduler;
pub mod seed;
pub mod system_migrations;
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

/// `hub_id` de desarrollo por defecto (mismo UUID fijo que `crates/server::DEV_HUB_ID`). El host
/// real (server/Tauri) sobreescribe con el del despliegue vía [`Runtime::with_hub_id`].
pub const DEV_HUB_ID: &str = "00000000-0000-0000-0000-000000000001";

/// El runtime: une el adaptador de BD con el registro de módulos y ejecuta queries/commands.
pub struct Runtime {
    db: Box<dyn DatabaseAdapter>,
    registry: Registry,
    /// `hub_id` del despliegue (§2.5). Scoping del estado de módulos (`hub_module`) y de las
    /// migraciones de sistema. Lo inyecta el host; en tests por defecto = [`DEV_HUB_ID`].
    hub_id: String,
}

impl Runtime {
    pub fn new(db: Box<dyn DatabaseAdapter>) -> Self {
        Self { db, registry: Registry::new(), hub_id: DEV_HUB_ID.to_string() }
    }

    /// Igual que [`Runtime::new`] pero fijando el `hub_id` del despliegue (lo usa el host real;
    /// el `hub_id` viene de `HubConfig.hub_id`, inyectado por el despliegue y no spoofable).
    pub fn with_hub_id(db: Box<dyn DatabaseAdapter>, hub_id: impl Into<String>) -> Self {
        Self { db, registry: Registry::new(), hub_id: hub_id.into() }
    }

    /// `hub_id` del despliegue de este runtime.
    pub fn hub_id(&self) -> &str {
        &self.hub_id
    }

    /// Acceso al adaptador de BD subyacente. Pensado para que el **gateway multi-tenant**
    /// (`erplora-server::tenant`, hub#24) y sus tests puedan verificar el **aislamiento entre
    /// pools por org** a nivel de almacenamiento (cada org tiene su propio adaptador). En
    /// producción el camino normal sigue siendo `execute_query`/`execute_command` (gate +
    /// scoping `hub_id`); esto NO salta el gate, solo expone el adaptador ya scopeado por org.
    #[doc(hidden)]
    pub fn db_for_test(&self) -> &dyn DatabaseAdapter {
        self.db.as_ref()
    }

    /// Instala un módulo ya extraído en `dir` (lee `module.json`, migra, registra, activa).
    pub async fn install_from_dir(&mut self, dir: &Path) -> Result<String> {
        installer::install(self.db.as_ref(), &mut self.registry, &self.hub_id, dir).await
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
        // 2) Estado persistido por hub ANTES de instalar (hub#31): `install` reactiva todo al
        // re-registrar desde disco, así que capturamos aquí el activo/inactivo previo **de este
        // hub** (filtrado por `hub_id`; en BD compartida no toma el estado de otro hub) para
        // reponerlo tras instalar. Lo leemos antes porque el upsert de `install` lo sobreescribiría.
        let persisted = installer::installed_status(self.db.as_ref(), &self.hub_id).await?;

        // 3) Orden topológico por depends_on (un ciclo sí aborta: error de diseño del conjunto).
        let pairs: Vec<(String, Vec<String>)> =
            found.iter().map(|(_, m)| (m.id.clone(), m.depends_on.clone())).collect();
        let order = installer::install_order(&pairs)?;
        // 4) Instala en orden; un módulo que falle se omite (log) sin tumbar a los demás.
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

        // 5) Repón el estado inactivo previo de este hub sobre el registro recién reconstruido y
        // persístelo (el upsert del install lo había dejado `active`). Solo módulos presentes en
        // disco; un estado huérfano de un módulo ya borrado se ignora.
        for (id, status) in persisted {
            if status == ModuleStatus::Inactive && self.registry.is_installed(&id) {
                self.deactivate(&id).await?;
            }
        }
        Ok(installed)
    }

    /// Activa un módulo instalado (sus capacidades vuelven a estar disponibles).
    pub async fn activate(&mut self, module_id: &str) -> Result<()> {
        installer::set_status(self.db.as_ref(), &mut self.registry, &self.hub_id, module_id, ModuleStatus::Active).await
    }

    /// Desactiva un módulo instalado (oculta su menú y bloquea sus queries/commands).
    pub async fn deactivate(&mut self, module_id: &str) -> Result<()> {
        installer::set_status(self.db.as_ref(), &mut self.registry, &self.hub_id, module_id, ModuleStatus::Inactive).await
    }

    /// Desinstala un módulo (quita sus capacidades; no borra sus datos).
    pub async fn uninstall(&mut self, module_id: &str) -> Result<()> {
        installer::uninstall(self.db.as_ref(), &mut self.registry, &self.hub_id, module_id).await
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

    /// Registra el **transporte de `host.notify`** (ADR-0012): el cliente real de email/sms/
    /// whatsapp. Lo pone el host (server/Tauri) al arrancar. Sin él, los eventos `*.reminder.due`
    /// se entregan a sus listeners de módulo pero el envío externo es no-op.
    pub fn set_notify_transport(&mut self, transport: Arc<dyn host_notify::NotifyTransport>) {
        self.registry.notify_transport = Some(transport);
    }

    /// Registra el **transporte de `host.backup_upload`** (ADR-0040): el cliente real que empaqueta
    /// el dump del SQLite, lo cifra en cliente, pide la credencial STS/presignada al Cloud y sube el
    /// blob a S3. Lo pone el host (server/Tauri) al arrancar. Sin él, los eventos `backup.requested`
    /// se entregan a sus listeners de módulo pero la subida es no-op (capacidad no disponible).
    pub fn set_backup_transport(&mut self, transport: Arc<dyn host_backup::BackupTransport>) {
        self.registry.backup_transport = Some(transport);
    }

    /// Marca un módulo como **WhatsApp premium de ERPlora** (su canal WhatsApp sale por el proxy
    /// de Cloud con `check_quota`, ADR-0006/ADR-0012). El `tier` vive en Cloud; el host lo siembra.
    pub fn mark_premium_whatsapp(&mut self, module_id: &str) {
        self.registry.premium_whatsapp_modules.insert(module_id.to_string());
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

    /// Asegura + migra el **esquema de sistema** del runtime (hub#37). Dos fases:
    ///  1. **ensure baseline (v0):** los `CREATE TABLE IF NOT EXISTS` de las tablas de sistema
    ///     (`hub_module`, outbox `_event_outbox`/`_event_delivery`, scheduler `_scheduled_tasks`,
    ///     identidad `hub_user`/`hub_session`). Cubre el hub vacío (BD nueva sin módulos).
    ///  2. **migrate (≥ v1):** aplica en orden las migraciones de sistema versionadas que aún no
    ///     estén registradas en `_hub_system_migrations`, **scoped por el `hub_id` del despliegue**.
    ///     Así un cambio de esquema de sistema llega también a un `erplora.db` ya existente (un
    ///     `CREATE IF NOT EXISTS` no altera tablas previas — ver `system_migrations.rs`).
    ///
    /// Idempotente: re-arrancar no reaplica. El server la llama al arrancar.
    pub async fn ensure_system_tables(&self) -> Result<()> {
        // 1) Baseline v0 (idempotente).
        installer::ensure_hub_module_table(self.db.as_ref()).await?;
        outbox::ensure_tables(self.db.as_ref()).await?;
        scheduler::ensure_tables(self.db.as_ref()).await?;
        identity::ensure_tables(self.db.as_ref()).await?;
        // 2) Migraciones de sistema versionadas (≥ v1), scoped por hub_id del despliegue.
        system_migrations::apply(self.db.as_ref(), &self.hub_id).await?;
        // 3) Marcador de unidad monetaria (ADR-0007): una instalación NUEVA (esquema ya en
        // céntimos) se auto-marca `money_unit=cents` para que el backfill jamás la convierta. Un
        // hub VIEJO en euros NO se auto-marca aquí — espera a `--backfill-money` (que convierte).
        money_backfill::seed_marker_if_cents(self.db.as_ref()).await?;
        Ok(())
    }

    /// Backfill **idempotente** euros→céntimos para hubs ya desplegados (ADR-0007). No-op en
    /// instalaciones nuevas (esquema ya en céntimos) y en hubs ya convertidos (marcador
    /// `_hub_meta.money_unit=cents`). Lo invoca el subcomando `--backfill-money` del binario.
    /// SEGURO de re-ejecutar. Ver [`money_backfill`].
    pub async fn backfill_money(&self) -> Result<money_backfill::BackfillReport> {
        money_backfill::run_logged(self.db.as_ref()).await
    }

    /// Aplica un **seed de configuración inicial** (SQL idempotente) sobre la conexión del runtime,
    /// **después** de [`Runtime::ensure_system_tables`] (hub#36). Mecanismo genérico de carga de
    /// config (no es "modo demo"); la idempotencia la garantiza el propio SQL. Devuelve cuántas
    /// sentencias aplicó. Lo llama el host al arrancar si hay `HUB_SEED_SQL`/`HUB_SEED_SQL_PATH`.
    pub async fn apply_seed(&self, sql: &str) -> Result<usize> {
        seed::apply(self.db.as_ref(), sql).await
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

    /// Refresca la sesión local: rota el token opaco y extiende la expiración. `(nuevo_token, user)`
    /// o `None` si la sesión no es válida (hub#15).
    pub async fn refresh_session(&self, token: &str, ttl_secs: i64) -> Result<Option<(String, identity::HubUser)>> {
        identity::refresh_session(self.db.as_ref(), token, ttl_secs).await
    }

    /// Marca un dispositivo como de confianza (tras el primer login online). Idempotente (§2.9).
    pub async fn trust_device(&self, device_id: &str, label: &str) -> Result<()> {
        identity::trust_device(self.db.as_ref(), device_id, label).await
    }

    /// `true` si el dispositivo es de confianza (gate del login por PIN, §2.9).
    pub async fn is_device_trusted(&self, device_id: &str) -> Result<bool> {
        identity::is_device_trusted(self.db.as_ref(), device_id).await
    }

    /// Revoca la confianza de un dispositivo (perdido/robado). Idempotente (§2.9).
    pub async fn untrust_device(&self, device_id: &str) -> Result<()> {
        identity::untrust_device(self.db.as_ref(), device_id).await
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

    /// Un ciclo del barrido del **scheduler** (ADR-0011): ejecuta las scheduled tasks vencidas de
    /// los módulos activos. Lo llama el bucle de background del server (junto al relay del outbox).
    /// Devuelve cuántas tareas corrió. `hub_id` es el del despliegue (contexto de sistema).
    pub async fn process_scheduler(&self, hub_id: &str) -> Result<usize> {
        scheduler::process_once(self.db.as_ref(), &self.registry, hub_id).await
    }

    /// Catch-up del scheduler al **arrancar** (Tauri/local): ejecuta una sola vez las tareas con
    /// backlog vencido (collapse) y reprograma las demás. Lo llama el host una vez al arrancar.
    pub async fn scheduler_catch_up(&self, hub_id: &str) -> Result<usize> {
        scheduler::catch_up_on_boot(self.db.as_ref(), &self.registry, hub_id).await
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
