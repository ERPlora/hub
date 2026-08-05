//! E2E — brute-force guard on the PIN login (hub#329).
//!
//! The hub lives on the public internet (`{slug}.erplora.com`) and a PIN is 4 digits: 10,000
//! combinations. `identity.rs` itself states the security model depends on device-trust **plus
//! rate-limiting on login**; this is that second half. After N straight failures for an
//! identity, further attempts get 429 — even with the RIGHT pin — until the lock expires; a
//! success before the threshold resets the counter, and the lock never bleeds into other users.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// App in `Session` mode with two PIN users (the lock must be per identity).
async fn fixture() -> axum::Router {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-rate");
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    rt.create_user("Cashier", "2222", "employee", None).await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-pin-rate-{}", std::process::id()));
    let cfg = HubConfig {
        hub_id: "hub-rate".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    app(AppState::with_config(rt, cfg))
}

fn pin_login(name: &str, pin: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/auth/pin")
        .header("content-type", "application/json")
        .body(Body::from(json!({ "name": name, "pin": pin }).to_string()))
        .unwrap()
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

#[tokio::test]
async fn five_straight_failures_lock_the_identity_even_for_the_right_pin() {
    let router = fixture().await;
    for _ in 0..5 {
        let resp = router.clone().oneshot(pin_login("Admin", "0000")).await.unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }
    // The 6th attempt is throttled BEFORE verification: even the right pin gets 429.
    let resp = router.clone().oneshot(pin_login("Admin", "1111")).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::TOO_MANY_REQUESTS,
        "without a lockout, 4 digits are 10,000 free tries"
    );
    let body = body_json(resp).await;
    assert_eq!(body["code"], json!("too_many_attempts"), "{body}");
    assert!(
        body["retry_after_secs"].as_u64().unwrap_or(0) > 0,
        "the client needs to know when to retry: {body}"
    );
}

#[tokio::test]
async fn a_success_before_the_threshold_resets_the_counter() {
    let router = fixture().await;
    for _ in 0..4 {
        let resp = router.clone().oneshot(pin_login("Admin", "0000")).await.unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }
    let resp = router.clone().oneshot(pin_login("Admin", "1111")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "4 failures + the right pin must still log in");
    // Counter is clean again: a fresh failure is a plain 401, not a lock.
    let resp = router.clone().oneshot(pin_login("Admin", "0000")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn the_lock_is_per_identity_not_global() {
    let router = fixture().await;
    for _ in 0..5 {
        let resp = router.clone().oneshot(pin_login("Admin", "0000")).await.unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }
    // Admin is locked; the cashier keeps working (a brute-force on one name must not DoS the shop).
    let resp = router.clone().oneshot(pin_login("Cashier", "2222")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}
