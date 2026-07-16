//! E2E real del módulo `cash_register` (portado de old_modules/m_cash_register v1.2.6).
//! Sesiones de caja: apertura, movimientos, arqueo por denominaciones (WASM), cierre
//! con reconciliación (expected = opening + Σ movimientos; difference = closing - expected),
//! y la cadena sale.completed → movimiento de caja en la sesión abierta.
use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params { v.as_object().cloned().unwrap_or_default() }
fn mdir(n: &str) -> PathBuf { PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules").join(n) }
fn admin() -> RequestContext { RequestContext::new("h1", "u1", ["*".to_string()]) }
fn wasm() -> bool { mdir("cash_register").join("dist/handler.wasm").exists() }

async fn rt_cr() -> Runtime {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
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
    let rt = rt_cr().await;
    let reg = rt.registry();
    assert!(reg.is_installed("cash_register"));
    assert!(reg.get_command("cash_register.session.open").is_some());
    assert!(reg.get_command("cash_register.count.add").is_some());
    assert_eq!(reg.listeners_for("sale.completed"), ["cash_register.record_sale"]);
}

#[tokio::test]
async fn open_movements_close_reconciles() {
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
    assert_eq!(sum[0]["total_sales"].as_i64().unwrap(), 5000);
    // FIX SIGNO (QA 2026-06-25): el desglose se presenta como MAGNITUD POSITIVA — un refund
    // almacenado en -1000 se reporta como 1000 (la query niega el SUM de salidas).
    assert_eq!(sum[0]["total_refunds"].as_i64().unwrap(), 1000);
    assert_eq!(sum[0]["movement_count"], json!(4));
}

#[tokio::test]
async fn add_count_wasm_sums_denominations() {
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
    // Cadena cross-módulo completa: inventory+customers+invoice+sales+cash_register.
    if !wasm() || !mdir("sales").join("dist/handler.wasm").exists() { eprintln!("SKIP"); return; }
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("taxes")).await.unwrap(); // inventory depende de taxes (ADR-0066)
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap();
    rt.install_from_dir(&mdir("invoice")).await.unwrap();
    rt.install_from_dir(&mdir("cash_register")).await.unwrap();
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    let ctx = admin();

    // sesión abierta del usuario activo (u1).
    let sid = open_session(&rt, &ctx, 0).await;

    // venta de 30 → cash_register.record_sale añade un movimiento 'sale' de 30 a la sesión.
    rt.execute_command("sales.complete_sale", &params(json!({
        "tax_included": false,
        "items": [{ "product_name": "X", "price": 3000, "quantity": 1, "tax_rate": 0.0 }]
    })), &ctx).await.unwrap();
    // Entrega asíncrona: el relay procesa sale.completed → cash_register.record_sale.
    rt.drain_outbox().await.unwrap();

    let movs = rt.execute_query("cash_register.movements.list", &params(json!({"session_id": sid})), &ctx).await.unwrap();
    assert_eq!(movs.len(), 1, "la venta debe registrar 1 movimiento de caja");
    assert_eq!(movs[0]["movement_type"], json!("sale"));
    assert_eq!(movs[0]["amount"].as_i64().unwrap(), 3000);
}

/// El CAJÓN es efectivo FÍSICO (QA restaurante 07-16, P0 del arqueo): una venta con
/// TARJETA se registra (visible en movimientos y KPI de ventas) pero NO infla el
/// efectivo esperado — con día mixto, el arqueo debe cuadrar contra lo contado.
#[tokio::test]
async fn card_sales_do_not_inflate_expected_cash() {
    let rt = rt_cr().await;
    let ctx = admin();
    rt.execute_command("cash_register.session.open", &params(json!({
        "register_id": null, "session_number": "CARD-1", "opening_balance": 10000, "opening_notes": ""
    })), &ctx).await.unwrap();
    let sid = rt.execute_query("cash_register.sessions.list", &Params::new(), &ctx).await.unwrap()
        .last().unwrap()["id"].as_str().unwrap().to_string();

    // Venta en efectivo (+3000) y venta con tarjeta (+2500).
    rt.execute_command("cash_register.movement.add", &params(json!({
        "session_id": sid, "movement_type": "sale", "amount": 3000, "payment_method": "cash",
        "sale_reference": "s-cash", "description": "venta efectivo"
    })), &ctx).await.unwrap();
    rt.execute_command("cash_register.movement.add", &params(json!({
        "session_id": sid, "movement_type": "sale", "amount": 2500, "payment_method": "card",
        "sale_reference": "s-card", "description": "venta tarjeta"
    })), &ctx).await.unwrap();

    // KPI en vivo: el esperado del CAJÓN solo suma efectivo.
    let cur = rt.execute_query("cash_register.current_session", &Params::new(), &ctx).await.unwrap();
    assert_eq!(cur[0]["expected_total"].as_i64().unwrap(), 13000,
        "la tarjeta no entra en el cajón (10000 + 3000)");
    // Las ventas del día sí cuentan TODOS los métodos.
    assert_eq!(cur[0]["total_sales"].as_i64().unwrap(), 5500);

    // Cierre: contado = 13000 → diferencia CERO con día mixto.
    rt.execute_command("cash_register.session.close", &params(json!({
        "session_id": sid, "closing_balance": 13000, "closing_notes": ""
    })), &ctx).await.unwrap();
    let closed = rt.execute_query("cash_register.sessions.list", &params(json!({"session_number": "CARD-1"})), &ctx)
        .await.unwrap();
    let s = closed.iter().find(|s| s["id"] == json!(sid)).unwrap();
    assert_eq!(s["expected_balance"].as_i64().unwrap(), 13000);
    assert_eq!(s["difference"].as_i64().unwrap(), 0, "día mixto cuadra contra el efectivo contado");
}
