//! `_hub_meta` — the hub's own key/value system metadata.
//!
//! A tiny table (`key TEXT PRIMARY KEY, value TEXT NOT NULL`) for the markers the **host** needs to
//! remember across restarts: "the money is already in cents" ([`crate::money_backfill`]), "the
//! declared blueprint was already imported" (ADR-0212). It is deliberately NOT `hub_settings`:
//! that one is the business configuration the user edits and that travels in a bundle — these are
//! facts about this installation, and nobody should see or change them from a settings screen.
//!
//! It survives what the container does not. A Hub Cloud task is stateless (its modules live in
//! `/tmp` and are lost on a reschedule), so an in-memory "already done" flag would be re-armed on
//! every redeploy — which for a one-shot import means applying it again.
//!
//! The table has no `hub_id` column, by the same reasoning as the money backfill: since ADR-0201
//! there is **one database per hub**, so the row is already scoped by the database it lives in.

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::Result;

/// DDL of the metadata table. Idempotent: every reader ensures it before touching it.
const ENSURE_META: &str = "CREATE TABLE IF NOT EXISTS _hub_meta (\
    key TEXT PRIMARY KEY, value TEXT NOT NULL);";

/// Creates `_hub_meta` if it is missing (idempotent).
pub async fn ensure_table(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_META).await?;
    Ok(())
}

/// Value stored under `key`, or `None` if there is no such row.
pub async fn get(db: &dyn DatabaseAdapter, key: &str) -> Result<Option<String>> {
    ensure_table(db).await?;
    let mut p = Params::new();
    p.insert("key".into(), json!(key));
    let res = db
        .query("SELECT value FROM _hub_meta WHERE key = :key", &p)
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["value"].as_str().map(str::to_string)))
}

/// Writes `key = value` (UPSERT: re-writing the same marker is a no-op, not an error).
pub async fn set(db: &dyn DatabaseAdapter, key: &str, value: &str) -> Result<()> {
    ensure_table(db).await?;
    let mut p = Params::new();
    p.insert("key".into(), json!(key));
    p.insert("value".into(), json!(value));
    db.execute(
        "INSERT INTO _hub_meta (key, value) VALUES (:key, :value) \
         ON CONFLICT (key) DO UPDATE SET value = :value",
        &p,
    )
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The DDL is the one the money backfill has always used: the two must not drift apart, or a
    /// hub upgraded from an older build would find a table with a different shape than the one this
    /// module writes to.
    #[test]
    fn the_table_shape_is_the_one_the_hub_already_has() {
        assert!(ENSURE_META.contains("_hub_meta"));
        assert!(ENSURE_META.contains("key TEXT PRIMARY KEY"));
        assert!(ENSURE_META.contains("value TEXT NOT NULL"));
        // `IF NOT EXISTS` is what makes every read safe to call on a hub that never wrote a marker.
        assert!(ENSURE_META.contains("IF NOT EXISTS"));
    }
}
