//! Arnés compartido de los tests de paridad SQLite↔Postgres (`tests/parity.rs`).
//!
//! Vive en `tests/parity_support/mod.rs` (no en `tests/parity_support.rs`) **a propósito**: Cargo
//! compila cada `tests/*.rs` como su propio binario de test, pero NO los submódulos en subcarpetas.
//! Así esto es código de soporte, no un binario de test suelto.
//!
//! Responsabilidades:
//! - localizar la `modules-workspace` del monorepo y leer el SQL **real** de cada módulo
//!   (`migrations/<dialect>/*.sql`, `queries/*.sql`, `commands/*.sql`);
//! - abrir un `SqliteAdapter` en memoria y, **si hay entorno**, un `PgAdapter` contra un Postgres
//!   real (`ERPLORA_TEST_PG_URL` / `DATABASE_URL`), con un schema aislado por test;
//! - ejecutar el mismo command/query en ambos y comparar `QueryResult` fila a fila tras normalizar
//!   los valores no deterministas.

use std::path::PathBuf;
use std::sync::atomic::{AtomicU32, Ordering};

use erplora_db::{DatabaseAdapter, Params, PgAdapter, QueryResult, SqliteAdapter};
use serde_json::{json, Value as Json};

/// `Params` desde un `serde_json::json!({...})`.
pub fn params(v: Json) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

/// Contador para dar a cada test su propio schema Postgres aislado (los tests corren en paralelo,
/// comparten el mismo Postgres → necesitan namespaces disjuntos para no pisarse las tablas).
static PG_SCHEMA_SEQ: AtomicU32 = AtomicU32::new(0);

/// Inserta `options=-c search_path=<schema>` en un DSN de Postgres, para que cada conexión del pool
/// nazca con el `search_path` apuntando al schema aislado del test (evita el problema de `SET
/// search_path` connection-local sobre un pool multi-conexión). El espacio de `-c search_path` se
/// codifica como `%20` en la query string del URL.
fn with_search_path(url: &str, schema: &str) -> String {
    let opt = format!("options=-c%20search_path%3D{schema}");
    if url.contains('?') {
        format!("{url}&{opt}")
    } else {
        format!("{url}?{opt}")
    }
}

/// Raíz de la `modules-workspace` (donde vive el source de cada módulo declarativo).
/// `CARGO_MANIFEST_DIR` = `hub/crates/db`; subimos a la raíz del monorepo.
fn modules_root() -> PathBuf {
    // hub/crates/db → hub/crates → hub → <monorepo>
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let monorepo = here.parent().unwrap().parent().unwrap().parent().unwrap();
    let p = monorepo.join("modules-workspace").join("modules");
    assert!(
        p.is_dir(),
        "no encuentro la modules-workspace en {p:?}; los tests de paridad leen el SQL real de los \
         módulos. Ejecuta desde el monorepo ERPlora."
    );
    p
}

/// Lee un fichero SQL del módulo y falla con un mensaje claro si no existe.
fn read_sql(module: &str, rel: &str) -> String {
    let path = modules_root().join(module).join(rel);
    std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("no pude leer {path:?}: {e}"))
}

/// Los dos backends bajo prueba. `pg` es `None` cuando no hay Postgres en el entorno: en ese caso la
/// paridad se degrada a "solo SQLite" y se imprime un aviso (honesto sobre lo que no se pudo correr).
pub struct Backends {
    pub sqlite: SqliteAdapter,
    pub pg: Option<PgAdapter>,
    /// Schema Postgres aislado de este test (search_path), para correr en paralelo sin colisiones.
    /// Ya va inyectado en el DSN del pool (ver `connect`); se conserva para diagnóstico/legibilidad.
    #[allow(dead_code)]
    pg_schema: Option<String>,
}

