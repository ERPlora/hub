//! E2E del contador de tareas del módulo `tasks` sobre **Postgres** real.
//!
//! Gemelo del test `pg_create_assigns_sequential_appointment_numbers_same_day` de
//! `appointments_availability_e2e.rs`: reproduce la MISMA familia de bug (#29, #25) en
//! el único otro módulo que aún escribía `SET last_number = last_number + 1` con el RHS
//! sin cualificar en un `ON CONFLICT` → Postgres lo rechaza con error 42702 (columna
//! ambigua: tabla destino vs `excluded`). SQLite lo acepta, por lo que el CI de módulos
//! (SQLite-only) no lo caza; hace falta un Postgres real para verlo.
//!
//! `tasks.tasks.create` (handler WASM) emite dos intenciones por tarea en una misma tx:
//! `tasks._bump_counter` (upsert atómico sobre `tasks_counter`) + `tasks._insert_task`,
//! que lee el contador recién incrementado vía subselect y forma `TSK-YYYYMMDD-NNNN`.
//! El test crea dos tareas el mismo día y comprueba la secuencia `0001 → 0002`: cubre a
//! la vez el 42702 (sin el fix, la 1ª `create` revienta) y la trampa de `excluded` (si el
//! fix leyera `excluded.last_number`, el contador se quedaría en 1 y ambas serían `0001`).
//!
//! ```sh
//! DATABASE_URL=postgres://postgres:test@localhost:5433/hub_test \
//!   cargo test -p erplora-runtime --test tasks_e2e -- --ignored --test-threads=1 --nocapture
//! ```
use std::path::PathBuf;

use chrono::Utc;
use erplora_db::{DatabaseAdapter, Params, PgAdapter};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(n: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules")
        .join(n)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// Instala `tasks` (no tiene `depends_on`) sobre Postgres, partiendo de esquema limpio.
async fn rt_tasks_pg() -> Runtime {
    let url = std::env::var("DATABASE_URL").expect("set DATABASE_URL para los tests PG");
    let db = PgAdapter::connect(&url).await.expect("connect to postgres");
    db.execute_batch("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        .await
        .expect("reset schema public");
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.expect("ensure_system_tables");
    rt.install_from_dir(&mdir("tasks")).await.expect("instalar tasks");
    rt
}

/// `last_number` del contador de tareas para el día `day_key` (YYYYMMDD) de este hub.
async fn counter_for_day(rt: &Runtime, day_key: &str) -> Option<i64> {
    let mut p = Params::new();
    p.insert("day".into(), json!(day_key));
    let rows = rt
        .db_for_test()
        .query(
            "SELECT last_number FROM tasks_counter WHERE hub_id = 'h1' AND day = :day",
            &p,
        )
        .await
        .expect("SELECT last_number")
        .rows;
    rows.first()
        .and_then(|r| r["last_number"].as_i64())
}

/// Reproduce el bug #29 en `tasks`: `commands/_bump_counter.sql` escribía
/// `SET last_number = last_number + 1` con el RHS sin cualificar → error 42702 en
/// Postgres (SQLite lo traga). Y cubre la trampa de `excluded.last_number`: si el fix
/// leyera esa pseudo-fila, el contador nunca pasaría de 1.
///
/// Aislamos el contador invocando el sub-comando `tasks._bump_counter` directamente (es
/// la 1ª intención que emite el handler `tasks.tasks.create`, antes de `_insert_task`).
/// Así el test no depende del `_insert_task` —que padece OTRO bug PG aparte (42P08 por
/// tipo no inferible de `:project_id`), fuera del scope de #29— y mide solo el fix del
/// contador. El runtime inyecta `:hub_id`/`:current_user_id`/`:now`/`:new_id` desde el
/// contexto; el handler aporta `:day`.
#[tokio::test]
#[ignore = "requires a real Postgres via DATABASE_URL"]
async fn pg_bump_counter_increments_sequentially_same_day() {
    let rt = rt_tasks_pg().await;
    let ctx = admin();

    let day_key = Utc::now().format("%Y%m%d").to_string(); // hoy UTC

    // 1ª intención: inserta la fila del día con last_number=1.
    rt.execute_command(
        "tasks._bump_counter",
        &params(json!({ "day": day_key })),
        &ctx,
    )
    .await
    .expect("1ª _bump_counter (sin el fix revienta con 42702)");
    assert_eq!(
        counter_for_day(&rt, &day_key).await,
        Some(1),
        "la 1ª intención inicializa el contador del día en 1"
    );

    // 2ª intención MISMO día: debe INCREMENTAR a 2 (no quedarse en 1).
    rt.execute_command(
        "tasks._bump_counter",
        &params(json!({ "day": day_key })),
        &ctx,
    )
    .await
    .expect("2ª _bump_counter");
    assert_eq!(
        counter_for_day(&rt, &day_key).await,
        Some(2),
        "la 2ª intención incrementa el contador a 2 (cubre la trampa de excluded: \
         si el fix leyera excluded.last_number, seguiría en 1 y toda tarea del día \
         compartiría TSK-<day>-0001)"
    );
}
