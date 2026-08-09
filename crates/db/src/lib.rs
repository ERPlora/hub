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

use async_trait::async_trait;
use serde_json::{Map, Value as Json};
use sqlx::encode::IsNull;
use sqlx::error::BoxDynError;
use sqlx::{Column, Encode, Row, Type, TypeInfo, ValueRef};

mod migration_lock;
pub use migration_lock::{MigrationLock, MigrationLockError};

use sqlx::postgres::{PgPool, PgPoolOptions, PgRow};

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
    /// The gate failed; the tx **rolled back** (no mutation, no outbox). `sql_counts` holds the
    /// affected counts of just the mutation statements, so the runtime can report the real number.
    RolledBack { sql_counts: Vec<u64> },
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
    /// - `sql_op_count`: the leading ops are the command's mutation statements; the rest are outbox
    ///   inserts (and `extra_ops`). The gate runs over the per-op counts of the FIRST
    ///   `sql_op_count` ops only — outbox INSERTs always affect exactly 1 and must not feed the gate
    ///   (otherwise a "confirm" over a missing appointment would mutate 0 rows but still pass once
    ///   its outbox INSERT is counted).
    /// - `min_affected_rows`: the required total across those `sql_op_count` statements. `None`
    ///   disables the gate (legacy behavior — commit unconditionally, like [`execute_tx`]).
    ///
    /// On commit returns [`TxGatedOutcome::Committed`] with every per-op count (diagnostics);
    /// on a gate failure returns [`TxGatedOutcome::RolledBack`] with the SQL counts so the runtime
    /// can build the stable `MinAffectedRows` error. A real DB error propagates as `Err` (the tx
    /// has already rolled back). `execute_tx` stays as the total-only path for callers that don't
    /// care (reset, migrations, user_profile): changing its return type would be a wider blast
    /// radius for no gain.
    async fn execute_tx_gated(
        &self,
        ops: &[(String, Params)],
        sql_op_count: usize,
        min_affected_rows: Option<u64>,
    ) -> Result<TxGatedOutcome, DbError>;

    /// Runs a query and returns the rows as JSON objects.
    async fn query(&self, sql: &str, params: &Params) -> Result<QueryResult, DbError>;

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
        let mut q = sqlx::query(sqlx::AssertSqlSafe($tsql));
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
/// construction ([`PG_MAX_CONNECTIONS_ENV`], per plan, managed by the SaaS); the rest of the
/// pool tuning (TLS, timeouts) is pending (§8).
pub struct PgAdapter {
    pool: PgPool,
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
    /// TODO §8: use `PgPoolOptions` with TLS require,
    /// max_lifetime/idle_timeout to survive failovers.
    pub async fn connect(dsn: &str) -> Result<Self, DbError> {
        let pool = PgPoolOptions::new()
            .max_connections(pg_max_connections_from_env())
            .connect(dsn)
            .await?;
        Ok(Self { pool })
    }

