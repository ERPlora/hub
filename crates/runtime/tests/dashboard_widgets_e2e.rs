//! E2E de los WIDGETS de dashboard (ADR-0054, T3 del prompt KPIs-production-ready).
//!
//! Contrato a probar: con DATOS REALES sembrados por los comandos reales de cada módulo, la
//! `query` que alimenta cada KPI del dashboard devuelve el NÚMERO CORRECTO — nunca un placeholder
//! ni un dato inventado (regla CERO MOCKS). Es el gemelo a nivel runtime de los tests de render
//! (`apps/web/src/lib/dashboard-widgets.test.ts`, T2): aquí verificamos el DATO; allí, el pintado.
//!
//! Un test por módulo con widgets (sales, inventory, staff, cash_register, verifactu): runtime con
//! SQLite en memoria, instala el módulo (+ deps en orden topológico), siembra vía comando real y
//! asserta la COLUMNA que el widget mapea (ver el bloque `widgets` de cada `module.json`):
//!   sales.today            → query `sales.today`                        cols `total`, `tickets`
//!   inventory.*            → query `inventory.products.stats`           cols `products_low_stock`,
//!                                                                         `total_inventory_value`,
//!                                                                         `products_in_stock`
//!   staff.headcount        → query `staff.members.stats`               col  `active_members`
//!   cash_register.session  → query `cash_register.current_session`     col  `expected_total`
//!   verifactu.pending      → query `verifactu.stats.compliance_summary` col `pending_count`
//!
//! Los 3 viewports (móvil/tablet/escritorio) y el pintado del ok-* son de NAVEGADOR (Playwright /
//! hub-qa contra el stack corriendo); fuera del alcance de este e2e headless de runtime.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

/// Postgres decodifica `SUM(...)` sobre enteros como `NUMERIC` → JSON **string** (contrato de
/// dinero, `pg_cell`), mientras que `COUNT(*)` es `INT8` → número. Lee un i64 en ambos casos.
fn i64_of(v: &serde_json::Value) -> i64 {
    v.as_i64()
        .or_else(|| v.as_str().and_then(|s| s.parse::<f64>().ok()).map(|f| f.round() as i64))
        .unwrap_or_else(|| panic!("valor entero/NUMERIC esperado, got {v}"))
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

/// Céntimos de un agregado: Postgres devuelve `SUM(bigint)`/`opening + SUM(...)` como NUMERIC →
/// JSON **string** (`"352"`), no número. Acepta ambas representaciones.
fn cents(v: &serde_json::Value) -> i64 {
    v.as_i64()
        .or_else(|| v.as_str().and_then(|s| s.parse::<f64>().ok()).map(|f| f.round() as i64))
        .unwrap_or_else(|| panic!("no es un importe numérico: {v:?}"))
}

fn mdir(n: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules")
        .join(n)
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn rt() -> Runtime {
    let db = fresh_db().await;
    Runtime::new(Box::new(db))
}

/// Ejecuta la query de un widget y devuelve la ÚNICA fila (las queries de KPI son singleton).
async fn kpi_row(rt: &Runtime, query: &str, ctx: &RequestContext) -> serde_json::Value {
    let rows = rt
        .execute_query(query, &Params::new(), ctx)
        .await
        .unwrap_or_else(|e| panic!("query `{query}` del widget falló: {e:?}"));
    assert!(!rows.is_empty(), "la query `{query}` del widget no devolvió filas");
    rows[0].clone()
}

// ── sales: `sales.today` → total del día + nº de tickets ─────────────────────────────────────────
#[tokio::test]
async fn sales_today_kpi_shows_real_total_and_tickets() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let mut rt = rt().await;
    // sales depende de taxes (ADR-0066) + inventory + customers.
    rt.install_from_dir(&mdir("taxes")).await.expect("taxes");
    rt.install_from_dir(&mdir("inventory")).await.expect("inventory");
    rt.install_from_dir(&mdir("customers")).await.expect("customers");
    rt.install_from_dir(&mdir("sales")).await.expect("sales");
    let ctx = admin();

    // KPI en un hub sin ventas: 0 € / 0 tickets (estado real, no placeholder).
    let empty = kpi_row(&rt, "sales.today", &ctx).await;
    assert_eq!(empty["total"].as_i64().unwrap_or(0), 0, "sin ventas el total es 0");
    assert_eq!(empty["tickets"].as_i64().unwrap_or(0), 0, "sin ventas los tickets son 0");

    // Una venta REAL: Café 1.21€×2 + Agua 1.10€×1, IVA incluido → total 352 céntimos (proven en sales_e2e).
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "tax_included": true, "amount_tendered": 2000, "customer_name": "Bar Manolo",
            "items": [
                { "product_name": "Café", "price": 121, "quantity": 2_000_000, "tax_rate": 21.0 },
                { "product_name": "Agua", "price": 110, "quantity": 1_000_000, "tax_rate": 10.0 }
            ]
        })),
        &ctx,
    )
    .await
    .expect("complete_sale");

    // El KPI refleja la venta real: 352 céntimos (3,52 €) y 1 ticket.
    let after = kpi_row(&rt, "sales.today", &ctx).await;
    assert_eq!(cents(&after["total"]), 352, "el KPI de ventas de hoy debe ser el total real");
    assert_eq!(i64_of(&after["tickets"]), 1, "el KPI de tickets debe contar la venta real");
}

