//! erplora-db — database abstraction for hub (ARQUITECTURA.md §8).
//!
//! Single engine **sqlx** with a Postgres pool behind the [`DatabaseAdapter`] trait:
//! - [`PgAdapter`] — `PgPool` (Hub Cloud, multi-user, per-org database).
//!
//! Since ADR-0154 the Hub is **Postgres-only** (no local/SQLite backend, no Tauri desktop app):
//! the trait keeps a single implementation. It stays a trait so the runtime depends on the
//! contract, not the concrete pool, and so tests can inject an ephemeral adapter.
//!
//! - **Dynamic SQL**: statements come from `module.json`/`queries/*.sql` at runtime,
//!   not known at compile time ⇒ we use `sqlx::query(&str)` (not `query_as::<T>`).
//! - Modules always write named parameters `:name`; [`translate`] lowers them to `$n`
//!   (Postgres). The module never sees the positional placeholder.
//! - Rows are returned as `serde_json::Value` inside [`QueryResult`], ready for the SDK.

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, LazyLock};
use std::time::{Duration, Instant};

use async_trait::async_trait;
use serde_json::{Map, Value as Json};
use sqlx::encode::IsNull;
use sqlx::error::BoxDynError;
use sqlx::{Column, Connection, Encode, Executor, Row, Type, TypeInfo, ValueRef};

mod migration_lock;
pub use migration_lock::{MigrationLock, MigrationLockError};

use sqlx::postgres::{PgConnectOptions, PgPool, PgPoolOptions, PgRow, PgSslMode};

/// Helpers de test compartidos (esquema Postgres efímero por test). Compilados para los tests del
/// propio crate y para quien active la feature `test-util`.
#[cfg(any(test, feature = "test-util"))]
pub mod testutil;

/// Named parameters of a statement (`:key` → JSON value).
pub type Params = Map<String, Json>;

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

/// Outcome of [`DatabaseAdapter::execute_tx_gated`] (hub#140). The tx is over either way; this
/// only tells the runtime WHICH end it reached so it can either emit (committed) or raise the
/// stable `MinAffectedRows` error (rolled back). The per-op counts of the **mutation** statements
/// are carried in both branches for diagnostics and error construction.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TxGatedOutcome {
    /// The gate passed; the tx committed with these per-statement affected counts (SQL mutation +
    /// outbox inserts + `extra_ops`, in the order they were passed).
    Committed { per_op: Vec<u64> },
    /// A gate failed; the tx **rolled back** (no mutation, no outbox). `gate` is the index into
    /// the `gates` slice of the one that failed — with more than one gate in flight, "it did not
    /// commit" is not enough: the caller has to name the sub-command whose contract was broken, and
    /// mint ITS error code. `sql_counts` holds the affected counts of that gate's statements, so
    /// the runtime can report the real number.
    RolledBack { gate: usize, sql_counts: Vec<u64> },
}

/// One row-count gate over a **contiguous group** of ops inside a transaction (hub#140/#139,
/// generalised by hub#1025).
///
/// It started as a single `(sql_op_count, min)` pair because only the DECLARATIVE path was gated,
/// and there the whole command is one group. But a command resolved by a WASM/native handler emits
/// **several** operations, each one a different sub-command with its own contract — and a single
/// total is not the same question: in `customers.set_groups` the `_clear` affects 1 row and the
/// `_add` affects 0, so a summed minimum of 1 would pass while the row the user asked for was never
/// written. Each group has to be asked its own question.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RowGate {
    /// Index of the group's first op inside `ops`.
    pub first: usize,
    /// How many consecutive ops the group spans.
    pub count: usize,
    /// Required TOTAL affected rows across the group.
    pub min: u64,
}

/// What a column of a SELECT holds, boiled down to the only distinction the list engine's `range`
/// filter needs (ERPlora/hub#1542): does `>=` compare NUMBERS or does it compare STRINGS?
///
/// A `range` bound is the one place a caller's raw value meets a column with `>=`/`<=`, and a
/// caller that is not a screen — a flow, an assistant tool, an integration — sends what it has at
/// hand, which is text. Postgres has no `bigint >= text` operator, so that bound used to fail the
/// whole page with `42883`. The engine cannot decide from the VALUE either: the published
/// catalogue declares `range` over TEXT columns whose values are all digits
/// (`customers.list.f_tax_id`), so "looks like a number ⇒ compare as a number" would trade this
/// failure for a regression on a filter that works today. Only the column knows.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ColumnKind {
    /// Any of the numeric families — `int2`/`int4`/`int8`, `float4`/`float8`, `numeric`. A TEXT
    /// bound has to be read as a number before it can be compared.
    Numeric,
    /// Everything else, and the answer whenever the type is not known. TEXT above all: the row
    /// contract stores dates and instants as ISO-8601 TEXT (ADR-0007), and those already compare
    /// correctly as strings.
    Other,
}

impl ColumnKind {
    /// Maps the type NAME sqlx reports for a column (`INT8`, `TEXT`, `NUMERIC`, …).
    ///
    /// Unknown names answer [`Other`](Self::Other) on purpose: not knowing has to leave the bound
    /// exactly as the caller wrote it, never guess a conversion.
    pub fn of(type_name: &str) -> Self {
        match type_name.to_ascii_uppercase().as_str() {
            "INT2" | "INT4" | "INT8" | "FLOAT4" | "FLOAT8" | "NUMERIC" => Self::Numeric,
            _ => Self::Other,
        }
    }
}

/// Common contract for the backend. The runtime only knows this trait; it does not know the
/// concrete pool sitting underneath. One contract, one Postgres implementation (ADR-0154).
#[async_trait]
pub trait DatabaseAdapter: Send + Sync {
    /// Runs a write. Returns affected rows.
    async fn execute(&self, sql: &str, params: &Params) -> Result<CommandResult, DbError>;

    /// Runs several statements in a **transaction** (all-or-nothing).
    async fn execute_tx(&self, ops: &[(String, Params)]) -> Result<CommandResult, DbError>;

    /// Runs several statements in a **transaction** (all-or-nothing), but lets the caller **gate
    /// the commit** on the per-statement affected-row counts (hub#140).
    ///
    /// # Por qué existe
    ///
    /// A declarative command batches its mutation SQL + its `_event_outbox` INSERTs into ONE tx so
    /// that events are written iff the mutation commits (escritura atómica, ARQUITECTURA §5.4).
    /// hub#140 adds a second invariant: if the mutation affected fewer rows than the manifest
    /// demanded (`min_affected_rows`), the **whole** tx must roll back — neither the mutation nor
    /// the outbox may land — because the declared fact never happened. That check must run
    /// **inside** the tx to stay atomic: running the SQL, seeing 0 rows, and *then* trying to skip
    /// the outbox would already have committed the outbox inserts in the same batch.
    ///
    /// - `gates`: the groups to check, each a [`RowGate`]. A group NEVER covers the outbox INSERTs
    ///   (which always affect exactly 1 and would make the gate vacuous: a "confirm" over a missing
    ///   appointment mutates 0 rows but would still pass once its event INSERT is counted). An
    ///   empty slice disables gating entirely — legacy behaviour, commit unconditionally, like
    ///   [`execute_tx`].
    /// - Gates are evaluated **in order**, and the FIRST failure decides: it is the one whose
    ///   sub-command the caller will name in the error.
    ///
    /// On commit returns [`TxGatedOutcome::Committed`] with every per-op count (diagnostics); on a
    /// gate failure returns [`TxGatedOutcome::RolledBack`] naming the failed gate, so the runtime
    /// can build the stable error of THAT sub-command. A real DB error propagates as `Err` (the tx
    /// has already rolled back). `execute_tx` stays as the total-only path for callers that don't
    /// care (reset, migrations, user_profile): changing its return type would be a wider blast
    /// radius for no gain.
    async fn execute_tx_gated(
        &self,
        ops: &[(String, Params)],
        gates: &[RowGate],
    ) -> Result<TxGatedOutcome, DbError>;

    /// Runs a query and returns the rows as JSON objects.
    async fn query(&self, sql: &str, params: &Params) -> Result<QueryResult, DbError>;

    /// The [`ColumnKind`] of every column the SELECT `sql` returns, as the SERVER resolves it
    /// (ERPlora/hub#1542).
    ///
    /// The list engine asks for this when a `range` bound arrives as TEXT: only the column knows
    /// whether `>=` has to compare numbers or strings, and guessing from the value is what turns
    /// one bug into another (an all-digit tax id is a TEXT bound that looks like a number).
    ///
    /// The default answers "I do not know" (an empty map), which reads as [`ColumnKind::Other`]
    /// everywhere and leaves the bound exactly as the caller wrote it. The hub is Postgres-only
    /// (ADR-0154); the in-memory doubles of the test suite have no column types to report.
    async fn column_kinds(&self, _sql: &str) -> Result<BTreeMap<String, ColumnKind>, DbError> {
        Ok(BTreeMap::new())
    }

    /// Toma el lock que serializa **el arranque que migra** de este hub (hub#539).
    ///
    /// Con `order: start-first` (ADR-0269) hay **dos procesos del mismo hub contra la misma base**
    /// en cada actualización, y los dos corren el arranque entero. Sin esto pueden leer el mismo
    /// `max_applied_version` y aplicar la misma migración a la vez: `CREATE TABLE` sin
    /// `IF NOT EXISTS` da **42P07**, un `ALTER` deja el esquema a medias, y el `INSERT` de control
    /// choca contra la PK.
    ///
    /// La clave sale del `hub_id`, así que **dos hubs distintos no se estorban** — importa cuando
    /// la flota entera se actualiza a la vez.
    ///
    /// Si no lo consigue en `timeout_ms`, **falla**. No se cuelga: colgarse dejaría el contenedor
    /// arrancando para siempre, `/readyz` sin dar `UP`, y Swarm esperando a que expire
    /// `start_period` para revertir — cuando el diagnóstico estaba disponible desde el segundo uno.
    ///
    /// El default no bloquea nada: los adaptadores en memoria de los tests no tienen concurrencia
    /// que serializar.
    async fn migration_lock(
        &self,
        hub_id: &str,
        timeout_ms: u64,
    ) -> Result<MigrationLock, MigrationLockError> {
        let _ = (hub_id, timeout_ms);
        Ok(MigrationLock::noop())
    }

    /// Runs a multi-statement script (migrations).
    async fn execute_batch(&self, sql: &str) -> Result<(), DbError>;

    /// How many writes this adapter has had rejected by a read-only replica (`25006`) — i.e. how
    /// many times the database switched over underneath it (hub#1376).
    ///
    /// Monotonic for the life of the process, and the number the health snapshot reports: a
    /// switchover the hub survived silently is still something an operator has to be able to see.
    /// Defaults to `0` for the in-memory adapters, which have no replica to be demoted to.
    fn read_only_rejections(&self) -> u64 {
        0
    }

    /// Hands over the rejections **not yet reported to monitoring** and resets that tally.
    ///
    /// Separate from [`DatabaseAdapter::read_only_rejections`] on purpose: the running total is
    /// for whoever reads a health snapshot, while this one exists so the host raises exactly ONE
    /// alert per switchover instead of repeating the same one on every health check forever.
    fn take_unreported_read_only_rejections(&self) -> u64 {
        0
    }
}

// ── NULL binding (context-inferred OID on Postgres) ────────────────────────────────────────
//
// Binding a JSON `null` as `Option::<String>::None` sends a NULL **typed as TEXT** (OID 25).
// Postgres rejects it against a column of another type (`42804`: "column is of type bigint but
// expression is of type text") — e.g. `cash_register/commands/close_session.sql` binding
// `:closing_balance` (INTEGER nullable) as NULL.
//
// `DynNull` is a zero-sized marker for "SQL NULL of inferred type". The key is its `Encode<Postgres>`
// impl: `produces()` returns `PgTypeInfo::with_oid(Oid(0))`, the Postgres **unknown/infer** OID. In
// the Parse message that 0 tells Postgres "infer this parameter's type from context" (the target
// column), so the NULL is coerced to whatever the column is (bigint, double precision, …) instead of
// being fixed to TEXT.
#[derive(Debug, Clone, Copy)]
struct DynNull;

impl Type<sqlx::Postgres> for DynNull {
    fn type_info() -> sqlx::postgres::PgTypeInfo {
        // OID 0 = "let the server infer the parameter type from context" (the target column).
        sqlx::postgres::PgTypeInfo::with_oid(sqlx::postgres::types::Oid(0))
    }
    fn compatible(_: &sqlx::postgres::PgTypeInfo) -> bool {
        // An untyped NULL is compatible with any column; the server coerces it.
        true
    }
}

impl<'q> Encode<'q, sqlx::Postgres> for DynNull {
    fn encode_by_ref(
        &self,
        _buf: &mut sqlx::postgres::PgArgumentBuffer,
    ) -> Result<IsNull, BoxDynError> {
        // Write nothing; the -1 length prefix written by the driver marks the value as NULL.
        Ok(IsNull::Yes)
    }
    fn produces(&self) -> Option<sqlx::postgres::PgTypeInfo> {
        // Overrides `type_info()` for the Parse message: OID 0 ⇒ inferred-by-context NULL.
        Some(sqlx::postgres::PgTypeInfo::with_oid(sqlx::postgres::types::Oid(0)))
    }
}

