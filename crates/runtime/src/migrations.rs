//! Aplicación de migraciones por módulo y por dialecto, idempotente.
//! Se registran en `_hub_migrations` para no reaplicarlas. ARQUITECTURA.md §8.
use std::path::Path;

use erplora_db::{DatabaseAdapter, Dialect, Params};
use serde_json::json;

use crate::errors::Result;
use crate::loader;
use crate::manifest::Manifest;

const ENSURE_TABLE: &str = "CREATE TABLE IF NOT EXISTS _hub_migrations (\
    module_id TEXT NOT NULL, filename TEXT NOT NULL, applied_at TEXT NOT NULL, \
    PRIMARY KEY (module_id, filename));";

pub fn ensure_table(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_TABLE)?;
    Ok(())
}

/// Aplica las migraciones del dialecto activo que aún no se hayan aplicado.
pub fn apply(db: &dyn DatabaseAdapter, dir: &Path, manifest: &Manifest) -> Result<()> {
    ensure_table(db)?;

    let files = match db.dialect() {
        Dialect::Sqlite => &manifest.migrations.sqlite,
        Dialect::Postgres => &manifest.migrations.postgres,
    };

    for file in files {
        if is_applied(db, &manifest.id, file)? {
            continue;
        }
        let sql = loader::read_text(dir, file)?;
        db.execute_batch(&sql)?;
        record_applied(db, &manifest.id, file)?;
    }
    Ok(())
}

fn is_applied(db: &dyn DatabaseAdapter, module_id: &str, file: &str) -> Result<bool> {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(module_id));
    p.insert("filename".into(), json!(file));
    let rows = db.query(
        "SELECT 1 AS ok FROM _hub_migrations WHERE module_id = :module_id AND filename = :filename",
        &p,
    )?;
    Ok(!rows.is_empty())
}

fn record_applied(db: &dyn DatabaseAdapter, module_id: &str, file: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(module_id));
    p.insert("filename".into(), json!(file));
    p.insert("applied_at".into(), json!(crate::registry::now_rfc3339()));
    db.execute(
        "INSERT INTO _hub_migrations (module_id, filename, applied_at) \
         VALUES (:module_id, :filename, :applied_at)",
        &p,
    )?;
    Ok(())
}
