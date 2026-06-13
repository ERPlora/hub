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
        let schema = load_schema(dir, name, def.schema.as_deref())?;
        registry.queries.insert(
            name.clone(),
            RegisteredQuery { module_id: manifest.id.clone(), def: def.clone(), sql, schema },
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
            RegisteredCommand { module_id: manifest.id.clone(), def: def.clone(), sql, wasm, schema },
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

/// Lee y **compila** el JSON Schema del payload de una query/command (si lo declara).
/// Se compila UNA vez aquí (instalación) y queda cacheado en el `Registry`; un schema
/// ilegible o que no compila aborta la instalación con error tipado (hub#27).
fn load_schema(dir: &Path, name: &str, rel: Option<&str>) -> Result<Option<CompiledSchema>> {
    let Some(rel) = rel else { return Ok(None) };
    let text = loader::read_text(dir, rel)?;
    let value: serde_json::Value = serde_json::from_str(&text).map_err(|e| {
        RuntimeError::Schema { name: name.to_string(), detail: format!("{rel}: JSON inválido: {e}") }
    })?;
    let compiled = CompiledSchema::compile(&value).map_err(|detail| {
        RuntimeError::Schema { name: name.to_string(), detail: format!("{rel}: {detail}") }
    })?;
    Ok(Some(compiled))
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

/// Ordena módulos topológicamente por `depends_on` (hub#16): una dependencia va **antes** que
/// quien la declara, sin importar el orden del sistema de ficheros. Las dependencias **fuera del
/// lote** (ya instaladas, o que se validarán en `install()`) se ignoran a efectos de orden.
/// Devuelve los índices en orden de instalación; `DependencyCycle` si hay un ciclo.
///
/// `modules` = `(id, depends_on)` por módulo. DFS con marcado tri-estado (post-orden).
pub fn install_order(modules: &[(String, Vec<String>)]) -> Result<Vec<usize>> {
    use std::collections::HashMap;
    // 0 = sin visitar · 1 = en pila (si se reentra ⇒ ciclo) · 2 = terminado.
    let index: HashMap<&str, usize> =
        modules.iter().enumerate().map(|(i, (id, _))| (id.as_str(), i)).collect();
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
        1 => return Err(RuntimeError::DependencyCycle { module: modules[i].0.clone() }),
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

#[cfg(test)]
mod tests {
    use super::install_order;
    use crate::errors::RuntimeError;

    fn m(id: &str, deps: &[&str]) -> (String, Vec<String>) {
        (id.to_string(), deps.iter().map(|s| s.to_string()).collect())
    }

    /// Comprueba que en el orden devuelto cada dependencia (dentro del lote) precede al módulo.
    fn assert_deps_before(modules: &[(String, Vec<String>)], order: &[usize]) {
        let pos: std::collections::HashMap<&str, usize> =
            order.iter().enumerate().map(|(p, &i)| (modules[i].0.as_str(), p)).collect();
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
