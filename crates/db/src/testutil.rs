//! Test-only Postgres helpers (ADR-0154): an **ephemeral schema per test** so the runtime/db tests
//! run in parallel with full isolation, against a real Postgres.
//!
//! The tests point at `DATABASE_URL` (default `postgres://postgres:test@localhost:5433/hub_test`).
//! Each test gets its own uniquely-named schema; the pool's `search_path` is pinned to it, so every
//! unqualified `CREATE TABLE`/`INSERT`/`SELECT` lands in that schema and never collides with another
//! test's tables. Schemas are not dropped at the end of each test (a killed process could not do it
//! anyway); instead, the first `TestDb::new` of each test binary garbage-collects the schemas of
//! DEAD runs — in CI the container is throwaway, but a long-lived local container would otherwise
//! accumulate orphans until catalog queries crawl (2 822 schemas / 30 864 tables on 2026-08-06).
//!
//! Bring one up locally with:
//! ```sh
//! docker run -d --name erplora-test-pg -e POSTGRES_PASSWORD=test -p 5433:5432 postgres:18
//! ```

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};

use sqlx::postgres::PgConnectOptions;
use sqlx::{ConnectOptions, Connection};

use crate::PgAdapter;

/// Default DSN when `DATABASE_URL` is not set (matches the CI service container and the local
/// throwaway container).
pub const DEFAULT_TEST_DATABASE_URL: &str = "postgres://postgres:test@localhost:5433/hub_test";

/// The DSN the tests use: `DATABASE_URL` if set, else [`DEFAULT_TEST_DATABASE_URL`].
pub fn test_database_url() -> String {
    std::env::var("DATABASE_URL").unwrap_or_else(|_| DEFAULT_TEST_DATABASE_URL.to_string())
}

fn base_opts() -> PgConnectOptions {
    test_database_url()
        .parse()
        .expect("DATABASE_URL/DEFAULT_TEST_DATABASE_URL no es un DSN Postgres válido")
}

/// Monotonic counter for unique schema names within this process.
static SCHEMA_SEQ: AtomicU64 = AtomicU64::new(0);

fn next_schema_name() -> String {
    let n = SCHEMA_SEQ.fetch_add(1, Ordering::Relaxed);
    // pid + counter keeps it unique across parallel tests (and across concurrent test binaries).
    format!("t_{}_{}", std::process::id(), n)
}

/// An ephemeral, per-test Postgres schema. Building an [`adapter`](TestDb::adapter) twice against
/// the same `TestDb` simulates a **process restart** over the same data (used by the system-migrations
/// idempotency tests).
pub struct TestDb {
    schema: String,
    opts: PgConnectOptions,
}

impl TestDb {
    /// Ensure the base database exists and create a brand-new empty schema for this test.
    pub async fn new() -> Self {
        let opts = base_opts();
        ensure_database(&opts).await;
        let schema = next_schema_name();
        let mut conn = opts
            .clone()
            .connect()
            .await
            .expect("conectar a la BD de test (¿está el Postgres de test levantado?)");
        // One best-effort GC per test binary: schemas from dead runs (killed processes never
        // clean up after themselves) must not pile up in a long-lived local container.
        static GC_DONE: AtomicBool = AtomicBool::new(false);
        if !GC_DONE.swap(true, Ordering::Relaxed) {
            match gc_dead_run_schemas(&mut conn).await {
                Ok(0) => {}
                Ok(n) => eprintln!("testutil: dropped {n} orphan schemas from dead test runs"),
                Err(e) => eprintln!("testutil: orphan-schema GC failed (ignored): {e}"),
            }
        }
        run(
            &mut conn,
            &format!("DROP SCHEMA IF EXISTS \"{schema}\" CASCADE; CREATE SCHEMA \"{schema}\";"),
        )
        .await
        .expect("crear el esquema efímero de test");
        let _ = conn.close().await;
        Self { schema, opts }
    }

    /// The schema name backing this test (all its tables live here).
    pub fn schema(&self) -> &str {
        &self.schema
    }

    /// A fresh [`PgAdapter`] whose pool has `search_path` pinned to this test's schema.
    pub async fn adapter(&self) -> PgAdapter {
        self.adapter_with_max_connections(5).await
    }

    /// Same as [`TestDb::adapter`], with an explicit pool cap.
    ///
    /// `max_connections(1)` is how a test STATES that its calls share one connection instead of
    /// leaning on the pool handing the idle one back. Per-connection state — sqlx's
    /// prepared-statement cache above all (ERPlora/hub#1348) — is invisible to a test that cannot
    /// pin the connection down.
    pub async fn adapter_with_max_connections(&self, max_connections: u32) -> PgAdapter {
        let opts = self
            .opts
            .clone()
            .options([("search_path", self.schema.as_str())]);
        PgAdapter::connect_with_options(opts, max_connections)
            .await
            .expect("abrir el pool sobre el esquema de test")
    }
    /// An adapter whose pool is read-only **from birth**: every connection, new ones included,
    /// rejects writes with `25006`. Models "the whole cluster is read-only" (Patroni with no
    /// leader, a full disk) — the case where retrying cannot possibly help and the error has to
    /// reach the caller instead of turning into an infinite loop (ERPlora/hub#1376).
    pub async fn adapter_read_only(&self) -> PgAdapter {
        let opts = self.opts.clone().options([
            ("search_path", self.schema.as_str()),
            ("default_transaction_read_only", "on"),
        ]);
        PgAdapter::connect_with_options(opts, 5)
            .await
            .expect("abrir el pool solo-lectura sobre el esquema de test")
    }
}

