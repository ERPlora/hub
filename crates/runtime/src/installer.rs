//! Ciclo de vida de módulos desde una carpeta ya extraída (ARQUITECTURA.md §4):
//! validar manifest → comprobar dependencias → migrar → registrar capacidades → estado.
//! El estado por hub se persiste en la tabla `hub_module` (§2.5). La descarga/verificación
//! SHA256 del zip es responsabilidad de `erplora-source`.
use std::path::Path;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::loader;
use crate::manifest::Manifest;
use crate::migrations;
use crate::registry::{
    CompiledSchema, ModuleStatus, NavEntry, RegisteredCommand, RegisteredQuery, Registry,
};

// Baseline (v0) de `hub_module`: PK simple `module_id`. La migración de sistema v1 (hub#31 /
// ADR-0005) la recompone a PK `(hub_id, module_id)` para BD compartida por org. Las BD nuevas
// nacen con este baseline y la v1 lo migra al arrancar (ver `system_migrations.rs`); las viejas
// que ya tienen la tabla reciben el cambio por la misma v1. No editar este baseline para añadir
// hub_id aquí: el cambio de esquema va SIEMPRE por migración versionada para que llegue a BD
// existentes (un `CREATE IF NOT EXISTS` no altera una tabla ya creada).
const ENSURE_HUB_MODULE: &str = "CREATE TABLE IF NOT EXISTS hub_module (\
    module_id TEXT PRIMARY KEY, version TEXT NOT NULL, status TEXT NOT NULL, \
    installed_at TEXT NOT NULL, updated_at TEXT NOT NULL);";

/// Asegura el baseline (v0) de `hub_module` (idempotente). Lo llama `ensure_system_tables` antes
/// de aplicar las migraciones de sistema, para que la migración v1 (que recrea/altera la tabla)
/// tenga sobre qué operar también en un hub vacío.
pub async fn ensure_hub_module_table(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_HUB_MODULE).await?;
    Ok(())
}

