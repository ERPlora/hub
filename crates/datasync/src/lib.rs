//! erplora-datasync — motor de sync local↔cloud (PRIMER BORRADOR, ADR-0031).
//!
//! ⚠️ **Columna del humano.** Escrito por la IA bajo **excepción explícita** (ciclo de
//! aprendizaje: borrador → el humano compara → el humano reescribe la parte final). No es un
//! mock: es lógica real (Last-Write-Wins por `updated_at`, cursores transaccionales), pero su
//! API/algoritmo los **revisa y reescribe el humano**. No confundir con `erplora-sync` (cliente
//! WS de eventos en vivo).
//!
//! # Modelo (ADR-0031)
//! Local-first: cada dispositivo opera sobre su **SQLite local como autoridad** y **sincroniza**
//! contra Aurora (el nodo cloud es el *master*, topología estrella). El motor es **genérico sobre
//! el trait [`DatabaseAdapter`](erplora_db::DatabaseAdapter)** de `erplora-db`, así que el mismo
//! código sirve SQLite (local) ↔ Postgres/Aurora (cloud) sin SQL específico de backend.
//!
//! # Algoritmo
//! Sync row-level con **Last-Write-Wins** por la columna `updated_at` (ISO-8601 TEXT, comparable
//! lexicográficamente). La autoridad del timestamp es el **`:now` del servidor** que el runtime ya
//! inyecta — no el reloj del dispositivo (evita clock-skew, ADR-0031). Cursores incrementales por
//! tabla en `_sync_state` (local).
//!
//! - **push**: filas locales con `updated_at > push_cursor` → UPSERT en remoto con guarda LWW.
//! - **pull**: filas remotas con `updated_at > pull_cursor` → UPSERT en local con guarda LWW.
//!
//! El UPSERT usa `INSERT ... ON CONFLICT (pk) DO UPDATE SET ... WHERE destino.updated_at <
//! excluded.updated_at` (SQL portable ADR-0007). El soft-delete (`is_deleted`) se propaga como una
//! fila normal (tombstone): no se borra físicamente, así que el borrado viaja por el mismo canal.
//!
//! # Límites de este borrador (columna humano — ver `architecture/hub/data-sync.md`)
//! - **PK = UUID v4** (ADR-0035): ids `TEXT` globalmente únicos vía `:new_id` ⇒ **sin remapeo** al
//!   fusionar local↔cloud (la decisión previa de PK numérica + remapeo de §2.5 queda superada).
//! - **Stock**: hub-scoped, se sincroniza como cualquier tabla en fase 1 (ADR-0035). Límite conocido:
//!   LWW ciego entre varios dispositivos del MISMO hub puede perder decrementos (refino futuro;
//!   stock entre tiendas = módulo `warehouse`, futuro).
//! - **Edición con timestamp anterior al cursor**: no se reenvía (asume `updated_at` monótono =
//!   `now()` creciente, que es el caso real del runtime).

use erplora_db::{DatabaseAdapter, DbError, Params};
use serde_json::{json, Map, Value as Json};
use thiserror::Error;

/// Errores del motor de sync.
#[derive(Debug, Error)]
pub enum SyncError {
    #[error("db: {0}")]
    Db(#[from] DbError),
    /// Una fila devuelta por `query` no era un objeto JSON (no debería ocurrir).
    #[error("la fila no es un objeto JSON")]
    NotObject,
}

/// Descripción de una tabla sincronizable.
#[derive(Debug, Clone)]
pub struct SyncTable {
    /// Nombre de la tabla (debe existir en ambos lados; las migraciones crean el esquema).
    pub name: String,
    /// Columnas que forman el conflict-target del UPSERT (la PK lógica).
    pub pk: Vec<String>,
    /// Columna de versión para LWW (ISO-8601 TEXT). Por defecto `updated_at`.
    pub updated_at: String,
    /// Si la tabla lleva `hub_id`, se filtra por hub en push/pull (tenancy, §2.5).
    pub hub_scoped: bool,
}

impl SyncTable {
    /// Tabla hub-scoped con `updated_at` por defecto.
    pub fn new(name: &str, pk: &[&str]) -> Self {
        Self {
            name: name.to_string(),
            pk: pk.iter().map(|s| s.to_string()).collect(),
            updated_at: "updated_at".to_string(),
            hub_scoped: true,
        }
    }

