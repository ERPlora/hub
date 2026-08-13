//! E2E real del módulo `cash_register` (portado de old_modules/m_cash_register v1.2.6).
//! Sesiones de caja: apertura, movimientos, arqueo por denominaciones (WASM), cierre
//! con reconciliación (expected = opening + Σ movimientos; difference = closing - expected),
//! y la cadena sale.completed → movimiento de caja en la sesión abierta.
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{EventSink, EventSource, RequestContext, Runtime};
use serde_json::json;

/// Sink mínimo que captura los NOMBRES de los eventos emitidos (para asertar el `emit` de un command).
#[derive(Default, Debug)]
struct Sink {
    names: Mutex<Vec<String>>,
}
impl EventSink for Sink {
    fn emit(&self, _source: EventSource<'_>, name: &str, _payload: &serde_json::Value) {
        self.names.lock().unwrap().push(name.to_string());
    }
}

fn params(v: serde_json::Value) -> Params { v.as_object().cloned().unwrap_or_default() }
/// Céntimos de un agregado: Postgres devuelve `SUM(bigint)` como NUMERIC → JSON **string**
/// (`"5000"`), no número. Acepta ambas representaciones.
fn cents(v: &serde_json::Value) -> i64 {
    v.as_i64()
        .or_else(|| v.as_str().and_then(|s| s.parse::<f64>().ok()).map(|f| f.round() as i64))
        .unwrap_or_else(|| panic!("no es un importe numérico: {v:?}"))
}
fn mdir(n: &str) -> PathBuf { erplora_runtime::e2e_support::modules_root().join(n) }
fn admin() -> RequestContext { RequestContext::new("h1", "u1", ["*".to_string()]) }
fn wasm() -> bool { mdir("cash_register").join("dist/handler.wasm").exists() }

/// Id of the CASH payment method from the hub's seeded catalog (hub#594): with the runtime and
/// the ctx sharing "h1", the `sales` seed is visible and `complete_sale` enforces
/// `payment_method_id` against it instead of silently degrading.
async fn cash_method_id(rt: &Runtime, ctx: &RequestContext) -> String {
    let rows = rt
        .execute_query("sales.payment_methods", &Params::new(), ctx)
        .await
        .expect("sales.payment_methods");
    rows.iter()
        .find(|r| r["type"] == json!("cash"))
        .unwrap_or_else(|| panic!("the hub's catalog must carry the `cash` method: {rows:?}"))["id"]
        .as_str()
        .expect("payment method id")
        .to_string()
}

async fn rt_cr() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&mdir("cash_register")).await.expect("instalar cash_register");
    rt
}

async fn open_session(rt: &Runtime, ctx: &RequestContext, opening: i64) -> String {
    rt.execute_command("cash_register.session.open", &params(json!({
        "register_id": null, "session_number": "AB-260531-1000",
        "opening_balance": opening, "opening_notes": ""
    })), ctx).await.unwrap();
    rt.execute_query("cash_register.sessions.list", &Params::new(), ctx).await.unwrap()
        .last().unwrap()["id"].as_str().unwrap().to_string()
}

#[tokio::test]
async fn install_registers_capabilities() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = rt_cr().await;
    let reg = rt.registry();
    assert!(reg.is_installed("cash_register"));
    assert!(reg.get_command("cash_register.session.open").is_some());
    assert!(reg.get_command("cash_register.count.add").is_some());
    assert_eq!(reg.listeners_for("sale.completed"), ["cash_register.record_sale"]);
}