/// Instala el módulo de `dir` en el registro, aplica migraciones y lo deja **activo**.
/// Persiste el estado en `hub_module` **scoped por `hub_id`** (§2.5). Devuelve el id del módulo.
pub async fn install(
    db: &dyn DatabaseAdapter,
    registry: &mut Registry,
    hub_id: &str,
    dir: &Path,
) -> Result<String> {
    let manifest = Manifest::load(dir)?;

    // `hub` es el namespace RESERVADO del core (ADR-0188): el dispatcher resuelve `hub.*` antes de
    // mirar el registry, así que un módulo con ese id tendría capacidades inalcanzables y aparentaría
    // servir la identidad del propio Hub. Se rechaza en la frontera hostil (el zip de terceros).
    if manifest.id == crate::hub_users::CORE_NAMESPACE.trim_end_matches('.') {
        return Err(RuntimeError::Storage(format!(
            "`{}` es un id reservado del core: ningún módulo puede ocupar el namespace `{}`",
            manifest.id,
            crate::hub_users::CORE_NAMESPACE
        )));
    }

    // `static_files.folder` es un nombre, nunca una ruta. Se vuelve a validar en runtime aunque el
    // toolkit ya lo haga: un ZIP descargado es una frontera hostil. Si el host ha inyectado el
    // backend, materializamos la carpeta ANTES de activar el módulo.
    if let Some(static_files) = &manifest.static_files {
        if !static_files.is_valid_folder() {
            return Err(RuntimeError::Storage(format!(
                "carpeta inválida en `static_files.folder`: `{}`",
                static_files.folder
            )));
        }
        if let Some(storage) = registry.module_storage.clone() {
            storage
                .ensure_module_folder(hub_id, &static_files.folder)
                .await?;
        }
    }

    // Tablas de sistema del runtime (outbox de eventos): necesarias en cuanto un command emita.
    crate::outbox::ensure_tables(db).await?;

    if registry.is_installed(&manifest.id) {
        // Reinstalar = volver a registrar capacidades (p. ej. tras update). Limpiamos antes.
        registry.remove_module(&manifest.id);
    }

    // Dependencias declaradas deben estar ya instaladas (orden topológico = del llamador).
    for dep in &manifest.depends_on {
        if !registry.is_installed(dep) {
            return Err(RuntimeError::MissingDependency {
                module: manifest.id.clone(),
                dep: dep.clone(),
            });
        }
    }

    migrations::apply(db, dir, &manifest).await?;

    // Datos de REFERENCIA del módulo (ADR-0147): unidades de medida, categorías fiscales… lo que
    // todo hub necesita y el usuario no puede aportar. Va DESPUÉS de migrar porque escribe en las
    // tablas que las migraciones acaban de crear, y es idempotente por contrato (`WHERE NOT
    // EXISTS`), así que reinstalar no duplica.
    //
    // Esto llevaba declarado en `taxes` desde ADR-0085 sin que lo ejecutara nadie: el bloque no
    // estaba en `module.schema.json` ni había una línea de Rust que lo leyera, así que las
    // categorías fiscales canónicas y las reglas de IVA de España NO se sembraban al instalar.
    let seed_files = match db.dialect() {
        erplora_db::Dialect::Sqlite => &manifest.seed.sqlite,
        erplora_db::Dialect::Postgres => &manifest.seed.postgres,
    };
    if !seed_files.is_empty() {
        let now = crate::registry::now_rfc3339();
        for file in seed_files {
            let sql = loader::read_text(dir, file)?;
            crate::seed::apply_module_seed(db, &sql, hub_id, &now).await?;
        }
    }

    for perm in &manifest.permissions {
        registry.permissions.insert(perm.clone());
    }
    for (name, def) in &manifest.queries {
        let sql = loader::read_text(dir, &def.sql)?;
        let schema = load_schema(dir, name, def.schema.as_deref())?;
        registry.queries.insert(
            name.clone(),
            RegisteredQuery {
                module_id: manifest.id.clone(),
                def: def.clone(),
                sql,
                schema,
            },
        );
    }
    for (name, def) in &manifest.commands {
        let mut sql = Vec::with_capacity(def.sql.len());
        for rel in &def.sql {
            sql.push(loader::read_text(dir, rel)?);
        }
        // Tier 2: si el command declara un handler WASM, lee sus bytes del disco.
        // (Los handlers `native` no llevan fichero: el plugin va horneado en el runtime,
        // registrado vía `Runtime::register_native` — ADR-0009.)
        let wasm = match &def.handler {
            Some(handler) if handler.kind == "wasm" => {
                let file = handler.file.as_deref().ok_or_else(|| {
                    RuntimeError::Wasm(format!(
                        "command `{name}`: handler wasm sin `file` en el manifest"
                    ))
                })?;
                let path = dir.join(file);
                let bytes = std::fs::read(&path).map_err(|e| {
                    RuntimeError::Io(std::io::Error::new(
                        e.kind(),
                        format!("no se pudo leer wasm `{}`: {e}", path.display()),
                    ))
                })?;
                Some(bytes)
            }
            _ => None,
        };
        let schema = load_schema(dir, name, def.schema.as_deref())?;
        registry.commands.insert(
            name.clone(),
            RegisteredCommand {
                module_id: manifest.id.clone(),
                def: def.clone(),
                sql,
                wasm,
                schema,
            },
        );
    }
    for (event, listener) in &manifest.events.listen {
        registry
            .listeners
            .entry(event.clone())
            .or_default()
            .push(listener.command.clone());
    }
    for nav in &manifest.navigation {
        registry.navigation.push(NavEntry {
            module_id: manifest.id.clone(),
            nav: nav.clone(),
        });
    }
    // Traducciones del módulo (ADR-0055): `locales/*.json` del paquete → registry. Best-effort;
    // si el módulo no trae i18n, el runtime sirve los valores del manifest (inglés canónico).
    registry.set_locales(&manifest.id, Manifest::load_locales(dir));

    // Vuelca las scheduled tasks del manifest a `_scheduled_tasks` (ADR-0011). Idempotente:
    // preserva el reloj (next_run/last_run) de las tareas ya existentes en una reinstalación y
    // borra las retiradas del manifest. El `command` de cada tarea debe ser del propio módulo.
    crate::scheduler::seed_module_tasks(db, &manifest.id, &manifest.scheduled_tasks).await?;

    let id = manifest.id.clone();
    let version = manifest.version.clone();
    registry.installed.push(manifest);
    registry.status.insert(id.clone(), ModuleStatus::Active);

    persist_status(db, hub_id, &id, &version, ModuleStatus::Active).await?;
    Ok(id)
}

/// Lee y **compila** el JSON Schema del payload de una query/command (si lo declara).
/// Se compila UNA vez aquí (instalación) y queda cacheado en el `Registry`; un schema
/// ilegible o que no compila aborta la instalación con error tipado (hub#27).
fn load_schema(dir: &Path, name: &str, rel: Option<&str>) -> Result<Option<CompiledSchema>> {
    let Some(rel) = rel else { return Ok(None) };
    let text = loader::read_text(dir, rel)?;
    let value: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| RuntimeError::Schema {
            name: name.to_string(),
            detail: format!("{rel}: JSON inválido: {e}"),
        })?;
    let compiled = CompiledSchema::compile(&value).map_err(|detail| RuntimeError::Schema {
        name: name.to_string(),
        detail: format!("{rel}: {detail}"),
    })?;
    Ok(Some(compiled))
}

