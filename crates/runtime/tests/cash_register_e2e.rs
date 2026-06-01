//! E2E real del módulo `cash_register` (portado de old_modules/m_cash_register v1.2.6).
//! Sesiones de caja: apertura, movimientos, arqueo por denominaciones (WASM), cierre
//! con reconciliación (expected = opening + Σ movimientos; difference = closing - expected),
//! y la cadena sale.completed → movimiento de caja en la sesión abierta.
use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params { v.as_object().cloned().unwrap_or_default() }
fn mdir(n: &str) -> PathBuf { PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../modules").join(n) }
fn admin() -> RequestContext { RequestContext::new("h1", "u1", ["*".to_string()]) }
fn wasm() -> bool { mdir("cash_register").join("dist/handler.wasm").exists() }

fn rt_cr() -> Runtime {
    let db = SqliteAdapter::open_in_memory().unwrap();
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("cash_register")).expect("instalar cash_register");
    rt
}

fn open_session(rt: &Runtime, ctx: &RequestContext, opening: f64) -> String {
    rt.execute_command("cash_register.session.open", &params(json!({
        "register_id": null, "session_number": "AB-260531-1000",
        "opening_balance": opening, "opening_notes": ""
    })), ctx).unwrap();
    rt.execute_query("cash_register.sessions.list", &Params::new(), ctx).unwrap()
        .last().unwrap()["id"].as_str().unwrap().to_string()
}

#[test]
fn install_registers_capabilities() {
    let rt = rt_cr();
    let reg = rt.registry();
    assert!(reg.is_installed("cash_register"));
    assert!(reg.get_command("cash_register.session.open").is_some());
    assert!(reg.get_command("cash_register.count.add").is_some());
    assert_eq!(reg.listeners_for("sale.completed"), ["cash_register.record_sale"]);
}

#[test]
fn open_movements_close_reconciles() {
    let rt = rt_cr();
    let ctx = admin();
    let sid = open_session(&rt, &ctx, 100.0);

    // dos movimientos: venta +50, retirada -20.
    rt.execute_command("cash_register.movement.add", &params(json!({
        "session_id": sid, "movement_type": "sale", "amount": 50.0, "payment_method": "cash",
        "sale_reference": "", "description": "venta"
    })), &ctx).unwrap();
    rt.execute_command("cash_register.movement.add", &params(json!({
        "session_id": sid, "movement_type": "out", "amount": -20.0, "payment_method": "cash",
        "sale_reference": "", "description": "retirada"
    })), &ctx).unwrap();

    // cierre declarando 135 contados → expected = 100+50-20 = 130; difference = 135-130 = 5.
    rt.execute_command("cash_register.session.close", &params(json!({
        "session_id": sid, "closing_balance": 135.0, "closing_notes": ""
    })), &ctx).unwrap();

    let sessions = rt.execute_query("cash_register.sessions.list", &Params::new(), &ctx).unwrap();
    let s = &sessions[0];
    assert_eq!(s["status"], json!("closed"));
    assert_eq!(s["expected_balance"].as_f64().unwrap(), 130.0);
    assert_eq!(s["difference"].as_f64().unwrap(), 5.0);
}

#[test]
fn session_summary_aggregates_by_type() {
    let rt = rt_cr();
    let ctx = admin();
    let sid = open_session(&rt, &ctx, 0.0);
    for (ty, amt) in [("sale", 30.0), ("sale", 20.0), ("refund", -10.0), ("in", 5.0)] {
        rt.execute_command("cash_register.movement.add", &params(json!({
            "session_id": sid, "movement_type": ty, "amount": amt, "payment_method": "cash",
            "sale_reference": "", "description": ""
        })), &ctx).unwrap();
    }
    let sum = rt.execute_query("cash_register.session.summary", &params(json!({"session_id": sid})), &ctx).unwrap();
    assert_eq!(sum[0]["total_sales"].as_f64().unwrap(), 50.0);
    assert_eq!(sum[0]["total_refunds"].as_f64().unwrap(), -10.0);
    assert_eq!(sum[0]["movement_count"], json!(4));
}

#[test]
fn add_count_wasm_sums_denominations() {
    if !wasm() { eprintln!("SKIP: cash_register handler.wasm ausente"); return; }
    let rt = rt_cr();
    let ctx = admin();
    let sid = open_session(&rt, &ctx, 0.0);
    // 2×50 + 5×20 + 10×1 = 210.
    let res = rt.execute_command("cash_register.count.add", &params(json!({
        "session_id": sid, "count_type": "opening",
        "denominations": { "bills": { "50": 2, "20": 5 }, "coins": { "1": 10 } }
    })), &ctx).expect("count.add WASM");
    assert_eq!(res["operations"], json!(1));
    let counts = rt.execute_query("cash_register.counts.list", &params(json!({"session_id": sid})), &ctx).unwrap();
    assert_eq!(counts.len(), 1);
    assert_eq!(counts[0]["total"].as_f64().unwrap(), 210.0);
}

#[test]
fn sale_completed_records_cash_movement() {
    // Cadena cross-módulo completa: inventory+customers+invoice+sales+cash_register.
    if !wasm() || !mdir("sales").join("dist/handler.wasm").exists() { eprintln!("SKIP"); return; }
    let db = SqliteAdapter::open_in_memory().unwrap();
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("inventory")).unwrap();
    rt.install_from_dir(&mdir("customers")).unwrap();
    rt.install_from_dir(&mdir("invoice")).unwrap();
    rt.install_from_dir(&mdir("cash_register")).unwrap();
    rt.install_from_dir(&mdir("sales")).unwrap();
    let ctx = admin();

    // sesión abierta del usuario activo (u1).
    let sid = open_session(&rt, &ctx, 0.0);

    // venta de 30 → cash_register.record_sale añade un movimiento 'sale' de 30 a la sesión.
    rt.execute_command("sales.complete_sale", &params(json!({
        "tax_included": false,
        "items": [{ "product_name": "X", "price": 30.0, "quantity": 1, "tax_rate": 0.0 }]
    })), &ctx).unwrap();

    let movs = rt.execute_query("cash_register.movements.list", &params(json!({"session_id": sid})), &ctx).unwrap();
    assert_eq!(movs.len(), 1, "la venta debe registrar 1 movimiento de caja");
    assert_eq!(movs[0]["movement_type"], json!("sale"));
    assert_eq!(movs[0]["amount"].as_f64().unwrap(), 30.0);
}
