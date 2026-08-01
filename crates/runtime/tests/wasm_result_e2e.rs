//! E2E real del canal `result` a través de guests WASM publicados (hub#70).

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::{json, Value};

fn modules_root() -> PathBuf {
    std::env::var_os("ERPLORA_MODULES_WORKSPACE")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules")
        })
}

fn module(name: &str) -> PathBuf {
    if name == "schedules" {
        if let Some(path) = std::env::var_os("ERPLORA_SCHEDULES_MODULE_DIR") {
            return PathBuf::from(path);
        }
    }
    modules_root().join(name)
}

fn params(value: Value) -> Params {
    value.as_object().cloned().unwrap_or_default()
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

#[tokio::test]
async fn taxes_calculate_returns_the_authoritative_wasm_result() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "h1");
    runtime.install_from_dir(&module("taxes")).await.unwrap();
    let ctx = admin();

    runtime
        .execute_command(
            "taxes.categories.create",
            &params(json!({ "key": "test.standard", "name": "Test standard" })),
            &ctx,
        )
        .await
        .unwrap();
    runtime
        .execute_command(
            "taxes.rules.create",
            &params(json!({
                "country_code": "ES",
                "region_code": null,
                "tax_category_key": "test.standard",
                "rate_pct": 21.0,
                "tax_type": "vat",
                "valid_from": null,
                "valid_to": null
            })),
            &ctx,
        )
        .await
        .unwrap();

    // El caller aporta importe/categoría, NO las filas internas de taxes.rules.
    let out = runtime
        .execute_command(
            "taxes.calculate",
            &params(json!({
                "amount": 1210,
                "tax_included": true,
                "tax_category_key": "test.standard"
            })),
            &ctx,
        )
        .await
        .unwrap();
    assert_eq!(out["operations"], json!(0));
    assert_eq!(out["result"]["base"], json!(1000));
    assert_eq!(out["result"]["tax"], json!(210));
    assert_eq!(out["result"]["total"], json!(1210));
    assert_eq!(out["result"]["source"], json!("rule"));
}

#[tokio::test]
async fn schedules_is_open_reads_internal_tables_and_returns_result_without_caller_rows() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "h1");
    runtime
        .install_from_dir(&module("schedules"))
        .await
        .unwrap();
    let ctx = admin();

    runtime
        .execute_command(
            "schedules.special_days.create",
            &params(json!({
                "date": "2026-12-25",
                "name": "Navidad",
                "is_closed": true
            })),
            &ctx,
        )
        .await
        .unwrap();

    // No `special_days`, `overrides` ni `business_hours` en el payload: las precarga el host desde
    // las reads declaradas y el guest las consume desde `context.reads`.
    let out = runtime
        .execute_command(
            "schedules.is_open",
            &params(json!({ "when": "2026-12-25T12:00:00Z" })),
            &ctx,
        )
        .await
        .unwrap();
    assert_eq!(out["operations"], json!(0));
    assert_eq!(out["result"]["is_open"], json!(false));
    assert_eq!(out["result"]["reason"], json!("Navidad"));
    assert_eq!(out["result"]["today"], json!("2026-12-25"));

    let error = runtime
        .execute_command(
            "schedules.is_open",
            &params(json!({ "when": "fecha-invalida" })),
            &ctx,
        )
        .await
        .unwrap_err();
    assert!(matches!(
        error,
        RuntimeError::Domain { ref code, .. } if code == "schedules.invalid_date"
    ));
}
