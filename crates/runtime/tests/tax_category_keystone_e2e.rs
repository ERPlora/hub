//! E2E del keystone fiscal ADR-0085: el impuesto se resuelve **server-side por CATEGORÍA**
//! (`tax_category_key`) usando el país/región del hub (identidad fiscal en `hub_settings`,
//! default ES) contra las reglas de `taxes` pre-cargadas (reads `taxes.rules.list`), y se
//! **congela el snapshot** en la línea de venta. Una factura/venta ya emitida NO cambia aunque
//! cambie la regla (snapshot inmutable). Supersede el modelo `tax_rate_id` de ADR-0066.
//!
//! El catálogo canónico (6 categorías) + alias de fábrica + reglas IVA ES los siembra el
//! **instalador** automáticamente (campo `seed` del module.json de `taxes`, ADR-0085): por eso
//! estos tests NO siembran categorías/reglas a mano — un hub recién instalado ya las tiene.
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::Mutex;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{EventSink, RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules").join(name)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}
fn wasm_present() -> bool {
    mdir("sales").join("dist/handler.wasm").exists() && mdir("taxes").join("dist/handler.wasm").exists()
}

#[derive(Default, Debug)]
struct Sink {
    events: Mutex<Vec<(String, serde_json::Value)>>,
}
impl EventSink for Sink {
    fn emit(&self, name: &str, payload: &serde_json::Value) {
        self.events.lock().unwrap().push((name.to_string(), payload.clone()));
    }
}

async fn fresh() -> (Runtime, Arc<Sink>) {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    // El runtime se construye con el MISMO hub_id que usa el ctx ("h1"): en producción el hub_id del
    // despliegue == el del usuario, y el seed por install se siembra bajo ese hub (ADR-0085).
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    // Instalar taxes dispara su SEED (catálogo canónico + alias + reglas ES) automáticamente.
    rt.install_from_dir(&mdir("taxes")).await.expect("instalar taxes");
    rt.install_from_dir(&mdir("inventory")).await.expect("instalar inventory");
    rt.install_from_dir(&mdir("customers")).await.expect("instalar customers");
    rt.install_from_dir(&mdir("sales")).await.expect("instalar sales");
    (rt, sink)
}

#[tokio::test]
async fn install_seeds_canonical_catalog_aliases_and_es_rules() {
    let (rt, _) = fresh().await;
    let ctx = admin();

    // Las 6 categorías canónicas existen tras instalar (sin sembrar a mano).
    let cats = rt.execute_query("taxes.categories.list", &Params::new(), &ctx).await.unwrap();
    assert!(cats.len() >= 6, "≥6 categorías canónicas sembradas, hay {}", cats.len());
    for key in ["restaurant.food", "restaurant.drink", "service.generic", "product.generic"] {
        assert!(cats.iter().any(|c| c["key"] == json!(key)), "falta categoría {key}");
    }

    // Alias de fábrica resuelve (pizza → restaurant.food).
    let a = rt.execute_query("taxes.aliases.resolve", &params(json!({ "alias": "pizza" })), &ctx).await.unwrap();
    assert_eq!(a[0]["tax_category_key"], json!("restaurant.food"));

    // Regla ES sembrada: restaurant.food = 10%.
    let rules = rt.execute_query("taxes.rules.by_country", &params(json!({ "country_code": "ES" })), &ctx).await.unwrap();
    let food = rules.iter().find(|r| r["tax_category_key"] == json!("restaurant.food")).expect("regla ES restaurant.food");
    assert_eq!(food["rate_pct"].as_f64().unwrap(), 10.0);

    // Idempotencia: re-instalar taxes NO duplica el seed.
    let mut rt2 = rt;
    rt2.install_from_dir(&mdir("taxes")).await.expect("reinstalar taxes");
    let cats2 = rt2.execute_query("taxes.categories.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(cats2.len(), cats.len(), "el seed no duplica al reinstalar");
}

#[tokio::test]
async fn sale_resolves_tax_by_category_from_seeded_rules() {
    if !wasm_present() {
        eprintln!("SKIP: handler.wasm ausente");
        return;
    }
    let (rt, _sink) = fresh().await;
    let ctx = admin();

    // Producto enlazado por categoría (restaurant.food, 10% ES sembrado). SIN seed manual.
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Menú del día", "sku": "MENU-1", "price": 10000, "tax_category_key": "restaurant.food" })),
        &ctx,
    )
    .await
    .expect("crear producto");

    // El POS manda la categoría; el servidor resuelve el % por país (contexto, default ES) + categoría.
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "tax_included": false, "amount_tendered": 11000,
            "items": [{ "product_name": "Menú del día", "price": 10000, "quantity": 1, "tax_category_key": "restaurant.food" }]
        })),
        &ctx,
    )
    .await
    .expect("complete_sale");

    let sales = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    let sale_id = sales[0]["id"].clone();
    let line = rt.execute_query("sales.lines", &params(json!({ "sale_id": sale_id })), &ctx).await.unwrap()[0].clone();
    // Resuelto server-side a 10% (regla ES sembrada) sobre 100,00€ → 10,00€.
    assert_eq!(line["net_amount"].as_i64().unwrap(), 10000);
    assert_eq!(line["tax_amount"].as_i64().unwrap(), 1000);
    assert_eq!(line["tax_rate"].as_f64().unwrap(), 10.0);
    // Snapshot inmutable ADR-0085 congelado en la línea.
    assert_eq!(line["tax_category_key"], json!("restaurant.food"));
    assert_eq!(line["tax_country_code"], json!("ES"));
    assert!(line["tax_rule_id"].as_str().is_some_and(|s| !s.is_empty()), "tax_rule_id congelado");
}

