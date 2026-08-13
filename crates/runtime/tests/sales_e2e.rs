//! E2E real del módulo `sales` (portado de old_modules/m_sales v2.4.9). El kernel
//! del POS: ventas con líneas, IVA por línea (incl/excl), número de venta atómico,
//! cambio. Instala sales (con sus deps inventory+customers) y ejercita el handler
//! WASM complete_sale + el evento sale.completed (que inventory/customers escuchan).
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{EventSink, EventSource, RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
/// Céntimos de un agregado: Postgres devuelve `SUM(bigint)` como NUMERIC → JSON **string**
/// (`"5000"`), no número. Acepta ambas representaciones (número directo o string numérico).
fn cents(v: &serde_json::Value) -> i64 {
    v.as_i64()
        .or_else(|| v.as_str().and_then(|s| s.parse::<f64>().ok()).map(|f| f.round() as i64))
        .unwrap_or_else(|| panic!("no es un importe numérico: {v:?}"))
}
fn mdir(name: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(name)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}
fn wasm_present() -> bool {
    mdir("sales").join("dist/handler.wasm").exists()
}
/// `idempotency_key` del INTENTO de cobro (sales#20): obligatorio en `sales.complete_sale` desde
/// `sales` v2.13.x. Es la clave de la PANTALLA de cobro, no de la petición — se reutiliza en los
/// reintentos para que dos peticiones no cobren dos veces. En los tests, por tanto: una clave
/// DISTINTA por cada venta esperada, la MISMA para probar el reintento.
fn key(k: &str) -> serde_json::Value {
    json!(format!("e2e-{k}"))
}

/// Id of the CASH payment method from the hub's seeded catalog.
///
/// "The client proposes, the server disposes" (sales#20): when the hub has a payment-method
/// catalog, `complete_sale` demands a `payment_method_id` that is IN it — a sale without one is
/// rejected with `sales.payment_method_required`. Resolved through the public query instead of
/// hand-composing the seed id, so the test does not couple to how `sales` builds its ids.
async fn cash_method_id(rt: &Runtime, ctx: &RequestContext) -> String {
    let rows = rt
        .execute_query("sales.payment_methods", &Params::new(), ctx)
        .await
        .expect("sales.payment_methods");
    rows.iter()
        .find(|r| r["type"] == json!("cash"))
        .unwrap_or_else(|| panic!("the hub's catalog must carry the `cash` method: {rows:?}"))["id"]
        .as_str()
        .expect("payment method id")
        .to_string()
}

#[derive(Default, Debug)]
struct Sink {
    events: Mutex<Vec<(String, serde_json::Value)>>,
}
impl EventSink for Sink {
    fn emit(&self, _source: EventSource<'_>, name: &str, payload: &serde_json::Value) {
        self.events.lock().unwrap().push((name.to_string(), payload.clone()));
    }
}

/// Runtime with inventory + customers + sales (topological dependency order).
///
/// The runtime's hub_id matches the RequestContext's ("h1"): module seeds are applied under the
/// RUNTIME's hub_id, so with `Runtime::new` (DEV_HUB_ID) the seeded payment-method catalog was
/// invisible to the tests and `complete_sale` silently degraded instead of enforcing
/// `payment_method_id` against the hub's trusted catalog (hub#594).
async fn fresh() -> (Runtime, Arc<Sink>) {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
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
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
    // sales without its deps (inventory/taxes) must fail: topological order is the installer's job.
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    let err = rt.install_from_dir(&mdir("sales")).await;
    assert!(err.is_err(), "sales sin deps debe fallar");
}

#[tokio::test]
async fn complete_sale_creates_header_and_lines() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() { eprintln!("SKIP: sales/dist/handler.wasm ausente"); return; }
    let (rt, sink) = fresh().await;
    let ctx = admin();
    // Money in CENTS (ADR-0007): price 121=1.21€, 110=1.10€; tendered 2000=20€.
    let res = rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("header-lines"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "tax_included": true, "amount_tendered": 2000, "customer_name": "Bar Manolo",
        "items": [
            { "product_name": "Café", "price": 121, "quantity": 2_000_000, "tax_rate": 21.0 },
            { "product_name": "Agua", "price": 110, "quantity": 1_000_000, "tax_rate": 10.0 }
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
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // TWO distinct charges → TWO distinct keys (sales#20): the key identifies the charge attempt,
    // so repeating it would ask for the SAME sale, not a second one.
    let pm = cash_method_id(&rt, &ctx).await;
    let venta = |k: &str| params(json!({
        "idempotency_key": key(k), "payment_method_id": pm,
        "items": [{ "product_name": "X", "price": 1000, "quantity": 1_000_000, "tax_rate": 21.0 }]
    }));
    rt.execute_command("sales.complete_sale", &venta("num-1"), &ctx).await.unwrap();
    rt.execute_command("sales.complete_sale", &venta("num-2"), &ctx).await.unwrap();
    let mut nums: Vec<String> = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap()
        .iter().map(|s| s["sale_number"].as_str().unwrap().to_string()).collect();
    nums.sort();
    assert!(nums[0].ends_with("-0001") && nums[1].ends_with("-0002"), "{nums:?}");
}

#[tokio::test]
async fn el_mismo_intento_de_cobro_reintentado_no_cobra_dos_veces() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // sales#20: `idempotency_key` es la clave del INTENTO de cobro. El caso real: el cajero da a
    // «Cobrar», la respuesta se pierde (red, tablet que se duerme) y la pantalla reintenta con la
    // MISMA clave. Debe salir UNA venta, no dos — y el cliente no paga dos veces.
    //
    // El hub CONSUME este contrato (es lo que hace que su POS pueda reintentar sin miedo), así que
    // lo fija aquí: si `sales` lo relajara, este e2e se entera — que es justo lo que no pasó cuando
    // el campo pasó a obligatorio (hub#540).
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    let intento = params(json!({
        "idempotency_key": key("reintento-del-mismo-cobro"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "amount_tendered": 1000,
        "items": [{ "product_name": "X", "price": 1000, "quantity": 1_000_000, "tax_rate": 21.0 }]
    }));

    rt.execute_command("sales.complete_sale", &intento, &ctx).await.expect("primer intento");
    rt.execute_command("sales.complete_sale", &intento, &ctx).await
        .expect("el reintento es un no-op limpio, no un error");

    let ventas = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(ventas.len(), 1, "el mismo intento de cobro reintentado deja UNA venta: {ventas:?}");
}

#[tokio::test]
async fn sale_decrements_stock_via_event() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // producto con stock 10.
    rt.execute_command("inventory.products.create", &params(json!({
        "name": "Café", "sku": "CAF", "price": 121, "cost": 50, "stock": 10_000_000,
        "low_stock_threshold": 5, "product_type": "physical",
        "ean13": null, "description": "", "tax_category_key": "product.generic", "image": ""
    })), &ctx).await.unwrap();
    let pid = rt.execute_query("inventory.products.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    // selling 3 units of that product → the event decrements stock to 7.
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("stock-decrement"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "items": [{ "product_id": pid, "product_name": "Café", "price": 121, "quantity": 3_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.unwrap();
    // Entrega asíncrona: el relay procesa sale.completed → inventory.stock.decrease.
    rt.drain_outbox().await.unwrap();

    let p = rt.execute_query("inventory.products.get", &params(json!({"product_id": pid})), &ctx).await.unwrap();
    assert_eq!(p[0]["stock"].as_i64().unwrap(), 7_000_000, "el evento sale.completed debe descontar stock");
}

#[tokio::test]
async fn sale_persists_staff_id_and_breaks_down_by_staff() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // Atribución por profesional: la venta guarda staff_id (≠ employee_id), lo expone en
    // sales.get/list, y sales.by_staff lo agrega por profesional para el cierre del día.
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // two sales attributed to staff-A, one to staff-B.
    let pm = cash_method_id(&rt, &ctx).await;
    let mk = |staff: &str, price: i64| params(json!({
        "idempotency_key": key(&format!("by-staff-{staff}-{price}")),
        "payment_method_id": pm,
        "tax_included": true, "amount_tendered": 0, "staff_id": staff,
        "items": [{ "product_name": "Corte", "price": price, "quantity": 1_000_000, "tax_rate": 21.0, "is_service": true }]
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
    assert_eq!(cents(&a["gross_total"]), 5000); // 20€ + 30€ = 50.00€
    let b = by_staff.iter().find(|r| r["staff_id"] == json!("staff-B")).unwrap();
    assert_eq!(cents(&b["gross_total"]), 1000);
}

#[tokio::test]
async fn by_staff_respects_date_range_and_excludes_unattributed() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // Ventas sin staff_id NO aparecen en by_staff; el rango de fechas acota.
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // one sale WITHOUT staff (regular POS) + one WITH staff.
    let pm = cash_method_id(&rt, &ctx).await;
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("sin-staff"), "payment_method_id": pm,
        "items": [{ "product_name": "Café", "price": 121, "quantity": 1_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.unwrap();
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("con-staff"), "payment_method_id": pm,
        "staff_id": "staff-X",
        "items": [{ "product_name": "Corte", "price": 2000, "quantity": 1_000_000, "tax_rate": 21.0 }]
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
    if !erplora_runtime::require_modules_workspace() { return; }
    // Cita→venta: pasar appointment_id construye una venta atribuida al profesional de la cita
    // y EMITE sales.sale.created_from_appointment (traza para que appointments la marque
    // convertida en SU listener — sales no toca appointments).
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, sink) = fresh().await;
    let ctx = admin();
    // The POS builds the items from the appointment (service, price) and passes staff_id + appointment_id.
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("desde-la-cita"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "tax_included": true, "amount_tendered": 0,
        "staff_id": "stylist-1", "appointment_id": "appt-42",
        "customer_id": "cust-9", "customer_name": "Ana",
        "items": [{ "product_name": "Tinte", "price": 4500, "quantity": 1_000_000, "tax_rate": 21.0, "is_service": true }]
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
    if !erplora_runtime::require_modules_workspace() { return; }
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

    // sale to that customer → record_purchase: lead → first_purchase, total_spent goes up.
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("compra-del-cliente"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "customer_id": cid, "customer_name": "Cliente",
        "items": [{ "product_name": "X", "price": 5000, "quantity": 1_000_000, "tax_rate": 0.0 }]
    })), &ctx).await.unwrap();
    // Entrega asíncrona: el relay procesa sale.completed → customers.record_purchase.
    rt.drain_outbox().await.unwrap();

    let c = rt.execute_query("customers.get", &params(json!({"customer_id": cid})), &ctx).await.unwrap();
    assert_eq!(c[0]["lifecycle_stage"], json!("first_purchase"));
    assert_eq!(c[0]["total_purchases"], json!(1));
    assert_eq!(c[0]["total_spent"].as_i64().unwrap(), 5000); // 50.00€ en céntimos
}

#[tokio::test]
async fn open_order_persists_open_order_with_lines() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ADR-0141 Gate 2: `sales.order.open` abre un `order` MUTABLE (status=open) con sus líneas
    // materializadas TEMPRANO (filas reales sales_order/sales_order_item). Invariante del ADR:
    // `sales` es AGNÓSTICO de la mesa — el payload no lleva table_id (la asociación mesa↔pedido la
    // OWNea `tables` en table_session.order_id). Importes PROVISIONALES; la cuota fiscal se congela
    // al cobrar (complete_sale).
    if !wasm_present() { eprintln!("SKIP: sales/dist/handler.wasm ausente"); return; }
    let (rt, _sink) = fresh().await;
    let ctx = admin();
    // Dinero en CÉNTIMOS (ADR-0007): 121=1.21€, 110=1.10€.
    let res = rt.execute_command("sales.order.open", &params(json!({
        "items": [
            { "product_name": "Café", "price": 121, "quantity": 2_000_000 },
            { "product_name": "Agua", "price": 110, "quantity": 1_000_000 }
        ]
    })), &ctx).await.expect("sales.order.open WASM");
    assert_eq!(res["operations"], json!(3)); // 1 cabecera + 2 líneas materializadas

    let orders = rt.execute_query("sales.orders.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(orders.len(), 1);
    assert_eq!(orders[0]["status"], json!("open"), "el pedido nace abierto (mutable)");
    // provisional_total = 121*2 + 110 = 352 céntimos (display, no fiscal).
    assert_eq!(orders[0]["provisional_total"].as_i64().unwrap(), 352);
    let oid = orders[0]["id"].as_str().unwrap().to_string();

    let lines = rt.execute_query("sales.order.lines", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(lines.len(), 2, "una línea real por artículo (materialización temprana)");
    let cafe = lines.iter().find(|l| l["product_name"] == json!("Café")).unwrap();
    assert_eq!(cafe["quantity"].as_i64().unwrap(), 2_000_000, "punto fijo 10⁶ (ADR-0147)");
    assert_eq!(cafe["line_total"].as_i64().unwrap(), 242); // 121*2, provisional
    assert_eq!(cafe["order_id"], json!(oid), "la línea cuelga del order");
}

#[tokio::test]
async fn command_response_returns_created_ids() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ADR-0141 Gate 6: la UI necesita el id de lo que acaba de crear — el POS abre un pedido y debe
    // saber su `order_id` para añadirle líneas. El runtime es la AUTORIDAD de ids (context.new_ids),
    // pero la respuesta solo traía {ok, operations} y el id se perdía: el cliente no podía
    // correlacionar. Se devuelven los ids del lote; por convención new_ids[0] es la entidad principal.
    if !wasm_present() { eprintln!("SKIP: sales/dist/handler.wasm ausente"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    let res = rt.execute_command("sales.order.open", &params(json!({
        "items": [{ "product_name": "Café", "price": 121, "quantity": 1_000_000 }]
    })), &ctx).await.unwrap();

    let ids = res["new_ids"].as_array().expect("la respuesta debe traer los ids creados");
    let order_id = ids.first().and_then(|v| v.as_str()).expect("new_ids[0] = entidad principal");
    let ord = rt.execute_query("sales.order.get", &params(json!({"order_id": order_id})), &ctx).await.unwrap();
    assert_eq!(ord.len(), 1, "el id devuelto identifica el pedido recién creado");
    assert_eq!(ord[0]["status"], json!("open"));
}

#[tokio::test]
async fn mutate_open_order_recomputes_provisional_total() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ADR-0141 Gate 3: un pedido abierto es MUTABLE. add/update/remove línea recomputan el total
    // provisional; void lo cancela. Reemplaza el blob `sales_active_cart` por filas reales.
    if !wasm_present() { eprintln!("SKIP: sales/dist/handler.wasm ausente"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    // abre un pedido con 1 línea (Café 121×2 = 242).
    rt.execute_command("sales.order.open", &params(json!({
        "items": [{ "product_name": "Café", "price": 121, "quantity": 2_000_000 }]
    })), &ctx).await.unwrap();
    let oid = rt.execute_query("sales.orders.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    // add_line: Agua 110×1 → provisional 242 + 110 = 352.
    rt.execute_command("sales.order.add_line", &params(json!({
        "order_id": oid, "product_name": "Agua", "unit_price": 110, "quantity": 1_000_000, "line_total": 110
    })), &ctx).await.expect("add_line");
    let ord = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(ord[0]["provisional_total"].as_i64().unwrap(), 352, "add_line recomputa el total");

    // update_line: Café a qty 3 → line_total 363; total 363 + 110 = 473.
    let lines = rt.execute_query("sales.order.lines", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    let cafe_id = lines.iter().find(|l| l["product_name"] == json!("Café")).unwrap()["id"]
        .as_str().unwrap().to_string();
    let agua_id = lines.iter().find(|l| l["product_name"] == json!("Agua")).unwrap()["id"]
        .as_str().unwrap().to_string();
    rt.execute_command("sales.order.update_line", &params(json!({
        "order_id": oid, "line_id": cafe_id, "quantity": 3_000_000, "line_total": 363
    })), &ctx).await.expect("update_line");
    let ord = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(ord[0]["provisional_total"].as_i64().unwrap(), 473, "update_line recomputa el total");

    // remove_line: quita el Agua → total 363, queda 1 línea.
    rt.execute_command("sales.order.remove_line", &params(json!({
        "order_id": oid, "line_id": agua_id
    })), &ctx).await.expect("remove_line");
    let ord = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(ord[0]["provisional_total"].as_i64().unwrap(), 363, "remove_line recomputa el total");
    assert_eq!(rt.execute_query("sales.order.lines", &params(json!({"order_id": oid})), &ctx).await.unwrap().len(), 1);

    // void: el pedido abierto se cancela → status 'voided'.
    rt.execute_command("sales.order.void", &params(json!({"order_id": oid})), &ctx).await.expect("void");
    let ord = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(ord[0]["status"], json!("voided"), "el pedido queda anulado");
}

#[tokio::test]
async fn checkout_order_marks_it_completed_and_links_sale() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ADR-0141 Gate 4: cobrar un pedido (complete_sale con order_id) congela una venta INMUTABLE
    // ligada al pedido y lo marca completado (open → completed). El POS envía los items del pedido.
    if !wasm_present() { eprintln!("SKIP: sales/dist/handler.wasm ausente"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    rt.execute_command("sales.order.open", &params(json!({
        "items": [{ "product_name": "Café", "price": 121, "quantity": 2_000_000 }]
    })), &ctx).await.unwrap();
    let oid = rt.execute_query("sales.orders.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("checkout-del-pedido"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "order_id": oid, "amount_tendered": 300,
        "items": [{ "product_name": "Café", "price": 121, "quantity": 2_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.expect("checkout");

    // el pedido queda completado.
    let ord = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(ord[0]["status"], json!("completed"), "el pedido se completa al cobrar");

    // existe UNA venta inmutable ligada al pedido.
    let sales = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(sales.len(), 1);
    let sale = rt.execute_query("sales.get", &params(json!({"sale_id": sales[0]["id"]})), &ctx).await.unwrap();
    assert_eq!(sale[0]["order_id"], json!(oid), "la venta apunta al pedido");
}

#[tokio::test]
async fn split_bill_one_order_produces_two_sales() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ADR-0141 Gate 4: split-bill = 1 order → N sale. Dos cobros parciales (keep_order_open) del
    // mismo pedido producen dos ventas inmutables; el pedido se completa en el cobro FINAL.
    if !wasm_present() { eprintln!("SKIP: sales/dist/handler.wasm ausente"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    rt.execute_command("sales.order.open", &params(json!({
        "items": [
            { "product_name": "Plato A", "price": 1000, "quantity": 1_000_000 },
            { "product_name": "Plato B", "price": 500, "quantity": 1_000_000 }
        ]
    })), &ctx).await.unwrap();
    let oid = rt.execute_query("sales.orders.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    // split 1: charges Plato A, leaves the order OPEN.
    let pm = cash_method_id(&rt, &ctx).await;
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("split-plato-a"), "payment_method_id": pm,
        "order_id": oid, "keep_order_open": true, "amount_tendered": 1000,
        "items": [{ "product_name": "Plato A", "price": 1000, "quantity": 1_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.expect("split 1");
    let ord = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(ord[0]["status"], json!("open"), "un split parcial deja el pedido abierto");

    // split 2 (final): charges Plato B → completes the order.
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("split-plato-b"), "payment_method_id": pm,
        "order_id": oid, "amount_tendered": 500,
        "items": [{ "product_name": "Plato B", "price": 500, "quantity": 1_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.expect("split 2");
    let ord = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(ord[0]["status"], json!("completed"), "el cobro final completa el pedido");

    // dos ventas, ambas ligadas al MISMO pedido (1 order → N sale).
    let sales = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(sales.len(), 2, "1 order → 2 sale (split-bill)");
    for s in &sales {
        let g = rt.execute_query("sales.get", &params(json!({"sale_id": s["id"]})), &ctx).await.unwrap();
        assert_eq!(g[0]["order_id"], json!(oid), "cada venta apunta al pedido");
    }
}

#[tokio::test]
async fn el_pedido_no_sabe_de_clientes_la_junction_la_owna_customers() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ADR-0141: el pedido NO guarda `customer_id` —una tienda de alimentación vende sin cliente—.
    // La asociación cliente↔pedido la OWNea `customers` en su junction. El pedido es ajeno a ella.
    if !wasm_present() { eprintln!("SKIP: sales/dist/handler.wasm ausente"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();

    rt.execute_command("customers.create", &params(json!({
        "name": "Ana", "email": "", "phone": "", "tax_id": "", "address": "", "city": "",
        "postal_code": "", "country": "", "avatar": "", "notes": "", "lifecycle_stage": "lead",
        "source": "walk_in", "company_name": "", "birthday": null, "anniversary": null,
        "preferred_channel": "none", "marketing_consent": 0, "consent_date": null
    })), &ctx).await.unwrap();
    let cid = rt.execute_query("customers.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    let res = rt.execute_command("sales.order.open", &params(json!({
        "items": [{ "product_name": "Café", "price": 121, "quantity": 1_000_000 }]
    })), &ctx).await.unwrap();
    let oid = res["new_ids"][0].as_str().unwrap().to_string();

    // 1) el pedido NO expone cliente por ningún lado.
    let ord = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert!(ord[0].get("customer_id").is_none(), "el pedido no debe saber de clientes: {:?}", ord[0]);

    // 2) la asociación la escribe CUSTOMERS, en su junction.
    rt.execute_command("customers.orders.link", &params(json!({
        "customer_id": cid, "order_id": oid
    })), &ctx).await.expect("customers.orders.link");

    let pedidos = rt.execute_query("customers.orders.by_customer", &params(json!({"customer_id": cid})), &ctx)
        .await.unwrap();
    assert_eq!(pedidos.len(), 1, "el cliente tiene su pedido enlazado");
    assert_eq!(pedidos[0]["order_id"], json!(oid));

    // 3) re-asignar NO duplica: un pedido tiene como mucho un cliente.
    rt.execute_command("customers.orders.link", &params(json!({
        "customer_id": cid, "order_id": oid
    })), &ctx).await.unwrap();
    let otra_vez = rt.execute_query("customers.orders.by_customer", &params(json!({"customer_id": cid})), &ctx)
        .await.unwrap();
    assert_eq!(otra_vez.len(), 1, "re-asignar sustituye, no duplica");
}

#[tokio::test]
async fn un_command_tier0_tambien_devuelve_el_id_que_acaba_de_crear() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // Encontrado en el navegador (ADR-0141/0144): el camarero toca 5 veces la tortilla, la pantalla
    // marca 5 y la BD guarda 1. Causa: `sales.order.add_line` es Tier-0 (SQL puro) y ese camino
    // respondía `{ok:true}` a secas, sin el id de la fila. El POS se queda sin `line_id`, y cada
    // toque posterior sube la cantidad EN PANTALLA sin persistirla — en silencio. Si la comanda se
    // retoma en otra tablet o tras recargar, se sirven 5 y se cobra 1.
    //
    // El runtime ya generaba el id (`:new_id` de system_params); solo faltaba devolverlo, igual que
    // hace el camino WASM.
    if !wasm_present() { eprintln!("SKIP: sales/dist/handler.wasm ausente"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    let res = rt.execute_command("sales.order.open", &params(json!({
        "items": [{ "product_name": "Caña", "price": 250, "quantity": 1_000_000 }]
    })), &ctx).await.unwrap();
    let oid = res["new_ids"][0].as_str().unwrap().to_string();

    let res = rt.execute_command("sales.order.add_line", &params(json!({
        "order_id": oid, "product_id": null, "product_name": "Tortilla", "product_sku": "",
        "quantity": 1_000_000, "unit_price": 750, "is_gift": 0, "gift_reason": "",
        "tax_category_key": "", "cost": 0, "line_total": 750
    })), &ctx).await.expect("añadir línea");

    let line_id = res["new_ids"][0].as_str().expect("un Tier-0 también devuelve el id creado");
    let lineas = rt.execute_query("sales.order.lines", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    let tortilla = lineas.iter().find(|l| l["product_name"] == json!("Tortilla")).expect("la línea existe");
    assert_eq!(tortilla["id"], json!(line_id), "el id devuelto es EL de la fila recién creada");

    // Y con ese id se puede subir la cantidad: es justo lo que el POS no podía hacer.
    rt.execute_command("sales.order.update_line", &params(json!({
        "order_id": oid, "line_id": line_id, "quantity": 5_000_000, "unit_price": 750,
        "is_gift": 0, "gift_reason": "", "line_total": 3750
    })), &ctx).await.expect("actualizar la cantidad");
    let lineas = rt.execute_query("sales.order.lines", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    let tortilla = lineas.iter().find(|l| l["product_name"] == json!("Tortilla")).unwrap();
    assert_eq!(tortilla["quantity"], json!(5_000_000), "5 toques, 5 tortillas (punto fijo 10⁶)");
}

#[tokio::test]
async fn split_bill_cada_uno_paga_lo_suyo() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ADR-0146 etapa 5: dos comensales, una cuenta. El primero paga SU línea; la otra sigue
    // pendiente y el pedido abierto. Al cobrar la segunda, el pedido se cierra.
    //
    // Lo que este test protege: que lo ya pagado NO vuelva a la pantalla al reanudar el pedido —
    // si volviera, se cobraría dos veces.
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();

    let res = rt.execute_command("sales.order.open", &params(json!({
        "items": [
            { "product_name": "Menú A", "price": 1200, "quantity": 1_000_000 },
            { "product_name": "Menú B", "price": 1500, "quantity": 1_000_000 }
        ]
    })), &ctx).await.unwrap();
    let oid = res["new_ids"][0].as_str().unwrap().to_string();
    let lineas = rt.execute_query("sales.order.lines", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(lineas.len(), 2);
    let linea_a = lineas.iter().find(|l| l["product_name"] == json!("Menú A")).unwrap()["id"]
        .as_str().unwrap().to_string();

    // The first diner pays their share: PARTIAL charge with their line.
    let pm = cash_method_id(&rt, &ctx).await;
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("cada-uno-lo-suyo-primero"), "payment_method_id": pm,
        "order_id": oid, "keep_order_open": true, "line_ids": [linea_a],
        "amount_tendered": 1200, "tax_included": true,
        "items": [{ "product_name": "Menú A", "price": 1200, "quantity": 1_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.expect("cobro del primero");

    // El pedido sigue abierto y solo queda LA OTRA línea.
    let pendientes = rt.execute_query("sales.order.lines", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(pendientes.len(), 1, "lo ya pagado no vuelve: {pendientes:?}");
    assert_eq!(pendientes[0]["product_name"], json!("Menú B"));
    let pedido = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(pedido[0]["status"], json!("open"), "aún queda quien pague");

    // The second diner pays: final charge, the order closes.
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("cada-uno-lo-suyo-segundo"), "payment_method_id": pm,
        "order_id": oid, "amount_tendered": 1500, "tax_included": true,
        "items": [{ "product_name": "Menú B", "price": 1500, "quantity": 1_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.expect("cobro del segundo");

    let pedido = rt.execute_query("sales.order.get", &params(json!({"order_id": oid})), &ctx).await.unwrap();
    assert_eq!(pedido[0]["status"], json!("completed"));
    let ventas = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(ventas.len(), 2, "una cuenta → DOS ventas, cada una con lo suyo");
}

#[tokio::test]
async fn media_racion_de_gambas_descuenta_medio_kilo_y_cobra_la_mitad() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ADR-0147 de punta a punta por el PAR sales↔inventory: el caso que abrió todo esto.
    // Antes: `quantity: 0.5` viajaba como f64 → inventory `as_i64(0.5)` = 0 → `qty <= 0 →
    // continue` → vender al peso NO descontaba stock, en silencio. Ahora la cantidad es punto
    // fijo 10⁶ en el comando, la línea, el evento y el movimiento de stock — el mismo número.
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, sink) = fresh().await;
    let ctx = admin();

    // Gambas al peso: unidad kg (escalón 1 g), 12,00 €/kg, 2,5 kg en cámara.
    rt.execute_command("inventory.products.create", &params(json!({
        "name": "Gambas", "sku": "GAM", "price": 1200, "cost": 800, "stock": 2_500_000,
        "unit_code": "kg", "low_stock_threshold": 0, "product_type": "physical",
        "ean13": null, "description": "", "tax_category_key": "product.generic", "image": ""
    })), &ctx).await.unwrap();
    let pid = rt.execute_query("inventory.products.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    // Half portion: 0.5 kg with its unit context FROZEN (§2.4).
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("media-racion-de-gambas"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "tax_included": true, "amount_tendered": 600,
        "items": [{
            "product_id": pid, "product_name": "Gambas", "price": 1200, "quantity": 500_000,
            "unit_code": "kg", "unit_name": "Kilogram", "increment_value": 1_000,
            "tax_rate": 21.0
        }]
    })), &ctx).await.expect("vender 0,5 kg");
    rt.drain_outbox().await.unwrap();

    // El dinero: 1200 × 0,5 = 600 céntimos — un solo HALF_UP, por línea (ADR-0123 intacto).
    let sale = &rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap()[0];
    assert_eq!(sale["total"].as_i64().unwrap(), 600, "medio kilo cuesta la mitad");
    let lines = rt.execute_query("sales.lines", &params(json!({"sale_id": sale["id"]})), &ctx).await.unwrap();
    assert_eq!(lines[0]["quantity"].as_i64(), Some(500_000), "la línea persiste el punto fijo");
    assert_eq!(lines[0]["unit_code"], json!("kg"), "y su unidad congelada");

    // El evento habló el mismo idioma: entero 10⁶, nunca float.
    let evs = sink.events.lock().unwrap();
    let (_, ev) = evs.iter().find(|(n, _)| n == "sale.completed").expect("sale.completed");
    assert_eq!(ev["items"][0]["quantity"].as_i64(), Some(500_000), "{:?}", ev["items"][0]["quantity"]);
    drop(evs);

    // Y el stock bajó MEDIO KILO: quedan 2 kg. (El bug era que quedaban 2,5 y nadie se enteraba.)
    let p = rt.execute_query("inventory.products.get", &params(json!({"product_id": pid})), &ctx).await.unwrap();
    assert_eq!(p[0]["stock"].as_i64().unwrap(), 2_000_000, "0,5 kg SÍ descuenta 0,5 kg");
}

#[tokio::test]
async fn una_cantidad_fuera_de_la_rejilla_no_crea_venta_ni_toca_stock() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ADR-0147 §2.2: el incremento VALIDA, no redondea. Medio gramo con escalón de gramo →
    // el comando se RECHAZA entero: ni venta, ni líneas, ni evento, ni stock movido.
    if !wasm_present() { eprintln!("SKIP"); return; }
    let (rt, _) = fresh().await;
    let ctx = admin();
    rt.execute_command("inventory.products.create", &params(json!({
        "name": "Azafrán", "sku": "AZA", "price": 900_000, "cost": 0, "stock": 1_000_000,
        "unit_code": "kg", "low_stock_threshold": 0, "product_type": "physical",
        "ean13": null, "description": "", "tax_category_key": "product.generic", "image": ""
    })), &ctx).await.unwrap();
    let pid = rt.execute_query("inventory.products.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    let r = rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("azafran-fuera-de-rejilla"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "items": [{
            "product_id": pid, "product_name": "Azafrán", "price": 900_000, "quantity": 500,
            "unit_code": "kg", "increment_value": 1_000, "tax_rate": 21.0
        }]
    })), &ctx).await;
    // El rechazo debe ser POR LA REJILLA. Un `is_err()` a secas se conformaba con cualquier fallo:
    // mientras al payload le faltó `idempotency_key` (hub#540) este test pasó en verde sin llegar
    // nunca a validar el incremento.
    let err = r.expect_err("medio gramo no cae en la rejilla de gramos");
    assert!(
        err.to_string().contains("quantity_off_grid"),
        "el rechazo debe ser por la rejilla del incremento (ADR-0147 §2.2), no otro error: {err}"
    );

    assert_eq!(rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap().len(), 0,
               "el rechazo no deja media venta escrita");
    rt.drain_outbox().await.unwrap();
    let p = rt.execute_query("inventory.products.get", &params(json!({"product_id": pid})), &ctx).await.unwrap();
    assert_eq!(p[0]["stock"].as_i64().unwrap(), 1_000_000, "y el stock ni se ha rozado");
}
