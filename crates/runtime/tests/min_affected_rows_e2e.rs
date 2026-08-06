//! hub#140 — un command SQL que afecta 0 filas NO debe emitir sus eventos.
//!
//! Antes de este fix, un `UPDATE ... WHERE` que no casa devolvía OK y el runtime escribía todos
//! los `emit` declarados en el outbox (y notificaba al WS). El runtime no distinguía una mutación
//! real de un no-op: confirmar por segunda vez una cita, o confirmar un `booking_id` inexistente,
//! emitían su evento igual (ERPlora/appointments#18, ERPlora/online_booking#2).
//!
//! Estos tests ejercen el contrato de mutación `min_affected_rows` contra un Postgres real:
//!  - 0 filas + `min_affected_rows: 1` → la tx revienta con `MinAffectedRows` (kind `not_found`) y
//!    NO queda ninguna fila en `_event_outbox` para ese evento (escritura atómica).
//!  - mutación real (1 fila) → commitea, el item cambia de estado y SÍ emite `w140.item.confirmed`.
//!  - ausencia del campo (legacy) → comportamiento de siempre: emite aunque el WHERE case 0 filas
//!    (compatibilidad hacia atrás: ningún módulo publicado declara el campo nuevo).
//!
//! No hay adaptador SQLite desde ADR-0154 (Hub Postgres-only), así que la "paridad SQLite/PG" del
//! issue se cubre con el único motor que existe.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_w140")
}

fn admin_ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

/// Cuenta las filas pendientes del outbox para un `event_name` dado, en este hub. Va directo al
/// adaptador (el runtime lo expone para tests) y filtra por nombre — es el oráculo de "¿se emitió?".
async fn outbox_count(rt: &Runtime, hub_id: &str, event_name: &str) -> i64 {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("event_name".into(), json!(event_name));
    let rows = rt
        .db()
        .query(
            "SELECT COUNT(*) AS n FROM _event_outbox WHERE hub_id = :hub_id AND event_name = :event_name",
            &p,
        )
        .await
        .expect("contar el outbox")
        .rows;
    rows[0]["n"]
        .as_i64()
        .unwrap_or_else(|| panic!("COUNT devolvió algo raro: {rows:?}"))
}

async fn fresh_runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture_dir())
        .await
        .expect("instalar w140");
    rt
}

async fn create_item(rt: &Runtime, ctx: &RequestContext, name: &str) -> String {
    rt.execute_command("w140.items.create", &params(json!({ "name": name })), ctx)
        .await
        .expect("crear item");
    let id = rt
        .execute_query("w140.items.list", &Params::new(), ctx)
        .await
        .unwrap()
        .into_iter()
        .find(|r| r["name"] == json!(name))
        .expect("el item recién creado está en la lista")["id"]
        .as_str()
        .unwrap()
        .to_string();
    id
}

#[tokio::test]
async fn cero_filas_con_min_afectados_falla_con_not_found_y_no_emite() {
    // El caso central de hub#140: confirmar un item INEXISTENTE. El UPDATE casa 0 filas; con
    // `min_affected_rows: 1` la tx revienta entera y NO se escribe `w140.item.confirmed` en el
    // outbox. Antes del fix esto devolvía OK y emitía el evento.
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();

    let err = rt
        .execute_command(
            "w140.items.confirm",
            &params(json!({ "item_id": "no-existe" })),
            &ctx,
        )
        .await
        .expect_err("0 filas con min_affected_rows:1 debe fallar");

    match err {
        RuntimeError::MinAffectedRows {
            command,
            required,
            affected,
            kind,
        } => {
            assert_eq!(command, "w140.items.confirm");
            assert_eq!(required, 1, "el mínimo exigido es el del manifest");
            assert_eq!(
                affected, 0,
                "el UPDATE sobre un item inexistente muta 0 filas"
            );
            assert_eq!(
                kind.as_str(),
                "not_found",
                "0 filas → not_found (no conflict)"
            );
        }
        other => panic!("esperaba MinAffectedRows, llegó {other:?}"),
    }

    assert_eq!(
        outbox_count(&rt, "h1", "w140.item.confirmed").await,
        0,
        "la tx revertida NO debe haber escrito el evento en el outbox"
    );
}

