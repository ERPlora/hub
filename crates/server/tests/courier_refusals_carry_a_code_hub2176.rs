//! **Every refusal of the boot courier carries a stable `code`** (hub#2176).
//!
//! When the native shell's courier redemption fails, the shell reports the failure through the
//! client error pipe (hub#2152). It deliberately does NOT report the `error` prose — the code is a
//! credential and the prose is not ours to trust — so the only thing that tells the team WHY the
//! courier failed is the `code` next to it. Before this, `POST /api/auth/courier` answered all five
//! refusals with prose alone, and every report read `courier exchange failed: RuntimeError`.
//!
//! Each branch is driven for real: a malformed code, a hub with no machine credential, a SaaS that
//! does not answer, a SaaS that refuses the code (`400`), a SaaS that refuses the hub itself
//! (`401`), and a SaaS that answers `2xx` with something that is not a grant. Asserts on the code
//! and the status, never on the prose (ADR-0055).
use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::response::IntoResponse;
use axum::routing::post;
use axum::Router;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig, DEV_HUB_ID};
use serde_json::Value;
use tower::ServiceExt;

const COURIER_PATH: &str = "/api/v1/hub/device/session-courier/";

fn config(cloud_base_url: String, machine_token: Option<&str>) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-courier-code-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-courier-code".into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: machine_token.map(str::to_string),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

/// A SaaS whose courier redemption always answers `status` with `body`.
async fn a_saas_answering(status: StatusCode, body: &'static str) -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let router = Router::new().route(
        COURIER_PATH,
        post(move || async move {
            (status, [("content-type", "application/json")], body).into_response()
        }),
    );
    tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });
    format!("http://{address}")
}

/// An address on the loopback with nothing listening: the cheap stand-in for «the SaaS is down».
async fn a_saas_that_is_not_listening() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    format!("http://{address}")
}

async fn redeem(
    cloud_base_url: String,
    machine_token: Option<&str>,
    body: &str,
) -> (StatusCode, Value) {
    redeem_on(config(cloud_base_url, machine_token), body).await
}

async fn redeem_on(config: HubConfig, body: &str) -> (StatusCode, Value) {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), &config.hub_id);
    rt.ensure_system_tables().await.unwrap();
    let router = app(AppState::with_config(rt, config));
    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/courier")
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let json: Value = serde_json::from_slice(&bytes).unwrap_or_else(|_| {
        panic!(
            "the courier door answers JSON: {}",
            String::from_utf8_lossy(&bytes)
        )
    });
    (status, json)
}

fn code_of(json: &Value) -> &str {
    json.get("code")
        .and_then(Value::as_str)
        .unwrap_or_else(|| panic!("a courier refusal must carry a stable `code`: {json}"))
}

#[tokio::test]
async fn a_malformed_courier_code_is_refused_with_courier_invalid() {
    let (status, json) = redeem(
        a_saas_that_is_not_listening().await,
        Some("machine-secret"),
        r#"{"code":"   "}"#,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "{json}");
    assert_eq!(code_of(&json), "courier_invalid");
}

/// On a real install, a hub without its machine credential never reaches the courier: the
/// registration barrier answers first, with its own nested code, which the shell already reads.
#[tokio::test]
async fn an_unregistered_hub_is_refused_by_the_registration_barrier_with_its_code() {
    let (status, json) = redeem(
        a_saas_that_is_not_listening().await,
        None,
        r#"{"code":"abc"}"#,
    )
    .await;
    assert_eq!(status, StatusCode::PRECONDITION_REQUIRED, "{json}");
    assert_eq!(
        json.pointer("/error/code").and_then(Value::as_str),
        Some("machine_registration_required"),
        "{json}"
    );
}

/// The development hub passes the registration barrier, so the courier's own «no machine
/// credential» branch is the one that answers there.
#[tokio::test]
async fn the_dev_hub_without_a_machine_credential_is_refused_with_hub_not_enrolled() {
    let mut dev = config(a_saas_that_is_not_listening().await, None);
    dev.hub_id = DEV_HUB_ID.into();
    dev.auth_mode = AuthMode::Dev;
    let (status, json) = redeem_on(dev, r#"{"code":"abc"}"#).await;
    assert_eq!(status, StatusCode::FAILED_DEPENDENCY, "{json}");
    assert_eq!(code_of(&json), "hub_not_enrolled");
}

#[tokio::test]
async fn a_saas_that_does_not_answer_is_reported_as_cloud_unreachable() {
    let (status, json) = redeem(
        a_saas_that_is_not_listening().await,
        Some("machine-secret"),
        r#"{"code":"abc"}"#,
    )
    .await;
    assert_eq!(status, StatusCode::FAILED_DEPENDENCY, "{json}");
    assert_eq!(code_of(&json), "cloud_unreachable");
}

#[tokio::test]
async fn a_code_the_saas_will_not_redeem_is_refused_with_courier_rejected() {
    let saas = a_saas_answering(
        StatusCode::BAD_REQUEST,
        r#"{"detail":"invalid or expired code"}"#,
    )
    .await;
    let (status, json) = redeem(saas, Some("machine-secret"), r#"{"code":"abc"}"#).await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "{json}");
    assert_eq!(code_of(&json), "courier_rejected");
}

/// A `401`/`403`/`5xx` from the SaaS is not about the code the person carried: the SaaS refused
/// the HUB (its machine credential) or failed. Naming it `courier_rejected` would send whoever
/// reads the report after the wrong culprit.
#[tokio::test]
async fn a_saas_that_refuses_the_hub_itself_is_reported_as_cloud_rejected() {
    let saas = a_saas_answering(StatusCode::UNAUTHORIZED, r#"{"detail":"invalid token"}"#).await;
    let (status, json) = redeem(saas, Some("machine-secret"), r#"{"code":"abc"}"#).await;
    assert_eq!(status, StatusCode::FAILED_DEPENDENCY, "{json}");
    assert_eq!(code_of(&json), "cloud_rejected");
}

#[tokio::test]
async fn a_saas_answer_that_is_not_a_grant_is_reported_as_cloud_unreadable() {
    let saas = a_saas_answering(StatusCode::OK, r#"{"access":"","refresh":""}"#).await;
    let (status, json) = redeem(saas, Some("machine-secret"), r#"{"code":"abc"}"#).await;
    assert_eq!(status, StatusCode::FAILED_DEPENDENCY, "{json}");
    assert_eq!(code_of(&json), "cloud_unreadable");
}