// ── inventory: `inventory.products.stats` → stock bajo, valor, en stock ───────────────────────────
#[tokio::test]
async fn inventory_stats_kpis_show_real_numbers() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let mut rt = rt().await;
    rt.install_from_dir(&mdir("taxes")).await.expect("taxes");
    rt.install_from_dir(&mdir("inventory")).await.expect("inventory");
    let ctx = admin();

    // Un producto REAL con stock 3 y umbral 5 (escala 10⁶) → en stock bajo; valoración A COSTE
    // (inventory#9): 200 × 3 = 600 céntimos — cantidad × dinero SÍ divide por la escala.
    rt.execute_command(
        "inventory.products.create",
        &params(json!({
            "name": "Café", "sku": "CAF", "price": 450, "cost": 200,
            "stock": 3_000_000, "low_stock_threshold": 5_000_000, "product_type": "physical",
            "ean13": null, "description": "", "tax_category_key": null, "image": ""
        })),
        &ctx,
    )
    .await
    .expect("products.create");

    let stats = kpi_row(&rt, "inventory.products.stats", &ctx).await;
    assert_eq!(i64_of(&stats["products_low_stock"]), 1, "1 producto en stock bajo (real)");
    assert_eq!(i64_of(&stats["products_in_stock"]), 1, "1 producto con existencias (real)");
    assert_eq!(i64_of(&stats["total_inventory_value"]), 600, "valoración a COSTE: 200 × 3");
}

// ── staff: `staff.members.stats` → empleados activos ─────────────────────────────────────────────
#[tokio::test]
async fn staff_headcount_kpi_counts_active_members() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let mut rt = rt().await;
    rt.install_from_dir(&mdir("staff")).await.expect("staff");
    let ctx = admin();

    let create = |first: &str, status: &str| {
        params(json!({
            "first_name": first, "last_name": "Pro", "email": "", "phone": "", "employee_id": "",
            "role_id": null, "hire_date": null, "status": status, "bio": "", "specialties": "",
            "is_bookable": 1, "color": "", "hourly_rate": 0, "commission_rate": 0, "notes": ""
        }))
    };
    // 2 activos + 1 terminado (excluido del headcount).
    rt.execute_command("staff.members.create", &create("Ana", "active"), &ctx).await.unwrap();
    rt.execute_command("staff.members.create", &create("Beto", "active"), &ctx).await.unwrap();
    rt.execute_command("staff.members.create", &create("Caro", "terminated"), &ctx).await.unwrap();

    let stats = kpi_row(&rt, "staff.members.stats", &ctx).await;
    assert_eq!(i64_of(&stats["active_members"]), 2, "el KPI cuenta SOLO los activos reales");
}

