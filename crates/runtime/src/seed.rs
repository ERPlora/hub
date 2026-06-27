//! Seed-al-arrancar: carga de **configuración inicial** vía SQL idempotente (hub#36).
//!
//! Mecanismo GENÉRICO (NO es "modo demo"): si el host pasa SQL de seed (env `HUB_SEED_SQL`
//! inline o `HUB_SEED_SQL_PATH` a un fichero), el runtime lo ejecuta **una vez al arrancar**,
//! **después** de [`crate::Runtime::ensure_system_tables`] (las tablas de sistema ya existen).
//!
//! Idempotencia: es responsabilidad del propio SQL (usa `WHERE NOT EXISTS` / `ON CONFLICT`),
//! igual que hacía el seed legacy. Cualquier hub puede usarlo para sembrar config inicial; el
//! caso de uso inmediato es el despliegue *demo* (un `hub_user` "Demo" + dispositivo de confianza),
//! pero la mecánica no tiene nada específico de demo.
//!
//! Se aplica sobre la **misma conexión del runtime** (mismo adaptador → funciona en SQLite y
//! Postgres). Se parte en sentencias con [`crate::system_migrations`]-style split (`;`).

use std::path::Path;

use erplora_db::{DatabaseAdapter, Dialect, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::manifest::Manifest;

/// Aplica el **seed de datos por hub** declarado por un módulo (ADR-0085), DESPUÉS de migrar. A
/// diferencia de [`apply`] (host-level, sin params), inyecta `:hub_id`/`:now`/`:current_user_id`
/// (sistema) en cada sentencia, para que el SQL del módulo siembre filas **scoped por hub**
/// (catálogo de `taxes`, alias, reglas…). Idempotente por el propio SQL (`WHERE NOT EXISTS`/
/// `ON CONFLICT`): se re-ejecuta en cada install/rehydrate sin duplicar. Selecciona el fichero del
/// **dialecto activo** (igual que las migraciones). Devuelve cuántas sentencias aplicó.
pub async fn apply_module(db: &dyn DatabaseAdapter, dir: &Path, manifest: &Manifest, hub_id: &str) -> Result<usize> {
    let files = match db.dialect() {
        Dialect::Sqlite => &manifest.seed.sqlite,
        Dialect::Postgres => &manifest.seed.postgres,
    };
    if files.is_empty() {
        return Ok(0);
    }
    let now = crate::registry::now_rfc3339();
    let mut applied = 0usize;
    for rel in files {
        let path = dir.join(rel);
        let sql = std::fs::read_to_string(&path)
            .map_err(|e| RuntimeError::Other(format!("seed: no se pudo leer `{}`: {e}", path.display())))?;
        for (i, stmt) in split_statements(&sql).iter().enumerate() {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!(hub_id));
            p.insert("now".into(), json!(now));
            p.insert("current_user_id".into(), json!("system"));
            db.execute(stmt, &p).await.map_err(|e| {
                RuntimeError::Other(format!(
                    "seed `{}` ({rel}): fallo en la sentencia #{}: {e}\n  SQL: {stmt}",
                    manifest.id,
                    i + 1
                ))
            })?;
            applied += 1;
        }
    }
    Ok(applied)
}

/// Aplica `sql` (un batch de sentencias separadas por `;`) sobre `db`, una por una.
///
/// Devuelve cuántas sentencias aplicó. Se asume que el SQL es **idempotente** (el llamador lo
/// garantiza con `WHERE NOT EXISTS`/`ON CONFLICT`); este módulo NO añade guardas: solo ejecuta.
///
/// Si una sentencia falla, devuelve un error claro (con el índice de la sentencia) para que el
/// host aborte el arranque — un seed roto debe ser visible, no silencioso.
pub async fn apply(db: &dyn DatabaseAdapter, sql: &str) -> Result<usize> {
    let stmts = split_statements(sql);
    let mut applied = 0usize;
    for (i, stmt) in stmts.iter().enumerate() {
        db.execute_batch(stmt).await.map_err(|e| {
            RuntimeError::Other(format!(
                "seed: fallo en la sentencia #{} de {}: {e}\n  SQL: {stmt}",
                i + 1,
                stmts.len()
            ))
        })?;
        applied += 1;
    }
    Ok(applied)
}

