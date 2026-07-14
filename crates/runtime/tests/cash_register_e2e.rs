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

#[tokio::test]
async fn sale_by_another_cashier_lands_in_the_open_session() {
    // ADR-0130: la sesión de caja es del TERMINAL, no del cajero — es el patrón unánime del mercado
    // (Odoo, Loyverse, Square, Lightspeed, Shopify): se abre una vez y TODOS los cajeros venden
    // dentro de ella.
    //
    // El bug que esto fija PIERDE DINERO: `current_session` resolvía la sesión abierta del HUB, pero
    // `_movement_for_open_session` la buscaba del USUARIO ACTIVO. Si la cajera A abría la caja y
    // cobraba la B, el INSERT ... SELECT no casaba ninguna fila → NO se insertaba el movimiento, SIN
    // ERROR, y el efectivo de esa venta desaparecía del arqueo (mientras el KPI seguía diciendo que
    // había caja abierta).
    if !wasm() || !mdir("sales").join("dist/handler.wasm").exists() { eprintln!("SKIP"); return; }
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("taxes")).await.unwrap();
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap();
    rt.install_from_dir(&mdir("invoice")).await.unwrap();
    rt.install_from_dir(&mdir("cash_register")).await.unwrap();
    rt.install_from_dir(&mdir("sales")).await.unwrap();

    // La cajera A (u1) abre la caja del turno.
    let cajera_a = RequestContext::new("h1", "u1", ["*".to_string()]);
    let sid = open_session(&rt, &cajera_a, 0).await;

    // Entra la cajera B (u2) —relevo, o simplemente otro cajero en el mismo terminal— y cobra.
    let cajera_b = RequestContext::new("h1", "u2", ["*".to_string()]);
    rt.execute_command("sales.complete_sale", &params(json!({
        "tax_included": false,
        "items": [{ "product_name": "Corte", "price": 3000, "quantity": 1, "tax_rate": 0.0 }]
    })), &cajera_b).await.unwrap();
    rt.drain_outbox().await.unwrap();

    let movs = rt.execute_query("cash_register.movements.list", &params(json!({"session_id": sid})), &cajera_a).await.unwrap();
    assert_eq!(movs.len(), 1, "el efectivo cobrado por OTRO cajero debe entrar en la sesión abierta del terminal");
    assert_eq!(movs[0]["amount"].as_i64().unwrap(), 3000);
    // Y queda la traza de QUIÉN cobró: la sesión es del terminal, la responsabilidad es de la persona.
    assert_eq!(movs[0]["employee_id"], json!("u2"), "el movimiento atribuye la venta al cajero que cobró");
}
