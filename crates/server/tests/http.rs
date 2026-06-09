//! Tests de integración del server por HTTP (sin red): `tower::ServiceExt::oneshot`.
use std::path::PathBuf;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::SqliteAdapter;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

fn fixture() -> PathBuf {
    // Reusa el fixture del runtime (módulo inventory completo).
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_inventory")
}

async fn make_app() -> axum::Router {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.unwrap();
    app(AppState::new(rt))
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

fn post(uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u1")
        .header("x-permissions", "*")
        .body(Body::from(body.to_string()))
        .unwrap()
}

#[tokio::test]
async fn healthz_ok() {
    let resp = make_app().await
        .oneshot(Request::builder().uri("/healthz").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn navigation_lists_module_menu() {
    let resp = make_app().await
        .oneshot(Request::builder().uri("/api/navigation").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(true));
    assert_eq!(j["data"][0]["component"], json!("erp-inventory-products"));
}

#[tokio::test]
async fn command_then_query_roundtrip() {
    let app = make_app().await;

    let create = app
        .clone()
        .oneshot(post(
            "/api/command",
            json!({ "name": "inventory.products.create",
                    "payload": { "name": "Café", "sku": "CAF", "price": 4.5, "stock": 10 } }),
        ))
        .await
        .unwrap();
    assert_eq!(create.status(), StatusCode::OK);
    assert_eq!(body_json(create).await["ok"], json!(true));

    let list = app
        .oneshot(post("/api/query", json!({ "name": "inventory.products.list" })))
        .await
        .unwrap();
    assert_eq!(list.status(), StatusCode::OK);
    let j = body_json(list).await;
    assert_eq!(j["data"].as_array().unwrap().len(), 1);
    assert_eq!(j["data"][0]["name"], json!("Café"));
}

#[tokio::test]
async fn permission_denied_is_403() {
    let req = Request::builder()
        .method("POST")
        .uri("/api/command")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u2")
        .header("x-permissions", "inventory.products.read") // sin create
        .body(Body::from(
            json!({ "name": "inventory.products.create",
                    "payload": { "name": "X", "sku": "X", "price": 1, "stock": 1 } })
            .to_string(),
        ))
        .unwrap();
    let resp = make_app().await.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    assert_eq!(body_json(resp).await["error"]["code"], json!("permission_denied"));
}

#[tokio::test]
async fn unknown_query_is_404() {
    let resp = make_app().await.oneshot(post("/api/query", json!({ "name": "nope.q" }))).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn hub_context_returns_configured_hub_id() {
    use erplora_server::HubConfig;
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let rt = Runtime::new(Box::new(db));
    let cfg = HubConfig {
        hub_id: "hub-xyz".into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache: std::env::temp_dir().join("erplora-test-cache"),
        auth_mode: erplora_server::AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: None,
    };
    let app = app(AppState::with_config(rt, cfg));
    let resp = app
        .oneshot(Request::builder().uri("/api/hub/context").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["hub_id"], json!("hub-xyz"));
    assert_eq!(j["user"], Value::Null);
}

#[tokio::test]
async fn request_install_without_bearer_is_401() {
    // Sin `Authorization: Bearer`, el flujo de instalación se rechaza antes de tocar el Cloud.
    let req = Request::builder()
        .method("POST")
        .uri("/api/modules/request-install")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .body(Body::from(json!({ "module_id": "inventory", "version": "1.0.0" }).to_string()))
        .unwrap();
    let resp = make_app().await.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(body_json(resp).await["ok"], json!(false));
}

#[tokio::test]
async fn assistant_stream_without_bearer_is_401() {
    let req = Request::builder()
        .method("POST")
        .uri("/api/assistant/chat/stream")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .body(Body::from(json!({ "messages": [{ "role": "user", "content": "hi" }] }).to_string()))
        .unwrap();
    let resp = make_app().await.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}