/// Convenience: a fresh adapter on a brand-new ephemeral schema. Most tests want exactly this.
pub async fn fresh_db() -> PgAdapter {
    TestDb::new().await.adapter().await
}

/// Demotes every connection the pool currently holds to "replica": they stay open and pooled, but
/// refuse writes with `25006 read_only_sql_transaction`, exactly like the ex-leader does after a
/// Patroni switchover (ERPlora/hub#1376).
///
/// `SET default_transaction_read_only = on` is a faithful stand-in because sqlx runs no
/// `DISCARD ALL` when a connection goes back to the pool (there is no `after_release` hook here),
/// so the session flag survives the round trip — same SQLSTATE, same live connection.
pub async fn demote_pooled_connections_to_replica(db: &PgAdapter, how_many: usize) {
    let mut held = Vec::with_capacity(how_many);
    for _ in 0..how_many {
        let mut conn = db.pool.acquire().await.expect("acquire a pooled connection");
        sqlx::query("SET default_transaction_read_only = on")
            .execute(&mut *conn)
            .await
            .expect("mark the pooled session read-only");
        held.push(conn);
    }
    drop(held);
    wait_until_idle(db, how_many).await;
}

/// Waits until the pool has `want` connections back in the idle queue.
///
/// Dropping a `PoolConnection` hands it back through a **spawned** task, so without this the next
/// `acquire` could race it and open a brand-new (healthy) connection instead — the test would then
/// pass without ever touching the poisoned one. A false green, which is the very failure mode
/// hub#1376 is about.
async fn wait_until_idle(db: &PgAdapter, want: usize) {
    for _ in 0..1_000 {
        if db.pool.num_idle() >= want {
            return;
        }
        tokio::time::sleep(std::time::Duration::from_millis(2)).await;
    }
    panic!("the pool never returned {want} connection(s) to the idle queue");
}

/// Ensure the base database named in the DSN exists; create it via the `postgres` maintenance DB if
/// missing. Race-safe: a duplicate-database error from a concurrent creator is ignored.
async fn ensure_database(opts: &PgConnectOptions) {
    // Cheap path: if we can connect to the target DB, it already exists.
    if opts.clone().connect().await.is_ok() {
        return;
    }
    let db_name = opts.get_database().unwrap_or("hub_test").to_string();
    let mut conn = opts
        .clone()
        .database("postgres")
        .connect()
        .await
        .expect("conectar a la BD de mantenimiento 'postgres'");
    // CREATE DATABASE no puede ir en transacción; si otra ejecución la creó ya (42P04) lo ignoramos.
    let _ = run(&mut conn, &format!("CREATE DATABASE \"{db_name}\"")).await;
    let _ = conn.close().await;
}

/// Drop ephemeral schemas (`t_<pid>_<n>`) whose owning process is no longer alive on this host.
/// Returns how many were dropped. Safe under concurrency: a live run's schema is never touched
/// (its PID probes alive), and two GCs racing over the same corpses just `DROP IF EXISTS` twice.
async fn gc_dead_run_schemas(conn: &mut sqlx::PgConnection) -> Result<usize, sqlx::Error> {
    let names: Vec<String> =
        sqlx::query_scalar("SELECT nspname FROM pg_namespace WHERE nspname LIKE 't\\_%'")
            .fetch_all(&mut *conn)
            .await?;
    let dead: Vec<String> = names
        .into_iter()
        .filter(|n| matches!(schema_run_pid(n), Some(pid) if !process_alive(pid)))
        .collect();
    // Batched so one statement never grows unbounded (thousands of orphans is the normal case
    // this GC exists for).
    for chunk in dead.chunks(50) {
        let sql: String =
            chunk.iter().map(|s| format!("DROP SCHEMA IF EXISTS \"{s}\" CASCADE; ")).collect();
        run(&mut *conn, &sql).await?;
    }
    Ok(dead.len())
}

/// `t_<pid>_<n>` → the run's PID; anything else (foreign schema, unparsable name) → `None`,
/// meaning "not ours to judge": the GC leaves it alone.
fn schema_run_pid(name: &str) -> Option<i32> {
    let rest = name.strip_prefix("t_")?;
    let (pid, seq) = rest.split_once('_')?;
    seq.parse::<u64>().ok()?;
    let pid = pid.parse::<i32>().ok()?;
    (pid > 0).then_some(pid)
}

/// Is a process with this PID alive on this host? Conservative: on unsupported platforms it
/// answers "alive", so schemas are kept rather than wrongly dropped.
#[cfg(unix)]
fn process_alive(pid: i32) -> bool {
    // Signal 0 = pure existence probe: 0 → alive; EPERM → alive but not ours; ESRCH → dead.
    if unsafe { libc::kill(pid, 0) } == 0 {
        return true;
    }
    std::io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
}

#[cfg(not(unix))]
fn process_alive(_pid: i32) -> bool {
    true
}

/// Run a raw (possibly multi-statement) SQL script on a single connection.
async fn run(conn: &mut sqlx::PgConnection, sql: &str) -> Result<(), sqlx::Error> {
    sqlx::raw_sql(sqlx::AssertSqlSafe(sql.to_string()))
        .execute(&mut *conn)
        .await?;
    Ok(())
}

#[cfg(test)]
#[path = "testutil_test.rs"]
mod tests;

/// Dos adaptadores **sobre el mismo esquema**: los dos runtimes del solape blue/green, cada uno con
/// su propio pool, exactamente como en producción.
pub async fn two_adapters_sharing_a_schema() -> (PgAdapter, PgAdapter) {
    let db = TestDb::new().await;
    (db.adapter().await, db.adapter().await)
}
