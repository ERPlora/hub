//! Test de integración del walking skeleton (Fase 1, §12). `cargo test -p erplora-runtime`.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn module_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_inventory")
}

async fn fresh_runtime() -> Runtime {
    let db = fresh_db().await;
    // The runtime's hub_id MUST match the RequestContext's ("h1"). The installer applies module
    // seeds under the RUNTIME's hub_id (`Runtime::new` defaults to DEV_HUB_ID), so a mismatch
    // installs the catalog in one hub and queries it from another: seeded reference data becomes
    // invisible and handlers silently fall back to their degraded paths (hub#594).
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&module_dir())
        .await
        .expect("install inventory");
    rt
}

fn admin_ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

#[tokio::test]
async fn install_registers_capabilities() {
    let rt = fresh_runtime().await;
    let reg = rt.registry();
    assert!(reg.is_installed("inventory"));
    assert!(reg.get_query("inventory.products.list").is_some());
    assert!(reg.get_command("inventory.products.create").is_some());
    assert!(reg.get_command("inventory.stock.decrease").is_some());
    assert_eq!(rt.navigation().len(), 1);
    assert_eq!(
        reg.listeners_for("pos.sale.completed"),
        ["inventory.stock.decrease"]
    );
}

#[tokio::test]
async fn create_then_list_scoped_by_hub() {
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();

    let before = rt
        .execute_query("inventory.products.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(before.len(), 0);

    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Café", "sku": "CAF", "price": 4.5, "stock": 10 })),
        &ctx,
    )
    .await
    .unwrap();

    let rows = rt
        .execute_query("inventory.products.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["name"], json!("Café"));
    assert_eq!(rows[0]["stock"], json!(10.0));

    // Otro hub no ve el producto (scope hub_id).
    let other = RequestContext::new("h2", "u9", ["*".to_string()]);
    let rows2 = rt
        .execute_query("inventory.products.list", &Params::new(), &other)
        .await
        .unwrap();
    assert_eq!(rows2.len(), 0, "hub_id debe aislar los datos entre hubs");
}

#[tokio::test]
async fn stock_decrease_updates_value() {
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Café", "sku": "CAF", "price": 4.5, "stock": 10 })),
        &ctx,
    )
    .await
    .unwrap();
    let id = rt
        .execute_query("inventory.products.list", &Params::new(), &ctx)
        .await
        .unwrap()[0]["id"]
        .as_str()
        .unwrap()
        .to_string();

    rt.execute_command(
        "inventory.stock.decrease",
        &params(json!({ "product_id": id, "qty": 4 })),
        &ctx,
    )
    .await
    .unwrap();

    let rows = rt
        .execute_query("inventory.products.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(rows[0]["stock"], json!(6.0));
}

#[tokio::test]
async fn permission_is_enforced() {
    let rt = fresh_runtime().await;
    let ro = RequestContext::new("h1", "u2", ["inventory.products.read".to_string()]);

    let err = rt
        .execute_command(
            "inventory.products.create",
            &params(json!({ "name": "X", "sku": "X", "price": 1, "stock": 1 })),
            &ro,
        )
        .await
        .unwrap_err();
    assert!(matches!(err, RuntimeError::PermissionDenied(p) if p == "inventory.products.create"));

    assert!(rt
        .execute_query("inventory.products.list", &Params::new(), &ro)
        .await
        .is_ok());
}

#[tokio::test]
async fn unknown_capabilities_error() {
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();
    // `nope` no está instalado: desde ADR-0127 la ausencia del MÓDULO tiene su propio error para
    // queries (es lo que permite a `queryOptional` distinguirla de un contrato roto). Desde
    // hub#1428 los commands llevan el MISMO error propio, por la misma razón: `commandOptional`
    // necesita distinguir "el módulo no está" de "el command no existe".
    assert!(matches!(
        rt.execute_query("nope.query", &Params::new(), &ctx)
            .await
            .unwrap_err(),
        RuntimeError::ModuleNotInstalled { .. }
    ));
    assert!(matches!(
        rt.execute_command("nope.cmd", &Params::new(), &ctx)
            .await
            .unwrap_err(),
        RuntimeError::ModuleNotInstalled { .. }
    ));
}