// ── dynamic binding ──────────────────────────────────────────────────────────────────────
//
// SQL is dynamic, so we bind in a loop over `names` (the bind order returned by `translate`).
// We use a macro instead of a helper fn to avoid spelling the type
// `Query<'q, Postgres, PgArguments>` by hand: the macro expands in context and inference picks the
// Postgres pool where `q` is executed.
macro_rules! build_query {
    ($tsql:expr, $names:expr, $params:expr) => {{
        // `AssertSqlSafe`: sqlx 0.9 requires `'static` SQL or an explicit assertion (anti-injection).
        // Correct here: the SQL skeleton comes from trusted module manifests and the values are
        // bound separately (`:name` → placeholder), never interpolated into the text.
        //
        // `.persistent(false)`: do NOT let sqlx cache the prepared statement (ERPlora/hub#1348).
        // That cache is keyed on the SQL **text** alone — `get_or_prepare` reads it BEFORE it
        // looks at this flag — so the parameter types negotiated by the FIRST execution of a text
        // stay pinned to it for the life of the connection. Our SQL is dynamic and our parameters
        // are JSON, so the same text legitimately arrives with different parameter types: a `null`
        // binds as `DynNull` (OID 0, server-inferred from context) while a value binds as
        // int8/float8/text. Cache the first shape and the second is decoded against the wrong
        // type — `22P03 incorrect binary data format in bind parameter N` when the widths differ,
        // and silently wrong data when they do not.
        //
        // Cost, MEASURED and not assumed (during review of this fix; loopback Postgres 18, 400
        // reps, pool pinned to one connection). An uncached statement is NOT free: sqlx's
        // `prepare()` writes Parse+Describe, then flushes and AWAITS `ReadyForQuery` before it
        // writes Bind/Execute, so every call pays a SECOND roundtrip that a cache hit does not.
        // Point lookup 0.44 → 0.62 ms/query, list+join 0.72 → 1.00 ms, INSERT 0.57 → 0.70 ms:
        // roughly +0.15…+0.28 ms, +24 %…+40 %. Accepted deliberately — it buys back a class of
        // SILENT corruption of money and quantity fields, and a fraction of a millisecond per
        // query is not where the POS spends its latency budget. What the flag does save is the
        // `Close` on eviction: nothing is cached, so nothing is ever evicted.
        let mut q = sqlx::query(sqlx::AssertSqlSafe($tsql)).persistent(false);
        for name in $names.iter() {
            q = match $params.get(name) {
                // NULL — bound as `DynNull` (see its definition above): emits a NULL with OID 0
                // (inferred-by-context), so the server coerces it to the target column's type
                // (bigint, double precision, …) instead of fixing it to TEXT and raising 42804.
                None | Some(Json::Null) => q.bind(DynNull),
                // Row contract: flags are INTEGER 0/1, never BOOLEAN — so bind bools as `i64` 0/1
                // (kills the `bigint but expression is of type boolean` class, hub#208 / ADR-0154).
                Some(Json::Bool(b)) => q.bind(if *b { 1_i64 } else { 0_i64 }),
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

// ── Postgres backend (Hub Cloud) ─────────────────────────────────────────────────────────

/// Postgres backend over `PgPool`. `max_connections` is injected via environment at
/// construction ([`PG_MAX_CONNECTIONS_ENV`], per plan, managed by the SaaS).
pub struct PgAdapter {
    pool: PgPool,
    /// Shared with the pool's `before_acquire` hook — see [`ReplicaWatch`].
    replica: Arc<ReplicaWatch>,
}

/// Default del pool Postgres cuando [`PG_MAX_CONNECTIONS_ENV`] no está configurado: **10**, el
/// default de sqlx `PoolOptions` — cero cambio de comportamiento para los despliegues
/// existentes que no inyectan el env.
const DEFAULT_PG_MAX_CONNECTIONS: u32 = 10;

/// Env que fija el nº máximo de conexiones del pool Postgres **por hub** (entero > 0). Lo
/// inyecta el SaaS al desplegar (`plan.max_db_connections` en hubs de pago; 3 en demos —
/// ERPlora/saas#609): el tope por hub se aplica aquí, en el pool del propio hub, y el
/// `CONNECTION LIMIT` del rol de la org queda como red de seguridad.
const PG_MAX_CONNECTIONS_ENV: &str = "HUB_DB_MAX_CONNECTIONS";

/// Resuelve el tamaño del pool a partir del **valor crudo** del env. Función pura (no lee el
/// entorno del proceso) para poder testearla sin mutar envs con tests en paralelo.
///
/// - Ausente o vacío (idioma del repo para "sin configurar") → default, sin warning.
/// - Entero > 0 → ese valor.
/// - Inválido (no numérico, 0, negativo) → default + mensaje de warning para el caller.
fn resolve_pg_max_connections(raw: Option<&str>) -> (u32, Option<String>) {
    let Some(raw) = raw.map(str::trim).filter(|s| !s.is_empty()) else {
        return (DEFAULT_PG_MAX_CONNECTIONS, None);
    };
    match raw.parse::<u32>() {
        Ok(n) if n > 0 => (n, None),
        _ => (
            DEFAULT_PG_MAX_CONNECTIONS,
            Some(format!(
                "{PG_MAX_CONNECTIONS_ENV} inválido ({raw:?}): se esperaba un entero > 0; \
                 usando el default {DEFAULT_PG_MAX_CONNECTIONS}"
            )),
        ),
    }
}

/// Lee [`PG_MAX_CONNECTIONS_ENV`] del entorno en el punto de construcción (mismo idioma que
/// `HUB_MAX_ORG_POOLS` en el server) y loguea el warning si el valor es inválido.
fn pg_max_connections_from_env() -> u32 {
    let raw = std::env::var(PG_MAX_CONNECTIONS_ENV).ok();
    let (n, warning) = resolve_pg_max_connections(raw.as_deref());
    if let Some(w) = warning {
        eprintln!("db: {w}");
    }
    n
}

impl PgAdapter {
    /// Connects with a standard Postgres DSN (`postgres://user:pass@host:5432/db`).
    /// `max_connections` comes from [`PG_MAX_CONNECTIONS_ENV`] (per-hub cap injected by the
    /// SaaS at deploy time; absent/invalid → the sqlx default of 10 — ERPlora/saas#609).
    pub async fn connect(dsn: &str) -> Result<Self, DbError> {
        let opts: PgConnectOptions = dsn.parse()?;
        Self::open(opts, pg_max_connections_from_env()).await
    }

    /// Same, from explicit connect options — the door the test helpers use, so a test pool is
    /// configured **exactly** like a production one (timeouts, switchover recycling and TLS
    /// policy included) instead of proving things about a pool shape production does not have.
    #[cfg(any(test, feature = "test-util"))]
    pub(crate) async fn connect_with_options(
        opts: PgConnectOptions,
        max_connections: u32,
    ) -> Result<Self, DbError> {
        Self::open(opts, max_connections).await
    }

    /// Shared by [`connect`] and [`connect_with_options`]: builds the pool and decides its TLS
    /// policy in exactly one place, so the two entry points can never drift apart (hub#1398).
    async fn open(opts: PgConnectOptions, max_connections: u32) -> Result<Self, DbError> {
        let replica = Arc::new(ReplicaWatch::default());
        let pool = pg_pool_options(max_connections, Arc::clone(&replica))
            .connect_with(require_tls_unless_local(opts))
            .await?;
        Ok(Self { pool, replica })
    }
}

/// Ranks [`PgSslMode`] weakest-to-strongest so [`require_tls_unless_local`] can tell "already at
/// least as strong as `require`" from "still at the unset default" without hand-matching every
/// variant at each call site.
fn ssl_mode_strength(mode: PgSslMode) -> u8 {
    match mode {
        PgSslMode::Disable => 0,
        PgSslMode::Allow => 1,
        PgSslMode::Prefer => 2,
        PgSslMode::Require => 3,
        PgSslMode::VerifyCa => 4,
        PgSslMode::VerifyFull => 5,
    }
}

/// Upgrades `opts` to `sslmode=require` unless the host is the local test/dev Postgres, or the
/// DSN already asked for something at least as strong.
///
/// `Prefer` — sqlx's default when a DSN omits `sslmode` — tries SSL first but falls back to
/// plaintext without complaint if the negotiation itself fails, so a misrouted target that does
/// not offer TLS downgrades the session silently. What this buys is exactly that and no more:
/// `require` refuses the DOWNGRADE, it does not authenticate the server — sqlx sets
/// `accept_invalid_certs` for every mode below `verify-ca`, so a MITM presenting any certificate
/// still completes the handshake. Closing that needs `verify-full` plus the cluster CA shipped to
/// every hub (today's cert is self-signed, generated by the db-server entrypoint), which is its
/// own piece of work. Production's `pg_hba` already accepts nothing but
/// `hostssl` for remote connections (`infra/postgres/scripts/render_patroni_yml.sh`), so this
/// does not change what goes over the wire there — it makes the client refuse a downgrade instead
/// of relying entirely on the server side to reject it. The local container
/// (`erplora-test-pg-5433`) has no TLS configured at all, so loopback hosts are left alone —
/// hub#1398, closing the TLS half of `crates/db`'s old pending item §8 (hub#1395 closed the
/// timeouts half).
fn require_tls_unless_local(opts: PgConnectOptions) -> PgConnectOptions {
    // Both of sqlx's spellings for a Unix socket, because `fetch_socket()` honours both: the
    // `socket` field (what a DSN with a `/`-prefixed host parses into) and a bare `host` that
    // starts with `/` (where `PgConnectOptions::new()` lands by itself — `default_host()` probes
    // `/var/run/postgresql`, `/private/tmp`, `/tmp`). Missing the second one is not cosmetic:
    // sqlx runs the TLS upgrade over a UDS as well, and `Require` there dies with «server does
    // not support TLS» — Postgres never speaks SSL on a Unix socket.
    let local = opts.get_socket().is_some()
        || opts.get_host().starts_with('/')
        || matches!(opts.get_host(), "localhost" | "127.0.0.1" | "::1" | "[::1]");
    if local || ssl_mode_strength(opts.get_ssl_mode()) >= ssl_mode_strength(PgSslMode::Require) {
        return opts;
    }
    opts.ssl_mode(PgSslMode::Require)
}

// ── Leader switchover: recycling connections pinned to the replica (hub#1376) ────────────────

/// The SQLSTATE Postgres answers with when a write reaches a read-only standby.
const READ_ONLY_SQLSTATE: &str = "25006";

/// `25006 read_only_sql_transaction`: the write was refused because this session is talking to a
/// **standby**, not to the leader.
///
/// After a Patroni switchover the private LB is TCP-level: it routes only NEW connections to the
/// promoted node, and never tears down the ones already established. Those stay pinned to the
/// ex-leader — now a replica — perfectly healthy as sockets, and unable to write ever again. So
/// `25006` is a **connection** fault dressed as a query error, and the only cure is to throw the
/// connection away.
fn is_read_only_transaction(error: &sqlx::Error) -> bool {
    matches!(error.as_database_error().and_then(|e| e.code()), Some(code) if code == READ_ONLY_SQLSTATE)
}

/// Hard cap on how long a pooled connection may live. A hub with no write traffic never trips
/// `25006`, so without this its connections would sit on the ex-leader indefinitely — serving
/// reads from a node that is no longer the leader. Ten minutes bounds that window while staying
/// far too long to cause connection churn in normal operation.
const PG_MAX_LIFETIME: Duration = Duration::from_secs(600);

/// Idle connections go sooner: nothing is in flight on them, so recycling costs nothing, and it
/// keeps a quiet hub from holding a whole pool of sockets against the wrong node.
const PG_IDLE_TIMEOUT: Duration = Duration::from_secs(300);

/// Retries allowed for ONE operation after a `25006`.
///
/// With the generation drain in [`ReplicaWatch`] a single retry is already enough: the failing
/// connection is closed and every connection opened before the switchover is refused at acquire
/// time, so the retry necessarily runs on one opened afterwards. The second is margin for the
/// window in which the LB has not yet flipped its health check and hands out one more ex-leader
/// connection. It stays deliberately SMALL: if the whole cluster is read-only (Patroni with no
/// leader, a full disk) no amount of retrying helps, and a large budget would turn every request
/// into a connection storm against a database that is already in trouble.
const READ_ONLY_MAX_RETRIES: u32 = 2;

/// Monotonic process clock used to date connections. `Instant` cannot be dragged backwards by an
/// NTP step the way wall-clock time can.
static PROCESS_START: LazyLock<Instant> = LazyLock::new(Instant::now);

fn now_ms() -> u64 {
    // Saturating at u64 milliseconds would take ~584 million years of uptime.
    PROCESS_START.elapsed().as_millis() as u64
}

/// Tracks the last switchover this pool noticed, and how many writes the replica rejected.
///
/// The pool's `before_acquire` hook asks [`ReplicaWatch::is_stale`] and refuses every connection
/// **established before** that switchover. That is what makes the recovery deterministic instead
/// of merely eventual: closing only the connection that happened to fail would leave the other
/// idle ones — up to `max_connections` of them — still pinned to the ex-leader, so the next
/// several requests would fail too, one per stale connection.
#[derive(Default)]
struct ReplicaWatch {
    /// [`now_ms`] of the last `25006`; `0` means "no switchover seen yet".
    poisoned_at_ms: AtomicU64,
    /// Total writes the replica rejected. Monotonic on purpose: this is the number that still
    /// says "this hub went through a switchover" long after the log line has scrolled away.
    rejections: AtomicU64,
    /// The share of `rejections` not yet handed to monitoring. Drained by
    /// [`DatabaseAdapter::take_unreported_read_only_rejections`] so the host raises ONE alert per
    /// switchover instead of one per health check for the rest of the process's life.
    unreported: AtomicU64,
}

impl ReplicaWatch {
    /// Records a rejected write and opens a new connection generation.
    fn record_rejection(&self) {
        self.rejections.fetch_add(1, Ordering::Relaxed);
        self.unreported.fetch_add(1, Ordering::Relaxed);
        // Stored offset by one so `0` can keep meaning "never" without colliding with millisecond
        // zero — which is not a hypothetical: this is the call that initialises [`PROCESS_START`],
        // so the very first rejection of a process really does land on `now_ms() == 0`.
        self.poisoned_at_ms.store(now_ms() + 1, Ordering::Relaxed);
    }

    /// Was a connection of this age established before the last switchover we saw?
    fn is_stale(&self, age: Duration) -> bool {
        let Some(poisoned_at) = self.poisoned_at_ms.load(Ordering::Relaxed).checked_sub(1) else {
            return false; // no switchover seen yet
        };
        // Compared as AGES rather than as absolute instants (`established_at < poisoned_at`):
        // near process start the absolute form floors every subtraction to zero and calls an
        // hour-old connection fresh.
        //
        // Strictly `>`. A connection established in the very millisecond of the switchover is
        // ambiguous at this granularity, and the safe side of that doubt is to KEEP it: the retry
        // is the backstop, so wrongly keeping one costs a single `25006` that is already handled,
        // whereas wrongly discarding would throw away the fresh connection the retry just opened
        // and make every burst after a switchover reconnect its whole pool a second time.
        age.as_millis() as u64 > now_ms().saturating_sub(poisoned_at)
    }

    fn rejections(&self) -> u64 {
        self.rejections.load(Ordering::Relaxed)
    }

    fn take_unreported(&self) -> u64 {
        self.unreported.swap(0, Ordering::Relaxed)
    }
}

/// The pool configuration EVERY [`PgAdapter`] uses, production and tests alike.
fn pg_pool_options(max_connections: u32, replica: Arc<ReplicaWatch>) -> PgPoolOptions {
    PgPoolOptions::new()
        .max_connections(max_connections)
        .max_lifetime(PG_MAX_LIFETIME)
        .idle_timeout(PG_IDLE_TIMEOUT)
        .before_acquire(move |_conn, meta| {
            // Decided synchronously: this runs on every acquire and must not cost a round trip.
            // sqlx never calls `before_acquire` for a connection it has just opened, so a fresh
            // connection can never be refused here — no risk of an acquire loop.
            let fresh = !replica.is_stale(meta.age);
            Box::pin(async move { Ok(fresh) })
        })
}

/// Runs `$body` on a pooled connection bound to `$conn` and, if Postgres answers `25006`, throws
/// that connection out of the pool and runs `$body` again on a fresh one.
///
/// Retrying a write is safe here *precisely* because of what `25006` means: Postgres refused the
/// statement, so the transaction it belonged to committed **nothing**. There is no partial effect
/// to duplicate — which is why this treats `25006`, and only `25006`, this way. Every other error
/// propagates untouched on the first try.
///
/// A macro rather than a generic helper: the closure would have to be generic over the borrowed
/// connection's lifetime (`for<'c>`) while also capturing the caller's `sql`/`params`, which is
/// not expressible today without boxing everything and fighting the borrow checker for no gain.
macro_rules! on_the_leader {
    ($self:expr, |$conn:ident| $body:block) => {{
        let mut retries = 0u32;
        loop {
            let mut $conn = $self.pool.acquire().await?;
            let outcome: Result<_, sqlx::Error> = async { $body }.await;
            match outcome {
                Ok(value) => break Ok(value),
                Err(error) if is_read_only_transaction(&error) => {
                    $self.replica.record_rejection();
                    // Out of the pool for good: handing it back would give the next caller the
                    // same dead end.
                    let _ = $conn.close().await;
                    if retries >= READ_ONLY_MAX_RETRIES {
                        eprintln!(
                            "db: database still read-only after {retries} retries \
                             ({READ_ONLY_SQLSTATE}); is the cluster left without a leader? \
                             (hub#1376)"
                        );
                        break Err(DbError::from(error));
                    }
                    retries += 1;
                    eprintln!(
                        "db: a replica rejected a write ({READ_ONLY_SQLSTATE}) — the database \
                         switched over. Recycling the connections opened before it and retrying \
                         ({retries}/{READ_ONLY_MAX_RETRIES}) — hub#1376"
                    );
                }
                Err(error) => break Err(DbError::from(error)),
            }
        }
    }};
}

/// `55P03 lock_not_available`: Postgres se rindió esperando el lock (lo puso `SET LOCAL
/// lock_timeout`). Es la única forma de distinguir «otro arranque lo tiene» de un error de verdad.
fn is_lock_timeout(error: &sqlx::Error) -> bool {
    matches!(error.as_database_error().and_then(|e| e.code()), Some(code) if code == "55P03")
}

#[async_trait]
impl DatabaseAdapter for PgAdapter {
    async fn execute(&self, sql: &str, params: &Params) -> Result<CommandResult, DbError> {
        let (tsql, names) = translate(sql);
        let affected = on_the_leader!(self, |conn| {
            // Rebuilt per attempt (`AssertSqlSafe` takes the string by value). One clone of the
            // statement text against a network round trip is noise, and it keeps the retry able
            // to run the very same SQL on the new connection.
            let q = build_query!(tsql.clone(), names, params);
            Ok(q.execute(&mut *conn).await?.rows_affected())
        })?;
        Ok(CommandResult::affected(affected))
    }

    async fn execute_tx(&self, ops: &[(String, Params)]) -> Result<CommandResult, DbError> {
        let total = on_the_leader!(self, |conn| {
            let mut tx = conn.begin().await?;
            let mut total = 0u64;
            for (sql, params) in ops {
                let (tsql, names) = translate(sql);
                let q = build_query!(tsql, names, params);
                total += q.execute(&mut *tx).await?.rows_affected();
            }
            tx.commit().await?;
            Ok(total)
        })?;
        Ok(CommandResult::affected(total))
    }

    async fn execute_tx_gated(
        &self,
        ops: &[(String, Params)],
        gates: &[RowGate],
    ) -> Result<TxGatedOutcome, DbError> {
        on_the_leader!(self, |conn| {
        let mut tx = conn.begin().await?;
        let mut per_op = Vec::with_capacity(ops.len());
        for (sql, params) in ops {
            let (tsql, names) = translate(sql);
            let q = build_query!(tsql, names, params);
            per_op.push(q.execute(&mut *tx).await?.rows_affected());
        }
        // Cada gate se evalúa SOLO sobre las sentencias de SU grupo: los INSERT del outbox siempre
        // afectan 1 y no entran en ningún grupo (un "confirmar" sobre una cita inexistente muta 0
        // filas, aunque luego inserte un evento — si el evento contara, la gate pasaría siempre).
        // Y los grupos se cuentan por separado (hub#1025): sumarlos dejaría que una operación que
        // sí casó tapase a la que no, que es exactamente el id ajeno que la gate existe para cazar.
        for (i, gate) in gates.iter().enumerate() {
            let end = gate.first.saturating_add(gate.count).min(per_op.len());
            let slice = &per_op[gate.first.min(per_op.len())..end];
            let affected: u64 = slice.iter().sum();
            if affected < gate.min {
                // Rollback explícito: el default-drop de sqlx haría lo mismo al caer del scope,
                // pero dejarlo tácito es justo el tipo de "OK silencioso" que hub#140 elimina.
                tx.rollback().await?;
                return Ok(TxGatedOutcome::RolledBack {
                    gate: i,
                    sql_counts: slice.to_vec(),
                });
            }
        }
        tx.commit().await?;
        Ok(TxGatedOutcome::Committed { per_op })
        })
    }

    /// Reads never hit `25006` — a standby serves them happily — so there is nothing to retry
    /// here. They still benefit from the switchover recycling: the moment any write trips the
    /// error, the pool's `before_acquire` hook starts refusing every connection opened before it,
    /// so reads stop being served from the node that is no longer the leader.
    async fn query(&self, sql: &str, params: &Params) -> Result<QueryResult, DbError> {
        let (tsql, names) = translate(sql);
        let q = build_query!(tsql, names, params);
        let rows = q.fetch_all(&self.pool).await?;
        let out = rows.iter().map(pg_row_to_json).collect();
        Ok(QueryResult::new(out))
    }

    /// One `Parse`+`Describe` of the SELECT with the parameter types left for the server to
    /// infer, read back off the prepared statement.
    ///
    /// The answer is ALWAYS the server's, never sqlx's per-connection statement cache (hub#2359).
    /// `prepare_with` stores what it prepares in that cache, keyed on the text, and answers the
    /// next call from it without asking the server — so after a module migration added a column
    /// behind the same `SELECT *`, the connection that described the old shape kept answering it.
    /// The runtime remembers the answer per installed version (`ColumnKindsCache`) and forgets it
    /// when a module migrates, which only works if asking again really asks. So the statement is
    /// dropped from the connection right after its columns are read: one extra round trip per
    /// describe, and a describe now happens once per list per installed version, not per request.
    ///
    /// The cache is also the one hub#1348 keeps `query()` out of: sqlx keys it on the TEXT and
    /// `get_or_prepare` reads it BEFORE it honours `.persistent(false)`, so a text described here
    /// must never be one `query()` executes — the cached statement would pin the server-inferred
    /// parameter types onto that execution (a FLOAT8 bound decoded as INT8: the row vanishes,
    /// silently). Clearing covers that too; the marker below stays as the second lock, making the
    /// described text unique to this door. Postgres ignores the comment.
    async fn column_kinds(&self, sql: &str) -> Result<BTreeMap<String, ColumnKind>, DbError> {
        use sqlx::{Connection, SqlSafeStr, Statement};
        let (tsql, _names) = translate(sql);
        let described = format!("{tsql}\n/* column_kinds: described, never executed (hub#1348) */");
        let mut conn = self.pool.acquire().await?;
        let stmt = (&mut *conn)
            .prepare_with(sqlx::AssertSqlSafe(described).into_sql_str(), &[])
            .await?;
        let kinds = stmt
            .columns()
            .iter()
            .map(|c| (c.name().to_string(), ColumnKind::of(c.type_info().name())))
            .collect();
        conn.clear_cached_statements().await?;
        Ok(kinds)
    }

    async fn migration_lock(
        &self,
        hub_id: &str,
        timeout_ms: u64,
    ) -> Result<MigrationLock, MigrationLockError> {
        let mut tx = self.pool.begin().await.map_err(DbError::from)?;

        // `lock_timeout` no admite parámetro, y `timeout_ms` es un u64 nuestro: no hay entrada de
        // usuario que interpolar. `SET LOCAL` muere con la transacción, así que no contamina la
        // conexión cuando vuelva al pool.
        // `AssertSqlSafe`: sqlx 0.9 exige SQL `'static` o una aserción explícita (anti-inyección).
        // Aquí lo interpolado es un `u64` nuestro, no entrada de nadie.
        sqlx::query(sqlx::AssertSqlSafe(format!(
            "SET LOCAL lock_timeout = '{timeout_ms}ms'"
        )))
            .execute(&mut *tx)
            .await
            .map_err(DbError::from)?;

        // `hashtext()` y no un hash de Rust: la clave la calculan DOS PROCESOS DISTINTOS y tiene
        // que salir idéntica. `DefaultHasher` no garantiza estabilidad entre versiones ni entre
        // procesos; lo de Postgres sí, y de paso no hay que serializar nada.
        let taken = sqlx::query("SELECT pg_advisory_xact_lock(hashtext($1))")
            .bind(hub_id)
            .execute(&mut *tx)
            .await;

        match taken {
            Ok(_) => Ok(MigrationLock::held(tx)),
            Err(error) if is_lock_timeout(&error) => Err(MigrationLockError::Timeout {
                hub_id: hub_id.to_string(),
                waited_ms: timeout_ms,
            }),
            Err(error) => Err(MigrationLockError::Db(DbError::from(error))),
        }
    }

    async fn execute_batch(&self, sql: &str) -> Result<(), DbError> {
        // Migraciones: normaliza los tipos del `CREATE TABLE` al motor target (ADR-0007 §4b):
        // TEXT→TEXT, INTEGER→BIGINT, REAL→DOUBLE PRECISION, BLOB→BYTEA.
        let normalized = shim_ddl_types(sql);
        on_the_leader!(self, |conn| {
            sqlx::raw_sql(sqlx::AssertSqlSafe(normalized.clone())).execute(&mut *conn).await?;
            Ok(())
        })
    }

    fn read_only_rejections(&self) -> u64 {
        self.replica.rejections()
    }

    fn take_unreported_read_only_rejections(&self) -> u64 {
        self.replica.take_unreported()
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
/// column's type name. We cover the scalar types modules use plus the fiscal/money types
/// (§8/§9): NUMERIC, TIMESTAMPTZ/TIMESTAMP/DATE/TIME, UUID and JSONB/JSON.
///
/// Money/precision contract: NUMERIC is decoded to a **string** (via `BigDecimal`) so no
/// precision is lost on the JSON round-trip — modules format it in the UI. Temporals are
/// emitted as ISO-8601 strings; UUID as its canonical string; JSONB/JSON as the parsed JSON.
fn pg_cell(row: &PgRow, i: usize) -> Json {
    use sqlx::types::chrono::{DateTime, NaiveDate, NaiveDateTime, NaiveTime, Utc};
    use sqlx::types::{BigDecimal, Uuid};

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
        // NUMERIC/money → string to preserve exact precision (never f64).
        "NUMERIC" => row
            .try_get::<BigDecimal, _>(i)
            .map(|v| Json::String(v.to_string()))
            .unwrap_or(Json::Null),
        // Temporals → ISO-8601 strings.
        "TIMESTAMPTZ" => row
            .try_get::<DateTime<Utc>, _>(i)
            .map(|v| Json::String(v.to_rfc3339()))
            .unwrap_or(Json::Null),
        "TIMESTAMP" => row
            .try_get::<NaiveDateTime, _>(i)
            .map(|v| Json::String(v.format("%Y-%m-%dT%H:%M:%S%.f").to_string()))
            .unwrap_or(Json::Null),
        "DATE" => row
            .try_get::<NaiveDate, _>(i)
            .map(|v| Json::String(v.to_string()))
            .unwrap_or(Json::Null),
        "TIME" => row
            .try_get::<NaiveTime, _>(i)
            .map(|v| Json::String(v.to_string()))
            .unwrap_or(Json::Null),
        // UUID → canonical hyphenated string.
        "UUID" => row
            .try_get::<Uuid, _>(i)
            .map(|v| Json::String(v.to_string()))
            .unwrap_or(Json::Null),
        // JSONB/JSON → the parsed JSON value, verbatim.
        "JSONB" | "JSON" => row.try_get::<Json, _>(i).unwrap_or(Json::Null),
        _ => row.try_get::<String, _>(i).map(Json::String).unwrap_or(Json::Null),
    }
}

// ── shim de funciones-puente: ERPlora SQL → expresión nativa Postgres (ADR-0007 §4a) ─────────

/// **Set fijo y cerrado** de funciones-puente `erp_*` que el shim sabe reescribir
/// (ADR-0007 decisión 4a; ejemplos enumerados en `runtime-dispatcher.md §4bis`). Es cerrado a
/// propósito: usar una `erp_*` fuera de este set debe **fallar en `validate`** (build) del
/// `module-toolkit`, nunca colarse a runtime.
///
/// **REGLA VINCULANTE: este array DEBE coincidir EXACTAMENTE con `BRIDGE_FUNCTIONS` del
/// validador del toolkit** (`module-toolkit/src/validate-sql.mjs`). Si añades/quitas una
/// función-puente, cámbiala en LOS DOS sitios a la vez o el validador y el runtime se
/// desincronizan (el validador aceptaría algo que el runtime no sabe reescribir, o al revés).
///
/// Conjunto (ADR-0007 §4a; cubre las divergencias reales de los módulos POS):
/// - String/número:  `erp_now`, `erp_pad`, `erp_lpad`.
/// - Fecha/hora (las fechas se guardan como TEXT ISO-8601, ADR-0007 §1):
///   `erp_dt` (normaliza un texto ISO a datetime comparable), `erp_date` (parte fecha),
///   `erp_dateadd` (suma intervalo), `erp_month_start` (trunca a inicio de mes),
///   `erp_dow_mon0` (día de la semana 0=lunes…6=domingo), `erp_extract` (extrae hora/minuto),
///   `erp_datediff_days` (diferencia fraccionaria en días), `erp_timefmt` (formatea HH:MM).
pub const BRIDGE_FUNCTIONS: &[&str] = &[
    "erp_now",
    "erp_lpad",
    "erp_pad",
    "erp_dt",
    "erp_date",
    "erp_dateadd",
    "erp_month_start",
    "erp_dow_mon0",
    "erp_extract",
    "erp_datediff_days",
    "erp_timefmt",
];

/// Reescribe las **funciones-puente** del subconjunto portable a la expresión nativa de Postgres.
/// Sustitución textual anclada con escaneo de paréntesis balanceados (NO es un parser AST),
/// aplicada al traducir el SQL del módulo. UTF-8-safe. Recursiva: un argumento puede contener a
/// su vez otra función-puente.
///
/// Funciones cubiertas (ver [`BRIDGE_FUNCTIONS`]):
/// - `erp_now()` → `now()`. Timestamp del servidor (ADR-0007: fechas `TEXT` ISO-8601).
/// - `erp_lpad(valor, ancho, relleno)` → rellena por la izquierda hasta `ancho`.
/// - `erp_pad(valor, ancho)` = atajo de `erp_lpad(valor, ancho, '0')` para números de documento
///   (factura `FAC-00042`, ticket `TCK-0042`).
///
///   🔴 En ambas, **`ancho` es un MÍNIMO, nunca un techo**: un valor más largo que `ancho` se
///   conserva ENTERO. Ver [`pad_to_min_width`] — el `lpad` pelado de Postgres truncaba y hacía
///   colisionar el documento 10.000 con el 1.000 (hub#1378).
fn shim_functions(sql: &str) -> String {
    // Atajo: si ningún nombre del set aparece, no hay nada que reescribir.
    let lower = sql.to_ascii_lowercase();
    if !BRIDGE_FUNCTIONS.iter().any(|f| lower.contains(f)) {
        return sql.to_string();
    }
    let bytes = sql.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(sql.len() + 16);
    let mut i = 0;
    let mut in_string = false;
    while i < bytes.len() {
        let c = bytes[i];
        if in_string {
            out.push(c);
            if c == b'\'' {
                in_string = false;
            }
            i += 1;
            continue;
        }
        if c == b'\'' {
            in_string = true;
            out.push(c);
            i += 1;
            continue;
        }
        // Comentarios `-- …` (línea) y `/* … */` (bloque), fuera de string: se emiten VERBATIM y
        // NO tocan el estado de cadena — igual que hace `translate` con sus `:name` (hub#1026).
        // Sin esto, un apóstrofo en prosa (`-- the slot's capacity`) abría un literal fantasma y
        // dejaba TODAS las funciones-puente posteriores sin reescribir → Postgres `function
        // erp_datediff_days(text, text) does not exist`. Se copia por slice para preservar el
        // UTF-8 del comentario.
        if c == b'-' && bytes.get(i + 1) == Some(&b'-') {
            let start = i;
            while i < bytes.len() && bytes[i] != b'\n' {
                i += 1;
            }
            out.extend_from_slice(&bytes[start..i]);
            continue;
        }
        if c == b'/' && bytes.get(i + 1) == Some(&b'*') {
            let start = i;
            i += 2;
            while i < bytes.len() && !(bytes[i] == b'*' && bytes.get(i + 1) == Some(&b'/')) {
                i += 1;
            }
            i = (i + 2).min(bytes.len()); // consume el `*/` de cierre
            out.extend_from_slice(&bytes[start..i]);
            continue;
        }
        // Sólo arranca un nombre del set si el carácter previo NO es parte de un identificador
        // (descarta `xerp_pad`).
        let prev_is_ident = i > 0 && (bytes[i - 1].is_ascii_alphanumeric() || bytes[i - 1] == b'_');
        if !prev_is_ident {
            if let Some((name, after_name)) = match_bridge_fn(bytes, i) {
                if let Some((open, args, after)) = next_call(bytes, after_name) {
                    let _ = open;
                    if let Some(repl) = render_bridge_fn(name, sql, &args) {
                        out.extend_from_slice(repl.as_bytes());
                        i = after;
                        continue;
                    }
                }
            }
        }
        out.push(c);
        i += 1;
    }
    String::from_utf8(out).unwrap_or_else(|_| sql.to_string())
}

/// Si en `i` empieza (case-insensitive) una de las [`BRIDGE_FUNCTIONS`], devuelve su nombre
/// canónico y el índice **tras** el nombre. El próximo carácter (tras espacios) debe ser `(` para
/// que sea una llamada; eso lo comprueba [`next_call`]. Elige la coincidencia más larga
/// (`erp_pad` vs un hipotético `erp_padx`) requiriendo que el carácter siguiente al nombre no sea
/// de identificador.
fn match_bridge_fn(bytes: &[u8], i: usize) -> Option<(&'static str, usize)> {
    for &name in BRIDGE_FUNCTIONS {
        let n = name.len();
        if bytes[i..].len() >= n && bytes[i..i + n].eq_ignore_ascii_case(name.as_bytes()) {
            let next = bytes.get(i + n).copied();
            let next_is_ident =
                next.map(|b| b.is_ascii_alphanumeric() || b == b'_').unwrap_or(false);
            if !next_is_ident {
                return Some((name, i + n));
            }
        }
    }
    None
}

/// Dado el índice tras el nombre de la función, salta espacios y, si hay un `(`, escanea los
/// argumentos balanceados. Devuelve `(idx_open, spans_args, idx_tras_cierre)`.
fn next_call(bytes: &[u8], after_name: usize) -> Option<(usize, Vec<(usize, usize)>, usize)> {
    let mut p = after_name;
    while p < bytes.len() && (bytes[p] as char).is_whitespace() {
        p += 1;
    }
    if p < bytes.len() && bytes[p] == b'(' {
        let (args, after) = scan_call_args(bytes, p)?;
        return Some((p, args, after));
    }
    None
}

/// Expresión Postgres que rellena `value` por la izquierda hasta `width` **sin truncar nunca**
/// (hub#1378).
///
/// El `lpad(texto, ancho, relleno)` de Postgres impone un ancho **EXACTO**: recorta lo que sobra,
/// así que `lpad('10000', 4, '0')` = `'1000'` y el número de documento 10.000 colisionaba con el
/// 1.000 en el índice UNIQUE del ticket (ERPlora/sales#241; en `invoice`, 1.000.000 contra
/// 100.000). El contrato de las funciones-puente dice ancho **MÍNIMO**, así que se le pide a
/// `lpad` el mayor entre el ancho pedido y la longitud real del valor: lo que cabe se rellena
/// igual que antes y lo que no cabe se conserva entero.
///
/// `length()` cuenta **caracteres**, no bytes, así que un valor acentuado no pierde posiciones de
/// relleno.
///
/// ⚠️ La expresión del valor aparece **dos veces**, de modo que debe ser no-volátil. Las llamadas
/// reales de los módulos son columnas o subconsultas de solo lectura, estables dentro del snapshot
/// de la sentencia, y el validador del toolkit reescribe la misma expresión.
fn pad_to_min_width(value: &str, width: &str, fill: &str) -> String {
    format!("lpad(({value})::text, greatest({width}, length(({value})::text)), {fill})")
}

/// Renderiza una función-puente concreta a su expresión nativa Postgres. `None` = aridad
/// incorrecta (se deja el texto intacto; el validador del toolkit debería haberlo atrapado en build).
fn render_bridge_fn(name: &str, sql: &str, args: &[(usize, usize)]) -> Option<String> {
    // Cada argumento puede a su vez contener funciones-puente → recursión.
    let arg = |k: usize| shim_functions(sql[args[k].0..args[k].1].trim());
    match name {
        "erp_now" => {
            // `erp_now()` no toma argumentos (un único arg vacío es válido: `()`).
            let empty = args.len() == 1 && sql[args[0].0..args[0].1].trim().is_empty();
            if !(args.is_empty() || empty) {
                return None;
            }
            Some("now()".to_string())
        }
        "erp_pad" => {
            if args.len() != 2 {
                return None;
            }
            let value = arg(0);
            let width = arg(1);
            Some(pad_to_min_width(&value, &width, "'0'"))
        }
        "erp_lpad" => {
            if args.len() != 3 {
                return None;
            }
            let value = arg(0);
            let width = arg(1);
            let fill = arg(2); // literal `'x'` o expresión
            Some(pad_to_min_width(&value, &width, &fill))
        }

        // ── funciones-puente de fecha/hora ───────────────────────────────────────────────────
        // Contrato (ADR-0007 §1): las fechas se guardan como **TEXT ISO-8601**. En Postgres hay que
        // castear (`::timestamptz` / `::date`). Comparar dos `erp_dt(...)` entre sí es portable
        // porque ambos lados quedan en el tipo nativo del motor.
        "erp_dt" => {
            // erp_dt(x): normaliza un texto ISO a datetime comparable.
            if args.len() != 1 {
                return None;
            }
            let x = arg(0);
            Some(format!("(({x})::timestamptz)"))
        }
        "erp_date" => {
            // erp_date(x): parte fecha (sin hora) de un texto ISO.
            if args.len() != 1 {
                return None;
            }
            let x = arg(0);
            Some(format!("(({x})::date)"))
        }
        "erp_dateadd" => {
            // erp_dateadd(x, n, unit): suma `n` veces `unit` a `x`. `unit` es un literal
            // ('minutes'|'hours'|'days'|'months'|…) compatible con los campos de `interval` de
            // Postgres. `n` puede ser una expresión (columna).
            if args.len() != 3 {
                return None;
            }
            let x = arg(0);
            let n = arg(1);
            let unit = arg(2); // literal entre comillas: 'minutes'
            Some(format!("(({x})::timestamptz + (({n}) || ' ' || {unit})::interval)"))
        }
        "erp_month_start" => {
            // erp_month_start(x): trunca al inicio del mes de `x`.
            if args.len() != 1 {
                return None;
            }
            let x = arg(0);
            Some(format!("date_trunc('month', ({x})::timestamptz)"))
        }
        "erp_dow_mon0" => {
            // erp_dow_mon0(x): día de la semana con 0=lunes … 6=domingo (convención de los
            // módulos). En Postgres ISODOW da 1=lunes … 7=domingo → (ISODOW - 1).
            if args.len() != 1 {
                return None;
            }
            let x = arg(0);
            Some(format!("((EXTRACT(ISODOW FROM ({x})::timestamptz)::int) - 1)"))
        }
        "erp_extract" => {
            // erp_extract(part, x): extrae un campo de `x` como INTEGER. `part` es un literal:
            // 'hour' | 'minute' | 'second' | 'epoch'.
            if args.len() != 2 {
                return None;
            }
            let part_raw = sql[args[0].0..args[0].1].trim();
            let x = arg(1);
            // El literal debe ir entre comillas simples; tomamos su contenido en minúsculas.
            let part = part_raw.trim_matches('\'').to_ascii_lowercase();
            let pg_field = match part.as_str() {
                "hour" => "hour",
                "minute" => "minute",
                "second" => "second",
                "epoch" => "epoch",
                _ => return None, // parte no soportada → el validador debió atraparlo
            };
            Some(format!("(EXTRACT({pg_field} FROM ({x})::timestamptz)::bigint)"))
        }
        "erp_datediff_days" => {
            // erp_datediff_days(a, b): diferencia (a - b) en días, fraccionaria (REAL).
            if args.len() != 2 {
                return None;
            }
            let a = arg(0);
            let b = arg(1);
            Some(format!(
                "(EXTRACT(EPOCH FROM (({a})::timestamptz - ({b})::timestamptz)) / 86400.0)"
            ))
        }
        "erp_timefmt" => {
            // erp_timefmt(h, m): formatea "HH:MM" a partir de dos enteros (horas, minutos).
            if args.len() != 2 {
                return None;
            }
            let h = arg(0);
            let m = arg(1);
            // Mismo contrato de ancho mínimo (hub#1378): una duración de 100 h se renderizaba
            // "10:00" porque `lpad` recortaba las horas.
            let hh = pad_to_min_width(&h, "2", "'0'");
            let mm = pad_to_min_width(&m, "2", "'0'");
            Some(format!("({hh} || ':' || {mm})"))
        }
        _ => None,
    }
}

// ── shim de normalización de tipos en DDL (ERPlora SQL → tipo nativo Postgres) (ADR-0007 §4b) ─

/// Tabla de equivalencias del **subconjunto portable de tipos** a su tipo nativo Postgres
/// (ADR-0007 / module-system §4bis: PK `TEXT`, fechas `TEXT` ISO-8601, booleanos y dinero
/// `INTEGER`; `REAL`/`BLOB` para flotantes/binarios no monetarios).
///
/// Devuelve `None` para un tipo que no esté en el subconjunto (se deja intacto: el validador del
/// toolkit debe rechazar tipos no portables en build).
fn normalize_ddl_type(portable: &str) -> Option<&'static str> {
    match portable.to_ascii_uppercase().as_str() {
        "TEXT" => Some("TEXT"),
        "INTEGER" => Some("BIGINT"), // dinero/booleanos/contadores en céntimos → 64-bit seguro
        "REAL" => Some("DOUBLE PRECISION"),
        "BLOB" => Some("BYTEA"),
        _ => None,
    }
}

/// Normaliza los **tipos de columna** de las sentencias `CREATE TABLE` del SQL al tipo nativo de
/// Postgres (ADR-0007 §4b). Sustitución textual anclada (NO parser AST):
///
/// Para cada **token de tipo del subconjunto portable** (`TEXT`/`INTEGER`/`REAL`/`BLOB`, como
/// palabra completa, fuera de literales) lo reemplaza por su equivalente nativo según
/// [`normalize_ddl_type`]. Cualquier otra cosa se deja intacta (nombres de columna, `PRIMARY KEY`,
/// `NOT NULL`, `DEFAULT …`, etc.). Se aplica en `execute_batch` (path de migraciones), no en cada query.
pub fn shim_ddl_types(sql: &str) -> String {
    // Reconstruye sobre BYTES (no `byte as char`): un `push(c as char)` reinterpretaría cada byte
    // de una secuencia UTF-8 como Latin-1 → mojibake (`Café`→`CafÃ©`) en literales/comentarios del
    // DDL+DML de seed/import. Se emiten bytes crudos y se decodifica UTF-8 al final.
    let bytes = sql.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(sql.len() + 16);
    let mut i = 0;
    let mut in_string = false;
    while i < bytes.len() {
        let c = bytes[i];
        if in_string {
            out.push(c);
            if c == b'\'' {
                in_string = false;
            }
            i += 1;
            continue;
        }
        if c == b'\'' {
            in_string = true;
            out.push(b'\'');
            i += 1;
            continue;
        }
        // Comentarios verbatim, sin tocar el estado de cadena — misma regla que `translate` y que
        // `shim_functions` (hub#1026). Aquí el precio de no hacerlo es más caro: un apóstrofo en
        // prosa dejaba los tipos portables posteriores SIN normalizar, y `BLOB` no existe en
        // Postgres (la migración revienta) mientras `INTEGER` no es `BIGINT` (queda de 4 bytes).
        if c == b'-' && bytes.get(i + 1) == Some(&b'-') {
            let start = i;
            while i < bytes.len() && bytes[i] != b'\n' {
                i += 1;
            }
            out.extend_from_slice(&bytes[start..i]);
            continue;
        }
        if c == b'/' && bytes.get(i + 1) == Some(&b'*') {
            let start = i;
            i += 2;
            while i < bytes.len() && !(bytes[i] == b'*' && bytes.get(i + 1) == Some(&b'/')) {
                i += 1;
            }
            i = (i + 2).min(bytes.len());
            out.extend_from_slice(&bytes[start..i]);
            continue;
        }
        // Sólo reescribe tipos como palabra completa.
        let prev_is_ident = i > 0 && (bytes[i - 1].is_ascii_alphanumeric() || bytes[i - 1] == b'_');
        if !prev_is_ident {
            if let Some((tok, end)) = read_ident(bytes, i) {
                let next_is_ident =
                    bytes.get(end).map(|b| b.is_ascii_alphanumeric() || *b == b'_').unwrap_or(false);
                if !next_is_ident {
                    if let Some(native) = normalize_ddl_type(tok) {
                        out.extend_from_slice(native.as_bytes());
                        i = end;
                        continue;
                    }
                }
            }
        }
        out.push(c);
        i += 1;
    }
    String::from_utf8(out).unwrap_or_else(|_| sql.to_string())
}

/// Lee un identificador ASCII (`[A-Za-z_][A-Za-z0-9_]*`) desde `i`; devuelve `(slice, fin)`.
fn read_ident(bytes: &[u8], i: usize) -> Option<(&str, usize)> {
    if !(bytes[i].is_ascii_alphabetic() || bytes[i] == b'_') {
        return None;
    }
    let mut j = i + 1;
    while j < bytes.len() && (bytes[j].is_ascii_alphanumeric() || bytes[j] == b'_') {
        j += 1;
    }
    std::str::from_utf8(&bytes[i..j]).ok().map(|s| (s, j))
}

/// Dado el índice del `(` de apertura de una llamada, devuelve los spans `(inicio, fin)` de los
/// argumentos de **primer nivel** (separados por comas no anidadas, ignorando comas dentro de
/// `'...'`) y el índice **después** del `)` de cierre. `None` si los paréntesis no cierran.
fn scan_call_args(bytes: &[u8], open: usize) -> Option<(Vec<(usize, usize)>, usize)> {
    let mut depth = 0usize;
    let mut in_string = false;
    let mut args: Vec<(usize, usize)> = Vec::new();
    let mut arg_start = open + 1;
    let mut i = open;
    while i < bytes.len() {
        let c = bytes[i];
        if in_string {
            if c == b'\'' {
                in_string = false;
            }
            i += 1;
            continue;
        }
        match c {
            b'\'' => in_string = true,
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    args.push((arg_start, i));
                    return Some((args, i + 1));
                }
            }
            b',' if depth == 1 => {
                args.push((arg_start, i));
                arg_start = i + 1;
            }
            _ => {}
        }
        i += 1;
    }
    None
}

// ── placeholder translator `:name` → `$n` (Postgres) ──────────────────────────────────────

/// Translates named parameters `:name` (what modules write) into Postgres positional
/// placeholders `$1,$2…`.
///
/// Rules:
/// - `:ident` (alphanumeric/`_`) → `$n`, with `n` in order of first appearance; a repeated name
///   **reuses** its index (so `names` lists each name only once).
/// - `::` is the Postgres cast, never a parameter: emitted verbatim.
/// - A `:` inside a `'...'` literal is left intact.
///
/// Returns the rewritten SQL and the ordered (deduplicated) list of names, so the caller binds
/// in that order.
pub(crate) fn translate(sql: &str) -> (String, Vec<String>) {
    // Funciones-puente ERPlora SQL → expresión nativa Postgres (ADR-0007 §4a), antes de bajar los
    // placeholders. Trabaja sobre el texto ya con `:name` (se traducen en el segundo paso).
    let shimmed = shim_functions(sql);
    let sql = shimmed.as_str();

    // Reconstruye sobre BYTES (no `byte as char`): emitir un byte de una secuencia UTF-8 como
    // `char` lo reinterpretaría como Latin-1 → mojibake en literales `'...'`. Los `c` de abajo son
    // solo para COMPARAR (siempre ASCII: `'`, `-`, `/`, `*`, `:`); lo que se emite es el byte crudo.
    let mut out: Vec<u8> = Vec::with_capacity(sql.len());
    let bytes = sql.as_bytes();
    let mut names: Vec<String> = Vec::new();
    let mut i = 0;
    let mut in_string = false;

    while i < bytes.len() {
        let c = bytes[i] as char;

        if in_string {
            out.push(bytes[i]);
            if c == '\'' {
                in_string = false;
            }
            i += 1;
            continue;
        }

        if c == '\'' {
            in_string = true;
            out.push(bytes[i]);
            i += 1;
            continue;
        }

        // Comentarios `-- …` (línea) y `/* … */` (bloque), fuera de string: se emiten VERBATIM y
        // sus `:name` NO se tratan como parámetros. Antes se traducían a `$N`, creando placeholders
        // FANTASMA — bindeados pero ausentes del SQL que parsea el motor (que ignora los comentarios)
        // → Postgres aborta con `could not determine data type of parameter $N`, rompiendo la lista
        // de TODO módulo cuyo SELECT documenta binds en un comentario (verifactu, taxes, staff, …).
        // Se copia por slice (no byte-a-byte) para preservar el UTF-8 del comentario.
        if c == '-' && bytes.get(i + 1) == Some(&b'-') {
            let start = i;
            while i < bytes.len() && bytes[i] != b'\n' {
                i += 1;
            }
            out.extend_from_slice(sql[start..i].as_bytes());
            continue;
        }
        if c == '/' && bytes.get(i + 1) == Some(&b'*') {
            let start = i;
            i += 2;
            while i < bytes.len() && !(bytes[i] == b'*' && bytes.get(i + 1) == Some(&b'/')) {
                i += 1;
            }
            i = (i + 2).min(bytes.len()); // consume el `*/` de cierre
            out.extend_from_slice(sql[start..i].as_bytes());
            continue;
        }

        if c == ':' {
            // `::` is the Postgres cast operator, not a parameter.
            if i + 1 < bytes.len() && bytes[i + 1] == b':' {
                out.extend_from_slice(b"::");
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
                out.push(b'$');
                out.extend_from_slice(idx.to_string().as_bytes());
                i = j;
                continue;
            }
        }

        out.push(bytes[i]);
        i += 1;
    }

    (String::from_utf8(out).unwrap_or_else(|_| sql.to_string()), names)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testutil::{TestDb, demote_pooled_connections_to_replica, fresh_db};
    use serde_json::json;

    fn params(v: Json) -> Params {
        v.as_object().cloned().unwrap_or_default()
    }

    // ── DB roundtrips contra un Postgres real (test-util: esquema efímero por test) ───────────

    #[tokio::test]
    async fn create_insert_query_roundtrip() {
        let db = fresh_db().await;
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
        let db = fresh_db().await;
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

    /// DDL portable + función-puente `erp_pad` de extremo a extremo en Postgres real.
    #[tokio::test]
    async fn portable_ddl_and_bridge_fn_roundtrip() {
        let db = fresh_db().await;
        // DDL portable: INTEGER (dinero en céntimos, booleano 0/1) → BIGINT en Postgres.
        db.execute_batch(
            "CREATE TABLE invoices (id TEXT PRIMARY KEY, hub_id TEXT, seq INTEGER, \
             amount_cents INTEGER, paid INTEGER);",
        )
        .await
        .unwrap();
        db.execute(
            "INSERT INTO invoices (id, hub_id, seq, amount_cents, paid) \
             VALUES (:id, :hub_id, :seq, :amount, :paid)",
            &params(json!({"id":"i1","hub_id":"h1","seq":42,"amount":12345,"paid":1})),
        )
        .await
        .unwrap();
        // Función-puente erp_pad: número de factura con ceros a la izquierda.
        let q = db
            .query(
                "SELECT 'FAC-' || erp_pad(seq, 5) AS num, amount_cents, paid \
                 FROM invoices WHERE hub_id = :hub_id",
                &params(json!({"hub_id":"h1"})),
            )
            .await
            .unwrap();
        assert_eq!(q.rows.len(), 1);
        assert_eq!(q.rows[0]["num"], json!("FAC-00042"));
        assert_eq!(q.rows[0]["amount_cents"], json!(12345));
        assert_eq!(q.rows[0]["paid"], json!(1));
    }

    /// Regresión (hub#1378): `erp_pad` es padding **mínimo**, nunca un techo. En Postgres `lpad`
    /// TRUNCA cuando el valor supera el ancho, así que el contador diario 10.000 se renderizaba
    /// `1000` y COLISIONABA con la venta 1.000 en el índice UNIQUE del número de documento
    /// (ERPlora/sales#241; en `invoice` el fallback de 6 dígitos choca en 1.000.000 con 100.000).
    /// Reproduce la forma real de `sales._insert_sale`: el número se arma leyendo el contador
    /// recién incrementado en la MISMA sentencia, con una subconsulta escalar.
    #[tokio::test]
    async fn erp_pad_never_truncates_so_document_numbers_stay_unique() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE counter (hub_id TEXT, day TEXT, last_number INTEGER, \
               PRIMARY KEY (hub_id, day)); \
             CREATE TABLE sale (id TEXT PRIMARY KEY, hub_id TEXT, sale_number TEXT); \
             CREATE UNIQUE INDEX uq_sale_number ON sale (hub_id, sale_number);",
        )
        .await
        .unwrap();
        db.execute(
            "INSERT INTO counter (hub_id, day, last_number) VALUES (:hub_id, :day, 1000)",
            &params(json!({ "hub_id": "h1", "day": "20260901" })),
        )
        .await
        .unwrap();

        let insert_sale = "INSERT INTO sale (id, hub_id, sale_number) VALUES (:id, :hub_id, \
             :day || '-' || erp_pad((SELECT last_number FROM counter \
                                     WHERE hub_id = :hub_id AND day = :day), 4))";
        db.execute(insert_sale, &params(json!({ "id": "s1", "hub_id": "h1", "day": "20260901" })))
            .await
            .unwrap();

        // La venta 10.000 del día: cuatro dígitos ya no le bastan y el ancho es un MÍNIMO.
        db.execute(
            "UPDATE counter SET last_number = 10000 WHERE hub_id = :hub_id AND day = :day",
            &params(json!({ "hub_id": "h1", "day": "20260901" })),
        )
        .await
        .unwrap();
        db.execute(insert_sale, &params(json!({ "id": "s2", "hub_id": "h1", "day": "20260901" })))
            .await
            .expect("la venta 10.000 no puede colisionar con la 1.000 en uq_sale_number");

        let q = db
            .query("SELECT sale_number FROM sale ORDER BY id", &Params::new())
            .await
            .unwrap();
        assert_eq!(q.rows.len(), 2);
        assert_eq!(q.rows[0]["sale_number"], json!("20260901-1000"));
        assert_eq!(
            q.rows[1]["sale_number"],
            json!("20260901-10000"),
            "erp_pad rellena hasta el ancho, no recorta a el"
        );
    }

    /// Regresión (hub#1378): el contrato de anchura es un MÍNIMO en ambas funciones-puente, y el
    /// relleno de `erp_lpad` cuenta CARACTERES (no bytes) para que el acento no coma una posición.
    #[tokio::test]
    async fn erp_pad_and_erp_lpad_pad_to_a_minimum_width() {
        let db = fresh_db().await;
        let q = db
            .query(
                "SELECT erp_pad(:small, 5) AS small, erp_pad(:big, 4) AS big, \
                        erp_lpad(:word, 6, '.') AS narrow, erp_lpad(:phrase, 4, '.') AS wide",
                &params(json!({
                    "small": 42, "big": 10000, "word": "café", "phrase": "cafetería"
                })),
            )
            .await
            .unwrap();
        assert_eq!(q.rows[0]["small"], json!("00042"), "lo que cabe se rellena igual que antes");
        assert_eq!(q.rows[0]["big"], json!("10000"), "lo que no cabe se conserva entero");
        assert_eq!(q.rows[0]["narrow"], json!("..café"), "el relleno cuenta caracteres");
        assert_eq!(q.rows[0]["wide"], json!("cafetería"), "9 caracteres no se recortan a 4");
    }

    /// Regresión (ADR-0154): `shim_ddl_types`/`translate` reconstruían el SQL byte-a-byte con
    /// `push(byte as char)` → mojibake para no-ASCII (`Café`→`CafÃ©`) en TODO `execute_batch`/
    /// `execute` (seed/import). Antes quedaba oculto porque en SQLite `shim_ddl_types` era la
    /// identidad; en Postgres siempre corre. Round-trip por AMBOS caminos (batch y execute).
    #[tokio::test]
    async fn utf8_literal_roundtrip_batch_and_execute() {
        let db = fresh_db().await;
        // execute_batch → shim_ddl_types: DDL + INSERT con literal no-ASCII.
        db.execute_batch(
            "CREATE TABLE t (id TEXT PRIMARY KEY, name TEXT); \
             INSERT INTO t (id, name) VALUES ('a', 'Café')",
        )
        .await
        .unwrap();
        // execute → translate: literal no-ASCII dentro de la sentencia (sin params).
        db.execute("INSERT INTO t (id, name) VALUES ('b', 'Niño €')", &Params::new())
            .await
            .unwrap();
        let q = db.query("SELECT id, name FROM t ORDER BY id", &Params::new()).await.unwrap();
        assert_eq!(q.rows[0]["name"], json!("Café"), "shim_ddl_types no debe romper UTF-8");
        assert_eq!(q.rows[1]["name"], json!("Niño €"), "translate no debe romper UTF-8");
    }

    #[tokio::test]
    async fn pg_roundtrip() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE erplora_pg_test (id BIGINT, name TEXT, ok BOOLEAN, price FLOAT8)",
        )
        .await
        .unwrap();
        // `ok` se puebla con un literal SQL `true` (no por param): desde hub#208/ADR-0154 los bool
        // se bindean como INTEGER 0/1, así que un bool-param a columna BOOLEAN ya no aplica. La
        // columna BOOLEAN se mantiene aquí para seguir cubriendo el **decode** de lectura (pg_cell).
        let res = db
            .execute(
                "INSERT INTO erplora_pg_test (id, name, ok, price) \
                 VALUES (:id, :name, true, :price)",
                &params(json!({"id": 1, "name": "alice", "price": 4.5})),
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

    /// §8/§9 — decode de los tipos fiscales/dinero de Postgres. Inserta literales (no el path de
    /// params) para aislar los brazos de decode de `pg_cell`.
    #[tokio::test]
    async fn pg_fiscal_types_roundtrip() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE erplora_pg_fiscal ( \
                 amount NUMERIC(10,2), ts TIMESTAMPTZ, d DATE, uid UUID, meta JSONB \
             ); \
             INSERT INTO erplora_pg_fiscal (amount, ts, d, uid, meta) VALUES ( \
                 12345.67, \
                 '2026-06-13T10:30:00Z', \
                 '2026-06-13', \
                 '00000000-0000-0000-0000-000000000001', \
                 '{\"a\":1}' \
             )",
        )
        .await
        .unwrap();
        let q = db
            .query(
                "SELECT amount, ts, d, uid, meta FROM erplora_pg_fiscal",
                &params(json!({})),
            )
            .await
            .unwrap();
        assert_eq!(q.rows.len(), 1);
        let r = &q.rows[0];
        // NUMERIC decodes to a **string** (never f64), preserving exact precision. sqlx/bigdecimal
        // may render trailing zeros (`12345.6700`), which is lossless — assert the value, not the
        // exact rendering, and that it is a string (not a JSON number).
        let amount = r["amount"].as_str().expect("NUMERIC debe decodificarse como string, no f64");
        assert_eq!(amount.parse::<f64>().unwrap(), 12345.67);
        // TIMESTAMPTZ → RFC-3339 (UTC).
        assert_eq!(r["ts"], json!("2026-06-13T10:30:00+00:00"));
        assert_eq!(r["d"], json!("2026-06-13"));
        assert_eq!(r["uid"], json!("00000000-0000-0000-0000-000000000001"));
        // JSONB → parsed value, verbatim.
        assert_eq!(r["meta"], json!({"a": 1}));
    }

    // ── the column, not the value, decides how a `range` bound compares (hub#1542) ────────────

    /// `column_kinds` reports what the SERVER resolved for every column a SELECT returns, which is
    /// the only thing that can tell a numeric `range` filter from a text one.
    ///
    /// It has to answer for a plain column, for a computed one (an aggregate — `inventory
    /// .categories.list.product_count` is a `COUNT(*)`), and it has to keep an all-digit TEXT
    /// column TEXT: that is the regression the "parse the bound as a number" shortcut would cause
    /// on `customers.list.f_tax_id`.
    #[tokio::test]
    async fn column_kinds_reports_what_the_server_resolved() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE erplora_kinds (n BIGINT NOT NULL, r REAL NOT NULL, \
             m NUMERIC NOT NULL, t TEXT NOT NULL, d DATE NOT NULL);",
        )
        .await
        .unwrap();

        let kinds = db
            .column_kinds(
                "SELECT n, r, m, t, d, COUNT(*) OVER() AS c FROM erplora_kinds WHERE t <> :skip",
            )
            .await
            .unwrap();

        assert_eq!(kinds.get("n"), Some(&ColumnKind::Numeric));
        assert_eq!(kinds.get("r"), Some(&ColumnKind::Numeric));
        assert_eq!(kinds.get("m"), Some(&ColumnKind::Numeric));
        assert_eq!(kinds.get("c"), Some(&ColumnKind::Numeric), "a computed count is numeric too");
        assert_eq!(
            kinds.get("t"),
            Some(&ColumnKind::Other),
            "a TEXT column stays TEXT however numeric its values look"
        );
        assert_eq!(
            kinds.get("d"),
            Some(&ColumnKind::Other),
            "a native DATE is not a number: its bounds are written as text"
        );
    }

    /// The SQL shape the engine emits for a numeric `range` bound: the bound stays a TEXT bind and
    /// the CAST is written into the statement, so a `NUMERIC` money column keeps its exact
    /// precision instead of going through an `f64`.
    #[tokio::test]
    async fn a_text_bound_cast_to_numeric_compares_by_number() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE erplora_cast (n BIGINT NOT NULL, m NUMERIC NOT NULL); \
             INSERT INTO erplora_cast (n, m) VALUES (10, 12345.67), (100, 0.01);",
        )
        .await
        .unwrap();

        // `'100' <= '20'` is TRUE as text and FALSE as a number — the row that catches a fix that
        // compared both sides as strings.
        let q = db
            .query(
                "SELECT n FROM erplora_cast WHERE n >= CAST(:lo AS NUMERIC) \
                 AND n <= CAST(:hi AS NUMERIC) ORDER BY n",
                &params(json!({"lo": "10", "hi": "20"})),
            )
            .await
            .unwrap();
        assert_eq!(q.rows.iter().map(|r| r["n"].clone()).collect::<Vec<_>>(), vec![json!(10)]);

        // Exact decimal, no float rounding: `12345.67` is not representable in binary.
        let q = db
            .query(
                "SELECT n FROM erplora_cast WHERE m >= CAST(:lo AS NUMERIC) ORDER BY n",
                &params(json!({"lo": "12345.67"})),
            )
            .await
            .unwrap();
        assert_eq!(q.rows.len(), 1, "the exact decimal bound matches its own row: {:?}", q.rows);
    }

    /// hub#1542 × hub#1348 — DESCRIBING a text must never pin the parameter types of RUNNING
    /// that same text. sqlx's statement cache is keyed on the SQL text alone and `get_or_prepare`
    /// reads it BEFORE it honours `.persistent(false)`, so a `column_kinds` that left the
    /// server-inferred types in that cache would hand them to the next `query()` of the same text
    /// on that connection. Reproduced in the review of hub#1567: after the describe, a `5.0`
    /// bound (FLOAT8) was decoded with the cached `INT8` and the row a fresh connection answers
    /// went missing — silently, the exact shape of corruption hub#1348 closed. One connection on
    /// purpose: a pool is what would otherwise hide it.
    #[tokio::test]
    async fn describing_a_text_never_pins_the_parameter_types_of_running_it() {
        let test_db = crate::testutil::TestDb::new().await;
        let db = test_db.adapter_with_max_connections(1).await;
        db.execute_batch(
            "CREATE TABLE erplora_pin (n INTEGER NOT NULL); INSERT INTO erplora_pin (n) VALUES (5);",
        )
        .await
        .unwrap();
        let sql = "SELECT n FROM erplora_pin WHERE n = :v";

        let kinds = db.column_kinds(sql).await.unwrap();
        assert_eq!(kinds.get("n"), Some(&ColumnKind::Numeric));

        // `5.0` binds as FLOAT8 and `n = 5.0` is TRUE for the row. Decoded with the parameter
        // type the describe left behind, the same eight bytes are another number: the row vanishes.
        let q = db
            .query(sql, &params(json!({"v": 5.0})))
            .await
            .expect("running the text just described must bind by its OWN parameter types");
        assert_eq!(
            q.rows.len(),
            1,
            "the row a fresh connection answers must not vanish after a describe: {:?}",
            q.rows
        );
    }

    /// hub#2359 — a describe answers the schema as it is NOW, not as it was the last time this
    /// connection described the same text. sqlx keeps every prepared statement in a per-connection
    /// cache keyed on the text, and `prepare_with` answers from it without asking the server: after
    /// a module migration added a column behind the same `SELECT *`, the connection that described
    /// the old shape kept answering it and the list failed (`integer >= text`) on the new column.
    /// One connection on purpose: a pool is what would otherwise hide it.
    #[tokio::test]
    async fn a_describe_after_a_migration_answers_the_new_shape() {
        let test_db = crate::testutil::TestDb::new().await;
        let db = test_db.adapter_with_max_connections(1).await;
        db.execute_batch("CREATE TABLE erplora_shape (id TEXT NOT NULL);")
            .await
            .unwrap();
        let sql = "SELECT * FROM erplora_shape WHERE id <> :skip";

        let before = db.column_kinds(sql).await.unwrap();
        assert_eq!(before.keys().collect::<Vec<_>>(), vec!["id"]);

        db.execute_batch("ALTER TABLE erplora_shape ADD COLUMN score INTEGER NOT NULL DEFAULT 0;")
            .await
            .unwrap();

        let after = db.column_kinds(sql).await.unwrap();
        assert_eq!(
            after.get("score"),
            Some(&ColumnKind::Numeric),
            "the column the migration added must be described: {after:?}"
        );
    }

    // ── JSON boolean → INTEGER 0/1 (hub#208 / ADR-0154) ───────────────────────────────────────

    /// hub#208 — el contrato de filas de la casa usa **INTEGER 0/1** para los flags (ninguna
    /// columna real de módulo es BOOLEAN). Un comando Tier-0 cuyo schema declara `boolean` y escribe
    /// una columna INTEGER debe funcionar: `Json::Bool` se coacciona a `i64` 0/1 en el bind.
    ///
    /// (a) INSERT con param bool `true`/`false` a columna INTEGER guarda 1/0.
    /// (b) round-trip: la query devuelve 1/0 **como número** (el decode de lectura no cambia: sigue
    ///     siendo la rama INT8 → JSON number, nunca un booleano).
    ///
    /// Antes del fix (bind nativo PG `bool`) esto fallaba con:
    /// `column "is_active" is of type bigint but expression is of type boolean`.
    #[tokio::test]
    async fn bool_param_binds_into_integer_flag_column() {
        let db = fresh_db().await;
        // INTEGER en el DDL portable → BIGINT en Postgres (shim_ddl_types): el tipo real de un flag.
        db.execute_batch(
            "CREATE TABLE flags (id TEXT PRIMARY KEY, is_active INTEGER, is_deleted INTEGER);",
        )
        .await
        .unwrap();
        // true → 1, false → 0, ambos por el path de params (Json::Bool).
        db.execute(
            "INSERT INTO flags (id, is_active, is_deleted) VALUES (:id, :active, :deleted)",
            &params(json!({"id": "a", "active": true, "deleted": false})),
        )
        .await
        .unwrap();
        let q = db
            .query(
                "SELECT is_active, is_deleted FROM flags WHERE id = :id",
                &params(json!({"id": "a"})),
            )
            .await
            .unwrap();
        assert_eq!(q.rows.len(), 1);
        assert_eq!(q.rows[0]["is_active"], json!(1), "true debe guardarse/leerse como 1");
        assert_eq!(q.rows[0]["is_deleted"], json!(0), "false debe guardarse/leerse como 0");
    }

    /// hub#208 (c) — un `WHERE columna_INTEGER = :flag` con un bool debe filtrar por 0/1: `:active`
    /// = `true` se coacciona a 1 y matchea solo las filas con `is_active = 1`.
    #[tokio::test]
    async fn bool_param_in_where_matches_integer_flag() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE flags (id TEXT PRIMARY KEY, is_active INTEGER);")
            .await
            .unwrap();
        db.execute("INSERT INTO flags (id, is_active) VALUES ('on', 1), ('off', 0)", &Params::new())
            .await
            .unwrap();
        let q = db
            .query(
                "SELECT id FROM flags WHERE is_active = :active",
                &params(json!({"active": true})),
            )
            .await
            .unwrap();
        assert_eq!(q.rows.len(), 1, "true debe matchear solo la fila con is_active = 1");
        assert_eq!(q.rows[0]["id"], json!("on"));
    }

    // ── translator `:name` → `$n` (no DB) ─────────────────────────────────────────────────

    #[test]
    fn pg_translate_basic() {
        let (sql, names) = translate("SELECT * FROM t WHERE a = :a AND b = :b");
        assert_eq!(sql, "SELECT * FROM t WHERE a = $1 AND b = $2");
        assert_eq!(names, vec!["a", "b"]);
    }

    #[test]
    fn pg_translate_ignores_params_inside_comments() {
        // Un `:name` dentro de un comentario NO es un parámetro. Regresión: se traducía a `$N`,
        // creando placeholders fantasma (bindeados pero ausentes del SQL parseado, que ignora los
        // comentarios) → Postgres `could not determine data type of parameter $N`, rompiendo la
        // lista de módulos (verifactu, taxes, staff…) cuyo SELECT documenta binds en comentarios.
        let (sql, names) = translate(
            "-- binds opcionales: :status y :record_type\nSELECT * FROM t WHERE hub_id = :hub_id /* :ghost */ AND is_deleted = 0",
        );
        assert_eq!(names, vec!["hub_id"], "solo el bind real, no los de los comentarios");
        assert!(
            sql.contains(":status") && sql.contains(":record_type") && sql.contains(":ghost"),
            "los comentarios se preservan verbatim: {sql}"
        );
        assert!(sql.contains("hub_id = $1"), "el bind real sí se traduce: {sql}");
    }

    #[test]
    fn pg_translate_repeated_reuses_index() {
        let (sql, names) = translate("SELECT :x, :x, :y");
        assert_eq!(sql, "SELECT $1, $1, $2");
        assert_eq!(names, vec!["x", "y"]);
    }

    #[test]
    fn pg_translate_keeps_cast_operator() {
        let (sql, names) = translate("SELECT id::int FROM t WHERE id = :id");
        assert_eq!(sql, "SELECT id::int FROM t WHERE id = $1");
        assert_eq!(names, vec!["id"]);
    }

    #[test]
    fn pg_translate_cast_right_after_param() {
        let (sql, names) = translate("SELECT :amount::numeric");
        assert_eq!(sql, "SELECT $1::numeric");
        assert_eq!(names, vec!["amount"]);
    }

    #[test]
    fn pg_translate_ignores_colon_in_string_literal() {
        let (sql, names) = translate("SELECT ':notparam' AS s, :real AS r");
        assert_eq!(sql, "SELECT ':notparam' AS s, $1 AS r");
        assert_eq!(names, vec!["real"]);
    }

    #[test]
    fn pg_translate_returns_name_order() {
        let (sql, names) = translate("SELECT :b, :a, :b::text, ':c', :a");
        assert_eq!(sql, "SELECT $1, $2, $1::text, ':c', $2");
        assert_eq!(names, vec!["b", "a"]);
    }

    // ── shim de funciones-puente (ADR-0007 §4a): erp_pad → lpad ─────────────────────────────

    #[test]
    fn shim_erp_pad() {
        let (sql, names) = translate("SELECT 'FAC-' || erp_pad(:n, 5)");
        assert_eq!(sql, "SELECT 'FAC-' || lpad(($1)::text, greatest(5, length(($1)::text)), '0')");
        assert_eq!(names, vec!["n"]);
    }

    #[test]
    fn shim_erp_pad_nested_subquery() {
        // El valor es una subconsulta con paréntesis anidados: el escáner balanceado la respeta.
        let (sql, names) = translate(
            "SELECT erp_pad((SELECT max(seq) + 1 FROM t WHERE hub_id = :h), 6)",
        );
        assert_eq!(
            sql,
            "SELECT lpad(((SELECT max(seq) + 1 FROM t WHERE hub_id = $1))::text, \
             greatest(6, length(((SELECT max(seq) + 1 FROM t WHERE hub_id = $1))::text)), '0')"
        );
        assert_eq!(names, vec!["h"]);
    }

    #[test]
    fn shim_ignores_erp_pad_inside_string_literal() {
        let (sql, _) = translate("SELECT 'erp_pad(x, 5) literal'");
        assert_eq!(sql, "SELECT 'erp_pad(x, 5) literal'");
    }

    #[test]
    fn shim_does_not_match_partial_identifier() {
        // `xerp_pad` no es la función-puente: se deja intacto.
        let (sql, _) = translate("SELECT xerp_pad");
        assert_eq!(sql, "SELECT xerp_pad");
    }

    #[test]
    fn shim_skips_line_comments_so_an_apostrophe_does_not_swallow_the_rest() {
        // hub#1026: an apostrophe inside a `--` comment used to open a phantom string literal,
        // leaving EVERY bridge function after it unrewritten — Postgres then failed with
        // `function erp_now() does not exist`. The comment is copied verbatim and never touches
        // the string state, exactly like `translate` already does for its `:name` binds.
        let (sql, _) = translate("-- the slot's capacity\nSELECT erp_now()");
        assert_eq!(sql, "-- the slot's capacity\nSELECT now()");
    }

    #[test]
    fn shim_skips_block_comments_so_an_apostrophe_does_not_swallow_the_rest() {
        let (sql, _) = translate("/* it's here */ SELECT erp_now()");
        assert_eq!(sql, "/* it's here */ SELECT now()");
    }

    #[test]
    fn shim_leaves_a_bridge_call_inside_a_comment_verbatim() {
        // A call documented in a comment is prose, not code: it must not be rewritten.
        let (sql, _) = translate("-- use erp_now() here\nSELECT 1");
        assert_eq!(sql, "-- use erp_now() here\nSELECT 1");
    }

    #[test]
    fn ddl_shim_skips_comments_so_an_apostrophe_does_not_swallow_the_types() {
        // hub#1026, same root cause one function over: a `'` in a `--` comment left the rest of a
        // MIGRATION "inside a string", so the portable types after it were never normalised —
        // `BLOB` does not exist in Postgres and `INTEGER` is not `BIGINT`. Worse than the bridge
        // case: it lands in the schema.
        let out = shim_ddl_types("-- the slot's capacity\nCREATE TABLE t (n INTEGER, b BLOB);");
        assert_eq!(
            out,
            "-- the slot's capacity\nCREATE TABLE t (n BIGINT, b BYTEA);"
        );
    }

    #[test]
    fn shim_erp_now() {
        let (sql, _) = translate("INSERT INTO t (created_at) VALUES (erp_now())");
        assert_eq!(sql, "INSERT INTO t (created_at) VALUES (now())");
    }

    #[test]
    fn shim_erp_lpad() {
        let (sql, names) = translate("SELECT erp_lpad(:code, 8, '*')");
        assert_eq!(sql, "SELECT lpad(($1)::text, greatest(8, length(($1)::text)), '*')");
        assert_eq!(names, vec!["code"]);
    }

    #[test]
    fn shim_erp_dt() {
        let (p, _) = translate("SELECT erp_dt(:x)");
        assert_eq!(p, "SELECT (($1)::timestamptz)");
    }

    #[test]
    fn shim_erp_date() {
        let (p, _) = translate("SELECT erp_date(:x)");
        assert_eq!(p, "SELECT (($1)::date)");
    }

    #[test]
    fn shim_erp_dateadd() {
        let (p, _) = translate("SELECT erp_dateadd(:now, c.dur, 'minutes')");
        assert_eq!(p, "SELECT (($1)::timestamptz + ((c.dur) || ' ' || 'minutes')::interval)");
    }

    #[test]
    fn shim_erp_month_start() {
        let (p, _) = translate("WHERE x >= erp_month_start(:now)");
        assert_eq!(p, "WHERE x >= date_trunc('month', ($1)::timestamptz)");
    }

    #[test]
    fn shim_erp_dow_mon0() {
        let (p, _) = translate("SELECT erp_dow_mon0(:date)");
        assert_eq!(p, "SELECT ((EXTRACT(ISODOW FROM ($1)::timestamptz)::int) - 1)");
    }

    #[test]
    fn shim_erp_extract() {
        let (p, _) = translate("SELECT erp_extract('minute', :dt)");
        assert_eq!(p, "SELECT (EXTRACT(minute FROM ($1)::timestamptz)::bigint)");
    }

    #[test]
    fn shim_erp_datediff_days() {
        let (p, _) = translate("WHERE erp_datediff_days(:a, :b) >= 1");
        assert_eq!(
            p,
            "WHERE (EXTRACT(EPOCH FROM (($1)::timestamptz - ($2)::timestamptz)) / 86400.0) >= 1"
        );
    }

    #[test]
    fn shim_erp_timefmt() {
        let (p, _) = translate("SELECT erp_timefmt(m / 60, m % 60)");
        assert_eq!(
            p,
            "SELECT (lpad((m / 60)::text, greatest(2, length((m / 60)::text)), '0') || ':' || \
             lpad((m % 60)::text, greatest(2, length((m % 60)::text)), '0'))"
        );
    }

    #[test]
    fn shim_erp_date_funcs_distinguish_similar_prefixes() {
        // erp_date / erp_dateadd / erp_datediff_days comparten prefijo: el guard `next_is_ident`
        // garantiza que se elige el nombre correcto sin depender del orden del array.
        let (p, _) = translate(
            "SELECT erp_date(:x), erp_dateadd(:x, 1, 'days'), erp_datediff_days(:x, :y)",
        );
        assert_eq!(
            p,
            "SELECT (($1)::date), (($1)::timestamptz + ((1) || ' ' || 'days')::interval), \
             (EXTRACT(EPOCH FROM (($1)::timestamptz - ($2)::timestamptz)) / 86400.0)"
        );
    }

    // ── shim de normalización de tipos en DDL (ADR-0007 §4b) ──────────────────────────────────

    #[test]
    fn ddl_types_postgres_mapping() {
        let ddl = "CREATE TABLE t (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, qty INTEGER, \
                   amount_cents INTEGER, weight REAL, raw BLOB)";
        let out = shim_ddl_types(ddl);
        assert_eq!(
            out,
            "CREATE TABLE t (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, qty BIGINT, \
             amount_cents BIGINT, weight DOUBLE PRECISION, raw BYTEA)"
        );
    }

    #[test]
    fn ddl_types_do_not_touch_column_names_or_literals() {
        // Una columna llamada `text` (no tipo) ni un literal `'INTEGER'` deben tocarse: sólo el
        // token de tipo en posición de tipo. Comprobamos que respeta literales y mayúsculas/minúsculas.
        let ddl = "CREATE TABLE t (note TEXT DEFAULT 'an INTEGER value', flag integer)";
        let out = shim_ddl_types(ddl);
        assert_eq!(out, "CREATE TABLE t (note TEXT DEFAULT 'an INTEGER value', flag BIGINT)");
    }

    // ── tamaño del pool Postgres vía env `HUB_DB_MAX_CONNECTIONS` (§8; ERPlora/saas#609) ──────
    //
    // Contrato acordado con el SaaS: entero > 0. Ausente (o vacío) → default 10 SIN warning.
    // Valor inválido (basura, 0, negativo) → default 10 CON warning. Se testea la función pura
    // `resolve_pg_max_connections` (no toca el env del proceso: los tests corren en paralelo).

    #[test]
    fn pg_max_connections_valid_value_is_used() {
        assert_eq!(resolve_pg_max_connections(Some("5")), (5, None));
        assert_eq!(resolve_pg_max_connections(Some("40")), (40, None));
        assert_eq!(resolve_pg_max_connections(Some(" 7 ")), (7, None));
    }

    #[test]
    fn pg_max_connections_absent_defaults_silently() {
        assert_eq!(resolve_pg_max_connections(None), (DEFAULT_PG_MAX_CONNECTIONS, None));
    }

    #[test]
    fn pg_max_connections_empty_is_treated_as_absent() {
        assert_eq!(resolve_pg_max_connections(Some("")), (DEFAULT_PG_MAX_CONNECTIONS, None));
        assert_eq!(resolve_pg_max_connections(Some("   ")), (DEFAULT_PG_MAX_CONNECTIONS, None));
    }

    #[test]
    fn pg_max_connections_garbage_defaults_with_warning() {
        let (n, warn) = resolve_pg_max_connections(Some("banana"));
        assert_eq!(n, DEFAULT_PG_MAX_CONNECTIONS);
        let warn = warn.expect("un valor inválido debe producir un warning");
        assert!(warn.contains("HUB_DB_MAX_CONNECTIONS"), "el warning nombra el env: {warn}");
        assert!(warn.contains("banana"), "el warning incluye el valor recibido: {warn}");
    }

    #[test]
    fn pg_max_connections_zero_or_negative_is_invalid() {
        let (n, warn) = resolve_pg_max_connections(Some("0"));
        assert_eq!((n, warn.is_some()), (DEFAULT_PG_MAX_CONNECTIONS, true));
        let (n, warn) = resolve_pg_max_connections(Some("-3"));
        assert_eq!((n, warn.is_some()), (DEFAULT_PG_MAX_CONNECTIONS, true));
    }

    #[test]
    fn pg_max_connections_default_matches_sqlx_default() {
        assert_eq!(DEFAULT_PG_MAX_CONNECTIONS, 10);
    }

    // ── Statement cache vs. NULL binds (`DynNull`, OID 0) — ERPlora/hub#1348 ──────────────────
    //
    // sqlx keys its prepared-statement cache on the SQL **text** alone, and `get_or_prepare`
    // consults that cache before it honours `persistent`. So the parameter types negotiated by the
    // FIRST execution of a text stay pinned to it for the life of the connection.
    //
    // A JSON `null` binds as `DynNull` (OID 0 = "infer from context"), which hands the type choice
    // to the server. With `CAST(:cost AS INTEGER)` — the shape
    // `inventory/commands/_receive_line.sql` really uses — the server picks `int4`. The next
    // execution binds an `i64`: 8 bytes of binary payload into a 4-byte slot, and Postgres answers
    // `22P03 incorrect binary data format in bind parameter N`.
    //
    // It is not an inventory quirk: ANY optional `["integer","null"]` field that is sometimes sent
    // and sometimes omitted hits it, and in production one pooled connection serves thousands of
    // requests, so the two shapes meeting on one connection is the normal case, not the rare one.
    // The pools below are capped at ONE connection so these tests prove that instead of hoping for
    // it.

    /// Write path: the same INSERT text run first with `null`, then with a typed value.
    #[tokio::test]
    async fn null_bind_then_typed_bind_on_the_same_sql_hub1348() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_with_max_connections(1).await;
        db.execute_batch("CREATE TABLE stock (id TEXT PRIMARY KEY, hub_id TEXT, cost INTEGER);")
            .await
            .unwrap();

        // The SAME text on both calls: that is what makes them meet on the cached statement.
        let sql =
            "INSERT INTO stock (id, hub_id, cost) VALUES (:id, :hub_id, CAST(:cost AS INTEGER))";

        db.execute(sql, &params(json!({ "id": "a", "hub_id": "h1", "cost": Json::Null })))
            .await
            .expect("el bind NULL (DynNull, OID 0) debe insertar");

        db.execute(sql, &params(json!({ "id": "b", "hub_id": "h1", "cost": 180 })))
            .await
            .expect(
                "tras preparar la sentencia con un bind NULL, un valor tipado en la MISMA \
                 conexión debe seguir funcionando (hub#1348)",
            );

        // Not blowing up is not enough: both values have to have landed RIGHT. A slot with the
        // wrong type can also swallow the bytes and store garbage without saying anything.
        let rows = db
            .query(
                "SELECT id, cost FROM stock WHERE hub_id = :hub_id ORDER BY id",
                &params(json!({ "hub_id": "h1" })),
            )
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 2, "las dos filas se insertaron: {rows:?}");
        assert_eq!(rows[0]["cost"], Json::Null, "la fila del bind NULL guarda NULL");
        assert_eq!(rows[1]["cost"], json!(180), "la fila tipada guarda el valor exacto");
    }

    /// Read path: same story through `query`. A list that filters by an optional field breaks the
    /// same way, and `build_query!` is the single door both paths go through.
    #[tokio::test]
    async fn null_bind_then_typed_bind_on_the_same_select_hub1348() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_with_max_connections(1).await;
        db.execute_batch("CREATE TABLE stock (id TEXT PRIMARY KEY, hub_id TEXT, cost INTEGER);")
            .await
            .unwrap();
        db.execute_batch(
            "INSERT INTO stock (id, hub_id, cost) VALUES ('a', 'h1', NULL), ('b', 'h1', 180);",
        )
        .await
        .unwrap();

        let sql = "SELECT id FROM stock WHERE hub_id = :hub_id \
                   AND cost IS NOT DISTINCT FROM CAST(:cost AS INTEGER) ORDER BY id";

        let null_first = db
            .query(sql, &params(json!({ "hub_id": "h1", "cost": Json::Null })))
            .await
            .expect("el bind NULL (DynNull, OID 0) debe consultar");
        assert_eq!(null_first.rows.len(), 1, "el filtro NULL devuelve su fila");
        assert_eq!(null_first.rows[0]["id"], json!("a"));

        let typed_second = db
            .query(sql, &params(json!({ "hub_id": "h1", "cost": 180 })))
            .await
            .expect(
                "tras preparar el SELECT con un bind NULL, un valor tipado en la MISMA conexión \
                 debe seguir funcionando (hub#1348)",
            );
        assert_eq!(typed_second.rows.len(), 1, "el filtro tipado devuelve su fila");
        assert_eq!(typed_second.rows[0]["id"], json!("b"));
    }

    /// The SILENT face of the same bug, and the reason the fix is a blanket one: no `NULL` is
    /// involved here at all. `build_query!` picks the Rust type from the JSON value — `i64` for
    /// `180`, `f64` for `180.5` (see the bind loop above) — so one SQL text legitimately reaches
    /// the same slot as two different types. With the statement cached, the second execution's 8
    /// bytes of `f64` are decoded as the `int8` the first execution pinned: same width, so
    /// Postgres raises NOTHING and stores the IEEE-754 bit pattern as a number.
    ///
    /// This is what rules out the narrower fix of "skip the cache only when a bind is `DynNull`":
    /// it would leave this open, and this one does not announce itself (ERPlora/hub#1348).
    #[tokio::test]
    async fn int_bind_then_float_bind_on_the_same_sql_hub1348() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_with_max_connections(1).await;
        db.execute_batch(
            "CREATE TABLE stock (id TEXT PRIMARY KEY, hub_id TEXT, cost DOUBLE PRECISION);",
        )
        .await
        .unwrap();

        let sql = "INSERT INTO stock (id, hub_id, cost) VALUES (:id, :hub_id, \
                   CAST(:cost AS DOUBLE PRECISION))";

        db.execute(sql, &params(json!({ "id": "a", "hub_id": "h1", "cost": 180 })))
            .await
            .expect("el bind entero debe insertar");

        db.execute(sql, &params(json!({ "id": "b", "hub_id": "h1", "cost": 180.5 })))
            .await
            .expect("el bind decimal en la MISMA conexión debe insertar (hub#1348)");

        let rows = db
            .query(
                "SELECT id, cost FROM stock WHERE hub_id = :hub_id ORDER BY id",
                &params(json!({ "hub_id": "h1" })),
            )
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 2, "las dos filas se insertaron: {rows:?}");
        assert_eq!(rows[0]["cost"], json!(180.0), "la fila entera guarda 180");
        assert_eq!(
            rows[1]["cost"],
            json!(180.5),
            "la fila decimal guarda 180.5 y NO el patrón de bits reinterpretado como int8"
        );
    }

    #[test]
    fn portable_sql_normalizes_for_postgres() {
        let sql = "INSERT INTO t (n, ts) VALUES (erp_pad(:seq, 4), erp_now())";
        let (pg, _) = translate(sql);
        assert_eq!(
            pg,
            "INSERT INTO t (n, ts) VALUES (lpad(($1)::text, greatest(4, length(($1)::text)), '0'), \
             now())"
        );
    }

    // ── hub#1376: a database switchover must not leave the pool writing to the replica ───────
    //
    // Patroni promotes another node and the private LB (TCP level) only routes NEW connections to
    // the leader: the ones the pool already had open stay pinned to the ex-leader, now a replica,
    // which rejects every write with `25006 read_only_sql_transaction`. Without recycling them the
    // hub is unusable FOREVER — measured in PRE on 2026-08-29: 25 minutes hammering the replica.
    //
    // `SET default_transaction_read_only = on` reproduces that EXACTLY on a live pooled connection:
    // same SQLSTATE, same connection. sqlx runs no `DISCARD ALL` when a connection goes back to the
    // pool (there is no `after_release` hook configured), so the poison survives the round trip.

    fn sqlstate_of(err: &DbError) -> Option<String> {
        let DbError::Sqlx(e) = err;
        e.as_database_error().and_then(|e| e.code()).map(|c| c.to_string())
    }

    /// The single-statement write path (`execute`) — the one the outbox/flow-trigger/scheduled-task
    /// claim loops hammer, and the one that logged 147 lines of `25006` during the incident.
    #[tokio::test]
    async fn execute_recovers_from_a_switchover_instead_of_writing_to_the_replica_hub1376() {
        let tdb = TestDb::new().await;
        // One connection: the test STATES that the write reuses the poisoned one instead of
        // hoping the pool hands it back.
        let db = tdb.adapter_with_max_connections(1).await;
        db.execute_batch("CREATE TABLE claims (id BIGINT PRIMARY KEY, n BIGINT);")
            .await
            .unwrap();
        db.execute("INSERT INTO claims (id, n) VALUES (1, 1)", &params(json!({})))
            .await
            .unwrap();

        demote_pooled_connections_to_replica(&db, 1).await;

        db.execute("UPDATE claims SET n = 2 WHERE id = 1", &params(json!({})))
            .await
            .expect(
                "after a switchover the pooled connection talks to a replica: the write must \
                 recycle it and land on a fresh one, not fail forever (hub#1376)",
            );

        let rows = db.query("SELECT n FROM claims WHERE id = 1", &params(json!({}))).await.unwrap().rows;
        assert_eq!(rows[0]["n"], json!(2), "the retried write actually landed");
    }

    /// The transactional write path (`execute_tx`): a declarative command batches its mutation and
    /// its `_event_outbox` INSERTs into one tx, so this is what a real sale goes through.
    #[tokio::test]
    async fn execute_tx_recovers_from_a_switchover_hub1376() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_with_max_connections(1).await;
        db.execute_batch("CREATE TABLE sales (id BIGINT PRIMARY KEY, total BIGINT);")
            .await
            .unwrap();

        demote_pooled_connections_to_replica(&db, 1).await;

        db.execute_tx(&[
            ("INSERT INTO sales (id, total) VALUES (1, 100)".to_string(), params(json!({}))),
            ("INSERT INTO sales (id, total) VALUES (2, 200)".to_string(), params(json!({}))),
        ])
        .await
        .expect("a transaction that opened on the replica must be retried on the leader (hub#1376)");

        let rows = db.query("SELECT id FROM sales ORDER BY id", &params(json!({}))).await.unwrap().rows;
        assert_eq!(rows.len(), 2, "the whole transaction landed exactly once: {rows:?}");
    }

    /// The gated transactional path (`execute_tx_gated`) — the door every declarative command with
    /// `min_affected_rows` goes through.
    #[tokio::test]
    async fn execute_tx_gated_recovers_from_a_switchover_hub1376() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_with_max_connections(1).await;
        db.execute_batch("CREATE TABLE appts (id BIGINT PRIMARY KEY, state TEXT);")
            .await
            .unwrap();
        db.execute("INSERT INTO appts (id, state) VALUES (1, 'booked')", &params(json!({})))
            .await
            .unwrap();

        demote_pooled_connections_to_replica(&db, 1).await;

        let out = db
            .execute_tx_gated(
                &[("UPDATE appts SET state = 'done' WHERE id = 1".to_string(), params(json!({})))],
                &[RowGate { first: 0, count: 1, min: 1 }],
            )
            .await
            .expect("a gated transaction must survive a switchover too (hub#1376)");
        assert!(
            matches!(out, TxGatedOutcome::Committed { .. }),
            "the gate saw the real affected-row count of the retried tx: {out:?}"
        );
    }

    /// Migrations (`execute_batch`) run on boot, which is exactly when a hub is redeployed after a
    /// switchover — the path must recycle the connection as well.
    #[tokio::test]
    async fn execute_batch_recovers_from_a_switchover_hub1376() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_with_max_connections(1).await;
        db.execute_batch("CREATE TABLE a (id BIGINT PRIMARY KEY);").await.unwrap();

        demote_pooled_connections_to_replica(&db, 1).await;

        db.execute_batch("CREATE TABLE b (id BIGINT PRIMARY KEY);")
            .await
            .expect("DDL must be retried on a fresh connection after a switchover (hub#1376)");
    }

    /// More than one poisoned connection: after a switchover EVERY connection the pool holds is
    /// stale, not just the one that happened to trip the error. Closing only the offending one
    /// would leave the next request to fail again — which is how "it recovers" turns into "it
    /// recovers eventually, maybe".
    #[tokio::test]
    async fn a_switchover_drains_every_stale_connection_not_just_the_failing_one_hub1376() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_with_max_connections(4).await;
        db.execute_batch("CREATE TABLE claims (id BIGINT PRIMARY KEY, n BIGINT);")
            .await
            .unwrap();

        demote_pooled_connections_to_replica(&db, 4).await;

        // Every one of these would hit a different poisoned connection.
        for id in 1..=4i64 {
            db.execute(
                "INSERT INTO claims (id, n) VALUES (:id, 1)",
                &params(json!({ "id": id })),
            )
            .await
            .unwrap_or_else(|e| panic!("write {id} after a switchover must succeed: {e}"));
        }

        let rows = db.query("SELECT id FROM claims", &params(json!({}))).await.unwrap().rows;
        assert_eq!(rows.len(), 4, "all four writes landed: {rows:?}");
    }

    /// The other side of the coin: if the whole cluster really is read-only (Patroni with no
    /// leader, a full disk), retrying cannot help. The error MUST come back — bounded — instead of
    /// looping forever or being swallowed. A retry that never gives up is an outage that never
    /// shows up in the logs.
    #[tokio::test]
    async fn a_genuinely_read_only_database_surfaces_the_error_instead_of_looping_hub1376() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_read_only().await;
        let err = db
            .execute("CREATE TABLE nope (id BIGINT)", &params(json!({})))
            .await
            .expect_err("a read-only cluster must surface the error, not retry forever");
        assert_eq!(
            sqlstate_of(&err).as_deref(),
            Some(READ_ONLY_SQLSTATE),
            "the caller still sees the real SQLSTATE: {err:?}"
        );
    }


    /// The switchover must not be silent. `/` answering 200 while every write fails is exactly how
    /// this went unnoticed for 25 minutes in PRE, so the recovery leaves a number behind.
    #[tokio::test]
    async fn a_recovered_switchover_is_counted_so_it_is_not_silent_hub1376() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_with_max_connections(1).await;
        db.execute_batch("CREATE TABLE claims (id BIGINT PRIMARY KEY);").await.unwrap();
        assert_eq!(db.read_only_rejections(), 0, "nothing has gone wrong yet");

        demote_pooled_connections_to_replica(&db, 1).await;
        db.execute("INSERT INTO claims (id) VALUES (1)", &params(json!({}))).await.unwrap();

        assert_eq!(
            db.read_only_rejections(),
            1,
            "the write recovered, but the switchover it survived is still visible to the operator"
        );
    }

    /// The alert is raised once per switchover, not once per health check: an alert that repeats
    /// forever is an alert everyone learns to ignore, which is the same silence in a louder shirt.
    #[tokio::test]
    async fn the_switchover_alert_is_handed_over_once_hub1376() {
        let tdb = TestDb::new().await;
        let db = tdb.adapter_with_max_connections(1).await;
        db.execute_batch("CREATE TABLE claims (id BIGINT PRIMARY KEY);").await.unwrap();

        demote_pooled_connections_to_replica(&db, 1).await;
        db.execute("INSERT INTO claims (id) VALUES (1)", &params(json!({}))).await.unwrap();

        assert_eq!(db.take_unreported_read_only_rejections(), 1, "the host gets the alert once");
        assert_eq!(
            db.take_unreported_read_only_rejections(),
            0,
            "and not again on the next health check"
        );
        assert_eq!(
            db.read_only_rejections(),
            1,
            "the running total survives the hand-over: it is what a later postmortem reads"
        );
    }

    /// A hub with no write traffic never trips `25006`, so nothing would ever recycle its
    /// connections: they would sit on the ex-leader serving reads from a node that is no longer
    /// the leader. The lifetime cap is the only thing covering that hub, so it is not optional.
    #[test]
    fn the_pool_recycles_connections_even_without_write_traffic_hub1376() {
        let opts = pg_pool_options(7, Arc::new(ReplicaWatch::default()));
        assert_eq!(opts.get_max_connections(), 7, "the per-plan cap still comes from the caller");
        assert_eq!(
            opts.get_max_lifetime(),
            Some(PG_MAX_LIFETIME),
            "a pooled connection must not outlive the leader that answered it"
        );
        assert_eq!(
            opts.get_idle_timeout(),
            Some(PG_IDLE_TIMEOUT),
            "an idle connection costs nothing to recycle, so it goes sooner"
        );
        assert!(
            PG_IDLE_TIMEOUT < PG_MAX_LIFETIME,
            "idle connections have to be dropped before the hard cap, not after"
        );
    }

    // ── TLS policy for the connect options (hub#1398) ─────────────────────────────────────────

    #[test]
    fn a_remote_dsn_gets_upgraded_to_ssl_require_hub1398() {
        let opts: PgConnectOptions = "postgres://user:pass@10.10.1.6:5432/hub".parse().unwrap();
        assert!(
            matches!(opts.get_ssl_mode(), PgSslMode::Prefer),
            "sanity: sqlx's own default for a DSN with no sslmode"
        );

        let opts = require_tls_unless_local(opts);

        assert!(
            matches!(opts.get_ssl_mode(), PgSslMode::Require),
            "lb-db is not loopback: the client must refuse a downgrade instead of silently \
             falling back to plaintext"
        );
    }

    #[test]
    fn the_local_test_database_keeps_prefer_hub1398() {
        for host in ["localhost", "127.0.0.1", "[::1]"] {
            let dsn = format!("postgres://postgres:test@{host}:5433/hub_test");
            let opts: PgConnectOptions = dsn.parse().unwrap();
            let opts = require_tls_unless_local(opts);
            assert!(
                matches!(opts.get_ssl_mode(), PgSslMode::Prefer),
                "erplora-test-pg-5433 has no TLS configured — forcing require would break \
                 every test ({host})"
            );
        }
    }

    /// sqlx has TWO spellings for a Unix socket and `fetch_socket()` honours both: the `socket`
    /// field, and a plain `host` that starts with `/` (`PgConnectOptions::new()` lands there on
    /// its own — `default_host()` returns `/var/run/postgresql` on Debian, `/private/tmp` on a
    /// homebrew Mac, whenever the socket file is present). Only the first was exempted, and the
    /// miss is not cosmetic: sqlx runs the TLS upgrade over a UDS too, and `Require` there dies
    /// with «server does not support TLS» — Postgres never speaks SSL on a Unix socket.
    #[test]
    fn a_unix_socket_spelled_as_a_host_path_keeps_prefer_hub1398() {
        for dir in ["/var/run/postgresql", "/private/tmp", "/tmp"] {
            let opts = PgConnectOptions::new().host(dir);
            assert!(
                matches!(opts.get_ssl_mode(), PgSslMode::Prefer),
                "sanity: sqlx's own default before the policy runs ({dir})"
            );

            let opts = require_tls_unless_local(opts);

            assert!(
                matches!(opts.get_ssl_mode(), PgSslMode::Prefer),
                "a host that starts with `/` IS a Unix socket for sqlx: forcing require makes \
                 the connection fail outright ({dir})"
            );
        }
    }

    #[test]
    fn a_dsn_that_already_asks_for_a_stronger_mode_is_left_alone_hub1398() {
        let opts: PgConnectOptions = "postgres://user:pass@lb-db:5432/hub?sslmode=verify-full"
            .parse()
            .unwrap();

        let opts = require_tls_unless_local(opts);

        assert!(
            matches!(opts.get_ssl_mode(), PgSslMode::VerifyFull),
            "an explicit verify-full must not be downgraded to require"
        );
    }

    /// The generation check itself, without a database in the way: it is what decides whether the
    /// pool keeps a connection, so its edges deserve to be pinned down.
    #[test]
    fn only_connections_older_than_the_switchover_are_discarded_hub1376() {
        let watch = ReplicaWatch::default();
        assert!(
            !watch.is_stale(Duration::from_secs(3600)),
            "with no switchover seen, even an ancient connection is fine"
        );

        watch.record_rejection();
        assert!(
            watch.is_stale(Duration::from_secs(60)),
            "a connection opened a minute before the switchover is pinned to the ex-leader"
        );
        assert!(
            !watch.is_stale(Duration::ZERO),
            "a connection opened after the switchover talks to the new leader and is kept — \
             otherwise the retry would throw away the very connection it just opened"
        );
        assert_eq!(watch.rejections(), 1, "the rejection was counted exactly once");
    }

}
