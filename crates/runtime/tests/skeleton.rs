//! Test de integración del walking skeleton (Fase 1, §12). `cargo test -p erplora-runtime`.
use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn module_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_inventory")
}

fn fresh_runtime() -> Runtime {
    let db = SqliteAdapter::open_in_memory().expect("sqlite en memoria");
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&module_dir()).expect("instalar inventory");
    rt
}

fn admin_ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

#[test]
fn install_registers_capabilities() {
    let rt = fresh_runtime();
    let reg = rt.registry();
    assert!(reg.is_installed("inventory"));
    assert!(reg.get_query("inventory.products.list").is_some());
    assert!(reg.get_command("inventory.products.create").is_some());
    assert!(reg.get_command("inventory.stock.decrease").is_some());
    assert_eq!(rt.navigation().len(), 1);
    assert_eq!(reg.listeners_for("pos.sale.completed"), ["inventory.stock.decrease"]);
}

#[test]
fn create_then_list_scoped_by_hub() {
    let rt = fresh_runtime();
    let ctx = admin_ctx();

    let before = rt.execute_query("inventory.products.list", &Params::new(), &ctx).unwrap();
    assert_eq!(before.len(), 0);

    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Café", "sku": "CAF", "price": 4.5, "stock": 10 })),
        &ctx,
    )
    .unwrap();

    let rows = rt.execute_query("inventory.products.list", &Params::new(), &ctx).unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["name"], json!("Café"));
    assert_eq!(rows[0]["stock"], json!(10.0));

    // Otro hub no ve el producto (scope hub_id).
    let other = RequestContext::new("h2", "u9", ["*".to_string()]);
    let rows2 = rt.execute_query("inventory.products.list", &Params::new(), &other).unwrap();
    assert_eq!(rows2.len(), 0, "hub_id debe aislar los datos entre hubs");
}

#[test]
fn stock_decrease_updates_value() {
    let rt = fresh_runtime();
    let ctx = admin_ctx();
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Café", "sku": "CAF", "price": 4.5, "stock": 10 })),
        &ctx,
    )
    .unwrap();
    let id = rt.execute_query("inventory.products.list", &Params::new(), &ctx).unwrap()[0]["id"]
        .as_str()
        .unwrap()
        .to_string();

    rt.execute_command(
        "inventory.stock.decrease",
        &params(json!({ "product_id": id, "qty": 4 })),
        &ctx,
    )
    .unwrap();

    let rows = rt.execute_query("inventory.products.list", &Params::new(), &ctx).unwrap();
    assert_eq!(rows[0]["stock"], json!(6.0));
}

#[test]
fn permission_is_enforced() {
    let rt = fresh_runtime();
    let ro = RequestContext::new("h1", "u2", ["inventory.products.read".to_string()]);

    let err = rt
        .execute_command(
            "inventory.products.create",
            &params(json!({ "name": "X", "sku": "X", "price": 1, "stock": 1 })),
            &ro,
        )
        .unwrap_err();
    assert!(matches!(err, RuntimeError::PermissionDenied(p) if p == "inventory.products.create"));

    assert!(rt.execute_query("inventory.products.list", &Params::new(), &ro).is_ok());
}

#[test]
fn unknown_capabilities_error() {
    let rt = fresh_runtime();
    let ctx = admin_ctx();
    assert!(matches!(
        rt.execute_query("nope.query", &Params::new(), &ctx).unwrap_err(),
        RuntimeError::QueryNotFound(_)
    ));
    assert!(matches!(
        rt.execute_command("nope.cmd", &Params::new(), &ctx).unwrap_err(),
        RuntimeError::CommandNotFound(_)
    ));
}
