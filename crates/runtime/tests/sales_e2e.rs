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
    rt.install_from_dir(&mdir("taxes")).await.expect("instalar taxes"); // inventory depende de taxes (ADR-0066)
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
async fn sale_persists_staff_id_and_breaks_down_by_staff() {
    // Atribución por profesional: la venta guarda staff_id (≠ employee_id), lo expone en
    // sales.get/list, y sales.by_staff lo agrega por profesional para el cierre del día.
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // dos ventas atribuidas a staff-A, una a staff-B.
    let mk = |staff: &str, price: i64| params(json!({
        "tax_included": true, "amount_tendered": 0, "staff_id": staff,
        "items": [{ "product_name": "Corte", "price": price, "quantity": 1, "tax_rate": 21.0, "is_service": true }]
    }));
    rt.execute_command("sales.complete_sale", &mk("staff-A", 2000), &ctx).await.unwrap();
    rt.execute_command("sales.complete_sale", &mk("staff-A", 3000), &ctx).await.unwrap();
    rt.execute_command("sales.complete_sale", &mk("staff-B", 1000), &ctx).await.unwrap();

    // sales.get expone staff_id.
    let sale = &rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap()[0];
    let got = rt.execute_query("sales.get", &params(json!({"sale_id": sale["id"]})), &ctx).await.unwrap();
    assert!(got[0]["staff_id"].is_string(), "sales.get debe exponer staff_id");

    // sales.by_staff: 2 filas (A y B), A con gross 50€ (5000 céntimos) y 2 ventas, B con 10€.
    let by_staff = rt.execute_query("sales.by_staff", &params(json!({
        "date_from": "2026-01-01", "date_to": "2030-12-31"
    })), &ctx).await.unwrap();
    assert_eq!(by_staff.len(), 2, "una fila por profesional: {by_staff:?}");
    let a = by_staff.iter().find(|r| r["staff_id"] == json!("staff-A")).unwrap();
    assert_eq!(a["sales_count"].as_i64().unwrap(), 2);
    assert_eq!(a["gross_total"].as_i64().unwrap(), 5000); // 20€ + 30€ = 50.00€
    let b = by_staff.iter().find(|r| r["staff_id"] == json!("staff-B")).unwrap();
    assert_eq!(b["gross_total"].as_i64().unwrap(), 1000);
}

#[tokio::test]
async fn by_staff_respects_date_range_and_excludes_unattributed() {
    // Ventas sin staff_id NO aparecen en by_staff; el rango de fechas acota.
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // venta SIN staff (TPV normal) + venta CON staff.
    rt.execute_command("sales.complete_sale", &params(json!({
        "items": [{ "product_name": "Café", "price": 121, "quantity": 1, "tax_rate": 21.0 }]
    })), &ctx).await.unwrap();
    rt.execute_command("sales.complete_sale", &params(json!({
        "staff_id": "staff-X",
        "items": [{ "product_name": "Corte", "price": 2000, "quantity": 1, "tax_rate": 21.0 }]
    })), &ctx).await.unwrap();

    // rango amplio: solo la atribuida.
    let rows = rt.execute_query("sales.by_staff", &params(json!({
        "date_from": "2026-01-01", "date_to": "2030-12-31"
    })), &ctx).await.unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["staff_id"], json!("staff-X"));

    // rango en el pasado: ninguna venta (las de hoy quedan fuera).
    let none = rt.execute_query("sales.by_staff", &params(json!({
        "date_from": "2020-01-01", "date_to": "2020-12-31"
    })), &ctx).await.unwrap();
    assert_eq!(none.len(), 0, "el rango pasado no debe incluir ventas de hoy");
}

#[tokio::test]
async fn create_from_appointment_tags_sale_and_emits_conversion() {
    // Cita→venta: pasar appointment_id construye una venta atribuida al profesional de la cita
    // y EMITE sales.sale.created_from_appointment (traza para que appointments la marque
    // convertida en SU listener — sales no toca appointments).
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, sink) = fresh().await;
    let ctx = admin();
    // El POS arma los items desde la cita (servicio, precio) y pasa staff_id + appointment_id.
    rt.execute_command("sales.complete_sale", &params(json!({
        "tax_included": true, "amount_tendered": 0,
        "staff_id": "stylist-1", "appointment_id": "appt-42",
        "customer_id": "cust-9", "customer_name": "Ana",
        "items": [{ "product_name": "Tinte", "price": 4500, "quantity": 1, "tax_rate": 21.0, "is_service": true }]
    })), &ctx).await.expect("create_from_appointment via complete_sale");

    let sale = &rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap()[0];
    let got = rt.execute_query("sales.get", &params(json!({"sale_id": sale["id"]})), &ctx).await.unwrap();
    assert_eq!(got[0]["staff_id"], json!("stylist-1"));
    assert_eq!(got[0]["appointment_id"], json!("appt-42"));

    // se emitió el evento de conversión con el appointment_id.
    let evs = sink.events.lock().unwrap();
    let conv = evs.iter().find(|(n, _)| n == "sales.sale.created_from_appointment")
        .expect("debe emitir sales.sale.created_from_appointment");
    assert_eq!(conv.1["appointment_id"], json!("appt-42"));
    assert_eq!(conv.1["staff_id"], json!("stylist-1"));
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
