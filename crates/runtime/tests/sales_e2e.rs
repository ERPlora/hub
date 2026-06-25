//! E2E real del módulo `sales` (portado de old_modules/m_sales v2.4.9). El kernel
//! del POS: ventas con líneas, IVA por línea (incl/excl), número de venta atómico,
//! cambio. Instala sales (con sus deps inventory+customers) y ejercita el handler
//! WASM complete_sale + el evento sale.completed (que inventory/customers escuchan).
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

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
    mdir("sales").join("dist/handler.wasm").exists()
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

/// Runtime con inventory + customers + sales (orden topológico de deps).
async fn fresh() -> (Runtime, Arc<Sink>) {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    rt.install_from_dir(&mdir("taxes")).await.expect("instalar taxes");
    rt.install_from_dir(&mdir("inventory")).await.expect("instalar inventory");
    rt.install_from_dir(&mdir("customers")).await.expect("instalar customers");
    rt.install_from_dir(&mdir("sales")).await.expect("instalar sales");
    (rt, sink)
}

#[tokio::test]
async fn install_with_deps() {
    let (rt, _) = fresh().await;
    let reg = rt.registry();
    assert!(reg.is_installed("sales"));
    assert!(reg.get_command("sales.complete_sale").is_some());
    // inventory y customers escuchan sale.completed (descuento de stock / record_purchase).
    let listeners = reg.listeners_for("sale.completed");
    assert!(listeners.contains(&"inventory.stock.decrease_on_sale".to_string()), "{listeners:?}");
    assert!(listeners.contains(&"customers.record_purchase".to_string()), "{listeners:?}");
}

#[tokio::test]
async fn missing_dep_fails() {
    // sales sin sus deps debe fallar (orden topológico es responsabilidad del instalador).
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    let err = rt.install_from_dir(&mdir("sales")).await;
    assert!(err.is_err(), "sales sin deps debe fallar");
}

#[tokio::test]
async fn complete_sale_creates_header_and_lines() {
    if !wasm_present() { eprintln!("SKIP: sales/dist/handler.wasm ausente"); return; }
    let (rt, sink) = fresh().await;
    let ctx = admin();
    // Dinero en CÉNTIMOS (ADR-0007): price 121=1.21€, 110=1.10€; tendered 2000=20€.
    let res = rt.execute_command("sales.complete_sale", &params(json!({
        "tax_included": true, "amount_tendered": 2000, "customer_name": "Bar Manolo",
        "items": [
            { "product_name": "Café", "price": 121, "quantity": 2, "tax_rate": 21.0 },
            { "product_name": "Agua", "price": 110, "quantity": 1, "tax_rate": 10.0 }
        ]
    })), &ctx).await.expect("complete_sale WASM");
    assert_eq!(res["operations"], json!(4)); // counter + sale + 2 líneas

    let sales = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(sales.len(), 1);
    let sale = &sales[0];
    assert!(sale["sale_number"].as_str().unwrap().ends_with("-0001"));
    assert_eq!(sale["total"].as_i64().unwrap(), 352); // 242 + 110 céntimos = 3.52€

    let lines = rt.execute_query("sales.lines", &params(json!({"sale_id": sale["id"]})), &ctx).await.unwrap();
    assert_eq!(lines.len(), 2);
    let cafe = lines.iter().find(|l| l["product_name"] == json!("Café")).unwrap();
    assert_eq!(cafe["net_amount"].as_i64().unwrap(), 200);   // 242/1.21 = 2.00€ = 200 céntimos
    assert_eq!(cafe["tax_amount"].as_i64().unwrap(), 42);

    // sale.completed emitido con totales.
    let evs = sink.events.lock().unwrap();
    assert!(evs.iter().any(|(n, _)| n == "sale.completed"), "{evs:?}");
}

#[tokio::test]
async fn keystone_resolves_tax_from_catalog_ignoring_client_hint() {
    // ADR-0069 E2E real: el handler resuelve el % desde `taxes` (pre-cargado por el runtime
    // vía `reads`), NO del cliente. Prueba la cadena completa keystone + taxes + sales.
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // Siembra IVA General 21% (ES) en el catálogo.
    rt.execute_command("taxes.rates.create", &params(json!({
        "code": "es-std", "name": "IVA General", "country_code": "ES", "rate_pct": 21.0
    })), &ctx).await.expect("crear tipo");
    let std_id = rt.execute_query("taxes.rates.list", &Params::new(), &ctx).await.unwrap()
        .iter().find(|r| r["code"] == json!("es-std")).unwrap()["id"].as_str().unwrap().to_string();

    // Venta: `tax_rate_id` del catálogo + un hint MENTIROSO del cliente (99). El servidor usa 21.
    rt.execute_command("sales.complete_sale", &params(json!({
        "tax_included": false,
        "items": [{ "product_name": "Café", "price": 1000, "quantity": 1, "tax_rate": 99.0, "tax_rate_id": std_id }]
    })), &ctx).await.expect("venta");

    let sales = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    let lines = rt.execute_query("sales.lines", &params(json!({"sale_id": sales[0]["id"]})), &ctx).await.unwrap();
    let l = &lines[0];
    assert_eq!(l["net_amount"].as_i64().unwrap(), 1000);
    assert_eq!(l["tax_amount"].as_i64().unwrap(), 210, "21% del catálogo, NO el 99 del cliente");
    assert_eq!(l["tax_rate"].as_f64().unwrap(), 21.0);
}

