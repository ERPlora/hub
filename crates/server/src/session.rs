//! Persistencia de la sesión del usuario activo (JWT + refresh) en la tabla `hub_session`.
//! Migrado a la API async de `erplora-db` (named params `:name` + `Params`).
use erplora_db::{DatabaseAdapter, DbError, Params};
use serde_json::json;

const ENSURE_HUB_SESSION: &str = "CREATE TABLE IF NOT EXISTS hub_session (\
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, hub_id TEXT NOT NULL, \
    access_token TEXT NOT NULL, refresh_token TEXT NOT NULL, created_at INTEGER NOT NULL);";

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct Session {
    pub id: String,
    pub user_id: String,
    pub hub_id: String,
    pub access_token: String,
    pub refresh_token: String,
    pub created_at: i64,
}

/// Crea la tabla `hub_session` si no existe (idempotente).
pub async fn ensure_table(db: &dyn DatabaseAdapter) -> Result<(), DbError> {
    db.execute_batch(ENSURE_HUB_SESSION).await?;
    Ok(())
}

/// Inserta una sesión.
pub async fn create(db: &dyn DatabaseAdapter, session: &Session) -> Result<(), DbError> {
    let mut p = Params::new();
    p.insert("id".into(), json!(session.id));
    p.insert("user_id".into(), json!(session.user_id));
    p.insert("hub_id".into(), json!(session.hub_id));
    p.insert("access_token".into(), json!(session.access_token));
    p.insert("refresh_token".into(), json!(session.refresh_token));
    p.insert("created_at".into(), json!(session.created_at));
    db.execute(
        "INSERT INTO hub_session (id, user_id, hub_id, access_token, refresh_token, created_at) \
         VALUES (:id, :user_id, :hub_id, :access_token, :refresh_token, :created_at)",
        &p,
    )
    .await?;
    Ok(())
}

/// Devuelve la sesión por id, o `None` si no existe.
pub async fn get(db: &dyn DatabaseAdapter, id: &str) -> Result<Option<Session>, DbError> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    let res = db
        .query(
            "SELECT id, user_id, hub_id, access_token, refresh_token, created_at \
             FROM hub_session WHERE id = :id",
            &p,
        )
        .await?;
    // Deserialize the first row (if any) into `Session`; malformed rows fall back to `None`.
    Ok(res.rows.into_iter().next().and_then(|row| serde_json::from_value(row).ok()))
}

/// Borra la sesión por id (idempotente).
pub async fn delete(db: &dyn DatabaseAdapter, id: &str) -> Result<(), DbError> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    db.execute("DELETE FROM hub_session WHERE id = :id", &p).await?;
    Ok(())
}
