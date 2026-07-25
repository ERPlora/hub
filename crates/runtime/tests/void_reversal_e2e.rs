//! E2E real de la REVERSIÓN al ANULAR una venta (ADR-0073): la cadena cross-módulo
//! `sales.void` → evento `sale.voided` → cash_register (`_reverse_sale`) + inventory
//! (`_restock_on_void`). Verifica que:
//!   1. una venta en EFECTIVO que subió la caja y bajó el stock,
//!   2. al anularla, deja la caja en el NETO previo (movimiento `refund` compensatorio,
//!      sin mutar el `sale` original) y el stock RESTITUIDO,
//!   3. y una REENTREGA del evento NO duplica (idempotencia: `_event_delivery` del runtime
//!      + guardas SQL / marcador propio de cada listener).
//!
//! Pertenece a cash_register/inventory (la IA es dueña de ambos). La PRECONDICIÓN (la venta
//! completada: filas en `sales_sale`/`sales_sale_item` + el movimiento `sale` de caja) se
//! SIEMBRA directamente —no vía `sales.complete_sale`— para aislar el test de trabajo en
//! vuelo del módulo `sales` (ajeno). El disparo real es `sales.void` (solo UPDATE+emit) y el
//! relay del Outbox; las aserciones leen por las queries públicas reales.
use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params { v.as_object().cloned().unwrap_or_default() }
fn mdir(n: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules").join(n)
}
fn admin() -> RequestContext { RequestContext::new("h1", "u1", ["*".to_string()]) }

async fn full_stack() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("taxes")).await.unwrap(); // inventory depende de taxes (ADR-0066)
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap(); // sales depende de customers
    rt.install_from_dir(&mdir("cash_register")).await.unwrap();
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    rt
}

async fn open_cash_session(rt: &Runtime, ctx: &RequestContext, opening: i64) -> String {
    rt.execute_command("cash_register.session.open", &params(json!({
        "register_id": null, "session_number": "VR-260625-1000",
        "opening_balance": opening, "opening_notes": ""
    })), ctx).await.unwrap();
    rt.execute_query("cash_register.sessions.list", &Params::new(), ctx).await.unwrap()
        .last().unwrap()["id"].as_str().unwrap().to_string()
}

/// Efectivo esperado de la sesión ABIERTA (KPI en vivo) = opening + Σ(sale,in) − Σ(refund,out).
/// Útil ANTES de que exista una reversión. OJO: `current_session` flipa el signo de refund/out
/// asumiéndolos positivos, mientras que el resto del módulo los almacena negativos (ver SEAM en
/// el changelog); por eso el ARQUEO post-void se mide con `arqueo()` (la reconciliación canónica).
async fn expected_cash(rt: &Runtime, ctx: &RequestContext) -> i64 {
    rt.execute_query("cash_register.current_session", &Params::new(), ctx).await.unwrap()[0]
        ["expected_total"].as_i64().unwrap()
}

/// ARQUEO canónico de la sesión: cierra y devuelve `expected_balance` (= opening + Σ amount, la
/// misma fórmula que `close_session`/`session.summary`). Es la métrica que el bug nombra
/// ("el arqueo queda inflado por cada anulación"). Refund/out se almacenan NEGATIVOS, así que
/// una venta cash revertida deja Σ amount = 0 y el arqueo vuelve al neto de apertura.
async fn arqueo(rt: &Runtime, ctx: &RequestContext, sid: &str) -> i64 {
    rt.execute_command("cash_register.session.close", &params(json!({
        "session_id": sid, "closing_balance": 0, "closing_notes": ""
    })), ctx).await.unwrap();
    rt.execute_query("cash_register.sessions.list", &params(json!({"session_number": "VR-260625-1000"}), ), ctx)
        .await.unwrap().iter().find(|s| s["id"] == json!(sid)).unwrap()
        ["expected_balance"].as_i64().unwrap()
}

async fn create_product(rt: &Runtime, ctx: &RequestContext, name: &str, sku: &str, stock: i64) -> String {
    rt.execute_command("inventory.products.create", &params(json!({
        "name": name, "sku": sku, "price": 1000, "cost": 500, "stock": stock,
        "low_stock_threshold": 5, "product_type": "physical",
        "ean13": null, "description": "", "tax_category_key": null, "image": ""
    })), ctx).await.unwrap();
    rt.execute_query("inventory.products.list", &params(json!({"search": sku})), ctx).await.unwrap()[0]
        ["id"].as_str().unwrap().to_string()
}