#[tokio::test]
async fn open_movements_close_reconciles() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = rt_cr().await;
    let ctx = admin();
    let sid = open_session(&rt, &ctx, 10000).await;

    // dos movimientos: venta +50, retirada -20.
    rt.execute_command("cash_register.movement.add", &params(json!({
        "session_id": sid, "movement_type": "sale", "amount": 5000, "payment_method": "cash",
        "sale_reference": "", "description": "venta"
    })), &ctx).await.unwrap();
    rt.execute_command("cash_register.movement.add", &params(json!({
        "session_id": sid, "movement_type": "out", "amount": -2000, "payment_method": "cash",
        "sale_reference": "", "description": "retirada"
    })), &ctx).await.unwrap();

    // cierre declarando 135 contados → expected = 100+50-20 = 130; difference = 135-130 = 5.
    rt.execute_command("cash_register.session.close", &params(json!({
        "session_id": sid, "closing_balance": 13500, "closing_notes": ""
    })), &ctx).await.unwrap();

    let sessions = rt.execute_query("cash_register.sessions.list", &Params::new(), &ctx).await.unwrap();
    let s = &sessions[0];
    assert_eq!(s["status"], json!("closed"));
    assert_eq!(s["expected_balance"].as_i64().unwrap(), 13000);
    assert_eq!(s["difference"].as_i64().unwrap(), 500);
}

#[tokio::test]
async fn session_summary_aggregates_by_type() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = rt_cr().await;
    let ctx = admin();
    let sid = open_session(&rt, &ctx, 0).await;
    for (ty, amt) in [("sale", 3000), ("sale", 2000), ("refund", -1000), ("in", 500)] {
        rt.execute_command("cash_register.movement.add", &params(json!({
            "session_id": sid, "movement_type": ty, "amount": amt, "payment_method": "cash",
            "sale_reference": "", "description": ""
        })), &ctx).await.unwrap();
    }
    let sum = rt.execute_query("cash_register.session.summary", &params(json!({"session_id": sid})), &ctx).await.unwrap();
    assert_eq!(cents(&sum[0]["total_sales"]), 5000);
    // FIX SIGNO (QA 2026-06-25): el desglose se presenta como MAGNITUD POSITIVA — un refund
    // almacenado en -1000 se reporta como 1000 (la query niega el SUM de salidas).
    assert_eq!(cents(&sum[0]["total_refunds"]), 1000);
    assert_eq!(sum[0]["movement_count"], json!(4));
}

#[tokio::test]
async fn add_count_wasm_sums_denominations() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm() { eprintln!("SKIP: cash_register handler.wasm ausente"); return; }
    let rt = rt_cr().await;
    let ctx = admin();
    let sid = open_session(&rt, &ctx, 0).await;
    // 2×50 + 5×20 + 10×1 = 210.
    let res = rt.execute_command("cash_register.count.add", &params(json!({
        "session_id": sid, "count_type": "opening",
        "denominations": { "bills": { "50": 2, "20": 5 }, "coins": { "1": 10 } }
    })), &ctx).await.expect("count.add WASM");
    assert_eq!(res["operations"], json!(1));
    let counts = rt.execute_query("cash_register.counts.list", &params(json!({"session_id": sid})), &ctx).await.unwrap();
    assert_eq!(counts.len(), 1);
    assert_eq!(counts[0]["total"].as_i64().unwrap(), 21000);
}

#[tokio::test]
async fn sale_completed_records_cash_movement() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // Cadena cross-módulo completa: inventory+customers+invoice+sales+cash_register.
    if !wasm() || !mdir("sales").join("dist/handler.wasm").exists() { eprintln!("SKIP"); return; }
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&mdir("taxes")).await.unwrap(); // inventory depende de taxes (ADR-0066)
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap();
    rt.install_from_dir(&mdir("cash_register")).await.unwrap();
    // `sales` ANTES que `invoice`: invoice declara `depends_on: [taxes, sales]` (la read `sales.get`
    // de create_from_sale, hub#108) y el instalador exige el orden topológico.
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    rt.install_from_dir(&mdir("invoice")).await.unwrap();
    let ctx = admin();

    // sesión abierta del usuario activo (u1).
    let sid = open_session(&rt, &ctx, 0).await;

    // venta de 30 → cash_register.record_sale añade un movimiento 'sale' de 30 a la sesión.
    rt.execute_command("sales.complete_sale", &params(json!({
        // `idempotency_key` of the charge attempt (sales#20, mandatory since v2.13.x).
        "idempotency_key": "cash-e2e-movimiento-de-caja",
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "tax_included": false,
        "items": [{ "product_name": "X", "price": 3000, "quantity": 1_000_000, "tax_rate": 0.0 }]
    })), &ctx).await.unwrap();
    // Entrega asíncrona: el relay procesa sale.completed → cash_register.record_sale.
    rt.drain_outbox().await.unwrap();

    let movs = rt.execute_query("cash_register.movements.list", &params(json!({"session_id": sid})), &ctx).await.unwrap();
    assert_eq!(movs.len(), 1, "la venta debe registrar 1 movimiento de caja");
    assert_eq!(movs[0]["movement_type"], json!("sale"));
    assert_eq!(movs[0]["amount"].as_i64().unwrap(), 3000);
}

