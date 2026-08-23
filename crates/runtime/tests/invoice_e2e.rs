//! E2E real del módulo `invoice` (portado de old_modules/m_invoice v1.0.6). Entidad
//! fiscal: series con numeración monotónica, líneas con tax_breakdown, rectificación
//! (R1 negada), e inmutabilidad. Incluye la cadena sale.completed → auto-F2.
use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params { v.as_object().cloned().unwrap_or_default() }
fn mdir(n: &str) -> PathBuf { erplora_runtime::e2e_support::modules_root().join(n) }
// The ctx shares the Runtime's hub_id (DEV_HUB_ID) so `set_business_identity` and the dispatcher's
// enricher read the SAME `hub_settings` row — required since the fiscal precondition gate
// (hub#328, ADR-0203): issuing an invoice needs the hub's business identity configured.
fn admin() -> RequestContext { RequestContext::new(erplora_runtime::DEV_HUB_ID, "u1", ["*".to_string()]) }
fn wasm() -> bool { mdir("invoice").join("dist/handler.wasm").exists() }

/// `idempotency_key` del intento de cobro — obligatorio en `sales.complete_sale` (sales#20): una
/// clave distinta por venta esperada. Aquí `sales` solo es el ORIGEN de la factura, pero la venta
/// tiene que poder crearse para que la cadena `sale.completed → invoice.create_from_sale` corra.
fn key(k: &str) -> serde_json::Value { json!(format!("invoice-e2e-{k}")) }

/// Id del método de pago EN EFECTIVO del catálogo del hub.
///
/// «El cliente propone, el servidor dispone» (sales#20): cuando el hub tiene catálogo de métodos
/// de pago, `complete_sale` exige un `payment_method_id` que esté EN él —una venta sin método se
/// rechaza con `sales.payment_method_required`—. Se resuelve por la query pública en vez de
/// componer el id del seed a mano: así el test no se ata a cómo `sales` construye sus ids.
async fn cash_method_id(rt: &Runtime, ctx: &RequestContext) -> String {
    let rows = rt.execute_query("sales.payment_methods", &Params::new(), ctx).await
        .expect("sales.payment_methods");
    rows.iter()
        .find(|r| r["type"] == json!("cash"))
        .unwrap_or_else(|| panic!("el catálogo del hub debe traer el método `cash`: {rows:?}"))
        ["id"].as_str().expect("id del método de pago").to_string()
}

/// Configures the hub's business identity (ADR-0061 single source) — the fiscal precondition
/// (hub#328): without it, `invoice.*` commands are rejected with `FiscalPrecondition`.
async fn set_business_identity(rt: &Runtime) {
    let mut up = serde_json::Map::new();
    up.insert("business_tax_id".into(), json!("B12345674"));
    up.insert("business_legal_name".into(), json!("Mi Empresa SL"));
    rt.set_settings(&up, "u1").await.expect("set business identity");
}

/// Runtime con la cadena completa de dependencias de `invoice`.
///
/// `invoice` declara `depends_on: ["sales"]` (necesario para la `read` de `sales.get` que valida
/// la existencia de la venta en `create_from_sale`, hub#108), y `sales` a su vez depende de
/// `inventory`+`taxes`. Sin instalar toda la cadena, `invoice` no se instala y la read no resuelve.
async fn rt_invoice() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    for m in ["taxes", "inventory", "customers", "sales", "invoice"] {
        rt.install_from_dir(&mdir(m)).await.unwrap_or_else(|e| panic!("instalar {m}: {e}"));
    }
    set_business_identity(&rt).await;
    rt
}

#[tokio::test]
async fn install_registers_capabilities() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = rt_invoice().await;
    let reg = rt.registry();
    assert!(reg.is_installed("invoice"));
    assert!(reg.get_command("invoice.create").is_some());
    assert!(reg.get_command("invoice.rectify").is_some());
    // Al instalar toda la cadena de dependencias de invoice, otros módulos también escuchan
    // sale.completed (inventory, customers). Lo que importa es que invoice SÍ está suscrito.
    let listeners = reg.listeners_for("sale.completed");
    assert!(
        listeners.iter().any(|l| l == "invoice.create_from_sale"),
        "invoice.create_from_sale debe escuchar sale.completed; listeners reales: {listeners:?}"
    );
}

