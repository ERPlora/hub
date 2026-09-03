//! HTTP contract of «Mi perfil» → cambiar mi PIN (hub#1430): before this, the ONLY door that could
//! rotate an employee's own PIN was Personal → their row → Edit — the admin screen, gated by the
//! `employees` permission, meant for administering somebody ELSE. This reuses the self-service door
//! that already existed for the alta-tras-login-cloud flow (`POST /api/auth/set-pin`), so the
//! contract this file locks down is what CHANGED about that door, not the door itself:
//!
//!  - `GET /api/profile` now says whether the caller has a PIN today (`has_pin`), so the screen can
//!    tell "change it" from "set one for the first time" apart.
//!  - Once a PIN exists, rotating it needs the CURRENT one — same rule as changing any other
//!    password, and the guard against a stranger locking the real owner out from an unlocked
//!    session. A missing or wrong `current_pin` is refused (409, stable code), the stored PIN is
//!    left untouched, and the right one rotates it.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// Router + a session token for `pin` ("" = cloud-only, no PIN yet).
async fn fixture(pin: &str) -> (axum::Router, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-pin-rotate");
    rt.ensure_system_tables().await.unwrap();
    let user_id = rt
        .create_user("Nora Vega", pin, "employee", None)
        .await
        .unwrap();
    let token = rt.create_session(&user_id, 3600, None).await.unwrap();
    let media = std::env::temp_dir().join(format!(
        "erplora-pin-rotate-{}-{}",
        std::process::id(),
        user_id
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-pin-rotate".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: media.join("modules"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: media,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    (app(AppState::with_config(rt, cfg)), token)
}

async fn get_profile(router: &axum::Router, session: &str) -> Value {
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/profile")
                .header("x-hub-session", session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    body_json(response).await
}

async fn set_pin(
    router: &axum::Router,
    session: &str,
    pin: &str,
    current_pin: Option<&str>,
) -> axum::response::Response {
    let mut body = json!({ "pin": pin });
    if let Some(current) = current_pin {
        body["current_pin"] = json!(current);
    }
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/set-pin")
                .header("content-type", "application/json")
                .header("x-hub-session", session)
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap()
}

#[tokio::test]
async fn profile_names_whether_the_caller_has_a_pin_today() {
    let (router, session) = fixture("").await;
    let profile = get_profile(&router, &session).await;
    assert_eq!(profile["has_pin"], false);

    let response = set_pin(&router, &session, "4170", None).await;
    assert_eq!(response.status(), StatusCode::OK);
    let profile = get_profile(&router, &session).await;
    assert_eq!(profile["has_pin"], true);
}

#[tokio::test]
async fn a_first_pin_needs_no_confirmation() {
    let (router, session) = fixture("").await;
    let response = set_pin(&router, &session, "8520", None).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(body_json(response).await["ok"], true);
}

#[tokio::test]
async fn rotating_an_existing_pin_is_refused_without_the_current_one() {
    // "1379"/"8246": deliberately NOT guessable (no repeated digit, no straight run), so the 409
    // this test asserts can only come from the mismatch it is testing — not from `clean_pin`
    // refusing the new PIN's shape for an unrelated reason.
    let (router, session) = fixture("1379").await;

    let missing = set_pin(&router, &session, "8246", None).await;
    assert_eq!(missing.status(), StatusCode::CONFLICT);
    let body = body_json(missing).await;
    assert_eq!(body["error"]["code"], "hub.users.pin_current_mismatch");

    let wrong = set_pin(&router, &session, "8246", Some("0007")).await;
    assert_eq!(wrong.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(wrong).await["error"]["code"],
        "hub.users.pin_current_mismatch"
    );
}

#[tokio::test]
async fn rotating_an_existing_pin_succeeds_with_the_current_one() {
    let (router, session) = fixture("1379").await;
    let response = set_pin(&router, &session, "8246", Some("1379")).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(body_json(response).await["ok"], true);
}
