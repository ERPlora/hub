//! **Who may turn the lock off** — HTTP contract of the "ask for a PIN: always / per shift /
//! never" setting (plan step 2b, hub#359).
//!
//! `never` is the value that stops the till asking *which* of the staff is standing at it. That
//! makes this file the security half of the feature, and the question it answers is not "does the
//! dial work" (that is `crates/runtime/tests/pin_policy.rs`) but the one that decides whether the
//! whole thing is worth anything:
//!
//! > **Can the lock be taken off without going through the lock?**
//!
//! The answer has to be no, in every direction a caller can push:
//!
//!  - **Writing it is an ADMIN session** — the `/api/settings` door, the same one as the currency,
//!    the API keys and the role catalogue. Not the employee holding the tablet, and certainly not
//!    the login screen, which runs with no session at all.
//!  - **Nothing a client sends declares a policy.** There is no header, no login field and no
//!    query parameter that exempts the caller: the hub reads its own setting. A body that smuggles
//!    one changes nothing.
//!  - **An unknown spelling is refused, never guessed.** A value the hub cannot read must not
//!    resolve to the lax end of the dial — the one that would be silently reached by a typo, a
//!    restored backup or a newer version writing a value this build does not know.
//!
//! The first three tests are deliberately about the DOOR, not about the key: they were written
//! before the setting existed and passed then too (the door already refuses everyone without an
//! admin session, and already refuses a key it does not know). What they stop is the regression
//! where adding the setting quietly opens a second, easier entrance for it.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

type Response = axum::response::Response;