/// Cambia el estado (activar/desactivar) de un módulo instalado y lo persiste para `hub_id`.
pub async fn set_status(
    db: &dyn DatabaseAdapter,
    registry: &mut Registry,
    hub_id: &str,
    module_id: &str,
    status: ModuleStatus,
) -> Result<()> {
    if !registry.set_status(module_id, status) {
        return Err(RuntimeError::CommandNotFound(format!(
            "módulo no instalado: {module_id}"
        )));
    }
    let version = registry
        .installed
        .iter()
        .find(|m| m.id == module_id)
        .map(|m| m.version.clone())
        .unwrap_or_default();
    persist_status(db, hub_id, module_id, &version, status).await?;
    Ok(())
}

/// Desinstala: quita capacidades del registro y borra la fila de `hub_module` **de este hub**
/// (no toca el mismo módulo en otros hubs de la BD compartida). No borra datos.
pub async fn uninstall(
    db: &dyn DatabaseAdapter,
    registry: &mut Registry,
    hub_id: &str,
    module_id: &str,
) -> Result<()> {
    if !registry.remove_module(module_id) {
        return Err(RuntimeError::CommandNotFound(format!(
            "módulo no instalado: {module_id}"
        )));
    }
    // Quita las scheduled tasks del módulo (ADR-0011): sus capacidades dejan de existir.
    crate::scheduler::remove_module_tasks(db, module_id).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(module_id));
    db.execute(
        "DELETE FROM hub_module WHERE hub_id = :hub_id AND module_id = :module_id",
        &p,
    )
    .await?;
    Ok(())
}

/// Lee de `hub_module` el estado persistido de los módulos **de este hub** (`hub_id`), como
/// `(module_id, status)`. Filtra por `hub_id`: en una BD compartida por org, dos hubs tienen sets
/// distintos y este SELECT solo devuelve los del hub que pregunta. Lo usa la reconstrucción del
/// `Registry` para respetar el estado activo/inactivo por hub tras un reinicio. Idempotente: si la
/// tabla aún no tiene la forma hub-scoped, asegura+migra primero.
pub async fn installed_status(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<(String, ModuleStatus)>> {
    ensure_hub_module_table(db).await?;
    crate::system_migrations::apply(db, hub_id).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT module_id, status FROM hub_module WHERE hub_id = :hub_id",
            &p,
        )
        .await?;
    let mut out = Vec::with_capacity(res.rows.len());
    for row in &res.rows {
        let id = row["module_id"].as_str().unwrap_or_default().to_string();
        let status = match row["status"].as_str() {
            Some("inactive") => ModuleStatus::Inactive,
            Some("inactive_auto") => ModuleStatus::InactiveAuto,
            _ => ModuleStatus::Active,
        };
        out.push((id, status));
    }
    Ok(out)
}

/// Como [`installed_status`] pero incluye también la `version` instalada de cada módulo (para
/// localizar su carpeta en la caché de descargas `<cache>/<id>/<version>/` al RE-HIDRATAR el
/// Registry tras un reinicio). Filtra por `hub_id` (BD compartida por org). `(id, version, status)`.
pub async fn installed_status_versioned(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<(String, String, ModuleStatus)>> {
    ensure_hub_module_table(db).await?;
    crate::system_migrations::apply(db, hub_id).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT module_id, version, status FROM hub_module WHERE hub_id = :hub_id",
            &p,
        )
        .await?;
    let mut out = Vec::with_capacity(res.rows.len());
    for row in &res.rows {
        let id = row["module_id"].as_str().unwrap_or_default().to_string();
        let version = row["version"].as_str().unwrap_or_default().to_string();
        let status = match row["status"].as_str() {
            Some("inactive") => ModuleStatus::Inactive,
            Some("inactive_auto") => ModuleStatus::InactiveAuto,
            _ => ModuleStatus::Active,
        };
        out.push((id, version, status));
    }
    Ok(out)
}

/// Ordena módulos topológicamente por `depends_on` (hub#16): una dependencia va **antes** que
/// quien la declara, sin importar el orden del sistema de ficheros. Las dependencias **fuera del
/// lote** (ya instaladas, o que se validarán en `install()`) se ignoran a efectos de orden.
/// Devuelve los índices en orden de instalación; `DependencyCycle` si hay un ciclo.
///
/// `modules` = `(id, depends_on)` por módulo. DFS con marcado tri-estado (post-orden).
pub fn install_order(modules: &[(String, Vec<String>)]) -> Result<Vec<usize>> {
    use std::collections::HashMap;
    // 0 = sin visitar · 1 = en pila (si se reentra ⇒ ciclo) · 2 = terminado.
    let index: HashMap<&str, usize> = modules
        .iter()
        .enumerate()
        .map(|(i, (id, _))| (id.as_str(), i))
        .collect();
    let mut state = vec![0u8; modules.len()];
    let mut order = Vec::with_capacity(modules.len());
    for i in 0..modules.len() {
        visit(i, modules, &index, &mut state, &mut order)?;
    }
    Ok(order)
}