impl Backends {
    /// Abre SQLite en memoria + (si hay URL) un Postgres real con un schema dedicado.
    pub async fn connect() -> Self {
        let sqlite = SqliteAdapter::open_in_memory().await.expect("sqlite in-memory");

        let url = std::env::var("ERPLORA_TEST_PG_URL")
            .or_else(|_| std::env::var("DATABASE_URL"))
            .ok();

        let (pg, pg_schema) = match url {
            Some(url) => {
                // Schema aislado por test (los tests corren en paralelo sobre el MISMO Postgres).
                let n = PG_SCHEMA_SEQ.fetch_add(1, Ordering::SeqCst);
                let schema = format!("parity_{}_{}", std::process::id(), n);

                // 1) Conexión base sólo para crear el schema.
                let base = PgAdapter::connect(&url)
                    .await
                    .expect("ERPLORA_TEST_PG_URL/DATABASE_URL apunta a un Postgres no accesible");
                base.execute_batch(&format!(
                    "DROP SCHEMA IF EXISTS {schema} CASCADE; CREATE SCHEMA {schema};"
                ))
                .await
                .expect("crear schema de test en Postgres");

                // 2) Reconectar con el `search_path` en el DSN (libpq `options=-c search_path=…`),
                //    para que TODA conexión del pool nazca apuntando al schema del test. Así no
                //    dependemos de `SET search_path` por-conexión (el pool tiene varias).
                let scoped_url = with_search_path(&url, &schema);
                let pg = PgAdapter::connect(&scoped_url)
                    .await
                    .expect("reconectar a Postgres con search_path scoped");
                (Some(pg), Some(schema))
            }
            None => {
                eprintln!(
                    "⚠️  paridad: sin ERPLORA_TEST_PG_URL/DATABASE_URL → se corre SOLO la rama \
                     SQLite (Postgres PENDIENTE DE ENTORNO). Levanta un Postgres y reexporta la URL \
                     para validar la paridad completa."
                );
                (None, None)
            }
        };

        Self { sqlite, pg, pg_schema }
    }

    /// `true` si la rama Postgres está activa (hay un Postgres real conectado).
    #[allow(dead_code)] // helper público del arnés; no todos los tests lo consultan.
    pub fn has_pg(&self) -> bool {
        self.pg.is_some()
    }

    /// Aplica TODAS las migraciones reales del módulo, **cada motor con su propio dialecto**
    /// (`migrations/sqlite/*.sql` en SQLite, `migrations/postgres/*.sql` en Postgres), en orden
    /// lexicográfico de nombre de fichero (001_, 002_, …) — igual que el instalador del runtime.
    pub async fn migrate(&self, module: &str) {
        // El `search_path` va en el DSN (ver `connect`), así que toda conexión del pool ya apunta al
        // schema aislado del test: las tablas caen en el namespace correcto sin `SET` por-op.
        self.apply_migrations(module, "sqlite").await;
        if self.pg.is_some() {
            self.apply_migrations(module, "postgres").await;
        }
    }

    async fn apply_migrations(&self, module: &str, dialect: &str) {
        let dir = modules_root().join(module).join("migrations").join(dialect);
        let mut files: Vec<PathBuf> = std::fs::read_dir(&dir)
            .unwrap_or_else(|e| panic!("no pude listar {dir:?}: {e}"))
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.extension().map(|x| x == "sql").unwrap_or(false))
            .collect();
        files.sort();
        assert!(!files.is_empty(), "el módulo {module} no tiene migraciones {dialect} en {dir:?}");

