//! HTTP contract of the **device mode** (plan step 2b, hub#357): `GET`/`PUT /api/device/mode`.
//!
//! `shared` is the counter till several people take turns at; `personal` is the owner's own
//! laptop. The mode decides how much identity friction there is — the conditional pinpad of
//! hub#358 hangs from it — so the question this file answers is not "does it persist" (that is
//! `crates/runtime/tests/device_mode.rs`) but **who is allowed to declare it**.
//!
//! The answer is the conservative one, and every test here is one half of it:
//!
//!  - **Reading is public, because it has to be**: the login screen asks before there is any
//!    session. It answers only for the `X-Device-Id` presented, and an unknown one gets `shared` —
//!    the strict mode — so the read door can neither be enumerated for anything useful nor talked
//!    into lowering the friction of a device the hub never met.
//!  - **Writing is an ADMIN session**, the same door as settings, API keys and the role catalogue:
//!    it decides whether a terminal asks who is standing at it.
//!  - **The client never declares its own mode.** `X-Device-Id` is an identifier the client sends
//!    in plain text, not a credential; it can only ever NAME a device, never claim a mode for it.
//!    The login endpoints do not take a mode, and a body that smuggles one changes nothing.
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

/// Router + admin session + employee session. `laptop-1` is already trusted, as an online (cloud)
/// login on it would have left it; `till-1` too. Nothing is trusted under any other id.
async fn fixture() -> (axum::Router, String, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-dm");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let employee_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    rt.trust_device("till-1", "Counter till").await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-device-mode-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-dm".into(),
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
        bootstrap_blueprint: None,
    };
    (app(AppState::with_config(rt, cfg)), admin, employee)
}

/// `GET /api/device/mode` identifying the device with `X-Device-Id` (or nothing at all).
async fn get_mode(router: &axum::Router, device_id: Option<&str>) -> (StatusCode, Value) {
    let mut builder = Request::builder().uri("/api/device/mode");
    if let Some(id) = device_id {
        builder = builder.header("x-device-id", id);
    }
    let response = router
        .clone()
        .oneshot(builder.body(Body::empty()).unwrap())
        .await
        .unwrap();
    let status = response.status();
    (status, body_json(response).await)
}

/// The mode the hub answers for `device_id` (asserting the read itself succeeded).
async fn mode_of(router: &axum::Router, device_id: &str) -> String {
    let (status, body) = get_mode(router, Some(device_id)).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    body["data"]["mode"].as_str().unwrap_or_default().to_string()
}

async fn put_mode(
    router: &axum::Router,
    session: Option<&str>,
    device_header: Option<&str>,
    body: Value,
) -> Response {
    let mut builder = Request::builder()
        .method("PUT")
        .uri("/api/device/mode")
        .header("content-type", "application/json");
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    if let Some(id) = device_header {
        builder = builder.header("x-device-id", id);
    }
    router
        .clone()
        .oneshot(builder.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap()
}

#[tokio::test]
async fn the_login_screen_reads_the_mode_without_a_session_and_an_unknown_device_is_shared() {
    let (router, _admin, _employee) = fixture().await;

    // No session: the pinpad question comes BEFORE anybody has signed in.
    assert_eq!(mode_of(&router, "laptop-1").await, "shared");
    assert_eq!(
        mode_of(&router, "a-device-nobody-enrolled").await,
        "shared",
        "an unknown device gets the strict mode"
    );

    // A client that identifies no device at all is answered too — with the strict mode.
    let (status, body) = get_mode(&router, None).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["data"]["mode"], json!("shared"));
}

#[tokio::test]
async fn only_an_administrator_declares_the_mode_of_a_device() {
    let (router, admin, employee) = fixture().await;

    let anonymous = put_mode(
        &router,
        None,
        None,
        json!({ "device_id": "laptop-1", "mode": "personal" }),
    )
    .await;
    assert_eq!(
        anonymous.status(),
        StatusCode::UNAUTHORIZED,
        "the client that presents a device id is not thereby allowed to describe it"
    );

    let denied = put_mode(
        &router,
        Some(&employee),
        None,
        json!({ "device_id": "laptop-1", "mode": "personal" }),
    )
    .await;
    assert_eq!(
        denied.status(),
        StatusCode::UNAUTHORIZED,
        "removing the pinpad from a terminal is administration of the hub"
    );
    assert_eq!(
        mode_of(&router, "laptop-1").await,
        "shared",
        "a refused call changes nothing"
    );

    let granted = put_mode(
        &router,
        Some(&admin),
        None,
        json!({ "device_id": "laptop-1", "mode": "personal" }),
    )
    .await;
    assert_eq!(granted.status(), StatusCode::OK);
    let body = body_json(granted).await;
    assert_eq!(body["ok"], json!(true));
    assert_eq!(
        body["data"]["mode"],
        json!("personal"),
        "the answer carries the mode that is now in force"
    );
    assert_eq!(mode_of(&router, "laptop-1").await, "personal");
    assert_eq!(
        mode_of(&router, "till-1").await,
        "shared",
        "the till of the same business is untouched: the mode is of the device"
    );
}

