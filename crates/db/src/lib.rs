//! erplora-db — abstracción de base de datos para hub-next (ARQUITECTURA.md §8).
//!
//! Expone el trait [`DatabaseAdapter`] (el mismo contrato para SQLite local y
//! Postgres/Aurora cloud) y dos implementaciones:
//! - [`SqliteAdapter`] — siempre disponible (local / Tauri).
//! - [`PgAdapter`] — backend Postgres (cloud / Aurora), **detrás de la feature
//!   `postgres`** para no obligar a compilar el cliente Postgres a quien no lo use.
//!
//! - Los parámetros son **nombrados** (`:nombre`) y se pasan como un `serde_json::Map`,
//!   igual que el payload que llega del SDK. Solo se enlazan los `:nombre` que el SQL usa.
//! - Las filas se devuelven como `serde_json::Value` (array de objetos) listas para el SDK.

use std::sync::Mutex;

use rusqlite::types::Value as SqlValue;
use rusqlite::{Connection, ToSql};
use serde_json::{Map, Value as Json};

/// Parámetros nombrados de una sentencia (`:clave` → valor JSON).
pub type Params = Map<String, Json>;

/// Dialecto SQL del backend activo.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Dialect {
    Sqlite,
    Postgres,
}

#[derive(Debug, thiserror::Error)]
pub enum DbError {
    #[error("sqlite: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("error de bloqueo de la conexión (mutex envenenado)")]
    Lock,
    /// Error del backend Postgres (solo con la feature `postgres`).
    #[cfg(feature = "postgres")]
    #[error("postgres: {0}")]
    Postgres(#[from] postgres::Error),
}

/// Contrato común para todos los backends de base de datos.
///
/// El runtime (`erplora-runtime`) solo conoce este trait; no sabe si por debajo hay SQLite
/// (local/Tauri) o Postgres (cloud/Aurora). Misma interfaz, distinta implementación.
pub trait DatabaseAdapter: Send + Sync {
    fn dialect(&self) -> Dialect;

    /// Ejecuta una sentencia de escritura. Devuelve filas afectadas.
    fn execute(&self, sql: &str, params: &Params) -> Result<u64, DbError>;

    /// Ejecuta varias sentencias en una **transacción** (todo o nada). Devuelve filas afectadas.
    fn execute_tx(&self, ops: &[(String, Params)]) -> Result<u64, DbError>;

    /// Ejecuta una consulta y devuelve las filas como objetos JSON.
    fn query(&self, sql: &str, params: &Params) -> Result<Vec<Json>, DbError>;

    /// Ejecuta un script SQL con múltiples sentencias (para migraciones).
    fn execute_batch(&self, sql: &str) -> Result<(), DbError>;
}

/// Backend SQLite (local / Tauri). Envuelve la conexión en un `Mutex` para ser `Send+Sync`.
pub struct SqliteAdapter {
    conn: Mutex<Connection>,
}

impl SqliteAdapter {
    /// Abre (o crea) una base de datos SQLite en `path`.
    pub fn open(path: &str) -> Result<Self, DbError> {
        let conn = Connection::open(path)?;
        Ok(Self { conn: Mutex::new(conn) })
    }

    /// Base de datos en memoria (para tests / ejemplos).
    pub fn open_in_memory() -> Result<Self, DbError> {
        let conn = Connection::open_in_memory()?;
        Ok(Self { conn: Mutex::new(conn) })
    }
}

impl DatabaseAdapter for SqliteAdapter {
    fn dialect(&self) -> Dialect {
        Dialect::Sqlite
    }

    fn execute(&self, sql: &str, params: &Params) -> Result<u64, DbError> {
        let conn = self.conn.lock().map_err(|_| DbError::Lock)?;
        run_exec(&conn, sql, params)
    }