async fn body_json(response: Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// Router + an admin session + an employee session. `till-1` is trusted, as an online (cloud)
/// login on it would have left it.
async fn fixture() -> (axum::Router, String, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-pp");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let employee_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    rt.trust_device("till-1", "Counter till").await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-pin-policy-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-pp".into(),
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
    (app(AppState::with_config(rt, cfg)), admin, employee)
}

/// `PUT /api/settings` with an optional session token.
async fn put_settings(router: &axum::Router, session: Option<&str>, body: Value) -> Response {
    let mut builder = Request::builder()
        .method("PUT")
        .uri("/api/settings")
        .header("content-type", "application/json");
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    router
        .clone()
        .oneshot(builder.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap()
}

/// `GET /api/device/mode` — the **unauthenticated** read the login screen does. Optionally naming
/// a device, and optionally smuggling extra headers a client might hope are taken as a claim.
async fn get_device_mode(
    router: &axum::Router,
    device_id: Option<&str>,
    smuggled: &[(&str, &str)],
) -> (StatusCode, Value) {
    let mut builder = Request::builder().uri("/api/device/mode");
    if let Some(id) = device_id {
        builder = builder.header("x-device-id", id);
    }
    for (name, value) in smuggled {
        builder = builder.header(*name, *value);
    }
    let response = router
        .clone()
        .oneshot(builder.body(Body::empty()).unwrap())
        .await
        .unwrap();
    let status = response.status();
    (status, body_json(response).await)
}

/// The policy in force according to the hub, read the way the login screen reads it.
async fn policy_of(router: &axum::Router, device_id: &str) -> String {
    let (status, body) = get_device_mode(router, Some(device_id), &[]).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    body["data"]["pin_policy"]
        .as_str()
        .unwrap_or_default()
        .to_string()
}

// ── The guards: the lock cannot be taken off without going through the lock ─────────────────────

#[tokio::test]
async fn nobody_without_an_admin_session_turns_the_pin_off() {
    let (router, _admin, employee) = fixture().await;

    // The login screen has no session at all. If it could write this, the pinpad would be a
    // switch reachable from in front of the lock.
    let anonymous = put_settings(&router, None, json!({ "pin_policy": "never" })).await;
    assert_eq!(
        anonymous.status(),
        StatusCode::UNAUTHORIZED,
        "a caller with no session must not be able to stop the hub asking who is selling"
    );

    // Nor the person holding the tablet: deciding that sales stop carrying a name is
    // administration of the business, not a preference of whoever is on shift.
    let denied = put_settings(&router, Some(&employee), json!({ "pin_policy": "never" })).await;
    assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);

    // And a refused call changed nothing: the hub still asks.
    assert_ne!(
        policy_of(&router, "till-1").await,
        "never",
        "a refused write must not have landed anyway"
    );
}

#[tokio::test]
async fn a_policy_the_hub_cannot_read_is_refused_and_never_lands_on_never() {
    let (router, admin, _employee) = fixture().await;

    // Every one of these is a value that is *nearly* right. None of them may be guessed, and above
    // all none of them may fall through to the lax end: `never` has to be typed exactly, by an
    // administrator, on purpose.
    for candidate in ["", " ", "Never", "never ", "nunca", "sometimes", "0", "false"] {
        let refused = put_settings(&router, Some(&admin), json!({ "pin_policy": candidate })).await;
        assert_eq!(
            refused.status(),
            StatusCode::UNPROCESSABLE_ENTITY,
            "`{candidate}` was accepted as a policy"
        );
        assert_ne!(
            policy_of(&router, "till-1").await,
            "never",
            "`{candidate}` moved the hub towards not asking"
        );
    }

    // Same for a value of the wrong TYPE: JSON has more shapes than the dial has positions.
    for candidate in [json!(true), json!(0), json!(null), json!(["never"])] {
        let refused = put_settings(&router, Some(&admin), json!({ "pin_policy": candidate })).await;
        assert_eq!(
            refused.status(),
            StatusCode::UNPROCESSABLE_ENTITY,
            "{candidate} was accepted as a policy"
        );
    }
}

#[tokio::test]
async fn a_client_cannot_declare_itself_exempt() {
    let (router, _admin, _employee) = fixture().await;

    // The read door takes no session, because the login screen has none. So it is the door a
    // client would try to talk INTO answering `never` — with a header, with a made-up device, with
    // both. It only ever reports what an administrator recorded.
    let smuggled = get_device_mode(
        &router,
        Some("till-1"),
        &[
            ("x-pin-policy", "never"),
            ("x-erplora-pin-policy", "never"),
            ("x-device-mode", "personal"),
        ],
    )
    .await;
    assert_eq!(smuggled.0, StatusCode::OK, "{}", smuggled.1);
    assert_ne!(
        smuggled.1["data"]["pin_policy"], json!("never"),
        "a header is not a decision: the hub reads its own setting"
    );

    // And an id the hub never met buys nothing either.
    assert_ne!(policy_of(&router, "a-device-nobody-enrolled").await, "never");
}

// ── The behaviour: the dial exists, and the login screen can see where it points ────────────────

#[tokio::test]
async fn an_administrator_turns_it_off_and_the_login_screen_sees_it_without_a_session() {
    let (router, admin, _employee) = fixture().await;

    // Before anybody decides anything, the hub asks: the default is a value that keeps every sale
    // attributed to a person.
    assert_eq!(
        policy_of(&router, "till-1").await,
        "per_shift",
        "the default has to be one of the two that keep asking"
    );

    let granted = put_settings(&router, Some(&admin), json!({ "pin_policy": "never" })).await;
    assert_eq!(granted.status(), StatusCode::OK, "{:?}", granted.status());
    assert_eq!(
        body_json(granted).await["pin_policy"],
        json!("never"),
        "the settings answer carries the policy now in force"
    );

    // The login screen reads it on the door that takes no session — the same one that already
    // answers the device mode. It has to: this is what decides whether the pinpad is painted, and
    // at that point nobody has signed in.
    assert_eq!(policy_of(&router, "till-1").await, "never");

    // It is a dial, not a one-way door.
    let back = put_settings(&router, Some(&admin), json!({ "pin_policy": "always" })).await;
    assert_eq!(back.status(), StatusCode::OK);
    assert_eq!(policy_of(&router, "till-1").await, "always");
}
