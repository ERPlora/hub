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
use serde_json::{json, Value as Json};

pub mod access_email;
pub mod api_keys;
pub mod capabilities;
pub mod certificate;
pub mod certificate_refetch;
pub mod commands;
pub mod device_mode;
pub mod devices;
pub mod e2e_support;
pub mod elevation;
pub mod error_registry;
pub mod errors;
pub mod event_shape;
pub mod events;
pub mod export;
pub mod fiscal_profile;
pub mod flows;
pub mod host_notify;
pub mod hub_meta;
pub mod hub_users;
pub mod identity;
pub mod import;
pub mod import_sql;
pub mod installer;
pub mod loader;
pub mod manifest;
pub mod migration_guard;
pub mod migrations;
pub mod module_package;
pub mod module_storage;
pub mod module_update;
pub mod money_backfill;
pub mod native;
pub mod outbox;
pub mod permissions;
pub mod pin_policy;
pub mod print_drain;
pub mod print_hosts;
pub mod print_queue;
pub mod print_stations;
pub mod producer_facts;
pub mod queries;
pub mod registry;
pub mod reset;
pub mod retention;
pub mod roles;
pub mod scheduler;
pub mod secret_box;
pub mod seed;
pub mod settings;
pub mod setup_status;
pub mod system_migrations;
pub mod ui;
pub mod update_history;
pub mod user_profile;
pub mod wasm;
pub mod wasm_cache;

pub use error_registry::{ErrorEvent, ErrorRegistry, ErrorSink};
pub use errors::{DemoLock, Result, RuntimeError};
pub use manifest::{Manifest, ManifestWarning, CORE_VERSION};
pub use module_update::ModuleUpdate;
pub use registry::{
    AutomationCtx, EventSink, EventSource, ModuleSnapshot, ModuleStatus, NavEntry, Principal,
    Registry, RequestContext,
};
// Re-export del guard de e2e para los tests de integración (ERPlora/hub#253): raíz corta
// `erplora_runtime::require_modules_workspace()` en vez del path completo del módulo.
// `modules_root` travels with the guard on purpose: a test that resolves module paths by hand
// diverges from the guard and reintroduces hub#253 (the guard says "run", every path is wrong,
// the test skips itself and still reports `ok`).
pub use e2e_support::{modules_root, require_modules_workspace};

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
    /// What this core did not understand of the module's manifest and installed anyway (hub#521).
    ///
    /// Empty for every module that fits the contract, which is all 24 published ones bar the two
    /// carrying a retired `validates`. It travels here — and not only to a log — because "the hub
    /// ignores it in silence" is not fixed by writing the silence down somewhere nobody looks:
    /// whoever is staring at a module that half works has to be able to ASK.
    pub manifest_warnings: Vec<crate::manifest::ManifestWarning>,
}

/// **What one event set off** (hub#666): the event itself, the flow runs it started and the events
/// its delivery caused. One level of the chain, because a transitive walk is a single query that
/// can traverse the whole outbox — the caller follows the links it cares about.
#[derive(Debug, Clone, serde::Serialize)]
pub struct EventTrace {
    pub event: outbox::CorrelatedEvent,
    pub runs: Vec<flows::FlowRun>,
    pub caused: Vec<outbox::CorrelatedEvent>,
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
    /// Live **step-up approvals** (hub#361). In memory and nowhere else: an approval describes
    /// somebody standing at the till right now, so it dies with the process on purpose — see
    /// [`elevation`] for why persisting it would be worse than losing it.
    elevation: elevation::Grants,
}

/// Cuánto espera un arranque por el lock de migración antes de rendirse.
///
/// 120 s por defecto: el que espera es el arranque NUEVO del solape blue/green, y lo que espera es
/// a que el viejo —o el otro nuevo— termine de migrar. Las migraciones son aditivas por contrato
/// (ADR-0269), así que duran segundos; el margen es para un backfill lento, no para una espera
/// normal. Ajustable con `HUB_MIGRATION_LOCK_TIMEOUT_MS` por si algún hub tiene un histórico gordo.
fn migration_lock_timeout_ms() -> u64 {
    std::env::var("HUB_MIGRATION_LOCK_TIMEOUT_MS")
        .ok()
        .and_then(|raw| raw.trim().parse().ok())
        .unwrap_or(120_000)
}

impl Runtime {
    pub fn new(db: Box<dyn DatabaseAdapter>) -> Self {
        Self {
            db,
            registry: Registry::new(),
            hub_id: DEV_HUB_ID.to_string(),
            elevation: elevation::Grants::new(),
        }
    }

