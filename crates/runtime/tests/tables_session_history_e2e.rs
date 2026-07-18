//! ADR-0146 — la sesión de servicio es la fuente de verdad de la sala.
//!
//! Etapa 1: SOLO esquema, migración/backfill e invariantes de `tables_session_assignment`. No se
//! tocan los comandos ni se retira nada de lo anterior hasta que esto esté verde.
//!
//! Por qué existe esta tabla: `tables_session.table_id` solo sabe **dónde está ahora** una cuenta.
//! Al mover de la mesa 12 a la 8 se sobrescribe y el paso por la 12 desaparece — justo lo que hace
//! falta para saber cuánto estuvo ocupada cada mesa. El historial es append-only: cada tramo se
//! abre con su motivo y se cierra con el suyo (`assignment_reason` / `release_reason`), así aparcar
//! solo CIERRA el tramo vivo y no hay que inventar una fila para el periodo aparcado.

use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::Runtime;
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules").join(name)
}

/// Runtime con `tables` instalado (no depende de nadie).
async fn fresh() -> Runtime {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("tables")).await.expect("instalar tables");
    // Las mesas del ejemplo: `tables_session` tiene FK interna a `tables_table`.
    for (id, numero) in [("m12", "12"), ("m8", "8")] {
        rt.db_for_test()
            .execute(
                "INSERT INTO tables_table (id, hub_id, number, name, capacity, is_deleted, created_at)
                 VALUES (:id, 'h1', :numero, :nombre, 4, 0, '2026-07-19T00:00:00+00:00')",
                &params(json!({ "id": id, "numero": numero, "nombre": format!("Mesa {numero}") })),
            )
            .await
            .expect("mesa de ejemplo");
    }
    rt
}

/// Inserta una sesión «de antes», como las que ya existen en los hubs en marcha.
async fn sesion_legacy(rt: &Runtime, id: &str, table_id: &str, abierta: &str, cerrada: Option<&str>) {
    rt.db_for_test()
        .execute(
            "INSERT INTO tables_session (id, hub_id, table_id, opened_at, closed_at, guests_count,
                 status, notes, is_deleted, created_at)
             VALUES (:id, 'h1', :table_id, :opened_at, :closed_at, 2, :status, '', 0, :opened_at)",
            &params(json!({
                "id": id, "table_id": table_id, "opened_at": abierta, "closed_at": cerrada,
                "status": if cerrada.is_some() { "closed" } else { "active" },
            })),
        )
        .await
        .expect("sesión legacy");
}

async fn asignacion(
    rt: &Runtime, id: &str, session_id: &str, table_id: &str, op: &str, released: Option<&str>,
) -> Result<(), String> {
    rt.db_for_test()
        .execute(
            "INSERT INTO tables_session_assignment (id, hub_id, session_id, table_id, assigned_at,
                 released_at, assignment_reason, release_reason, operation_id, is_deleted, created_at)
             VALUES (:id, 'h1', :session_id, :table_id, '2026-07-19T20:00:00+00:00', :released,
                     'assigned', :release_reason, :op, 0, '2026-07-19T20:00:00+00:00')",
            &params(json!({
                "id": id, "session_id": session_id, "table_id": table_id, "op": op,
                "released": released,
                "release_reason": if released.is_some() { "moved" } else { "" },
            })),
        )
        .await
        .map(|_| ())
        .map_err(|e| e.to_string())
}

async fn contar(rt: &Runtime, sql: &str) -> i64 {
    let res = rt.db_for_test().query(sql, &Params::new()).await.expect("consulta");
    res.rows
        .first()
        .and_then(|r| r.as_object())
        .and_then(|o| o.values().next().cloned())
        .and_then(|v| v.as_i64())
        .unwrap_or(-1)
}

#[tokio::test]
async fn la_tabla_de_historial_existe_y_admite_un_tramo() {
    let rt = fresh().await;
    sesion_legacy(&rt, "s1", "m12", "2026-07-19T20:00:00+00:00", None).await;
    asignacion(&rt, "a1", "s1", "m12", "op-1", None).await.expect("un tramo vivo");
    assert_eq!(contar(&rt, "SELECT COUNT(*) FROM tables_session_assignment").await, 1);
}

