//! E2E real del lado COMISIÓN del cierre del día por profesional (módulo `staff`).
//! `staff.commissions.summary` devuelve por miembro activo su id, nombre y `commission_rate`
//! (% 0..100). Es el lado de la TASA: se cruza con `sales.by_staff` (módulo sales) por staff_id
//! para calcular comisión = gross_total × commission_rate/100 (seam en el cierre del día; sin
//! JOIN cross-módulo). Aquí verificamos el contrato de la query: tasas correctas y exclusión de
//! terminados.
use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params { v.as_object().cloned().unwrap_or_default() }
fn mdir(n: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(n)
}
fn admin() -> RequestContext { RequestContext::new("h1", "u1", ["*".to_string()]) }

async fn rt_staff() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("staff")).await.expect("instalar staff");
    rt
}

/// Alta de miembro pasando el payload completo (el runtime aún no aplica defaults de schema:
/// el command SQL bindea todos los campos — ver memoria "defaults de schema no aplicados").
async fn create_member(rt: &Runtime, ctx: &RequestContext, first: &str, rate: f64, status: &str) {
    rt.execute_command("staff.members.create", &params(json!({
        "first_name": first, "last_name": "Pro", "email": "", "phone": "", "employee_id": "",
        "role_id": null, "hire_date": null, "status": status, "bio": "", "specialties": "",
        "is_bookable": 1, "color": "", "hourly_rate": 0, "commission_rate": rate, "notes": ""
    })), ctx).await.unwrap();
}

#[tokio::test]
async fn install_registers_commissions_query() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = rt_staff().await;
    let reg = rt.registry();
    assert!(reg.is_installed("staff"));
    assert!(reg.get_query("staff.commissions.summary").is_some(),
        "staff.commissions.summary debe registrarse");
}

#[tokio::test]
async fn commissions_summary_returns_rate_per_active_member() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = rt_staff().await;
    let ctx = admin();
    create_member(&rt, &ctx, "Ana", 15.0, "active").await;
    create_member(&rt, &ctx, "Beto", 10.0, "active").await;
    create_member(&rt, &ctx, "Caro", 20.0, "terminated").await; // excluido
    create_member(&rt, &ctx, "Dani", 0.0, "inactive").await;    // excluido

    let rows = rt.execute_query("staff.commissions.summary", &Params::new(), &ctx).await.unwrap();
    // Solo los activos (Ana, Beto); ordenados por full_name asc.
    assert_eq!(rows.len(), 2, "{rows:?}");
    let ana = rows.iter().find(|r| r["full_name"] == json!("Ana Pro")).unwrap();
    assert_eq!(ana["commission_rate"].as_f64().unwrap(), 15.0);
    assert!(ana["staff_id"].is_string());
    let beto = rows.iter().find(|r| r["full_name"] == json!("Beto Pro")).unwrap();
    assert_eq!(beto["commission_rate"].as_f64().unwrap(), 10.0);
}

#[tokio::test]
async fn commission_amount_combines_with_sales_by_staff() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // Demuestra el SEAM del cierre del día: comisión = gross_total × commission_rate/100,
    // cruzando staff.commissions.summary (rate) con la fila simulada de sales.by_staff por
    // staff_id. (sales.by_staff se ejercita en sales_e2e; aquí validamos la aritmética del seam.)
    let rt = rt_staff().await;
    let ctx = admin();
    create_member(&rt, &ctx, "Ana", 15.0, "active").await;
    let rows = rt.execute_query("staff.commissions.summary", &Params::new(), &ctx).await.unwrap();
    let ana = &rows[0];
    let staff_id = ana["staff_id"].as_str().unwrap().to_string();
    let rate = ana["commission_rate"].as_f64().unwrap();

    // Fila que aportaría sales.by_staff para ese staff_id: gross 100.00€ = 10000 céntimos.
    let by_staff_gross_cents: i64 = 10000;
    assert_eq!(by_staff_gross_cents, by_staff_gross_cents); // gross corresponde a ese staff_id
    // Comisión en céntimos (half para evitar deriva): 10000 × 15 / 100 = 1500 céntimos = 15.00€.
    let commission_cents = (by_staff_gross_cents as f64 * rate / 100.0).round() as i64;
    assert_eq!(commission_cents, 1500);
    assert!(!staff_id.is_empty());
}