    /// Build an adapter over an already-configured pool (used by the test helpers).
    #[cfg(any(test, feature = "test-util"))]
    pub(crate) fn from_pool(pool: PgPool) -> Self {
        Self { pool }
    }
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
        let q = build_query!(tsql, names, params);
        let res = q.execute(&self.pool).await?;
        Ok(CommandResult::affected(res.rows_affected()))
    }

    async fn execute_tx(&self, ops: &[(String, Params)]) -> Result<CommandResult, DbError> {
        let mut tx = self.pool.begin().await?;
        let mut total = 0u64;
        for (sql, params) in ops {
            let (tsql, names) = translate(sql);
            let q = build_query!(tsql, names, params);
            total += q.execute(&mut *tx).await?.rows_affected();
        }
        tx.commit().await?;
        Ok(CommandResult::affected(total))
    }

    async fn execute_tx_gated(
        &self,
        ops: &[(String, Params)],
        sql_op_count: usize,
        min_affected_rows: Option<u64>,
    ) -> Result<TxGatedOutcome, DbError> {
        let mut tx = self.pool.begin().await?;
        let mut per_op = Vec::with_capacity(ops.len());
        for (sql, params) in ops {
            let (tsql, names) = translate(sql);
            let q = build_query!(tsql, names, params);
            per_op.push(q.execute(&mut *tx).await?.rows_affected());
        }
        // La gate se evalúa SOLO sobre las sentencias de mutación (las primeras `sql_op_count`):
        // los INSERT del outbox siempre afectan 1 y NO deben entrar en el recuento (un "confirmar"
        // sobre una cita inexistente muta 0 filas, aunque luego inserte un evento — si el evento
        // contara, la gate pasaría siempre y el bug del issue seguiría vivo).
        if let Some(min) = min_affected_rows {
            let n = sql_op_count.min(per_op.len());
            let affected: u64 = per_op[..n].iter().sum();
            if affected < min {
                // Rollback explícito: el default-drop de sqlx haría lo mismo al caer del scope,
                // pero dejarlo tácito es justo el tipo de "OK silencioso" que hub#140 elimina.
                tx.rollback().await?;
                let sql_counts = per_op[..n].to_vec();
                return Ok(TxGatedOutcome::RolledBack { sql_counts });
            }
        }
        tx.commit().await?;
        Ok(TxGatedOutcome::Committed { per_op })
    }

    async fn query(&self, sql: &str, params: &Params) -> Result<QueryResult, DbError> {
        let (tsql, names) = translate(sql);
        let q = build_query!(tsql, names, params);
        let rows = q.fetch_all(&self.pool).await?;
        let out = rows.iter().map(pg_row_to_json).collect();
        Ok(QueryResult::new(out))
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
        sqlx::raw_sql(sqlx::AssertSqlSafe(normalized)).execute(&self.pool).await?;
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
/// - `erp_lpad(valor, ancho, relleno)` → `lpad((<valor>)::text, <ancho>, <relleno>)`.
/// - `erp_pad(valor, ancho)` = atajo de `erp_lpad(valor, ancho, '0')` para números de documento
///   (factura `FAC-00042`, ticket `TCK-0042`) → `lpad((<valor>)::text, <ancho>, '0')`.
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
            Some(format!("lpad(({value})::text, {width}, '0')"))
        }
        "erp_lpad" => {
            if args.len() != 3 {
                return None;
            }
            let value = arg(0);
            let width = arg(1);
            let fill = arg(2); // literal `'x'` o expresión
            Some(format!("lpad(({value})::text, {width}, {fill})"))
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
            Some(format!(
                "(lpad(({h})::text, 2, '0') || ':' || lpad(({m})::text, 2, '0'))"
            ))
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
    use crate::testutil::fresh_db;
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
        assert_eq!(sql, "SELECT 'FAC-' || lpad(($1)::text, 5, '0')");
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
            "SELECT lpad(((SELECT max(seq) + 1 FROM t WHERE hub_id = $1))::text, 6, '0')"
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
    fn shim_erp_now() {
        let (sql, _) = translate("INSERT INTO t (created_at) VALUES (erp_now())");
        assert_eq!(sql, "INSERT INTO t (created_at) VALUES (now())");
    }

    #[test]
    fn shim_erp_lpad() {
        let (sql, names) = translate("SELECT erp_lpad(:code, 8, '*')");
        assert_eq!(sql, "SELECT lpad(($1)::text, 8, '*')");
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
            "SELECT (lpad((m / 60)::text, 2, '0') || ':' || lpad((m % 60)::text, 2, '0'))"
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

    #[test]
    fn portable_sql_normalizes_for_postgres() {
        let sql = "INSERT INTO t (n, ts) VALUES (erp_pad(:seq, 4), erp_now())";
        let (pg, _) = translate(sql);
        assert_eq!(pg, "INSERT INTO t (n, ts) VALUES (lpad(($1)::text, 4, '0'), now())");
    }
}
