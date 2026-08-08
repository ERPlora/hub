//! HTTP contract of the **print host registry** (hub#342, ADR-0196 §6).
//!
//! The queue (hub#341) guarantees a ticket is never lost for want of somebody holding a device.
//! This is the door where a device says *"I am the one that prints the kitchen's"*. What the tests
//! here pin is not that it persists — that is `erplora_runtime::print_hosts` — but **who may say
//! what about which device**:
//!
//!  - **A device only ever registers, beats for, or retires ITSELF.** The subject is the
//!    `X-Device-Id` of the caller and there is no way to name another device on the write doors,
//!    which is why an ordinary session is enough for them: the realistic gesture is "this device,
//!    the one in my hands, prints the kitchen's", and it has to work when the app starts, long
//!    after whoever set the hub up went home.
//!  - **Retiring somebody ELSE's device is an admin session** — the same asymmetry as
//!    `/api/device/mode`. That is the door for the till that was replaced or stolen, and it is the
//!    only one that can act on a device the caller is not holding.
//!  - **Reading takes a session.** Whether anything is going to print is operational information a
//!    cashier legitimately needs ("I charged and no ticket came out"), not public information.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB_ID: &str = "hub-print-hosts";

/// Router + an admin session and an employee session.
async fn fixture() -> (axum::Router, String, String) {
    let (router, admin, employee, _db) = fixture_with_db().await;
    (router, admin, employee)
}

