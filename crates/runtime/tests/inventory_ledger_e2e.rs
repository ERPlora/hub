//! E2E del LIBRO DE MOVIMIENTOS de inventory (inventory#7 + decimales de #10, ADR-0135):
//! todo cambio de stock deja un movimiento inmutable en `inventory_stock_movement`,
//! con delta, saldo resultante, tipo, referencia al documento origen y `location_id`
//! (ubicación lógica predeterminada `<hub>:default`, resuelta cuando el caller no la envía).
//!
//!   * `stock.receive` (WASM) → movimiento `reception` con qty, stock_after y unit_cost.
//!   * `stock.adjust` = RECUENTO ABSOLUTO (fin de la ambigüedad absoluto-vs-delta de #7):
//!     payload {product_id, stock, reason}; motivo OBLIGATORIO (schema); el movimiento
//!     `count` registra la diferencia. Un recuento sin cambio no ensucia el ledger.
//!   * el listener de `sale.completed` → movimiento `sale` con reference = sale_id, y
//!     acepta CANTIDADES DECIMALES (#10: fin del truncado float→i64).
//!   * `sale.voided` → movimientos `void` con reference = sale_id, idempotentes.
//!   * un descuento RECHAZADO (sobreventa no permitida) o con `track_stock=0` NO deja
//!     movimiento: el ledger solo registra lo que ocurrió.
//!
//! `inventory_product.stock` queda como PROYECCIÓN del saldo (decisión de #7): los
//! consumidores actuales siguen leyéndolo; el ledger es la traza auditable.
use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(n: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules").join(n)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}
fn wasm_present() -> bool {
    mdir("inventory").join("dist/handler.wasm").exists()
}

async fn stack() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("taxes")).await.unwrap();
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap();
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    rt
}

async fn create_product(rt: &Runtime, ctx: &RequestContext, sku: &str, stock: i64) -> String {
    rt.execute_command("inventory.products.create", &params(json!({
        "name": sku, "sku": sku, "price": 1000, "cost": 250, "stock": stock,
        "low_stock_threshold": 5, "product_type": "physical",
        "ean13": null, "description": "", "tax_category_key": null, "image": ""
    })), ctx).await.unwrap();
    rt.execute_query("inventory.products.list", &params(json!({"search": sku})), ctx)
        .await.unwrap()[0]["id"].as_str().unwrap().to_string()
}

async fn stock_of(rt: &Runtime, ctx: &RequestContext, pid: &str) -> f64 {
    rt.execute_query("inventory.products.get", &params(json!({"product_id": pid})), ctx)
        .await.unwrap()[0]["stock"].as_f64().unwrap()
}

/// Movimientos de un producto vía la query pública (más reciente primero).
async fn movements(rt: &Runtime, ctx: &RequestContext, pid: &str) -> Vec<serde_json::Value> {
    rt.execute_query("inventory.stock.movements", &params(json!({"f_product_id": pid})), ctx)
        .await.unwrap()
}

async fn seed_sale(rt: &Runtime, sale_id: &str, lines: &[(&str, i64, f64)]) {
    let db = rt.db_for_test();
    db.execute(
        "INSERT INTO sales_sale (id, hub_id, sale_number, status, subtotal, tax_amount, \
         tax_breakdown, discount_amount, discount_percent, total, payment_method_name, \
         amount_tendered, change_due, customer_name, notes, source_module, channel, \
         is_deleted, created_at, updated_at) \
         VALUES (:id, 'h1', :id, 'completed', 1000, 0, '{}', 0, 0, 1000, 'cash', \
         1000, 0, '', '', 'pos', 'pos', 0, :now, :now)",
        &params(json!({ "id": sale_id, "now": "2026-07-16T10:00:00+00:00" })),
    ).await.unwrap();
    for (i, (product_id, is_service, qty)) in lines.iter().enumerate() {
        let pid = if product_id.is_empty() { json!(null) } else { json!(product_id) };
        db.execute(
            "INSERT INTO sales_sale_item (id, hub_id, sale_id, product_id, product_name, \
             product_sku, is_service, quantity, unit_price, discount_percent, tax_rate, \
             tax_class_name, net_amount, tax_amount, line_total, created_at) \
             VALUES (:id, 'h1', :sale_id, :product_id, :name, '', :is_service, :qty, 1000, 0, 0, \
             '', 1000, 0, 1000, :now)",
            &params(json!({ "id": format!("{sale_id}-L{i}"), "sale_id": sale_id, "product_id": pid,
                "name": format!("L{i}"), "is_service": is_service, "qty": qty,
                "now": "2026-07-16T10:00:00+00:00" })),
        ).await.unwrap();
    }
}

