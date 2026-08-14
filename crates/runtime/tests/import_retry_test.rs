//! Engine guarantees behind «retry only what did not make it in» (hub#845).
//!
//! The retry endpoint (server layer) re-executes the SAME bundle with the selection narrowed to
//! the sections that failed. What makes that safe is a property of THIS engine, not of the UI:
//!
//!   - a section that already applied is not duplicated when it is re-applied — the technical-key
//!     guard (`(hub_id, derived id)`, hub#260) skips the exact same rows, and the natural-key
//!     guards (ADR-0304, hub#753) skip rows the destination created on its own;
//!   - a retry with the selection narrowed to the failed section applies ONLY that section and
//!     leaves everything already present untouched.
//!
//! These tests pin that property against a real Postgres, with real modules from
//! `modules-workspace` — same fixtures as `import_test.rs`.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::export::{export_hub, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn modules_root() -> PathBuf {
    erplora_runtime::e2e_support::modules_root()
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "u1", ["*".to_string()])
}

async fn create_product(rt: &Runtime, hub: &str, name: &str, sku: &str) {
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": name, "sku": sku, "price": 450, "cost": 200, "stock": 10, "tax_category_key": "product.generic" })),
        &ctx(hub),
    )
    .await
    .unwrap_or_else(|e| panic!("create product {name}: {e}"));
}

async fn product_names(rt: &Runtime, hub: &str) -> Vec<String> {
    let rows = rt
        .execute_query("inventory.products.list", &params(json!({})), &ctx(hub))
        .await
        .expect("list products");
    rows.iter().filter_map(|p| p["name"].as_str().map(str::to_string)).collect()
}

fn full_export_selection() -> ExportSelection {
    ExportSelection {
        users: false,
        settings: true,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![
            ModuleDataSelection { module_id: "taxes".into(), with_data: true, tables: None },
            ModuleDataSelection { module_id: "inventory".into(), with_data: true, tables: None },
        ],
        purpose: Default::default(),
    }
}

fn import_everything() -> ImportSelection {
    ImportSelection {
        users: false,
        settings: true,
        fiscal: false,
        media: false,
        modules: vec!["taxes".into(), "inventory".into()],
    }
}

/// The selection the retry derives: ONLY what failed (here, the `inventory` data section).
fn retry_only_inventory() -> ImportSelection {
    ImportSelection {
        users: false,
        settings: false,
        fiscal: false,
        media: false,
        modules: vec!["inventory".into()],
    }
}

const CREATED_AT: &str = "2026-08-14T09:00:00Z";

/// Bundle exported from a source hub (h1) with two products in `inventory`.
async fn exported_bundle() -> erplora_runtime::export::ExportBundle {
    let db = fresh_db().await;
    let mut a = Runtime::with_hub_id(Box::new(db), "h1");
    a.install_from_dir(&modules_root().join("taxes")).await.expect("install taxes in A");
    a.install_from_dir(&modules_root().join("inventory")).await.expect("install inventory in A");
    create_product(&a, "h1", "Café", "CAF").await;
    create_product(&a, "h1", "Té verde", "TEV").await;
    export_hub(&a, "h1", &full_export_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export A")
}

/// hub#845 acceptance: a partial import (a module data section failed because the module was not
/// installed) is retried with the selection narrowed to what failed. The retry applies ONLY that
/// section, does not duplicate what the destination already has — neither what a previous section
/// applied nor what the hub created on its own (natural key, ADR-0304).
#[tokio::test]
async fn retry_applies_only_the_failed_section_and_never_duplicates_what_is_present() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let bundle = exported_bundle().await;

    // Destination hub B (tenant h2) with ONLY `taxes` installed: the `inventory` section fails.
    let db = fresh_db().await;
    let mut b = Runtime::with_hub_id(Box::new(db), "h2");
    b.install_from_dir(&modules_root().join("taxes")).await.expect("install taxes in B");

    let first = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_everything(), "h2")
        .await
        .expect("first (partial) import");
    let inv = first
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory section in the report");
    assert!(
        matches!(inv.status, SectionStatus::Failed(_)),
        "the fixture needs a REAL failure: modules/inventory should fail (module not installed), got {:?}",
        inv.status
    );

    // The admin fixes the cause (the module gets installed) and creates their OWN product whose
    // SKU collides with one the bundle carries: the retry must respect it, not duplicate it.
    b.install_from_dir(&modules_root().join("inventory")).await.expect("install inventory in B");
    create_product(&b, "h2", "Local brew", "CAF").await;

    // Retry = re-execute the SAME bundle with selection narrowed to what failed.
    let retry = import_sections(&mut b, &bundle.manifest, &bundle.files, &retry_only_inventory(), "h2")
        .await
        .expect("retry");
    let inv = retry
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory section in the retry report");
    assert!(
        matches!(inv.status, SectionStatus::Applied),
        "retried section should apply, got {:?}",
        inv.status
    );
    // What was NOT selected is not touched again.
    let settings = retry
        .sections
        .iter()
        .find(|s| s.section == "hub_settings")
        .expect("settings section in the retry report");
    assert!(
        matches!(settings.status, SectionStatus::Skipped),
        "a section that is not part of the retry selection must be Skipped, got {:?}",
        settings.status
    );

    let mut names = product_names(&b, "h2").await;
    names.sort();
    assert_eq!(
        names,
        vec!["Local brew".to_string(), "Té verde".to_string()],
        "retry must add only what was missing: the bundle's «Café» (sku CAF) is skipped because \
         the hub already has that SKU (natural key, ADR-0304), and nothing is duplicated"
    );
}

/// hub#845 acceptance: retrying an import that fully applied is a NO-OP, not a duplicate — the
/// blind case the UI cannot always prevent (the user may re-run the whole thing).
#[tokio::test]
async fn a_blind_full_reimport_of_an_applied_bundle_is_a_noop() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let bundle = exported_bundle().await;

    let db = fresh_db().await;
    let mut b = Runtime::with_hub_id(Box::new(db), "h2");
    b.install_from_dir(&modules_root().join("taxes")).await.expect("install taxes in B");
    b.install_from_dir(&modules_root().join("inventory")).await.expect("install inventory in B");

    import_sections(&mut b, &bundle.manifest, &bundle.files, &import_everything(), "h2")
        .await
        .expect("first import");
    let after_first = product_names(&b, "h2").await.len();
    assert_eq!(after_first, 2, "the first import brings the bundle's two products");

    // Blind re-import of the SAME bundle with the SAME full selection.
    let second = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_everything(), "h2")
        .await
        .expect("blind re-import");
    let inv = second
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory section in the second report");
    assert!(
        matches!(inv.status, SectionStatus::Applied),
        "re-applying is idempotent, not an error: {:?}",
        inv.status
    );
    assert_eq!(
        product_names(&b, "h2").await.len(),
        after_first,
        "re-importing an already applied bundle must not duplicate a single row"
    );
}