/// Same fixture, plus a **second handle on the same schema**. Only the liveness test needs it: a
/// device that was switched off cannot report anything, so the only way to simulate it is to let
/// time pass on `last_seen_at`, and there is no HTTP door that writes it into the past (there must
/// not be — that would be a door for declaring yourself alive, which is exactly what the design
/// refuses).
async fn fixture_with_db() -> (axum::Router, String, String, erplora_db::PgAdapter) {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let db = test_db.adapter().await;
    let probe = test_db.adapter().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let employee_id = rt
        .create_user("Cashier", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-print-hosts-{}", std::process::id()));
    let cfg = HubConfig {
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
        bootstrap_blueprint: None,
    };
    (app(AppState::with_config(rt, cfg)), admin, employee, probe)
}

fn request(
    method: &str,
    uri: &str,
    session: Option<&str>,
    device_id: Option<&str>,
    body: Option<Value>,
) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    if let Some(id) = device_id {
        builder = builder.header("x-device-id", id);
    }
    match body {
        Some(b) => builder
            .header("content-type", "application/json")
            .body(Body::from(b.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    }
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// `POST /api/print/hosts` as `device_id`, for `role`.
async fn register(
    router: &axum::Router,
    session: &str,
    device_id: Option<&str>,
    role: &str,
    label: &str,
) -> (StatusCode, Value) {
    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/hosts",
            Some(session),
            device_id,
            Some(json!({ "role": role, "label": label })),
        ))
        .await
        .unwrap();
    (resp.status(), body_json(resp).await)
}

async fn registry(router: &axum::Router, session: &str) -> Value {
    let resp = router
        .clone()
        .oneshot(request(
            "GET",
            "/api/print/hosts",
            Some(session),
            None,
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    body_json(resp).await
}

fn coverage_of<'a>(body: &'a Value, role: &str) -> Option<&'a Value> {
    body["coverage"]
        .as_array()?
        .iter()
        .find(|c| c["role"] == json!(role))
}

/// The registry is hub data behind the same session gate as the rest of the core API — on every
/// door, including the read.
#[tokio::test]
async fn the_print_host_registry_requires_a_user_session() {
    let (router, _admin, _employee) = fixture().await;

    for (method, uri, body) in [
        (
            "POST",
            "/api/print/hosts",
            Some(json!({ "role": "kitchen" })),
        ),
        ("POST", "/api/print/hosts/heartbeat", None),
        ("GET", "/api/print/hosts", None),
        ("DELETE", "/api/print/hosts", None),
    ] {
        let resp = router
            .clone()
            .oneshot(request(method, uri, None, Some("till-1"), body))
            .await
            .unwrap();
        assert_eq!(
            resp.status(),
            StatusCode::UNAUTHORIZED,
            "{method} {uri} must not be anonymous"
        );
    }
}

/// The happy path: the device in the cashier's hands declares itself the kitchen's print host and
/// shows up live, under the name the owner will read.
#[tokio::test]
async fn a_device_registers_itself_and_shows_up_live() {
    let (router, _admin, employee) = fixture().await;

    let (status, body) = register(
        &router,
        &employee,
        Some("till-1"),
        "kitchen",
        "Counter till",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["ok"], json!(true));
    assert_eq!(body["host"]["deviceId"], json!("till-1"));
    assert_eq!(body["host"]["role"], json!("kitchen"));
    assert_eq!(body["host"]["label"], json!("Counter till"));
    assert_eq!(body["host"]["live"], json!(true));

    let body = registry(&router, &employee).await;
    assert_eq!(body["hosts"].as_array().unwrap().len(), 1);
    assert_eq!(body["hosts"][0]["deviceId"], json!("till-1"));
    assert_eq!(body["hosts"][0]["live"], json!(true));
    assert_eq!(
        coverage_of(&body, "kitchen").unwrap()["liveHosts"],
        json!(1)
    );
}

/// The write doors act on the CALLER's device, so a caller that names none has not said which
/// device prints anything. Refused, never guessed — a registration under an empty id would put a
/// host that does not exist in front of a real queue.
#[tokio::test]
async fn a_caller_that_names_no_device_cannot_register_or_beat() {
    let (router, _admin, employee) = fixture().await;

    let (status, body) = register(&router, &employee, None, "kitchen", "").await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(body["error"]["code"], json!("invalid_payload"));
    // The message has to name the HEADER, not a body field. The runtime rejects an empty device id
    // too, with the same status and the same code, so without this assertion the door's own guard
    // could be deleted and every test here would still pass — while the client got told that
    // "device_id is required" about something it never puts in the body.
    let message = body["error"]["message"].as_str().unwrap_or_default();
    assert!(
        message.contains("X-Device-Id"),
        "the caller must learn WHICH header is missing, got: {message}"
    );

    let (status, _) = register(&router, &employee, Some("   "), "kitchen", "").await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "blanks are no id");

    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/hosts/heartbeat",
            Some(&employee),
            None,
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// **The hub tells the host how often to report.** Otherwise the client hard-codes an interval that
/// can drift away from the hub's window, and the day they disagree every till looks offline.
#[tokio::test]
async fn the_hub_tells_the_host_how_often_to_report() {
    let (router, _admin, employee) = fixture().await;
    let expected = json!(erplora_runtime::print_hosts::HEARTBEAT_SECONDS);

    let (_, body) = register(&router, &employee, Some("till-1"), "kitchen", "").await;
    assert_eq!(body["heartbeatSeconds"], expected);

    let resp = router
        .oneshot(request(
            "POST",
            "/api/print/hosts/heartbeat",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["refreshed"], json!(1));
    assert_eq!(
        body["heartbeatSeconds"], expected,
        "the interval travels on every beat, not only at registration"
    );
}

/// A beat from a device that hosts nothing answers `0` instead of failing: that is the signal the
/// app needs to register again, and a 404 would look like a broken hub instead.
#[tokio::test]
async fn a_beat_from_a_device_that_hosts_nothing_answers_zero() {
    let (router, _admin, employee) = fixture().await;

    let resp = router
        .oneshot(request(
            "POST",
            "/api/print/hosts/heartbeat",
            Some(&employee),
            Some("phone-9"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["refreshed"], json!(0));
}

/// A device retires itself from one role and keeps the others: "this till no longer prints the
/// kitchen's" is not "this till prints nothing".
#[tokio::test]
async fn a_device_retires_itself_from_one_role() {
    let (router, _admin, employee) = fixture().await;
    register(&router, &employee, Some("till-1"), "kitchen", "Counter").await;
    register(&router, &employee, Some("till-1"), "receipt", "Counter").await;

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?role=kitchen",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["removed"], json!(1));

    let body = registry(&router, &employee).await;
    assert_eq!(body["hosts"].as_array().unwrap().len(), 1);
    assert_eq!(body["hosts"][0]["role"], json!("receipt"));
}

/// With no `role`, the device retires from everything: "this device is no longer a print host".
#[tokio::test]
async fn a_device_retires_itself_from_every_role() {
    let (router, _admin, employee) = fixture().await;
    register(&router, &employee, Some("till-1"), "kitchen", "Counter").await;
    register(&router, &employee, Some("till-1"), "receipt", "Counter").await;

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(body_json(resp).await["removed"], json!(2));
    assert!(registry(&router, &employee).await["hosts"]
        .as_array()
        .unwrap()
        .is_empty());
}

/// **Retiring somebody else's device is administration.** It is the door for the till that was
/// replaced or stolen — the only gesture here that reaches a device the caller is not holding —
/// so it takes the same session as settings and the role catalogue. An ordinary cashier cannot
/// silently stop another till from printing.
#[tokio::test]
async fn retiring_another_device_takes_an_admin_session() {
    let (router, admin, employee) = fixture().await;
    register(&router, &employee, Some("till-2"), "kitchen", "Old till").await;

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?deviceId=till-2",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::UNAUTHORIZED,
        "a cashier cannot retire a till they are not holding"
    );
    assert_eq!(
        registry(&router, &employee).await["hosts"]
            .as_array()
            .unwrap()
            .len(),
        1,
        "and nothing was removed"
    );

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?deviceId=till-2",
            Some(&admin),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["removed"], json!(1));
    assert!(registry(&router, &admin).await["hosts"]
        .as_array()
        .unwrap()
        .is_empty());
}

/// Naming your OWN device explicitly is still your own device, so it does not need an admin: the
/// gate is "somebody else's", not "the parameter was present".
#[tokio::test]
async fn naming_your_own_device_explicitly_needs_no_admin() {
    let (router, _admin, employee) = fixture().await;
    register(&router, &employee, Some("till-1"), "kitchen", "Counter").await;

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?deviceId=till-1",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["removed"], json!(1));
}

/// **A device that went quiet reports `live: false` over the wire.** The whole point of deriving
/// liveness is that the owner's screen can tell "nobody is printing this" from "somebody is"; a
/// door that always answered `true` would look right on the happy path and hide the only state
/// worth showing.
#[tokio::test]
async fn a_host_that_went_quiet_is_reported_as_not_live() {
    let (router, _admin, employee, db) = fixture_with_db().await;
    register(&router, &employee, Some("till-1"), "kitchen", "Counter").await;
    assert_eq!(
        registry(&router, &employee).await["hosts"][0]["live"],
        json!(true)
    );

    // The device was switched off: it cannot tell anybody, so silence is the only signal.
    use erplora_db::{DatabaseAdapter, Params};
    let mut p = Params::new();
    p.insert(
        "at".into(),
        json!((chrono::Utc::now()
            - chrono::Duration::seconds(erplora_runtime::print_hosts::HOST_TTL_SECONDS + 5))
        .to_rfc3339()),
    );
    db.execute(
        "UPDATE _print_host SET last_seen_at = :at WHERE device_id = 'till-1'",
        &p,
    )
    .await
    .unwrap();

    let body = registry(&router, &employee).await;
    assert_eq!(
        body["hosts"][0]["live"],
        json!(false),
        "the registry must report the till that stopped answering"
    );
    assert_eq!(
        coverage_of(&body, "kitchen").unwrap()["liveHosts"],
        json!(0)
    );
}

/// **`X-Device-Id` is trimmed at the door.** A header the client padded with a space has to name
/// the same device as the unpadded one — otherwise `" till-1 "` registers a second, phantom host,
/// and worse, retiring your own device by name stops matching the header and demands an admin.
#[tokio::test]
async fn a_padded_device_header_names_the_same_device() {
    let (router, _admin, employee) = fixture().await;

    register(&router, &employee, Some(" till-1 "), "kitchen", "Counter").await;
    let body = registry(&router, &employee).await;
    assert_eq!(
        body["hosts"].as_array().unwrap().len(),
        1,
        "one device, not one per spelling"
    );
    assert_eq!(body["hosts"][0]["deviceId"], json!("till-1"));

    // Naming your own device explicitly must still be "your own", padding and all: with an
    // untrimmed header this comparison fails and a cashier is refused their own till.
    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?deviceId=till-1",
            Some(&employee),
            Some(" till-1 "),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "a padded header is the same device, so no admin is needed"
    );
    assert_eq!(body_json(resp).await["removed"], json!(1));
}

/// **Somebody charged and nothing is going to print.** The sale is not blocked and the ticket is
/// not lost — it waits — but the registry now says so out loud, per role, which is what lets a
/// screen warn the owner instead of leaving them to find out at the pass.
#[tokio::test]
async fn the_registry_reports_work_waiting_with_nobody_to_print_it() {
    let (router, _admin, employee) = fixture().await;

    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/jobs",
            Some(&employee),
            Some("phone-1"),
            Some(json!({
                "jobId": "j1",
                "role": "kitchen",
                "documentType": "kitchen_order",
                "document": { "receipt_id": "K-1" },
            })),
        ))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "charging never depends on a printer being attended"
    );

    let body = registry(&router, &employee).await;
    let kitchen = coverage_of(&body, "kitchen").expect("the role is reported even with no host");
    assert_eq!(kitchen["waiting"], json!(1));
    assert_eq!(kitchen["liveHosts"], json!(0));
}
