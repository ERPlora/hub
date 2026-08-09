//! Aplicación de migraciones por módulo y por dialecto, idempotente.
//! Se registran en `_hub_migrations` para no reaplicarlas. ARQUITECTURA.md §8.
use std::path::Path;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::Result;
use crate::loader;
use crate::manifest::Manifest;

const ENSURE_TABLE: &str = "CREATE TABLE IF NOT EXISTS _hub_migrations (\
    module_id TEXT NOT NULL, filename TEXT NOT NULL, applied_at TEXT NOT NULL, \
    PRIMARY KEY (module_id, filename));";

pub async fn ensure_table(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_TABLE).await?;
    Ok(())
}

/// Aplica las migraciones del dialecto activo que aún no se hayan aplicado.
///
/// La lista efectiva es la **unión** `manifest ∪ migrations/<dialecto>/*.sql` del paquete,
/// ordenada por nombre de fichero (prefijos `NNN_`) — decisión 2026-07-05 (A2): varios
/// manifests publicados omiten `migrations.postgres` (o la listan a medias) aunque el `.sql`
/// viaja en el zip, y aplicar solo la lista del manifest dejaba el módulo "instalado pero
/// muerto" en Hub Cloud. Como el zip ya trae ambos dialectos, la unión los sana sin
/// republicar. Para un manifest completo la unión coincide con su lista (sin cambio).
pub async fn apply(db: &dyn DatabaseAdapter, dir: &Path, manifest: &Manifest) -> Result<()> {
    ensure_table(db).await?;

    // Hub Cloud es Postgres-only (ADR-0154): siempre el dialecto `postgres`.
    let (declared, subdir) = (&manifest.migrations.postgres, "postgres");
    let mut files: Vec<(String, crate::migration_guard::Kind)> = declared
        .iter()
        .map(|entry| (entry.file().to_string(), entry.kind()))
        .collect();
    if let Ok(entries) = std::fs::read_dir(dir.join("migrations").join(subdir)) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            if !name.ends_with(".sql") {
                continue;
            }
            // Misma ruta relativa que usa el manifest: dedupe aquí y en `_hub_migrations`.
            let rel = format!("migrations/{subdir}/{name}");
            if !files.iter().any(|(f, _)| f == &rel) {
                eprintln!("⚠ módulo {}: migración {rel} no listada en el manifest — se aplica desde el paquete", manifest.id);
                // Sin declaración, `expand`: lo más restrictivo que sigue siendo el caso normal.
                files.push((rel, crate::migration_guard::Kind::Expand));
            }
        }
    }
    files.sort_by(|(a, _), (b, _)| a.cmp(b));

    for (file, kind) in &files {
        if is_applied(db, &manifest.id, file).await? {
            continue;
        }
        let sql = loader::read_text(dir, file)?;

        // 🚪 La puerta que protege (hub#542): no se fía del paquete. Devuelve las sentencias ya
        // traducidas — en un `contract`, con los `DROP` convertidos en rename.
        let plan = crate::migration_guard::check(&manifest.id, file, &sql, *kind)
            .map_err(|error| crate::errors::RuntimeError::Domain {
                code: "hub.module_migration_rejected".into(),
                message: format!("módulo `{}`, {file}: {error}", manifest.id),
            })?;

        // El SQL se ejecuta TAL CUAL salvo en un `contract`. Recomponer un batch que se ha partido
        // por `;` corrompe SQL válido —el splitter no entiende dollar-quoting— y el peor caso de
        // eso es romper un módulo que estaba bien. Ver `migration_guard::Plan`.
        match plan {
            crate::migration_guard::Plan::AsWritten => db.execute_batch(&sql).await?,
            crate::migration_guard::Plan::Rewritten(statements) => {
                db.execute_batch(&format!("{};", statements.join(";\n"))).await?
            }
        }
        record_applied(db, &manifest.id, file).await?;
    }
    Ok(())
}

async fn is_applied(db: &dyn DatabaseAdapter, module_id: &str, file: &str) -> Result<bool> {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(module_id));
    p.insert("filename".into(), json!(file));
    let res = db.query(
        "SELECT 1 AS ok FROM _hub_migrations WHERE module_id = :module_id AND filename = :filename",
        &p,
    ).await?;
    Ok(!res.rows.is_empty())
}

async fn record_applied(db: &dyn DatabaseAdapter, module_id: &str, file: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(module_id));
    p.insert("filename".into(), json!(file));
    p.insert("applied_at".into(), json!(crate::registry::now_rfc3339()));
    db.execute(
        "INSERT INTO _hub_migrations (module_id, filename, applied_at) \
         VALUES (:module_id, :filename, :applied_at)",
        &p,
    ).await?;
    Ok(())
}