    /// Marca la tabla como NO hub-scoped (sin filtro `hub_id`).
    pub fn global(mut self) -> Self {
        self.hub_scoped = false;
        self
    }
}

/// Resultado de un ciclo de sync: nº de filas transferidas en cada sentido.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct SyncReport {
    pub pushed: u64,
    pub pulled: u64,
}

/// Motor de sync entre un backend `local` (autoridad) y uno `remote` (Aurora, master).
///
/// Ambos son `&dyn DatabaseAdapter`, así que el motor es agnóstico al backend.
pub struct SyncEngine<'a> {
    local: &'a dyn DatabaseAdapter,
    remote: &'a dyn DatabaseAdapter,
    tables: Vec<SyncTable>,
}

impl<'a> SyncEngine<'a> {
    pub fn new(
        local: &'a dyn DatabaseAdapter,
        remote: &'a dyn DatabaseAdapter,
        tables: Vec<SyncTable>,
    ) -> Self {
        Self { local, remote, tables }
    }

    /// Crea la tabla de cursores en el lado local (idempotente).
    pub async fn ensure_state_table(&self) -> Result<(), SyncError> {
        self.local
            .execute_batch(
                "CREATE TABLE IF NOT EXISTS _sync_state (\
                   table_name TEXT PRIMARY KEY,\
                   push_cursor TEXT NOT NULL DEFAULT '',\
                   pull_cursor TEXT NOT NULL DEFAULT ''\
                 );",
            )
            .await?;
        Ok(())
    }

    /// Un ciclo completo: push de todas las tablas y luego pull de todas. At-least-once e
    /// idempotente (el UPSERT con guarda LWW absorbe los reenvíos).
    pub async fn sync(&self, hub_id: &str) -> Result<SyncReport, SyncError> {
        self.ensure_state_table().await?;
        let mut report = SyncReport::default();
        for t in &self.tables {
            report.pushed += self.transfer(t, hub_id, Direction::Push).await?;
        }
        for t in &self.tables {
            report.pulled += self.transfer(t, hub_id, Direction::Pull).await?;
        }
        Ok(report)
    }

    /// Núcleo común de push/pull: lee del origen las filas más nuevas que el cursor, las aplica
    /// en el destino dentro de **una transacción** (todo-o-nada) y avanza el cursor.
    async fn transfer(
        &self,
        t: &SyncTable,
        hub_id: &str,
        dir: Direction,
    ) -> Result<u64, SyncError> {
        let (source, target, cursor_col) = match dir {
            Direction::Push => (self.local, self.remote, "push_cursor"),
            Direction::Pull => (self.remote, self.local, "pull_cursor"),
        };

        let cursor = self.read_cursor(&t.name, cursor_col).await?;

        let mut sql = format!("SELECT * FROM {} WHERE {} > :cursor", t.name, t.updated_at);
        if t.hub_scoped {
            sql.push_str(" AND hub_id = :hub_id");
        }
        sql.push_str(&format!(" ORDER BY {}", t.updated_at));

        let mut params = Params::new();
        params.insert("cursor".to_string(), json!(cursor));
        if t.hub_scoped {
            params.insert("hub_id".to_string(), json!(hub_id));
        }

        let rows = source.query(&sql, &params).await?.rows;
        if rows.is_empty() {
            return Ok(0);
        }

        let mut ops: Vec<(String, Params)> = Vec::with_capacity(rows.len());
        let mut max_cursor = cursor.clone();
        for row in &rows {
            let obj = row.as_object().ok_or(SyncError::NotObject)?;
            if let Some(v) = obj.get(&t.updated_at).and_then(Json::as_str) {
                if v > max_cursor.as_str() {
                    max_cursor = v.to_string();
                }
            }
            ops.push(build_upsert(t, obj));
        }

        // Todo-o-nada: si la transacción falla, el cursor NO avanza y se reintenta el lote entero.
        target.execute_tx(&ops).await?;
        self.write_cursor(&t.name, cursor_col, &max_cursor).await?;
        Ok(rows.len() as u64)
    }

