//! The column types of a list's base SELECT, asked of the database ONCE per installed version
//! (hub#2359).
//!
//! The list engine needs them to place a `range` bound against its column (hub#1542/hub#1566), and
//! it used to ask on every request: an `acquire` from the pool plus a describe, 0.33–0.38 ms warm,
//! for an answer that only changes when a module migrates. Measured in the review of hub#2355.
//!
//! What this memory may never do:
//!
//!  * **Outlive a migration.** A `SELECT *` keeps its text across an update that adds a column, so
//!    the text alone cannot tell the two shapes apart. The whole memory is forgotten by
//!    `installer::register_module` right before it migrates — the one place every module migration
//!    runs: install, update, reinstall, and the reload of what another task of the hub installed
//!    (hub#1875). All of it, not just that module's lists, because a list may read another
//!    module's table. Uninstalling forgets nothing: it never touches the schema.
//!  * **Cross a database.** It lives in the [`crate::registry::Registry`], and each `Runtime` owns
//!    exactly one registry and one database; a hub-per-org deploy builds one `Runtime` per org
//!    (`server::tenant`). Never a process-wide `static`.
//!  * **Cross a hub.** The key carries the `hub_id` that asked, so a runtime that adopts another
//!    `hub_id` never serves it from the previous one's answer.
//!  * **Remember a failure.** A describe that failed stores nothing: the engine degrades for that
//!    request (bounds left as written, as before hub#1542) and the next one asks again.

use std::collections::{BTreeMap, HashMap};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};

use erplora_db::{ColumnKind, DatabaseAdapter, DbError};

/// What the server answered for one base SELECT: column name → kind. Shared, never copied.
pub type ColumnKinds = Arc<BTreeMap<String, ColumnKind>>;

/// `(hub_id, base SQL)` → the column types the server resolved for it.
#[derive(Debug, Default)]
pub struct ColumnKindsCache {
    entries: Mutex<HashMap<(String, String), ColumnKinds>>,
}

impl ColumnKindsCache {
    /// The column types of `sql` for `hub_id`: remembered if already asked since the last module
    /// change, otherwise asked of `db` and remembered — only if the answer arrived.
    ///
    /// Two requests that miss at the same time both ask; the second answer simply replaces the
    /// first, which is the same one. Not worth a lock held across the round trip.
    pub async fn get_or_describe(
        &self,
        db: &dyn DatabaseAdapter,
        hub_id: &str,
        sql: &str,
    ) -> Result<ColumnKinds, DbError> {
        let key = (hub_id.to_string(), sql.to_string());
        if let Some(known) = self.entries().get(&key) {
            return Ok(known.clone());
        }
        let kinds: ColumnKinds = Arc::new(db.column_kinds(sql).await?);
        self.entries().insert(key, kinds.clone());
        Ok(kinds)
    }

    /// Forgets every answer. Called before a module migrates: the schema may change behind any
    /// list.
    pub fn forget_all(&self) {
        self.entries().clear();
    }

    /// A panic while holding this lock cannot leave a half-written answer (insert and clear are
    /// single calls), so a poisoned map is still a correct one.
    fn entries(&self) -> MutexGuard<'_, HashMap<(String, String), ColumnKinds>> {
        self.entries.lock().unwrap_or_else(PoisonError::into_inner)
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use erplora_db::{CommandResult, Params, QueryResult, RowGate, TxGatedOutcome};

    use super::*;

    /// Answers `column_kinds` with one column named after the SQL it was asked about, and counts
    /// the questions. Nothing else is ever called. (A FAILED describe is pinned against real
    /// Postgres in `tests/list_column_kinds_cache_e2e.rs`: `DbError` can only be built from a
    /// `sqlx` error, and this crate does not depend on `sqlx`.)
    #[derive(Default)]
    struct Describer {
        asked: AtomicUsize,
    }

    #[async_trait::async_trait]
    impl DatabaseAdapter for Describer {
        async fn execute(&self, _: &str, _: &Params) -> Result<CommandResult, DbError> {
            unreachable!("the cache only describes")
        }
        async fn execute_tx(&self, _: &[(String, Params)]) -> Result<CommandResult, DbError> {
            unreachable!("the cache only describes")
        }
        async fn execute_tx_gated(
            &self,
            _: &[(String, Params)],
            _: &[RowGate],
        ) -> Result<TxGatedOutcome, DbError> {
            unreachable!("the cache only describes")
        }
        async fn query(&self, _: &str, _: &Params) -> Result<QueryResult, DbError> {
            unreachable!("the cache only describes")
        }
        async fn execute_batch(&self, _: &str) -> Result<(), DbError> {
            unreachable!("the cache only describes")
        }
        async fn column_kinds(&self, sql: &str) -> Result<BTreeMap<String, ColumnKind>, DbError> {
            self.asked.fetch_add(1, Ordering::SeqCst);
            Ok(BTreeMap::from([(sql.to_string(), ColumnKind::Numeric)]))
        }
    }

    #[tokio::test]
    async fn the_same_hub_and_sql_is_asked_once() {
        let (cache, db) = (ColumnKindsCache::default(), Describer::default());

        let first = cache.get_or_describe(&db, "h1", "SELECT a").await.unwrap();
        let second = cache.get_or_describe(&db, "h1", "SELECT a").await.unwrap();

        assert_eq!(db.asked.load(Ordering::SeqCst), 1);
        assert_eq!(first, second);
        assert_eq!(second.get("SELECT a"), Some(&ColumnKind::Numeric));
    }

    #[tokio::test]
    async fn another_sql_is_its_own_question() {
        let (cache, db) = (ColumnKindsCache::default(), Describer::default());

        cache.get_or_describe(&db, "h1", "SELECT a").await.unwrap();
        let b = cache.get_or_describe(&db, "h1", "SELECT b").await.unwrap();

        assert_eq!(db.asked.load(Ordering::SeqCst), 2);
        assert!(b.contains_key("SELECT b"), "never another list's answer: {b:?}");
    }

    #[tokio::test]
    async fn another_hub_is_its_own_question() {
        let (cache, db) = (ColumnKindsCache::default(), Describer::default());

        cache.get_or_describe(&db, "h1", "SELECT a").await.unwrap();
        cache.get_or_describe(&db, "h2", "SELECT a").await.unwrap();

        assert_eq!(db.asked.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn forgetting_makes_the_next_request_ask_again() {
        let (cache, db) = (ColumnKindsCache::default(), Describer::default());

        cache.get_or_describe(&db, "h1", "SELECT a").await.unwrap();
        cache.forget_all();
        cache.get_or_describe(&db, "h1", "SELECT a").await.unwrap();

        assert_eq!(db.asked.load(Ordering::SeqCst), 2);
    }
}