async fn stock_of(rt: &Runtime, ctx: &RequestContext, pid: &str) -> f64 {
    rt.execute_query("inventory.products.get", &params(json!({"product_id": pid})), ctx).await.unwrap()[0]
        ["stock"].as_f64().unwrap()
}

/// Siembra una venta COMPLETADA (cabecera `sales_sale` + líneas `sales_sale_item`), como si
/// `complete_sale` ya hubiera corrido. `lines`: (product_id|"", is_service 0/1, quantity).
/// Solo usa columnas del esquema base committeado de sales (sin tocar trabajo en vuelo ajeno).
async fn seed_sale(
    rt: &Runtime, sale_id: &str, sale_number: &str, total: i64, payment_method: &str,
    lines: &[(&str, i64, f64)],
) {
    let db = rt.db_for_test();
    db.execute(
        "INSERT INTO sales_sale (id, hub_id, sale_number, status, subtotal, tax_amount, \
         tax_breakdown, discount_amount, discount_percent, total, payment_method_name, \
         amount_tendered, change_due, customer_name, notes, source_module, channel, \
         is_deleted, created_at, updated_at) \
         VALUES (:id, 'h1', :num, 'completed', :total, 0, '{}', 0, 0, :total, :pm, \
         :total, 0, '', '', 'pos', 'pos', 0, :now, :now)",
        &params(json!({ "id": sale_id, "num": sale_number, "total": total,
            "pm": payment_method, "now": "2026-06-25T10:00:00+00:00" })),
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
                "now": "2026-06-25T10:00:00+00:00" })),
        ).await.unwrap();
    }
}

/// El movimiento de caja `sale` que `record_sale` habría creado al cobrar (lo escribe el
/// command PÚBLICO real de cash_register; `sale_reference` = sale_id, como hace record_sale).
async fn seed_cash_sale_movement(rt: &Runtime, ctx: &RequestContext, sid: &str, sale_id: &str, amount: i64) {
    rt.execute_command("cash_register.movement.add", &params(json!({
        "session_id": sid, "movement_type": "sale", "amount": amount, "payment_method": "cash",
        "sale_reference": sale_id, "description": format!("Sale {sale_id}")
    })), ctx).await.unwrap();
}

/// Aplica el descuento de stock que `decrease_on_sale` habría hecho al cobrar (command real).
async fn seed_stock_decrease(rt: &Runtime, ctx: &RequestContext, pid: &str, qty: i64) {
    rt.execute_command("inventory.stock.decrease", &params(json!({ "product_id": pid, "qty": qty })), ctx)
        .await.unwrap();
}

/// Listeners de sale.voided registrados por ambos módulos.
#[tokio::test]
async fn install_registers_void_listeners() {
    let rt = full_stack().await;
    let reg = rt.registry();
    let listeners = reg.listeners_for("sale.voided");
    assert!(listeners.contains(&"cash_register._reverse_sale".to_string()), "{listeners:?}");
    assert!(listeners.contains(&"inventory._restock_on_void".to_string()), "{listeners:?}");
}

/// Escenario completo: venta cash que subió caja + bajó stock → void → caja al neto previo y
/// stock restituido. Reentrega del evento no duplica.
#[tokio::test]
async fn cash_sale_void_reverts_cash_and_stock() {
    let rt = full_stack().await;
    let ctx = admin();

    // Fondo de apertura 100,00 € y un producto con stock 10.
    let opening = 10_000;
    let sid = open_cash_session(&rt, &ctx, opening).await;
    let pid = create_product(&rt, &ctx, "Café", "CAF", 10).await;

    // Precondición: venta cash de 30,00 € de 2 uds → caja +3000, stock 10→8.
    seed_sale(&rt, "sale-1", "S-1", 3000, "cash", &[(&pid, 0, 2.0)]).await;
    seed_cash_sale_movement(&rt, &ctx, &sid, "sale-1", 3000).await;
    seed_stock_decrease(&rt, &ctx, &pid, 2).await;
    assert_eq!(expected_cash(&rt, &ctx).await, opening + 3000, "la venta cash subió la caja");
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 8.0, "la venta bajó el stock");

    // ── ANULAR la venta (sales.void: UPDATE de estado + emit sale.voided) ───────────────
    rt.execute_command("sales.void", &params(json!({ "sale_id": "sale-1", "reason": "test" })), &ctx)
        .await.unwrap();
    rt.drain_outbox().await.unwrap(); // sale.voided → _reverse_sale + _restock_on_void

    // Stock restituido a 10 tras la anulación.
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 10.0, "la anulación restituye el stock");

    // El movimiento `sale` original SIGUE existiendo (no se muta): hay sale + refund.
    let movs = rt.execute_query("cash_register.movements.list", &params(json!({"session_id": sid})), &ctx)
        .await.unwrap();
    let types: Vec<&str> = movs.iter().map(|m| m["movement_type"].as_str().unwrap()).collect();
    assert!(types.contains(&"sale") && types.contains(&"refund"), "{types:?}");
    let refund = movs.iter().find(|m| m["movement_type"] == json!("refund")).unwrap();
    assert_eq!(refund["amount"].as_i64().unwrap(), -3000, "refund compensa el importe exacto (negativo, canónico)");

    // ── REENTREGA del evento: idempotencia (no duplica refund ni stock) ─────────────────
    rt.drain_outbox().await.unwrap();
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 10.0, "re-drenar no duplica la restitución");
    let movs2 = rt.execute_query("cash_register.movements.list", &params(json!({"session_id": sid})), &ctx)
        .await.unwrap();
    assert_eq!(movs2.len(), movs.len(), "no se añaden movimientos al reentregar el evento");

    // ARQUEO canónico: la venta cash anulada deja Σ amount = sale(+3000) + refund(−3000) = 0,
    // así que el arqueo vuelve al neto de apertura (el bug "arqueo inflado" queda resuelto).
    assert_eq!(arqueo(&rt, &ctx, &sid).await, opening, "el arqueo vuelve al neto previo tras la anulación");
}

