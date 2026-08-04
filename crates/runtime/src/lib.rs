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

pub mod api_keys;
pub mod capabilities;
pub mod certificate;
pub mod commands;
pub mod e2e_support;
pub mod error_registry;
pub mod errors;
pub mod events;
pub mod export;
pub mod host_notify;
pub mod hub_users;
pub mod identity;
pub mod import;
pub mod import_sql;
pub mod installer;
pub mod loader;
pub mod manifest;
pub mod migrations;
pub mod module_storage;
pub mod money_backfill;
pub mod native;
pub mod outbox;
pub mod permissions;
pub mod queries;
pub mod registry;
pub mod reset;
pub mod scheduler;
pub mod secret_box;
pub mod seed;
pub mod settings;
pub mod system_migrations;
pub mod ui;
pub mod user_profile;
pub mod wasm;

pub use error_registry::{ErrorEvent, ErrorRegistry, ErrorSink};
pub use errors::{Result, RuntimeError};
pub use manifest::Manifest;
pub use registry::{EventSink, ModuleStatus, NavEntry, Registry, RequestContext};
// Re-export del guard de e2e para los tests de integración (ERPlora/hub#253): raíz corta
// `erplora_runtime::require_modules_workspace()` en vez del path completo del módulo.
pub use e2e_support::require_modules_workspace;

