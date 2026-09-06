//! «Connect WhatsApp» from the hub (hub#1600, ADR-0452) — the runtime's four doors to the SaaS.
//!
//! The owner presses the button in the WhatsApp module's settings; the shell opens Meta's popup
//! and, when it closes, hands the runtime a `code` plus the ids Meta reported. The runtime is the
//! one that talks to the SaaS — with the hub's **machine credential**, never with anything the
//! browser sent — because the SaaS is where the token ends up (ADR-0012) and because a cashier
//! signed in by PIN has no cloud JWT to lend. Who is at the till is this side's job: **owner/admin
//! session**, the same gate as the rest of the hub's management.
//!
//! What is asserted: the gate (no session → 401, an employee → 403), the credential on the wire
//! (`X-Hub-Token`, no `Authorization`), the body reaching the SaaS verbatim, the SaaS's answer
//! coming back untouched (status included, so «no phone number» stays a 404 the page can name),
//! and a disconnect id that cannot climb out of its route.
use axum::body::Body;
use axum::extract::Path;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};
use tower::ServiceExt;

fn config(hub_id: &str, cloud_base_url: String, tag: &str) -> HubConfig {
    let temp =
        std::env::temp_dir().join(format!("erplora-wa-connect-{tag}-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        cloud_base_url,
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
    }
}

/// A router with one admin session and one employee session, pointed at `cloud_base_url`.
async fn fixture(cloud_base_url: String, tag: &str) -> (Router, String, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-wa");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let admin_session = rt.create_session(&admin, 3600, None).await.unwrap();
    let employee = rt
        .create_user("Luis", "2222", "employee", None)
        .await
        .unwrap();
    let employee_session = rt.create_session(&employee, 3600, None).await.unwrap();
    (
        app(AppState::with_config(
            rt,
            config("hub-wa", cloud_base_url, tag),
        )),
        admin_session,
        employee_session,
    )
}

fn get_as(uri: &str, session: Option<&str>) -> Request<Body> {
    let mut req = Request::get(uri);
    if let Some(s) = session {
        req = req.header("x-hub-session", s);
    }
    req.body(Body::empty()).unwrap()
}

fn post_as(uri: &str, session: Option<&str>, body: Value) -> Request<Body> {
    let mut req = Request::post(uri).header("content-type", "application/json");
    if let Some(s) = session {
        req = req.header("x-hub-session", s);
    }
    req.body(Body::from(body.to_string())).unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// What the fake SaaS saw: headers and body of the last call to each door.
#[derive(Default)]
struct Seen {
    headers: Vec<(String, String)>,
    body: Value,
    path: String,
}

fn record(seen: &Arc<Mutex<Seen>>, path: &str, headers: &HeaderMap, body: Value) {
    let mut s = seen.lock().unwrap();
    s.path = path.to_string();
    s.body = body;
    s.headers = headers
        .iter()
        .map(|(k, v)| (k.as_str().to_string(), v.to_str().unwrap_or("").to_string()))
        .collect();
}

fn machine_credential_and_nothing_else(seen: &Seen) {
    let get = |k: &str| {
        seen.headers
            .iter()
            .find(|(h, _)| h == k)
            .map(|(_, v)| v.clone())
    };
    assert_eq!(
        get("x-hub-token").as_deref(),
        Some("machine-secret"),
        "{:?}",
        seen.headers
    );
    assert_eq!(get("x-hub-id").as_deref(), Some("hub-wa"));
    assert!(
        get("authorization").is_none(),
        "the browser's bearer must never reach the SaaS"
    );
    assert!(
        get("x-hub-session").is_none(),
        "the local session token must never leave the hub"
    );
}

async fn fake_saas(seen: Arc<Mutex<Seen>>) -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let s1 = seen.clone();
    let s2 = seen.clone();
    let s3 = seen.clone();
    let s4 = seen.clone();
    let saas = Router::new()
        .route(
            "/api/v1/hub/device/whatsapp/config/",
            get(move |headers: HeaderMap| async move {
                record(&s1, "config", &headers, Value::Null);
                Json(json!({
                    "configured": true,
                    "app_id": "1534856651538860",
                    "config_id": "1963049141319502",
                    "graph_version": "v25.0"
                }))
            }),
        )
        .route(
            "/api/v1/hub/device/whatsapp/numbers/",
            get(move |headers: HeaderMap| async move {
                record(&s2, "numbers", &headers, Value::Null);
                Json(json!({ "numbers": [{ "phone_number_id": "phone_123", "display_phone": "+34 612 345 678", "is_active": true }] }))
            }),
        )
        .route(
            "/api/v1/hub/device/whatsapp/connect/",
            post(move |headers: HeaderMap, Json(body): Json<Value>| async move {
                let no_phone = body.get("event").and_then(Value::as_str) == Some("FINISH_ONLY_WABA");
                record(&s3, "connect", &headers, body);
                if no_phone {
                    return (StatusCode::NOT_FOUND, Json(json!({ "error": "No phone numbers found in WhatsApp Business Account" })));
                }
                (StatusCode::OK, Json(json!({ "phone_number_id": "phone_123", "display_phone": "+34 612 345 678" })))
            }),
        )
        .route(
            "/api/v1/hub/device/whatsapp/disconnect/:phone_number_id/",
            post(move |Path(id): Path<String>, headers: HeaderMap| async move {
                record(&s4, &format!("disconnect:{id}"), &headers, Value::Null);
                Json(json!({ "success": true }))
            }),
        );
    tokio::spawn(async move { axum::serve(listener, saas).await.unwrap() });
    format!("http://{address}")
}

#[tokio::test]
async fn the_config_reaches_the_till_with_the_machine_credential() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "config").await;

    let response = router
        .oneshot(get_as("/api/hub/whatsapp/config", Some(&admin)))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["config_id"], "1963049141319502");
    assert_eq!(body["app_id"], "1534856651538860");
    machine_credential_and_nothing_else(&seen.lock().unwrap());
}

