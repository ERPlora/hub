//! hub#2499 — changing one's own PIN (`POST /api/auth/set-pin`, «Mi perfil») was an oracle with no
//! brake. PINs are unique among active people (hub#355), so the door has to say «that one is taken»
//! — and it said it to anybody with a session, as many times as they liked. A cashier typing
//! numbers one after another learnt which PINs belong to somebody, and the pinpad grid hands out the
//! names to try them against: the manager's or the owner's till session was a few minutes away.
//!
//! The door now spends a per-person budget, the same five tries per five minutes the pinpad gives a
//! name ([`erplora_server::login_throttle`]). **Every** try spends it, the accepted ones too: a free
//! number is stored as the prober's own PIN and they keep going, so counting only refusals would
//! still give them unlimited probes and a taken PIN every refusal. What this file locks down:
//!
//!  - once the budget is spent the door answers `429 too_many_attempts` BEFORE looking at the
//!    digits, so a taken PIN no longer says `pin_in_use`;
//!  - refusals (`pin_current_mismatch`, `pin_in_use`) spend the same budget;
//!  - the lock is the prober's: a colleague still changes their own PIN;
//!  - signing in again does not lift it (the key is the person, not the pinpad's name counter that
//!    a successful login clears).
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::login_throttle::MAX_FAILURES;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-pin-oracle";
const PROBER: &str = "Nora Vega";
const PROBER_PIN: &str = "1379";
const VICTIM_PIN: &str = "4917";
/// Free, non-guessable PINs the prober rotates through (none repeats a digit run nor matches
/// [`VICTIM_PIN`]). One more than the budget, so a test can always ask for one past it.
const FREE_PINS: [&str; 6] = ["8246", "3058", "6193", "7402", "5817", "2964"];

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// Router + the prober's session + the victim's session, both employees of the same hub.
async fn fixture() -> (axum::Router, String, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let prober = rt
        .create_user(PROBER, PROBER_PIN, "employee", None)
        .await
        .unwrap();
    let victim = rt
        .create_user("Marta Ruiz", VICTIM_PIN, "admin", None)
        .await
        .unwrap();
    let prober_session = rt.create_session(&prober, 3600, None).await.unwrap();
    let victim_session = rt.create_session(&victim, 3600, None).await.unwrap();
    let media = std::env::temp_dir().join(format!(
        "erplora-pin-oracle-{}-{}",
        std::process::id(),
        prober
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB.into(),
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
    (
        app(AppState::with_config(rt, cfg)),
        prober_session,
        victim_session,
    )
}

async fn set_pin(
    router: &axum::Router,
    session: &str,
    pin: &str,
    current_pin: &str,
) -> axum::response::Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/set-pin")
                .header("content-type", "application/json")
                .header("x-hub-session", session)
                .body(Body::from(
                    json!({ "pin": pin, "current_pin": current_pin }).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap()
}

async fn pin_login(router: &axum::Router, name: &str, pin: &str) -> axum::response::Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/pin")
                .header("content-type", "application/json")
                .body(Body::from(json!({ "name": name, "pin": pin }).to_string()))
                .unwrap(),
        )
        .await
        .unwrap()
}

/// Rotates the prober's PIN `n` times through [`FREE_PINS`], each accepted; returns the PIN the
/// prober holds afterwards.
async fn rotate(router: &axum::Router, session: &str, n: usize) -> &'static str {
    let mut current = PROBER_PIN;
    for next in FREE_PINS.iter().take(n) {
        let response = set_pin(router, session, next, current).await;
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "rotation to {next} inside the budget is accepted"
        );
        current = next;
    }
    current
}

async fn assert_locked(response: axum::response::Response) {
    assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
    let body = body_json(response).await;
    assert_eq!(body["code"], "too_many_attempts", "body: {body}");
    assert!(
        body["retry_after_secs"].as_u64().is_some_and(|s| s > 0),
        "the lock names its wait: {body}"
    );
}

/// The symptom of the issue: before, the probe past the budget still answered `pin_in_use`.
#[tokio::test]
async fn a_taken_pin_is_not_confirmed_once_the_budget_is_spent() {
    let (router, prober, _) = fixture().await;
    // Inside the budget the door does its job, refusal included: the PIN is unique.
    let held = rotate(&router, &prober, MAX_FAILURES as usize - 1).await;
    let probe = set_pin(&router, &prober, VICTIM_PIN, held).await;
    assert_eq!(probe.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(probe).await["error"]["code"],
        "hub.users.pin_in_use"
    );

    // Budget spent: the same probe no longer says whose it is.
    assert_locked(set_pin(&router, &prober, VICTIM_PIN, held).await).await;
}

/// Accepted changes spend the budget too: a free number is stored and the prober keeps going, so
/// a brake that counted only refusals would let them probe for ever.
#[tokio::test]
async fn accepted_changes_spend_the_budget_too() {
    let (router, prober, _) = fixture().await;
    let held = rotate(&router, &prober, MAX_FAILURES as usize).await;
    assert_locked(set_pin(&router, &prober, VICTIM_PIN, held).await).await;
}

/// Guessing the current PIN from an unattended session is the other half of the same door.
#[tokio::test]
async fn refusals_spend_the_same_budget() {
    let (router, prober, _) = fixture().await;
    for _ in 0..MAX_FAILURES {
        let wrong = set_pin(&router, &prober, FREE_PINS[0], "0007").await;
        assert_eq!(wrong.status(), StatusCode::CONFLICT);
        assert_eq!(
            body_json(wrong).await["error"]["code"],
            "hub.users.pin_current_mismatch"
        );
    }
    // Even the right current PIN is turned away now, before it is checked.
    assert_locked(set_pin(&router, &prober, FREE_PINS[0], PROBER_PIN).await).await;
}

#[tokio::test]
async fn the_lock_is_the_probers_alone() {
    let (router, prober, victim) = fixture().await;
    let held = rotate(&router, &prober, MAX_FAILURES as usize).await;
    assert_locked(set_pin(&router, &prober, FREE_PINS[5], held).await).await;

    let own = set_pin(&router, &victim, FREE_PINS[5], VICTIM_PIN).await;
    assert_eq!(
        own.status(),
        StatusCode::OK,
        "a colleague still changes their own PIN"
    );
}

/// A successful pinpad login clears the NAME's counter (hub#329). If the change door shared that
/// key, the prober would sign in again with their own PIN and start a fresh budget.
#[tokio::test]
async fn signing_in_again_does_not_lift_the_lock() {
    let (router, prober, _) = fixture().await;
    let held = rotate(&router, &prober, MAX_FAILURES as usize).await;
    assert_locked(set_pin(&router, &prober, VICTIM_PIN, held).await).await;

    let login = pin_login(&router, PROBER, held).await;
    assert_eq!(
        login.status(),
        StatusCode::OK,
        "the prober can still sign in"
    );
    let fresh = body_json(login).await["token"]
        .as_str()
        .expect("a session token")
        .to_string();
    assert_locked(set_pin(&router, &fresh, VICTIM_PIN, held).await).await;
}
