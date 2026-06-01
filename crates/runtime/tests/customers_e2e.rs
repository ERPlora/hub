//! E2E real del módulo `customers` (portado de old_modules/m_customers v2.2.10):
//! instala el módulo real (con dist/handler.wasm compilado) y ejercita CRUD
//! declarativo + handlers WASM batch (bulk_create, set_groups/set_tags M2M) +
//! el listener de sale.completed (record_purchase con transición de lifecycle).
use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../modules/customers")
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}
fn wasm_present() -> bool {
    dir().join("dist/handler.wasm").exists()
}
fn fresh() -> Runtime {
    let db = SqliteAdapter::open_in_memory().unwrap();
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&dir()).expect("instalar customers");
    rt
}

fn new_customer(rt: &Runtime, ctx: &RequestContext, name: &str, stage: &str) -> String {
    rt.execute_command(
        "customers.create",
        &params(json!({
            "name": name, "email": "", "phone": "", "tax_id": "", "address": "", "city": "",
            "postal_code": "", "country": "", "avatar": "", "notes": "", "lifecycle_stage": stage,
            "source": "walk_in", "company_name": "", "birthday": null, "anniversary": null,
            "preferred_channel": "none", "marketing_consent": 0, "consent_date": null
        })),
        ctx,
    )
    .unwrap();
    rt.execute_query("customers.list", &Params::new(), ctx).unwrap()
        .last().unwrap()["id"].as_str().unwrap().to_string()
}

#[test]
fn install_registers_capabilities() {
    let rt = fresh();
    let reg = rt.registry();
    assert!(reg.is_installed("customers"));
    assert!(reg.get_query("customers.list").is_some());
    assert!(reg.get_command("customers.create").is_some());
    assert!(reg.get_command("customers.bulk_create").is_some());
    assert!(reg.get_command("customers.set_groups").is_some());
    // sale.completed → record_purchase (CRM stats + lifecycle).
    assert_eq!(reg.listeners_for("sale.completed"), ["customers.record_purchase"]);
}

#[test]
fn customer_crud_and_stats() {
    let rt = fresh();
    let ctx = admin();
    new_customer(&rt, &ctx, "Bar Manolo", "lead");

    let rows = rt.execute_query("customers.list", &Params::new(), &ctx).unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["name"], json!("Bar Manolo"));
    assert_eq!(rows[0]["lifecycle_stage"], json!("lead"));

    let stats = rt.execute_query("customers.stats", &Params::new(), &ctx).unwrap();
    assert_eq!(stats[0]["total"], json!(1));
    assert_eq!(stats[0]["active"], json!(1));

    // scope hub_id.
    let other = RequestContext::new("h2", "u9", ["*".to_string()]);
    assert_eq!(rt.execute_query("customers.list", &Params::new(), &other).unwrap().len(), 0);
}

#[test]
fn record_purchase_transitions_lifecycle() {
    let rt = fresh();
    let ctx = admin();
    let id = new_customer(&rt, &ctx, "Lead X", "lead");

    // primera compra: lead → first_purchase.
    rt.execute_command("customers.record_purchase",
        &params(json!({ "customer_id": id, "total": 50.0 })), &ctx).unwrap();
    let c = rt.execute_query("customers.get", &params(json!({"customer_id": id})), &ctx).unwrap();
    assert_eq!(c[0]["lifecycle_stage"], json!("first_purchase"));
    assert_eq!(c[0]["total_purchases"], json!(1));
    // SQLite NUMERIC: 50.0 sin fracción se almacena como entero → comparamos numéricamente.
    assert_eq!(c[0]["total_spent"].as_f64().unwrap(), 50.0);

    // segunda compra: first_purchase → active.
    rt.execute_command("customers.record_purchase",
        &params(json!({ "customer_id": id, "total": 30.0 })), &ctx).unwrap();
    let c2 = rt.execute_query("customers.get", &params(json!({"customer_id": id})), &ctx).unwrap();
    assert_eq!(c2[0]["lifecycle_stage"], json!("active"));
    assert_eq!(c2[0]["total_purchases"], json!(2));
    assert_eq!(c2[0]["total_spent"].as_f64().unwrap(), 80.0);
}

#[test]
fn bulk_create_wasm() {
    if !wasm_present() { eprintln!("SKIP: handler.wasm ausente"); return; }
    let rt = fresh();
    let ctx = admin();
    let res = rt.execute_command("customers.bulk_create", &params(json!({
        "items": [
            { "name": "C1", "email": "c1@x.es", "lifecycle_stage": "customer" },
            { "name": "C2", "phone": "611" },
            { "name": "C3" }
        ]
    })), &ctx).expect("bulk_create WASM");
    assert_eq!(res["operations"], json!(3));
    let rows = rt.execute_query("customers.list", &Params::new(), &ctx).unwrap();
    assert_eq!(rows.len(), 3);
    // "customer" → "active".
    let c1 = rows.iter().find(|r| r["name"] == json!("C1")).unwrap();
    assert_eq!(c1["lifecycle_stage"], json!("active"));
}

#[test]
fn set_groups_wasm_replaces_membership() {
    if !wasm_present() { eprintln!("SKIP: handler.wasm ausente"); return; }
    let rt = fresh();
    let ctx = admin();
    let cid = new_customer(&rt, &ctx, "C", "active");
    for n in ["VIP", "Mayorista"] {
        rt.execute_command("customers.groups.create", &params(json!({
            "name": n, "description": "", "discount_percent": 0, "color": "primary", "sort_order": 0
        })), &ctx).unwrap();
    }
    let groups = rt.execute_query("customers.groups.list", &Params::new(), &ctx).unwrap();
    let g0 = groups[0]["id"].as_str().unwrap().to_string();
    let g1 = groups[1]["id"].as_str().unwrap().to_string();

    let res = rt.execute_command("customers.set_groups",
        &params(json!({ "customer_id": cid, "ids": [g0, g1] })), &ctx).expect("set_groups WASM");
    assert_eq!(res["operations"], json!(3)); // clear + 2 add
    let after = rt.execute_query("customers.groups.list", &Params::new(), &ctx).unwrap();
    assert!(after.iter().all(|g| g["customer_count"] == json!(1)), "ambos grupos con 1 cliente");
}

#[test]
fn note_and_activity_timeline() {
    let rt = fresh();
    let ctx = admin();
    let cid = new_customer(&rt, &ctx, "C", "active");
    rt.execute_command("customers.activity.add", &params(json!({
        "customer_id": cid, "activity_type": "note", "title": "Llamada", "description": "OK",
        "extra_metadata": "{}", "related_object_id": null, "related_object_type": ""
    })), &ctx).unwrap();
    let acts = rt.execute_query("customers.activities", &params(json!({"customer_id": cid})), &ctx).unwrap();
    assert_eq!(acts.len(), 1);
    assert_eq!(acts[0]["activity_type"], json!("note"));
}
