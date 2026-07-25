//! E2E del CONTRATO de estadísticas del dashboard de inventory (inventory#9):
//! la valoración es **a COSTE** (no a precio de venta), en céntimos, y las métricas
//! excluyen lo que no debe contarse:
//!
//!   * `total_inventory_value` = Σ (cost × stock) SOLO de productos físicos activos
//!     con stock > 0 — los servicios no valoran, y un stock negativo (sobreventa,
//!     inventory#6) no RESTA valor.
//!   * los servicios no cuentan como seguidos/en stock/agotados/bajo umbral
//!     (no tienen existencias físicas).
//!   * `products_without_cost` expone cuántos físicos valoran a 0 por no tener
//!     coste registrado — la UI muestra esa limitación en vez de callarla.
//!
//! La query `low_stock` tampoco lista servicios (hoy un servicio con stock 0
//! aparece como «stock bajo», ruido puro para reponer).
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

async fn stack() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("taxes")).await.unwrap();
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt
}

async fn create(rt: &Runtime, ctx: &RequestContext, v: serde_json::Value) {
    rt.execute_command("inventory.products.create", &params(v), ctx).await.unwrap();
}

/// Catálogo de prueba:
///   A físico: stock 10, umbral 5, coste 200  → en stock, valora 2000
///   B físico: stock 0,  umbral 5, coste 300  → agotado + bajo umbral, valora 0
///   C físico: stock 2,  umbral 5, coste 0    → en stock + bajo umbral + SIN coste
///   D físico: stock -3, umbral 5, coste 400  → agotado (sobreventa); NO resta valor
///   S servicio: stock 3, coste 100           → fuera de todo (ni valora ni cuenta)
async fn seed_catalog(rt: &Runtime, ctx: &RequestContext) {
    create(rt, ctx, json!({ "name": "A", "sku": "A", "price": 500,  "cost": 200, "stock": 10_000_000, "low_stock_threshold": 5_000_000, "product_type": "physical" })).await;
    create(rt, ctx, json!({ "name": "B", "sku": "B", "price": 900,  "cost": 300, "stock": 0,  "low_stock_threshold": 5_000_000, "product_type": "physical" })).await;
    create(rt, ctx, json!({ "name": "C", "sku": "C", "price": 700,  "cost": 0,   "stock": 2_000_000,  "low_stock_threshold": 5_000_000, "product_type": "physical" })).await;
    create(rt, ctx, json!({ "name": "D", "sku": "D", "price": 800,  "cost": 400, "stock": 5_000_000,  "low_stock_threshold": 5_000_000, "product_type": "physical" })).await;
    create(rt, ctx, json!({ "name": "S", "sku": "S", "price": 1500, "cost": 100, "stock": 3_000_000,  "low_stock_threshold": 5_000_000, "product_type": "service" })).await;
    // D pasa a stock -3 vía sobreventa permitida (inventory#6): venta real, no seed a mano.
    rt.execute_command("inventory.settings.update", &params(json!({
        "track_stock": 1, "allow_sell_without_stock": 1, "low_stock_threshold": 10_000_000
    })), ctx).await.unwrap();
    let d_id = rt
        .execute_query("inventory.products.list", &params(json!({"search": "D"})), ctx)
        .await.unwrap()[0]["id"].as_str().unwrap().to_string();
    rt.execute_command("inventory.stock.decrease", &params(json!({ "product_id": d_id, "qty": 8_000_000 })), ctx)
        .await.unwrap();
}

#[tokio::test]
async fn stats_value_products_at_cost_excluding_services_and_negative_stock() {
    let rt = stack().await;
    let ctx = admin();
    seed_catalog(&rt, &ctx).await;

    let stats = rt.execute_query("inventory.products.stats", &Params::new(), &ctx).await.unwrap();
    let s = &stats[0];

    // Valoración A COSTE, céntimos: solo A (200×10) — C sin coste, B/D sin stock positivo, S servicio.
    assert_eq!(s["total_inventory_value"].as_i64().unwrap(), 2000, "{s}");
    // Contadores sobre físicos activos (S fuera de todos).
    assert_eq!(s["total_products"].as_i64().unwrap(), 5, "el catálogo entero, servicios incluidos");
    assert_eq!(s["products_tracked"].as_i64().unwrap(), 4, "físicos activos (seguidos)");
    assert_eq!(s["products_in_stock"].as_i64().unwrap(), 2, "A y C (stock > 0)");
    assert_eq!(s["products_out_of_stock"].as_i64().unwrap(), 2, "B (0) y D (-3, sobreventa)");
    assert_eq!(s["products_low_stock"].as_i64().unwrap(), 3, "B, C y D en o bajo su umbral");
    assert_eq!(s["products_without_cost"].as_i64().unwrap(), 1, "C valora a 0 y se avisa");
}

#[tokio::test]
async fn low_stock_excludes_services() {
    let rt = stack().await;
    let ctx = admin();
    seed_catalog(&rt, &ctx).await;

    let rows = rt.execute_query("inventory.products.low_stock", &Params::new(), &ctx).await.unwrap();
    let skus: Vec<&str> = rows.iter().map(|r| r["sku"].as_str().unwrap()).collect();

    assert!(!skus.contains(&"S"), "un servicio no es stock a reponer: {skus:?}");
    assert!(skus.contains(&"B") && skus.contains(&"C") && skus.contains(&"D"), "{skus:?}");
    assert!(!skus.contains(&"A"), "A está por encima de su umbral: {skus:?}");
}
