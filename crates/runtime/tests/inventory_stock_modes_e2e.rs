//! E2E de los MODOS OPERATIVOS del control de stock (inventory#6, frontera ADR-0135):
//! los ajustes `track_stock` / `allow_sell_without_stock` deben GOBERNAR la operativa,
//! no solo guardarse.
//!
//!   * `track_stock = 1` + `allow_sell_without_stock = 0` (defaults, también SIN fila de
//!     settings): una disminución insuficiente se RECHAZA atómicamente — el stock no se
//!     mueve, nunca se trunca a 0 en silencio.
//!   * `track_stock = 1` + `allow_sell_without_stock = 1`: la operación se permite y el
//!     saldo resultante se REPRESENTA (negativo incluido), sin truncar.
//!   * `track_stock = 0`: ni bloqueos ni movimientos automáticos — el descuento directo y
//!     el listener de `sale.completed` son no-op, y la ANULACIÓN posterior de esa venta
//!     NO restituye (la venta no generó movimientos): marcador `inventory_void_restock`
//!     sembrado por el listener.
//!   * El umbral global de settings es la SEMILLA del umbral por producto: un alta sin
//!     `low_stock_threshold` explícito hereda el global del hub (precedencia resuelta:
//!     el umbral por producto siempre manda; el global es su default de creación).
//!
//! Sigue el patrón de `void_reversal_e2e.rs`: módulos reales desde `modules-workspace/`,
//! la venta completada se SIEMBRA (aislado del trabajo en vuelo de `sales`), el disparo
//! del void es `sales.void` real + relay del Outbox, y las aserciones leen queries públicas.
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
    rt.install_from_dir(&mdir("taxes")).await.unwrap(); // inventory depende de taxes
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap(); // sales depende de customers
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    rt
}

async fn set_settings(rt: &Runtime, ctx: &RequestContext, track: i64, allow: i64, threshold: i64) {
    rt.execute_command(
        "inventory.settings.update",
        &params(json!({
            "track_stock": track,
            "allow_sell_without_stock": allow,
            "low_stock_threshold": threshold
        })),
        ctx,
    )
    .await
    .unwrap();
}

/// Alta de producto; `threshold: None` = el caller NO manda `low_stock_threshold`
/// (debe heredar el global del hub).
async fn create_product(
    rt: &Runtime,
    ctx: &RequestContext,
    name: &str,
    sku: &str,
    stock: i64,
    threshold: Option<i64>,
) -> String {
    let mut payload = json!({
        "name": name, "sku": sku, "price": 1000, "cost": 500, "stock": stock,
        "product_type": "physical",
        "ean13": null, "description": "", "tax_category_key": null, "image": ""
    });
    if let Some(t) = threshold {
        payload["low_stock_threshold"] = json!(t);
    }
    rt.execute_command("inventory.products.create", &params(payload), ctx).await.unwrap();
    rt.execute_query("inventory.products.list", &params(json!({"search": sku})), ctx)
        .await
        .unwrap()[0]["id"]
        .as_str()
        .unwrap()
        .to_string()
}

async fn product(rt: &Runtime, ctx: &RequestContext, pid: &str) -> serde_json::Value {
    rt.execute_query("inventory.products.get", &params(json!({"product_id": pid})), ctx)
        .await
        .unwrap()[0]
        .clone()
}

async fn stock_of(rt: &Runtime, ctx: &RequestContext, pid: &str) -> f64 {
    product(rt, ctx, pid).await["stock"].as_f64().unwrap()
}

async fn decrease(rt: &Runtime, ctx: &RequestContext, pid: &str, qty: i64) {
    rt.execute_command(
        "inventory.stock.decrease",
        &params(json!({ "product_id": pid, "qty": qty })),
        ctx,
    )
    .await
    .unwrap();
}

/// Venta COMPLETADA sembrada (cabecera + líneas), como en `void_reversal_e2e.rs`:
/// aísla el test del contrato en vuelo de `sales.complete_sale` (módulo ajeno).
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
    )
    .await
    .unwrap();
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
        )
        .await
        .unwrap();
    }
}

/// Ejecuta el listener real de `sale.completed` (command WASM del módulo) como lo haría
/// el relay del Outbox al entregar el evento: payload = el del evento de `sales`.
async fn deliver_sale_completed(rt: &Runtime, ctx: &RequestContext, sale_id: &str, pid: &str, qty: i64) {
    rt.execute_command(
        "inventory.stock.decrease_on_sale",
        &params(json!({
            "sale_id": sale_id,
            "items": [ { "product_id": pid, "quantity": qty, "is_service": false } ]
        })),
        ctx,
    )
    .await
    .unwrap();
}

async fn void_sale(rt: &Runtime, ctx: &RequestContext, sale_id: &str) {
    rt.execute_command("sales.void", &params(json!({ "sale_id": sale_id, "reason": "test" })), ctx)
        .await
        .unwrap();
    rt.drain_outbox().await.unwrap();
}

// ── Modo 3a: tracking activo, sobreventa NO permitida (defaults, sin fila de settings) ──

/// Una disminución INSUFICIENTE se rechaza atómicamente: el stock no se mueve.
/// (Bug original: `CASE WHEN <0 THEN 0` truncaba a cero en silencio.)
#[tokio::test]
async fn insufficient_decrease_is_rejected_atomically() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = stack().await;
    let ctx = admin();
    let pid = create_product(&rt, &ctx, "Café", "CAF", 5, Some(5)).await;

    decrease(&rt, &ctx, &pid, 10).await;

    assert_eq!(stock_of(&rt, &ctx, &pid).await, 5.0, "stock intacto: ni negativo ni truncado a 0");
}