    /// Lee un cursor (cadena vacía si la tabla aún no tiene fila de estado).
    async fn read_cursor(&self, table: &str, col: &str) -> Result<String, SyncError> {
        let sql = format!("SELECT {col} AS c FROM _sync_state WHERE table_name = :t");
        let mut p = Params::new();
        p.insert("t".to_string(), json!(table));
        let res = self.local.query(&sql, &p).await?;
        Ok(res
            .rows
            .first()
            .and_then(|r| r.get("c"))
            .and_then(Json::as_str)
            .unwrap_or("")
            .to_string())
    }

    /// Escribe un cursor (update; si no existía la fila, insert). Cada `:param` aparece una sola
    /// vez por sentencia para no depender de cómo `translate` maneje nombres repetidos.
    async fn write_cursor(&self, table: &str, col: &str, value: &str) -> Result<(), SyncError> {
        let mut p = Params::new();
        p.insert("t".to_string(), json!(table));
        p.insert("v".to_string(), json!(value));

        let upd = format!("UPDATE _sync_state SET {col} = :v WHERE table_name = :t");
        let res = self.local.execute(&upd, &p).await?;
        if res.affected == 0 {
            let ins = format!("INSERT INTO _sync_state (table_name, {col}) VALUES (:t, :v)");
            self.local.execute(&ins, &p).await?;
        }
        Ok(())
    }
}

#[derive(Clone, Copy)]
enum Direction {
    Push,
    Pull,
}