        for f in files {
            let sql = std::fs::read_to_string(&f).unwrap_or_else(|e| panic!("leer {f:?}: {e}"));
            match dialect {
                "sqlite" => {
                    self.sqlite
                        .execute_batch(&sql)
                        .await
                        .unwrap_or_else(|e| panic!("migración SQLite {f:?} falló: {e:?}"));
                }
                "postgres" => {
                    let pg = self.pg.as_ref().unwrap();
                    pg.execute_batch(&sql)
                        .await
                        .unwrap_or_else(|e| panic!("migración Postgres {f:?} falló: {e:?}"));
                }
                _ => unreachable!(),
            }
        }
    }

    /// Aplica un batch DDL/SQL ad-hoc en SQLite (pasa por `execute_batch` → `shim_ddl_types`).
    pub async fn sqlite_batch(&self, sql: &str) {
        self.sqlite
            .execute_batch(sql)
            .await
            .unwrap_or_else(|e| panic!("SQLite batch falló:\n{sql}\n{e:?}"));
    }

    /// Aplica un batch DDL/SQL ad-hoc en Postgres dentro del schema aislado del test (no-op sin PG).
    pub async fn pg_batch(&self, sql: &str) {
        if let Some(pg) = &self.pg {
            pg.execute_batch(sql)
                .await
                .unwrap_or_else(|e| panic!("Postgres batch falló:\n{sql}\n{e:?}"));
        }
    }

    /// SQL crudo de un command del módulo (`commands/<name>.sql`).
    pub fn command_sql(&self, module: &str, name: &str) -> String {
        read_sql(module, &format!("commands/{name}.sql"))
    }

    /// SQL crudo de una query del módulo (`queries/<name>.sql`).
    pub fn query_sql(&self, module: &str, name: &str) -> String {
        read_sql(module, &format!("queries/{name}.sql"))
    }

    /// Ejecuta un command (write) en **ambos** motores con los mismos params. Aserta que el número de
    /// filas afectadas coincide (un command que afecta N en SQLite debe afectar N en Postgres).
    pub async fn exec_both(&self, sql: &str, payload: Json) {
        let p = params(payload);
        let s = self
            .sqlite
            .execute(sql, &p)
            .await
            .unwrap_or_else(|e| panic!("SQLite execute falló:\n{sql}\nerror: {e:?}"));
        if let Some(pg) = &self.pg {
            let g = pg
                .execute(sql, &p)
                .await
                .unwrap_or_else(|e| panic!("Postgres execute falló:\n{sql}\nerror: {e:?}"));
            assert_eq!(
                s.affected, g.affected,
                "filas afectadas distintas entre motores para:\n{sql}\nsqlite={} postgres={}",
                s.affected, g.affected
            );
        }
    }

    /// Ejecuta un command que se SABE que diverge: SQLite lo acepta, Postgres lo **rechaza**.
    /// Documenta un defecto de portabilidad real del SQL del módulo / del adaptador (ver los
    /// `[REVISAR HUMANO]` del informe). Mantiene la suite verde y honesta: aserta que la divergencia
    /// EXISTE hoy (no la oculta). Devuelve el mensaje de error de Postgres para inspección. Si la
    /// rama Postgres no está activa, sólo comprueba que SQLite lo acepta y avisa.
    ///
    /// `expect_pg_code`: SQLSTATE esperado del error de Postgres (p.ej. "42883" función inexistente,
    /// "42702" referencia ambigua) — fija el fallo concreto para que, cuando el humano arregle el
    /// shim/SQL, este test salte y haya que convertirlo en paridad normal.
    // Sin uso hoy: las 3 divergencias de portabilidad conocidas (42804/42883/42702) están resueltas
    // y sus tests son ahora paridad normal. Se conserva como arnés para fijar futuras divergencias.
    #[allow(dead_code)]
    pub async fn exec_known_divergence(&self, sql: &str, payload: Json, expect_pg_code: &str) {
        let p = params(payload);
        self.sqlite
            .execute(sql, &p)
            .await
            .unwrap_or_else(|e| panic!("SQLite DEBERÍA aceptar este SQL pero falló:\n{sql}\n{e:?}"));
        match &self.pg {
            None => eprintln!(
                "ℹ️  divergencia conocida verificada SOLO en SQLite (Postgres pendiente de entorno): \
                 se esperaba SQLSTATE {expect_pg_code} en Postgres.\n{sql}"
            ),
            Some(pg) => {
                let err = pg.execute(sql, &p).await.expect_err(&format!(
                    "Postgres DEBERÍA rechazar este SQL (divergencia conocida {expect_pg_code}); si \
                     ahora lo acepta, el shim/SQL se arregló → convierte este test en paridad normal.\n{sql}"
                ));
                let msg = format!("{err:?}");
                assert!(
                    msg.contains(expect_pg_code),
                    "Postgres falló con un error DISTINTO al esperado {expect_pg_code}:\n{msg}"
                );
            }
        }
    }

    /// Lanza una query en ambos motores y devuelve los dos `QueryResult` (sqlite, pg?).
    async fn query_both(&self, sql: &str, payload: &Json) -> (QueryResult, Option<QueryResult>) {
        let p = params(payload.clone());
        let s = self
            .sqlite
            .query(sql, &p)
            .await
            .unwrap_or_else(|e| panic!("SQLite query falló:\n{sql}\nerror: {e:?}"));
        let g = if let Some(pg) = &self.pg {
            Some(
                pg.query(sql, &p)
                    .await
                    .unwrap_or_else(|e| panic!("Postgres query falló:\n{sql}\nerror: {e:?}")),
            )
        } else {
            None
        };
        (s, g)
    }
}

