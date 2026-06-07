//! erplora-db — database abstraction for hub (ARQUITECTURA.md §8).
//!
//! Single engine **sqlx** with two pools behind the same [`DatabaseAdapter`] trait:
//! - [`SqliteAdapter`] — `SqlitePool` (local / Tauri, single-user).
//! - [`PgAdapter`]     — `PgPool`     (cloud / Aurora, multi-user).
//!
//! - **Dynamic SQL**: statements come from `module.json`/`queries/*.sql` at runtime,
//!   not known at compile time ⇒ we use `sqlx::query(&str)` (not `query_as::<T>`).
//! - Modules always write named parameters `:name`; [`translate`] lowers them to
//!   `$n` (Postgres) or `?n` (SQLite). The module never sees the positional placeholder.
//! - Rows are returned as `serde_json::Value` inside [`QueryResult`], ready for the SDK.

use async_trait::async_trait;
use serde_json::{Map, Value as Json};
use sqlx::{Column, Row, TypeInfo, ValueRef};

use sqlx::postgres::{PgPool, PgRow};
use sqlx::sqlite::{SqlitePool, SqlitePoolOptions, SqliteRow};

/// Named parameters of a statement (`:key` → JSON value).
pub type Params = Map<String, Json>;

/// SQL dialect of the active backend.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Dialect {
    Sqlite,
    Postgres,
}

#[derive(Debug, thiserror::Error)]
pub enum DbError {
    #[error("sqlx: {0}")]
    Sqlx(#[from] sqlx::Error),
}

/// Result of a **read** (`query`). Wraps the rows so we can add metadata
/// (pagination, warnings…) without breaking the trait signature. Serialized
/// into the `data` field of `envelope.schema.json` (§7.6).
#[derive(Debug, Clone, PartialEq)]
pub struct QueryResult {
    pub rows: Vec<Json>,
    pub warnings: Vec<String>,
}

impl QueryResult {
    pub fn new(rows: Vec<Json>) -> Self {
        Self { rows, warnings: Vec::new() }
    }
}

/// Result of a **write** (`execute`/`execute_tx`). `returning` is reserved
/// for `INSERT ... RETURNING`.
#[derive(Debug, Clone, PartialEq)]
pub struct CommandResult {
    pub affected: u64,
    pub returning: Option<Vec<Json>>,
    pub warnings: Vec<String>,
}

impl CommandResult {
    pub fn affected(n: u64) -> Self {
        Self { affected: n, returning: None, warnings: Vec::new() }
    }
}

/// Common contract for all backends. The runtime only knows this trait; it does not know
/// whether SQLite (local) or Postgres (cloud) sits underneath. Same contract, different impl.
#[async_trait]
pub trait DatabaseAdapter: Send + Sync {
    fn dialect(&self) -> Dialect;

    /// Runs a write. Returns affected rows.
    async fn execute(&self, sql: &str, params: &Params) -> Result<CommandResult, DbError>;

    /// Runs several statements in a **transaction** (all-or-nothing).
    async fn execute_tx(&self, ops: &[(String, Params)]) -> Result<CommandResult, DbError>;

    /// Runs a query and returns the rows as JSON objects.
    async fn query(&self, sql: &str, params: &Params) -> Result<QueryResult, DbError>;