fn visit(
    i: usize,
    modules: &[(String, Vec<String>)],
    index: &std::collections::HashMap<&str, usize>,
    state: &mut [u8],
    order: &mut Vec<usize>,
) -> Result<()> {
    match state[i] {
        2 => return Ok(()),
        1 => {
            return Err(RuntimeError::DependencyCycle {
                module: modules[i].0.clone(),
            })
        }
        _ => {}
    }
    state[i] = 1;
    for dep in &modules[i].1 {
        if let Some(&j) = index.get(dep.as_str()) {
            visit(j, modules, index, state, order)?;
        }
    }
    state[i] = 2;
    order.push(i);
    Ok(())
}

/// Upsert del estado del módulo en `hub_module`, **scoped por `hub_id`** (§2.5). Asegura primero
/// que el esquema hub-scoped existe: baseline (v0) + migración de sistema v1 (que recompone la PK
/// a `(hub_id, module_id)`). Es idempotente y barato (las migraciones ya aplicadas se saltan), y
/// cubre el caso de instalar un módulo en un hub vacío antes de que `ensure_system_tables` corra.
async fn persist_status(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    version: &str,
    status: ModuleStatus,
) -> Result<()> {
    ensure_hub_module_table(db).await?;
    crate::system_migrations::apply(db, hub_id).await?;
    let status_str = match status {
        ModuleStatus::Active => "active",
        ModuleStatus::Inactive => "inactive",
        ModuleStatus::InactiveAuto => "inactive_auto",
    };
    let now = crate::registry::now_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(id));
    p.insert("version".into(), json!(version));
    p.insert("status".into(), json!(status_str));
    p.insert("now".into(), json!(now));
    // upsert por PK compuesta (hub_id, module_id): instalar/activar el mismo módulo en otro hub
    // de la misma BD es una fila distinta, no un conflicto.
    db.execute(
        "INSERT INTO hub_module (hub_id, module_id, version, status, installed_at, updated_at) \
         VALUES (:hub_id, :module_id, :version, :status, :now, :now) \
         ON CONFLICT(hub_id, module_id) DO UPDATE SET status = :status, version = :version, updated_at = :now",
        &p,
    ).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::install_order;
    use crate::errors::RuntimeError;

    fn m(id: &str, deps: &[&str]) -> (String, Vec<String>) {
        (id.to_string(), deps.iter().map(|s| s.to_string()).collect())
    }

    /// Comprueba que en el orden devuelto cada dependencia (dentro del lote) precede al módulo.
    fn assert_deps_before(modules: &[(String, Vec<String>)], order: &[usize]) {
        let pos: std::collections::HashMap<&str, usize> = order
            .iter()
            .enumerate()
            .map(|(p, &i)| (modules[i].0.as_str(), p))
            .collect();
        for (id, deps) in modules {
            for dep in deps {
                if let (Some(&pd), Some(&pi)) = (pos.get(dep.as_str()), pos.get(id.as_str())) {
                    assert!(pd < pi, "la dep `{dep}` debe ir antes que `{id}`");
                }
            }
        }
    }

    #[test]
    fn orders_dependency_before_dependent() {
        // invoice depende de inventory; sales de inventory; el orden del FS daría invoice primero.
        let modules = vec![
            m("invoice", &["inventory"]),
            m("sales", &["inventory", "taxes"]),
            m("inventory", &[]),
            m("taxes", &[]),
        ];
        let order = install_order(&modules).unwrap();
        assert_eq!(order.len(), 4);
        assert_deps_before(&modules, &order);
    }

    #[test]
    fn ignores_deps_outside_the_batch() {
        // `payments` depende de `core`, que no está en el lote (ya instalado): no afecta al orden
        // ni es error aquí (lo valida install() por módulo).
        let modules = vec![m("payments", &["core"]), m("cash_register", &[])];
        let order = install_order(&modules).unwrap();
        assert_eq!(order.len(), 2);
    }

    #[test]
    fn detects_cycle() {
        let modules = vec![m("a", &["b"]), m("b", &["a"])];
        let err = install_order(&modules).unwrap_err();
        assert!(matches!(err, RuntimeError::DependencyCycle { .. }));
    }

    #[test]
    fn keeps_all_independent_modules() {
        let modules = vec![m("a", &[]), m("b", &[]), m("c", &[])];
        let order = install_order(&modules).unwrap();
        assert_eq!(order.len(), 3);
        let mut ids: Vec<usize> = order.clone();
        ids.sort_unstable();
        assert_eq!(ids, vec![0, 1, 2]);
    }
}