    fn execute_tx(&self, ops: &[(String, Params)]) -> Result<u64, DbError> {
        let mut conn = self.conn.lock().map_err(|_| DbError::Lock)?;
        let tx = conn.transaction()?;
        let mut total = 0u64;
        for (sql, params) in ops {
            total += run_exec(&tx, sql, params)?; // &Transaction → &Connection (deref coerción)
        }
        tx.commit()?;
        Ok(total)
    }

    fn query(&self, sql: &str, params: &Params) -> Result<Vec<Json>, DbError> {
        let conn = self.conn.lock().map_err(|_| DbError::Lock)?;
        run_query(&conn, sql, params)
    }

    fn execute_batch(&self, sql: &str) -> Result<(), DbError> {
        let conn = self.conn.lock().map_err(|_| DbError::Lock)?;
        conn.execute_batch(sql)?;
        Ok(())
    }
}

// ── helpers internos ───────────────────────────────────────────────────────────────────

/// Recolecta los parámetros nombrados que el statement realmente usa, como pares
/// `(":nombre", valor)` listos para la API estable de rusqlite. Los `:nombre` que el SQL
/// no use se ignoran; los que el SQL use y no estén en `params` → NULL.
fn collect_params(stmt: &rusqlite::Statement<'_>, params: &Params) -> Vec<(String, SqlValue)> {
    let count = stmt.parameter_count();
    (1..=count)
        .filter_map(|i| stmt.parameter_name(i)) // p. ej. ":hub_id" (incluye el ':')
        .map(|full| {
            let key = &full[1..]; // sin ':'
            (full.to_string(), json_to_sql(params.get(key)))
        })
        .collect()
}

/// Vista `&[(&str, &dyn ToSql)]` sobre los pares recolectados (lo que espera rusqlite).
fn as_named<'a>(pairs: &'a [(String, SqlValue)]) -> Vec<(&'a str, &'a dyn ToSql)> {
    pairs.iter().map(|(k, v)| (k.as_str(), v as &dyn ToSql)).collect()
}

fn run_exec(conn: &Connection, sql: &str, params: &Params) -> Result<u64, DbError> {
    let mut stmt = conn.prepare(sql)?;
    let pairs = collect_params(&stmt, params);
    let n = stmt.execute(as_named(&pairs).as_slice())?;
    Ok(n as u64)
}

fn run_query(conn: &Connection, sql: &str, params: &Params) -> Result<Vec<Json>, DbError> {
    let mut stmt = conn.prepare(sql)?;
    let columns: Vec<String> = stmt.column_names().iter().map(|s| s.to_string()).collect();
    let pairs = collect_params(&stmt, params);

    let mut out = Vec::new();
    let mut rows = stmt.query(as_named(&pairs).as_slice())?;
    while let Some(row) = rows.next()? {
        let mut obj = Map::new();
        for (i, col) in columns.iter().enumerate() {
            let val: SqlValue = row.get(i)?;
            obj.insert(col.clone(), sql_to_json(val));
        }
        out.push(Json::Object(obj));
    }
    Ok(out)
}

/// JSON → valor SQLite enlazable.
fn json_to_sql(value: Option<&Json>) -> SqlValue {
    match value {
        None | Some(Json::Null) => SqlValue::Null,
        Some(Json::Bool(b)) => SqlValue::Integer(i64::from(*b)),
        Some(Json::Number(n)) => {
            if let Some(i) = n.as_i64() {
                SqlValue::Integer(i)
            } else if let Some(u) = n.as_u64() {
                SqlValue::Integer(u as i64)
            } else {
                SqlValue::Real(n.as_f64().unwrap_or(0.0))
            }
        }
        Some(Json::String(s)) => SqlValue::Text(s.clone()),
        Some(other) => SqlValue::Text(other.to_string()), // arrays/objetos → JSON string
    }
}

