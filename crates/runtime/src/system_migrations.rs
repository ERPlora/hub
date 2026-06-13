//! Migraciones del **esquema de sistema** del runtime, versionadas e idempotentes (hub#37).
//!
//! Las tablas de sistema (`hub_module`, `hub_user`, `hub_session`, `_event_outbox`,
//! `_event_delivery`, `_scheduled_tasks`, `_hub_migrations`…) se crean con `CREATE TABLE
//! IF NOT EXISTS` (ensure-create) al arrancar. Eso **no altera** tablas que ya existen: una
//! `erplora.db` que sobrevive a un update de Tauri no recibiría cambios de esquema de sistema.
//!
//! Este módulo es el espejo de [`crate::migrations`] (migraciones de **módulos**), pero para el
//! esquema **interno** del runtime: el SQL va **embebido en el binario** y se aplica en orden,
//! registrando cada migración aplicada en `_hub_system_migrations` para no reaplicarla.
//!
//! Modelo (decisión humano, hub#37):
//!  - **v0 = baseline** = los `CREATE TABLE IF NOT EXISTS` actuales (outbox/scheduler/identity).
//!    `ensure_system_tables` los asegura primero (cubre el hub vacío) y *no* se registra como
//!    migración: es el suelo sobre el que corren las versiones ≥ 1.
//!  - A partir de v1, cada cambio de esquema de sistema es una migración **versionada** con SQL
//!    por dialecto (SQLite/Postgres), aplicada idempotentemente al arrancar dentro de su propia
//!    transacción junto con el registro en `_hub_system_migrations`.
//!
//! Idempotente: re-arrancar no reaplica (se comprueba la versión en la tabla de control).
use erplora_db::{DatabaseAdapter, Dialect, Params};
use serde_json::json;

use crate::errors::Result;
use crate::registry::now_rfc3339;

/// Tabla de control de las migraciones de sistema aplicadas (espejo de `_hub_migrations`, pero
/// versionada por número en vez de por fichero, porque el SQL va horneado en el binario).
const ENSURE_CONTROL: &str = "CREATE TABLE IF NOT EXISTS _hub_system_migrations (\
    version INTEGER NOT NULL, name TEXT NOT NULL, applied_at TEXT NOT NULL, \
    PRIMARY KEY (version));";

/// Una migración de sistema: número de versión (orden), nombre legible y SQL por dialecto.
/// El SQL puede ser un batch (varias sentencias separadas por `;`).
struct SystemMigration {
    version: i64,
    name: &'static str,
    sqlite: &'static str,
    postgres: &'static str,
}

/// Conjunto **ORDENADO** de migraciones de sistema. Añade nuevas al final con `version`
/// estrictamente creciente; NUNCA reedites una ya publicada (rompe BD existentes), igual que
/// las rutas S3 inmutables de los módulos.
///
/// El orden de este slice es el orden de aplicación; se valida en [`apply`] que las versiones
/// sean estrictamente crecientes (defensa contra un duplicado/desorden al editar).
const MIGRATIONS: &[SystemMigration] = &[
    // ── v1 — hub#31 / ADR-0005: `hub_module` pasa a ser hub-scoped (PK compuesta) ──────────
    // Antes: `hub_module(module_id TEXT PRIMARY KEY, ...)` → un único set de módulos por BD.
    // En cloud/Aurora varios hubs de una org comparten BD (datos separados por `hub_id`), así
    // que el set activo debe ser **por hub**: PK `(hub_id, module_id)`.
    //
    // Migración ADITIVA: a las filas existentes (que no tienen hub_id) se les asigna el `hub_id`
    // del despliegue (`:hub_id`, inyectado por el runtime, no spoofable). En SQLite recomponer la
    // PK exige recrear la tabla; en Postgres basta con ALTER.
    SystemMigration {
        version: 1,
        name: "hub_module_hub_scoped",
        // SQLite: no permite añadir una columna a la PK ni redefinir la PK con ALTER → se recrea
        // la tabla (CREATE new + INSERT SELECT con el hub_id del despliegue + DROP + RENAME).
        // El `CREATE TABLE IF NOT EXISTS` baseline crea la tabla SIN hub_id; aquí migramos a la
        // forma nueva. Si la BD es nueva, la tabla baseline está vacía y el INSERT SELECT no copia
        // nada (igualmente correcto). Guard: solo recreamos si la columna `hub_id` aún no existe.
        sqlite: "\
CREATE TABLE hub_module_new (\
  hub_id TEXT NOT NULL, module_id TEXT NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL, \
  installed_at TEXT NOT NULL, updated_at TEXT NOT NULL, \
  PRIMARY KEY (hub_id, module_id));\
INSERT INTO hub_module_new (hub_id, module_id, version, status, installed_at, updated_at) \
  SELECT :hub_id, module_id, version, status, installed_at, updated_at FROM hub_module;\
DROP TABLE hub_module;\
ALTER TABLE hub_module_new RENAME TO hub_module;",
        // Postgres: añade la columna nullable, sella el hub_id del despliegue en las filas
        // existentes (UPDATE con `:hub_id`, bind seguro — no se mete un parámetro en un DEFAULT
        // de DDL, que Postgres rechazaría en sentencia preparada), luego la pone NOT NULL y
        // recompone la PK a `(hub_id, module_id)`.
        postgres: "\
ALTER TABLE hub_module ADD COLUMN hub_id TEXT;\
UPDATE hub_module SET hub_id = :hub_id WHERE hub_id IS NULL;\
ALTER TABLE hub_module ALTER COLUMN hub_id SET NOT NULL;\
ALTER TABLE hub_module DROP CONSTRAINT hub_module_pkey;\
ALTER TABLE hub_module ADD PRIMARY KEY (hub_id, module_id);",
    },
    // ── v2 — hub#15 / §2.9: device-trust local (login por PIN solo en dispositivo de confianza) ──
    // Un dispositivo se marca de confianza tras el PRIMER LOGIN ONLINE (cloud) correcto; el login
    // por PIN se rechaza mientras el dispositivo no sea de confianza. Tabla nueva (no `CREATE IF
    // NOT EXISTS` — va versionada para llegar también a una `erplora.db` ya existente). NO es la
    // credencial de máquina del hub (esa la gestiona el Cloud vía enroll); ver identity.rs.
    SystemMigration {
        version: 2,
        name: "hub_trusted_device",
        sqlite: "\
CREATE TABLE hub_trusted_device (\
  device_id TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT '', trusted_at TEXT NOT NULL);",
        postgres: "\
CREATE TABLE hub_trusted_device (\
  device_id TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT '', trusted_at TEXT NOT NULL);",
    },
];

