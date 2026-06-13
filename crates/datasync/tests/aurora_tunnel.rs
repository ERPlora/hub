//! Verificación REAL del motor de sync contra Postgres/Aurora (vía túnel SSH).
//!
//! No es un mock: abre un `PgAdapter` real contra el DSN de `DATASYNC_PG_DSN` (Aurora por el
//! túnel del bastion, ver `/db-tunnel`), crea una tabla **aislada y efímera** (`_sync_demo_<pid>`),
//! hace un round-trip SQLite↔Aurora con el motor y la **borra** al final (cleanup garantizado
//! antes de los asserts, así no deja rastro en prod aunque falle).
//!
//! Por defecto está `#[ignore]` (el `cargo test` normal no toca la red). Para correrlo:
//! ```sh
//! # 1) túnel:  ssh -i ~/.ssh/id_erplora -L 5433:<aurora-endpoint>:5432 ubuntu@<bastion>
//! # 2) DSN:    export DATASYNC_PG_DSN='postgres://USER:PASS@127.0.0.1:5433/erplora_cloud?sslmode=disable'
//! # 3) correr: cargo test -p erplora-datasync --test aurora_tunnel -- --ignored --nocapture
//! ```

use erplora_datasync::{SyncEngine, SyncTable};
use erplora_db::{DatabaseAdapter, Params, PgAdapter, SqliteAdapter};
use serde_json::{json, Value as Json};

fn order(id: &str, total: f64, ua: &str) -> Params {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!("tunnel-test-hub"));
    p.insert("total".into(), json!(total));
    p.insert("ua".into(), json!(ua));
    p
}

#[tokio::test]
#[ignore = "necesita DATASYNC_PG_DSN (Aurora vía túnel)"]
async fn round_trip_sqlite_aurora() {
    let dsn = std::env::var("DATASYNC_PG_DSN")
        .expect("export DATASYNC_PG_DSN='postgres://…@127.0.0.1:5433/erplora_cloud?sslmode=disable'");

    let remote = PgAdapter::connect(&dsn).await.expect("conectar a Aurora");
    let local = SqliteAdapter::open_in_memory().await.unwrap();

    // Tabla aislada y única → cero riesgo sobre datos de negocio/control de prod.
    let t = format!("_sync_demo_{}", std::process::id());
    let cols = "(id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, total DOUBLE PRECISION NOT NULL, \
                 is_deleted INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)";
    remote
        .execute_batch(&format!("CREATE TABLE IF NOT EXISTS {t} {cols}"))
        .await
        .expect("crear tabla demo en Aurora");
    local
        .execute_batch(&format!(
            "CREATE TABLE {t} (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, total REAL NOT NULL, \
             is_deleted INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)"
        ))
        .await
        .unwrap();

    let ins = format!(
        "INSERT INTO {t} (id, hub_id, total, updated_at) VALUES (:id, :hub_id, :total, :ua) \
         ON CONFLICT (id) DO UPDATE SET total = excluded.total, updated_at = excluded.updated_at"
    );

    // 1) fila nacida en el LOCAL (caja offline) + fila nacida en el CLOUD (otro dispositivo).
    local.execute(&ins, &order("loc-1", 10.0, "2026-06-13T10:00:00Z")).await.unwrap();
    remote.execute(&ins, &order("cld-1", 20.0, "2026-06-13T10:30:00Z")).await.unwrap();

    let mut table = SyncTable::new(&t, &["id"]);
    table.hub_scoped = true;
    let engine = SyncEngine::new(&local, &remote, vec![table.clone()]);
    let report = engine.sync("tunnel-test-hub").await.expect("sync round-trip");

    // 2) LWW: el cloud actualiza loc-1 con timestamp posterior → debe ganar al bajar.
    remote.execute(&ins, &order("loc-1", 77.0, "2026-06-13T12:00:00Z")).await.unwrap();
    engine.sync("tunnel-test-hub").await.expect("segundo sync");

    // --- recoger resultados ANTES de limpiar (cleanup garantizado aunque falle un assert) ---
    async fn total_pg(db: &PgAdapter, t: &str, id: &str) -> Option<f64> {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        db.query(&format!("SELECT total FROM {t} WHERE id = :id"), &p)
            .await
            .unwrap()
            .rows
            .first()
            .and_then(|r| r.get("total"))
            .and_then(Json::as_f64)
    }
    async fn total_sqlite(db: &SqliteAdapter, t: &str, id: &str) -> Option<f64> {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        db.query(&format!("SELECT total FROM {t} WHERE id = :id"), &p)
            .await
            .unwrap()
            .rows
            .first()
            .and_then(|r| r.get("total"))
            .and_then(Json::as_f64)
    }

    let pushed_to_cloud = total_pg(&remote, &t, "loc-1").await; // existía en Aurora tras push
    let pulled_to_local = total_sqlite(&local, &t, "cld-1").await; // bajó del cloud
    let lww_local = total_sqlite(&local, &t, "loc-1").await; // 77.0 si LWW bajó el más nuevo

    // 3) cleanup garantizado.
    remote.execute_batch(&format!("DROP TABLE IF EXISTS {t}")).await.expect("drop tabla demo");

    // --- asserts ---
    assert_eq!(report.pushed, 1, "loc-1 sube al cloud");
    assert!(pushed_to_cloud.is_some(), "loc-1 está en Aurora tras el push");
    assert_eq!(pulled_to_local, Some(20.0), "cld-1 bajó al SQLite local");
    assert_eq!(lww_local, Some(77.0), "LWW: la versión más nueva del cloud ganó en local");

    println!("✅ round-trip SQLite↔Aurora OK (push={}, pull={})", report.pushed, report.pulled);
}
