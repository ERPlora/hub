//! Producción y restauración de un **dump consistente del SQLite local** (ADR-0040/0041, opción B).
//!
//! El producto **Local** = un único fichero SQLite (ADR-0040). El módulo `backup` necesita una
//! **copia consistente** del estado del hub para streamearla al Cloud (que la guarda en S3 con SSE)
//! sin **parar el hub**. Esta capa vive en `erplora-db` porque es la dueña de `sqlx`/SQLite — el
//! resto del runtime/server consume estos helpers sin tocar `sqlx` ni el path del fichero a mano.
//!
//! **Estrategia: `VACUUM INTO '<dst>'`.** SQLite hace un snapshot **transaccionalmente consistente**
//! (toma un read-lock, no copia páginas WAL a medias) hacia un **fichero nuevo y compacto** — es el
//! mecanismo recomendado para backups en caliente, superior a copiar el `.db` a pelo (que puede
//! capturar un WAL a medio aplicar). El resultado es un **fichero SQLite válido** restaurable.
//!
//! > **Nota sobre "export lógico" (`backup.md` §1).** El doc de arquitectura contempla a futuro un
//! > export **lógico** (INSERTs portables ERPlora-SQL) para reaplicar entre versiones de esquema y,
//! > más adelante, migrar Local→Cloud. La Fase 1 (ADR-0041, "backup + restore simple") restaura el
//! > **mismo** producto Local (SQLite→SQLite), así que un snapshot binario consistente es suficiente
//! > y evita reimplementar un serializador lógico. El export lógico queda como TODO (ver
//! > `host_backup.rs`) cuando entre la migración Local→Cloud (ADR aparte).

use sqlx::sqlite::SqlitePoolOptions;

use crate::DbError;

/// Produce un **dump consistente** del SQLite en `src_path` escribiéndolo en `dst_path`.
///
/// Abre una conexión **propia** (no reusa el pool vivo del hub) en solo-lectura sobre `src_path` y
/// ejecuta `VACUUM INTO '<dst_path>'`: SQLite escribe un fichero nuevo, compacto y
/// transaccionalmente consistente. No para el hub (toma un read-lock breve). `dst_path` **no** debe
/// existir (SQLite falla si el destino ya existe) — el llamador usa un tmpfile nuevo.
///
/// Devuelve el número de bytes del fichero producido.
pub async fn vacuum_into(src_path: &str, dst_path: &str) -> Result<u64, DbError> {
    // Conexión propia de solo-lectura sobre el fichero del hub (no toca el pool vivo).
    let url = format!("sqlite://{src_path}?mode=ro");
    let pool = SqlitePoolOptions::new().max_connections(1).connect(&url).await?;
    // `VACUUM INTO` no admite parámetros ligados para el path → literal SQL con las comillas
    // simples escapadas (duplicadas), el escape estándar de SQLite para string-literals.
    let escaped = dst_path.replace('\'', "''");
    let sql = format!("VACUUM INTO '{escaped}'");
    sqlx::raw_sql(sqlx::AssertSqlSafe(sql)).execute(&pool).await?;
    pool.close().await;
    let bytes = std::fs::metadata(dst_path).map(|m| m.len()).unwrap_or(0);
    Ok(bytes)
}

/// Verifica que `path` es un fichero SQLite **válido y abrible** (sanity check de un dump antes de
/// subirlo o tras descargarlo en un restore). Abre la BD en solo-lectura y corre `PRAGMA
/// integrity_check`; devuelve `Ok(())` si el motor responde `ok`.
pub async fn verify_sqlite_file(path: &str) -> Result<(), DbError> {
    let url = format!("sqlite://{path}?mode=ro");
    let pool = SqlitePoolOptions::new().max_connections(1).connect(&url).await?;
    let row: (String,) = sqlx::query_as("PRAGMA integrity_check").fetch_one(&pool).await?;
    pool.close().await;
    if row.0 == "ok" {
        Ok(())
    } else {
        Err(DbError::Sqlx(sqlx::Error::Protocol(format!(
            "integrity_check del dump SQLite falló: {}",
            row.0
        ))))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{DatabaseAdapter, SqliteAdapter};
    use serde_json::json;

    /// Roundtrip: poblar un SQLite real en disco → `vacuum_into` produce un fichero válido →
    /// reabrirlo confirma que los datos sobreviven (dump consistente y restaurable).
    #[tokio::test]
    async fn vacuum_into_produces_valid_restorable_dump() {
        let dir = std::env::temp_dir().join(format!("erplora-backup-test-{}", uuid_like()));
        std::fs::create_dir_all(&dir).unwrap();
        let src = dir.join("hub.db");
        let dst = dir.join("dump.sqlite");
        let src_s = src.to_str().unwrap();
        let dst_s = dst.to_str().unwrap();

        // Pobla la BD origen.
        {
            let db = SqliteAdapter::connect(&format!("sqlite://{src_s}?mode=rwc")).await.unwrap();
            db.execute_batch("CREATE TABLE t (id TEXT PRIMARY KEY, name TEXT)").await.unwrap();
            let mut p = crate::Params::new();
            p.insert("id".into(), json!("a1"));
            p.insert("name".into(), json!("Alice"));
            db.execute("INSERT INTO t (id, name) VALUES (:id, :name)", &p).await.unwrap();
        }

        // Dump consistente → fichero válido.
        let bytes = vacuum_into(src_s, dst_s).await.unwrap();
        assert!(bytes > 0, "el dump tiene bytes");
        verify_sqlite_file(dst_s).await.unwrap();

        // Reabrir el dump (simula restore SQLite→SQLite): los datos están.
        {
            let restored = SqliteAdapter::connect(&format!("sqlite://{dst_s}?mode=ro")).await.unwrap();
            let res = restored.query("SELECT name FROM t WHERE id = :id", &{
                let mut p = crate::Params::new();
                p.insert("id".into(), json!("a1"));
                p
            }).await.unwrap();
            assert_eq!(res.rows.len(), 1);
            assert_eq!(res.rows[0]["name"], json!("Alice"));
        }

        let _ = std::fs::remove_dir_all(&dir);
    }

    fn uuid_like() -> String {
        use std::time::{SystemTime, UNIX_EPOCH};
        format!("{}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos())
    }
}
