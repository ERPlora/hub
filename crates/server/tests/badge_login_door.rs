//! **`POST /api/auth/badge`** — the badge login door (hub#658).
//!
//! The badge is a sibling of the PIN, so the question this file answers is not «does a card sign
//! somebody in» (that is `crates/runtime/tests/employee_badge.rs`) but the one that decides whether
//! adding it was safe:
//!
//! > **Does the new door carry every guard the old one has?**
//!
//! Three of them, and every one has a way of being quietly lost when a second login path is added:
//!
//!  - **device-trust** (§2.9, hub#330) — the hub answers on the public internet, and an EM4100 card
//!    is cloned with a Flipper Zero. A badge door that skipped this would be the rollback of
//!    hub#330 wearing a new name.
//!  - **the brute-force guard** (hub#329) — counted against the CARD, because there is no name to
//!    type here. That is also what stops anybody locking a colleague out by swiping rubbish.
//!  - **it says nothing** — one 401 for «no such card» and for «its owner was deactivated», so the
//!    door cannot be used to enumerate the cards this business has issued.
//!
//! And the property the whole decision rests on, asserted from the outside: **revoking the badge
//! leaves the PIN working**. Losing a card can never lock anybody out — the Lightspeed L-Series
//! (irrevocable card, no documented recovery, discontinued product) is why.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::TestDb;
use erplora_runtime::hub_users::UpdateHubUser;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

type Response = axum::response::Response;

const ANA_BADGE: &str = "0009171456";

async fn body_json(response: Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// A hub with Ana, who carries both a PIN and a card. `device_trust` arms the gate.
///
/// Two runtimes over the SAME schema: the router takes ownership of one, and the test keeps the
/// other to revoke a badge and read a PIN back through the runtime instead of through the door
/// being tested.
async fn fixture(device_trust: bool) -> (axum::Router, TestDb, Runtime) {
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-badge");
    rt.ensure_system_tables().await.unwrap();
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();
    rt.trust_device("till-1", "Counter till").await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-badge-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-badge".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: device_trust,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let served = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-badge");
    served.ensure_system_tables().await.unwrap();
    (app(AppState::with_config(served, cfg)), test_db, rt)
}

async fn post_badge(router: &axum::Router, body: Value) -> Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/badge")
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap()
}

#[tokio::test]
async fn a_swipe_opens_a_session_without_a_name() {
    let (router, _db, _rt) = fixture(false).await;

    let response = post_badge(
        &router,
        json!({ "badge": ANA_BADGE, "device_id": "till-1" }),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], json!(true));
    assert_eq!(body["user"]["name"], json!("Ana"));
    assert!(body["token"].as_str().is_some_and(|t| !t.is_empty()));
}

#[tokio::test]
async fn an_unknown_card_and_a_revoked_one_answer_identically() {
    let (router, _db, rt) = fixture(false).await;
    let unknown = post_badge(&router, json!({ "badge": "4A00B7C219E3" })).await;
    let unknown_status = unknown.status();
    let unknown_body = body_json(unknown).await;

    // Ana's card is revoked. From outside, the two must be indistinguishable: otherwise the door
    // tells a stranger which cards this shop has issued and which of them were cut off.
    let ana = rt.list_hub_users().await.unwrap();
    let ana = ana.iter().find(|u| u.name == "Ana").unwrap();
    rt.update_hub_user(
        &ana.id,
        &UpdateHubUser {
            badge: Some(String::new()),
            ..Default::default()
        }, 0,)
    .await
    .unwrap();
    let revoked = post_badge(&router, json!({ "badge": ANA_BADGE })).await;
    let revoked_status = revoked.status();

    assert_eq!(unknown_status, StatusCode::UNAUTHORIZED);
    assert_eq!(revoked_status, StatusCode::UNAUTHORIZED);
    assert_eq!(body_json(revoked).await, unknown_body);

    // …and the PIN of the person who lost the card still works. That is the whole contract.
    assert!(rt.verify_pin("Ana", "4729").await.unwrap().is_some());
}

#[tokio::test]
async fn the_device_trust_gate_applies_to_a_card_exactly_as_it_does_to_a_pin() {
    let (router, _db, _rt) = fixture(true).await;

    // No device id at all: the shape of the attack, not an oversight (hub#330).
    let unidentified = post_badge(&router, json!({ "badge": ANA_BADGE })).await;
    assert_eq!(unidentified.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(unidentified).await["code"],
        json!("device_unidentified")
    );

    // A device the hub has never seen an account sign in on.
    let untrusted = post_badge(
        &router,
        json!({ "badge": ANA_BADGE, "device_id": "stranger" }),
    )
    .await;
    assert_eq!(untrusted.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(untrusted).await["code"],
        json!("device_untrusted")
    );

    // The trusted till still works, so the gate is refusing the device and not the card.
    let ok = post_badge(
        &router,
        json!({ "badge": ANA_BADGE, "device_id": "till-1" }),
    )
    .await;
    assert_eq!(ok.status(), StatusCode::OK);
}

#[tokio::test]
async fn five_wrong_swipes_lock_the_card_and_only_that_card() {
    let (router, _db, _rt) = fixture(false).await;

    for _ in 0..5 {
        let refused = post_badge(&router, json!({ "badge": "4A00B7C219E3" })).await;
        assert_eq!(refused.status(), StatusCode::UNAUTHORIZED);
    }
    let locked = post_badge(&router, json!({ "badge": "4A00B7C219E3" })).await;
    assert_eq!(locked.status(), StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(body_json(locked).await["code"], json!("too_many_attempts"));

    // Ana's card is untouched: the guard is keyed on the CARD being tried, so nobody locks a
    // colleague out by swiping rubbish at the till.
    let ana = post_badge(&router, json!({ "badge": ANA_BADGE })).await;
    assert_eq!(ana.status(), StatusCode::OK);
}