/// Con stock suficiente el descuento sigue funcionando (regresión).
#[tokio::test]
async fn sufficient_decrease_still_decreases() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = stack().await;
    let ctx = admin();
    let pid = create_product(&rt, &ctx, "Té", "TE", 5, Some(5)).await;

    decrease(&rt, &ctx, &pid, 3).await;

    assert_eq!(stock_of(&rt, &ctx, &pid).await, 2.0);
}

// ── Modo 3b: tracking activo, sobreventa PERMITIDA ──────────────────────────────────────

/// Con `allow_sell_without_stock = 1` la operación se permite y el saldo resultante se
/// representa tal cual — NEGATIVO, nunca truncado a cero en silencio.
#[tokio::test]
async fn oversell_allowed_represents_negative_stock() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = stack().await;
    let ctx = admin();
    set_settings(&rt, &ctx, 1, 1, 10).await;
    let pid = create_product(&rt, &ctx, "Leche", "LEC", 5, Some(5)).await;

    decrease(&rt, &ctx, &pid, 10).await;

    assert_eq!(stock_of(&rt, &ctx, &pid).await, -5.0, "sobreventa representada como saldo negativo");
}

// ── Modo 2: `track_stock = 0` — catálogo sin control de stock ───────────────────────────

/// El descuento directo es no-op: no se crean movimientos con el tracking desactivado.
#[tokio::test]
async fn track_off_direct_decrease_is_noop() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = stack().await;
    let ctx = admin();
    set_settings(&rt, &ctx, 0, 0, 10).await;
    let pid = create_product(&rt, &ctx, "Pan", "PAN", 5, Some(5)).await;

    decrease(&rt, &ctx, &pid, 3).await;

    assert_eq!(stock_of(&rt, &ctx, &pid).await, 5.0, "track_stock=0: sin movimientos automáticos");
}

/// La cadena completa con tracking DESACTIVADO: la venta no genera movimientos y la
/// ANULACIÓN posterior tampoco restituye (la venta no descontó nada) — criterio #6:
/// «revertir una venta solo cuando la operación original haya generado movimientos».
#[tokio::test]
async fn track_off_sale_makes_no_movements_and_void_does_not_restock() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("⚠ dist/handler.wasm no compilado — test saltado");
        return;
    }
    let rt = stack().await;
    let ctx = admin();
    set_settings(&rt, &ctx, 0, 0, 10).await;
    let pid = create_product(&rt, &ctx, "Vino", "VIN", 8, Some(5)).await;

    seed_sale(&rt, "sm-off", &[(&pid, 0, 2_000_000.0)]).await;
    deliver_sale_completed(&rt, &ctx, "sm-off", &pid, 2_000_000).await;
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 8.0, "la venta con tracking OFF no mueve stock");

    void_sale(&rt, &ctx, "sm-off").await;
    assert_eq!(
        stock_of(&rt, &ctx, &pid).await,
        8.0,
        "anular una venta SIN movimientos no restituye nada (no infla el stock)"
    );
}

/// Regresión de la cadena con tracking ACTIVO: la venta descuenta y el void restituye
/// exactamente (el marcador de #6 no debe romper ADR-0075).
#[tokio::test]
async fn track_on_sale_decreases_and_void_restocks() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("⚠ dist/handler.wasm no compilado — test saltado");
        return;
    }
    let rt = stack().await;
    let ctx = admin();
    set_settings(&rt, &ctx, 1, 0, 10).await;
    let pid = create_product(&rt, &ctx, "Queso", "QUE", 8_000_000, Some(5_000_000)).await;

    seed_sale(&rt, "sm-on", &[(&pid, 0, 2_000_000.0)]).await;
    deliver_sale_completed(&rt, &ctx, "sm-on", &pid, 2_000_000).await;
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 6_000_000.0, "tracking ON: la venta descuenta");

    void_sale(&rt, &ctx, "sm-on").await;
    assert_eq!(stock_of(&rt, &ctx, &pid).await, 8_000_000.0, "el void restituye el descuento real");
}

// ── Precedencia del umbral de stock bajo ────────────────────────────────────────────────

/// El umbral GLOBAL de settings siembra el umbral por producto cuando el alta no lo trae:
/// el umbral por producto siempre manda; el global es su default de creación.
#[tokio::test]
async fn low_stock_threshold_seeds_from_global_settings() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = stack().await;
    let ctx = admin();
    set_settings(&rt, &ctx, 1, 0, 25).await;

    let pid = create_product(&rt, &ctx, "Aceite", "ACE", 50_000_000, None).await;

    assert_eq!(
        product(&rt, &ctx, &pid).await["low_stock_threshold"].as_i64().unwrap(),
        25_000_000,
        "alta sin umbral explícito hereda el global y lo convierte a escala 10⁶"
    );
}

/// El umbral explícito del caller sigue mandando sobre el global (regresión).
#[tokio::test]
async fn explicit_low_stock_threshold_wins_over_global() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = stack().await;
    let ctx = admin();
    set_settings(&rt, &ctx, 1, 0, 25).await;

    let pid = create_product(&rt, &ctx, "Sal", "SAL", 50_000_000, Some(3_000_000)).await;

    assert_eq!(
        product(&rt, &ctx, &pid).await["low_stock_threshold"].as_i64().unwrap(),
        3_000_000
    );
}
