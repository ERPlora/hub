//! Prueba e2e del **cableado completo** del sync (ADR-0031) con un dato REAL de negocio:
//! módulo con bloque `sync[]` instalado → fila creada vía `execute_command` → `Runtime::run_sync`
//! → la fila aparece en **Aurora real** (por el túnel SSH). No es un mock: ejercita
//! manifest→registry→run_sync→motor→Postgres de punta a punta.
//!
//! `#[ignore]` por defecto. Para correrlo (con el túnel abierto, ver `/db-tunnel`):
//! ```sh
//! export DATASYNC_PG_DSN='postgres://USER:PASS@127.0.0.1:5432/erplora_cloud?sslmode=require'
//! cargo test -p erplora-runtime --test sync_wiring_tunnel -- --ignored --nocapture
//! ```

use std::path::PathBuf;

use erplora_db::{DatabaseAdapter, Params, PgAdapter, SqliteAdapter};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_syncdemo")
}

#[tokio::test]
#[ignore = "necesita DATASYNC_PG_DSN (Aurora vía túnel)"]
async fn full_wiring_syncs_a_real_row_to_aurora() {
    let dsn = std::env::var("DATASYNC_PG_DSN")
        .expect("export DATASYNC_PG_DSN='postgres://…@127.0.0.1:5432/erplora_cloud?sslmode=require'");

    // 1) Runtime local (SQLite) con el módulo `syncdemo` (declara `sync[]`) instalado y activo.
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.expect("instalar syncdemo");
    rt.activate("syncdemo").await.ok();

    let hub_id = format!("demo-hub-{}", std::process::id());
    let ctx = RequestContext::new(hub_id.clone(), "u1", ["syncdemo.write".to_string()]);

    // 2) Crear una fila REAL por el command (el runtime inyecta `:new_id`/`:hub_id`/`:now`).
    let body = format!("hola-tunnel-{}", std::process::id());
    let mut payload = Params::new();
    payload.insert("body".into(), json!(body));
    rt.execute_command("syncdemo.create", &payload, &ctx).await.expect("crear fila local");

    // 3) Preparar la tabla espejo en Aurora y sincronizar por el cableado real.
    let remote = PgAdapter::connect(&dsn).await.expect("conectar a Aurora");
    remote
        .execute_batch(
            "CREATE TABLE IF NOT EXISTS syncdemo_item (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, \
             body TEXT, updated_at TEXT NOT NULL)",
        )
        .await
        .unwrap();
    let report = rt.run_sync(&remote, &hub_id).await.expect("run_sync");

    // 4) Leer de Aurora (antes de limpiar) y limpiar mis filas (cleanup garantizado).
    let mut q = Params::new();
    q.insert("hub_id".into(), json!(hub_id));
    let got = remote
        .query("SELECT body FROM syncdemo_item WHERE hub_id = :hub_id", &q)
        .await
        .unwrap();
    let body_in_cloud = got
        .rows
        .first()
        .and_then(|r| r.get("body"))
        .and_then(|v| v.as_str())
        .map(String::from);
    remote.execute("DELETE FROM syncdemo_item WHERE hub_id = :hub_id", &q).await.ok();
    remote.execute_batch("DROP TABLE IF EXISTS syncdemo_item").await.ok();

    // 5) Asserts.
    assert_eq!(report.pushed, 1, "una fila subió a Aurora");
    assert_eq!(body_in_cloud.as_deref(), Some(body.as_str()), "la fila real llegó a Aurora");

    println!(
        "✅ e2e cableado: fila '{}' creada en SQLite local vía command → Aurora (push={}, pull={})",
        body, report.pushed, report.pulled
    );
}