/// Parte un batch SQL en sentencias individuales (separa por `;`, descarta vacías). A diferencia de
/// [`crate::system_migrations`] (SQL horneado sin comentarios), un fichero de seed lo escribe un
/// humano y suele llevar comentarios `--`, que pueden contener `;` y romperían el split ingenuo;
/// por eso primero se **descartan las líneas de comentario `--`**. El seed es DDL/DML simple sin
/// literales con `;` embebidos. Cada sentencia se ejecuta por separado vía `execute_batch`.
fn split_statements(sql: &str) -> Vec<String> {
    let without_comments: String = sql
        .lines()
        .filter(|line| !line.trim_start().starts_with("--"))
        .collect::<Vec<_>>()
        .join("\n");
    without_comments
        .split(';')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .map(|s| format!("{s};"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::identity;
    use erplora_db::SqliteAdapter;

    /// SQL de seed del **demo** (el que el terraform pasa inline por `HUB_SEED_SQL`). Es el mismo
    /// contenido versionado en `crates/server/seeds/demo.sql`; aquí lo embebemos para que el test
    /// garantice que el hash del PIN y las columnas reales son correctos sin leer ficheros.
    const DEMO_SEED: &str = include_str!("../../server/seeds/demo.sql");

    #[tokio::test]
    async fn apply_runs_each_statement_and_is_idempotent() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        // Tres sentencias idempotentes (CREATE IF NOT EXISTS + dos inserts guardados).
        let sql = "\
CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY, v TEXT);\
INSERT INTO t (id, v) SELECT 'a', '1' WHERE NOT EXISTS (SELECT 1 FROM t WHERE id = 'a');\
INSERT INTO t (id, v) SELECT 'b', '2' WHERE NOT EXISTS (SELECT 1 FROM t WHERE id = 'b');";
        let n = apply(&db, sql).await.unwrap();
        assert_eq!(n, 3, "tres sentencias aplicadas");

        // Re-aplicar no duplica ni falla (idempotente por el propio SQL).
        apply(&db, sql).await.unwrap();
        let res = db
            .query("SELECT COUNT(*) AS c FROM t", &erplora_db::Params::new())
            .await
            .unwrap();
        assert_eq!(res.rows[0]["c"].as_i64(), Some(2), "no se duplican filas");
    }

    #[test]
    fn split_statements_drops_comment_lines() {
        let sql = "-- a comment with a ; semicolon inside\n\
                   INSERT INTO t VALUES (1);\n\
                   -- another comment;\n\
                   INSERT INTO t VALUES (2);";
        let stmts = split_statements(sql);
        assert_eq!(stmts.len(), 2, "solo las dos sentencias, no los comentarios: {stmts:?}");
        assert!(stmts[0].starts_with("INSERT INTO t VALUES (1)"));
        assert!(stmts[1].starts_with("INSERT INTO t VALUES (2)"));
    }

    #[tokio::test]
    async fn apply_reports_clear_error_on_bad_statement() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        let err = apply(&db, "SELECT * FROM no_such_table;").await.unwrap_err();
        assert!(format!("{err}").contains("seed:"), "error de seed claro: {err}");
    }

    /// GARANTÍA del seed del demo (hub#36): aplicar `demo.sql` sobre un Runtime SQLite real deja
    /// un usuario "Demo" cuyo PIN "0000" verifica, y un dispositivo de confianza `demo-trusted-device`.
    /// Si el hash del PIN o los nombres de columna fueran erróneos, este test FALLA — es la red de
    /// seguridad que pide hub#36.
    #[tokio::test]
    async fn demo_seed_enables_demo_pin_login_and_trusted_device() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        let runtime = crate::Runtime::new(Box::new(db));
        // Mismo orden que en el server: tablas de sistema primero, luego seed.
        runtime.ensure_system_tables().await.unwrap();
        let n = apply(runtime.db_for_test(), DEMO_SEED).await.unwrap();
        assert!(n >= 2, "el seed del demo aplica al menos usuario + dispositivo, fue {n}");

        // El PIN "0000" del usuario "Demo" verifica (valida el formato del hash).
        let user = runtime.verify_pin("Demo", "0000").await.unwrap();
        let user = user.expect("Demo verifica con PIN 0000");
        assert_eq!(user.name, "Demo");
        assert!(user.is_active);
        // Rol con permisos completos (admin/owner): el seed lo fija; comprobamos que NO está vacío.
        assert!(!user.role.is_empty(), "el usuario demo tiene un rol");
        // PIN incorrecto NO verifica.
        assert!(runtime.verify_pin("Demo", "1111").await.unwrap().is_none());

        // El dispositivo de confianza del demo está activo.
        assert!(
            runtime.is_device_trusted("demo-trusted-device").await.unwrap(),
            "demo-trusted-device es de confianza"
        );

        // Re-aplicar el seed es idempotente (no crea un segundo "Demo" ni falla).
        apply(runtime.db_for_test(), DEMO_SEED).await.unwrap();
        let res = identity_count_demo(&runtime).await;
        assert_eq!(res, 1, "el seed no duplica el usuario Demo al re-aplicarse");
    }

    async fn identity_count_demo(runtime: &crate::Runtime) -> i64 {
        let mut p = erplora_db::Params::new();
        p.insert("name".into(), serde_json::json!("Demo"));
        let res = runtime
            .db_for_test()
            .query("SELECT COUNT(*) AS c FROM hub_user WHERE name = :name", &p)
            .await
            .unwrap();
        res.rows[0]["c"].as_i64().unwrap_or_default()
    }

    // Sanity: el módulo de identidad expone verify_pin (compila el import).
    #[allow(unused_imports)]
    use identity::HubUser as _SeedHubUser;
}