/// Valor SQLite → JSON.
fn sql_to_json(value: SqlValue) -> Json {
    match value {
        SqlValue::Null => Json::Null,
        SqlValue::Integer(i) => Json::from(i),
        SqlValue::Real(f) => Json::from(f),
        SqlValue::Text(s) => Json::String(s),
        SqlValue::Blob(b) => Json::String(String::from_utf8_lossy(&b).into_owned()),
    }
}

// ── traductor de placeholders `:nombre` → `$n` (Postgres) ────────────────────────────────

/// Traduce los parámetros nombrados `:nombre` (estilo SQLite, el que usan los
/// módulos) a placeholders posicionales `$n` que entiende el crate `postgres`
/// (rust-postgres usa `$1, $2, …`).
///
/// Reglas:
/// - `:ident` (alfanumérico/`_`) pasa a `$n`, donde `n` respeta el orden de
///   primera aparición; un nombre repetido **reusa** su índice anterior (por eso
///   el `Vec<String>` devuelto lista cada nombre **una sola vez**, en orden de
///   enlace).
/// - `::` es el operador de *cast* de Postgres, nunca un parámetro: se emite tal
///   cual y se salta.
/// - Un `:` dentro de un literal entre comillas simples se deja intacto.
///
/// Devuelve el SQL reescrito y la lista ordenada (sin duplicados) de nombres,
/// para que el llamador construya el array de argumentos `$n` en el orden correcto.
///
/// Siempre se compila (sus tests corren sin la feature `postgres`); solo el
/// `PgAdapter` que lo consume está detrás de la feature, de ahí `allow(dead_code)`.
#[allow(dead_code)]
pub(crate) fn translate_named_to_positional(sql: &str) -> (String, Vec<String>) {
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
            // `::` es el operador de cast de Postgres, no un parámetro.
            if i + 1 < bytes.len() && bytes[i + 1] == b':' {
                out.push_str("::");
                i += 2;
                continue;
            }
            // Posible `:nombre`.
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
                out.push('$');
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

// ── backend Postgres (cloud / Aurora) — detrás de la feature `postgres` ──────────────────

#[cfg(feature = "postgres")]
mod pg {
    use super::{translate_named_to_positional, DatabaseAdapter, DbError, Dialect, Params};
    use postgres::types::{ToSql, Type};
    use postgres::{Client, NoTls, Row};
    use serde_json::{Map, Value as Json};
    use std::sync::Mutex;

    /// Un valor de parámetro bajado a un tipo Rust concreto que el crate
    /// `postgres` sabe enlazar. JSON → text / i64 / f64 / bool / null.
    enum PgVal {
        Null,
        Bool(bool),
        Int(i64),
        Float(f64),
        Text(String),
    }

    impl PgVal {
        /// Baja un valor JSON. Arrays/objetos se serializan a su forma textual
        /// (se mantiene simple: los módulos solo usan parámetros escalares).
        fn from_json(v: Option<&Json>) -> PgVal {
            match v {
                None | Some(Json::Null) => PgVal::Null,
                Some(Json::Bool(b)) => PgVal::Bool(*b),
                Some(Json::Number(n)) => {
                    if let Some(i) = n.as_i64() {
                        PgVal::Int(i)
                    } else if let Some(u) = n.as_u64() {
                        PgVal::Int(u as i64)
                    } else {
                        PgVal::Float(n.as_f64().unwrap_or(0.0))
                    }
                }
                Some(Json::String(s)) => PgVal::Text(s.clone()),
                Some(other) => PgVal::Text(other.to_string()),
            }
        }

        /// Presta el valor como `&dyn ToSql` para el array posicional `$n`.
        fn as_to_sql(&self) -> &(dyn ToSql + Sync) {
            match self {
                PgVal::Null => &Option::<i64>::None,
                PgVal::Bool(b) => b,
                PgVal::Int(i) => i,
                PgVal::Float(f) => f,
                PgVal::Text(s) => s,
            }
        }
    }

    /// Construye la lista ordenada de `PgVal` para los nombres que el SQL usa.
    /// Los nombres ausentes se enlazan como NULL.
    fn bind_pg_values(names: &[String], params: &Params) -> Vec<PgVal> {
        names.iter().map(|n| PgVal::from_json(params.get(n))).collect()
    }

    /// Convierte una celda de columna Postgres a JSON.
    ///
    /// Los tipos de columna en Postgres son variados, así que usamos un enfoque
    /// **robusto dirigido por tipo**: hacemos `match` sobre el `Type` de la
    /// columna y extraemos con el getter correspondiente, tratando un NULL SQL
    /// (o un fallo de decodificación) como JSON `null`. Cubrimos los tipos que
    /// usan los módulos: `int2/int4/int8` → entero, `float4/float8` → número,
    /// `bool` → booleano, y todo lo demás (text, varchar, uuid, timestamps,
    /// json, …) → string. Lo que no se pueda decodificar cae a `null`.
    fn cell_to_json(row: &Row, idx: usize, ty: &Type) -> Json {
        match *ty {
            Type::BOOL => row
                .try_get::<_, Option<bool>>(idx)
                .ok()
                .flatten()
                .map(Json::from)
                .unwrap_or(Json::Null),
            Type::INT2 => row
                .try_get::<_, Option<i16>>(idx)
                .ok()
                .flatten()
                .map(|v| Json::from(v as i64))
                .unwrap_or(Json::Null),
            Type::INT4 => row
                .try_get::<_, Option<i32>>(idx)
                .ok()
                .flatten()
                .map(|v| Json::from(v as i64))
                .unwrap_or(Json::Null),
            Type::INT8 => row
                .try_get::<_, Option<i64>>(idx)
                .ok()
                .flatten()
                .map(Json::from)
                .unwrap_or(Json::Null),
            Type::FLOAT4 => row
                .try_get::<_, Option<f32>>(idx)
                .ok()
                .flatten()
                .map(|v| Json::from(v as f64))
                .unwrap_or(Json::Null),
            Type::FLOAT8 => row
                .try_get::<_, Option<f64>>(idx)
                .ok()
                .flatten()
                .map(Json::from)
                .unwrap_or(Json::Null),
            // Todo lo demás (text-like): leer como String, NULL si no se puede.
            _ => row
                .try_get::<_, Option<String>>(idx)
                .ok()
                .flatten()
                .map(Json::String)
                .unwrap_or(Json::Null),
        }
    }

    /// Backend Postgres (cloud / Aurora). Envuelve un [`Client`] síncrono de
    /// rust-postgres en un `Mutex`; habla [`Dialect::Postgres`].
    pub struct PgAdapter {
        client: Mutex<Client>,
    }

    impl PgAdapter {
        /// Conecta con un connection string / URL estándar de Postgres, p. ej.
        /// `postgres://user:pass@host:5432/dbname`. No configura TLS (`NoTls`);
        /// envuelve con un conector TLS en el call site si hace falta (Aurora).
        pub fn connect(conn_str: &str) -> Result<Self, DbError> {
            let client = Client::connect(conn_str, NoTls)?;
            Ok(Self { client: Mutex::new(client) })
        }
    }

    impl DatabaseAdapter for PgAdapter {
        fn dialect(&self) -> Dialect {
            Dialect::Postgres
        }

        fn execute(&self, sql: &str, params: &Params) -> Result<u64, DbError> {
            let mut client = self.client.lock().map_err(|_| DbError::Lock)?;
            let (tsql, names) = translate_named_to_positional(sql);
            let vals = bind_pg_values(&names, params);
            let refs: Vec<&(dyn ToSql + Sync)> = vals.iter().map(|v| v.as_to_sql()).collect();
            let n = client.execute(tsql.as_str(), refs.as_slice())?;
            Ok(n)
        }

        fn execute_tx(&self, ops: &[(String, Params)]) -> Result<u64, DbError> {
            let mut client = self.client.lock().map_err(|_| DbError::Lock)?;
            let mut tx = client.transaction()?;
            let mut total = 0u64;
            for (sql, params) in ops {
                let (tsql, names) = translate_named_to_positional(sql);
                let vals = bind_pg_values(&names, params);
                let refs: Vec<&(dyn ToSql + Sync)> = vals.iter().map(|v| v.as_to_sql()).collect();
                total += tx.execute(tsql.as_str(), refs.as_slice())?;
            }
            tx.commit()?;
            Ok(total)
        }

        fn query(&self, sql: &str, params: &Params) -> Result<Vec<Json>, DbError> {
            let mut client = self.client.lock().map_err(|_| DbError::Lock)?;
            let (tsql, names) = translate_named_to_positional(sql);
            let vals = bind_pg_values(&names, params);
            let refs: Vec<&(dyn ToSql + Sync)> = vals.iter().map(|v| v.as_to_sql()).collect();
            let rows = client.query(tsql.as_str(), refs.as_slice())?;
            let mut out = Vec::with_capacity(rows.len());
            for row in &rows {
                let mut obj = Map::new();
                for (idx, col) in row.columns().iter().enumerate() {
                    obj.insert(col.name().to_string(), cell_to_json(row, idx, col.type_()));
                }
                out.push(Json::Object(obj));
            }
            Ok(out)
        }

        fn execute_batch(&self, sql: &str) -> Result<(), DbError> {
            let mut client = self.client.lock().map_err(|_| DbError::Lock)?;
            client.batch_execute(sql)?;
            Ok(())
        }
    }
}

#[cfg(feature = "postgres")]
pub use pg::PgAdapter;

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn params(v: Json) -> Params {
        v.as_object().cloned().unwrap_or_default()
    }

    #[test]
    fn create_insert_query_roundtrip() {
        let db = SqliteAdapter::open_in_memory().unwrap();
        db.execute_batch(
            "CREATE TABLE t (id TEXT PRIMARY KEY, hub_id TEXT, name TEXT, price REAL);",
        )
        .unwrap();

        let n = db
            .execute(
                "INSERT INTO t (id, hub_id, name, price) VALUES (:id, :hub_id, :name, :price)",
                &params(json!({ "id": "a", "hub_id": "h1", "name": "Café", "price": 4.5 })),
            )
            .unwrap();
        assert_eq!(n, 1);

        let rows = db
            .query(
                "SELECT id, name, price FROM t WHERE hub_id = :hub_id",
                &params(json!({ "hub_id": "h1" })),
            )
            .unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["name"], json!("Café"));
        assert_eq!(rows[0]["price"], json!(4.5));
    }

    #[test]
    fn tx_is_atomic() {
        let db = SqliteAdapter::open_in_memory().unwrap();
        db.execute_batch("CREATE TABLE t (id TEXT PRIMARY KEY);").unwrap();
        let res = db.execute_tx(&[
            ("INSERT INTO t (id) VALUES (:id)".into(), params(json!({"id":"x"}))),
            ("INSERT INTO t (id) VALUES (:id)".into(), params(json!({"id":"x"}))),
        ]);
        assert!(res.is_err());
        let rows = db.query("SELECT id FROM t", &Params::new()).unwrap();
        assert_eq!(rows.len(), 0, "la transacción debe revertir por completo");
    }

    // ── traductor `:nombre` → `$n` (sin DB, sin feature) ─────────────────────────────────

    #[test]
    fn pg_translate_basic() {
        let (sql, names) =
            translate_named_to_positional("SELECT * FROM t WHERE a = :a AND b = :b");
        assert_eq!(sql, "SELECT * FROM t WHERE a = $1 AND b = $2");
        assert_eq!(names, vec!["a", "b"]);
    }

    #[test]
    fn pg_translate_repeated_reuses_index() {
        // Un nombre repetido reusa su $n y aparece una sola vez en `names`.
        let (sql, names) = translate_named_to_positional("SELECT :x, :x, :y");
        assert_eq!(sql, "SELECT $1, $1, $2");
        assert_eq!(names, vec!["x", "y"]);
    }

    #[test]
    fn pg_translate_keeps_cast_operator() {
        // `::int` es un cast, no un parámetro: intacto. El `:id` real sí se traduce.
        let (sql, names) =
            translate_named_to_positional("SELECT id::int FROM t WHERE id = :id");
        assert_eq!(sql, "SELECT id::int FROM t WHERE id = $1");
        assert_eq!(names, vec!["id"]);
    }

    #[test]
    fn pg_translate_cast_right_after_param() {
        // Parámetro seguido inmediatamente de cast: `:amount::numeric`.
        let (sql, names) = translate_named_to_positional("SELECT :amount::numeric");
        assert_eq!(sql, "SELECT $1::numeric");
        assert_eq!(names, vec!["amount"]);
    }

    #[test]
    fn pg_translate_ignores_colon_in_string_literal() {
        // Un `:` dentro de un literal entre comillas simples no es parámetro.
        let (sql, names) =
            translate_named_to_positional("SELECT ':notparam' AS s, :real AS r");
        assert_eq!(sql, "SELECT ':notparam' AS s, $1 AS r");
        assert_eq!(names, vec!["real"]);
    }

    #[test]
    fn pg_translate_returns_name_order() {
        // El orden de primera aparición se preserva entre repeticiones y casts.
        let (sql, names) =
            translate_named_to_positional("SELECT :b, :a, :b::text, ':c', :a");
        assert_eq!(sql, "SELECT $1, $2, $1::text, ':c', $2");
        assert_eq!(names, vec!["b", "a"]);
    }

    // ── tests de integración Postgres (requieren DB real) ────────────────────────────────
    //
    // Necesitan un Postgres accesible vía $DATABASE_URL, así que van detrás de la
    // feature `postgres` Y de `#[ignore]` (desactivados por defecto). Para correrlos:
    //
    //   DATABASE_URL=postgres://user:pass@localhost:5432/erplora_test \
    //     cargo test -p erplora-db --features postgres -- --ignored
    #[cfg(feature = "postgres")]
    mod pg_integration {
        use super::*;

        fn adapter() -> PgAdapter {
            let url = std::env::var("DATABASE_URL")
                .expect("define DATABASE_URL para correr los tests ignorados de pg");
            PgAdapter::connect(&url).expect("conectar a postgres")
        }

        #[test]
        #[ignore = "requiere un Postgres real vía DATABASE_URL"]
        fn pg_roundtrip() {
            let db = adapter();
            assert_eq!(db.dialect(), Dialect::Postgres);
            db.execute_batch(
                "DROP TABLE IF EXISTS erplora_pg_test; \
                 CREATE TABLE erplora_pg_test (id BIGINT, name TEXT, ok BOOLEAN, price FLOAT8)",
            )
            .unwrap();
            let n = db
                .execute(
                    "INSERT INTO erplora_pg_test (id, name, ok, price) \
                     VALUES (:id, :name, :ok, :price)",
                    &params(json!({"id": 1, "name": "alice", "ok": true, "price": 4.5})),
                )
                .unwrap();
            assert_eq!(n, 1);
            let rows = db
                .query(
                    "SELECT id, name, ok, price FROM erplora_pg_test WHERE id = :id",
                    &params(json!({"id": 1})),
                )
                .unwrap();
            assert_eq!(rows.len(), 1);
            assert_eq!(rows[0]["id"], json!(1));
            assert_eq!(rows[0]["name"], json!("alice"));
            assert_eq!(rows[0]["ok"], json!(true));
            assert_eq!(rows[0]["price"], json!(4.5));
        }
    }
}
