//! Device-trust has no bypass: omitting `device_id` must not skip the gate (hub#330).
//!
//! With `HUB_DEVICE_TRUST=enforce` the PIN login is meant to be refused on a device that never
//! did an online (cloud) login — §2.9. The check used to live inside an `if let Some(device_id)`
//! with **no `else`**, so a client that simply left `device_id` out walked straight past it. The
//! hub is on the public internet (`{slug}.erplora.com`), so "the client forgot to identify its
//! device" is not a benign case: it is the shape of the bypass.
//!
//! Contract fixed here:
//!   - enforce ON  + no `device_id`      → refused (`device_unidentified`)
//!   - enforce ON  + untrusted device    → refused (`device_untrusted`)
//!   - enforce ON  + trusted device      → allowed
//!   - enforce OFF + no `device_id`      → allowed (opt-in gate, unchanged behaviour)
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// App in `Session` mode with one admin (PIN 1111), the given device-trust setting, and
/// optionally a device already marked as trusted (as an online cloud login would leave it).
async fn fixture(enforce: bool, trusted_device: Option<&str>) -> axum::Router {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-dt");
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    if let Some(device_id) = trusted_device {
        rt.trust_device(device_id, "Admin").await.unwrap();
    }
    let temp = std::env::temp_dir().join(format!("erplora-device-trust-{}", std::process::id()));
    let cfg = HubConfig {
        hub_id: "hub-dt".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: enforce,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: None,
    };
    app(AppState::with_config(rt, cfg))
}

async fn post_pin(app_: &axum::Router, body: Value) -> (StatusCode, Value) {
    let res = app_
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/pin")
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = res.status();
    let bytes = res.into_body().collect().await.unwrap().to_bytes();
    let json: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, json)
}

#[tokio::test]
async fn enforce_on_without_device_id_is_refused() {
    let app_ = fixture(true, None).await;
    let (status, body) = post_pin(&app_, json!({ "name": "Admin", "pin": "1111" })).await;
    assert_eq!(
        status,
        StatusCode::FORBIDDEN,
        "omitting device_id must not skip the gate: {body}"
    );
    assert_eq!(body["code"], json!("device_unidentified"), "{body}");
}

#[tokio::test]
async fn enforce_on_with_an_untrusted_device_is_refused() {
    let app_ = fixture(true, None).await;
    let (status, body) =
        post_pin(&app_, json!({ "name": "Admin", "pin": "1111", "device_id": "tablet-1" })).await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["code"], json!("device_untrusted"), "{body}");
}

#[tokio::test]
async fn enforce_on_with_a_trusted_device_is_allowed() {
    let app_ = fixture(true, Some("tablet-ok")).await;
    let (status, body) =
        post_pin(&app_, json!({ "name": "Admin", "pin": "1111", "device_id": "tablet-ok" })).await;
    assert_eq!(status, StatusCode::OK, "a trusted device still logs in: {body}");
    assert_eq!(body["ok"], json!(true), "{body}");
}

#[tokio::test]
async fn enforce_off_without_device_id_still_works() {
    let app_ = fixture(false, None).await;
    let (status, body) = post_pin(&app_, json!({ "name": "Admin", "pin": "1111" })).await;
    assert_eq!(status, StatusCode::OK, "the gate is opt-in: {body}");
    assert_eq!(body["ok"], json!(true), "{body}");
}
