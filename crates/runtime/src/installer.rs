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
use crate::registry::{ModuleStatus, NavEntry, RegisteredCommand, RegisteredQuery, Registry};

const ENSURE_HUB_MODULE: &str = "CREATE TABLE IF NOT EXISTS hub_module (\
    module_id TEXT PRIMARY KEY, version TEXT NOT NULL, status TEXT NOT NULL, \
    installed_at TEXT NOT NULL, updated_at TEXT NOT NULL);";

/// Instala el módulo de `dir` en el registro, aplica migraciones y lo deja **activo**.
/// Persiste el estado en `hub_module`. Devuelve el id del módulo.
pub async fn install(db: &dyn DatabaseAdapter, registry: &mut Registry, dir: &Path) -> Result<String> {
    let manifest = Manifest::load(dir)?;

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

    for perm in &manifest.permissions {
        registry.permissions.insert(perm.clone());
    }
    for (name, def) in &manifest.queries {
        let sql = loader::read_text(dir, &def.sql)?;
        registry.queries.insert(
            name.clone(),
            RegisteredQuery { module_id: manifest.id.clone(), def: def.clone(), sql },
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
        registry.commands.insert(
            name.clone(),
            RegisteredCommand { module_id: manifest.id.clone(), def: def.clone(), sql, wasm },
        );
    }
    for (event, listener) in &manifest.events.listen {
        registry.listeners.entry(event.clone()).or_default().push(listener.command.clone());
    }
    for nav in &manifest.navigation {
        registry.navigation.push(NavEntry { module_id: manifest.id.clone(), nav: nav.clone() });
    }

    let id = manifest.id.clone();
    let version = manifest.version.clone();
    registry.installed.push(manifest);
    registry.status.insert(id.clone(), ModuleStatus::Active);

    persist_status(db, &id, &version, ModuleStatus::Active).await?;
    Ok(id)
}

/// Cambia el estado (activar/desactivar) de un módulo instalado y lo persiste.
pub async fn set_status(db: &dyn DatabaseAdapter, registry: &mut Registry, module_id: &str, status: ModuleStatus) -> Result<()> {
    if !registry.set_status(module_id, status) {
        return Err(RuntimeError::CommandNotFound(format!("módulo no instalado: {module_id}")));
    }
    let version = registry
        .installed
        .iter()
        .find(|m| m.id == module_id)
        .map(|m| m.version.clone())
        .unwrap_or_default();
    persist_status(db, module_id, &version, status).await?;
    Ok(())
}

/// Desinstala: quita capacidades del registro y borra la fila de `hub_module`. No borra datos.
pub async fn uninstall(db: &dyn DatabaseAdapter, registry: &mut Registry, module_id: &str) -> Result<()> {
    if !registry.remove_module(module_id) {
        return Err(RuntimeError::CommandNotFound(format!("módulo no instalado: {module_id}")));
    }
    let mut p = Params::new();
    p.insert("module_id".into(), json!(module_id));
    db.execute("DELETE FROM hub_module WHERE module_id = :module_id", &p).await?;
    Ok(())
}

async fn persist_status(db: &dyn DatabaseAdapter, id: &str, version: &str, status: ModuleStatus) -> Result<()> {
    db.execute_batch(ENSURE_HUB_MODULE).await?;
    let status_str = match status {
        ModuleStatus::Active => "active",
        ModuleStatus::Inactive => "inactive",
    };
    let now = crate::registry::now_rfc3339();
    let mut p = Params::new();
    p.insert("module_id".into(), json!(id));
    p.insert("version".into(), json!(version));
    p.insert("status".into(), json!(status_str));
    p.insert("now".into(), json!(now));
    // upsert por PK (SQLite ON CONFLICT).
    db.execute(
        "INSERT INTO hub_module (module_id, version, status, installed_at, updated_at) \
         VALUES (:module_id, :version, :status, :now, :now) \
         ON CONFLICT(module_id) DO UPDATE SET status = :status, version = :version, updated_at = :now",
        &p,
    ).await?;
    Ok(())
}
