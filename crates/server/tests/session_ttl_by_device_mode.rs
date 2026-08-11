//! How long a login lasts depends on **what kind of device it happened on** (plan step 2b,
//! hub#358).
//!
//! `crates/runtime/tests/device_mode.rs` fixes the rule; this file fixes that the login doors
//! actually *use* it. They are two different failures: a runtime that knows a till deserves a short
//! session while `mint_session` keeps stamping thirty days would pass every test over there and
//! ship a till that asks for the PIN once and then never again.
//!
//! Why it belongs to hub#358 at all: the conditional pinpad is only a real gate if the session it
//! opens expires. Otherwise the shared mode buys one PIN prompt a month — a decoration — and the
//! copy the owner reads ("it asks who is at the till each shift") would be false.
//!
//! The direction of the failure is the same as everywhere else in this feature: a device the hub
//! cannot identify gets the **short** session, never the long one.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::device_mode::DeviceMode;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// Router + the database behind it, so the test can read back the session row the login wrote.
/// `till-1` and `laptop-1` are both trusted, as an online login on each would have left them.
async fn fixture() -> (axum::Router, TestDb) {
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-ttl");
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Marta", "2222", "employee", None)
        .await
        .unwrap();
    rt.trust_device("till-1", "Counter till").await.unwrap();
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    rt.set_device_mode("laptop-1", DeviceMode::Personal, &admin_id)
        .await
        .unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-session-ttl-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-ttl".into(),
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
    (app(AppState::with_config(rt, cfg)), test_db)
}

/// Signs `Marta` in by PIN from `device_id` (or from a client that names no device) and returns the
/// session token.
async fn pin_login(router: &axum::Router, device_id: Option<&str>) -> String {
    let mut body = json!({ "name": "Marta", "pin": "2222" });
    if let Some(id) = device_id {
        body["device_id"] = json!(id);
    }
    let response = router
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
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    let json: Value = serde_json::from_slice(&bytes).unwrap();
    json["token"].as_str().unwrap().to_string()
}

/// Seconds from now until that session stops resolving, read from the row the login wrote.
async fn lifetime_secs(test_db: &TestDb, token: &str) -> i64 {
    let db = test_db.adapter().await;
    let mut p = Params::new();
    p.insert("token".into(), json!(token));
    let res = db
        .query(
            "SELECT expires_at FROM hub_session WHERE token = :token",
            &p,
        )
        .await
        .unwrap();
    let raw = res.rows[0]["expires_at"].as_str().unwrap().to_string();
    let expires = chrono::DateTime::parse_from_rfc3339(&raw).expect("expires_at is RFC3339");
    (expires.with_timezone(&chrono::Utc) - chrono::Utc::now()).num_seconds()
}

/// Half a day of slack: the assertions are about which of two orders of magnitude the session
/// landed in (a shift vs a month), not about the exact second the row was stamped.
const SLACK_SECS: i64 = 60 * 60 * 12;

#[tokio::test]
async fn a_login_at_the_till_expires_within_the_shift_it_opened() {
    let (router, test_db) = fixture().await;

    let token = pin_login(&router, Some("till-1")).await;
    let lifetime = lifetime_secs(&test_db, &token).await;

    assert!(
        lifetime <= DeviceMode::Shared.session_ttl_secs(),
        "a shared till got a {lifetime}s session, longer than the shared window"
    );
    assert!(
        lifetime > DeviceMode::Shared.session_ttl_secs() - SLACK_SECS,
        "a shared till got {lifetime}s, far shorter than the shared window it should have"
    );
}

#[tokio::test]
async fn a_login_on_the_personal_laptop_is_the_one_that_stays_signed_in() {
    let (router, test_db) = fixture().await;

    let token = pin_login(&router, Some("laptop-1")).await;
    let lifetime = lifetime_secs(&test_db, &token).await;

    assert!(
        lifetime > DeviceMode::Shared.session_ttl_secs() + SLACK_SECS,
        "the device its owner marked personal got only {lifetime}s: «remember me» has to mean something"
    );
    assert!(
        lifetime <= DeviceMode::Personal.session_ttl_secs(),
        "a session cannot outlive the long window either ({lifetime}s)"
    );
}

#[tokio::test]
async fn a_client_that_names_no_device_gets_the_short_session() {
    let (router, test_db) = fixture().await;

    // Not identifying yourself is the shape of the attack, not a personal laptop: it has to land on
    // the strict side, the same way an unknown id resolves to `shared`.
    let token = pin_login(&router, None).await;
    let lifetime = lifetime_secs(&test_db, &token).await;

    assert!(
        lifetime <= DeviceMode::Shared.session_ttl_secs(),
        "an unidentified client got a {lifetime}s session: the fallback has to be the short one"
    );
}

#[tokio::test]
async fn taking_the_laptop_back_behind_the_counter_shortens_the_next_login() {
    let (router, test_db) = fixture().await;

    let long = lifetime_secs(&test_db, &pin_login(&router, Some("laptop-1")).await).await;

    // The admin changes their mind (or the laptop moves to the counter). The decision is not a
    // one-way door: the very next login is back to the short session.
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-ttl");
    rt.set_device_mode("laptop-1", DeviceMode::Shared, "hub_user:admin")
        .await
        .unwrap();

    let short = lifetime_secs(&test_db, &pin_login(&router, Some("laptop-1")).await).await;

    assert!(
        short < long,
        "the mode is read at every login, not cached from the first one ({short}s vs {long}s)"
    );
    assert!(short <= DeviceMode::Shared.session_ttl_secs());
}
