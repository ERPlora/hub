//! E2E ROJOS (TDD, ADR-0166 Fase 2) del LÍMITE FISCAL del reset.
//!
//! Bajo **RD 1007/2023** los registros de facturación VeriFactu son **inalterables** y van
//! encadenados por `(hub_id, issuer_nif)`. Borrar facturas ya remitidas a la AEAT no es una
//! preferencia de producto: es ilegal, y expone a ERPlora como fabricante del software de
//! facturación, no solo al cliente.
//!
//! El gate es **computable exacto**, no una heurística: una factura remitida deja rastro en
//! `verifactu_record.status` (`transmitted`/`accepted`) o en `aeat_csv`. Los datos de demo nunca
//! alcanzan ese estado (`environment='testing'`, sin CSV), así que el caso que motiva el ADR
//! —probar la demo y borrarla— queda libre.
//!
//! Contrato que fijan estos tests:
//!   - el bloqueo se ve en el `plan` (la UI deshabilita la sección **con el motivo escrito**, no
//!     descubre el error al pulsar),
//!   - `execute_reset` lo aplica **en el servidor** aunque el cliente insista, y sin efectos
//!     parciales,
//!   - bloquea **solo** las secciones fiscales: quien quiere limpiar el catálogo de demo puede,
//!   - una factura NO remitida (`pending`) no bloquea nada.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::reset::{execute_reset, plan_reset, ResetSelection};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn modules_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules")
}

fn have_modules() -> bool {
    modules_root().exists()
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "u1", ["*".to_string()])
}

/// Runtime con la cadena fiscal REAL instalada: verifactu → invoice → sales → inventory+taxes.
async fn fresh_fiscal() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    for m in ["taxes", "inventory", "sales", "invoice", "verifactu"] {
        rt.install_from_dir(&modules_root().join(m))
            .await
            .unwrap_or_else(|e| panic!("instalar {m}: {e}"));
    }
    rt
}

/// Inserta un registro VeriFactu real en la tabla del módulo. `status`/`csv` deciden si cuenta
/// como REMITIDO a la AEAT.
/// `seq` va explícito: la cadena VeriFactu tiene un único `(hub_id, issuer_nif,
/// sequence_number)`, así que dos registros del mismo hub no pueden compartir número.
async fn insert_record(rt: &Runtime, hub: &str, seq: i64, num: &str, status: &str, csv: &str) {
    let mut p = Params::new();
    p.insert("id".into(), json!(format!("rec-{hub}-{num}")));
    p.insert("hub_id".into(), json!(hub));
    p.insert("seq".into(), json!(seq));
    p.insert("num".into(), json!(num));
    p.insert("status".into(), json!(status));
    p.insert("csv".into(), json!(csv));
    rt.db()
        .execute(
            "INSERT INTO verifactu_record (id, hub_id, record_type, sequence_number, issuer_nif, \
             issuer_name, invoice_number, invoice_date, invoice_type, generation_timestamp, \
             status, aeat_csv, created_at) \
             VALUES (:id, :hub_id, 'alta', :seq, 'B12345678', 'Demo SL', :num, '2026-07-31', 'F1', \
             '2026-07-31T10:00:00+02:00', :status, :csv, '2026-07-31T10:00:00Z')",
            &p,
        )
        .await
        .expect("insertar verifactu_record");
}

async fn count(rt: &Runtime, table: &str, hub: &str) -> i64 {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub));
    let res = rt
        .db()
        .query(&format!("SELECT count(*) AS n FROM {table} WHERE hub_id = :hub_id"), &p)
        .await
        .unwrap_or_else(|e| panic!("contar {table}: {e}"));
    res.rows[0]["n"].as_i64().expect("count(*)")
}

fn blocked(plan: &erplora_runtime::reset::ResetPlan, section: &str) -> Option<String> {
    plan.sections.iter().find(|s| s.section == section).and_then(|s| s.blocked_by.clone())
}

// ── El bloqueo se VE antes de pulsar ────────────────────────────────────────────────────

