//! **`PATCH /api/business/certificate` — the «Usar mi propio certificado» switch** (Ioan, 2026-09-15).
//!
//! The runtime half (`crates/runtime/tests/own_certificate_switch.rs`) pins WHAT the switch does.
//! This file pins the door the screen goes through:
//!  - an admin switches it, and the answer is the same `{ok, data}` status the other three doors
//!    answer (`present` stays true, the route follows the choice);
//!  - the body is validated, only an admin may switch, and switching ON with nothing uploaded
//!    answers the domain code the screen translates;
//!  - 🔴 **the SaaS hears about it at once.** The SaaS keeps its own copy of the route and only
//!    refreshed it on the daily heartbeat, so a hub that stopped filing with its own certificate got
//!    `409 own_certificate_direct` from the gateway-token door for up to 24 hours and every record
//!    stayed pending. Deleting the certificate had the very same lag. After PATCH and DELETE a
//!    heartbeat carrying the new route leaves immediately.
use axum::body::Body;
use axum::extract::State;
use axum::http::{Request, StatusCode};
use axum::routing::post;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tower::ServiceExt;

const HUB: &str = "hub-switch-door";
const URI: &str = "/api/business/certificate";

type Beats = Arc<Mutex<Vec<Value>>>;

fn config(cloud_base_url: String, tag: &str) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-cert-switch-{tag}-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: HUB.into(),
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

/// A fake SaaS that records every heartbeat body it receives.
async fn fake_cloud() -> (String, Beats) {
    let beats: Beats = Arc::new(Mutex::new(Vec::new()));
    async fn heartbeat(State(beats): State<Beats>, Json(body): Json<Value>) -> Json<Value> {
        beats.lock().unwrap().push(body);
        Json(json!({}))
    }
    let router = Router::new()
        .route("/api/v1/hub/device/heartbeat/", post(heartbeat))
        .with_state(beats.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{addr}"), beats)
}

struct Fixture {
    router: Router,
    admin: String,
    employee: String,
    beats: Beats,
}

async fn fixture(tag: &str, with_certificate: bool) -> Fixture {
    let (cloud, beats) = fake_cloud().await;
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    if with_certificate {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(HUB));
        rt.db()
            .execute(
                "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
                 VALUES (:hub_id, 'own', 'v1:ciphertext', 'v1:ciphertext', '2026-09-15T13:34:39Z', 'hub_user:owner')",
                &p,
            )
            .await
            .unwrap();
    }
    let admin_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee_id = rt.create_user("Caja", "2222", "employee", None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    Fixture {
        router: app(AppState::with_config(rt, config(cloud, tag))),
        admin,
        employee,
        beats,
    }
}

async fn send(router: &Router, method: &str, session: &str, body: Option<Value>) -> (StatusCode, Value) {
    let mut request = Request::builder()
        .method(method)
        .uri(URI)
        .header("x-hub-session", session);
    let body = match body {
        Some(b) => {
            request = request.header("content-type", "application/json");
            Body::from(b.to_string())
        }
        None => Body::empty(),
    };
    let response = router.clone().oneshot(request.body(body).unwrap()).await.unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (status, serde_json::from_slice(&bytes).unwrap_or(Value::Null))
}

/// Waits (bounded) for a heartbeat carrying `route`. The heartbeat is fired in the background, so
/// the door answers without waiting for the SaaS — but it must arrive in seconds, not in 24 h.
async fn heartbeat_with_route(beats: &Beats, route: &str) -> bool {
    for _ in 0..50 {
        if beats
            .lock()
            .unwrap()
            .iter()
            .any(|b| b.get("transmission_route").and_then(Value::as_str) == Some(route))
        {
            return true;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    false
}

#[tokio::test]
async fn an_admin_switches_the_certificate_off_and_it_stays_uploaded() {
    let f = fixture("off", true).await;

    let (status, body) = send(&f.router, "PATCH", &f.admin, Some(json!({ "use_for_transmission": false }))).await;

    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["ok"], json!(true), "{body}");
    assert_eq!(body["data"]["present"], json!(true), "{body}");
    assert_eq!(body["data"]["use_for_transmission"], json!(false), "{body}");
    assert_eq!(body["data"]["transmission_route"], json!("delegated"), "{body}");

    let (status, body) = send(&f.router, "PATCH", &f.admin, Some(json!({ "use_for_transmission": true }))).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["data"]["transmission_route"], json!("own"), "{body}");
}

#[tokio::test]
async fn the_saas_hears_the_new_route_right_after_the_switch() {
    let f = fixture("beat-patch", true).await;

    let (status, body) = send(&f.router, "PATCH", &f.admin, Some(json!({ "use_for_transmission": false }))).await;
    assert_eq!(status, StatusCode::OK, "{body}");

    assert!(
        heartbeat_with_route(&f.beats, "delegated").await,
        "a heartbeat with the new route must leave at once, not on the 24-hour tick: {:?}",
        f.beats.lock().unwrap()
    );
}

#[tokio::test]
async fn the_saas_hears_the_new_route_right_after_deleting_the_certificate() {
    let f = fixture("beat-delete", true).await;

    let (status, body) = send(&f.router, "DELETE", &f.admin, None).await;
    assert_eq!(status, StatusCode::OK, "{body}");

    assert!(
        heartbeat_with_route(&f.beats, "delegated").await,
        "deleting the certificate had the same 24-hour lag: {:?}",
        f.beats.lock().unwrap()
    );
}

#[tokio::test]
async fn the_body_must_say_on_or_off() {
    let f = fixture("invalid", true).await;

    for bad in [json!({}), json!({ "use_for_transmission": "no" })] {
        let (status, body) = send(&f.router, "PATCH", &f.admin, Some(bad.clone())).await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "{bad} → {body}");
        assert_eq!(body["error"]["code"], json!("invalid_field"), "{body}");
        assert_eq!(body["error"]["field"], json!("use_for_transmission"), "{body}");
    }
}

#[tokio::test]
async fn only_an_admin_switches_it() {
    let f = fixture("employee", true).await;

    let (status, body) = send(&f.router, "PATCH", &f.employee, Some(json!({ "use_for_transmission": false }))).await;

    assert!(
        status == StatusCode::FORBIDDEN || status == StatusCode::UNAUTHORIZED,
        "a cashier does not decide how the business files: {status} {body}"
    );
    let (_, after) = send(&f.router, "GET", &f.admin, None).await;
    assert_eq!(after["data"]["transmission_route"], json!("own"), "{after}");
}

#[tokio::test]
async fn switching_on_with_nothing_uploaded_answers_the_domain_code() {
    let f = fixture("absent", false).await;

    let (status, body) = send(&f.router, "PATCH", &f.admin, Some(json!({ "use_for_transmission": true }))).await;

    assert_eq!(status, StatusCode::CONFLICT, "{body}");
    assert_eq!(body["error"]["code"], json!("fiscal.own_certificate_not_uploaded"), "{body}");
}