/// Un caso de paridad: corre la MISMA query en ambos motores y aserta filas idénticas.
pub struct Case {
    name: String,
    /// Filas ya normalizadas y comparadas (SQLite es la referencia; Postgres debe coincidir).
    rows: Vec<Json>,
}

impl Case {
    pub fn new(name: &str) -> CaseBuilder {
        CaseBuilder { name: name.to_string() }
    }

    /// Aserta que la query devolvió exactamente `n` filas (idéntico en ambos motores ya verificado).
    pub fn assert_rows(self, n: usize) -> Self {
        assert_eq!(
            self.rows.len(),
            n,
            "[{}] esperaba {n} filas, obtuve {}: {:#?}",
            self.name,
            self.rows.len(),
            self.rows
        );
        self
    }

    /// Aserta el valor de una celda `(fila, columna)` (sobre el resultado ya verificado idéntico).
    pub fn assert_cell(self, row: usize, col: &str, expected: Json) -> Self {
        let got = self
            .rows
            .get(row)
            .unwrap_or_else(|| panic!("[{}] no hay fila {row}", self.name))
            .get(col)
            .unwrap_or_else(|| panic!("[{}] fila {row} no tiene columna '{col}'", self.name));
        assert_eq!(
            got, &expected,
            "[{}] celda ({row},{col}): esperaba {expected}, obtuve {got}",
            self.name
        );
        self
    }
}

pub struct CaseBuilder {
    name: String,
}

impl CaseBuilder {
    /// Corre la query en ambos motores y **aserta que el resultado es idéntico fila a fila**.
    /// Devuelve un `Case` con las filas (de SQLite, ya confirmadas iguales a Postgres) para
    /// asertar contenido específico encima.
    pub async fn assert_parity(self, b: &Backends, sql: &str, payload: Json) -> Case {
        let (s, g) = b.query_both(sql, &payload).await;
        let s_rows = normalize_rows(&s.rows);

        if let Some(g) = g {
            let g_rows = normalize_rows(&g.rows);
            assert_eq!(
                s_rows.len(),
                g_rows.len(),
                "[{}] nº de filas distinto: sqlite={} postgres={}\nsql:\n{sql}",
                self.name,
                s_rows.len(),
                g_rows.len()
            );
            for (i, (sr, gr)) in s_rows.iter().zip(g_rows.iter()).enumerate() {
                assert_eq!(
                    sr, gr,
                    "[{}] fila {i} difiere entre motores\nsql:\n{sql}\nsqlite={sr:#?}\npostgres={gr:#?}",
                    self.name
                );
            }
        } else {
            // Sin Postgres: registramos que la mitad de la paridad queda pendiente de entorno.
            eprintln!(
                "ℹ️  [{}] verificado SOLO en SQLite (Postgres pendiente de entorno).",
                self.name
            );
        }

        Case { name: self.name, rows: s_rows }
    }
}

/// Normaliza las filas para comparar entre motores: convierte cualquier número entero codificado como
/// float (`4.0`) y los flotantes a una forma canónica, y deja el resto verbatim. SQLite y el adaptador
/// ya devuelven JSON homogéneo (enteros como Number i64, REAL como f64, TEXT/NULL igual), así que la
/// normalización es ligera; existe para absorber el caso `1.0` vs `1` si apareciera.
fn normalize_rows(rows: &[Json]) -> Vec<Json> {
    rows.iter().map(normalize_value).collect()
}

fn normalize_value(v: &Json) -> Json {
    match v {
        Json::Object(map) => {
            Json::Object(map.iter().map(|(k, v)| (k.clone(), normalize_value(v))).collect())
        }
        Json::Array(a) => Json::Array(a.iter().map(normalize_value).collect()),
        Json::Number(n) => {
            // Un float que es entero exacto (4.0) → entero, para que 4.0 (un motor) == 4 (otro).
            if let Some(f) = n.as_f64() {
                if f.fract() == 0.0 && f.is_finite() && f.abs() < 9.007_199_254_740_992e15 {
                    return json!(f as i64);
                }
            }
            Json::Number(n.clone())
        }
        other => other.clone(),
    }
}