#[tokio::test]
async fn the_code_meta_handed_the_till_reaches_the_saas_verbatim_and_its_answer_comes_back() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "connect").await;
    let popup = json!({
        "code": "oauth-code",
        "event": "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING",
        "waba_id": "waba_123",
        "phone_number_id": "phone_123",
        "business_id": "biz_123"
    });

    let response = router
        .oneshot(post_as(
            "/api/hub/whatsapp/connect",
            Some(&admin),
            popup.clone(),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(body_json(response).await["phone_number_id"], "phone_123");
    let s = seen.lock().unwrap();
    assert_eq!(s.path, "connect");
    assert_eq!(
        s.body, popup,
        "the SaaS must see exactly what Meta reported, nothing rewritten"
    );
    machine_credential_and_nothing_else(&s);
}

#[tokio::test]
async fn a_refusal_from_the_saas_keeps_its_status_so_the_page_can_name_it() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen).await, "no-phone").await;

    let response = router
        .oneshot(post_as(
            "/api/hub/whatsapp/connect",
            Some(&admin),
            json!({ "code": "c", "event": "FINISH_ONLY_WABA", "waba_id": "waba_123" }),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn the_numbers_and_the_disconnect_go_through_the_same_door() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "numbers").await;

    let response = router
        .clone()
        .oneshot(get_as("/api/hub/whatsapp/numbers", Some(&admin)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        body_json(response).await["numbers"][0]["phone_number_id"],
        "phone_123"
    );

    let response = router
        .oneshot(post_as(
            "/api/hub/whatsapp/disconnect/1122349777617204",
            Some(&admin),
            json!({}),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let s = seen.lock().unwrap();
    assert_eq!(s.path, "disconnect:1122349777617204");
    machine_credential_and_nothing_else(&s);
}

#[tokio::test]
async fn a_disconnect_id_cannot_climb_out_of_its_route() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "hostile").await;

    let response = router
        .oneshot(post_as(
            "/api/hub/whatsapp/disconnect/..%2Fnotify%2Fwhatsapp",
            Some(&admin),
            json!({}),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        seen.lock().unwrap().path,
        "",
        "nothing may reach the SaaS with an id like that"
    );
}

#[tokio::test]
async fn without_an_admin_session_the_doors_stay_closed() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, _admin, employee) = fixture(fake_saas(seen.clone()).await, "gate").await;

    let anonymous = router
        .clone()
        .oneshot(get_as("/api/hub/whatsapp/config", None))
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    let cashier = router
        .oneshot(post_as(
            "/api/hub/whatsapp/connect",
            Some(&employee),
            json!({ "code": "c" }),
        ))
        .await
        .unwrap();
    assert_eq!(
        cashier.status(),
        StatusCode::FORBIDDEN,
        "connecting the channel is the owner's, not the shift's"
    );
    assert_eq!(
        seen.lock().unwrap().path,
        "",
        "a refused call must not touch the SaaS"
    );
}

#[tokio::test]
async fn a_saas_that_does_not_answer_is_an_error_not_a_silent_ok() {
    let (router, admin, _) = fixture("http://127.0.0.1:1/".into(), "down").await;

    let response = router
        .oneshot(post_as(
            "/api/hub/whatsapp/connect",
            Some(&admin),
            json!({ "code": "c" }),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
}
