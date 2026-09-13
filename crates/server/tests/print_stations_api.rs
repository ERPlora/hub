//! HTTP contract of the **print stations** (hub#457, ADR-0196 §6).
//!
//! Stations became rows so that "which printer prints this" stops being a word two sides have to
//! spell the same way. That only pays off if *"new station"* actually exists as a gesture: a
//! restaurant with a *Terraza* has to be able to create it, or the closed part of the design (the
//! link) becomes a closed vocabulary, which is the Clover failure the market decision rejected.
//!
//! What these tests pin is **who may say what**:
//!
//!  - **Reading takes a session.** A cashier's screen needs the list to offer a destination, and
//!    the refusal of an unknown role names them anyway.
//!  - **Writing takes an admin session** — the same door as `/api/keys` and `/api/hub/users`.
//!    Adding a printing destination is configuring the business, not operating the till.
//!  - **Deleting refuses while work is queued (409)** and always for `receipt` (409). A station
//!    that vanished with tickets pointing at it would be the silent loss the queue exists to
//!    prevent, and a hub with no `receipt` could not print a sale at all.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB_ID: &str = "hub-print-stations";

/// Router + an admin session and an employee session.
async fn fixture() -> (axum::Router, String, String) {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let db = test_db.adapter().await;
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

    let temp = std::env::temp_dir().join(format!("erplora-print-stations-{}", std::process::id()));
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
    (app(AppState::with_config(rt, cfg)), admin, employee)
}

fn request(method: &str, uri: &str, session: Option<&str>, body: Option<Value>) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    match body {
        Some(b) => builder
            .header("content-type", "application/json")
            .body(Body::from(b.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    }
}

async fn call(
    router: &axum::Router,
    method: &str,
    uri: &str,
    session: Option<&str>,
    body: Option<Value>,
) -> (StatusCode, Value) {
    let resp = router
        .clone()
        .oneshot(request(method, uri, session, body))
        .await
        .unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    )
}

fn keys(list: &Value) -> Vec<String> {
    list["stations"]
        .as_array()
        .expect("a list of stations")
        .iter()
        .map(|s| s["key"].as_str().unwrap_or_default().to_string())
        .collect()
}

/// A brand-new hub already answers with the four destinations that every published contract sends
/// today — which is what lets step 2 resolve instead of compare without anybody touching a module.
#[tokio::test]
async fn a_fresh_hub_lists_the_four_stations_in_use_today() {
    let (router, _admin, employee) = fixture().await;
    let (status, body) = call(&router, "GET", "/api/print/stations", Some(&employee), None).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(keys(&body), ["bar", "kitchen", "label", "receipt"]);
}

