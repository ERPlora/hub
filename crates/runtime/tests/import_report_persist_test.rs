//! E2E ROJOS (TDD, hub#763) — the import report must SURVIVE navigation.
//!
//! `ImportPanel.vue` used to start at `step = 'pick'` no matter what, so an admin who ran a
//! partial import from the Dashboard hero and followed its «see the detail in Settings › Data»
//! arrived at a blank catalogue with no report, no reason and no way forward. The Dashboard was
//! promising a screen the destination did not have.
//!
//! Contract this test fixes:
//!   - the import engine PERSISTS its report under the same `batch_id` it opens, and
//!   - `last_import_report` recovers the last report for a hub (most recent first),
//!   - so navigating away (losing the in-memory `ref`) does not lose the actionable report.
//!
//! Implementation = human column; these tests go first and FAIL.

use std::path::PathBuf;

use erplora_db::testutil::fresh_db;
use erplora_runtime::e2e_support::units;
use erplora_runtime::export::{export_hub, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection};
use erplora_runtime::reset::last_import_report;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> erplora_db::Params {
    v.as_object().cloned().unwrap_or_default()
}

fn modules_root() -> PathBuf {
    erplora_runtime::e2e_support::modules_root()
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "u1", ["*".to_string()])
}

async fn fresh() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&modules_root().join("taxes"))
        .await
        .expect("instalar taxes");
    rt.install_from_dir(&modules_root().join("inventory"))
        .await
        .expect("instalar inventory");
    rt
}

async fn create_product(rt: &Runtime, hub: &str, name: &str, sku: &str) {
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": name, "sku": sku, "price": 450, "cost": 200, "stock": units(10), "tax_category_key": "product.generic" })),
        &ctx(hub),
    )
    .await
    .unwrap_or_else(|e| panic!("crear producto {name}: {e}"));
}

fn full_selection() -> ExportSelection {
    ExportSelection {
        users: true,
        settings: true,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![
            ModuleDataSelection {
                module_id: "taxes".into(),
                with_data: true,
                tables: None,
            },
            ModuleDataSelection {
                module_id: "inventory".into(),
                with_data: true,
                tables: None,
            },
        ],
        purpose: Default::default(),
    }
}

fn import_all() -> ImportSelection {
    ImportSelection {
        users: true,
        settings: true,
        fiscal: false,
        media: false,
        modules: vec!["taxes".into(), "inventory".into()],
    }
}

const CREATED_AT: &str = "2026-08-10T19:00:00Z";

async fn exported_bundle() -> erplora_runtime::export::ExportBundle {
    let a = fresh().await;
    create_product(&a, "h1", "Café", "CAF").await;
    create_product(&a, "h1", "Té verde", "TEV").await;
    export_hub(&a, "h1", &full_selection(), "pizzeria", "es", CREATED_AT)
        .await
        .expect("export A")
}

/// After a successful import the engine's report is recoverable by `batch_id` AND as the last
/// report of the hub — losing the in-memory value (what navigation does to a Vue `ref`) must not
/// lose the actionable report (hub#763).
#[tokio::test]
async fn import_report_survives_loss_of_in_memory_value() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let bundle = exported_bundle().await;
    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h1")
        .await
        .expect("import");
    let batch_id = report
        .batch_id
        .clone()
        .expect("el informe lleva el batch_id de su lote");

    // Drop the in-memory report entirely: this is what navigating away from the hero does.
    drop(report);

    // The report is recoverable from the hub, by batch_id and as the last one.
    let stored = last_import_report(&b, "h1", &batch_id)
        .await
        .expect("recuperar el informe por batch_id")
        .expect("el informe debe estar persistido");
    let recovered: erplora_runtime::import::ImportReport =
        serde_json::from_str(&stored.report).expect("el JSON persistido es un ImportReport");
    assert!(
        recovered
            .sections
            .iter()
            .any(|s| s.section == "modules/inventory"),
        "el informe recuperado conserva sus secciones: {:?}",
        recovered.sections
    );

    let last = erplora_runtime::reset::last_import_report_for_hub(&b, "h1")
        .await
        .expect("recuperar el último informe del hub")
        .expect("debe haber un último informe");
    assert_eq!(last.batch_id, batch_id);
}

/// An import report is scoped to its hub: reading another hub's report returns nothing
/// (same guarantee as `_hub_import_batch`, which undo depends on).
#[tokio::test]
async fn import_report_is_scoped_to_its_hub() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let bundle = exported_bundle().await;
    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h1")
        .await
        .expect("import");
    let batch_id = report.batch_id.clone().expect("batch_id");

    // Same id under a DIFFERENT hub → not found (the batch belongs to h1).
    let other = last_import_report(&b, "h2", &batch_id)
        .await
        .expect("leer no falla");
    assert!(other.is_none(), "el informe de otro hub no se expone");
}