#[tokio::test]
async fn mutacion_real_emite_y_cambia_estado() {
    // El lado feliz del contrato: cuando el UPDATE casa 1 fila, la gate pasa, la tx commitea y el
    // evento SÍ se emite. Garantiza que el fix no ahogue las mutaciones legítimas.
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();
    let id = create_item(&rt, &ctx, "Café").await;

    rt.execute_command(
        "w140.items.confirm",
        &params(json!({ "item_id": id })),
        &ctx,
    )
    .await
    .expect("confirmar un item existente debe commitear");

    let rows = rt
        .execute_query("w140.items.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(
        rows.iter().find(|r| r["id"] == json!(id)).unwrap()["status"],
        json!("confirmed"),
        "el item quedó confirmado en la BD"
    );
    assert_eq!(
        outbox_count(&rt, "h1", "w140.item.confirmed").await,
        1,
        "la mutación real SÍ escribe el evento en el outbox"
    );
}

#[tokio::test]
async fn confirmar_dos_veces_es_no_op_y_no_reemite() {
    // El caso de Appointments#18: confirmar una cita YA confirmada. La segunda vez el WHERE
    // (`status='pending'`) casa 0 filas → la gate corta como not_found y NO se reemite el evento.
    // Antes del fix, la segunda confirmación volvía a emitir `*.confirmed`.
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();
    let id = create_item(&rt, &ctx, "Té").await;

    rt.execute_command(
        "w140.items.confirm",
        &params(json!({ "item_id": id })),
        &ctx,
    )
    .await
    .expect("primera confirmación");

    let err = rt
        .execute_command(
            "w140.items.confirm",
            &params(json!({ "item_id": id })),
            &ctx,
        )
        .await
        .expect_err("segunda confirmación → 0 filas (ya confirmed)");
    assert!(
        matches!(err, RuntimeError::MinAffectedRows { kind, .. } if kind.as_str() == "not_found"),
        "la re-confirmación debe ser not_found, no OK: {err:?}"
    );

    assert_eq!(
        outbox_count(&rt, "h1", "w140.item.confirmed").await,
        1,
        "sólo la primera confirmación emitió — la segunda es no-op"
    );
}

#[tokio::test]
async fn sin_el_campo_legacy_emite_aunque_mutara_cero_filas() {
    // Compatibilidad hacia atrás (decisión: OPT-IN). Un command SIN `min_affected_rows` conserva el
    // comportamiento de siempre: emite su evento aunque el WHERE case 0 filas. Ningún módulo
    // publicado declara el campo nuevo, así que romper esto habría sido un P0 en 24 módulos.
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();

    rt.execute_command(
        "w140.items.legacy_touch",
        &params(json!({ "item_id": "no-existe" })),
        &ctx,
    )
    .await
    .expect("sin contrato de mutación, 0 filas sigue siendo OK (legacy)");

    assert_eq!(
        outbox_count(&rt, "h1", "w140.item.touched").await,
        1,
        "el command legacy emite aunque no mutara nada — compatibilidad hacia atrás"
    );
}

// ── hub#139: domain error channel ────────────────────────────────────────────────────────────

#[tokio::test]
async fn expect_rows_maps_zero_rows_to_a_namespaced_domain_error_and_does_not_emit() {
    // hub#139: `expect_rows` is the translatable flavour of `min_affected_rows`. A rejected
    // UPDATE must surface the module-declared, namespaced code (the UI translates by code via
    // the module i18n catalog, ADR-0055) instead of the generic MinAffectedRows variant — and
    // the whole tx (mutation + outbox) must still roll back.
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();

    let err = rt
        .execute_command(
            "w140.items.consume",
            &params(json!({ "item_id": "out-of-stock" })),
            &ctx,
        )
        .await
        .expect_err("0 affected rows must become a translatable business rejection");
    assert!(
        matches!(
            err,
            RuntimeError::Domain { ref code, ref message }
                if code == "w140.insufficient_stock" && message == "Not enough stock"
        ),
        "expected Domain with the manifest-declared code/message, got {err:?}"
    );

    assert_eq!(
        outbox_count(&rt, "h1", "w140.item.consumed").await,
        0,
        "the rejected UPDATE rolls back its emit as well"
    );
}

#[tokio::test]
async fn expect_rows_lets_a_real_mutation_commit_and_emit() {
    // Happy path: when the gate holds, `expect_rows` must be invisible — the tx commits and the
    // declared event reaches the outbox exactly like a legacy command.
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();
    let id = create_item(&rt, &ctx, "Beans").await;

    rt.execute_command("w140.items.consume", &params(json!({ "item_id": id })), &ctx)
        .await
        .expect("a matching UPDATE passes the expect_rows gate");

    assert_eq!(
        outbox_count(&rt, "h1", "w140.item.consumed").await,
        1,
        "the committed mutation emits its declared event"
    );
}