/// The list is operational information the till needs to offer a destination — a session, not an
/// admin session. Anonymous is still nothing.
#[tokio::test]
async fn listing_stations_needs_a_session_but_not_an_admin_one() {
    let (router, _admin, _employee) = fixture().await;
    let (status, _) = call(&router, "GET", "/api/print/stations", None, None).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

/// **The open half of the design.** A real restaurant has a *Terraza*; once created it is a
/// destination like any other, and the queue resolves onto it.
#[tokio::test]
async fn an_admin_adds_a_station_and_the_queue_can_then_use_it() {
    let (router, admin, employee) = fixture().await;
    let (status, body) = call(
        &router,
        "POST",
        "/api/print/stations",
        Some(&admin),
        Some(json!({ "label": "Barra de la terraza" })),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["station"]["key"], json!("barra_de_la_terraza"));
    assert_eq!(body["station"]["label"], json!("Barra de la terraza"));

    let (status, _) = call(
        &router,
        "POST",
        "/api/print/jobs",
        Some(&employee),
        Some(json!({
            "jobId": "j-terraza",
            "role": "barra_de_la_terraza",
            "documentType": "receipt",
            "document": { "total": 3 },
        })),
    )
    .await;
    assert_eq!(
        status,
        StatusCode::OK,
        "a station the hub created has to be a station the queue accepts"
    );
}

/// Adding a printing destination is configuring the business, like issuing an API key or creating
/// a user. A cashier operates the tills; it does not decide what the tills are.
#[tokio::test]
async fn an_employee_cannot_add_rename_or_delete_a_station() {
    let (router, admin, employee) = fixture().await;
    let (_, list) = call(&router, "GET", "/api/print/stations", Some(&admin), None).await;
    let bar = list["stations"][0]["id"].as_str().unwrap().to_string();

    for (method, uri, body) in [
        (
            "POST",
            "/api/print/stations".to_string(),
            Some(json!({ "label": "Terraza" })),
        ),
        (
            "PATCH",
            format!("/api/print/stations/{bar}"),
            Some(json!({ "label": "Barra" })),
        ),
        ("DELETE", format!("/api/print/stations/{bar}"), None),
    ] {
        let (status, _) = call(&router, method, &uri, Some(&employee), body).await;
        // hub#1705: a valid session without the role is `403 forbidden` — signing in again would not help.
        assert_eq!(
            status,
            StatusCode::FORBIDDEN,
            "{method} {uri} must take an admin session"
        );
    }
}

/// Renaming touches the **label**, never the key: the key is what every published contract sends
/// and what every queued job already carries.
#[tokio::test]
async fn renaming_a_station_keeps_the_key_the_wire_uses() {
    let (router, admin, employee) = fixture().await;
    let (_, list) = call(&router, "GET", "/api/print/stations", Some(&admin), None).await;
    let kitchen = list["stations"]
        .as_array()
        .unwrap()
        .iter()
        .find(|s| s["key"] == json!("kitchen"))
        .unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();

    let (status, body) = call(
        &router,
        "PATCH",
        &format!("/api/print/stations/{kitchen}"),
        Some(&admin),
        Some(json!({ "label": "Cocina caliente" })),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["station"]["label"], json!("Cocina caliente"));
    assert_eq!(body["station"]["key"], json!("kitchen"));

    let (status, _) = call(
        &router,
        "POST",
        "/api/print/jobs",
        Some(&employee),
        Some(json!({
            "jobId": "j-after-rename",
            "role": "kitchen",
            "documentType": "kitchen_order",
            "document": { "items": [{ "name": "Bacalao" }] },
        })),
    )
    .await;
    assert_eq!(
        status,
        StatusCode::OK,
        "a rename must not strand the tickets"
    );
}

/// **Deleting cannot drop a ticket on the floor.** A station with work still queued refuses with a
/// `409`, which is the same channel a domain conflict uses everywhere else in the hub.
#[tokio::test]
async fn a_station_with_a_queued_ticket_cannot_be_deleted() {
    let (router, admin, employee) = fixture().await;
    let (_, list) = call(&router, "GET", "/api/print/stations", Some(&admin), None).await;
    let bar = list["stations"]
        .as_array()
        .unwrap()
        .iter()
        .find(|s| s["key"] == json!("bar"))
        .unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();

    call(
        &router,
        "POST",
        "/api/print/jobs",
        Some(&employee),
        Some(json!({
            "jobId": "j-bar",
            "role": "bar",
            "documentType": "receipt",
            "document": { "total": 3 },
        })),
    )
    .await;

    let (status, body) = call(
        &router,
        "DELETE",
        &format!("/api/print/stations/{bar}"),
        Some(&admin),
        None,
    )
    .await;
    assert_eq!(status, StatusCode::CONFLICT, "{body}");
    assert_eq!(
        keys(
            &call(&router, "GET", "/api/print/stations", Some(&admin), None)
                .await
                .1
        ),
        ["bar", "kitchen", "label", "receipt"],
        "the refusal left the station where it was"
    );
}

/// `receipt` is the shell's default destination: a hub without it could not print a sale, and the
/// owner would find that out at the counter.
#[tokio::test]
async fn the_receipt_station_cannot_be_deleted() {
    let (router, admin, _employee) = fixture().await;
    let (_, list) = call(&router, "GET", "/api/print/stations", Some(&admin), None).await;
    let receipt = list["stations"]
        .as_array()
        .unwrap()
        .iter()
        .find(|s| s["key"] == json!("receipt"))
        .unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();

    let (status, _) = call(
        &router,
        "DELETE",
        &format!("/api/print/stations/{receipt}"),
        Some(&admin),
        None,
    )
    .await;
    assert_eq!(status, StatusCode::CONFLICT);
}

/// A station this hub does not use is the merchant's to remove once nothing is waiting for it.
#[tokio::test]
async fn an_unused_station_is_deleted() {
    let (router, admin, _employee) = fixture().await;
    let (_, list) = call(&router, "GET", "/api/print/stations", Some(&admin), None).await;
    let bar = list["stations"]
        .as_array()
        .unwrap()
        .iter()
        .find(|s| s["key"] == json!("bar"))
        .unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();

    let (status, _) = call(
        &router,
        "DELETE",
        &format!("/api/print/stations/{bar}"),
        Some(&admin),
        None,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        keys(
            &call(&router, "GET", "/api/print/stations", Some(&admin), None)
                .await
                .1
        ),
        ["kitchen", "label", "receipt"]
    );
}

/// Deleting something that is not a station of this hub is a `404`, not a silent success: an
/// "it worked" for an id that never existed is how a UI ends up out of step with the hub.
#[tokio::test]
async fn deleting_a_station_that_does_not_exist_is_a_404() {
    let (router, admin, _employee) = fixture().await;
    let (status, _) = call(
        &router,
        "DELETE",
        "/api/print/stations/not-a-station",
        Some(&admin),
        None,
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

/// **The bug, at the HTTP door.** A job for a destination this hub does not have is a `422` that
/// names the ones it does — so a `kitchn` is read as a typo instead of becoming a queue nobody
/// drains. Same status and shape as the sibling `documentType` guard.
#[tokio::test]
async fn a_job_for_an_unknown_station_is_a_422_that_names_the_real_ones() {
    let (router, _admin, employee) = fixture().await;
    let (status, body) = call(
        &router,
        "POST",
        "/api/print/jobs",
        Some(&employee),
        Some(json!({
            "jobId": "j-typo",
            "role": "kitchn",
            "documentType": "kitchen_order",
            "document": { "items": [{ "name": "Bacalao" }] },
        })),
    )
    .await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    let message = body["error"]["message"].as_str().unwrap_or_default();
    assert!(message.contains("kitchn"), "{body}");
    assert!(message.contains("kitchen"), "{body}");
}

/// The registry is the other side of the same door: a device cannot become the live host of a
/// queue no producer will ever fill.
#[tokio::test]
async fn registering_a_host_for_an_unknown_station_is_refused() {
    let (router, _admin, employee) = fixture().await;
    let resp = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/print/hosts")
                .header("x-hub-session", &employee)
                .header("x-device-id", "till-1")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({ "role": "kitchn", "label": "Caja" }).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}