/// Una venta con TARJETA no toca la caja al venderse (no hay movimiento `sale` en efectivo),
/// así que su anulación es no-op en caja (no se postea refund), pero el stock SÍ se restituye.
#[tokio::test]
async fn card_sale_void_restocks_but_no_cash_refund() {
    let rt = full_stack().await;
    let ctx = admin();
    let opening = 5_000;
    let sid = open_cash_session(&rt, &ctx, opening).await;
    let pid = create_product(&rt, &ctx, "Té", "TE", 7).await;

    // Venta tarjeta: NO crea movimiento de caja; solo baja stock 7→4.
    seed_sale(&rt, "sale-2", "S-2", 3000, "card", &[(&pid, 0, 3.0)]).await;
    seed_stock_decrease(&rt, &ctx, &pid, 3).await;
    assert_eq!(expected_cash(&rt, &ctx).await, opening, "tarjeta no toca la caja");
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 4.0);

    rt.execute_command("sales.void", &params(json!({ "sale_id": "sale-2", "reason": "x" })), &ctx)
        .await.unwrap();
    rt.drain_outbox().await.unwrap();

    // Caja intacta (no había movimiento cash que revertir); stock restituido.
    assert_eq!(expected_cash(&rt, &ctx).await, opening, "sin refund: la venta no fue en efectivo");
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 7.0, "el stock se restituye igual en tarjeta");
    let movs = rt.execute_query("cash_register.movements.list", &params(json!({"session_id": sid})), &ctx)
        .await.unwrap();
    assert!(movs.iter().all(|m| m["movement_type"] != json!("refund")), "no debe haber refund de caja");
}

/// Servicios (sin stock físico) no se restituyen: una venta cash de solo servicio se anula
/// revirtiendo la caja, sin tocar ningún stock de producto.
#[tokio::test]
async fn service_line_void_reverts_cash_without_touching_stock() {
    let rt = full_stack().await;
    let ctx = admin();
    let sid = open_cash_session(&rt, &ctx, 0).await;
    // Un producto físico de control: NO debe variar (la venta es de servicio sin product_id).
    let pid = create_product(&rt, &ctx, "Control", "CTRL", 5).await;

    seed_sale(&rt, "sale-3", "S-3", 2000, "cash", &[("", 1, 1.0)]).await; // línea servicio, sin product_id
    seed_cash_sale_movement(&rt, &ctx, &sid, "sale-3", 2000).await;
    assert_eq!(expected_cash(&rt, &ctx).await, 2000, "el servicio cobrado en cash subió la caja");

    rt.execute_command("sales.void", &params(json!({ "sale_id": "sale-3", "reason": "x" })), &ctx)
        .await.unwrap();
    rt.drain_outbox().await.unwrap();

    assert_eq!(stock_of(&rt, &ctx, &pid).await, 5.0, "ningún stock cambia al anular un servicio");
    // El servicio cash anulado: sale(+2000) + refund(−2000) = 0 → arqueo de vuelta al neto.
    assert_eq!(arqueo(&rt, &ctx, &sid).await, 0, "la anulación del servicio revierte la caja");
}
