//! hub#2499 — changing one's own PIN (`POST /api/auth/set-pin`, «Mi perfil») was an oracle with no
//! brake. PINs are unique among active people (hub#355), so the door has to say «that one is taken»
//! — and it said it to anybody with a session, as many times as they liked. A cashier typing
//! numbers one after another learnt which PINs belong to somebody, and the pinpad grid hands out the
//! names to try them against: the manager's or the owner's till session was a few minutes away.
//!
//! The door now spends a per-person budget, shared with the PIN doors of Empleados (hub#2518) and
//! sized for setting up a whole staff ([`PIN_CHANGE_MAX_ATTEMPTS`] per hour, hub#2564, fewer tries
//! a day than the five every five minutes it started with). **Every** try spends it, the accepted ones too: a free
//! number is stored as the prober's own PIN and they keep going, so counting only refusals would
//! still give them unlimited probes and a taken PIN every refusal. What this file locks down:
//!
//!  - once the budget is spent the door answers `429 too_many_attempts` BEFORE looking at the
//!    digits, so a taken PIN no longer says `pin_in_use`;
//!  - refusals (`pin_current_mismatch`, `pin_in_use`) spend the same budget;
//!  - the lock is the prober's: a colleague still changes their own PIN;
//!  - signing in again does not lift it (the key is the person, not the pinpad's name counter that
//!    a successful login clears);
//!  - the budget is this door's alone: the pinpad counts against whatever NAME the caller types,
//!    so a name spelt like this door's key neither locks somebody's PIN change nor refills it.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::login_throttle::{MAX_FAILURES, PIN_CHANGE_MAX_ATTEMPTS};
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-pin-oracle";
const PROBER: &str = "Nora Vega";
const PROBER_PIN: &str = "1379";
const VICTIM: &str = "Marta Ruiz";
const VICTIM_PIN: &str = "4917";
const ACCOMPLICE_PIN: &str = "9053";
/// The budget of tries, as a count.
const BUDGET: usize = PIN_CHANGE_MAX_ATTEMPTS as usize;

