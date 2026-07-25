//! E2E real del módulo `invoice` (portado de old_modules/m_invoice v1.0.6). Entidad
//! fiscal: series con numeración monotónica, líneas con tax_breakdown, rectificación
//! (R1 negada), e inmutabilidad. Incluye la cadena sale.completed → auto-F2.
use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params { v.as_object().cloned().unwrap_or_default() }
fn mdir(n: &str) -> PathBuf { PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules").join(n) }
fn admin() -> RequestContext { RequestContext::new("h1", "u1", ["*".to_string()]) }
fn wasm() -> bool { mdir("invoice").join("dist/handler.wasm").exists() }

async fn rt_invoice() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("invoice")).await.expect("instalar invoice");
    rt
}

#[tokio::test]
async fn install_registers_capabilities() {
    let rt = rt_invoice().await;
    let reg = rt.registry();
    assert!(reg.is_installed("invoice"));
    assert!(reg.get_command("invoice.create").is_some());
    assert!(reg.get_command("invoice.rectify").is_some());
    assert_eq!(reg.listeners_for("sale.completed"), ["invoice.create_from_sale"]);
}

#[tokio::test]
async fn create_invoice_with_lines_and_numbering() {
    if !wasm() { eprintln!("SKIP: invoice handler.wasm ausente"); return; }
    let rt = rt_invoice().await;
    let ctx = admin();
    let res = rt.execute_command("invoice.create", &params(json!({
        "series_code": "FACT", "issuer_nif": "B12345678", "issuer_name": "Mi Empresa SL",
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
    if !wasm() { eprintln!("SKIP"); return; }
    let rt = rt_invoice().await;
    let ctx = admin();
    let p = params(json!({ "series_code": "FACT",
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
    if !wasm() { eprintln!("SKIP"); return; }
    let rt = rt_invoice().await;
    let ctx = admin();
    rt.execute_command("invoice.create", &params(json!({ "series_code": "FACT", "customer_name": "ACME",
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
    // Cadena cross-módulo: una venta (sales) auto-crea una factura F2 (invoice).
    if !mdir("sales").join("dist/handler.wasm").exists() || !wasm() { eprintln!("SKIP"); return; }
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("taxes")).await.unwrap();
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap();
    rt.install_from_dir(&mdir("invoice")).await.unwrap();
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    let ctx = admin();

    rt.execute_command("sales.complete_sale", &params(json!({
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
    rt.install_from_dir(&mdir("invoice")).await.unwrap();
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    // El ctx debe compartir hub_id con el Runtime (DEV_HUB_ID) para que set_settings y la
    // enriquecedora lean la MISMA fila de hub_settings.
    let ctx = RequestContext::new(erplora_runtime::DEV_HUB_ID, "u1", ["*".to_string()]);

    // Identidad fiscal de negocio del hub (la pondría el setup fiscal guiado / PUT /api/settings).
    let mut up = serde_json::Map::new();
    up.insert("business_tax_id".into(), json!("B12345674"));
    up.insert("business_legal_name".into(), json!("Peluquería Demo SL"));
    rt.set_settings(&up, "u1").await.expect("set business identity");

    rt.execute_command("sales.complete_sale", &params(json!({
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