// ── P1 (ADR-0054 T3): evento de DATO-LISTO para el refresco en vivo del KPI de caja ───────────────
// El widget `cash_register.current_session` refrescaba al oír `sale.completed` (evento DISPARADOR),
// pero el movimiento de caja lo escribe `record_sale` de forma ASÍNCRONA (relay) → carrera: el
// re-query corría antes de que el movimiento estuviera en la BD. El arreglo: los comandos que
// ESCRIBEN un movimiento emiten `cash_register.movement_added` (evento de DATO-LISTO, en el MISMO
// tx transaccional del outbox), y el widget refresca con ese → cero carrera.

#[tokio::test]
async fn movement_add_emits_movement_added() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // Path directo determinista: `movement.add` escribe un movimiento → debe emitir el evento.
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    rt.install_from_dir(&mdir("cash_register")).await.expect("instalar cash_register");
    let ctx = admin();
    let sid = open_session(&rt, &ctx, 10000).await;

    rt.execute_command("cash_register.movement.add", &params(json!({
        "session_id": sid, "movement_type": "sale", "amount": 5000, "payment_method": "cash",
        "sale_reference": "", "description": "venta"
    })), &ctx).await.unwrap();

    let names = sink.names.lock().unwrap();
    assert!(
        names.iter().any(|n| n == "cash_register.movement_added"),
        "un movimiento de caja debe emitir `cash_register.movement_added` (dato-listo para el KPI); emitidos: {names:?}"
    );
}

#[tokio::test]
async fn record_sale_emits_movement_added_after_relay() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // Path REAL del P1: venta → (relay) record_sale escribe el movimiento Y emite el evento, en el
    // mismo tx del outbox → cuando el widget lo recibe, el dato YA está en la BD.
    if !wasm() || !mdir("sales").join("dist/handler.wasm").exists() { eprintln!("SKIP"); return; }
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    rt.install_from_dir(&mdir("taxes")).await.unwrap();
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap();
    rt.install_from_dir(&mdir("cash_register")).await.unwrap();
    // `sales` ANTES que `invoice`: invoice declara `depends_on: [taxes, sales]` (la read `sales.get`
    // de create_from_sale, hub#108) y el instalador exige el orden topológico.
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    rt.install_from_dir(&mdir("invoice")).await.unwrap();
    let ctx = admin();
    let sid = open_session(&rt, &ctx, 0).await;

    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": "cash-e2e-movement-added-por-el-relay",
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "tax_included": false,
        "items": [{ "product_name": "X", "price": 3000, "quantity": 1_000_000, "tax_rate": 0.0 }]
    })), &ctx).await.unwrap();
    rt.drain_outbox().await.unwrap(); // el relay corre record_sale (escribe el movimiento + emite)

    // Invariante del arreglo: el movimiento ESTÁ escrito Y el evento de dato-listo se emitió.
    let movs = rt.execute_query("cash_register.movements.list", &params(json!({"session_id": sid})), &ctx).await.unwrap();
    assert_eq!(movs.len(), 1, "la venta debe haber escrito el movimiento");
    let names = sink.names.lock().unwrap();
    assert!(
        names.iter().any(|n| n == "cash_register.movement_added"),
        "record_sale debe emitir `cash_register.movement_added` tras escribir el movimiento; emitidos: {names:?}"
    );
}