    /// Runs a multi-statement script (migrations).
    async fn execute_batch(&self, sql: &str) -> Result<(), DbError>;
}

// ── dynamic binding ──────────────────────────────────────────────────────────────────────
//
// SQL is dynamic, so we bind in a loop over `names` (the bind order returned by `translate`).
// We use a macro instead of a helper fn to avoid spelling the type
// `Query<'q, DB, DB::Arguments<'q>>` by hand: the macro expands in context and inference picks
// Sqlite vs Postgres from the pool where `q` is executed. A single definition serves both adapters.
macro_rules! build_query {
    ($tsql:expr, $names:expr, $params:expr) => {{
        // `AssertSqlSafe`: sqlx 0.9 requires `'static` SQL or an explicit assertion (anti-injection).
        // Correct here: the SQL skeleton comes from trusted module manifests and the values are
        // bound separately (`:name` → placeholder), never interpolated into the text.
        let mut q = sqlx::query(sqlx::AssertSqlSafe($tsql));
        for name in $names.iter() {
            q = match $params.get(name) {
                // NULL. Note (TODO Fase 0): in Postgres, binding a NULL typed as TEXT may clash
                // with columns of another type; validate against real Aurora. In SQLite it doesn't matter.
                None | Some(Json::Null) => q.bind(Option::<String>::None),
                Some(Json::Bool(b)) => q.bind(*b),
                Some(Json::Number(n)) => {
                    if let Some(i) = n.as_i64() {
                        q.bind(i)
                    } else if let Some(u) = n.as_u64() {
                        q.bind(u as i64)
                    } else {
                        q.bind(n.as_f64().unwrap_or(0.0))
                    }
                }
                Some(Json::String(s)) => q.bind(s.clone()),
                Some(other) => q.bind(other.to_string()), // arrays/objects → JSON string
            };
        }
        q
    }};
}

// ── SQLite backend (local / Tauri) ───────────────────────────────────────────────────────

/// SQLite backend over `SqlitePool`. Local is single-user, so the pool is small.
pub struct SqliteAdapter {
    pool: SqlitePool,
}

impl SqliteAdapter {
    /// Opens (or creates) a SQLite DB. `url` in sqlx style: `sqlite:///path/hub.db` or
    /// `sqlite::memory:`.
    pub async fn connect(url: &str) -> Result<Self, DbError> {
        let pool = SqlitePool::connect(url).await?;
        Ok(Self { pool })
    }

    /// In-memory DB for tests. `max_connections(1)` is **mandatory**: with several
    /// connections, each would open a separate in-memory DB and tests wouldn't see the table.
    pub async fn open_in_memory() -> Result<Self, DbError> {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await?;
        Ok(Self { pool })
    }
}

#[async_trait]
impl DatabaseAdapter for SqliteAdapter {
    fn dialect(&self) -> Dialect {
        Dialect::Sqlite
    }

    async fn execute(&self, sql: &str, params: &Params) -> Result<CommandResult, DbError> {
        let (tsql, names) = translate(sql, Dialect::Sqlite);
        let q = build_query!(tsql, names, params);
        let res = q.execute(&self.pool).await?;
        Ok(CommandResult::affected(res.rows_affected()))
    }

    async fn execute_tx(&self, ops: &[(String, Params)]) -> Result<CommandResult, DbError> {
        let mut tx = self.pool.begin().await?;
        let mut total = 0u64;
        for (sql, params) in ops {
            let (tsql, names) = translate(sql, Dialect::Sqlite);
            let q = build_query!(tsql, names, params);
            total += q.execute(&mut *tx).await?.rows_affected();
        }
        tx.commit().await?;
        Ok(CommandResult::affected(total))
    }

    async fn query(&self, sql: &str, params: &Params) -> Result<QueryResult, DbError> {
        let (tsql, names) = translate(sql, Dialect::Sqlite);
        let q = build_query!(tsql, names, params);
        let rows = q.fetch_all(&self.pool).await?;
        let out = rows.iter().map(sqlite_row_to_json).collect();
        Ok(QueryResult::new(out))
    }