/// Free, non-guessable PINs the prober rotates through (steps of 41 from 2000: none is a repeated
/// digit or a run, nor the fixture's PINs). One more than the budget, so a test can always ask for
/// one past it.
fn free_pin(i: usize) -> String {
    format!("{:04}", 2000 + 41 * i)
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// Router + the prober's session + the victim's session, both employees of the same hub.
async fn fixture() -> (axum::Router, String, String) {
    fixture_with(|_| None).await
}

/// [`fixture`] plus, when `accomplice` names one, a third person called whatever it returns for
/// the prober's id, holding [`ACCOMPLICE_PIN`].
async fn fixture_with(
    accomplice: impl Fn(&str) -> Option<String>,
) -> (axum::Router, String, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let prober = rt
        .create_user(PROBER, PROBER_PIN, "employee", None)
        .await
        .unwrap();
    if let Some(name) = accomplice(&prober) {
        rt.create_user(&name, ACCOMPLICE_PIN, "employee", None)
            .await
            .unwrap();
    }
    let victim = rt
        .create_user(VICTIM, VICTIM_PIN, "admin", None)
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

/// A person's id as the pinpad grid hands it out — to anybody, no session needed.
async fn grid_id(router: &axum::Router, name: &str) -> String {
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/hub/context")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    body["pin_users"]
        .as_array()
        .and_then(|users| users.iter().find(|u| u["name"] == name))
        .and_then(|u| u["id"].as_str())
        .unwrap_or_else(|| panic!("{name} is on the grid: {body}"))
        .to_string()
}

/// Rotates the prober's PIN `n` times through [`free_pin`], each accepted; returns the PIN the
/// prober holds afterwards.
async fn rotate(router: &axum::Router, session: &str, n: usize) -> String {
    let mut current = PROBER_PIN.to_string();
    for next in (0..n).map(free_pin) {
        let response = set_pin(router, session, &next, &current).await;
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
    let held = rotate(&router, &prober, BUDGET - 1).await;
    let probe = set_pin(&router, &prober, VICTIM_PIN, &held).await;
    assert_eq!(probe.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(probe).await["error"]["code"],
        "hub.users.pin_in_use"
    );

    // Budget spent: the same probe no longer says whose it is.
    assert_locked(set_pin(&router, &prober, VICTIM_PIN, &held).await).await;
}

/// Accepted changes spend the budget too: a free number is stored and the prober keeps going, so
/// a brake that counted only refusals would let them probe for ever.
#[tokio::test]
async fn accepted_changes_spend_the_budget_too() {
    let (router, prober, _) = fixture().await;
    let held = rotate(&router, &prober, BUDGET).await;
    assert_locked(set_pin(&router, &prober, VICTIM_PIN, &held).await).await;
}

/// Guessing the current PIN from an unattended session is the other half of the same door.
#[tokio::test]
async fn refusals_spend_the_same_budget() {
    let (router, prober, _) = fixture().await;
    for _ in 0..BUDGET {
        let wrong = set_pin(&router, &prober, &free_pin(0), "0007").await;
        assert_eq!(wrong.status(), StatusCode::CONFLICT);
        assert_eq!(
            body_json(wrong).await["error"]["code"],
            "hub.users.pin_current_mismatch"
        );
    }
    // Even the right current PIN is turned away now, before it is checked.
    assert_locked(set_pin(&router, &prober, &free_pin(0), PROBER_PIN).await).await;
}

#[tokio::test]
async fn the_lock_is_the_probers_alone() {
    let (router, prober, victim) = fixture().await;
    let held = rotate(&router, &prober, BUDGET).await;
    assert_locked(set_pin(&router, &prober, &free_pin(BUDGET), &held).await).await;

    let own = set_pin(&router, &victim, &free_pin(BUDGET), VICTIM_PIN).await;
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
    let held = rotate(&router, &prober, BUDGET).await;
    assert_locked(set_pin(&router, &prober, VICTIM_PIN, &held).await).await;

    let login = pin_login(&router, PROBER, &held).await;
    assert_eq!(
        login.status(),
        StatusCode::OK,
        "the prober can still sign in"
    );
    let fresh = body_json(login).await["token"]
        .as_str()
        .expect("a session token")
        .to_string();
    assert_locked(set_pin(&router, &fresh, VICTIM_PIN, &held).await).await;
}

/// How this door's key could be spelt as a NAME at the pinpad: the bare id, or the id behind the
/// prefix the first cut of the fix used. Neither may reach the budget.
fn spellings(id: &str) -> [String; 2] {
    [id.to_string(), format!("pin_change:{id}")]
}

/// The pinpad counts wrong PINs against whatever NAME the caller types, and the grid hands out
/// everybody's id without a session. Were this door's key a name in the pinpad's map, five wrong
/// PINs typed under it would lock that person out of changing their PIN — again every five
/// minutes, for as long as somebody kept typing, and never enough to trip the per-address guard.
#[tokio::test]
async fn wrong_pins_at_the_pinpad_do_not_lock_somebodys_pin_change() {
    let (router, _, victim) = fixture().await;
    for name in spellings(&grid_id(&router, VICTIM).await) {
        for _ in 0..MAX_FAILURES {
            let guess = pin_login(&router, &name, "0007").await;
            assert_eq!(guess.status(), StatusCode::UNAUTHORIZED);
        }
    }

    let own = set_pin(&router, &victim, &free_pin(0), VICTIM_PIN).await;
    assert_eq!(
        own.status(),
        StatusCode::OK,
        "nobody was probing this door: {}",
        body_json(own).await
    );
}

/// The other direction of the same collision: a successful pinpad login clears the counter of the
/// NAME typed. With somebody on the staff list called like the prober's key, signing them in would
/// hand the prober a fresh budget whenever it ran low.
#[tokio::test]
async fn a_sign_in_under_a_name_spelt_like_the_key_does_not_refill_the_budget() {
    for spelling in 0..2 {
        let (router, prober, _) = fixture_with(|id| Some(spellings(id)[spelling].clone())).await;
        let name = spellings(&grid_id(&router, PROBER).await)[spelling].clone();
        let held = rotate(&router, &prober, BUDGET - 1).await;

        let login = pin_login(&router, &name, ACCOMPLICE_PIN).await;
        assert_eq!(login.status(), StatusCode::OK, "{name} signs in");

        // The last try is still the last: it is answered, and the one after it is not.
        let last = set_pin(&router, &prober, VICTIM_PIN, &held).await;
        assert_eq!(last.status(), StatusCode::CONFLICT, "as {name}");
        assert_locked(set_pin(&router, &prober, VICTIM_PIN, &held).await).await;
    }
}