#[tokio::test]
async fn plan_bloquea_las_secciones_fiscales_si_hay_facturas_remitidas() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh_fiscal().await;
    insert_record(&rt, "h1", 1, "FAC-001", "accepted", "CSV-AEAT-001").await;
    insert_record(&rt, "h1", 2, "FAC-002", "transmitted", "").await;

    let plan = plan_reset(&rt, "h1").await.expect("plan");

    let motivo = blocked(&plan, "modules/verifactu")
        .expect("modules/verifactu debe llegar BLOQUEADA a la UI, no fallar al pulsar");
    // El motivo es legible y dice CUÁNTAS: un bloqueo sin cifra no explica nada.
    assert!(motivo.contains('2'), "el motivo debe decir cuántas facturas lo bloquean: {motivo}");
    assert!(
        motivo.to_lowercase().contains("aeat"),
        "el motivo debe nombrar a la AEAT para que se entienda que es legal, no un fallo: {motivo}"
    );
    // Las secciones que SUSTENTAN esas facturas también quedan bloqueadas.
    for s in ["modules/invoice", "modules/sales"] {
        assert!(blocked(&plan, s).is_some(), "{s} debe bloquearse: sostiene las facturas remitidas");
    }
}

/// Una factura emitida pero NO remitida (`pending`, sin CSV) no está protegida por el RD: es
/// exactamente el estado de los datos de demo, y bloquear ahí haría inútil la feature.
#[tokio::test]
async fn plan_no_bloquea_nada_si_las_facturas_no_se_han_remitido() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh_fiscal().await;
    insert_record(&rt, "h1", 1, "FAC-001", "pending", "").await;
    insert_record(&rt, "h1", 2, "FAC-002", "error", "").await;

    let plan = plan_reset(&rt, "h1").await.expect("plan");

    for s in ["modules/verifactu", "modules/invoice", "modules/sales"] {
        assert!(
            blocked(&plan, s).is_none(),
            "{s} NO puede bloquearse por facturas que nunca llegaron a la AEAT"
        );
    }
}

/// El bloqueo es del hub que pregunta: las facturas remitidas del vecino no pueden congelar
/// el reset de este hub (misma BD, distinto tenant).
#[tokio::test]
async fn plan_no_se_bloquea_por_las_facturas_de_otro_hub() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh_fiscal().await;
    insert_record(&rt, "h2", 1, "FAC-VECINO", "accepted", "CSV-VECINO").await;

    let plan = plan_reset(&rt, "h1").await.expect("plan");

    assert!(
        blocked(&plan, "modules/verifactu").is_none(),
        "las facturas del hub h2 no pueden bloquear el reset de h1"
    );
}

// ── El servidor lo aplica aunque el cliente insista ─────────────────────────────────────

#[tokio::test]
async fn execute_rechaza_la_seccion_bloqueada_y_no_borra_nada() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh_fiscal().await;
    insert_record(&rt, "h1", 1, "FAC-001", "accepted", "CSV-AEAT-001").await;
    let antes = count(&rt, "verifactu_record", "h1").await;

    // Un cliente manipulado pide borrar lo fiscal pese al bloqueo.
    let sel = ResetSelection { modules: vec!["verifactu".into()], ..Default::default() };
    let res = execute_reset(&rt, "h1", &sel, "u1").await;

    assert!(res.is_err(), "el servidor debe RECHAZAR el reset de una sección bloqueada");
    let err = res.unwrap_err().to_string();
    assert!(
        err.to_lowercase().contains("aeat") || err.to_lowercase().contains("remit"),
        "el error debe explicar el motivo legal, no ser genérico: {err}"
    );
    assert_eq!(
        count(&rt, "verifactu_record", "h1").await,
        antes,
        "🔴 se borró un registro fiscal remitido a la AEAT"
    );
}

/// Bloquear el reset ENTERO por una factura dejaría tirado a quien solo quiere limpiar el
/// catálogo de la demo — que es el caso que motiva todo el ADR.
#[tokio::test]
async fn execute_deja_resetear_lo_no_fiscal_aunque_haya_facturas_remitidas() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh_fiscal().await;
    insert_record(&rt, "h1", 1, "FAC-001", "accepted", "CSV-AEAT-001").await;
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Café", "sku": "CAF", "price": 450, "cost": 200, "stock": 10 })),
        &ctx("h1"),
    )
    .await
    .expect("crear producto");

    let sel = ResetSelection { modules: vec!["inventory".into()], ..Default::default() };
    execute_reset(&rt, "h1", &sel, "u1").await.expect("el catálogo SÍ se puede limpiar");

    assert_eq!(count(&rt, "inventory_product", "h1").await, 0, "el catálogo se limpió");
    assert_eq!(
        count(&rt, "verifactu_record", "h1").await,
        1,
        "y el registro fiscal remitido sigue intacto"
    );
}