#[tokio::test]
async fn una_sesion_no_puede_tener_dos_tramos_vivos_a_la_vez() {
    // Es LA invariante: una cuenta está en una mesa, no en dos. Sin esto volveríamos al fallo que
    // motivó el ADR — tres mesas ocupadas por el mismo pedido y ninguna liberándose.
    let rt = fresh().await;
    sesion_legacy(&rt, "s1", "m12", "2026-07-19T20:00:00+00:00", None).await;
    asignacion(&rt, "a1", "s1", "m12", "op-1", None).await.expect("el primero entra");

    let err = asignacion(&rt, "a2", "s1", "m8", "op-2", None).await;
    assert!(err.is_err(), "no puede haber dos tramos sin cerrar para la misma sesión");

    // Cerrando el primero, el segundo sí entra: eso es exactamente «mover de mesa».
    rt.db_for_test()
        .execute(
            "UPDATE tables_session_assignment SET released_at = '2026-07-19T20:45:00+00:00',
                 release_reason = 'moved' WHERE id = 'a1'",
            &Params::new(),
        )
        .await
        .unwrap();
    asignacion(&rt, "a2", "s1", "m8", "op-2", None).await.expect("tras cerrar el anterior, entra");
    assert_eq!(contar(&rt, "SELECT COUNT(*) FROM tables_session_assignment").await, 2);
}

#[tokio::test]
async fn el_mismo_operation_id_no_se_escribe_dos_veces() {
    // Idempotencia: el relay puede reentregar y el camarero puede tocar dos veces. Un `operation_id`
    // repetido es la MISMA operación, no dos tramos.
    let rt = fresh().await;
    sesion_legacy(&rt, "s1", "m12", "2026-07-19T20:00:00+00:00", None).await;
    asignacion(&rt, "a1", "s1", "m12", "op-1", Some("2026-07-19T20:45:00+00:00")).await.unwrap();

    let repe = asignacion(&rt, "a2", "s1", "m8", "op-1", None).await;
    assert!(repe.is_err(), "el mismo operation_id no puede crear otro tramo");
}

#[tokio::test]
async fn un_motivo_inventado_se_rechaza() {
    // El motivo lo deriva el handler de un juego cerrado (ADR-0146). Si alguien escribe cualquier
    // cosa, el historial queda contado pero no explicado.
    let rt = fresh().await;
    sesion_legacy(&rt, "s1", "m12", "2026-07-19T20:00:00+00:00", None).await;
    let err = rt
        .db_for_test()
        .execute(
            "INSERT INTO tables_session_assignment (id, hub_id, session_id, table_id, assigned_at,
                 assignment_reason, release_reason, operation_id, is_deleted, created_at)
             VALUES ('a9', 'h1', 's1', 'm12', '2026-07-19T20:00:00+00:00', 'porque-si', '', 'op-9', 0,
                     '2026-07-19T20:00:00+00:00')",
            &Params::new(),
        )
        .await;
    assert!(err.is_err(), "un motivo fuera del juego cerrado se rechaza");
}

#[tokio::test]
async fn el_backfill_da_historial_a_las_sesiones_que_YA_existian() {
    // Los hubs en marcha tienen sesiones sin historial. La migración les crea su primer tramo, o
    // esas mesas quedarían fuera de las estadísticas para siempre.
    let rt = fresh().await;
    sesion_legacy(&rt, "s-viva", "m12", "2026-07-19T20:00:00+00:00", None).await;
    sesion_legacy(&rt, "s-cerrada", "m8", "2026-07-19T18:00:00+00:00", Some("2026-07-19T19:30:00+00:00")).await;

    let backfill = std::fs::read_to_string(
        mdir("tables").join("migrations/sqlite/005_session_assignment.sql"),
    )
    .expect("la migración 005");
    // Se queda solo con el INSERT del backfill: fuera los comentarios (van antes de la sentencia,
    // así que sin quitarlos el trozo no «empieza por INSERT») y el resto de DDL.
    let sin_comentarios: String = backfill
        .lines()
        .filter(|l| !l.trim_start().starts_with("--"))
        .collect::<Vec<_>>()
        .join("\n");
    let backfill = sin_comentarios
        .split(';')
        .map(str::trim)
        .filter(|s| s.to_uppercase().starts_with("INSERT"))
        .collect::<Vec<_>>()
        .join(";");
    assert!(!backfill.is_empty(), "la migración debe traer su backfill");

    // Se ejecuta DOS veces: un backfill que duplica al reaplicarse es peor que no tenerlo.
    for _ in 0..2 {
        rt.db_for_test().execute(&backfill, &Params::new()).await.expect("backfill");
    }

    assert_eq!(
        contar(&rt, "SELECT COUNT(*) FROM tables_session_assignment").await,
        2,
        "una fila por sesión, y reaplicar no duplica"
    );
    assert_eq!(
        contar(
            &rt,
            "SELECT COUNT(*) FROM tables_session_assignment
             WHERE session_id = 's-viva' AND released_at IS NULL AND assignment_reason = 'opened'"
        )
        .await,
        1,
        "la sesión viva queda con su tramo ABIERTO"
    );
    assert_eq!(
        contar(
            &rt,
            "SELECT COUNT(*) FROM tables_session_assignment
             WHERE session_id = 's-cerrada' AND released_at = '2026-07-19T19:30:00+00:00'
               AND release_reason = 'closed'"
        )
        .await,
        1,
        "la cerrada queda con su tramo cerrado a la hora en que se cerró"
    );
}