#[tokio::test]
async fn create_invoice_with_lines_and_numbering() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm() { eprintln!("SKIP: invoice handler.wasm ausente"); return; }
    let rt = rt_invoice().await;
    let ctx = admin();
    let res = rt.execute_command("invoice.create", &params(json!({
        "series_code": "FACT", "issuer_nif": "B12345674", "issuer_name": "Mi Empresa SL",
        "customer_name": "ACME", "customer_tax_id": "B99",
        "items": [
            { "description": "Consultoría", "quantity": 1_000_000, "unit_price": 10000, "tax_rate": 21.0 },
            { "description": "Soporte", "quantity": 2_000_000, "unit_price": 5000, "tax_rate": 10.0 }
        ]
    })), &ctx).await.expect("create_invoice WASM");
    assert_eq!(res["operations"], json!(5)); // ensure + bump + invoice + 2 líneas

    let invs = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(invs.len(), 1);
    let inv = &invs[0];
    assert_eq!(inv["invoice_type"], json!("F1"));
    assert!(inv["number"].as_str().unwrap().starts_with("FACT-"), "{}", inv["number"]);
    assert!(inv["number"].as_str().unwrap().ends_with("-000001"));
    assert_eq!(inv["base_amount"].as_i64().unwrap(), 20000); // 200€ céntimos
    assert_eq!(inv["tax_amount"].as_i64().unwrap(), 3100);
    assert_eq!(inv["total_amount"].as_i64().unwrap(), 23100);

    let lines = rt.execute_query("invoice.lines", &params(json!({"invoice_id": inv["id"]})), &ctx).await.unwrap();
    assert_eq!(lines.len(), 2);
}

#[tokio::test]
async fn second_invoice_increments_series() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm() { eprintln!("SKIP"); return; }
    let rt = rt_invoice().await;
    let ctx = admin();
    // hub#1132 — la serie FACT es F1, y una F1 SIN NIF de cliente la rechaza `invoice` desde
    // invoice#52/#58 (`invoice.f1_requires_customer_tax_id`): sin él la AEAT la devuelve con el
    // error 1189 y el documento es en realidad un tique simplificado. Este test mide la NUMERACIÓN,
    // así que se le da el cliente que la serie exige y se deja intacto lo que comprueba.
    let p = params(json!({ "series_code": "FACT", "customer_name": "ACME", "customer_tax_id": "B99",
        "items": [{ "description": "X", "quantity": 1_000_000, "unit_price": 1000, "tax_rate": 21.0 }] }));
    rt.execute_command("invoice.create", &p, &ctx).await.unwrap();
    rt.execute_command("invoice.create", &p, &ctx).await.unwrap();
    let mut nums: Vec<String> = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap()
        .iter().map(|i| i["number"].as_str().unwrap().to_string()).collect();
    nums.sort();
    assert!(nums[0].ends_with("-000001") && nums[1].ends_with("-000002"), "{nums:?}");
}

#[tokio::test]
async fn rectify_creates_negated_and_cancels_original() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm() { eprintln!("SKIP"); return; }
    let rt = rt_invoice().await;
    let ctx = admin();
    // hub#1132 — misma razón: la original es una F1 y necesita el NIF del cliente para poder
    // emitirse. Lo que este test comprueba (la R1 negada y la anulación) no cambia.
    rt.execute_command("invoice.create", &params(json!({ "series_code": "FACT", "customer_name": "ACME",
        "customer_tax_id": "B99",
        "items": [{ "description": "X", "quantity": 1_000_000, "unit_price": 10000, "tax_rate": 21.0 }] })), &ctx).await.unwrap();
    let orig = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap()[0].clone();
    let orig_id = orig["id"].as_str().unwrap().to_string();
    assert_eq!(orig["total_amount"].as_i64().unwrap(), 12100);

    // rectificar (R1 negada). issue_date lo necesita el SELECT → lo pasamos.
    rt.execute_command("invoice.rectify", &params(json!({
        "original_id": orig_id, "reason": "Error en importe", "year": 2026,
        "issue_date": "2026-05-31"
    })), &ctx).await.unwrap();

    let all = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(all.len(), 2);
    let rect = all.iter().find(|i| i["invoice_type"] == json!("R1")).expect("R1 existe");
    assert_eq!(rect["total_amount"].as_i64().unwrap(), -12100, "importes negados");
    assert!(rect["number"].as_str().unwrap().starts_with("RECT-"));
    // original cancelada.
    let o = rt.execute_query("invoice.get", &params(json!({"invoice_id": orig_id})), &ctx).await.unwrap();
    assert_eq!(o[0]["status"], json!("cancelled"));
}