    /// Igual que [`Runtime::new`] pero fijando el `hub_id` del despliegue (lo usa el host real;
    /// el `hub_id` viene de `HubConfig.hub_id`, inyectado por el despliegue y no spoofable).
    pub fn with_hub_id(db: Box<dyn DatabaseAdapter>, hub_id: impl Into<String>) -> Self {
        Self {
            db,
            registry: Registry::new(),
            hub_id: hub_id.into(),
            elevation: elevation::Grants::new(),
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

    /// Actualiza a la versión ya extraída en `dir` un módulo que **ya está instalado** (hub#516).
    ///
    /// Es la misma puerta que [`install_from_dir`](Self::install_from_dir) —el paquete llega
    /// verificado (SHA256 + firma ed25519) y su manifest se valida igual—, con dos diferencias que
    /// solo existen aquí:
    ///
    /// - **Se exige que el módulo esté instalado.** Actualizar lo que no hay no es actualizar; sin
    ///   esto, un id mal escrito instalaría un módulo nuevo en silencio.
    /// - **Devuelve la transición `from → to`**, que es lo que el dueño ve (ADR-0269 §3.5) y lo que
    ///   la incidencia pregunta primero: qué cambió y desde dónde.
    ///
    /// Solo se aplican las migraciones que la versión nueva **añade** (`_hub_migrations` dedupe por
    /// fichero), y si el intento falla **sigue corriendo la versión anterior** — lo garantiza
    /// `installer::install`, no este método.
    pub async fn update_from_dir(&mut self, dir: &Path) -> Result<ModuleUpdate> {
        let manifest = crate::manifest::Manifest::load(dir)?;
        let from = self
            .registry
            .installed
            .iter()
            .find(|m| m.id == manifest.id)
            .map(|m| m.version.clone())
            .ok_or_else(|| {
                RuntimeError::CommandNotFound(format!("módulo no instalado: {}", manifest.id))
            })?;

        let module_id =
            installer::install(self.db.as_ref(), &mut self.registry, &self.hub_id, dir).await?;
        Ok(ModuleUpdate {
            module_id,
            from,
            to: manifest.version,
        })
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
            .filter(|dep| !self.registry.is_installed(&dep.id))
            .map(|dep| dep.id)
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
            .map(|(_, m)| {
                (
                    m.id.clone(),
                    m.depends_on.iter().map(|d| d.id.clone()).collect(),
                )
            })
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
                // `_unchecked`: reponer un estado ya persistido no es una decisión nueva, así que
                // no pasa por el retention gate (hub#314) — si lo hiciera, un módulo con registros
                // sin remitir tumbaría el arranque o resucitaría apagado por el admin.
                self.deactivate_unchecked(&id).await?;
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
                        // `_unchecked`: repón inactivo (install lo dejó active). Es estado ya
                        // persistido, no una decisión nueva → sin retention gate (hub#314).
                        let _ = self.deactivate_unchecked(&rid).await;
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
                pending.extend(m.depends_on.iter().map(|d| d.id.clone()));
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
                    ) && m.depends_on.iter().all(|d| self.registry.is_active(&d.id))
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

    /// Módulos que caerían al desactivar `module_id`: él mismo + todo dependiente transitivo hoy
    /// activo (ADR-0128). Puro (no muta): es el conjunto que la cascada de [`Self::deactivate`]
    /// apagaría, calculado ANTES para poder revisarlo entero (hub#314).
    fn deactivation_cascade(&self, module_id: &str) -> Vec<String> {
        let mut fallen = vec![module_id.to_string()];
        loop {
            let wave: Vec<String> = self
                .registry
                .installed
                .iter()
                .filter(|m| {
                    self.registry.is_active(&m.id)
                        && !fallen.contains(&m.id)
                        && m.depends_on.iter().any(|d| fallen.contains(&d.id))
                })
                .map(|m| m.id.clone())
                .collect();
            if wave.is_empty() {
                return fallen;
            }
            fallen.extend(wave);
        }
    }

    /// Retention gate (hub#314, ADR-0202 R2) sobre un módulo: pregunta a su motor nativo qué debe
    /// todavía a una autoridad externa y falla si queda algo. Ver
    /// [`installer::ensure_no_pending_obligations`].
    async fn ensure_module_can_go(&self, module_id: &str) -> Result<()> {
        // El host deja los motores nativos registrados aunque este hub no tenga el módulo. La
        // gate protege a un módulo que SE VA: si no está, no hay nada que proteger y quien llama
        // debe seguir viendo su «módulo no instalado» de siempre, no un rechazo de retención.
        if !self.registry.is_installed(module_id) {
            return Ok(());
        }
        let host = native::DbHost {
            db: self.db.as_ref(),
            storage: None,
            hub_id: &self.hub_id,
            module_id,
            static_folder: None,
        };
        installer::ensure_no_pending_obligations(&host, &self.registry, &self.hub_id, module_id)
            .await
    }

    /// Desactiva un módulo instalado — y ARRASTRA a todo dependiente transitivo activo (ADR-0128).
    ///
    /// El objetivo cae como `Inactive` (decisión MANUAL: se respeta hasta que el admin lo pida de
    /// vuelta). Los arrastrados caen como `InactiveAuto`: volverán solos en cuanto sus
    /// dependencias vuelvan a estar activas.
    ///
    /// hub#314: antes de tocar nada se revisa el conjunto ENTERO que caería. Apagar `invoice`
    /// arrastra a `verifactu`, así que gatear solo el objetivo dejaría la puerta de atrás abierta:
    /// si CUALQUIERA de los que caen aún debe registros sin remitir, no cae ninguno.
    pub async fn deactivate(&mut self, module_id: &str) -> Result<()> {
        let cascade = self.deactivation_cascade(module_id);
        // ADR-0273 D5 (hub#553): **el candado del CORE va PRIMERO**, y sobre el conjunto entero.
        // R2 le pregunta al motor cuánto debe; éste no pregunta a nadie, porque un módulo no puede
        // tener voto sobre si se le puede quitar. Y con la cola vacía R2 deja marchar al último
        // proveedor: la cola vacía protege el pasado, el daño lo hacen las ventas siguientes.
        self.ensure_fiscal_provider_remains(&cascade).await?;
        for id in cascade {
            self.ensure_module_can_go(&id).await?;
        }
        self.deactivate_unchecked(module_id).await
    }

    /// Comprueba el candado de proveedor fiscal (ADR-0273 D5) contra el conjunto que se va.
    ///
    /// Sin perfil todavía —un hub que nunca arrancó del todo— no hay nada que proteger: leer no
    /// puede ser la razón de que no se pueda desinstalar un módulo.
    async fn ensure_fiscal_provider_remains(&self, leaving: &[String]) -> Result<()> {
        let Some(profile) = fiscal_profile::load(self.db.as_ref(), &self.hub_id).await? else {
            return Ok(());
        };
        fiscal_profile::ensure_provider_remains(&profile, &self.registry, leaving)
    }

    /// [`Self::deactivate`] SIN el retention gate: repone un estado inactivo YA persistido
    /// (arranque/rehidratación), que no es una decisión nueva del admin. Gatearlo aquí solo podría
    /// tumbar el arranque o resucitar un módulo que el admin había apagado (hub#314).
    async fn deactivate_unchecked(&mut self, module_id: &str) -> Result<()> {
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
                        && m.depends_on.iter().any(|d| fallen.contains(&d.id))
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
    ///
    /// hub#314: se rechaza mientras su motor deba trabajo a una autoridad externa — borrar la fila
    /// de `hub_module` con registros sin remitir los dejaba huérfanos (VeriFactu FAQ §5).
    pub async fn uninstall(&mut self, module_id: &str) -> Result<()> {
        // ADR-0273 D5 (hub#553): antes que R2, y por la misma razón — con la cola vacía R2 deja
        // marchar al último proveedor, y desde ese momento el hub vende sin que nadie registre.
        self.ensure_fiscal_provider_remains(&[module_id.to_string()])
            .await?;
        self.ensure_module_can_go(module_id).await?;
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
                depends_on: m.depends_on.iter().map(|d| d.id.clone()).collect(),
                manifest_warnings: m.warnings.clone(),
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

    /// Sella que este despliegue es un hub de **DEMO efímera** (ADR-0197, hub#376). Lo llama el
    /// host UNA vez al arrancar con `HubConfig.demo` (env `HUB_DEMO`, que solo escribe el
    /// provisioning del SaaS), igual que sella el `event_sink` o el `notify_transport`.
    ///
    /// Es `&mut self` a propósito: se pone mientras se construye el runtime, antes de servir. No
    /// hay endpoint, comando ni setting que lo cambie después — ni para encenderlo (un hub real que
    /// se declarase demo dejaría de remitir sus ventas) ni para apagarlo (una demo que se declarase
    /// real remitiría a la AEAT de verdad).
    pub fn set_demo_hub(&mut self, demo: bool) {
        self.registry.demo_hub = demo;
    }

    /// ¿Es este despliegue un hub de demo efímera? (ADR-0197). Lectura del marcador que selló el
    /// host; el server la expone en `/api/hub/context` para que la UI se explique.
    pub fn is_demo_hub(&self) -> bool {
        self.registry.demo_hub
    }

    /// Fills in the fiscal identity of a **DEMO** hub at boot (hub#684), and does nothing at all in
    /// a real one. See [`settings::ensure_demo_fiscal_identity`] for why the demo needs the data
    /// written rather than the checklist taught to look away.
    ///
    /// The `demo_hub` guard lives HERE, next to the marker the host seals, and not inside the
    /// settings function: a real hub that woke up with a tax id it never typed would invoice under
    /// it, and ADR-0273 freezes that id at the first record — the mistake would be permanent.
    pub async fn ensure_demo_fiscal_identity(&self) -> Result<bool> {
        if !self.registry.demo_hub {
            return Ok(false);
        }
        settings::ensure_demo_fiscal_identity(self.db.as_ref(), &self.hub_id).await
    }

    /// Cierra una puerta en un hub de demo (ADR-0197 §4). Devuelve el error con el SUJETO del
    /// cierre, para que el cliente sepa cuál de los tres se negó.
    fn refuse_if_demo(&self, lock: DemoLock) -> Result<()> {
        if self.registry.demo_hub {
            return Err(RuntimeError::DemoLocked { lock });
        }
        Ok(())
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

    /// ¿La query (de un módulo activo — o del core, hub#884) declara bloque `list` (es paginada)?
    /// Lo usa el server para decidir la forma del `data` que devuelve por el wire.
    pub fn is_list_query(&self, name: &str) -> bool {
        hub_users::is_core_list_query(name)
            || self
                .registry
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
        let r = commands::execute(
            self.db.as_ref(),
            &self.registry,
            name,
            payload,
            ctx,
            &self.elevation,
        )
        .await;
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
            // The embedder seeding e2e data is the runtime calling itself: no approval to spend.
            None,
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
        // 🔒 UN solo arranque toca el esquema a la vez (hub#539).
        //
        // Con `order: start-first` (ADR-0269) hay **dos procesos del mismo hub contra la misma
        // base** en cada actualización, y los dos corren esto entero. Sin lock pueden leer el mismo
        // `max_applied_version` y aplicar la misma migración a la vez: `CREATE TABLE` sin
        // `IF NOT EXISTS` da 42P07, un `ALTER` deja el esquema a medias y el `INSERT` de control
        // choca contra la PK. El segundo espera, entra, y se encuentra el trabajo hecho —
        // todo lo de abajo es idempotente.
        //
        // Envuelve la función ENTERA y no solo `system_migrations::apply`: el baseline v0, el
        // marcador monetario y los backfills de más abajo escriben esquema y datos igual.
        //
        // Si no lo consigue, **falla el arranque**. Es deliberado: seguir sin él es migrar en
        // paralelo, y con `/readyz` de verdad (hub#538) un arranque fallido dispara el rollback en
        // vez de matar a la tarea que sí funcionaba.
        let _migration_lock = self
            .db
            .migration_lock(&self.hub_id, migration_lock_timeout_ms())
            .await
            .map_err(|error| RuntimeError::Domain {
                code: "hub.migration_lock_timeout".into(),
                message: error.to_string(),
            })?;

        // 1) Baseline v0 (idempotente).
        installer::ensure_hub_module_table(self.db.as_ref()).await?;
        // El ledger de migraciones de MÓDULO nace AQUÍ, no con la primera migración: el readiness
        // (`/readyz`, hub#538) lo consulta en cada latido, y en un hub RECIÉN NACIDO —cero
        // módulos— «relation _hub_migrations does not exist» era DOWN → 503 → el healthcheck de
        // Swarm mataba la tarea → `deployment_status=error`. Ningún hub nuevo podía aprovisionarse
        // (2026-08-09); los tests no lo veían porque su fixture creaba la tabla A MANO, cosa que
        // el boot real no hacía.
        migrations::ensure_table(self.db.as_ref()).await?;
        outbox::ensure_tables(self.db.as_ref()).await?;
        scheduler::ensure_tables(self.db.as_ref()).await?;
        identity::ensure_tables(self.db.as_ref()).await?;
        // 2) Migraciones de sistema versionadas (≥ v1), scoped por hub_id del despliegue.
        system_migrations::apply(self.db.as_ref(), &self.hub_id).await?;
        // 2a) Índices de las tablas de flujo que su migración creadora no podía prever (hub#666).
        // Va DESPUÉS de `apply` porque las tablas tienen que existir. No es migración numerada a
        // propósito: un índice no cambia la forma del dato y `IF NOT EXISTS` no cuesta nada en el
        // segundo arranque — mismo criterio que las columnas del outbox por su `ENSURE_TABLES`.
        flows::store::ensure_indexes(self.db.as_ref()).await?;
        // 2a-bis) The `wake_at` of the runs parked before hub#970, re-written in UTC. Same
        // criterion as 2b below: an invariant over data, not a schema change — the write side is
        // already fixed, but a run that is ALREADY asleep is only ever read by the very comparison
        // the offset breaks, so nothing else would reach it. Re-running it is a no-op.
        flows::store::normalize_wake_at(self.db.as_ref(), &self.hub_id).await?;
        // 2b) The device row an id that names the HUB left behind (hub#454). Not a versioned
        // migration on purpose: it is an invariant, not a schema change — it must also clean a
        // database restored from a backup taken before the fix, and re-running it is a no-op.
        identity::forget_hub_id_as_device(self.db.as_ref(), &self.hub_id).await?;
        // 2c) The hub's FISCAL PROFILE (ADR-0273, hub#549): what this hub owes, resolved from its
        // country and persisted by the core. It runs here — on the boot path every hub takes —
        // precisely so that owing VeriFactu is never a consequence of having installed something.
        // It only resolves and records; nothing rejects anything yet (hub#550/#556).
        fiscal_profile::ensure(self.db.as_ref(), &self.hub_id).await?;
        // 3) Marcador de unidad monetaria (ADR-0007): una instalación NUEVA (esquema ya en
        // céntimos) se auto-marca `money_unit=cents` para que el backfill jamás la convierta. Un
        // hub VIEJO en euros NO se auto-marca aquí — espera a `--backfill-money` (que convierte).
        money_backfill::seed_marker_if_cents(self.db.as_ref()).await?;
        // 4) Lo que el backfill de la v19 NO pudo decidir (hub#436): filas cuyo email vive solo en
        // el perfil y choca con otra identidad, así que su baja **no revoca** nada. No se adivina
        // —fusionar dos personas es peor que dejar una fila señalada—: se imprime en cada arranque
        // para que alguien lo mire. Consulta VIVA, no una foto: se calla sola al resolverse.
        //
        // **No aborta el arranque.** Es un aviso, no un paso del bootstrap: un hub que no abre es
        // una tienda que no cobra, y eso es mucho peor que un aviso que falta. Si la consulta
        // revienta se dice y se sigue.
        if let Err(e) = access_email::report_unresolved(self.db.as_ref(), &self.hub_id).await {
            eprintln!("[access-email] no se pudo comprobar los emails de acceso (hub#436): {e}");
        }
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
        seed::apply(self.db.as_ref(), sql, &self.hub_id).await
    }

    // ── Print queue of the hub (ADR-0196 §6, hub#341) ──────────────────────────────────────────

    /// Enqueues a document for a printer role, **idempotently by `jobId`**: repeating the same id
    /// never produces a second ticket (see [`print_queue`]). Scoped to the deployment's `hub_id`.
    /// With no print host connected the job **waits** — late, not lost.
    pub async fn enqueue_print_job(
        &self,
        job: &print_queue::NewPrintJob,
    ) -> Result<print_queue::EnqueueOutcome> {
        print_queue::enqueue(self.db.as_ref(), &self.hub_id, job).await
    }

    /// The hub's print queue in hand-out order (optional role/status filters). This is the
    /// observable view: what is waiting, what is printing and what died (and why).
    pub async fn print_queue(
        &self,
        role: Option<&str>,
        status: Option<&str>,
        limit: i64,
    ) -> Result<Vec<print_queue::PrintJob>> {
        print_queue::list(self.db.as_ref(), &self.hub_id, role, status, limit).await
    }

    // ── Print stations: the destinations themselves, as rows (hub#457) ─────────────────────────

    /// Every printing destination of this hub, by key. This is what a selector shows and what the
    /// refusal of an unknown role names.
    pub async fn print_stations(&self) -> Result<Vec<print_stations::PrintStation>> {
        print_stations::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Adds a station ("Barra de la terraza"). An empty `key` is derived from the label.
    pub async fn create_print_station(
        &self,
        key: &str,
        label: &str,
    ) -> Result<print_stations::PrintStation> {
        print_stations::create(self.db.as_ref(), &self.hub_id, key, label).await
    }

    /// Renames a station — the label only; the key is what every queued job already carries.
    /// `None` = no such station in this hub.
    pub async fn rename_print_station(
        &self,
        id: &str,
        label: &str,
    ) -> Result<Option<print_stations::PrintStation>> {
        print_stations::rename(self.db.as_ref(), &self.hub_id, id, label).await
    }

    /// Removes a station and the host registrations that pointed at it. Refuses while it still
    /// has unfinished work, and always for `receipt` — see [`print_stations::delete`].
    pub async fn delete_print_station(&self, id: &str) -> Result<print_stations::DeleteOutcome> {
        print_stations::delete(self.db.as_ref(), &self.hub_id, id).await
    }

    // ── Print hosts: who drains each printer role (ADR-0196 §6, hub#342) ───────────────────────

    /// Registers `device_id` as a print host of `role` (or refreshes a registration it had).
    /// Several devices may host one role and one device may host several — see [`print_hosts`].
    pub async fn register_print_host(
        &self,
        device_id: &str,
        role: &str,
        label: &str,
        actor: &str,
    ) -> Result<print_hosts::PrintHost> {
        print_hosts::register(
            self.db.as_ref(),
            &self.hub_id,
            device_id,
            role,
            label,
            actor,
        )
        .await
    }

    /// News from a print host: it is still there, for every role it drains. Returns how many
    /// registrations were refreshed (`0` = this device hosts nothing here and must register).
    pub async fn print_host_heartbeat(&self, device_id: &str) -> Result<usize> {
        print_hosts::heartbeat(self.db.as_ref(), &self.hub_id, device_id).await
    }

    /// Retires a device from `role`, or from all its roles when `role` is `None`. Returns how many
    /// registrations were removed.
    pub async fn unregister_print_host(
        &self,
        device_id: &str,
        role: Option<&str>,
    ) -> Result<usize> {
        print_hosts::unregister(self.db.as_ref(), &self.hub_id, device_id, role).await
    }

    /// The print host registry, with `live` resolved from each device's last news.
    pub async fn print_hosts(&self) -> Result<Vec<print_hosts::PrintHost>> {
        print_hosts::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Per printer role: how much work is waiting and how many hosts are live. This is what lets
    /// the hub say "nothing is printing the kitchen's tickets" instead of leaving the queue to
    /// grow in silence.
    pub async fn print_coverage(&self) -> Result<Vec<print_hosts::RoleCoverage>> {
        print_hosts::coverage(self.db.as_ref(), &self.hub_id).await
    }

    // ── Draining the queue: who may pull, and who may close (ADR-0196 §6, hub#343) ─────────────

    /// Hands the next job of `role` to `device_id` — **only** if that device is a registered print
    /// host of that role here. Reclaims expired leases on the way in, so a ticket stranded by a
    /// dead host comes back without any background sweeper having to be alive. See [`print_drain`].
    pub async fn claim_print_job(
        &self,
        device_id: &str,
        role: &str,
    ) -> Result<Option<print_queue::PrintJob>> {
        print_drain::claim(self.db.as_ref(), &self.hub_id, device_id, role).await
    }

    /// The print host confirms the paper came out. `false` = this hub has no such job (or it was
    /// already terminal). Refused if the device does not host that job's role.
    pub async fn confirm_print_job(&self, device_id: &str, job_id: &str) -> Result<bool> {
        print_drain::confirm(self.db.as_ref(), &self.hub_id, device_id, job_id).await
    }

    /// The print host could not print it. `true` = back in the queue, `false` = dead-lettered.
    pub async fn fail_print_job(
        &self,
        device_id: &str,
        job_id: &str,
        error: &str,
    ) -> Result<bool> {
        print_drain::report_failure(self.db.as_ref(), &self.hub_id, device_id, job_id, error).await
    }

    /// Which printer roles `device_id` hosts here — the hub's answer to "what am I for?", so the
    /// draining client never has to guess.
    pub async fn print_roles_of_device(&self, device_id: &str) -> Result<Vec<String>> {
        print_drain::hosted_roles(self.db.as_ref(), &self.hub_id, device_id).await
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
        identity::create_user(self.db.as_ref(), &self.hub_id, name, pin, role, cloud_user_id).await
    }

    #[doc(hidden)]
    pub async fn ensure_dev_user(&self, id: &str, name: &str, role: &str) -> Result<()> {
        identity::ensure_dev_user(self.db.as_ref(), &self.hub_id, id, name, role).await
    }

    /// Verifica el PIN de un usuario por nombre. `Some(user)` si encaja.
    pub async fn verify_pin(&self, name: &str, pin: &str) -> Result<Option<identity::HubUser>> {
        identity::verify_pin(self.db.as_ref(), &self.hub_id, name, pin).await
    }

    /// Usuarios activos del hub con PIN (para mostrar el grid de login local). `(id, name, role)`.
    pub async fn list_pin_users(&self) -> Result<Vec<(String, String, String)>> {
        identity::list_pin_users(self.db.as_ref(), &self.hub_id).await
    }

    // ── Placa de empleado (hub#658). Hermana del PIN: ver `identity`. ───────────────────────

    /// Resuelve una **placa** a su dueño activo. La placa sustituye al par (nombre, PIN) del
    /// pinpad, nunca al PIN.
    pub async fn verify_badge(&self, badge: &str) -> Result<Option<identity::BadgeMatch>> {
        identity::verify_badge(self.db.as_ref(), &self.hub_id, badge).await
    }

    /// Fija (o **retira**, con `badge` vacío) la placa de un usuario. No toca su PIN.
    pub async fn set_user_badge(&self, user_id: &str, badge: &str) -> Result<()> {
        identity::set_badge(self.db.as_ref(), &self.hub_id, user_id, badge).await
    }

    /// `true` si esta placa ya es de **otro** usuario activo del hub.
    pub async fn badge_is_taken(&self, badge: &str, excluding_id: Option<&str>) -> Result<bool> {
        identity::badge_is_taken(self.db.as_ref(), &self.hub_id, badge, excluding_id).await
    }

    /// La clave HMAC con la que este hub indexa sus placas (se acuña en la primera llamada).
    /// Expuesta para que la capa HTTP pueda derivar el índice de una placa **sin** verla en claro
    /// más allá de la petición — p. ej. para limitar los intentos por tarjeta en el login.
    pub async fn badge_index_key(&self) -> Result<Vec<u8>> {
        identity::badge_index_key(self.db.as_ref(), &self.hub_id).await
    }

    /// **The manager approves one action** (hub#361, PLAN paso 2b rules 2 and 4).
    ///
    /// `requester` is the cashier whose command was refused with
    /// [`RuntimeError::RequiresElevation`]; `req` carries the approver's name + PIN and the exact
    /// action being approved. On success the caller gets an opaque token to present on **one**
    /// retry of that same action ([`elevation`] explains the window).
    ///
    /// The PIN is verified **here**, against `hub_user` — rule 2: the client is never the
    /// authority, and the browser never learns whether four digits were right except through this
    /// answer. Five refusals in a row lock the approver at the HTTP door (the same
    /// `LoginThrottle` the pinpad uses): without a limit, ten thousand combinations typed by a
    /// script make the approval decorative.
    ///
    /// Order of the checks is deliberate — everything that is a fact about the **command** is
    /// answered before the digits are looked at, so an action that could never be approved never
    /// costs a throttle slot and never turns this door into an oracle:
    ///
    /// 1. **A machine principal has nobody to approve for** (`machine_principal`). An API key is
    ///    the hole hub#360 left open; now that an approval grants, it closes here too.
    /// 2. The command exists (`CommandNotFound`) and is not **internal** (`InternalCommand`):
    ///    minting an approval for a door the dispatcher refuses before the permission would hand
    ///    out a token that can never be spent.
    /// 3. The requester **does not already hold** the permission (`not_required`): an approval
    ///    nobody needed is a spendable credential left lying around.
    /// 4. The permission is **elevable** (`not_elevable`, [`permissions::is_elevable`]): rule 5,
    ///    `admin` territory is not approved at the counter — default-deny.
    /// 5. The PIN opens an **active** user (`rejected`).
    /// 6. That user **could have done it themselves** (`approver_cannot`): you cannot approve what
    ///    you have no right to do, so the approval never manufactures authority that did not
    ///    already exist in the hub.
    pub async fn approve_elevation(
        &self,
        requester: &RequestContext,
        req: elevation::ElevationRequest<'_>,
    ) -> Result<elevation::ElevationApproval> {
        let reject = |code: &str, message: &str| RuntimeError::Domain {
            code: format!("{}elevation.{code}", hub_users::CORE_NAMESPACE),
            message: message.to_string(),
        };

        if requester.principal == Principal::Machine {
            return Err(reject(
                "machine_principal",
                "an automated integration cannot be approved: a PIN says who is standing at the \
                 till, and nobody is. Give the key the permission it needs instead.",
            ));
        }

        let cmd = self
            .registry
            .get_command(req.command)
            .ok_or_else(|| RuntimeError::CommandNotFound(req.command.to_string()))?;
        if cmd.def.is_internal(req.command) {
            return Err(RuntimeError::InternalCommand(req.command.to_string()));
        }
        let permission = cmd.def.permission.clone();

        if permissions::has(requester, &permission) {
            return Err(reject(
                "not_required",
                "this action needs no approval: whoever asked for it can already do it.",
            ));
        }
        if !permissions::is_elevable(&self.registry, &permission) {
            return Err(reject(
                "not_elevable",
                "this action is not approved with a PIN: it belongs to whoever administers the \
                 hub, who signs in with their own account.",
            ));
        }

        // **Two presentations of one identity** (hub#658). The PIN resolves NAME + digits; a badge
        // resolves the person on its own. Both land on the same `hub_user`, and everything below
        // this point — including the `approver_cannot` check, which is what rule 5 actually is —
        // reads the ROLE, never how the person proved they were standing there.
        //
        // One answer for all the ways this can fail — an unknown name, a wrong PIN, a card nobody
        // carries, a deactivated user: a dialog at the counter must not become a way to find out
        // who works here, nor which cards this shop has issued.
        let rejected = || {
            reject(
                "rejected",
                "those details do not approve this action. Check the name and the PIN.",
            )
        };
        let (approver, credential) = match req.credential {
            elevation::ApproverCredential::Pin { name, pin } => (
                identity::verify_pin(self.db.as_ref(), &self.hub_id, name, pin)
                    .await?
                    .ok_or_else(rejected)?,
                identity::Credential::pin(),
            ),
            elevation::ApproverCredential::Badge { badge } => {
                let matched = identity::verify_badge(self.db.as_ref(), &self.hub_id, badge)
                    .await?
                    .ok_or_else(rejected)?;
                let credential = identity::Credential::badge(&matched.badge_index);
                (matched.user, credential)
            }
        };

        if !permissions::has(
            &RequestContext::new(
                &requester.hub_id,
                &approver.id,
                identity::session_permissions(&self.registry, &approver.role),
            ),
            &permission,
        ) {
            return Err(reject(
                "approver_cannot",
                "that person cannot approve this action: they do not have the right to do it \
                 themselves.",
            ));
        }

        let token = self.elevation.mint(
            elevation::Binding {
                hub_id: requester.hub_id.clone(),
                requester: requester.user_id.clone(),
                command: req.command.to_string(),
                fingerprint: elevation::fingerprint(req.payload),
                permission: permission.clone(),
            },
            &approver.id,
            credential,
        );
        Ok(elevation::ElevationApproval {
            token,
            permission,
            approved_by: approver.id,
            approver_name: approver.name,
            expires_in_seconds: elevation::GRANT_TTL.as_secs(),
        })
    }

    // ── Personal (core): gestión de TODOS los usuarios del hub. Ver [`hub_users`]. ──────────

    /// Todos los usuarios del hub — incluido el owner cloud sin PIN y los desactivados.
    pub async fn list_hub_users(&self) -> Result<Vec<hub_users::HubUserRow>> {
        hub_users::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Alta de un usuario del hub (nombre, rol, email y PIN opcionales). Devuelve su id.
    pub async fn create_hub_user(&self, input: &hub_users::NewHubUser) -> Result<String> {
        hub_users::create(self.db.as_ref(), &self.registry, &self.hub_id, input).await
    }

    /// Edición parcial de un usuario del hub; `is_active: Some(false)` es la baja.
    pub async fn update_hub_user(
        &self,
        user_id: &str,
        input: &hub_users::UpdateHubUser,
    ) -> Result<hub_users::HubUserRow> {
        hub_users::update(self.db.as_ref(), &self.registry, &self.hub_id, user_id, input).await
    }

    /// Roles del hub (catálogo base ∪ módulos activos ∪ en uso) con permisos y miembros.
    pub async fn list_hub_roles(&self) -> Result<Vec<hub_users::HubRole>> {
        hub_users::list_roles(self.db.as_ref(), &self.registry, &self.hub_id).await
    }

    /// Catálogo de roles del hub (paso 2b, hub#352).
    pub async fn role_catalog(&self) -> Result<Vec<roles::CatalogRole>> {
        roles::catalog(self.db.as_ref(), &self.registry, &self.hub_id).await
    }

    /// Activa o desactiva en ESTE hub un rol declarado por un módulo (paso 2b, hub#352).
    pub async fn set_role_active(&self, role_key: &str, active: bool, actor: &str) -> Result<()> {
        roles::set_active(
            self.db.as_ref(),
            &self.registry,
            &self.hub_id,
            role_key,
            active,
            actor,
        )
        .await
    }

    /// **Siembra el owner del hub** desde el env del provisioning (`HUB_OWNER_EMAIL`, ADR-0157): el
    /// owner es el CREADOR del hub. Idempotente (no duplica ni cambia si ya existe). `true` si sembró.
    pub async fn seed_owner(&self, email: &str) -> Result<bool> {
        identity::seed_owner(self.db.as_ref(), &self.hub_id, email).await
    }

    /// Resuelve (o enlaza/provisiona) el `hub_user` de una identidad cloud (mapeo del JWT). Enlaza
    /// por `cloud_user_id`, si no por `email` (owner sembrado / invitado), si no crea con el rol dado.
    ///
    /// `role_floor` es el **suelo** que impone el rol de la cuenta en el Cloud, reevaluado en cada
    /// login (paso 2b regla C, hub#347): sube el rol de una fila existente si se ha quedado corto,
    /// nunca lo baja y nunca concede `owner`. `None` = sin suelo, la fila se devuelve intacta.
    pub async fn get_or_link_cloud_user(
        &self,
        cloud_user_id: &str,
        default_name: &str,
        default_role: &str,
        email: Option<&str>,
        role_floor: Option<&str>,
    ) -> Result<identity::HubUser> {
        identity::get_or_link_cloud_user(
            self.db.as_ref(),
            &self.hub_id,
            cloud_user_id,
            default_name,
            default_role,
            email,
            role_floor,
        )
        .await
    }

    /// **Cierra el acceso local** de una identidad cloud cuyo membresía ha revocado el SaaS (paso 2b
    /// regla D, hub#348): desactiva su `hub_user` (sesión abierta, PIN y pinpad caen con él) y borra
    /// sus sesiones. Idempotente; devuelve cuántas filas cerró.
    pub async fn revoke_cloud_access(
        &self,
        cloud_user_id: &str,
        email: Option<&str>,
    ) -> Result<usize> {
        identity::revoke_cloud_access(self.db.as_ref(), &self.hub_id, cloud_user_id, email).await
    }

    /// **Alta** de un usuario-login por email + rol (flujo admin, ADR-0157 §7). Upsert por email.
    pub async fn create_login_user(&self, email: &str, role: &str) -> Result<identity::HubUser> {
        identity::create_login_user(self.db.as_ref(), &self.hub_id, email, role).await
    }

    /// **Baja** de un usuario-login por email (flujo admin, ADR-0157 §7). Desactiva; `true` si afectó.
    pub async fn deactivate_login_user(&self, email: &str) -> Result<bool> {
        identity::deactivate_login_user(self.db.as_ref(), &self.hub_id, email).await
    }

    /// Lista los usuarios-login del hub (los `hub_user` con email) para el panel admin.
    pub async fn list_login_users(&self) -> Result<Vec<identity::LoginUser>> {
        identity::list_login_users(self.db.as_ref(), &self.hub_id).await
    }

    /// Personas cuyo email **solo** está en su perfil y no se pudo llevar a donde se administra el
    /// acceso (hub#436): su baja NO revoca su membresía hasta que alguien decida qué fila es quién.
    /// Vacío es la respuesta normal. Ver [`access_email`].
    pub async fn unresolved_access_emails(
        &self,
    ) -> Result<Vec<access_email::UnresolvedAccessEmail>> {
        access_email::unresolved(self.db.as_ref(), &self.hub_id).await
    }

    /// Fija (o cambia) el PIN de un usuario existente por id (alta de PIN tras login cloud).
    pub async fn set_pin(&self, user_id: &str, pin: &str) -> Result<()> {
        identity::set_pin(self.db.as_ref(), &self.hub_id, user_id, pin).await
    }

    /// Abre una sesión server-side para `user_id`; devuelve el token opaco. `device_id` = identidad
    /// del dispositivo del login (o `None`); se persiste para el límite de dispositivos (ADR-0154).
    pub async fn create_session(
        &self,
        user_id: &str,
        ttl_secs: i64,
        device_id: Option<&str>,
    ) -> Result<String> {
        identity::create_session(self.db.as_ref(), &self.hub_id, user_id, ttl_secs, device_id).await
    }

    /// [`Runtime::create_session`] dejando escrito **con qué se probó la identidad** (hub#658):
    /// es la mitad de la traza que vive en el login. Lo usa la capa HTTP en cada puerta de login.
    pub async fn create_session_with_credential(
        &self,
        user_id: &str,
        ttl_secs: i64,
        device_id: Option<&str>,
        credential: &identity::Credential,
    ) -> Result<String> {
        identity::create_session_with_credential(
            self.db.as_ref(),
            &self.hub_id,
            user_id,
            ttl_secs,
            device_id,
            credential,
        )
        .await
    }

    /// Aplica el límite de dispositivos del plan ANTES de abrir sesión (ADR-0154): con
    /// `max_devices == 1` y `device_id` presente, desaloja las sesiones de otros dispositivos
    /// (*single active device session* con takeover). `0` = ilimitado / sin `device_id` = no-op.
    pub async fn enforce_device_limit(
        &self,
        max_devices: u32,
        device_id: Option<&str>,
    ) -> Result<()> {
        identity::enforce_device_limit(self.db.as_ref(), &self.hub_id, max_devices, device_id).await
    }

    /// Resuelve una sesión válida a su `hub_user` activo (o `None`).
    pub async fn resolve_session(&self, token: &str) -> Result<Option<identity::HubUser>> {
        identity::resolve_session(self.db.as_ref(), &self.hub_id, token).await
    }

    /// Cierra una sesión (logout).
    pub async fn delete_session(&self, token: &str) -> Result<()> {
        identity::delete_session(self.db.as_ref(), &self.hub_id, token).await
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

    /// The device an id names, or `None` when it names none (hub#454).
    ///
    /// The one id it refuses is **this hub's own**. A device id is a string the client chooses, so
    /// it can only ever NAME a device — but the `hub_id` was worse than an arbitrary string: the
    /// web presented it as its `X-Device-Id`, making every browser one device, and
    /// `GET /api/hub/context` publishes it without a session. Refusing it here is what stops a
    /// browser still running a cached build from writing that shared row back, and what makes a
    /// row restored from an old backup inert.
    ///
    /// Every caller fails closed on `None`, each in its own direction: nothing to trust, not
    /// trusted, the strict mode, no write.
    fn device_named<'a>(&self, device_id: &'a str) -> Option<&'a str> {
        (device_id != self.hub_id).then_some(device_id)
    }

    /// El **hub** al que pertenecen las filas de device-trust, o `None` si este despliegue no dice
    /// cuál es (hub#489).
    ///
    /// `hub_id = ''` es el valor que la migración v23 reserva para «esta fila no nombra hub»: son
    /// las filas anteriores a la columna, y se borran en vez de regalárselas a quien arranque
    /// primero. Devolver `None` aquí es lo que impide que el runtime vuelva a escribirlas —
    /// un hub arrancado sin `HUB_ID` re-crearía justo lo que la migración quita, y una
    /// re-aplicación de la migración borraría entonces confianza viva.
    fn hub_scope(&self) -> Option<&str> {
        (!self.hub_id.is_empty()).then_some(self.hub_id.as_str())
    }

    /// El par `(hub, dispositivo)` que nombra una llamada, o `None` si no nombra un dispositivo
    /// **de este hub**. Falla cerrado por los dos lados: sin hub no hay confianza que conceder, y
    /// el `hub_id` no es un dispositivo (hub#454).
    fn device_of_this_hub<'a>(&'a self, device_id: &'a str) -> Option<(&'a str, &'a str)> {
        Some((self.hub_scope()?, self.device_named(device_id)?))
    }

    /// Marca un dispositivo como de confianza (tras el primer login online). Idempotente (§2.9).
    /// La confianza es **de este hub** (hub#489): la misma tablet puede serlo en dos negocios.
    ///
    /// El dispositivo queda **sin nombre** (hub#494): quien sepa con qué nombre debería nacer usa
    /// [`Self::trust_device_with_default_name`].
    pub async fn trust_device(&self, device_id: &str, label: &str) -> Result<()> {
        self.trust_device_with_default_name(device_id, label, "").await
    }

    /// Igual que [`Self::trust_device`], más el nombre con el que nace el dispositivo la **primera**
    /// vez que este hub lo ve (hub#494).
    ///
    /// `default_name` se escribe **solo en el INSERT**: en un dispositivo ya conocido no toca nada,
    /// porque para entonces el nombre o lo eligió el dueño o es el que se le puso al nacer, y las
    /// dos cosas valen más que lo que traiga el login de turno. Lo que sí sigue reescribiéndose en
    /// cada entrada es `label`, que es otra cosa: quién entró la última vez.
    pub async fn trust_device_with_default_name(
        &self,
        device_id: &str,
        label: &str,
        default_name: &str,
    ) -> Result<()> {
        match self.device_of_this_hub(device_id) {
            Some((hub_id, id)) => {
                identity::trust_device(self.db.as_ref(), hub_id, id, label, default_name).await
            }
            None => Ok(()), // nothing to trust: naming the hub names no device.
        }
    }

    /// `true` si el dispositivo es de confianza **de este hub** (gate del login por PIN, §2.9).
    pub async fn is_device_trusted(&self, device_id: &str) -> Result<bool> {
        match self.device_of_this_hub(device_id) {
            Some((hub_id, id)) => identity::is_device_trusted(self.db.as_ref(), hub_id, id).await,
            None => Ok(false),
        }
    }

    /// Revoca la confianza de un dispositivo (perdido/robado). Idempotente (§2.9). Se lleva con
    /// ella el **modo** del dispositivo (hub#357): la fila borrada es donde vivía.
    pub async fn untrust_device(&self, device_id: &str) -> Result<()> {
        identity::untrust_device(self.db.as_ref(), &self.hub_id, device_id).await
    }

    /// Los dispositivos que este hub conoce, con lo que permite reconocerlos a ojo (hub#455).
    ///
    /// Ojo con lo que se puede creer: el `device_id` y la `label` los elige el **propio
    /// dispositivo** (cabecera `X-Device-Id` y campo `name` del login cloud); el resto —cuándo se
    /// confió, el modo y su auditoría, las sesiones abiertas— lo escribió el hub. Ver
    /// [`devices::TrustedDevice`].
    pub async fn list_devices(&self) -> Result<Vec<devices::TrustedDevice>> {
        devices::list(self.db.as_ref(), &self.hub_id).await
    }

    /// **Corta** un dispositivo perdido (hub#455): cierra sus sesiones abiertas y le retira la
    /// confianza —y con ella el modo `personal` y el login por PIN—. Idempotente.
    ///
    /// Es la pieza que faltaba: [`Self::untrust_device`] ya borraba la fila, pero dejaba viva la
    /// sesión que el dispositivo tuviera abierta (hasta **30 días** en un `personal`, hub#358), que
    /// es justo lo que sigue usando quien se llevó la tablet. Se ejecuta sobre **cualquier** id que
    /// se le nombre —revocar solo quita privilegio—, incluida una fila heredada cuyo id fuese el
    /// del propio hub (hub#454).
    pub async fn revoke_device(&self, device_id: &str) -> Result<devices::Revocation> {
        devices::revoke(self.db.as_ref(), &self.hub_id, device_id).await
    }

    /// **Nombra** un dispositivo que este hub ya conoce (hub#494): «Barra», «Cocina», «Portátil
    /// despacho». Es lo único de la fila que decide el negocio, y por eso es lo único de fiar al
    /// señalar cuál cortar. No crea filas: un dispositivo se lista porque se confió en él, nunca
    /// porque alguien escribió su id.
    pub async fn rename_device(&self, device_id: &str, name: &str) -> Result<devices::Renamed> {
        devices::rename(self.db.as_ref(), &self.hub_id, device_id, name).await
    }

    /// The hub's **fiscal profile** (ADR-0273, hub#549): what this hub owes, who it owes it as, and
    /// how far along it is. `None` only before [`Runtime::ensure_system_tables`] has ever run —
    /// booting resolves it. The authority on the obligation lives here, in the core, so that no
    /// module can take it away by being uninstalled.
    pub async fn fiscal_profile(&self) -> Result<Option<fiscal_profile::FiscalProfile>> {
        fiscal_profile::load(self.db.as_ref(), &self.hub_id).await
    }

    /// **What this hub owes right now** (ADR-0273 D2, hub#550): the stored status resolved against
    /// what is actually mounted. This is where `BLOCKED` comes from — derived on every read, never
    /// stored, so it is fixed by fixing the fact and cannot outlive the bug that caused it.
    ///
    /// Read-only: it never writes. The write side is [`Runtime::refresh_fiscal_profile`].
    pub async fn fiscal_mode(&self) -> Result<fiscal_profile::FiscalMode> {
        let profile = fiscal_profile::ensure(self.db.as_ref(), &self.hub_id).await?;
        Ok(fiscal_profile::determine_fiscal_mode(
            &profile,
            &self.registry,
            &self.hub_id,
        ))
    }

    /// Resolves the fiscal profile against the world and returns the effective mode (ADR-0273
    /// D2/D4, hub#550). The host calls it at boot **after re-hydrating the registry** — that is the
    /// first instant both halves of the answer exist: what the hub owes, and who is mounted to
    /// comply. Idempotent, so every restart and every redeploy runs it.
    pub async fn refresh_fiscal_profile(&self) -> Result<fiscal_profile::FiscalMode> {
        fiscal_profile::refresh(self.db.as_ref(), &self.registry, &self.hub_id).await
    }

    /// **El go-live** (ADR-0273 D3, hub#551): `READY → ACTIVE`, que ES `testing → production`.
    /// Una sola transición y un solo sitio donde se guarda. Exige que el perfil esté `READY` —la
    /// misma condición que enseña la checklist— y que el hub pueda hacerlo (una demo no).
    pub async fn fiscal_go_live(&self) -> Result<fiscal_profile::FiscalProfile> {
        fiscal_profile::go_live(self.db.as_ref(), &self.hub_id).await
    }

    /// **Apaga el go-live**, y solo mientras no haya salido ni un registro hacia la Hacienda real
    /// (ADR-0273 D3). Lo irreversible es el primer ENVÍO, no el clic: quien activa por error y se
    /// da cuenta antes de facturar puede volver.
    pub async fn fiscal_stand_down(&self) -> Result<fiscal_profile::FiscalProfile> {
        fiscal_profile::stand_down(self.db.as_ref(), &self.hub_id).await
    }

    /// **Cese de actividad** (ADR-0273 D2, hub#557): el negocio cierra y deja de facturar, pero
    /// sigue consultando y exportando sus libros. `actor` = quién lo decidió, y sin él no se
    /// cierra: una acción irreversible sin nadie detrás en el registro no es una traza.
    ///
    /// **Es función de producto, no compliance** — siendo VERI\*FACTU-only no hay registro de
    /// eventos que remitir, y el cese que existe es la baja censal (036/037) del obligado, que
    /// presenta él o su gestoría. Lo que compra es que quien cesó no siga facturando por error.
    ///
    /// No tiene vuelta: no hay `CLOSED → ACTIVE`. La **sesión admin y la confirmación** las pone
    /// la puerta que llama, igual que en el go-live.
    pub async fn fiscal_close(&self, actor: &str) -> Result<fiscal_profile::FiscalProfile> {
        fiscal_profile::close(self.db.as_ref(), &self.hub_id, actor).await
    }

    /// **Adopta una instalación AJENA** (ADR-0273 D8, hub#558): el hub se movió de despliegue —o se
    /// restauró en otro sitio—, el `hub_id` cambió y estas filas las escribió otra instalación.
    /// Como `NumeroInstalacion = hub_id` (ADR-0202), otro `hub_id` es **otro SIF y otra cadena**,
    /// que arranca con `PrimerRegistro=S`.
    ///
    /// **Jamás automático**: el arranque solo lo **marca** (`needs_review` + `BLOCKED` derivado) y
    /// el gate solo **rechaza**. Adoptar en silencio la instalación de otro es exactamente cómo se
    /// mezclan dos cadenas, y un registro ya remitido ni se reenvía ni se borra (ADR-0189). Sesión
    /// admin y confirmación las pone la puerta que llama; `actor` es la traza.
    pub async fn fiscal_adopt_installation(
        &self,
        actor: &str,
    ) -> Result<fiscal_profile::FiscalProfile> {
        fiscal_profile::adopt_installation(self.db.as_ref(), &self.hub_id, actor).await
    }

    /// Qué clase de dispositivo es este: `shared` (mostrador) o `personal` (equipo propio),
    /// paso 2b / hub#357. Un dispositivo que el hub no conoce es **`shared`** — el modo estricto.
    pub async fn device_mode(&self, device_id: &str) -> Result<device_mode::DeviceMode> {
        match self.device_of_this_hub(device_id) {
            Some((hub_id, id)) => device_mode::mode(self.db.as_ref(), hub_id, id).await,
            None => Ok(device_mode::DeviceMode::default()),
        }
    }

    /// Cuánto dura una sesión abierta **en este dispositivo** (segundos), hub#358 + hub#359.
    ///
    /// Lo deciden los **dos** controles a la vez, y gana **el más restrictivo**
    /// ([`pin_policy::effective_session_ttl_secs`], un `min`): el modo del dispositivo dice cuánto
    /// aguanta esta terminal (mostrador = el turno, equipo propio = «recordarme») y el dial del
    /// negocio dice cada cuánto se pregunta quién está en la caja. Ninguno puede **alargar** lo que
    /// el otro acortó: «nunca» no le compra al mostrador la sesión larga de un equipo personal, y
    /// marcar un equipo como personal no lo saca de la política estricta que eligió el negocio.
    ///
    /// Fail-closed igual que el modo: un dispositivo que el hub no conoce —o un cliente que no dice
    /// cuál es— recibe la sesión **corta**, nunca la larga.
    pub async fn session_ttl_for_device(&self, device_id: &str) -> Result<i64> {
        Ok(pin_policy::effective_session_ttl_secs(
            self.device_mode(device_id).await?,
            self.pin_policy().await?,
        ))
    }

    /// Cada cuánto pregunta este hub QUIÉN está en la caja (`always` | `per_shift` | `never`,
    /// hub#359). Un hub que no eligió —o cuyo valor almacenado no se puede leer— **sigue
    /// preguntando**: el default nunca es `never`.
    pub async fn pin_policy(&self) -> Result<pin_policy::PinPolicy> {
        pin_policy::policy(self.db.as_ref(), &self.hub_id).await
    }

    /// Fija el dial del hub. `actor` = quién lo decidió (auditoría); la puerta HTTP
    /// (`PUT /api/settings`) exige sesión **admin**. Escribe por el store de settings, que es la
    /// única puerta de escritura de esta clave.
    pub async fn set_pin_policy(&self, policy: pin_policy::PinPolicy, actor: &str) -> Result<()> {
        pin_policy::set_policy(self.db.as_ref(), &self.hub_id, policy, actor).await
    }

    /// Fija el modo de un dispositivo **ya conocido** (hub#357). `actor` = el `hub_user.id` que lo
    /// decidió; la puerta HTTP exige sesión **admin**. Rechaza un `device_id` que el hub nunca vio:
    /// esto registra una decisión sobre un dispositivo, no lo da de alta.
    pub async fn set_device_mode(
        &self,
        device_id: &str,
        mode: device_mode::DeviceMode,
        actor: &str,
    ) -> Result<()> {
        match self.device_of_this_hub(device_id) {
            Some((hub_id, id)) => {
                device_mode::set_mode(self.db.as_ref(), hub_id, id, mode, actor).await
            }
            None => Err(device_mode::unknown_device(device_id)),
        }
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
        scope: &api_keys::ApiKeyScope,
        rate_limit_per_minute: i64,
        created_by: &str,
    ) -> Result<api_keys::ApiKeySecret> {
        api_keys::create(self.db.as_ref(), &self.hub_id, name, scope, rate_limit_per_minute, created_by).await
    }

    /// The read-only key the hub issues to **itself** so our own app reads the event stream
    /// through the same door as any integration (hub#504). Idempotent; re-issued after a restore.
    pub async fn ensure_app_api_key(&self) -> Result<String> {
        api_keys::ensure_app_key(self.db.as_ref(), &self.hub_id).await
    }

    /// Resolves a key by **id** (no secret) — the redemption end of a stream ticket (hub#504).
    /// Same refusals as [`Self::resolve_api_key`]: revoked, unknown or another hub's key → `None`.
    pub async fn resolve_api_key_id(
        &self,
        key_id: &str,
    ) -> Result<Option<api_keys::ApiKeyPrincipal>> {
        api_keys::resolve_key_id(self.db.as_ref(), &self.registry, &self.hub_id, key_id).await
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

    /// El nombre IANA de la zona horaria del negocio, ya **resuelta** (hub#731): la declarada en
    /// `timezone` o, lo normal, la deducida de `country_code`/`region_code`. `get_settings`
    /// devuelve la clave cruda (`null` mientras se deduzca) porque tiene que poder volver por un
    /// `PUT`; esto es lo que la UI necesita para decir a qué hora local va a correr un flujo.
    pub async fn timezone_name(&self) -> Result<String> {
        Ok(settings::timezone_of(self.db.as_ref(), &self.hub_id)
            .await?
            .name()
            .to_string())
    }

    /// Aplica un mapa parcial de settings (valida cada clave conocida; rechaza desconocidas o
    /// valores inválidos antes de tocar la BD) y devuelve el objeto completo actualizado. El gate
    /// de rol (owner/admin) lo aplica el server. `updated_by` audita quién hizo el cambio.
    pub async fn set_settings(
        &self,
        updates: &serde_json::Map<String, Json>,
        updated_by: &str,
    ) -> Result<Json> {
        settings::set_many(
            self.db.as_ref(),
            &self.hub_id,
            updates,
            updated_by,
            self.registry.demo_hub,
        )
        .await
    }

    /// Capabilities DECLARADAS por un módulo con su estado de grant (ADR-0079). Para
    /// `GET /api/modules/:id/capabilities`. Lista vacía = el módulo no pide permisos.
    pub async fn module_capabilities(&self, module_id: &str) -> Result<Vec<(String, bool)>> {
        capabilities::list_for_module(self.db.as_ref(), &self.registry, &self.hub_id, module_id)
            .await
    }

    /// **Gate de UNA capability** para un módulo (ADR-0079, default-deny): tiene que estar
    /// DECLARADA en su `module.json` **y** CONCEDIDA por el dueño. Es [`capabilities::require`]
    /// con el `db`/`registry`/`hub_id` de este runtime ya puestos.
    ///
    /// La usa el server donde el host ejerce el primitivo. Hoy: la puerta del kernel de flujos
    /// (`/api/hub/flows*`, hub#714), que **suma** este gate al de sesión admin — nunca lo
    /// sustituye.
    pub async fn require_module_capability(
        &self,
        module_id: &str,
        kind: manifest::CapabilityKind,
    ) -> Result<()> {
        capabilities::require(
            self.db.as_ref(),
            &self.registry,
            module_id,
            &self.hub_id,
            kind,
        )
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

    /// Sube/reemplaza el certificado fiscal **del negocio** (ADR-0079). `by` = `hub_user:<id>` admin.
    ///
    /// Ata el slot [`certificate::CertificateKind::Own`] en el ÚNICO punto por el que entra un `.p12`
    /// del cliente (`PUT /api/business/certificate`): el certificado delegado de ERPlora lo escribe
    /// el plano de control por su propia vía (hub#317), nunca esta.
    ///
    /// **El TIPO sale de los bytes, y aquí no hay nada con lo que contrastarlo** (hub#470). Al
    /// certificado delegado lo acompaña una declaración del plano de control que
    /// [`certificate::set_delegated`] comprueba; este lo sube su dueño directamente, así que no hay
    /// frontera que cruzar ni segunda opinión que discrepe: el contenedor es la única fuente. Un
    /// negocio que suba un **sello de entidad** propio entra por `www10` sin tocar nada, que es
    /// justamente lo que la AEAT segrega.
    /// **Un hub de DEMO no sube certificado** (ADR-0197 §4, hub#376). El cierre va aquí, en la
    /// puerta del `own`, y NO en [`certificate::set`]: el certificado **delegado** de ERPlora sigue
    /// llegando por su vía (`set_delegated`, hub#317) — es la distribución normal de la flota y una
    /// demo la recibe como cualquier otro hub. Lo que no puede es tener identidad fiscal PROPIA.
    pub async fn set_business_certificate(
        &self,
        pkcs12_b64: &str,
        password: &str,
        by: &str,
    ) -> Result<()> {
        self.refuse_if_demo(DemoLock::BusinessCertificate)?;
        certificate::set(
            self.db.as_ref(),
            &self.hub_id,
            certificate::CertificateKind::Own,
            pkcs12_b64,
            password,
            by,
            // Sin versión: la del plano de control describe la ROTACIÓN CENTRAL del certificado
            // delegado (ADR-0202 §2.5). El del negocio lo sube y lo renueva su dueño, así que no hay
            // número de flota que le corresponda y ponerle uno haría que este hub reportase como
            // instalada una versión de ERPlora que no tiene.
            None,
            certificate::derive_certificate_type(pkcs12_b64, password),
        )
        .await
    }

    /// Estado de los certificados del hub (sin bytes ni contraseña): el del negocio en la raíz —
    /// como siempre— más `slots`/`active` (ADR-0202 §2.1).
    pub async fn business_certificate_status(&self) -> Result<Json> {
        certificate::status(self.db.as_ref(), &self.hub_id).await
    }

    /// Elimina el certificado **del negocio**. El delegado no se toca: no es del cliente.
    ///
    /// Cerrado también en una demo (hub#376): «no reemplazable» sin «no borrable» sería un
    /// reemplazo en dos pasos.
    pub async fn delete_business_certificate(&self) -> Result<()> {
        self.refuse_if_demo(DemoLock::BusinessCertificate)?;
        certificate::delete(self.db.as_ref(), &self.hub_id, certificate::CertificateKind::Own).await
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

    /// Dead-letters of this hub, newest first (hub#660). What the relay gave up on, with the
    /// payload it was carrying — the queue an admin operates from `/api/hub/events/dead`.
    pub async fn list_dead_events(&self, limit: i64) -> Result<Vec<outbox::DeadEvent>> {
        outbox::list_dead(self.db.as_ref(), &self.hub_id, limit).await
    }

    /// Puts a dead-letter back in front of the relay (`pending`, attempts reset). Three answers,
    /// because a row that CANNOT be replayed is neither a success nor a missing id
    /// ([`outbox::RetryOutcome`], hub#827).
    pub async fn retry_dead_event(&self, id: &str) -> Result<outbox::RetryOutcome> {
        outbox::retry(self.db.as_ref(), &self.hub_id, id).await
    }

    /// Closes a dead-letter for good, keeping the row (auditable). `discarded_by` is the identity
    /// the HTTP layer resolved from the session; `reason` is why the person closed it (hub#955),
    /// optional and stored clamped. `false` if there is no such dead-letter here.
    pub async fn discard_dead_event(
        &self,
        id: &str,
        discarded_by: &str,
        reason: &str,
    ) -> Result<bool> {
        outbox::discard(self.db.as_ref(), &self.hub_id, id, discarded_by, reason).await
    }

    /// Puts EVERY dead-letter of this hub back in front of the relay at once (bulk retry, hub#660).
    /// Returns how many rows it moved. The hub never stays stuck behind a queue that only moves one
    /// click at a time: a transient outage that killed several events is cleared in one gesture.
    pub async fn retry_all_dead_events(&self) -> Result<u64> {
        outbox::retry_all(self.db.as_ref(), &self.hub_id).await
    }

    /// How many dead-letters this hub has right now (hub#660). Cheap count — powers the topbar bell
    /// without dragging the payloads the listing carries.
    pub async fn count_dead_events(&self) -> Result<i64> {
        outbox::count_dead(self.db.as_ref(), &self.hub_id).await
    }

    /// **What one event carries**, inferred from the last `limit` real events of this hub
    /// (hub#715) — the read the flow editor's data picker is built from, so an owner chooses
    /// «Total de la venta — 42,50 €» instead of `sale.total`.
    ///
    /// What comes back is the SHAPE, never the stored payloads: keys, types and one sample each,
    /// with the sample withheld wherever the value could be about a person
    /// ([`crate::event_shape`] explains where that line is drawn and why it is minimisation and
    /// not anonymisation).
    ///
    /// Three answers, and the middle one is the reason this returns an `Option` rather than an
    /// empty shape:
    ///
    /// - `Some(shape)` with samples — the event has happened here;
    /// - `Some(shape)` with `samples: 0` — an installed module declares it and no example
    ///   survives: it has never fired, or the last one aged out of the ninety-day retention window
    ///   (hub#699). An infrequent event lives here, and the editor must still offer it;
    /// - `None` — nobody declares it and it has never been seen. Only THAT is «no such event».
    pub async fn event_shape(
        &self,
        event_name: &str,
        limit: i64,
    ) -> Result<Option<event_shape::EventShape>> {
        let declared_by = self.registry.modules_emitting(event_name);
        let samples = outbox::sample_payloads(self.db.as_ref(), &self.hub_id, event_name, limit).await?;
        if declared_by.is_empty() && samples.is_empty() {
            return Ok(None);
        }
        let payloads: Vec<Json> = samples.iter().map(|s| s.payload.clone()).collect();
        Ok(Some(event_shape::EventShape {
            event_name: event_name.to_string(),
            declared_by,
            samples: samples.len(),
            last_seen_at: samples.first().map(|s| s.created_at.clone()),
            // The NAME travels into the inference: for a flat payload it is the only thing that
            // says whose data this is (hub#826).
            fields: event_shape::infer(event_name, &payloads),
        }))
    }

    /// **Every event this hub can speak of**, by name (hub#823) — the read the flow editor's
    /// «Cuando pase…» dropdown is built from, so it stops being seeded from a hand-written file
    /// that can never offer an event this hub emits and the file does not know.
    ///
    /// The union of two honest sources, sorted by name:
    ///
    /// - what installed modules DECLARE ([`Registry::declared_events`]: `events.emits` plus each
    ///   command's `emit`) — a declared event that never fired is still offered, with no
    ///   `last_seen_at`;
    /// - what was really SEEN in the outbox ([`outbox::seen_event_names`]) — an event that
    ///   happened and that nobody declares any more (a core event, an uninstalled module) is
    ///   still offered, with `declared_by` empty.
    ///
    /// Names only: what an event carries is [`Self::event_shape`]'s answer, with its redaction.
    pub async fn event_catalog(&self) -> Result<Vec<event_shape::EventCatalogEntry>> {
        let mut entries: std::collections::BTreeMap<String, event_shape::EventCatalogEntry> = self
            .registry
            .declared_events()
            .into_iter()
            .map(|(name, declared_by)| {
                (
                    name.clone(),
                    event_shape::EventCatalogEntry {
                        name,
                        declared_by,
                        last_seen_at: None,
                    },
                )
            })
            .collect();
        for seen in outbox::seen_event_names(self.db.as_ref(), &self.hub_id).await? {
            entries
                .entry(seen.name.clone())
                .or_insert_with(|| event_shape::EventCatalogEntry {
                    name: seen.name,
                    declared_by: Vec::new(),
                    last_seen_at: None,
                })
                .last_seen_at = Some(seen.last_seen_at);
        }
        Ok(entries.into_values().collect())
    }

    /// Un ciclo del barrido del **scheduler** (ADR-0011): ejecuta las scheduled tasks vencidas de
    /// los módulos activos. Lo llama el bucle de background del server (junto al relay del outbox).
    /// Devuelve cuántas tareas corrió. `hub_id` es el del despliegue (contexto de sistema).
    pub async fn process_scheduler(&self, hub_id: &str) -> Result<usize> {
        scheduler::process_once(self.db.as_ref(), &self.registry, hub_id).await
    }

    // ── Automation kernel (ADR-0283, hub#661) ───────────────────────────────────────────────
    // The REST surface (`crates/server/src/flows_api.rs`) is the only caller of these; there are
    // deliberately no `hub.*` commands for flows (ADR-0283 §9 — the core is being frozen, and the
    // dispatcher is not where new core surface goes).

    /// One cycle of the flows kernel: fire due clock triggers, wake finished delays, advance
    /// claimed runs. Called from the same 1 s loop as the outbox relay and the scheduler.
    pub async fn process_flows(&self) -> Result<flows::executor::TickReport> {
        flows::tick(self.db.as_ref(), &self.registry, &self.hub_id).await
    }

    /// The **complete** half of claim → I/O → complete (hub#662): the server performed the call
    /// outside the lock and hands back what it produced, so the run can carry on — or stop.
    pub async fn complete_flow_io(
        &self,
        run_id: &str,
        step_id: &str,
        result: flows::IoResult,
    ) -> Result<()> {
        flows::executor::complete_io(self.db.as_ref(), &self.hub_id, run_id, step_id, result).await
    }

    /// Names of the `_flow_secrets` this hub holds. **Never the values** — there is no method that
    /// returns one, and the only reader is the executor while it builds a request (ADR-0283 §4).
    pub async fn list_flow_secrets(&self) -> Result<Vec<flows::secrets::SecretInfo>> {
        flows::secrets::list(self.db.as_ref(), &self.hub_id).await
    }

    pub async fn put_flow_secret(
        &self,
        name: &str,
        value: &str,
        by: &str,
    ) -> Result<flows::secrets::SecretInfo> {
        flows::secrets::put(self.db.as_ref(), &self.hub_id, name, value, by).await
    }

    pub async fn delete_flow_secret(&self, name: &str, by: &str) -> Result<()> {
        flows::secrets::delete(self.db.as_ref(), &self.hub_id, name, by).await
    }

    pub async fn list_flows(&self) -> Result<Vec<flows::Flow>> {
        flows::store::list(self.db.as_ref(), &self.hub_id).await
    }

    pub async fn get_flow(&self, id: &str) -> Result<flows::Flow> {
        flows::store::get(self.db.as_ref(), &self.hub_id, id).await
    }

    /// Saves a flow. The registry travels with it because the document names COMMANDS, and a
    /// document naming one the kernel can never invoke is refused at save (hub#824) — same reason
    /// `replace_flow_grants` carries it.
    pub async fn create_flow(&self, new: &flows::NewFlow, by: &str) -> Result<flows::Flow> {
        flows::store::create(self.db.as_ref(), &self.hub_id, &self.registry, new, by).await
    }

    pub async fn update_flow(
        &self,
        id: &str,
        new: &flows::NewFlow,
        by: &str,
    ) -> Result<flows::Flow> {
        flows::store::update(self.db.as_ref(), &self.hub_id, id, &self.registry, new, by).await
    }

    pub async fn delete_flow(&self, id: &str, by: &str) -> Result<()> {
        flows::store::delete(self.db.as_ref(), &self.hub_id, id, by).await
    }

    pub async fn list_flow_grants(&self, flow_id: &str) -> Result<Vec<flows::grants::Grant>> {
        flows::grants::list(self.db.as_ref(), &self.hub_id, flow_id).await
    }

    /// Replaces the grant list of a flow. The commands are checked against the **registry** here,
    /// so a grant naming something that does not exist is refused with the whole list.
    pub async fn replace_flow_grants(
        &self,
        flow_id: &str,
        wanted: &[(flows::grants::GrantKind, String)],
        granted_by: &str,
    ) -> Result<()> {
        // 404 first: granting to a flow that is not here must not create rows for a ghost.
        flows::store::get(self.db.as_ref(), &self.hub_id, flow_id).await?;
        flows::grants::replace(
            self.db.as_ref(),
            &self.hub_id,
            flow_id,
            &self.registry,
            wanted,
            granted_by,
        )
        .await
    }

    /// `manual` trigger: starts a run and returns its id. The run itself is advanced by the tick,
    /// never by the request — a flow with a delay would otherwise hold the HTTP call open.
    pub async fn start_flow_run(
        &self,
        flow_id: &str,
        input: &Json,
        started_by: &str,
    ) -> Result<String> {
        flows::executor::start_manual_run(
            self.db.as_ref(),
            &self.hub_id,
            flow_id,
            input,
            started_by,
        )
        .await
    }

    /// The history of one flow, newest first. `before` is the id of the last run of the previous
    /// page (a cursor, not an offset — see [`flows::store::list_runs`]).
    pub async fn list_flow_runs(
        &self,
        flow_id: &str,
        limit: i64,
        before: Option<&str>,
    ) -> Result<Vec<flows::FlowRun>> {
        flows::store::list_runs(self.db.as_ref(), &self.hub_id, flow_id, limit, before).await
    }

    pub async fn get_flow_run(
        &self,
        run_id: &str,
    ) -> Result<(flows::FlowRun, Vec<flows::FlowRunStep>)> {
        flows::store::get_run(self.db.as_ref(), &self.hub_id, run_id).await
    }

    /// The events one run emitted — the forward link from a run into everything downstream of it
    /// (hub#666).
    pub async fn events_of_run(&self, run_id: &str) -> Result<Vec<outbox::CorrelatedEvent>> {
        outbox::events_of_run(self.db.as_ref(), &self.hub_id, run_id).await
    }

    /// **What one event set off**: the runs it started and the events its delivery caused. This is
    /// the answer to «this sale fired these five steps», read from the event end of the chain.
    /// `None` when the event is not in this hub.
    pub async fn trace_event(&self, event_id: &str) -> Result<Option<EventTrace>> {
        let db = self.db.as_ref();
        let Some(event) = outbox::correlated_event(db, &self.hub_id, event_id).await? else {
            return Ok(None);
        };
        Ok(Some(EventTrace {
            runs: flows::store::runs_of_event(db, &self.hub_id, event_id).await?,
            caused: outbox::events_caused_by(db, &self.hub_id, event_id).await?,
            event,
        }))
    }

    // ── The agent step: what the server-side runner is allowed to ask for (hub#665) ──────────
    //
    // The runner lives in `crates/server` because it needs `cloud-client`, and the runtime has no
    // network by design. Everything it is NOT allowed to decide for itself goes through the
    // methods below (plus `complete_flow_io`, the seam hub#662 built) — and none of them lets it
    // build an automation context of its own:
    // `RequestContext.automation` is private with a `pub(crate)` setter precisely so that a caller
    // outside this crate cannot stamp a flow's identity on a request and inherit its grants
    // (flows.md §13.9).

    /// The `ai` step a run is stopped on, read once, with its prompt already resolved.
    pub async fn load_flow_ai_request(
        &self,
        run_id: &str,
        step_id: &str,
    ) -> Result<flows::AiRequest> {
        flows::agent::prepare(self.db.as_ref(), &self.hub_id, run_id, step_id).await
    }

    /// The live grants of a flow — what the runner intersects the offered tools with.
    pub async fn flow_authority(&self, flow_id: &str) -> Result<flows::grants::Authority> {
        flows::grants::authority(self.db.as_ref(), &self.hub_id, flow_id).await
    }

    /// Runs a READ on behalf of a flow. The grant is checked HERE, freshly, so a query the flow
    /// was not granted is refused by the runtime and not by the runner's good manners — a gate the
    /// caller can skip is not a gate.
    pub async fn execute_flow_query(
        &self,
        flow_id: &str,
        run_id: &str,
        name: &str,
        params: &Params,
    ) -> Result<Vec<Json>> {
        flows::grants::check_query_grant(self.db.as_ref(), &self.hub_id, flow_id, name).await?;
        let ctx = self.automation_ctx(flow_id, run_id).await?;
        let r = queries::execute(self.db.as_ref(), &self.registry, name, params, &ctx).await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "query", name, params);
        }
        r
    }

    /// Runs a WRITE on behalf of a flow, through the SAME door the kernel's own `command` steps
    /// use ([`commands::Origin::Automation`]). That is the whole reason ADR-0283 D2 puts the
    /// automation gate inside `execute_at`: a flow's command inherits the fiscal gates, the schema
    /// validation and the transactional outbox whole, instead of getting a dispatcher of its own.
    pub async fn execute_flow_command(
        &self,
        flow_id: &str,
        run_id: &str,
        depth: i64,
        name: &str,
        payload: &Params,
    ) -> Result<Json> {
        let ctx = self.automation_ctx(flow_id, run_id).await?;
        let r = commands::execute_at(
            self.db.as_ref(),
            &self.registry,
            name,
            payload,
            &ctx,
            depth.max(0) as u32,
            &[],
            commands::Origin::Automation,
            // No approval to spend: an elevation is a person authorising an action at the counter,
            // and there is nobody at the counter (hub#361).
            None,
        )
        .await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "command", name, payload);
        }
        r
    }

    /// **Would this payload be accepted by `name`, if it were run right now?** — asked without
    /// running anything, and answered by the same code that will judge it at execution
    /// ([`commands::validate_payload`]).
    ///
    /// hub#825: the agent runner asks this BEFORE parking a proposal in the approval tray. A
    /// proposal the hub can already refute must never become a question for a person — approving it
    /// would spend her decision on something that cannot happen.
    pub fn validate_command_payload(&self, name: &str, payload: &Params) -> Result<()> {
        commands::validate_payload(&self.registry, name, payload)
    }

    /// The context a flow acts under: attributed to the flow, machine-principal (never offered a
    /// manager's PIN), and carrying only the permissions of what it was granted.
    async fn automation_ctx(&self, flow_id: &str, run_id: &str) -> Result<RequestContext> {
        let authority = self.flow_authority(flow_id).await?;
        Ok(RequestContext::new(
            self.hub_id.clone(),
            format!("flow:{flow_id}"),
            authority.permissions(&self.registry),
        )
        .as_machine()
        .with_automation(AutomationCtx {
            flow_id: flow_id.to_string(),
            run_id: run_id.to_string(),
        }))
    }

    // ── The approval tray (ADR-0283 D3) ─────────────────────────────────────────────────────

    /// Parks a write the model proposed: the row a person reads in the morning, and the run
    /// stopped in the same gesture. A proposal with a run still marching forward would be a
    /// question nobody is waiting for.
    pub async fn request_flow_approval(
        &self,
        new: &flows::NewApproval,
    ) -> Result<flows::Approval> {
        let approval = flows::approvals::create(self.db.as_ref(), &self.hub_id, new).await?;
        // The park goes through the SAME seam an `http` step completes by (hub#662): one place
        // decides what «this run stopped on its I/O step» means, and a second one would drift.
        self.complete_flow_io(
            &new.run_id,
            &new.step_id,
            flows::IoResult::AwaitingApproval(new.partial_output.clone()),
        )
        .await?;
        // Ephemeral, WS-only (`events::notify_sink`): the tray lights up without polling. The
        // SCREEN is the module `flows`'s job — the core emits the fact and nothing else.
        let mut payload = Params::new();
        payload.insert("approval_id".into(), Json::from(approval.id.clone()));
        payload.insert("flow_id".into(), Json::from(approval.flow_id.clone()));
        payload.insert("run_id".into(), Json::from(approval.run_id.clone()));
        payload.insert("command".into(), Json::from(approval.command.clone()));
        events::notify_sink(
            &self.registry,
            registry::EventSource::Core,
            flows::approvals::EVENT_APPROVAL_CREATED,
            &payload,
        );
        Ok(approval)
    }

    /// What the agent turn had produced when it stopped for approval — parked on the step row, so
    /// a decision taken hours later completes the whole turn and not just its ending. Degrades to
    /// an empty object: a missing partial must not stop a booking somebody just approved.
    async fn parked_step_output(&self, run_id: &str) -> Json {
        self.get_flow_run(run_id)
            .await
            .ok()
            .and_then(|(run, steps)| {
                steps
                    .into_iter()
                    .find(|s| s.step_index == run.current_step)
                    .map(|s| s.output)
            })
            .filter(Json::is_object)
            .unwrap_or_else(|| json!({}))
    }

    pub async fn get_flow_approval(&self, id: &str) -> Result<flows::Approval> {
        flows::approvals::get(self.db.as_ref(), &self.hub_id, id).await
    }

    pub async fn list_flow_approvals(
        &self,
        status: Option<&str>,
        limit: i64,
    ) -> Result<Vec<flows::Approval>> {
        flows::approvals::list(self.db.as_ref(), &self.hub_id, status, limit).await
    }

    /// **The approval contract**, in one method because its four steps are one decision:
    ///
    /// 1. the proposal must still be decidable (once, and not expired);
    /// 2. on `approve`, the grant is **re-checked right now** — a proposal is not a stored
    ///    permission, and between 3 AM and 9 AM the owner may have withdrawn the capability. If it
    ///    is gone, nothing runs and the row stays **pending**: granting again and approving again
    ///    is a working remedy, whereas a burnt approval would force a re-run of the whole flow;
    /// 3. what runs is **exactly** the stored command with the stored payload, through
    ///    `Origin::Automation`. The model is **not** asked again — re-planning after a rejection is
    ///    product (the module `flows`), and a kernel that quietly re-planned would make "I approved
    ///    *this*" mean nothing;
    /// 4. the run continues from the step after the agent's, or — on `reject` — stops as
    ///    `cancelled`, because the steps written after an agent step assumed it acted.
    ///
    /// `decided_by` is the caller's job to resolve from the SESSION; this method never reads it
    /// from a body (same rule as `discarded_by` in `outbox_admin.rs`).
    pub async fn decide_flow_approval(
        &self,
        id: &str,
        approve: bool,
        decided_by: &str,
    ) -> Result<flows::Approval> {
        let approval = flows::approvals::claim_pending(self.db.as_ref(), &self.hub_id, id).await?;

        if !approve {
            let decided = flows::approvals::mark_decided(
                self.db.as_ref(),
                &self.hub_id,
                id,
                flows::approvals::STATUS_REJECTED,
                decided_by,
                "",
            )
            .await?;
            self.complete_flow_io(
                &approval.run_id,
                &approval.step_id,
                flows::IoResult::Cancelled(format!(
                    "`{}` was rejected by `{decided_by}`",
                    approval.command
                )),
            )
            .await?;
            return Ok(decided);
        }

        // Step 2 — the gate, NOW. Deliberately before anything is written: nothing about this
        // approval changes if the answer is no.
        flows::grants::check_command_grant(
            self.db.as_ref(),
            &self.hub_id,
            &approval.flow_id,
            &approval.command,
        )
        .await?;

        // Step 3 — exactly what was proposed.
        let payload: Params = approval
            .payload
            .as_object()
            .cloned()
            .unwrap_or_default();

        // Step 3a (hub#825) — **the net, not the first line.** The runner refuses to park a payload
        // the schema already rejects, so nothing reaches this tray that could not run when it was
        // written. What this covers is the one thing that check cannot: the contract MOVING between
        // 3 AM and 9 AM, because a module updated in between.
        //
        // It refuses like the revoked grant of §7.2 and NOT like §14.8: the row stays **pending**
        // and nobody is recorded as having decided it. `approved` with an error is the honest record
        // of «the person approved and the COMMAND broke» — something ran, or could have. Here
        // nothing could: this is refused before the door, so burning the approval would leave the
        // worst possible row, one that says a person authorised something that never happened, and
        // would take away her only remaining exit (rejecting, which ends the run cleanly).
        if let Err(e) = commands::validate_payload(&self.registry, &approval.command, &payload) {
            return Err(match e {
                RuntimeError::InvalidPayload { name, detail } => RuntimeError::InvalidPayload {
                    name,
                    detail: format!(
                        "{detail}. This proposal was written when `{}` accepted it; the command's \
                         contract changed in between, so approving cannot run it. Nothing was \
                         executed and the proposal is still PENDING: reject it to close the flow, \
                         or decide again once the command accepts this payload.",
                        approval.command
                    ),
                },
                other => other,
            });
        }

        let (run, _) = flows::store::get_run(self.db.as_ref(), &self.hub_id, &approval.run_id)
            .await?;
        let outcome = self
            .execute_flow_command(
                &approval.flow_id,
                &approval.run_id,
                run.depth,
                &approval.command,
                &payload,
            )
            .await;

        match outcome {
            Ok(result) => {
                let decided = flows::approvals::mark_decided(
                    self.db.as_ref(),
                    &self.hub_id,
                    id,
                    flows::approvals::STATUS_APPROVED,
                    decided_by,
                    "",
                )
                .await?;
                // The step's output is the WHOLE turn: what the model produced before it
                // proposed (parked on the step row hours ago) plus how the proposal ended.
                let mut output = self.parked_step_output(&approval.run_id).await;
                if let Some(map) = output.as_object_mut() {
                    map.insert("status".into(), json!(flows::approvals::STATUS_APPROVED));
                    map.insert("approval_id".into(), json!(id));
                    map.insert("command".into(), json!(approval.command));
                    map.insert("result".into(), result);
                }
                self.complete_flow_io(
                    &approval.run_id,
                    &approval.step_id,
                    flows::IoResult::Done(output),
                )
                .await?;
                Ok(decided)
            }
            Err(e) => {
                // The person DID approve; what broke is the command. Both facts are recorded, and
                // the error is returned so the tray shows a failure instead of a green tick.
                let message = format!("{e}");
                flows::approvals::mark_decided(
                    self.db.as_ref(),
                    &self.hub_id,
                    id,
                    flows::approvals::STATUS_APPROVED,
                    decided_by,
                    &message,
                )
                .await?;
                self.complete_flow_io(
                    &approval.run_id,
                    &approval.step_id,
                    flows::IoResult::Failed(format!("{}: {message}", approval.command)),
                )
                .await?;
                Err(e)
            }
        }
    }

    /// **Closes the proposals nobody answered** (hub#972) — the active sweep the TTL never had.
    ///
    /// `expires_at` was read only by `claim_pending`, so a proposal past its 72 h could be neither
    /// approved nor rejected (both go through that door) and its run sat in `waiting_approval` for
    /// ever: exempt from the 90-day prune, holding a verbatim `payload` that can carry a customer's
    /// personal details. There was no action a person could take, in a hub with no way to reach the
    /// database.
    ///
    /// What it does per swept row is decided by the ROW (`on_expire`, [`flows::approvals::ExpiryPolicy`]),
    /// never by this method: `reject`/`cancel` end the run, `continue` resumes it at the next step.
    /// The default is the conservative one — the steps written after an `ai` step assumed it acted.
    /// Whatever the policy, **nothing the model proposed is executed**: an expiry is the opposite of
    /// an approval.
    ///
    /// A run that has moved on (or been deleted) since is skipped and counted as `stranded` rather
    /// than aborting the pass: the proposal is already closed, and one broken run must not stop the
    /// hub from closing the rest.
    ///
    /// **One bounded pass** (`SWEEP_BATCH` proposals), like [`retention::prune_once`] and for the
    /// same reason: the caller holds the runtime lock the tills are queueing behind, and it re-takes
    /// it per pass instead of keeping it for a whole catch-up. Driven by the hourly retention tick
    /// in `crates/server`, **before** the prune, so a run that becomes terminal here can be pruned
    /// in the same hour it stops being live.
    pub async fn sweep_expired_flow_approvals(&self) -> Result<flows::ExpirySweepReport> {
        let now = registry::now_rfc3339();
        let mut report = flows::ExpirySweepReport::default();
        let swept = flows::approvals::sweep_expired(
            self.db.as_ref(),
            &self.hub_id,
            &now,
            flows::approvals::SWEEP_BATCH,
        )
        .await?;
        for approval in &swept {
            report.expired += 1;
            let resumed = matches!(approval.on_expire, flows::approvals::ExpiryPolicy::Continue);
            let result = if resumed {
                // The turn's own output is kept and closed with how it ended — the same shape
                // an approved proposal leaves, so `steps.<id>.status` answers the question
                // «what happened here?» whichever way it went.
                let mut output = self.parked_step_output(&approval.run_id).await;
                if let Some(map) = output.as_object_mut() {
                    map.insert("status".into(), json!(flows::approvals::STATUS_EXPIRED));
                    map.insert("approval_id".into(), json!(approval.id));
                    map.insert("command".into(), json!(approval.command));
                }
                flows::IoResult::Done(output)
            } else {
                flows::IoResult::Cancelled(format!(
                    "`{}` was never decided: the proposal expired at {} and `on_expire` is \
                     `{}`",
                    approval.command,
                    approval.expires_at,
                    approval.on_expire.as_str()
                ))
            };
            match self
                .complete_flow_io(&approval.run_id, &approval.step_id, result)
                .await
            {
                Ok(()) if resumed => report.runs_resumed += 1,
                Ok(()) => report.runs_stopped += 1,
                Err(e) => {
                    report.stranded += 1;
                    eprintln!(
                        "flows: approval {} expired but its run {} could not be closed: {e}",
                        approval.id, approval.run_id
                    );
                }
            }
            // Ephemeral, WS-only, exactly like `flow.approval.created`: a tray left open all
            // night has to stop showing a question that can no longer be answered, and the
            // SCREEN is the module `flows`'s job.
            let mut payload = Params::new();
            payload.insert("approval_id".into(), Json::from(approval.id.clone()));
            payload.insert("flow_id".into(), Json::from(approval.flow_id.clone()));
            payload.insert("run_id".into(), Json::from(approval.run_id.clone()));
            payload.insert("command".into(), Json::from(approval.command.clone()));
            payload.insert("expires_at".into(), Json::from(approval.expires_at.clone()));
            payload.insert("on_expire".into(), Json::from(approval.on_expire.as_str()));
            events::notify_sink(
                &self.registry,
                registry::EventSource::Core,
                flows::approvals::EVENT_APPROVAL_EXPIRED,
                &payload,
            );
        }
        Ok(report)
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
    // Who APPROVED this command, when it only ran because a manager stepped up (hub#361). Empty
    // for everything else, which is almost everything. It sits next to `:current_user_id` on
    // purpose: together they are the double attribution rule 3 asks for — `created_by` is the
    // cashier who was at the till, `approved_by` the manager who authorised. **This exposes it;
    // hub#362 owns the row contract** (which columns every module table carries, and the
    // migration that adds them). Never settable by a caller: the dispatcher writes it only after
    // spending a grant.
    p.insert(
        "approved_by".into(),
        Json::String(ctx.approved_by.clone().unwrap_or_default()),
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
                expect_rows: None,
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

    // ── Certificado del negocio CERRADO en una demo (ADR-0197 §4 · hub#376) ────────────────

    /// 🔴 Por la puerta que la APLICA: `set_business_certificate` es lo que llama
    /// `PUT /api/business/certificate`. Y falla ANTES de la clave maestra: la demo no llega
    /// siquiera a intentar cifrar (`HUB_SECRETS_KEY` ni hace falta).
    #[tokio::test]
    async fn a_demo_hub_cannot_upload_a_business_certificate() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        rt.set_demo_hub(true);
        let err = rt
            .set_business_certificate("Zm9v", "s3cret", "hub_user:1")
            .await
            .unwrap_err();
        assert!(
            matches!(
                err,
                RuntimeError::DemoLocked {
                    lock: DemoLock::BusinessCertificate
                }
            ),
            "got {err:?}"
        );
    }

    /// «No reemplazable» sin «no borrable» sería un reemplazo en dos pasos: borrar y subir.
    #[tokio::test]
    async fn a_demo_hub_cannot_delete_the_business_certificate_either() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        rt.set_demo_hub(true);
        let err = rt.delete_business_certificate().await.unwrap_err();
        assert!(
            matches!(
                err,
                RuntimeError::DemoLocked {
                    lock: DemoLock::BusinessCertificate
                }
            ),
            "got {err:?}"
        );
    }

    /// 🔴 La otra dirección: un hub REAL sube su `.p12` como siempre. Si esta guarda se escapase a
    /// un hub de pago, el negocio no podría remitir a la AEAT — el peor fallo posible, y mudo.
    /// (Aquí falla por la clave maestra ausente, que es la guarda de al lado: lo que importa es
    /// que NO es `DemoLocked`, o sea que la puerta está abierta para él.)
    #[tokio::test]
    async fn a_real_hub_uploads_its_certificate_as_always() {
        let rt = Runtime::new(Box::new(fresh_db().await));
        assert!(!rt.is_demo_hub(), "el default de un runtime es hub normal");
        let err = rt
            .set_business_certificate("Zm9v", "s3cret", "hub_user:1")
            .await
            .unwrap_err();
        assert!(
            !matches!(err, RuntimeError::DemoLocked { .. }),
            "un hub real no puede toparse con el cierre de la demo: {err:?}"
        );
    }

    /// Leer el estado del certificado NO se cierra: la demo tiene que poder EXPLICAR que no tiene
    /// uno (es media pantalla de VeriFactu). El cierre es de escritura, no un modo ciego.
    #[tokio::test]
    async fn a_demo_hub_still_reads_its_certificate_status() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        rt.ensure_system_tables().await.expect("system tables");
        rt.set_demo_hub(true);
        let status = rt
            .business_certificate_status()
            .await
            .expect("el estado del certificado se lee siempre");
        assert_eq!(status["present"], serde_json::json!(false));
    }

    /// El marcador lo sella el host y no lo mueve nadie más: el default es hub normal.
    #[tokio::test]
    async fn the_demo_marker_is_off_until_the_host_seals_it() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        assert!(!rt.is_demo_hub());
        rt.set_demo_hub(true);
        assert!(rt.is_demo_hub());
    }
}