    async fn execute_batch(&self, sql: &str) -> Result<(), DbError> {
        sqlx::raw_sql(sqlx::AssertSqlSafe(sql)).execute(&self.pool).await?;
        Ok(())
    }
}

/// SQLite row → JSON object.
fn sqlite_row_to_json(row: &SqliteRow) -> Json {
    let mut obj = Map::new();
    for col in row.columns() {
        obj.insert(col.name().to_string(), sqlite_cell(row, col.ordinal()));
    }
    Json::Object(obj)
}

/// SQLite cell → JSON, driven by the **runtime storage class** (SQLite is dynamically typed,
/// so the reliable type is the value's, not the declared column's).
fn sqlite_cell(row: &SqliteRow, i: usize) -> Json {
    // Read the raw value only to learn its type and discard NULL; then decode.
    let ty = {
        let Ok(raw) = row.try_get_raw(i) else { return Json::Null };
        if raw.is_null() {
            return Json::Null;
        }
        raw.type_info().name().to_string()
    };
    match ty.as_str() {
        "INTEGER" | "BOOLEAN" => row.try_get::<i64, _>(i).map(Json::from).unwrap_or(Json::Null),
        "REAL" => row.try_get::<f64, _>(i).map(Json::from).unwrap_or(Json::Null),
        // TEXT, BLOB and everything else → string (BLOB is lost if not UTF-8: falls to null).
        _ => row.try_get::<String, _>(i).map(Json::String).unwrap_or(Json::Null),
    }
}

// ── Postgres backend (cloud / Aurora) ────────────────────────────────────────────────────

/// Postgres backend over `PgPool`. Pool tuning (max_connections per plan, TLS,
/// timeouts) is injected via environment at construction — pending (§8, managed by Cloud).
pub struct PgAdapter {
    pool: PgPool,
}

impl PgAdapter {
    /// Connects with a standard Postgres DSN (`postgres://user:pass@host:5432/db`).
    /// TODO §8: use `PgPoolOptions` with max_connections (per plan, via env), TLS require,
    /// max_lifetime/idle_timeout to survive Aurora failovers.
    pub async fn connect(dsn: &str) -> Result<Self, DbError> {
        let pool = PgPool::connect(dsn).await?;
        Ok(Self { pool })
    }
}

#[async_trait]
impl DatabaseAdapter for PgAdapter {
    fn dialect(&self) -> Dialect {
        Dialect::Postgres
    }

    async fn execute(&self, sql: &str, params: &Params) -> Result<CommandResult, DbError> {
        let (tsql, names) = translate(sql, Dialect::Postgres);
        let q = build_query!(tsql, names, params);
        let res = q.execute(&self.pool).await?;
        Ok(CommandResult::affected(res.rows_affected()))
    }

    async fn execute_tx(&self, ops: &[(String, Params)]) -> Result<CommandResult, DbError> {
        let mut tx = self.pool.begin().await?;
        let mut total = 0u64;
        for (sql, params) in ops {
            let (tsql, names) = translate(sql, Dialect::Postgres);
            let q = build_query!(tsql, names, params);
            total += q.execute(&mut *tx).await?.rows_affected();
        }
        tx.commit().await?;
        Ok(CommandResult::affected(total))
    }

    async fn query(&self, sql: &str, params: &Params) -> Result<QueryResult, DbError> {
        let (tsql, names) = translate(sql, Dialect::Postgres);
        let q = build_query!(tsql, names, params);
        let rows = q.fetch_all(&self.pool).await?;
        let out = rows.iter().map(pg_row_to_json).collect();
        Ok(QueryResult::new(out))
    }