// ── Recepción ───────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn receive_creates_reception_movement_with_location_and_cost() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() { eprintln!("⚠ sin handler.wasm — saltado"); return; }
    let rt = stack().await;
    let ctx = admin();
    let pid = create_product(&rt, &ctx, "REC", 10).await;

    rt.execute_command("inventory.stock.receive", &params(json!({
        "items": [ { "product_id": pid, "qty": 4, "unit_cost": 180 } ]
    })), &ctx).await.unwrap();

    assert_eq!(stock_of(&rt, &ctx, &pid).await, 14.0);
    let movs = movements(&rt, &ctx, &pid).await;
    let m = movs.iter().find(|m| m["movement_type"] == json!("reception"))
        .expect("falta el movimiento de recepción");
    assert_eq!(m["qty"].as_f64().unwrap(), 4.0);
    assert_eq!(m["stock_after"].as_f64().unwrap(), 14.0);
    assert_eq!(m["unit_cost"].as_i64().unwrap(), 180);
    assert_eq!(m["location_id"], json!("h1:default"), "ubicación predeterminada resuelta");
}

// ── Recuento (ajuste ABSOLUTO con motivo) ───────────────────────────────────────────────

#[tokio::test]
async fn adjust_is_absolute_count_with_mandatory_reason() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = stack().await;
    let ctx = admin();
    let pid = create_product(&rt, &ctx, "CNT", 10).await;

    // Sin motivo → el schema lo rechaza ANTES de tocar la BD.
    let err = rt.execute_command("inventory.stock.adjust",
        &params(json!({ "product_id": pid, "stock": 7 })), &ctx).await;
    assert!(err.is_err(), "una corrección manual sin motivo debe rechazarse");

    // Recuento real: 10 → 7 (merma detectada).
    rt.execute_command("inventory.stock.adjust",
        &params(json!({ "product_id": pid, "stock": 7, "reason": "recuento semanal: merma" })), &ctx)
        .await.unwrap();
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 7.0, "ajuste ABSOLUTO: fija el valor contado");

    let movs = movements(&rt, &ctx, &pid).await;
    let m = movs.iter().find(|m| m["movement_type"] == json!("count")).expect("falta el movimiento count");
    assert_eq!(m["qty"].as_f64().unwrap(), -3.0, "el movimiento registra la DIFERENCIA");
    assert_eq!(m["stock_after"].as_f64().unwrap(), 7.0);
    assert_eq!(m["reason"], json!("recuento semanal: merma"));

    // Recontar el MISMO valor no ensucia el ledger.
    rt.execute_command("inventory.stock.adjust",
        &params(json!({ "product_id": pid, "stock": 7, "reason": "recuento sin cambios" })), &ctx)
        .await.unwrap();
    let counts = movements(&rt, &ctx, &pid).await.iter()
        .filter(|m| m["movement_type"] == json!("count")).count();
    assert_eq!(counts, 1, "un recuento sin diferencia no crea movimiento");
}

// ── Venta con DECIMALES (#10) + anulación con referencia ────────────────────────────────

#[tokio::test]
async fn sale_with_decimal_quantity_moves_ledger_and_void_reverses_it() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() { eprintln!("⚠ sin handler.wasm — saltado"); return; }
    let rt = stack().await;
    let ctx = admin();
    let pid = create_product(&rt, &ctx, "KG", 10_000_000).await;

    // Venta de 2,5 kg = 2500000 (punto fijo 10⁶, ADR-0147): el truncado float→i64 habría descontado 2.
    seed_sale(&rt, "sl-1", &[(&pid, 0, 2_500_000.0)]).await;
    rt.execute_command("inventory.stock.decrease_on_sale", &params(json!({
        "sale_id": "sl-1",
        "items": [ { "product_id": pid, "quantity": 2_500_000, "is_service": false } ]
    })), &ctx).await.unwrap();

    assert_eq!(stock_of(&rt, &ctx, &pid).await, 7_500_000.0, "2,5 kg descontados EXACTOS (10⁶)");
    let movs = movements(&rt, &ctx, &pid).await;
    let sale = movs.iter().find(|m| m["movement_type"] == json!("sale")).expect("falta el movimiento sale");
    assert_eq!(sale["qty"].as_f64().unwrap(), -2_500_000.0);
    assert_eq!(sale["stock_after"].as_f64().unwrap(), 7_500_000.0);
    assert_eq!(sale["reference"], json!("sl-1"), "referencia al documento origen");

    // Anular: restituye 2,5 y deja movimiento `void` con la misma referencia.
    rt.execute_command("sales.void", &params(json!({ "sale_id": "sl-1", "reason": "x" })), &ctx)
        .await.unwrap();
    rt.drain_outbox().await.unwrap();
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 10_000_000.0);
    let movs = movements(&rt, &ctx, &pid).await;
    let v = movs.iter().find(|m| m["movement_type"] == json!("void")).expect("falta el movimiento void");
    assert_eq!(v["qty"].as_f64().unwrap(), 2_500_000.0);
    assert_eq!(v["reference"], json!("sl-1"));

    // Reentrega del evento: ni stock ni ledger se duplican.
    rt.drain_outbox().await.unwrap();
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 10_000_000.0);
    let voids = movements(&rt, &ctx, &pid).await.iter()
        .filter(|m| m["movement_type"] == json!("void")).count();
    assert_eq!(voids, 1, "la reentrega no duplica movimientos");
}

