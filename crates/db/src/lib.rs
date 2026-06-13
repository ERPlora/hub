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
        // Migraciones: normaliza los tipos del `CREATE TABLE` al motor target (ADR-0007 §4b).
        // En SQLite es la identidad, pero lo aplicamos por simetría con el adaptador Postgres.
        let normalized = shim_ddl_types(sql, Dialect::Sqlite);
        sqlx::raw_sql(sqlx::AssertSqlSafe(normalized)).execute(&self.pool).await?;
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
        // Migraciones: normaliza los tipos del `CREATE TABLE` al motor target (ADR-0007 §4b).
        // En Postgres mapea TEXT→TEXT, INTEGER→BIGINT, REAL→DOUBLE PRECISION, BLOB→BYTEA.
        let normalized = shim_ddl_types(sql, Dialect::Postgres);
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

// ── shim de funciones-puente: ERPlora SQL → expresión nativa por dialecto (ADR-0007 §4a) ─────

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

/// Reescribe las **funciones-puente** del subconjunto portable a la expresión nativa del dialecto.
/// Sustitución textual anclada con escaneo de paréntesis balanceados (NO es un parser AST),
/// aplicada al traducir el SQL del módulo. UTF-8-safe. Recursiva: un argumento puede contener a
/// su vez otra función-puente.
///
/// Funciones cubiertas (ver [`BRIDGE_FUNCTIONS`]):
/// - `erp_now()` → `CURRENT_TIMESTAMP` (SQLite) / `now()` (Postgres). Timestamp del servidor en el
///   formato nativo del motor (ADR-0007 / runtime-dispatcher §4bis: fechas `TEXT` ISO-8601).
/// - `erp_lpad(valor, ancho, relleno)` → relleno por la izquierda hasta `ancho` con la cadena
///   `relleno`: `printf` no sirve para relleno arbitrario, así que se baja a la forma nativa:
///   - SQLite:   `(substr(replace(hex(zeroblob(<ancho>)),'00',<relleno>),1,max(<ancho>-length(<valor>),0)) || <valor>)`
///     no es portable de forma simple; SQLite **sí** trae `printf('%*s', ...)` para espacios, pero
///     no para relleno arbitrario. Para el caso real (relleno de un solo carácter) usamos
///     `printf` cuando el relleno es `'0'`, y en otro caso degradamos a concatenación.
///   - Postgres: `lpad((<valor>)::text, <ancho>, <relleno>)` (nativo).
/// - `erp_pad(valor, ancho)` = atajo de `erp_lpad(valor, ancho, '0')` para números de documento
///   (factura `FAC-00042`, ticket `TCK-0042`), ya en uso por el equipo:
///   - SQLite:   `printf('%0*d', <ancho>, <valor>)`   (printf admite `*` para tomar el ancho del arg)
///   - Postgres: `lpad((<valor>)::text, <ancho>, '0')`
fn shim_functions(sql: &str, dialect: Dialect) -> String {
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
                    if let Some(repl) = render_bridge_fn(name, sql, &args, dialect) {
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

/// Renderiza una función-puente concreta a su expresión nativa. `None` = aridad incorrecta (se
/// deja el texto intacto; el validador del toolkit debería haberlo atrapado en build).
fn render_bridge_fn(
    name: &str,
    sql: &str,
    args: &[(usize, usize)],
    dialect: Dialect,
) -> Option<String> {
    // Cada argumento puede a su vez contener funciones-puente → recursión.
    let arg = |k: usize| shim_functions(sql[args[k].0..args[k].1].trim(), dialect);
    match name {
        "erp_now" => {
            // `erp_now()` no toma argumentos (un único arg vacío es válido: `()`).
            let empty = args.len() == 1 && sql[args[0].0..args[0].1].trim().is_empty();
            if !(args.is_empty() || empty) {
                return None;
            }
            Some(match dialect {
                Dialect::Sqlite => "CURRENT_TIMESTAMP".to_string(),
                Dialect::Postgres => "now()".to_string(),
            })
        }
        "erp_pad" => {
            if args.len() != 2 {
                return None;
            }
            let value = arg(0);
            let width = arg(1);
            Some(match dialect {
                Dialect::Sqlite => format!("printf('%0*d', {width}, {value})"),
                Dialect::Postgres => format!("lpad(({value})::text, {width}, '0')"),
            })
        }
        "erp_lpad" => {
            if args.len() != 3 {
                return None;
            }
            let value = arg(0);
            let width = arg(1);
            let fill = arg(2); // literal `'x'` o expresión
            Some(match dialect {
                // Caso común relleno='0' con valor numérico → printf con `*`. En otro caso, SQLite
                // no tiene `lpad` nativo: degradamos a la forma con `substr(printf('%*s',...))` que
                // sólo vale para espacios → para relleno arbitrario emitimos un equivalente
                // portable que repite el carácter. Mantener simple: el caso real es '0'.
                Dialect::Sqlite => {
                    if fill == "'0'" {
                        format!("printf('%0*d', {width}, {value})")
                    } else {
                        // substr(printf('%*s', ancho, ''), 1, max(ancho-len,0)) rellena con espacios;
                        // replace cambia el espacio por el carácter de relleno.
                        format!(
                            "(replace(substr(printf('%*s', {width}, ''), 1, max({width} - length(({value})::text), 0)), ' ', {fill}) || ({value})::text)"
                        )
                    }
                }
                Dialect::Postgres => format!("lpad(({value})::text, {width}, {fill})"),
            })
        }

        // ── funciones-puente de fecha/hora ───────────────────────────────────────────────────
        // Contrato (ADR-0007 §1): las fechas se guardan como **TEXT ISO-8601**. En SQLite las
        // funciones `datetime()/date()/strftime()/julianday()` aceptan ese texto directamente; en
        // Postgres hay que castear (`::timestamptz` / `::date`). Comparar dos `erp_dt(...)` entre
        // sí es portable porque ambos lados quedan en el tipo nativo del motor.
        "erp_dt" => {
            // erp_dt(x): normaliza un texto ISO a datetime comparable.
            if args.len() != 1 {
                return None;
            }
            let x = arg(0);
            Some(match dialect {
                Dialect::Sqlite => format!("datetime({x})"),
                Dialect::Postgres => format!("(({x})::timestamptz)"),
            })
        }
        "erp_date" => {
            // erp_date(x): parte fecha (sin hora) de un texto ISO.
            if args.len() != 1 {
                return None;
            }
            let x = arg(0);
            Some(match dialect {
                Dialect::Sqlite => format!("date({x})"),
                Dialect::Postgres => format!("(({x})::date)"),
            })
        }
        "erp_dateadd" => {
            // erp_dateadd(x, n, unit): suma `n` veces `unit` a `x`. `unit` es un literal
            // ('minutes'|'hours'|'days'|'months'|…) compatible con los modificadores de SQLite y
            // con los campos de `interval` de Postgres. `n` puede ser una expresión (columna).
            if args.len() != 3 {
                return None;
            }
            let x = arg(0);
            let n = arg(1);
            let unit = arg(2); // literal entre comillas: 'minutes'
            Some(match dialect {
                // SQLite: datetime(x, '+' || n || ' ' || 'minutes')
                Dialect::Sqlite => {
                    format!("datetime({x}, '+' || ({n}) || ' ' || {unit})")
                }
                // Postgres: (x::timestamptz + ((n) || ' ' || 'minutes')::interval)
                Dialect::Postgres => {
                    format!("(({x})::timestamptz + (({n}) || ' ' || {unit})::interval)")
                }
            })
        }
        "erp_month_start" => {
            // erp_month_start(x): trunca al inicio del mes de `x`.
            if args.len() != 1 {
                return None;
            }
            let x = arg(0);
            Some(match dialect {
                Dialect::Sqlite => format!("datetime({x}, 'start of month')"),
                Dialect::Postgres => format!("date_trunc('month', ({x})::timestamptz)"),
            })
        }
        "erp_dow_mon0" => {
            // erp_dow_mon0(x): día de la semana con 0=lunes … 6=domingo (convención de los
            // módulos). SQLite `strftime('%w')` da 0=domingo … 6=sábado → (+6) % 7. En Postgres
            // ISODOW da 1=lunes … 7=domingo → (ISODOW - 1).
            if args.len() != 1 {
                return None;
            }
            let x = arg(0);
            Some(match dialect {
                Dialect::Sqlite => {
                    format!("((CAST(strftime('%w', {x}) AS INTEGER) + 6) % 7)")
                }
                Dialect::Postgres => {
                    format!("((EXTRACT(ISODOW FROM ({x})::timestamptz)::int) - 1)")
                }
            })
        }
        "erp_extract" => {
            // erp_extract(part, x): extrae un campo de `x` como INTEGER. `part` es un literal:
            // 'hour' | 'minute' | 'second' | 'epoch'. Cubre los strftime('%H'/'%M'/'%S'/'%s').
            if args.len() != 2 {
                return None;
            }
            let part_raw = sql[args[0].0..args[0].1].trim();
            let x = arg(1);
            // El literal debe ir entre comillas simples; tomamos su contenido en minúsculas.
            let part = part_raw.trim_matches('\'').to_ascii_lowercase();
            let (sqlite_code, pg_field) = match part.as_str() {
                "hour" => ("%H", "hour"),
                "minute" => ("%M", "minute"),
                "second" => ("%S", "second"),
                "epoch" => ("%s", "epoch"),
                _ => return None, // parte no soportada → el validador debió atraparlo
            };
            Some(match dialect {
                Dialect::Sqlite => format!("CAST(strftime('{sqlite_code}', {x}) AS INTEGER)"),
                Dialect::Postgres => {
                    format!("(EXTRACT({pg_field} FROM ({x})::timestamptz)::bigint)")
                }
            })
        }
        "erp_datediff_days" => {
            // erp_datediff_days(a, b): diferencia (a - b) en días, fraccionaria (REAL).
            if args.len() != 2 {
                return None;
            }
            let a = arg(0);
            let b = arg(1);
            Some(match dialect {
                Dialect::Sqlite => format!("(julianday({a}) - julianday({b}))"),
                Dialect::Postgres => format!(
                    "(EXTRACT(EPOCH FROM (({a})::timestamptz - ({b})::timestamptz)) / 86400.0)"
                ),
            })
        }
        "erp_timefmt" => {
            // erp_timefmt(h, m): formatea "HH:MM" a partir de dos enteros (horas, minutos).
            if args.len() != 2 {
                return None;
            }
            let h = arg(0);
            let m = arg(1);
            Some(match dialect {
                Dialect::Sqlite => format!("printf('%02d:%02d', {h}, {m})"),
                Dialect::Postgres => format!(
                    "(lpad(({h})::text, 2, '0') || ':' || lpad(({m})::text, 2, '0'))"
                ),
            })
        }
        _ => None,
    }
}

// ── shim de normalización de tipos en DDL (ERPlora SQL → tipo nativo por dialecto) (ADR-0007 §4b) ─

/// Tabla de equivalencias del **subconjunto portable de tipos** a su tipo nativo por motor
/// (ADR-0007 / module-system §4bis: PK `TEXT`, fechas `TEXT` ISO-8601, booleanos y dinero
/// `INTEGER`; `REAL`/`BLOB` para flotantes/binarios no monetarios).
///
/// Para **SQLite** la normalización es la identidad (los tipos ya son los nativos / affinity), así
/// que la tabla sólo mapea de verdad para **Postgres**. Devuelve `None` para un tipo que no esté
/// en el subconjunto (se deja intacto: el validador del toolkit debe rechazar tipos no portables
/// en build).
///
/// TODO (columna del humano): ADR-0007 nombra el subconjunto (`TEXT`/`INTEGER`/`REAL`/`BLOB`) pero
/// no publica una tabla cerrada de equivalencias. Confirmar el mapeo Postgres definitivo
/// (¿`INTEGER`→`BIGINT` siempre, o respetar `INTEGER` 32-bit cuando el módulo lo pida?).
fn normalize_ddl_type(portable: &str, dialect: Dialect) -> Option<&'static str> {
    let t = portable.to_ascii_uppercase();
    match dialect {
        // SQLite: identidad (affinity dinámica). Sólo validamos pertenencia al subconjunto.
        Dialect::Sqlite => match t.as_str() {
            "TEXT" => Some("TEXT"),
            "INTEGER" => Some("INTEGER"),
            "REAL" => Some("REAL"),
            "BLOB" => Some("BLOB"),
            _ => None,
        },
        // Postgres: tipo estático equivalente.
        Dialect::Postgres => match t.as_str() {
            "TEXT" => Some("TEXT"),
            "INTEGER" => Some("BIGINT"), // dinero/booleanos/contadores en céntimos → 64-bit seguro
            "REAL" => Some("DOUBLE PRECISION"),
            "BLOB" => Some("BYTEA"),
            _ => None,
        },
    }
}

/// Normaliza los **tipos de columna** de las sentencias `CREATE TABLE` del SQL al tipo nativo del
/// motor target (ADR-0007 §4b). Sustitución textual anclada (NO parser AST):
///
/// 1. Localiza cada `CREATE TABLE … ( … )` (con el escáner de paréntesis balanceados).
/// 2. Dentro del bloque de columnas, para cada **token de tipo del subconjunto portable**
///    (`TEXT`/`INTEGER`/`REAL`/`BLOB`, como palabra completa, fuera de literales) lo reemplaza por
///    su equivalente nativo según [`normalize_ddl_type`].
///
/// Sólo toca tipos del subconjunto; cualquier otra cosa se deja intacta (nombres de columna,
/// `PRIMARY KEY`, `NOT NULL`, `DEFAULT …`, etc.). Para SQLite es la identidad. Se aplica en
/// `execute_batch` (path de migraciones), no en cada query.
pub fn shim_ddl_types(sql: &str, dialect: Dialect) -> String {
    // SQLite: identidad (la tabla mapea cada tipo a sí mismo). Evita reescribir sin necesidad.
    if dialect == Dialect::Sqlite {
        return sql.to_string();
    }
    let bytes = sql.as_bytes();
    let mut out = String::with_capacity(sql.len() + 16);
    let mut i = 0;
    let mut in_string = false;
    while i < bytes.len() {
        let c = bytes[i];
        if in_string {
            out.push(c as char);
            if c == b'\'' {
                in_string = false;
            }
            i += 1;
            continue;
        }
        if c == b'\'' {
            in_string = true;
            out.push('\'');
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
                    if let Some(native) = normalize_ddl_type(tok, dialect) {
                        out.push_str(native);
                        i = end;
                        continue;
                    }
                }
            }
        }
        out.push(c as char);
        i += 1;
    }
    out
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
    // Funciones-puente ERPlora SQL → expresión nativa del dialecto (ADR-0007 §4a), antes de bajar
    // los placeholders. Trabaja sobre el texto ya con `:name` (se traducen en el segundo paso).
    let shimmed = shim_functions(sql, dialect);
    let sql = shimmed.as_str();

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

    // ── shim de funciones-puente (ADR-0007 §4a): erp_pad → printf/lpad ───────────────────────

    #[test]
    fn shim_erp_pad_sqlite() {
        let (sql, names) = translate("SELECT 'FAC-' || erp_pad(:n, 5)", Dialect::Sqlite);
        assert_eq!(sql, "SELECT 'FAC-' || printf('%0*d', 5, ?1)");
        assert_eq!(names, vec!["n"]);
    }

    #[test]
    fn shim_erp_pad_postgres() {
        let (sql, names) = translate("SELECT 'FAC-' || erp_pad(:n, 5)", Dialect::Postgres);
        assert_eq!(sql, "SELECT 'FAC-' || lpad(($1)::text, 5, '0')");
        assert_eq!(names, vec!["n"]);
    }

    #[test]
    fn shim_erp_pad_nested_subquery() {
        // El valor es una subconsulta con paréntesis anidados: el escáner balanceado la respeta.
        let (sql, names) = translate(
            "SELECT erp_pad((SELECT max(seq) + 1 FROM t WHERE hub_id = :h), 6)",
            Dialect::Postgres,
        );
        assert_eq!(
            sql,
            "SELECT lpad(((SELECT max(seq) + 1 FROM t WHERE hub_id = $1))::text, 6, '0')"
        );
        assert_eq!(names, vec!["h"]);
    }

    #[test]
    fn shim_ignores_erp_pad_inside_string_literal() {
        let (sql, _) = translate("SELECT 'erp_pad(x, 5) literal'", Dialect::Postgres);
        assert_eq!(sql, "SELECT 'erp_pad(x, 5) literal'");
    }

    #[test]
    fn shim_does_not_match_partial_identifier() {
        // `xerp_pad` no es la función-puente: se deja intacto.
        let (sql, _) = translate("SELECT xerp_pad", Dialect::Postgres);
        assert_eq!(sql, "SELECT xerp_pad");
    }

    // ── shim de funciones-puente: erp_now() (ADR-0007 §4a; runtime-dispatcher §4bis) ──────────

    #[test]
    fn shim_erp_now_sqlite() {
        let (sql, _) = translate("INSERT INTO t (created_at) VALUES (erp_now())", Dialect::Sqlite);
        assert_eq!(sql, "INSERT INTO t (created_at) VALUES (CURRENT_TIMESTAMP)");
    }

    #[test]
    fn shim_erp_now_postgres() {
        let (sql, _) = translate("INSERT INTO t (created_at) VALUES (erp_now())", Dialect::Postgres);
        assert_eq!(sql, "INSERT INTO t (created_at) VALUES (now())");
    }

    // ── shim de funciones-puente: erp_lpad(valor, ancho, relleno) ─────────────────────────────

    #[test]
    fn shim_erp_lpad_postgres() {
        let (sql, names) = translate("SELECT erp_lpad(:code, 8, '*')", Dialect::Postgres);
        assert_eq!(sql, "SELECT lpad(($1)::text, 8, '*')");
        assert_eq!(names, vec!["code"]);
    }

    #[test]
    fn shim_erp_lpad_zero_fill_is_printf_in_sqlite() {
        // relleno '0' → atajo con printf (mismo resultado que erp_pad).
        let (sql, _) = translate("SELECT erp_lpad(:n, 5, '0')", Dialect::Sqlite);
        assert_eq!(sql, "SELECT printf('%0*d', 5, ?1)");
    }

    #[test]
    fn shim_erp_lpad_arbitrary_fill_sqlite() {
        // relleno arbitrario → forma portable con substr/replace (espacios→relleno).
        let (sql, _) = translate("SELECT erp_lpad(:code, 4, '*')", Dialect::Sqlite);
        assert_eq!(
            sql,
            "SELECT (replace(substr(printf('%*s', 4, ''), 1, max(4 - length((?1)::text), 0)), ' ', '*') || (?1)::text)"
        );
    }

    // ── shim de funciones-puente de fecha/hora (ADR-0007 §4a) ─────────────────────────────────

    #[test]
    fn shim_erp_dt() {
        let (s, _) = translate("SELECT erp_dt(:x)", Dialect::Sqlite);
        assert_eq!(s, "SELECT datetime(?1)");
        let (p, _) = translate("SELECT erp_dt(:x)", Dialect::Postgres);
        assert_eq!(p, "SELECT (($1)::timestamptz)");
    }

    #[test]
    fn shim_erp_date() {
        let (s, _) = translate("SELECT erp_date(:x)", Dialect::Sqlite);
        assert_eq!(s, "SELECT date(?1)");
        let (p, _) = translate("SELECT erp_date(:x)", Dialect::Postgres);
        assert_eq!(p, "SELECT (($1)::date)");
    }

    #[test]
    fn shim_erp_dateadd() {
        let (s, _) = translate("SELECT erp_dateadd(:now, c.dur, 'minutes')", Dialect::Sqlite);
        assert_eq!(s, "SELECT datetime(?1, '+' || (c.dur) || ' ' || 'minutes')");
        let (p, _) = translate("SELECT erp_dateadd(:now, c.dur, 'minutes')", Dialect::Postgres);
        assert_eq!(p, "SELECT (($1)::timestamptz + ((c.dur) || ' ' || 'minutes')::interval)");
    }

    #[test]
    fn shim_erp_month_start() {
        let (s, _) = translate("WHERE x >= erp_month_start(:now)", Dialect::Sqlite);
        assert_eq!(s, "WHERE x >= datetime(?1, 'start of month')");
        let (p, _) = translate("WHERE x >= erp_month_start(:now)", Dialect::Postgres);
        assert_eq!(p, "WHERE x >= date_trunc('month', ($1)::timestamptz)");
    }

    #[test]
    fn shim_erp_dow_mon0() {
        let (s, _) = translate("SELECT erp_dow_mon0(:date)", Dialect::Sqlite);
        assert_eq!(s, "SELECT ((CAST(strftime('%w', ?1) AS INTEGER) + 6) % 7)");
        let (p, _) = translate("SELECT erp_dow_mon0(:date)", Dialect::Postgres);
        assert_eq!(p, "SELECT ((EXTRACT(ISODOW FROM ($1)::timestamptz)::int) - 1)");
    }

    #[test]
    fn shim_erp_extract() {
        let (s, _) = translate("SELECT erp_extract('hour', :dt)", Dialect::Sqlite);
        assert_eq!(s, "SELECT CAST(strftime('%H', ?1) AS INTEGER)");
        let (p, _) = translate("SELECT erp_extract('minute', :dt)", Dialect::Postgres);
        assert_eq!(p, "SELECT (EXTRACT(minute FROM ($1)::timestamptz)::bigint)");
    }

    #[test]
    fn shim_erp_datediff_days() {
        let (s, _) =
            translate("WHERE erp_datediff_days(:date || ' ' || :time, :now) >= 1", Dialect::Sqlite);
        assert_eq!(s, "WHERE (julianday(?1 || ' ' || ?2) - julianday(?3)) >= 1");
        let (p, _) = translate("WHERE erp_datediff_days(:a, :b) >= 1", Dialect::Postgres);
        assert_eq!(
            p,
            "WHERE (EXTRACT(EPOCH FROM (($1)::timestamptz - ($2)::timestamptz)) / 86400.0) >= 1"
        );
    }

    #[test]
    fn shim_erp_timefmt() {
        let (s, _) = translate("SELECT erp_timefmt(m / 60, m % 60)", Dialect::Sqlite);
        assert_eq!(s, "SELECT printf('%02d:%02d', m / 60, m % 60)");
        let (p, _) = translate("SELECT erp_timefmt(m / 60, m % 60)", Dialect::Postgres);
        assert_eq!(
            p,
            "SELECT (lpad((m / 60)::text, 2, '0') || ':' || lpad((m % 60)::text, 2, '0'))"
        );
    }

    #[test]
    fn shim_erp_date_funcs_distinguish_similar_prefixes() {
        // erp_date / erp_dateadd / erp_datediff_days comparten prefijo: el guard `next_is_ident`
        // garantiza que se elige el nombre correcto sin depender del orden del array.
        let (s, _) = translate(
            "SELECT erp_date(:x), erp_dateadd(:x, 1, 'days'), erp_datediff_days(:x, :y)",
            Dialect::Sqlite,
        );
        assert_eq!(
            s,
            "SELECT date(?1), datetime(?1, '+' || (1) || ' ' || 'days'), (julianday(?1) - julianday(?2))"
        );
    }

    #[tokio::test]
    async fn availability_shape_roundtrip_sqlite() {
        // Reproduce la forma real de appointments/availability_*: settings + cita + filtro de
        // solape con erp_dt/erp_dateadd, día de semana con erp_dow_mon0 y formato con erp_timefmt.
        // Verifica que el SQL migrado traduce a SQLite VÁLIDO y con la semántica esperada.
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        db.execute_batch(
            "CREATE TABLE appt (id TEXT, hub_id TEXT, start_datetime TEXT, end_datetime TEXT, is_deleted INTEGER);",
        )
        .await
        .unwrap();
        // Cita 2026-06-15 (lunes) 10:00–11:00.
        db.execute(
            "INSERT INTO appt (id, hub_id, start_datetime, end_datetime, is_deleted) \
             VALUES (:id, :h, :s, :e, 0)",
            &params(json!({
                "id":"a1","h":"h1",
                "s":"2026-06-15T10:00:00","e":"2026-06-15T11:00:00"
            })),
        )
        .await
        .unwrap();
        // Candidata 10:30–11:30 solapa; ventana de antelación 60 min desde :now.
        let q = db
            .query(
                "SELECT erp_dow_mon0(:date) AS dow, \
                        erp_timefmt(10, 30) AS t, \
                        EXISTS ( \
                          SELECT 1 FROM appt a \
                          WHERE a.hub_id = :h AND a.is_deleted = 0 \
                            AND erp_dt(a.start_datetime) < erp_dt(:cand_end) \
                            AND erp_dt(a.end_datetime) > erp_dt(:cand_start) \
                        ) AS overlaps, \
                        (erp_dt(:cand_start) >= erp_dateadd(:now, 60, 'minutes')) AS notice_ok",
                &params(json!({
                    "date":"2026-06-15","h":"h1",
                    "cand_start":"2026-06-15T10:30:00","cand_end":"2026-06-15T11:30:00",
                    "now":"2026-06-15T08:00:00"
                })),
            )
            .await
            .unwrap();
        assert_eq!(q.rows[0]["dow"], json!(0), "2026-06-15 es lunes → 0");
        assert_eq!(q.rows[0]["t"], json!("10:30"));
        assert_eq!(q.rows[0]["overlaps"], json!(1), "10:30–11:30 solapa con 10:00–11:00");
        assert_eq!(q.rows[0]["notice_ok"], json!(1), "10:30 está ≥ 08:00+60min");
    }

    #[tokio::test]
    async fn erp_dow_timefmt_roundtrip_sqlite() {
        // Verifica de extremo a extremo en SQLite real: día de la semana 0=lunes y formato HH:MM.
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        // 2026-06-15 es lunes → erp_dow_mon0 = 0. 8*60+5 = 485 min → '08:05'.
        let q = db
            .query(
                "SELECT erp_dow_mon0(:d) AS dow, erp_timefmt(485 / 60, 485 % 60) AS t",
                &params(json!({ "d": "2026-06-15" })),
            )
            .await
            .unwrap();
        assert_eq!(q.rows[0]["dow"], json!(0));
        assert_eq!(q.rows[0]["t"], json!("08:05"));
    }

    // ── shim de normalización de tipos en DDL (ADR-0007 §4b) ──────────────────────────────────

    #[test]
    fn ddl_types_sqlite_identity() {
        let ddl = "CREATE TABLE t (id TEXT PRIMARY KEY, qty INTEGER, weight REAL, blob BLOB)";
        assert_eq!(shim_ddl_types(ddl, Dialect::Sqlite), ddl);
    }

    #[test]
    fn ddl_types_postgres_mapping() {
        let ddl = "CREATE TABLE t (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, qty INTEGER, \
                   amount_cents INTEGER, weight REAL, raw BLOB)";
        let out = shim_ddl_types(ddl, Dialect::Postgres);
        assert_eq!(
            out,
            "CREATE TABLE t (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, qty BIGINT, \
             amount_cents BIGINT, weight DOUBLE PRECISION, raw BYTEA)"
        );
    }

    #[test]
    fn ddl_types_do_not_touch_column_names_or_literals() {
        // Una columna llamada `text` (no tipo) ni un literal `'INTEGER'` deben tocarse: sólo el
        // token de tipo en posición de tipo. Nuestro shim reescribe cualquier palabra-tipo fuera
        // de literales; comprobamos que respeta literales y mayúsculas/minúsculas mixtas.
        let ddl = "CREATE TABLE t (note TEXT DEFAULT 'an INTEGER value', flag integer)";
        let out = shim_ddl_types(ddl, Dialect::Postgres);
        assert_eq!(out, "CREATE TABLE t (note TEXT DEFAULT 'an INTEGER value', flag BIGINT)");
    }

    // ── roundtrip SQLite REAL con tipos portables + función-puente ────────────────────────────

    #[tokio::test]
    async fn portable_ddl_and_bridge_fn_roundtrip_sqlite() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        // DDL portable: TEXT/INTEGER (dinero en céntimos, booleano 0/1) → identidad en SQLite.
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

    // ── selección de driver por target (conexión, no traducción) ──────────────────────────────

    #[tokio::test]
    async fn dialect_selected_by_adapter() {
        // El target lo decide el despliegue vía el adaptador (lite→SQLite). Postgres se cubre en
        // los tests `#[ignore]` que requieren DATABASE_URL.
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        assert_eq!(db.dialect(), Dialect::Sqlite);
    }

    // El mismo SQL portable normaliza distinto por dialecto: prueba textual emparejada (Postgres
    // no necesita estar arrancado).
    #[test]
    fn same_portable_sql_normalizes_per_dialect() {
        let sql = "INSERT INTO t (n, ts) VALUES (erp_pad(:seq, 4), erp_now())";
        let (sqlite, _) = translate(sql, Dialect::Sqlite);
        let (pg, _) = translate(sql, Dialect::Postgres);
        assert_eq!(sqlite, "INSERT INTO t (n, ts) VALUES (printf('%0*d', 4, ?1), CURRENT_TIMESTAMP)");
        assert_eq!(pg, "INSERT INTO t (n, ts) VALUES (lpad(($1)::text, 4, '0'), now())");
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

    // §8/§9 — decode of the fiscal/money Postgres types. Inserts literals (not the param
    // path) so this isolates `pg_cell`'s decode arms. Requires a real Postgres.
    #[tokio::test]
    #[ignore = "requires a real Postgres via DATABASE_URL"]
    async fn pg_fiscal_types_roundtrip() {
        let url = std::env::var("DATABASE_URL").expect("set DATABASE_URL");
        let db = PgAdapter::connect(&url).await.expect("connect to postgres");
        db.execute_batch(
            "DROP TABLE IF EXISTS erplora_pg_fiscal; \
             CREATE TABLE erplora_pg_fiscal ( \
                 amount NUMERIC, ts TIMESTAMPTZ, d DATE, uid UUID, meta JSONB \
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
        // NUMERIC keeps exact precision as a string (never f64).
        assert_eq!(r["amount"], json!("12345.67"));
        // TIMESTAMPTZ → RFC-3339 (UTC).
        assert_eq!(r["ts"], json!("2026-06-13T10:30:00+00:00"));
        assert_eq!(r["d"], json!("2026-06-13"));
        assert_eq!(r["uid"], json!("00000000-0000-0000-0000-000000000001"));
        // JSONB → parsed value, verbatim.
        assert_eq!(r["meta"], json!({"a": 1}));
    }
}