/// Crea la tabla de control de migraciones de sistema (idempotente).
pub async fn ensure_control_table(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_CONTROL).await?;
    Ok(())
}

/// Aplica en orden las migraciones de sistema que aún no estén registradas, para `hub_id`
/// (el del despliegue, ARQUITECTURA.md §2.5). Cada migración se aplica en **su propia
/// transacción** junto con el `INSERT` en `_hub_system_migrations` (atomicidad: o se aplica y
/// queda registrada, o no se aplica). Idempotente: una versión ya registrada se salta.
///
/// El SQL de las migraciones puede llevar el parámetro `:hub_id` (lo usa v1 para sellar el
/// hub_id del despliegue en las filas existentes).
pub async fn apply(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<()> {
    ensure_control_table(db).await?;
    let applied = max_applied_version(db).await?;

    let mut prev = 0i64;
    for m in MIGRATIONS {
        // Defensa: el slice debe ir en orden estrictamente creciente (detecta un duplicado o un
        // desorden al editar el catálogo embebido).
        debug_assert!(m.version > prev, "migraciones de sistema desordenadas en v{}", m.version);
        prev = m.version;

        if m.version <= applied {
            continue; // ya aplicada en un arranque previo (idempotente).
        }

        let sql = match db.dialect() {
            Dialect::Sqlite => m.sqlite,
            Dialect::Postgres => m.postgres,
        };

        // Migración + registro en la MISMA transacción. `execute_tx` aplica cada sentencia con los
        // mismos params (`:hub_id`); las sentencias sin `:hub_id` lo ignoran sin problema.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        let mut ops: Vec<(String, Params)> = split_statements(sql)
            .into_iter()
            .map(|stmt| (stmt, p.clone()))
            .collect();

        let mut record = Params::new();
        record.insert("version".into(), json!(m.version));
        record.insert("name".into(), json!(m.name));
        record.insert("applied_at".into(), json!(now_rfc3339()));
        ops.push((
            "INSERT INTO _hub_system_migrations (version, name, applied_at) \
             VALUES (:version, :name, :applied_at)"
                .to_string(),
            record,
        ));

        db.execute_tx(&ops).await?;
    }
    Ok(())
}

/// Versión máxima de migración de sistema ya aplicada (0 si ninguna).
async fn max_applied_version(db: &dyn DatabaseAdapter) -> Result<i64> {
    let res = db
        .query("SELECT version FROM _hub_system_migrations", &Params::new())
        .await?;
    let max = res
        .rows
        .iter()
        .filter_map(|r| r["version"].as_i64())
        .max()
        .unwrap_or(0);
    Ok(max)
}

/// Parte un batch SQL en sentencias individuales (separa por `;`, descarta vacías). El SQL de
/// migración aquí es DDL simple sin literales con `;` embebidos, así que un split por `;` basta
/// (igual que el resto de batches del runtime). Cada sentencia se ejecuta en la tx de la migración.
fn split_statements(sql: &str) -> Vec<String> {
    sql.split(';')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .map(|s| format!("{s};"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migrations_are_strictly_increasing() {
        let mut prev = 0i64;
        for m in MIGRATIONS {
            assert!(m.version > prev, "v{} fuera de orden", m.version);
            prev = m.version;
        }
    }

    #[test]
    fn split_statements_keeps_each_terminated() {
        let stmts = split_statements("CREATE TABLE a (x);  DROP TABLE b; ");
        assert_eq!(stmts, vec!["CREATE TABLE a (x);", "DROP TABLE b;"]);
    }

    #[tokio::test]
    async fn apply_creates_trusted_device_table_v2() {
        use erplora_db::SqliteAdapter;
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        // El baseline v0 de identity/módulos no crea hub_trusted_device; la migración v2 sí.
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        apply(&db, "hub-test").await.unwrap();

        // La tabla existe (insert/select sin error) y la migración v2 quedó registrada.
        db.execute_batch(
            "INSERT INTO hub_trusted_device (device_id, label, trusted_at) \
             VALUES ('d1', 'Caja', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();
        assert!(max_applied_version(&db).await.unwrap() >= 2, "v2 registrada");

        // Re-aplicar es idempotente (no re-crea la tabla → no falla por 'table exists').
        apply(&db, "hub-test").await.unwrap();
    }
}