/// Descripción de un módulo instalado (para `/api/modules`).
#[derive(Debug, Clone, serde::Serialize)]
pub struct ModuleInfo {
    pub id: String,
    pub name: String,
    pub version: String,
    pub status: ModuleStatus,
    /// Dependencias declaradas (`depends_on`): la UI del shell las usa para avisar de la CASCADA
    /// (ADR-0128) antes de desactivar («también desactivará: …»).
    pub depends_on: Vec<String>,
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
        Self {
            db,
            registry: Registry::new(),
            hub_id: DEV_HUB_ID.to_string(),
        }
    }

    /// Igual que [`Runtime::new`] pero fijando el `hub_id` del despliegue (lo usa el host real;
    /// el `hub_id` viene de `HubConfig.hub_id`, inyectado por el despliegue y no spoofable).
    pub fn with_hub_id(db: Box<dyn DatabaseAdapter>, hub_id: impl Into<String>) -> Self {
        Self {
            db,
            registry: Registry::new(),
            hub_id: hub_id.into(),
        }
    }

    /// `hub_id` del despliegue de este runtime.
    pub fn hub_id(&self) -> &str {
        &self.hub_id
    }

    /// Adopta el `hub_id` real devuelto por el Cloud durante el bootstrap de la máquina.
    ///
    /// El shell Tauri arranca antes de que exista una vinculación y, por tanto, construye el
    /// runtime con [`DEV_HUB_ID`]. En cuanto el login Cloud registra el dispositivo, el host
    /// actualiza la identidad viva y llama a este método **antes de abrir la sesión local**. Desde
    /// ese instante instalaciones, ajustes, perfiles y comandos quedan scopeados por el UUID real
    /// sin exigir un reinicio de la aplicación.
    ///
    /// Esta operación pertenece exclusivamente al bootstrap: una máquina ya vinculada carga el
    /// UUID persistido antes de construir el runtime y no vuelve a cambiarlo durante su vida útil.
    pub fn adopt_hub_id(&mut self, hub_id: impl Into<String>) {
        self.hub_id = hub_id.into();
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

    /// Acceso de **solo lectura** al adaptador de BD para introspección de sistema
    /// (`/api/system`: dialecto, tamaño SQLite, conexiones Postgres). No salta el gate de
    /// permisos/scoping de `execute_query`/`execute_command` — es para métricas, no datos de negocio.
    pub fn db(&self) -> &dyn DatabaseAdapter {
        self.db.as_ref()
    }

    /// Instala un módulo ya extraído en `dir` (lee `module.json`, migra, registra, activa).
    pub async fn install_from_dir(&mut self, dir: &Path) -> Result<String> {
        installer::install(self.db.as_ref(), &mut self.registry, &self.hub_id, dir).await
    }

    /// Dependencias declaradas en el `module.json` de `dir` que aún NO están instaladas en este
    /// runtime (en el orden del manifest). Base de la **instalación anidada**: el flujo de
    /// instalación desde el Cloud (`server::install::install_from_cloud`) descarga e instala estas
    /// deps ANTES del módulo que las declara, replicando para el camino "descarga marketplace" el
    /// topo-orden que `install_all_from_dir` ya hace para los módulos horneados (hub#16). No
    /// modifica estado; solo lee el manifest y consulta el registro.
    pub fn missing_dependencies(&self, dir: &Path) -> Result<Vec<String>> {
        let manifest = crate::manifest::Manifest::load(dir)?;
        Ok(manifest
            .depends_on
            .into_iter()
            .filter(|dep| !self.registry.is_installed(dep))
            .collect())
    }

    /// Instala todos los módulos de las subcarpetas de `root` (las que tienen `module.json`),
    /// **resolviendo el orden de `depends_on` por topo-sort** (hub#16): una dependencia se instala
    /// antes que quien la declara, sin depender del orden del sistema de ficheros. Devuelve los ids
    /// instalados en el orden aplicado.
    ///
    /// **Tolerante** (como el arranque original): un módulo cuyo manifest no carga o cuya
    /// instalación falla se **omite con log** y NO tumba a los demás (un módulo de terceros roto no
    /// debe brickear el hub al arrancar). Un `root` **ausente** se trata como lote vacío (no hay
    /// módulos horneados que instalar) — el caso del contenedor stateless con `HUB_MODULES_DIR`
    /// apuntando a una ruta que el despliegue no crea (ERPlora/saas#616). Solo abortan: un
    /// `read_dir` que falla por OTRA razón (permisos, etc.) o un **ciclo** de `depends_on` (error
    /// estructural del conjunto, se reporta y no se instala nada del lote).
    pub async fn install_all_from_dir(&mut self, root: &Path) -> Result<Vec<String>> {
        // 1) Carga manifests; un manifest inválido se omite (log), no aborta el lote.
        let mut found: Vec<(std::path::PathBuf, crate::manifest::Manifest)> = Vec::new();
        // Un dir de módulos ausente NO es un error: significa "no hay módulos que instalar" (lote
        // vacío), igual que un dir presente pero vacío. Sin esto, un `HUB_MODULES_DIR` inexistente
        // (contenedor stateless) propagaba `io: No such file or directory (os error 2)` en TODOS los
        // arranques (#616). Otros errores de IO (permisos, etc.) sí se propagan.
        let entries = match std::fs::read_dir(root) {
            Ok(entries) => entries,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(e) => return Err(e.into()),
        };
        for entry in entries {
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
        let pairs: Vec<(String, Vec<String>)> = found
            .iter()
            .map(|(_, m)| (m.id.clone(), m.depends_on.clone()))
            .collect();
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
        // disco; un estado huérfano de un módulo ya borrado se ignora. Basta con reponer los
        // MANUALES: `deactivate` re-deriva la cascada (ADR-0128), así que los `inactive_auto`
        // persistidos renacen solos de su raíz — y si su raíz ya no existe, quedan activos, que
        // es lo coherente (sin causa no hay caída).
        for (id, status) in persisted {
            if status == ModuleStatus::Inactive && self.registry.is_installed(&id) {
                self.deactivate(&id).await?;
            }
        }
        Ok(installed)
    }

    /// Re-hidrata el Registry tras un REINICIO: re-registra los módulos ya instalados de ESTE hub
    /// leyéndolos de la caché de descargas (`cache_root/<id>/<version>/`). Necesario para el caso
    /// "descarga desde marketplace" (`modules_dir: None`): el estado persiste en `hub_module` + las
    /// tablas del módulo + la caché, pero el Registry en memoria arranca vacío, así que sin esto un
    /// módulo instalado "desaparece" del runtime al reiniciar (no expone queries/commands/nav).
    ///
    /// Idempotente y tolerante: salta los ya registrados (p. ej. los de `modules_dir`); un módulo
    /// cuya carpeta falte o cuyo install falle se omite con log (no tumba el arranque). `install_from_dir`
    /// reaplica migraciones sin efecto (registradas en `_hub_migrations`). Respeta el estado inactivo
    /// persistido. Devuelve los ids re-hidratados.
    pub async fn rehydrate_installed(&mut self, cache_root: &Path) -> Result<Vec<String>> {
        let persisted =
            installer::installed_status_versioned(self.db.as_ref(), &self.hub_id).await?;
        let mut out = Vec::new();
        for (id, version, status) in persisted {
            if self.registry.is_installed(&id) {
                continue; // ya re-registrado (p. ej. por modules_dir): no dupliques
            }
            let dir = cache_root.join(&id).join(&version);
            if !dir.join("module.json").exists() {
                eprintln!(
                    "✗ rehidratación {id}@{version}: sin module.json en caché ({})",
                    dir.display()
                );
                continue;
            }
            match self.install_from_dir(&dir).await {
                Ok(rid) => {
                    if status == ModuleStatus::Inactive {
                        let _ = self.deactivate(&rid).await; // repón inactivo (install lo dejó active)
                    }
                    eprintln!("✓ módulo re-hidratado: {rid}@{version}");
                    out.push(rid);
                }
                Err(e) => eprintln!("✗ rehidratación {id}@{version}: {e}"),
            }
        }
        Ok(out)
    }

    /// Módulos que `hub_module` dice **instalados** para este hub pero que **NO** quedaron
    /// registrados tras [`rehydrate_installed`] — típicamente porque su carpeta de caché no existía
    /// (contrato **stateless** de Hub Cloud: `module_cache` efímero en `/tmp`, se vacía en cada
    /// redeploy/reschedule). Devuelve `(id, version)` para que el host los **re-descargue** del
    /// marketplace (`server::install::install_from_cloud`) y el hub se auto-cure tras un reinicio
    /// sin depender de un volumen persistente. No modifica estado.
    pub async fn installed_but_unregistered(&self) -> Result<Vec<(String, String)>> {
        let persisted =
            installer::installed_status_versioned(self.db.as_ref(), &self.hub_id).await?;
        Ok(persisted
            .into_iter()
            .filter(|(id, _version, _status)| !self.registry.is_installed(id))
            .map(|(id, version, _status)| (id, version))
            .collect())
    }

    /// Activa un módulo instalado — con CASCADA en las dos direcciones (ADR-0128).
    ///
    /// El invariante es «activo ⇒ todas tus `depends_on` activas», y lo mantiene el runtime, no
    /// el admin: activar `sales` enciende también sus dependencias (el admin pidió sales; sales
    /// no existe sin ellas). Después, un barrido a punto fijo revive todo lo que cayó EN CASCADA
    /// (`InactiveAuto`) y ya tiene sus dependencias activas — lo apagado A MANO no se toca.
    pub async fn activate(&mut self, module_id: &str) -> Result<()> {
        // Cascada hacia ARRIBA: el módulo pedido + sus dependencias transitivas.
        let mut pending = vec![module_id.to_string()];
        let mut to_enable: Vec<String> = Vec::new();
        while let Some(id) = pending.pop() {
            if to_enable.contains(&id) {
                continue;
            }
            to_enable.push(id.clone());
            if let Some(m) = self.registry.installed.iter().find(|m| m.id == id) {
                pending.extend(m.depends_on.iter().cloned());
            }
        }
        for id in &to_enable {
            installer::set_status(
                self.db.as_ref(),
                &mut self.registry,
                &self.hub_id,
                id,
                ModuleStatus::Active,
            )
            .await?;
        }
        // Barrido a punto fijo: lo caído en cascada vuelve en cuanto puede.
        loop {
            let revivable: Vec<String> = self
                .registry
                .installed
                .iter()
                .filter(|m| {
                    matches!(
                        self.registry.status.get(&m.id),
                        Some(ModuleStatus::InactiveAuto)
                    ) && m.depends_on.iter().all(|d| self.registry.is_active(d))
                })
                .map(|m| m.id.clone())
                .collect();
            if revivable.is_empty() {
                break;
            }
            for id in revivable {
                installer::set_status(
                    self.db.as_ref(),
                    &mut self.registry,
                    &self.hub_id,
                    &id,
                    ModuleStatus::Active,
                )
                .await?;
            }
        }
        Ok(())
    }

    /// Desactiva un módulo instalado — y ARRASTRA a todo dependiente transitivo activo (ADR-0128).
    ///
    /// El objetivo cae como `Inactive` (decisión MANUAL: se respeta hasta que el admin lo pida de
    /// vuelta). Los arrastrados caen como `InactiveAuto`: volverán solos en cuanto sus
    /// dependencias vuelvan a estar activas.
    pub async fn deactivate(&mut self, module_id: &str) -> Result<()> {
        installer::set_status(
            self.db.as_ref(),
            &mut self.registry,
            &self.hub_id,
            module_id,
            ModuleStatus::Inactive,
        )
        .await?;
        // Cascada hacia ABAJO por el grafo inverso de depends_on, en oleadas.
        let mut fallen = vec![module_id.to_string()];
        loop {
            let wave: Vec<String> = self
                .registry
                .installed
                .iter()
                .filter(|m| {
                    self.registry.is_active(&m.id)
                        && m.depends_on.iter().any(|d| fallen.contains(d))
                })
                .map(|m| m.id.clone())
                .collect();
            if wave.is_empty() {
                break;
            }
            for id in wave {
                installer::set_status(
                    self.db.as_ref(),
                    &mut self.registry,
                    &self.hub_id,
                    &id,
                    ModuleStatus::InactiveAuto,
                )
                .await?;
                fallen.push(id);
            }
        }
        Ok(())
    }

    /// Desinstala un módulo (quita sus capacidades; no borra sus datos).
    pub async fn uninstall(&mut self, module_id: &str) -> Result<()> {
        installer::uninstall(
            self.db.as_ref(),
            &mut self.registry,
            &self.hub_id,
            module_id,
        )
        .await
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
                status: *self
                    .registry
                    .status
                    .get(&m.id)
                    .unwrap_or(&ModuleStatus::Inactive),
                depends_on: m.depends_on.clone(),
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

    /// Registra el backend persistente de módulos. El server lo resuelve a disco (Local) o al
    /// proxy Cloud→S3 (Cloud); el runtime y los módulos solo ven rutas bajo `media/modules/`.
    pub fn set_module_storage(&mut self, storage: Arc<dyn module_storage::ModuleStorage>) {
        self.registry.module_storage = Some(storage);
    }

    /// Marca un módulo como **WhatsApp premium de ERPlora** (su canal WhatsApp sale por el proxy
    /// de Cloud con `check_quota`, ADR-0006/ADR-0012). El `tier` vive en Cloud; el host lo siembra.
    pub fn mark_premium_whatsapp(&mut self, module_id: &str) {
        self.registry
            .premium_whatsapp_modules
            .insert(module_id.to_string());
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
    pub async fn execute_query(
        &self,
        name: &str,
        params: &Params,
        ctx: &RequestContext,
    ) -> Result<Vec<Json>> {
        let r = queries::execute(self.db.as_ref(), &self.registry, name, params, ctx).await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "query", name, params);
        }
        r
    }

    /// Ejecuta una query devolviendo la página completa (`rows` + `total` + `limit`/`offset`).
    /// Lo usa el server para queries de lista; el total alimenta el pager del `<data-table>`.
    pub async fn execute_query_page(
        &self,
        name: &str,
        params: &Params,
        ctx: &RequestContext,
    ) -> Result<queries::QueryPage> {
        let r = queries::execute_page(self.db.as_ref(), &self.registry, name, params, ctx).await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "query", name, params);
        }
        r
    }

    /// ¿La query (de un módulo activo) declara bloque `list` (es paginada)? Lo usa el server
    /// para decidir la forma del `data` que devuelve por el wire.
    pub fn is_list_query(&self, name: &str) -> bool {
        self.registry
            .get_query(name)
            .map(|q| q.def.list.is_some())
            .unwrap_or(false)
    }

    /// Ejecuta un command declarativo (solo si su módulo está activo). Los eventos emitidos se
    /// persisten en el outbox en la misma transacción; sus listeners los entrega el relay (§5.4).
    pub async fn execute_command(
        &self,
        name: &str,
        payload: &Params,
        ctx: &RequestContext,
    ) -> Result<Json> {
        let r = commands::execute(self.db.as_ref(), &self.registry, name, payload, ctx).await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "command", name, payload);
        }
        r
    }

    /// Como [`Runtime::execute_command`] pero con **origen INTERNO** (hub#131, hub#145): ejecuta
    /// también commands marcados internos (prefijo `_` en el último segmento, o `internal: true`),
    /// con el mismo `Origin::Internal` que el relay del Outbox y el scheduler.
    ///
    /// SOLO para el **host embebedor** del runtime (código Rust de confianza que ya tiene [`Runtime::db`]
    /// con acceso crudo): siembras de tests e2e que suplen un handler nativo/WASM no enlazado con la
    /// intención declarativa exacta que ese motor emitiría (`verifactu._insert_record`,
    /// `appointments._insert_appointment`). NINGUNA superficie externa (rutas HTTP, API pública de
    /// API keys, asistente/SDK) debe enrutar por aquí: esas pasan por [`Runtime::execute_command`],
    /// que gatea los internos con `internal_command`.
    #[doc(hidden)]
    pub async fn execute_command_internal(
        &self,
        name: &str,
        payload: &Params,
        ctx: &RequestContext,
    ) -> Result<Json> {
        let r = commands::execute_at(
            self.db.as_ref(),
            &self.registry,
            name,
            payload,
            ctx,
            0,
            &[],
            commands::Origin::Internal,
        )
        .await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "command", name, payload);
        }
        r
    }

    /// **Embudo único** de errores del dispatcher (§ error-registry). Reporta el `RuntimeError` de un
    /// `execute_command`/`execute_query` al registro global, etiquetándolo con `source="module"` +
    /// `module_id` cuando el nombre resuelve a un módulo registrado, o `source="hub"` si no (core /
    /// capacidad inexistente). Capturamos aquí — no (solo) en la capa HTTP — para cubrir también los
    /// errores de caminos no-HTTP (scheduler, relay del outbox, Tauri). Best-effort: no falla nunca.
    ///
    /// El contexto incluye el `kind`/`name` de la capacidad y las **claves** del payload (no los
    /// valores, para no arrastrar PII). El `module_id` se resuelve del registry sin filtrar por
    /// estado activo: un error sobre un command/query de un módulo desactivado igual se atribuye a él.
    fn report_dispatch_error(&self, err: &RuntimeError, kind: &str, name: &str, payload: &Params) {
        let module_id = self
            .registry
            .commands
            .get(name)
            .map(|c| c.module_id.clone())
            .or_else(|| self.registry.queries.get(name).map(|q| q.module_id.clone()));
        let source = if module_id.is_some() {
            error_registry::source::MODULE
        } else {
            error_registry::source::HUB
        };
        let payload_keys: Vec<&String> = payload.keys().collect();
        let context = serde_json::json!({ kind: name, "payload_keys": payload_keys });
        error_registry::report_runtime_error(err, source, module_id, context);
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
    pub async fn create_user(
        &self,
        name: &str,
        pin: &str,
        role: &str,
        cloud_user_id: Option<&str>,
    ) -> Result<String> {
        identity::create_user(self.db.as_ref(), name, pin, role, cloud_user_id).await
    }

    #[doc(hidden)]
    pub async fn ensure_dev_user(&self, id: &str, name: &str, role: &str) -> Result<()> {
        identity::ensure_dev_user(self.db.as_ref(), id, name, role).await
    }

    /// Verifica el PIN de un usuario por nombre. `Some(user)` si encaja.
    pub async fn verify_pin(&self, name: &str, pin: &str) -> Result<Option<identity::HubUser>> {
        identity::verify_pin(self.db.as_ref(), name, pin).await
    }

    /// Usuarios activos del hub con PIN (para mostrar el grid de login local). `(id, name, role)`.
    pub async fn list_pin_users(&self) -> Result<Vec<(String, String, String)>> {
        identity::list_pin_users(self.db.as_ref()).await
    }

    // ── Personal (core): gestión de TODOS los usuarios del hub. Ver [`hub_users`]. ──────────

    /// Todos los usuarios del hub — incluido el owner cloud sin PIN y los desactivados.
    pub async fn list_hub_users(&self) -> Result<Vec<hub_users::HubUserRow>> {
        hub_users::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Alta de un usuario del hub (nombre, rol, email y PIN opcionales). Devuelve su id.
    pub async fn create_hub_user(&self, input: &hub_users::NewHubUser) -> Result<String> {
        hub_users::create(self.db.as_ref(), &self.hub_id, input).await
    }

    /// Edición parcial de un usuario del hub; `is_active: Some(false)` es la baja.
    pub async fn update_hub_user(
        &self,
        user_id: &str,
        input: &hub_users::UpdateHubUser,
    ) -> Result<hub_users::HubUserRow> {
        hub_users::update(self.db.as_ref(), &self.hub_id, user_id, input).await
    }

    /// Roles del hub (catálogo base ∪ módulos activos ∪ en uso) con permisos y miembros.
    pub async fn list_hub_roles(&self) -> Result<Vec<hub_users::HubRole>> {
        hub_users::list_roles(self.db.as_ref(), &self.registry).await
    }

    /// **Siembra el owner del hub** desde el env del provisioning (`HUB_OWNER_EMAIL`, ADR-0157): el
    /// owner es el CREADOR del hub. Idempotente (no duplica ni cambia si ya existe). `true` si sembró.
    pub async fn seed_owner(&self, email: &str) -> Result<bool> {
        identity::seed_owner(self.db.as_ref(), email).await
    }

    /// Resuelve (o enlaza/provisiona) el `hub_user` de una identidad cloud (mapeo del JWT). Enlaza
    /// por `cloud_user_id`, si no por `email` (owner sembrado / invitado), si no crea con el rol dado.
    pub async fn get_or_link_cloud_user(
        &self,
        cloud_user_id: &str,
        default_name: &str,
        default_role: &str,
        email: Option<&str>,
    ) -> Result<identity::HubUser> {
        identity::get_or_link_cloud_user(
            self.db.as_ref(),
            cloud_user_id,
            default_name,
            default_role,
            email,
        )
        .await
    }

    /// **Alta** de un usuario-login por email + rol (flujo admin, ADR-0157 §7). Upsert por email.
    pub async fn create_login_user(&self, email: &str, role: &str) -> Result<identity::HubUser> {
        identity::create_login_user(self.db.as_ref(), email, role).await
    }

    /// **Baja** de un usuario-login por email (flujo admin, ADR-0157 §7). Desactiva; `true` si afectó.
    pub async fn deactivate_login_user(&self, email: &str) -> Result<bool> {
        identity::deactivate_login_user(self.db.as_ref(), email).await
    }

    /// Lista los usuarios-login del hub (los `hub_user` con email) para el panel admin.
    pub async fn list_login_users(&self) -> Result<Vec<identity::LoginUser>> {
        identity::list_login_users(self.db.as_ref()).await
    }

    /// Fija (o cambia) el PIN de un usuario existente por id (alta de PIN tras login cloud).
    pub async fn set_pin(&self, user_id: &str, pin: &str) -> Result<()> {
        identity::set_pin(self.db.as_ref(), user_id, pin).await
    }

    /// Abre una sesión server-side para `user_id`; devuelve el token opaco. `device_id` = identidad
    /// del dispositivo del login (o `None`); se persiste para el límite de dispositivos (ADR-0154).
    pub async fn create_session(
        &self,
        user_id: &str,
        ttl_secs: i64,
        device_id: Option<&str>,
    ) -> Result<String> {
        identity::create_session(self.db.as_ref(), user_id, ttl_secs, device_id).await
    }

    /// Aplica el límite de dispositivos del plan ANTES de abrir sesión (ADR-0154): con
    /// `max_devices == 1` y `device_id` presente, desaloja las sesiones de otros dispositivos
    /// (*single active device session* con takeover). `0` = ilimitado / sin `device_id` = no-op.
    pub async fn enforce_device_limit(
        &self,
        max_devices: u32,
        device_id: Option<&str>,
    ) -> Result<()> {
        identity::enforce_device_limit(self.db.as_ref(), max_devices, device_id).await
    }

    /// Resuelve una sesión válida a su `hub_user` activo (o `None`).
    pub async fn resolve_session(&self, token: &str) -> Result<Option<identity::HubUser>> {
        identity::resolve_session(self.db.as_ref(), token).await
    }

    /// Cierra una sesión (logout).
    pub async fn delete_session(&self, token: &str) -> Result<()> {
        identity::delete_session(self.db.as_ref(), token).await
    }

    /// Perfil y preferencias del usuario actual, aislados por `(hub_id, user_id)`.
    pub async fn user_profile(&self, user_id: &str) -> Result<user_profile::UserProfile> {
        user_profile::get(self.db.as_ref(), &self.hub_id, user_id).await
    }

    /// Actualiza únicamente el perfil del propio `user_id` resuelto por la sesión HTTP.
    pub async fn update_user_profile(
        &self,
        user_id: &str,
        input: &user_profile::UpdateUserProfile,
    ) -> Result<user_profile::UserProfile> {
        user_profile::update(self.db.as_ref(), &self.hub_id, user_id, input).await
    }

    /// Guarda la ruta relativa de la foto del usuario dentro de `media_dir`.
    pub async fn set_user_avatar(
        &self,
        user_id: &str,
        avatar_path: &str,
    ) -> Result<user_profile::UserProfile> {
        user_profile::set_avatar(self.db.as_ref(), &self.hub_id, user_id, avatar_path).await
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

    /// Permisos de una **sesión** con ese rol: los de los módulos + el permiso del core
    /// (`hub.users.view`, ADR-0192). Es lo que debe usar el gate de auth al abrir sesión.
    pub fn session_permissions(&self, role: &str) -> std::collections::HashSet<String> {
        identity::session_permissions(&self.registry, role)
    }

    /// Permisos efectivos del `role` (unión de `role_permissions` de los módulos activos).
    pub fn permissions_for_role(&self, role: &str) -> std::collections::HashSet<String> {
        identity::permissions_for_role(&self.registry, role)
    }

    // ── API pública por módulo: API keys (ADR-0057, public-api.md) ──────────────────────────

    /// Crea una API key para el `hub_id` del despliegue con `scope` (matriz módulo×{r,w}). Devuelve
    /// el token en claro **una sola vez**. `created_by` = identidad del admin que la crea.
    pub async fn create_api_key(
        &self,
        name: &str,
        scope: &[api_keys::ScopeEntry],
        rate_limit_per_minute: i64,
        created_by: &str,
    ) -> Result<api_keys::ApiKeySecret> {
        api_keys::create(self.db.as_ref(), &self.hub_id, name, scope, rate_limit_per_minute, created_by).await
    }

    /// Lista las API keys del hub (sin secreto), recientes primero.
    pub async fn list_api_keys(&self) -> Result<Vec<api_keys::ApiKeyInfo>> {
        api_keys::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Rota el secreto de una key (nuevo secreto, invalida el anterior). `None` si no existe.
    pub async fn rotate_api_key(&self, id: &str) -> Result<Option<api_keys::ApiKeySecret>> {
        api_keys::rotate(self.db.as_ref(), &self.hub_id, id).await
    }

    /// Revoca una key (kill-switch inmediato). `false` si no existía.
    pub async fn revoke_api_key(&self, id: &str) -> Result<bool> {
        api_keys::revoke(self.db.as_ref(), &self.hub_id, id).await
    }

    /// Verifica un token `erpl_live_…` y lo resuelve al `RequestContext` (con los permisos del
    /// scope expandido contra el Registry). `None` = token inválido/revocado (el server → 401).
    pub async fn resolve_api_key(&self, token: &str) -> Result<Option<api_keys::ApiKeyPrincipal>> {
        api_keys::verify_and_resolve(self.db.as_ref(), &self.registry, &self.hub_id, token).await
    }

    /// Consume una petición de la cuota durable de una API key autenticada.
    pub async fn consume_api_key_rate_limit(
        &self,
        principal: &api_keys::ApiKeyPrincipal,
    ) -> Result<api_keys::RateLimitDecision> {
        api_keys::consume_rate_limit(self.db.as_ref(), &principal.key_id, principal.rate_limit_per_minute).await
    }

    // ── Settings del hub (store key/value de sistema, scoped por hub_id) ────────────────────────

    /// Lee TODOS los settings conocidos del hub del despliegue: filas persistidas mezcladas sobre
    /// los defaults de las claves conocidas (objeto JSON completo). Lectura barata sin gate de rol;
    /// el server la expone a cualquier sesión de usuario válida.
    pub async fn get_settings(&self) -> Result<Json> {
        settings::get_all(self.db.as_ref(), &self.hub_id).await
    }

    /// Aplica un mapa parcial de settings (valida cada clave conocida; rechaza desconocidas o
    /// valores inválidos antes de tocar la BD) y devuelve el objeto completo actualizado. El gate
    /// de rol (owner/admin) lo aplica el server. `updated_by` audita quién hizo el cambio.
    pub async fn set_settings(
        &self,
        updates: &serde_json::Map<String, Json>,
        updated_by: &str,
    ) -> Result<Json> {
        settings::set_many(self.db.as_ref(), &self.hub_id, updates, updated_by).await
    }

    /// Capabilities DECLARADAS por un módulo con su estado de grant (ADR-0079). Para
    /// `GET /api/modules/:id/capabilities`. Lista vacía = el módulo no pide permisos.
    pub async fn module_capabilities(&self, module_id: &str) -> Result<Vec<(String, bool)>> {
        capabilities::list_for_module(self.db.as_ref(), &self.registry, &self.hub_id, module_id)
            .await
    }

    /// Concede/revoca una capability de un módulo (ADR-0079). `by` = `hub_user:<id>` admin.
    pub async fn set_module_capability(
        &self,
        module_id: &str,
        capability: &str,
        granted: bool,
        by: &str,
    ) -> Result<()> {
        capabilities::set_grant(
            self.db.as_ref(),
            &self.registry,
            &self.hub_id,
            module_id,
            capability,
            granted,
            by,
        )
        .await
    }

    /// Sube/reemplaza el certificado fiscal del negocio (ADR-0079). `by` = `hub_user:<id>` admin.
    pub async fn set_business_certificate(
        &self,
        pkcs12_b64: &str,
        password: &str,
        by: &str,
    ) -> Result<()> {
        certificate::set(self.db.as_ref(), &self.hub_id, pkcs12_b64, password, by).await
    }

    /// Estado del certificado del negocio (presente/ausente + metadatos; sin bytes ni contraseña).
    pub async fn business_certificate_status(&self) -> Result<Json> {
        certificate::status(self.db.as_ref(), &self.hub_id).await
    }

    /// Elimina el certificado del negocio.
    pub async fn delete_business_certificate(&self) -> Result<()> {
        certificate::delete(self.db.as_ref(), &self.hub_id).await
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
        self.registry
            .active_navigation()
            .into_iter()
            .cloned()
            .collect()
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
    // Identidad de NEGOCIO GLOBAL del hub (fuente única país-agnóstica, hub_settings — ADR-0061) —
    // disponible como `:business_tax_id`/`:business_legal_name`/`:business_address` en TODO el SQL de
    // comandos (incl. operaciones de handlers WASM/nativos), para que los módulos resuelvan el emisor
    // sin que el caller lo pase.
    p.insert(
        "business_tax_id".into(),
        Json::String(ctx.business_tax_id.clone()),
    );
    p.insert(
        "business_legal_name".into(),
        Json::String(ctx.business_legal_name.clone()),
    );
    p.insert(
        "business_address".into(),
        Json::String(ctx.business_address.clone()),
    );
    // Presencia del certificado fiscal del negocio (`_hub_certificate`, core — ADR-0081), como 0/1
    // para que el SQL del módulo lo use sin leer la tabla de sistema (p.ej. verifactu.config.get →
    // has_certificate / gate de "Probar" / setup.configured_when).
    p.insert(
        "has_certificate".into(),
        Json::from(if ctx.has_certificate { 1 } else { 0 }),
    );
    p
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::registry::{ModuleStatus, RegisteredCommand, RequestContext};
    use erplora_db::testutil::fresh_db;

    fn underscore_cmd(module: &str, sql: &str) -> RegisteredCommand {
        RegisteredCommand {
            module_id: module.to_string(),
            def: manifest::CommandDef {
                permission: format!("{module}.write"),
                reads: Vec::new(),
                transaction: false,
                sql: vec![],
                schema: None,
                emit: vec![],
                min_affected_rows: None,
                handler: None,
                ai: None,
                expose_api: false,
                internal: false,
            },
            sql: vec![sql.to_string()],
            wasm: None,
            schema: None,
        }
    }

    /// hub#131/#145: [`Runtime::execute_command`] (la puerta PÚBLICA del embedder, la única que
    /// exponen las rutas HTTP/API keys) rechaza un command interno `_` con `InternalCommand`;
    /// [`Runtime::execute_command_internal`] (host embebedor de confianza: siembras de e2e que
    /// suplen un handler nativo/WASM no enlazado) SÍ lo ejecuta — mismo `Origin::Internal` que el
    /// relay del Outbox y el scheduler — y el SQL declarativo del command corre de verdad.
    #[tokio::test]
    async fn public_gate_rejects_underscore_but_internal_entrypoint_runs_it() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();

        let mut rt = Runtime::new(Box::new(db));
        rt.registry
            .status
            .insert("appointments".to_string(), ModuleStatus::Active);
        rt.registry.commands.insert(
            "appointments._insert_appointment".to_string(),
            underscore_cmd("appointments", "INSERT INTO t (n) VALUES (1);"),
        );
        // Identidad de negocio ya rellena → `execute_at` no re-lee `hub_settings` (mismo patrón
        // que `ctx_admin()` en los tests del gate de `commands.rs`).
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]).with_business(
            "B00000000",
            "ACME Test",
            "Calle Falsa 123",
        );

        let err = rt
            .execute_command("appointments._insert_appointment", &Params::new(), &ctx)
            .await
            .unwrap_err();
        assert!(
            matches!(err, RuntimeError::InternalCommand(_)),
            "la puerta pública del embedder debe rechazar el command `_`: {err:?}"
        );

        rt.execute_command_internal("appointments._insert_appointment", &Params::new(), &ctx)
            .await
            .expect("la puerta interna del embedder debe ejecutar el command `_`");
        let r = rt
            .db()
            .query("SELECT COUNT(*) AS c FROM t WHERE n = 1", &Params::new())
            .await
            .unwrap();
        let c = r.rows[0]["c"]
            .as_i64()
            .or_else(|| r.rows[0]["c"].as_f64().map(|f| f as i64))
            .unwrap_or(-1);
        assert_eq!(c, 1, "el SQL del command interno debe haberse ejecutado");
    }
}
