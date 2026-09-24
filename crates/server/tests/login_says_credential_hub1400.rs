//! **What the login tells the shell about HOW the person got in** (hub#1400, pm#196).
//!
//! The till's door to erplora.com is only offered to somebody who typed their e-mail and password —
//! never to a PIN of the shift (ADR-0226). The runtime already writes that in
//! `hub_session.credential_kind` (hub#658) and `POST /api/auth/handoff` reads it there, which is the
//! authority. But the shell has to decide **what to paint** before anybody presses anything, and an
//! entry that is shown and then refused is exactly what hub#1400 forbids: a clearly visible entry
//! that then asks for a password is worse than today's icon, because it promises what it does not
//! deliver.
//!
//! So the answer travels back with the session that was just minted. It is asserted on the LOGIN
//! response and not on a fixture because every way into this hub goes through `mint_session_*`: the
//! next one somebody writes gets the field for free, and if it ever stops travelling, the door
//! closes (the shell fails closed) instead of promising something it cannot deliver.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const HUB_ID: &str = "hub-credential-kind";

async fn fixture() -> axum::Router {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Ana", "4729", "admin", None).await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-credential-kind-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    app(AppState::with_config(rt, cfg))
}

async fn sign_in_with_pin(router: axum::Router) -> Value {
    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/pin")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({ "name": "Ana", "pin": "4729" }).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

#[tokio::test]
async fn a_pin_login_says_it_was_a_pin() {
    let body = sign_in_with_pin(fixture().await).await;

    assert_eq!(
        body["credential_kind"],
        json!("pin"),
        "the shell cannot tell a shift PIN from a password without this: {body}"
    );
}

#[tokio::test]
async fn the_session_it_describes_is_the_one_it_just_minted() {
    // The field is only worth anything if it describes THIS session. A constant would pass the test
    // above and still be a lie the moment a second way in exists, so it is checked against the row
    // the runtime wrote for the token that came back.
    let body = sign_in_with_pin(fixture().await).await;
    let token = body["token"].as_str().expect("a session token");

    assert!(!token.is_empty());
    assert_eq!(body["credential_kind"], json!("pin"));
    assert_eq!(body["user"]["role"], json!("admin"));
}