    async fn execute_batch(&self, sql: &str) -> Result<(), DbError> {
        sqlx::raw_sql(sqlx::AssertSqlSafe(sql)).execute(&self.pool).await?;
        Ok(())
    }
}

/// Postgres row → JSON object.
fn pg_row_to_json(row: &PgRow) -> Json {
    let mut obj = Map::new();
    for col in row.columns() {
        obj.insert(col.name().to_string(), pg_cell(row, col.ordinal()));
    }
    Json::Object(obj)
}

/// Postgres cell → JSON. Postgres is statically typed per column, so we decide by the
/// column's type name. We cover the scalar types modules use.
///
/// TODO §8/§9: NUMERIC (money), TIMESTAMPTZ, UUID and JSONB currently fall to the `_` arm
/// (string) and, in binary format, fail to `null`. A fiscal ERP needs the sqlx features
/// (`uuid`, `chrono`/`time`, `bigdecimal`/`rust_decimal`) enabled and a dedicated arm here.
fn pg_cell(row: &PgRow, i: usize) -> Json {
    // NULL first: read the raw value only to ask `is_null`.
    let is_null = row.try_get_raw(i).map(|r| r.is_null()).unwrap_or(true);
    if is_null {
        return Json::Null;
    }
    match row.column(i).type_info().name() {
        "BOOL" => row.try_get::<bool, _>(i).map(Json::from).unwrap_or(Json::Null),
        "INT2" => row.try_get::<i16, _>(i).map(|v| Json::from(v as i64)).unwrap_or(Json::Null),
        "INT4" => row.try_get::<i32, _>(i).map(|v| Json::from(v as i64)).unwrap_or(Json::Null),
        "INT8" => row.try_get::<i64, _>(i).map(Json::from).unwrap_or(Json::Null),
        "FLOAT4" => row.try_get::<f32, _>(i).map(|v| Json::from(v as f64)).unwrap_or(Json::Null),
        "FLOAT8" => row.try_get::<f64, _>(i).map(Json::from).unwrap_or(Json::Null),
        _ => row.try_get::<String, _>(i).map(Json::String).unwrap_or(Json::Null),
    }
}

// ── placeholder translator `:name` → `$n` (Postgres) / `?n` (SQLite) ──────────────────────

/// Translates named parameters `:name` (what modules write) into the dialect's positional
/// placeholders: `$1,$2…` (Postgres) or `?1,?2…` (SQLite, via sqlx).
///
/// Rules:
/// - `:ident` (alphanumeric/`_`) → `<prefix>n`, with `n` in order of first appearance; a
///   repeated name **reuses** its index (so `names` lists each name only once).
/// - `::` is the Postgres cast, never a parameter: emitted verbatim.
/// - A `:` inside a `'...'` literal is left intact.
///
/// Returns the rewritten SQL and the ordered (deduplicated) list of names, so the caller binds
/// in that order. `names` is **identical** for both dialects: only the emitted SQL changes.
pub(crate) fn translate(sql: &str, dialect: Dialect) -> (String, Vec<String>) {
    let prefix = match dialect {
        Dialect::Postgres => '$',
        Dialect::Sqlite => '?',
    };

    let mut out = String::with_capacity(sql.len());
    let bytes = sql.as_bytes();
    let mut names: Vec<String> = Vec::new();
    let mut i = 0;
    let mut in_string = false;

    while i < bytes.len() {
        let c = bytes[i] as char;

        if in_string {
            out.push(c);
            if c == '\'' {
                in_string = false;
            }
            i += 1;
            continue;
        }

        if c == '\'' {
            in_string = true;
            out.push(c);
            i += 1;
            continue;
        }

        if c == ':' {
            // `::` is the Postgres cast operator, not a parameter.
            if i + 1 < bytes.len() && bytes[i + 1] == b':' {
                out.push_str("::");
                i += 2;
                continue;
            }
            // Possible `:name`.
            let start = i + 1;
            let mut j = start;
            while j < bytes.len() && (bytes[j].is_ascii_alphanumeric() || bytes[j] == b'_') {
                j += 1;
            }
            if j > start {
                let name = &sql[start..j];
                let idx = match names.iter().position(|n| n == name) {
                    Some(p) => p + 1,
                    None => {
                        names.push(name.to_string());
                        names.len()
                    }
                };
                out.push(prefix);
                out.push_str(&idx.to_string());
                i = j;
                continue;
            }
        }

        out.push(c);
        i += 1;
    }

    (out, names)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn params(v: Json) -> Params {
        v.as_object().cloned().unwrap_or_default()
    }

    #[tokio::test]
    async fn create_insert_query_roundtrip() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        db.execute_batch(
            "CREATE TABLE t (id TEXT PRIMARY KEY, hub_id TEXT, name TEXT, price REAL);",
        )
        .await
        .unwrap();

        let res = db
            .execute(
                "INSERT INTO t (id, hub_id, name, price) VALUES (:id, :hub_id, :name, :price)",
                &params(json!({ "id": "a", "hub_id": "h1", "name": "Café", "price": 4.5 })),
            )
            .await
            .unwrap();
        assert_eq!(res.affected, 1);

        let q = db
            .query(
                "SELECT id, name, price FROM t WHERE hub_id = :hub_id",
                &params(json!({ "hub_id": "h1" })),
            )
            .await
            .unwrap();
        assert_eq!(q.rows.len(), 1);
        assert_eq!(q.rows[0]["name"], json!("Café"));
        assert_eq!(q.rows[0]["price"], json!(4.5));
    }