#[tokio::test]
async fn keystone_group_tax_expands_to_components() {
    // ADR-0069 E2E: un `tax_rate_id` de tipo "group" se expande a sus componentes (IVA + recargo).
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // Grupo "IVA 21 + RE 5,2": el grupo (rate 0, tax_type=group) + dos hijos con parent_id.
    rt.execute_command("taxes.rates.create", &params(json!({
        "code": "es-iva-re", "name": "IVA+RE", "country_code": "ES", "rate_pct": 0.0, "tax_type": "group"
    })), &ctx).await.expect("crear grupo");
    let gid = rt.execute_query("taxes.rates.list", &Params::new(), &ctx).await.unwrap()
        .iter().find(|r| r["code"] == json!("es-iva-re")).unwrap()["id"].as_str().unwrap().to_string();
    rt.execute_command("taxes.rates.create", &params(json!({
        "code": "es-iva", "name": "IVA", "country_code": "ES", "rate_pct": 21.0, "parent_id": gid
    })), &ctx).await.unwrap();
    rt.execute_command("taxes.rates.create", &params(json!({
        "code": "es-re", "name": "RE", "country_code": "ES", "rate_pct": 5.2, "parent_id": gid
    })), &ctx).await.unwrap();

    // Venta de 100€ (10000 céntimos) sin IVA incluido → IVA 2100 + RE 520 = 2620.
    rt.execute_command("sales.complete_sale", &params(json!({
        "tax_included": false,
        "items": [{ "product_name": "Camiseta", "price": 10000, "quantity": 1, "tax_rate_id": gid }]
    })), &ctx).await.expect("venta grupo");

    let sales = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    let lines = rt.execute_query("sales.lines", &params(json!({"sale_id": sales[0]["id"]})), &ctx).await.unwrap();
    let l = &lines[0];
    assert_eq!(l["net_amount"].as_i64().unwrap(), 10000);
    assert_eq!(l["tax_amount"].as_i64().unwrap(), 2620, "grupo IVA 21 + RE 5,2 sobre 100€ = 26,20€");
}

#[tokio::test]
async fn second_sale_increments_number() {
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    let p = params(json!({ "items": [{ "product_name": "X", "price": 1000, "quantity": 1, "tax_rate": 21.0 }] }));
    rt.execute_command("sales.complete_sale", &p, &ctx).await.unwrap();
    rt.execute_command("sales.complete_sale", &p, &ctx).await.unwrap();
    let mut nums: Vec<String> = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap()
        .iter().map(|s| s["sale_number"].as_str().unwrap().to_string()).collect();
    nums.sort();
    assert!(nums[0].ends_with("-0001") && nums[1].ends_with("-0002"), "{nums:?}");
}

#[tokio::test]
async fn sale_decrements_stock_via_event() {
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // producto con stock 10.
    rt.execute_command("inventory.products.create", &params(json!({
        "name": "Café", "sku": "CAF", "price": 121, "cost": 50, "stock": 10,
        "low_stock_threshold": 5, "product_type": "physical",
        "ean13": null, "description": "", "tax_rate_id": null, "image": ""
    })), &ctx).await.unwrap();
    let pid = rt.execute_query("inventory.products.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    // venta de 3 unidades de ese producto → evento descuenta stock a 7.
    rt.execute_command("sales.complete_sale", &params(json!({
        "items": [{ "product_id": pid, "product_name": "Café", "price": 121, "quantity": 3, "tax_rate": 21.0 }]
    })), &ctx).await.unwrap();
    // Entrega asíncrona: el relay procesa sale.completed → inventory.stock.decrease.
    rt.drain_outbox().await.unwrap();

    let p = rt.execute_query("inventory.products.get", &params(json!({"product_id": pid})), &ctx).await.unwrap();
    assert_eq!(p[0]["stock"].as_f64().unwrap(), 7.0, "el evento sale.completed debe descontar stock");
}

#[tokio::test]
async fn sale_records_customer_purchase_via_event() {
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // cliente lead.
    rt.execute_command("customers.create", &params(json!({
        "name": "Cliente", "email": "", "phone": "", "tax_id": "", "address": "", "city": "",
        "postal_code": "", "country": "", "avatar": "", "notes": "", "lifecycle_stage": "lead",
        "source": "walk_in", "company_name": "", "birthday": null, "anniversary": null,
        "preferred_channel": "none", "marketing_consent": 0, "consent_date": null
    })), &ctx).await.unwrap();
    let cid = rt.execute_query("customers.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    // venta a ese cliente → record_purchase: lead → first_purchase, total_spent sube.
    rt.execute_command("sales.complete_sale", &params(json!({
        "customer_id": cid, "customer_name": "Cliente",
        "items": [{ "product_name": "X", "price": 5000, "quantity": 1, "tax_rate": 0.0 }]
    })), &ctx).await.unwrap();
    // Entrega asíncrona: el relay procesa sale.completed → customers.record_purchase.
    rt.drain_outbox().await.unwrap();

    let c = rt.execute_query("customers.get", &params(json!({"customer_id": cid})), &ctx).await.unwrap();
    assert_eq!(c[0]["lifecycle_stage"], json!("first_purchase"));
    assert_eq!(c[0]["total_purchases"], json!(1));
    assert_eq!(c[0]["total_spent"].as_i64().unwrap(), 5000); // 50.00€ en céntimos
}