#[tokio::test]
async fn without_a_device_in_the_body_the_administrator_marks_the_device_in_front_of_them() {
    let (router, admin, _employee) = fixture().await;

    // The realistic gesture: "this device is mine" from the device itself. The header only NAMES
    // the device — what authorises the write is the admin session.
    let response = put_mode(&router, Some(&admin), Some("laptop-1"), json!({ "mode": "personal" })).await;
    assert_eq!(response.status(), StatusCode::OK, "{:?}", response.status());
    assert_eq!(mode_of(&router, "laptop-1").await, "personal");

    // An explicit empty id means the same as no id: the device in front of them.
    let blank_id = put_mode(
        &router,
        Some(&admin),
        Some("till-1"),
        json!({ "device_id": "", "mode": "personal" }),
    )
    .await;
    assert_eq!(blank_id.status(), StatusCode::OK);
    assert_eq!(mode_of(&router, "till-1").await, "personal");

    // A padded id still names the device it spells out, not a device called "  till-1 ".
    let padded = put_mode(
        &router,
        Some(&admin),
        None,
        json!({ "device_id": "  till-1 ", "mode": "shared" }),
    )
    .await;
    assert_eq!(padded.status(), StatusCode::OK);
    assert_eq!(mode_of(&router, "till-1").await, "shared");

    // And with neither body id nor header there is nothing to write about.
    let nothing = put_mode(&router, Some(&admin), None, json!({ "mode": "personal" })).await;
    assert_eq!(nothing.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

#[tokio::test]
async fn a_device_the_hub_never_met_cannot_be_declared_personal() {
    let (router, admin, _employee) = fixture().await;

    let refused = put_mode(
        &router,
        Some(&admin),
        None,
        json!({ "device_id": "made-up-id", "mode": "personal" }),
    )
    .await;
    assert_eq!(
        refused.status(),
        StatusCode::CONFLICT,
        "an id that never did an online login is a string, not a device"
    );
    assert_eq!(
        body_json(refused).await["error"]["code"],
        json!("hub.device.unknown_device")
    );
    assert_eq!(mode_of(&router, "made-up-id").await, "shared");
}

#[tokio::test]
async fn a_mode_outside_the_catalogue_is_refused_instead_of_guessed() {
    let (router, admin, _employee) = fixture().await;

    for candidate in [json!("Personal"), json!("trusted"), json!(""), json!("root")] {
        let refused = put_mode(
            &router,
            Some(&admin),
            None,
            json!({ "device_id": "laptop-1", "mode": candidate }),
        )
        .await;
        assert_eq!(
            refused.status(),
            StatusCode::UNPROCESSABLE_ENTITY,
            "the set of modes is closed: {candidate}"
        );
    }
    assert_eq!(
        mode_of(&router, "laptop-1").await,
        "shared",
        "no refused spelling ever lands as the lax mode"
    );
}

#[tokio::test]
async fn a_login_cannot_smuggle_a_mode_for_its_own_device() {
    let (router, _admin, _employee) = fixture().await;

    // The whole point: the identifier travels with the login, the MODE never does. A client that
    // adds one is answered exactly as before — and its device stays shared.
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/pin")
                .header("content-type", "application/json")
                .header("x-device-id", "till-1")
                .body(Body::from(
                    json!({
                        "name": "Employee",
                        "pin": "2222",
                        "device_id": "till-1",
                        "mode": "personal",
                        "device_mode": "personal"
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK, "the login itself still works");

    assert_eq!(
        mode_of(&router, "till-1").await,
        "shared",
        "a client cannot lower its own identity friction by asking nicely in the login body"
    );
}