// ── cash_register: `cash_register.current_session` → efectivo esperado en caja ─────────────────────
#[tokio::test]
async fn cash_register_current_session_kpi_shows_expected_total() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let mut rt = rt().await;
    rt.install_from_dir(&mdir("cash_register")).await.expect("cash_register");
    let ctx = admin();

    // Sesión con apertura 100,00 € (10000 céntimos) + una venta en efectivo de 50,00 €.
    rt.execute_command(
        "cash_register.session.open",
        &params(json!({
            "register_id": null, "session_number": "AB-260531-1000",
            "opening_balance": 10000, "opening_notes": ""
        })),
        &ctx,
    )
    .await
    .expect("session.open");
    let sid = rt
        .execute_query("cash_register.sessions.list", &Params::new(), &ctx)
        .await
        .unwrap()
        .last()
        .unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();
    rt.execute_command(
        "cash_register.movement.add",
        &params(json!({
            "session_id": sid, "movement_type": "sale", "amount": 5000, "payment_method": "cash",
            "sale_reference": "", "description": "venta"
        })),
        &ctx,
    )
    .await
    .expect("movement.add");

    // Esperado en caja = apertura 10000 + venta 5000 = 15000 céntimos (150,00 €).
    let session = kpi_row(&rt, "cash_register.current_session", &ctx).await;
    assert_eq!(
        cents(&session["expected_total"]),
        15000,
        "el KPI de efectivo esperado debe reflejar apertura + movimientos reales"
    );
}

// ── verifactu: `verifactu.stats.compliance_summary` → registros pendientes de la AEAT ──────────────
#[tokio::test]
async fn verifactu_pending_kpi_counts_real_records() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let mut rt = rt().await;
    // verifactu depends_on invoice (que depende de taxes + customers).
    rt.install_from_dir(&mdir("taxes")).await.expect("taxes");
    rt.install_from_dir(&mdir("customers")).await.expect("customers");
    rt.install_from_dir(&mdir("invoice")).await.expect("invoice");
    rt.install_from_dir(&mdir("verifactu")).await.expect("verifactu");
    let ctx = admin();

    // Sin registros: 0 pendientes (estado real, no placeholder).
    let empty = kpi_row(&rt, "verifactu.stats.compliance_summary", &ctx).await;
    assert_eq!(empty["pending_count"].as_i64().unwrap_or(0), 0, "sin registros, 0 pendientes");

    // Un registro VeriFactu REAL en estado `pending`. `records.create` calcula el hash-chain en el
    // PLUGIN NATIVO first-party (ADR-0009, compliance-critical), que no se enlaza en este runtime
    // headless; sembramos con el comando interno declarativo `_insert_record` (Tier-0 SQL) — la
    // INTENCIÓN exacta que el motor nativo emite: una fila verifactu_record real con status pending.
    rt.execute_command(
        "verifactu._insert_record",
        &params(json!({
            "record_id": "rec-1", "record_type": "alta", "sequence_number": 1, "invoice_id": null,
            "issuer_nif": "B12345678", "issuer_name": "Bar Manolo SL",
            "invoice_number": "F-0001", "invoice_date": "2026-07-17", "invoice_type": "F1",
            "description": "",
            "base_amount": 1000, "tax_rate": 21, "tax_breakdown": "", "tax_amount": 210, "total_amount": 1210,
            "previous_hash": "", "record_hash": "seed-hash", "is_first_record": 1,
            "generation_timestamp": "2026-07-17T10:00:00Z", "qr_url": ""
        })),
        &ctx,
    )
    .await
    .expect("_insert_record");

    let summary = kpi_row(&rt, "verifactu.stats.compliance_summary", &ctx).await;
    assert_eq!(
        i64_of(&summary["pending_count"]),
        1,
        "el KPI de pendientes debe contar el registro real recién creado"
    );
}
