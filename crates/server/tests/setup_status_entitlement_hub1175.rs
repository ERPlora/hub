//! hub#1175 — proves the WIRING, not just the filter: `POST /api/query {"name":
//! "hub.setup.status"}` must not offer a checklist item for a module the entitlement gate is
//! about to refuse the moment its own "Configurar" button is clicked.
//!
//! `crates/runtime/tests/setup_status.rs` already pins the filter itself (`setup_status::status`
//! skipping a module named in `ctx.blocked_modules`, right next to `is_active`). What that unit
//! test cannot see is whether anybody ever POPULATES that field on a real request — the runtime
//! has no view of the SaaS's signed entitlement claims, only `crates/server`'s hybrid revalidation
//! (`crate::entitlement`) does. This test is the seam: `query()` in `crates/server/src/lib.rs`
//! must read `st.entitlement` and stamp `ctx.blocked_modules` BEFORE calling into the runtime, the
//! same way `proxy_entitlement` already builds `GET /api/entitlement`'s `revalidation` block. A
//! filter with nothing to filter on is not a fix — this is what would still be red if that one
//! line in `query()` were missing or reverted.
use std::path::PathBuf;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use cloud_client::{EntitledModule, EntitlementClaims};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// A throwaway module declaring a `setup` block — same shape as `invoice_series` in the reported
/// bug: installed, active, with an item that points somewhere. Kept local (rather than reused from
/// `crates/runtime/tests/setup_status.rs`) because that helper is private to its own test binary.
fn setup_module_fixture(id: &str) -> PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir =
        std::env::temp_dir().join(format!("erplora-hub1175-{}-{}", std::process::id(), nanos));
    std::fs::create_dir_all(dir.join("queries")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        json!({
            "id": id, "name": id, "version": "1.0.0",
            "permissions": [format!("{id}.configure")],
            "queries": {
                format!("{id}.config.get"): {
                    "permission": format!("{id}.configure"),
                    "sql": "queries/config_get.sql"
                }
            },
            "setup": {
                "query": format!("{id}.config.get"),
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": format!("Configure {id}"),
                "route": format!("/m/{id}/list"),
                "permission": format!("{id}.configure")
            }
        })
        .to_string(),
    )
    .unwrap();
    std::fs::write(dir.join("queries/config_get.sql"), "SELECT 1 AS ready").unwrap();
    dir
}

/// App + state, with the given module installed and active (never `fixture_inventory`: it
/// declares no `setup` block, so it cannot exercise this filter). Same shape as
/// `entitlement_test.rs::make_app` — this test only needs a different module on disk.
async fn make_app(module_id: &str) -> (axum::Router, AppState) {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let dir = setup_module_fixture(module_id);
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    let state = AppState::with_config(rt, HubConfig::from_env_with_auth(AuthMode::Dev));
    (app(state.clone()), state)
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

fn setup_status_request() -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/query")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u1")
        .header("x-permissions", "*")
        .body(Body::from(
            json!({ "name": "hub.setup.status", "params": {} }).to_string(),
        ))
        .unwrap()
}

/// Claims of test (`pub` fields; the signature is `verify_entitlement`'s job, not this test's).
fn claims(modules: &[&str]) -> EntitlementClaims {
    EntitlementClaims {
        hub_id: "h1".into(),
        modules: modules
            .iter()
            .map(|id| EntitledModule {
                module_id: (*id).to_string(),
                tier: "premium".into(),
                version: "1.0.0".into(),
            })
            .collect(),
        iat: 1_000,
        exp: 2_000,
        grace_until: i64::MAX,
        paid_grace_until: None,
        plan: None,
        max_devices: 0,
        max_database_size_gb: 0,
    }
}

fn items(doc: &Value) -> &Vec<Value> {
    doc["items"].as_array().expect("`items` is an array")
}

#[tokio::test]
async fn setup_status_omits_the_item_of_a_module_the_entitlement_no_longer_grants_hub1175() {
    let (router, state) = make_app("invoice_series").await;
    // The last successful refresh does NOT include `invoice_series` — exactly what a retired
    // module looks like: revoked/not purchased, same branch `entitlement_blocked` already gates
    // `/api/query`/`/api/command` on.
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims(&["otro_modulo"]), 1_000);

    let resp = router.oneshot(setup_status_request()).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "the checklist query itself is never gated"
    );
    let body = body_json(resp).await;
    let doc = &body["data"][0];
    assert!(
        items(doc)
            .iter()
            .all(|i| i["key"] != "invoice_series.setup"),
        "an entitlement-blocked module must not offer a route the dispatcher will refuse: {doc}"
    );
}

#[tokio::test]
async fn setup_status_keeps_the_item_of_a_module_the_entitlement_still_grants_hub1175() {
    let (router, state) = make_app("invoice_series").await;
    // Last successful refresh DOES include this module → nothing to filter, same as before hub#1175.
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims(&["invoice_series"]), 1_000);

    let resp = router.oneshot(setup_status_request()).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    let doc = &body["data"][0];
    assert!(
        items(doc)
            .iter()
            .any(|i| i["key"] == "invoice_series.setup"),
        "an entitled module must keep its checklist item: {doc}"
    );
}