// ── El ledger solo registra lo que OCURRIÓ ──────────────────────────────────────────────

#[tokio::test]
async fn rejected_or_untracked_decreases_leave_no_movement() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = stack().await;
    let ctx = admin();

    // Rechazo atómico (sobreventa no permitida): sin movimiento.
    let pid = create_product(&rt, &ctx, "REJ", 3).await;
    rt.execute_command("inventory.stock.decrease",
        &params(json!({ "product_id": pid, "qty": 9 })), &ctx).await.unwrap();
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 3.0);
    assert!(movements(&rt, &ctx, &pid).await.is_empty(), "un rechazo no deja rastro en el ledger");

    // track_stock = 0: sin movimiento.
    rt.execute_command("inventory.settings.update", &params(json!({
        "track_stock": 0, "allow_sell_without_stock": 0, "low_stock_threshold": 10
    })), &ctx).await.unwrap();
    rt.execute_command("inventory.stock.decrease",
        &params(json!({ "product_id": pid, "qty": 1 })), &ctx).await.unwrap();
    assert!(movements(&rt, &ctx, &pid).await.is_empty(), "tracking off: sin movimientos");
}

// ── Historial filtrable ─────────────────────────────────────────────────────────────────

#[tokio::test]
async fn movements_query_filters_by_type_and_reference() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() { eprintln!("⚠ sin handler.wasm — saltado"); return; }
    let rt = stack().await;
    let ctx = admin();
    let pid = create_product(&rt, &ctx, "FIL", 10).await;

    rt.execute_command("inventory.stock.receive", &params(json!({
        "items": [ { "product_id": pid, "qty": 5 } ]
    })), &ctx).await.unwrap();
    rt.execute_command("inventory.stock.adjust",
        &params(json!({ "product_id": pid, "stock": 12, "reason": "recuento" })), &ctx).await.unwrap();

    let all = movements(&rt, &ctx, &pid).await;
    assert_eq!(all.len(), 2);
    // El historial proyecta el nombre/sku del producto (JOIN) para pintarse sin N+1.
    assert_eq!(all[0]["sku"], json!("FIL"));

    let counts = rt.execute_query("inventory.stock.movements",
        &params(json!({"f_product_id": pid, "f_movement_type": "count"})), &ctx).await.unwrap();
    assert_eq!(counts.len(), 1);
    assert_eq!(counts[0]["movement_type"], json!("count"));
}

// ── Permisos diferenciados (#7) ─────────────────────────────────────────────────────────

#[tokio::test]
async fn stock_permissions_are_separate_from_product_editing() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = stack().await;
    let ctx = admin();
    let pid = create_product(&rt, &ctx, "PRM", 10).await;

    // Un rol que SOLO edita productos no puede recontar stock…
    let editor = RequestContext::new("h1", "u2", ["inventory.change_product".to_string()]);
    let err = rt.execute_command("inventory.stock.adjust",
        &params(json!({ "product_id": pid, "stock": 5, "reason": "x" })), &editor).await;
    assert!(err.is_err(), "ajustar stock exige su permiso propio (inventory.adjust_stock)");

    // …y uno con el permiso de stock puede, sin poder editar productos.
    let counter = RequestContext::new(
        "h1", "u3",
        ["inventory.adjust_stock".to_string(), "inventory.view_stock".to_string(), "inventory.view_product".to_string()],
    );
    rt.execute_command("inventory.stock.adjust",
        &params(json!({ "product_id": pid, "stock": 5, "reason": "recuento" })), &counter)
        .await.unwrap();
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 5.0);
    assert_eq!(movements(&rt, &counter, &pid).await.len(), 1, "consultar el ledger = inventory.view_stock");
}