/// Construye el UPSERT LWW para una fila. Las columnas salen de las claves del objeto JSON
/// (orden determinista: `serde_json::Map` es un `BTreeMap`), y los valores se pasan como `Params`
/// con el mismo nombre → `:col`, que el backend liga de forma segura (anti-inyección).
fn build_upsert(t: &SyncTable, row: &Map<String, Json>) -> (String, Params) {
    let cols: Vec<&str> = row.keys().map(String::as_str).collect();
    let col_list = cols.join(", ");
    let val_list = cols.iter().map(|c| format!(":{c}")).collect::<Vec<_>>().join(", ");
    let pk_set: std::collections::HashSet<&str> = t.pk.iter().map(String::as_str).collect();

    let assignments = cols
        .iter()
        .filter(|c| !pk_set.contains(**c))
        .map(|c| format!("{c} = excluded.{c}"))
        .collect::<Vec<_>>()
        .join(", ");
    let pk_list = t.pk.join(", ");

    let sql = if assignments.is_empty() {
        // Tabla que es toda PK: nada que actualizar, solo insertar si no existe.
        format!(
            "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO NOTHING",
            t.name, col_list, val_list, pk_list
        )
    } else {
        format!(
            "INSERT INTO {tbl} ({cols}) VALUES ({vals}) \
             ON CONFLICT ({pk}) DO UPDATE SET {set} \
             WHERE {tbl}.{ua} < excluded.{ua}",
            tbl = t.name,
            cols = col_list,
            vals = val_list,
            pk = pk_list,
            set = assignments,
            ua = t.updated_at,
        )
    };

    (sql, row.clone())
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::SqliteAdapter;

    const DDL: &str = "CREATE TABLE orders (\
        id TEXT PRIMARY KEY,\
        hub_id TEXT NOT NULL,\
        total REAL NOT NULL,\
        is_deleted INTEGER NOT NULL DEFAULT 0,\
        updated_at TEXT NOT NULL\
    );";

    async fn upsert_order(db: &SqliteAdapter, id: &str, total: f64, ua: &str) {
        let sql = "INSERT INTO orders (id, hub_id, total, updated_at) \
                   VALUES (:id, :hub_id, :total, :ua) \
                   ON CONFLICT (id) DO UPDATE SET total = excluded.total, updated_at = excluded.updated_at";
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!("h1"));
        p.insert("total".into(), json!(total));
        p.insert("ua".into(), json!(ua));
        db.execute(sql, &p).await.unwrap();
    }

    async fn total_of(db: &SqliteAdapter, id: &str) -> Option<f64> {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        let r = db
            .query("SELECT total FROM orders WHERE id = :id", &p)
            .await
            .unwrap();
        r.rows
            .first()
            .and_then(|row| row.get("total"))
            .and_then(Json::as_f64)
    }

    async fn pair() -> (SqliteAdapter, SqliteAdapter) {
        let local = SqliteAdapter::open_in_memory().await.unwrap();
        let remote = SqliteAdapter::open_in_memory().await.unwrap();
        local.execute_batch(DDL).await.unwrap();
        remote.execute_batch(DDL).await.unwrap();
        (local, remote)
    }

    fn engine<'a>(local: &'a SqliteAdapter, remote: &'a SqliteAdapter) -> SyncEngine<'a> {
        SyncEngine::new(local, remote, vec![SyncTable::new("orders", &["id"])])
    }

    #[tokio::test]
    async fn push_then_pull_propagates_new_rows_both_ways() {
        let (local, remote) = pair().await;
        upsert_order(&local, "o1", 10.0, "2026-06-13T10:00:00Z").await;
        upsert_order(&remote, "o2", 20.0, "2026-06-13T10:30:00Z").await;

        let report = engine(&local, &remote).sync("h1").await.unwrap();
        assert_eq!(report.pushed, 1, "o1 sube");
        assert_eq!(report.pulled, 2, "o2 (+o1 ya en remoto) se procesan al bajar");

        // o1 llegó al remoto; o2 llegó al local.
        assert_eq!(total_of(&remote, "o1").await, Some(10.0));
        assert_eq!(total_of(&local, "o2").await, Some(20.0));
    }

    #[tokio::test]
    async fn lww_newer_wins_on_pull() {
        let (local, remote) = pair().await;
        upsert_order(&local, "o1", 10.0, "2026-06-13T10:00:00Z").await;
        engine(&local, &remote).sync("h1").await.unwrap();

        // Otro dispositivo actualizó o1 en el cloud con timestamp posterior.
        upsert_order(&remote, "o1", 99.0, "2026-06-13T11:00:00Z").await;
        engine(&local, &remote).sync("h1").await.unwrap();

        assert_eq!(total_of(&local, "o1").await, Some(99.0), "el más nuevo gana al bajar");
    }

    #[tokio::test]
    async fn lww_rejects_stale_write_on_push() {
        let (local, remote) = pair().await;
        upsert_order(&local, "o1", 10.0, "2026-06-13T10:00:00Z").await;
        upsert_order(&remote, "o1", 99.0, "2026-06-13T12:00:00Z").await; // remoto más nuevo
        engine(&local, &remote).sync("h1").await.unwrap();

        // El push del local (10:00) NO debe pisar el remoto (12:00): guarda LWW.
        assert_eq!(total_of(&remote, "o1").await, Some(99.0), "el push viejo no pisa al nuevo");
    }

    #[tokio::test]
    async fn soft_delete_tombstone_propagates() {
        let (local, remote) = pair().await;
        upsert_order(&local, "o1", 10.0, "2026-06-13T10:00:00Z").await;
        engine(&local, &remote).sync("h1").await.unwrap();

        // Soft-delete local con timestamp posterior.
        let mut p = Params::new();
        p.insert("id".into(), json!("o1"));
        p.insert("ua".into(), json!("2026-06-13T13:00:00Z"));
        local
            .execute(
                "UPDATE orders SET is_deleted = 1, updated_at = :ua WHERE id = :id",
                &p,
            )
            .await
            .unwrap();
        engine(&local, &remote).sync("h1").await.unwrap();

        let mut q = Params::new();
        q.insert("id".into(), json!("o1"));
        let r = remote
            .query("SELECT is_deleted FROM orders WHERE id = :id", &q)
            .await
            .unwrap();
        let deleted = r.rows[0].get("is_deleted").and_then(Json::as_i64).unwrap();
        assert_eq!(deleted, 1, "el tombstone llegó al remoto");
    }

    #[tokio::test]
    async fn second_sync_is_noop_after_convergence() {
        let (local, remote) = pair().await;
        upsert_order(&local, "o1", 10.0, "2026-06-13T10:00:00Z").await;
        let eng = engine(&local, &remote);
        eng.sync("h1").await.unwrap();
        let second = eng.sync("h1").await.unwrap();
        assert_eq!(second, SyncReport { pushed: 0, pulled: 0 }, "ya convergido: nada que mover");
    }

    // ===================================================================
    // Worker E — tests de endurecimiento (ver todo/E-sync-review-findings.md)
    // ===================================================================

    /// Helper: tabla con una columna EXTRA respecto al esquema canónico (drift).
    const DDL_WITH_EXTRA: &str = "CREATE TABLE orders (\
        id TEXT PRIMARY KEY,\
        hub_id TEXT NOT NULL,\
        total REAL NOT NULL,\
        note TEXT,\
        is_deleted INTEGER NOT NULL DEFAULT 0,\
        updated_at TEXT NOT NULL\
    );";

    /// H1 (HIGH) — Deriva de esquema atasca la sync. El origen tiene una columna (`note`) que el
    /// destino no tiene: `build_upsert` la incluye en el INSERT y el `execute_tx` falla. El cursor
    /// NO avanza (todo-o-nada), así que el relay reintentaría el mismo lote para siempre.
    /// **Pasa hoy** (documenta que el drift produce `Err`); el comentario marca el riesgo de atasco.
    #[tokio::test]
    async fn schema_drift_wedges_push() {
        let local = SqliteAdapter::open_in_memory().await.unwrap();
        let remote = SqliteAdapter::open_in_memory().await.unwrap();
        local.execute_batch(DDL_WITH_EXTRA).await.unwrap();
        remote.execute_batch(DDL).await.unwrap(); // remoto SIN `note`

        let mut p = Params::new();
        p.insert("id".into(), json!("o1"));
        p.insert("hub_id".into(), json!("h1"));
        p.insert("total".into(), json!(10.0));
        p.insert("note".into(), json!("hola"));
        p.insert("ua".into(), json!("2026-06-13T10:00:00Z"));
        local
            .execute(
                "INSERT INTO orders (id, hub_id, total, note, updated_at) \
                 VALUES (:id, :hub_id, :total, :note, :ua)",
                &p,
            )
            .await
            .unwrap();

        let res = engine(&local, &remote).sync("h1").await;
        assert!(res.is_err(), "drift de columna debe fallar el ciclo (riesgo: atasco permanente)");
        // El cursor no avanzó: la fila sigue sin llegar al remoto.
        assert_eq!(total_of(&remote, "o1").await, None);
    }

    /// M3 (MED) — Tabla sin `updated_at`: el motor no valida la forma de la tabla y el
    /// `SELECT ... WHERE updated_at > :cursor` explota en runtime. **Pasa hoy** (documenta el footgun).
    #[tokio::test]
    async fn missing_updated_at_column_errors() {
        let local = SqliteAdapter::open_in_memory().await.unwrap();
        let remote = SqliteAdapter::open_in_memory().await.unwrap();
        let ddl = "CREATE TABLE thing (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);";
        local.execute_batch(ddl).await.unwrap();
        remote.execute_batch(ddl).await.unwrap();
        let mut p = Params::new();
        p.insert("id".into(), json!("t1"));
        p.insert("hub_id".into(), json!("h1"));
        local
            .execute("INSERT INTO thing (id, hub_id) VALUES (:id, :hub_id)", &p)
            .await
            .unwrap();

        let eng = SyncEngine::new(&local, &remote, vec![SyncTable::new("thing", &["id"])]);
        assert!(eng.sync("h1").await.is_err(), "tabla sin updated_at: el ciclo debe fallar, no corromper");
    }

    /// H2 (HIGH) — Empate de `updated_at` no converge. Dos devices (d1, d2) y un remoto. Ambos
    /// escriben `o1` con el MISMO timestamp pero valores distintos. La guarda LWW estricta (`<`) no
    /// pisa en empate → el remoto se queda con el primero y d2 conserva el suyo: **divergencia**.
    /// **Pasa hoy**: documenta el comportamiento real (split-brain).
    #[tokio::test]
    async fn tie_diverges_today() {
        let d1 = SqliteAdapter::open_in_memory().await.unwrap();
        let d2 = SqliteAdapter::open_in_memory().await.unwrap();
        let remote = SqliteAdapter::open_in_memory().await.unwrap();
        for db in [&d1, &d2, &remote] {
            db.execute_batch(DDL).await.unwrap();
        }
        let t = "2026-06-13T10:00:00Z";
        upsert_order(&d1, "o1", 10.0, t).await;
        upsert_order(&d2, "o1", 20.0, t).await;

        SyncEngine::new(&d1, &remote, vec![SyncTable::new("orders", &["id"])]).sync("h1").await.unwrap();
        SyncEngine::new(&d2, &remote, vec![SyncTable::new("orders", &["id"])]).sync("h1").await.unwrap();

        // El push de d2 (20@T) no pisó al remoto (10@T) por el empate, y el pull no pisó a d2.
        assert_eq!(total_of(&remote, "o1").await, Some(10.0), "remoto se queda con el primero");
        assert_eq!(total_of(&d2, "o1").await, Some(20.0), "d2 conserva el suyo → divergencia");
    }

    /// H2 — objetivo del arreglo: con desempate determinista, los tres lados deberían CONVERGER al
    /// mismo valor en empate de timestamp. Falla hoy (no hay tiebreaker) → `#[ignore]`.
    #[tokio::test]
    #[ignore = "BUG H2: LWW sin desempate determinista → no converge en empate (ver findings)"]
    async fn tie_should_converge() {
        let d1 = SqliteAdapter::open_in_memory().await.unwrap();
        let d2 = SqliteAdapter::open_in_memory().await.unwrap();
        let remote = SqliteAdapter::open_in_memory().await.unwrap();
        for db in [&d1, &d2, &remote] {
            db.execute_batch(DDL).await.unwrap();
        }
        let t = "2026-06-13T10:00:00Z";
        upsert_order(&d1, "o1", 10.0, t).await;
        upsert_order(&d2, "o1", 20.0, t).await;

        let tbl = || vec![SyncTable::new("orders", &["id"])];
        // Varias rondas para dar oportunidad a converger.
        for _ in 0..3 {
            SyncEngine::new(&d1, &remote, tbl()).sync("h1").await.unwrap();
            SyncEngine::new(&d2, &remote, tbl()).sync("h1").await.unwrap();
        }
        let r = total_of(&remote, "o1").await;
        assert_eq!(total_of(&d1, "o1").await, r, "d1 debe converger al remoto");
        assert_eq!(total_of(&d2, "o1").await, r, "d2 debe converger al remoto");
    }

    /// M1 (MED) — Reloj hacia atrás: una fila escrita con `updated_at < cursor` nunca se reenvía
    /// (filtro `>` estricto + cursor = máximo visto). Objetivo del arreglo: debería sincronizarse.
    /// Falla hoy → `#[ignore]`.
    #[tokio::test]
    #[ignore = "BUG M1: updated_at no monótono (reloj atrás) → fila con ts<cursor se pierde"]
    async fn clock_step_back_row_is_lost() {
        let (local, remote) = pair().await;
        upsert_order(&local, "o1", 10.0, "2026-06-13T10:00:02Z").await;
        engine(&local, &remote).sync("h1").await.unwrap(); // push_cursor = ...:02

        // El reloj retrocede: o2 se crea con un timestamp ANTERIOR al cursor.
        upsert_order(&local, "o2", 20.0, "2026-06-13T10:00:01Z").await;
        engine(&local, &remote).sync("h1").await.unwrap();

        assert_eq!(total_of(&remote, "o2").await, Some(20.0), "o2 debería haberse sincronizado");
    }

    /// M5 (MED) — Pérdida en la frontera del cursor. Tras un ciclo, `push_cursor = T`. Una fila
    /// escrita DESPUÉS con `updated_at` EXACTAMENTE `T` queda fuera del filtro `> :cursor` (estricto)
    /// y **nunca se reenvía**. Realista con timestamps de baja resolución o `:now` compartido por un
    /// comando (ver "Dato clave" del informe). **Pasa hoy**: documenta la pérdida silenciosa.
    #[tokio::test]
    async fn boundary_equal_timestamp_lost_today() {
        let (local, remote) = pair().await;
        let t = "2026-06-13T10:00:00Z";
        upsert_order(&local, "o1", 10.0, t).await;
        engine(&local, &remote).sync("h1").await.unwrap(); // push_cursor = t

        // Nueva fila con el MISMO timestamp que el cursor (mismo tick / :now compartido).
        upsert_order(&local, "o2", 20.0, t).await;
        engine(&local, &remote).sync("h1").await.unwrap();

        assert_eq!(
            total_of(&remote, "o2").await,
            None,
            "o2 (ua == cursor) se pierde por el filtro `>` estricto"
        );
    }

    /// M5 — objetivo del arreglo: una fila con `updated_at == cursor` debería sincronizarse (cursor
    /// compuesto `(ua, pk)` lo lograría). Falla hoy → `#[ignore]`.
    #[tokio::test]
    #[ignore = "BUG M5: fila con updated_at == cursor nunca se reenvía (cursor (ua,pk) lo arreglaría)"]
    async fn boundary_equal_timestamp_should_sync() {
        let (local, remote) = pair().await;
        let t = "2026-06-13T10:00:00Z";
        upsert_order(&local, "o1", 10.0, t).await;
        engine(&local, &remote).sync("h1").await.unwrap();

        upsert_order(&local, "o2", 20.0, t).await;
        engine(&local, &remote).sync("h1").await.unwrap();

        assert_eq!(
            total_of(&remote, "o2").await,
            Some(20.0),
            "o2 debería sincronizar pese a empatar con el cursor"
        );
    }

    /// M4 / I1 (pasa) — Aislamiento por hub en PULL: una Aurora de org con filas de DOS hubs; el
    /// device del hub `h1` solo baja las suyas. Ancla el filtro `hub_id = :hub_id` (no fuga cross-hub).
    #[tokio::test]
    async fn pull_filters_other_hub_rows() {
        let (local, remote) = pair().await;
        // Remoto (Aurora de la org) con o1 de h1 y o2 de h2.
        for (id, hub, total) in [("o1", "h1", 10.0), ("o2", "h2", 20.0)] {
            let mut p = Params::new();
            p.insert("id".into(), json!(id));
            p.insert("hub_id".into(), json!(hub));
            p.insert("total".into(), json!(total));
            p.insert("ua".into(), json!("2026-06-13T10:00:00Z"));
            remote
                .execute(
                    "INSERT INTO orders (id, hub_id, total, updated_at) VALUES (:id, :hub_id, :total, :ua)",
                    &p,
                )
                .await
                .unwrap();
        }

        engine(&local, &remote).sync("h1").await.unwrap();

        assert_eq!(total_of(&local, "o1").await, Some(10.0), "h1 baja lo suyo");
        assert_eq!(total_of(&local, "o2").await, None, "h2 NO llega al device de h1");
    }

    /// Endurecimiento (pasa) — reaparición tras tombstone: un `is_deleted=1` con ts posterior viaja,
    /// y un `is_deleted=0` con ts aún más nuevo lo "resucita" vía LWW. Verifica el ciclo completo.
    #[tokio::test]
    async fn tombstone_reappearance_undeletes() {
        let (local, remote) = pair().await;
        upsert_order(&local, "o1", 10.0, "2026-06-13T10:00:00Z").await;
        engine(&local, &remote).sync("h1").await.unwrap();

        // Borrado lógico con ts posterior → se propaga.
        let mut p = Params::new();
        p.insert("id".into(), json!("o1"));
        p.insert("ua".into(), json!("2026-06-13T11:00:00Z"));
        local
            .execute("UPDATE orders SET is_deleted = 1, updated_at = :ua WHERE id = :id", &p)
            .await
            .unwrap();
        engine(&local, &remote).sync("h1").await.unwrap();

        // Reaparición con ts aún más nuevo → LWW lo resucita en el remoto.
        let mut p2 = Params::new();
        p2.insert("id".into(), json!("o1"));
        p2.insert("ua".into(), json!("2026-06-13T12:00:00Z"));
        local
            .execute("UPDATE orders SET is_deleted = 0, total = 55, updated_at = :ua WHERE id = :id", &p2)
            .await
            .unwrap();
        engine(&local, &remote).sync("h1").await.unwrap();

        let mut q = Params::new();
        q.insert("id".into(), json!("o1"));
        let r = remote
            .query("SELECT is_deleted, total FROM orders WHERE id = :id", &q)
            .await
            .unwrap();
        let deleted = r.rows[0].get("is_deleted").and_then(Json::as_i64).unwrap();
        assert_eq!(deleted, 0, "la reaparición (ts más nuevo) revierte el tombstone");
        assert_eq!(total_of(&remote, "o1").await, Some(55.0));
    }
}