#[tokio::test]
async fn auto_f2_on_sale_completed() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // Cadena cross-módulo: una venta (sales) auto-crea una factura F2 (invoice).
    if !mdir("sales").join("dist/handler.wasm").exists() || !wasm() { eprintln!("SKIP"); return; }
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("taxes")).await.unwrap();
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap();
    // invoice depende de sales (depends_on), así que sales va PRIMERO; si no, la instalación de
    // invoice falla con MissingDependency. (La read sales.get de create_from_sale, hub#108.)
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    rt.install_from_dir(&mdir("invoice")).await.unwrap();
    set_business_identity(&rt).await;
    let ctx = admin();

    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("auto-f2"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "customer_name": "Bar Manolo", "tax_included": false,
        "items": [{ "product_name": "Café", "price": 200, "quantity": 3_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.unwrap();
    // Entrega asíncrona: el relay procesa sale.completed → invoice.create_from_sale.
    rt.drain_outbox().await.unwrap();

    // invoice escuchó sale.completed → F2 TICKET con la línea de la venta.
    let invs = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(invs.len(), 1, "una venta debe auto-crear 1 factura F2");
    let inv = &invs[0];
    assert_eq!(inv["invoice_type"], json!("F2"));
    assert_eq!(inv["series"], json!("TICKET"));
    assert_eq!(inv["source_type"], json!("sale"));
    // céntimos: base 3*200 = 600, tax 21% = 126.
    assert_eq!(inv["base_amount"].as_i64().unwrap(), 600);
    assert_eq!(inv["tax_amount"].as_i64().unwrap(), 126);
}

#[tokio::test]
async fn auto_f2_propagates_business_issuer_via_outbox() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // REGRESIÓN QA (2026-06-25): la identidad fiscal del hub (hub_settings, ADR-0061) debe llegar a
    // la factura F2 que se crea de forma ASÍNCRONA por el relay del Outbox (sale.completed →
    // invoice.create_from_sale, depth>0). Antes la enriquecedora del dispatcher solo corría a
    // depth==0, así que las facturas del relay salían con issuer_nif='' → VeriFactu no encadenaba.
    if !mdir("sales").join("dist/handler.wasm").exists() || !wasm() { eprintln!("SKIP"); return; }
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("taxes")).await.unwrap();
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap();
    // invoice depende de sales (depends_on) → sales PRIMERO (ver auto_f2_on_sale_completed).
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    rt.install_from_dir(&mdir("invoice")).await.unwrap();
    // El ctx debe compartir hub_id con el Runtime (DEV_HUB_ID) para que set_settings y la
    // enriquecedora lean la MISMA fila de hub_settings.
    let ctx = RequestContext::new(erplora_runtime::DEV_HUB_ID, "u1", ["*".to_string()]);

    // Identidad fiscal de negocio del hub (la pondría el setup fiscal guiado / PUT /api/settings).
    let mut up = serde_json::Map::new();
    up.insert("business_tax_id".into(), json!("B12345674"));
    up.insert("business_legal_name".into(), json!("Peluquería Demo SL"));
    rt.set_settings(&up, "u1").await.expect("set business identity");

    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("issuer-por-el-outbox"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "customer_name": "Cliente", "tax_included": true,
        "items": [{ "product_name": "Corte", "price": 2500, "quantity": 1_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.unwrap();
    rt.drain_outbox().await.unwrap();

    let invs = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(invs.len(), 1);
    // invoice.list no proyecta issuer_nif → leemos el detalle con invoice.get.
    let mut gp = Params::new();
    gp.insert("invoice_id".into(), invs[0]["id"].clone());
    let detail = rt.execute_query("invoice.get", &gp, &ctx).await.unwrap();
    assert_eq!(
        detail[0]["issuer_nif"].as_str().unwrap(),
        "B12345674",
        "la factura auto-F2 del relay debe llevar el NIF emisor de hub_settings"
    );
}

// ── hub#108: create_from_sale con sale_id inexistente debe FALLAR, no facturar cero ───────────────
//
// Regresión fiscal (P0): un `invoice.create_from_sale` directo con un `sale_id` que no existe
// generaba una factura cero (source_id inexistente, NIF vacío, total 0), consumiendo numeración y
// contaminando totales/trazabilidad. El handler ahora valida la existencia de la venta contra la
// `read` de confianza `sales.get` (el host la pre-carga en `context.reads`) y rechaza si la venta
// no está. El rechazo es un trap WASM → el runtime NO persiste nada (ni factura ni numeración).

/// Un `sale_id` inexistente: el command falla, no se crea ninguna factura y la numeración de la
/// serie TICKET NO se consume (la primera factura válida posterior sale con `-000001`).
#[tokio::test]
async fn create_from_sale_nonexistent_sale_id_fails_and_creates_no_invoice() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm() { eprintln!("SKIP: invoice handler.wasm ausente"); return; }
    let rt = rt_invoice().await;
    let ctx = admin();

    // sale_id que NO existe en el hub → la read `sales.get` devuelve 0 filas → el handler rechaza.
    let err = rt.execute_command("invoice.create_from_sale", &params(json!({
        "sale_id": "__missing_sale__",
        "customer_name": "Nadie",
        "items": [{ "product_name": "Café", "quantity": 1_000_000, "unit_price": 100, "tax_rate": 21.0 }]
    })), &ctx).await.unwrap_err();
    // Error estable (no un panic opaco): el handler emite `sale_not_found: …`.
    let msg = err.to_string();
    assert!(
        msg.contains("sale_not_found"),
        "esperaba rechazo sale_not_found para una venta inexistente; llegó: {msg}"
    );

    // Ninguna factura se creó (antes quedaba una factura cero con source inexistente).
    let invs = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    assert!(invs.is_empty(), "una venta inexistente NO debe generar factura; list: {invs:?}");

    // Y la numeración NO se consumió: la primera factura válida posterior sale con -000001.
    // (El rechazo ocurre ANTES de persistir → el contador de serie no se incrementa.)
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("venta-real-tras-el-rechazo"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "customer_name": "Bar Real", "tax_included": false,
        "items": [{ "product_name": "Café", "price": 100, "quantity": 1_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.expect("crear una venta real");
    rt.drain_outbox().await.unwrap();
    let invs = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(invs.len(), 1, "la venta real auto-crea exactamente 1 factura");
    assert!(
        invs[0]["number"].as_str().unwrap().ends_with("-000001"),
        "el primer número debe ser 000001 (el intento fallido no consumió numeración): {}",
        invs[0]["number"]
    );
}

/// Un `sale_id` REAL: la read `sales.get` encuentra la venta → el handler emite la factura F2
/// correcta, enlazada al source y con los importes de la venta.
#[tokio::test]
async fn create_from_sale_with_real_sale_creates_correct_invoice() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm() { eprintln!("SKIP: invoice handler.wasm ausente"); return; }
    let rt = rt_invoice().await;
    let ctx = admin();

    // Creamos una venta real y obtenemos su id. NO drenamos el outbox todavía: así el relay
    // (sale.completed → create_from_sale) aún NO ha creado la F2, y la invocación DIRECTA que
    // sigue es la PRIMERA factura para esa venta (el camino del issue: la API externa llama a
    // create_from_sale con un sale_id).
    rt.execute_command("sales.complete_sale", &params(json!({
        "idempotency_key": key("venta-para-facturar-directo"),
        "payment_method_id": cash_method_id(&rt, &ctx).await,
        "customer_name": "Bar Manolo", "tax_included": false,
        "items": [{ "product_name": "Café", "price": 200, "quantity": 2_000_000, "tax_rate": 21.0 }]
    })), &ctx).await.expect("crear la venta");
    let ventas = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    let sale_id = ventas[0]["id"].as_str().unwrap().to_string();

    // Invocación DIRECTA con un sale_id real. La read sales.get resuelve la venta → la factura se
    // emite (no se rechaza). El handler devuelve 4 intenciones para 1 línea (ensure + bump + invoice
    // + 1 línea), como create_invoice con una línea.
    let res = rt.execute_command("invoice.create_from_sale", &params(json!({
        "sale_id": sale_id,
        "customer_name": "Bar Manolo",
        "items": [{ "product_name": "Café", "quantity": 2_000_000, "unit_price": 200, "tax_rate": 21.0 }]
    })), &ctx).await.expect("una venta real debe poder facturarse");
    assert_eq!(res["operations"], json!(4), "operaciones esperadas para 1 línea: {res}");

    // Exactamente 1 factura (la directa), correcta y enlazada al source.
    let invs = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(invs.len(), 1, "la invocación directa crea 1 factura: {invs:?}");
    let inv = &invs[0];
    assert_eq!(inv["invoice_type"], json!("F2"), "de venta → simplificada F2");
    assert_eq!(inv["series"], json!("TICKET"));
    assert_eq!(inv["source_type"], json!("sale"), "origen = venta");
    // céntimos: base 2×200 = 400, tax 21 % = 84, total 484.
    assert_eq!(inv["base_amount"].as_i64().unwrap(), 400, "base = 2 × 2,00 €");
    assert_eq!(inv["tax_amount"].as_i64().unwrap(), 84, "21 % de 4,00 €");
    assert_eq!(inv["total_amount"].as_i64().unwrap(), 484);

    // Idempotencia D2 (1 factura por venta, sin huecos de numeración): al drenar el outbox el relay
    // vuelve a intentar create_from_sale para la misma venta, pero ya existe → no se duplica.
    rt.drain_outbox().await.unwrap();
    let invs = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(invs.len(), 1, "idempotencia: el relay no duplica la factura de la venta");
}