    #[tokio::test]
    async fn tx_is_atomic() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        db.execute_batch("CREATE TABLE t (id TEXT PRIMARY KEY);").await.unwrap();
        let res = db
            .execute_tx(&[
                ("INSERT INTO t (id) VALUES (:id)".into(), params(json!({"id":"x"}))),
                ("INSERT INTO t (id) VALUES (:id)".into(), params(json!({"id":"x"}))),
            ])
            .await;
        assert!(res.is_err());
        let q = db.query("SELECT id FROM t", &Params::new()).await.unwrap();
        assert_eq!(q.rows.len(), 0, "the transaction must roll back entirely");
    }

    // ── translator `:name` → positional (no DB) ──────────────────────────────────────────

    #[test]
    fn pg_translate_basic() {
        let (sql, names) = translate("SELECT * FROM t WHERE a = :a AND b = :b", Dialect::Postgres);
        assert_eq!(sql, "SELECT * FROM t WHERE a = $1 AND b = $2");
        assert_eq!(names, vec!["a", "b"]);
    }

    #[test]
    fn sqlite_translate_basic() {
        // Same `names`, different SQL: SQLite uses `?n`.
        let (sql, names) = translate("SELECT * FROM t WHERE a = :a AND b = :b", Dialect::Sqlite);
        assert_eq!(sql, "SELECT * FROM t WHERE a = ?1 AND b = ?2");
        assert_eq!(names, vec!["a", "b"]);
    }

    #[test]
    fn pg_translate_repeated_reuses_index() {
        let (sql, names) = translate("SELECT :x, :x, :y", Dialect::Postgres);
        assert_eq!(sql, "SELECT $1, $1, $2");
        assert_eq!(names, vec!["x", "y"]);
    }

    #[test]
    fn pg_translate_keeps_cast_operator() {
        let (sql, names) = translate("SELECT id::int FROM t WHERE id = :id", Dialect::Postgres);
        assert_eq!(sql, "SELECT id::int FROM t WHERE id = $1");
        assert_eq!(names, vec!["id"]);
    }

    #[test]
    fn pg_translate_cast_right_after_param() {
        let (sql, names) = translate("SELECT :amount::numeric", Dialect::Postgres);
        assert_eq!(sql, "SELECT $1::numeric");
        assert_eq!(names, vec!["amount"]);
    }

    #[test]
    fn pg_translate_ignores_colon_in_string_literal() {
        let (sql, names) = translate("SELECT ':notparam' AS s, :real AS r", Dialect::Postgres);
        assert_eq!(sql, "SELECT ':notparam' AS s, $1 AS r");
        assert_eq!(names, vec!["real"]);
    }

    #[test]
    fn pg_translate_returns_name_order() {
        let (sql, names) = translate("SELECT :b, :a, :b::text, ':c', :a", Dialect::Postgres);
        assert_eq!(sql, "SELECT $1, $2, $1::text, ':c', $2");
        assert_eq!(names, vec!["b", "a"]);
    }

    // ── Postgres integration (requires a real DB via DATABASE_URL, hence #[ignore]) ───────
    //
    //   DATABASE_URL=postgres://user:pass@localhost:5432/erplora_test \
    //     cargo test -p erplora-db -- --ignored
    #[tokio::test]
    #[ignore = "requires a real Postgres via DATABASE_URL"]
    async fn pg_roundtrip() {
        let url = std::env::var("DATABASE_URL").expect("set DATABASE_URL");
        let db = PgAdapter::connect(&url).await.expect("connect to postgres");
        assert_eq!(db.dialect(), Dialect::Postgres);
        db.execute_batch(
            "DROP TABLE IF EXISTS erplora_pg_test; \
             CREATE TABLE erplora_pg_test (id BIGINT, name TEXT, ok BOOLEAN, price FLOAT8)",
        )
        .await
        .unwrap();
        let res = db
            .execute(
                "INSERT INTO erplora_pg_test (id, name, ok, price) \
                 VALUES (:id, :name, :ok, :price)",
                &params(json!({"id": 1, "name": "alice", "ok": true, "price": 4.5})),
            )
            .await
            .unwrap();
        assert_eq!(res.affected, 1);
        let q = db
            .query(
                "SELECT id, name, ok, price FROM erplora_pg_test WHERE id = :id",
                &params(json!({"id": 1})),
            )
            .await
            .unwrap();
        assert_eq!(q.rows.len(), 1);
        assert_eq!(q.rows[0]["id"], json!(1));
        assert_eq!(q.rows[0]["name"], json!("alice"));
        assert_eq!(q.rows[0]["ok"], json!(true));
        assert_eq!(q.rows[0]["price"], json!(4.5));
    }
}