#[tokio::test]
async fn rule_change_does_not_alter_already_issued_sale() {
    if !wasm_present() {
        eprintln!("SKIP");
        return;
    }
    let (rt, _sink) = fresh().await;
    let ctx = admin();

    // Venta 1 con la regla SEMBRADA product.generic ES = 21% → congela 21%.
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "tax_included": false, "amount_tendered": 12100,
            "items": [{ "product_name": "Cosa", "price": 10000, "quantity": 1, "tax_category_key": "product.generic" }]
        })),
        &ctx,
    )
    .await
    .expect("venta 1");

    let sale1_id = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap()[0]["id"].clone();
    let line1 = rt.execute_query("sales.lines", &params(json!({ "sale_id": sale1_id.clone() })), &ctx).await.unwrap()[0].clone();
    assert_eq!(line1["tax_amount"].as_i64().unwrap(), 2100); // 21%

    // Cambia la regla: nueva regla 23% para product.generic con valid_from hoy (gana por vigencia
    // más reciente sobre la sembrada de 2012). NO tocamos la venta ya emitida.
    rt.execute_command(
        "taxes.rules.create",
        &params(json!({ "country_code": "ES", "tax_category_key": "product.generic", "rate_pct": 23.0, "valid_from": "2026-06-27" })),
        &ctx,
    )
    .await
    .expect("nueva regla 23%");

    // Venta 2 → resuelve la regla nueva (23%).
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "tax_included": false, "amount_tendered": 12300, "date": "2026-06-27",
            "items": [{ "product_name": "Cosa", "price": 10000, "quantity": 1, "tax_category_key": "product.generic" }]
        })),
        &ctx,
    )
    .await
    .expect("venta 2");

    // La venta 1 sigue intacta (snapshot): 21%, no 23%.
    let line1_again = rt.execute_query("sales.lines", &params(json!({ "sale_id": sale1_id })), &ctx).await.unwrap()[0].clone();
    assert_eq!(line1_again["tax_amount"].as_i64().unwrap(), 2100, "la venta emitida NO cambia al cambiar la regla");
    assert_eq!(line1_again["tax_rate"].as_f64().unwrap(), 21.0);

    // La venta 2 (la más nueva) refleja la regla nueva.
    let sales = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    let sale2 = sales.iter().max_by_key(|s| s["sale_number"].as_str().unwrap_or("").to_string()).unwrap();
    let line2 = rt.execute_query("sales.lines", &params(json!({ "sale_id": sale2["id"].clone() })), &ctx).await.unwrap()[0].clone();
    assert_eq!(line2["tax_amount"].as_i64().unwrap(), 2300, "la venta nueva usa la regla nueva (23%)");
}
