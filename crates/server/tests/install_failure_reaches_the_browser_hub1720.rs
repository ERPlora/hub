//! **A failed install has to be READABLE by the person in front of the screen** (hub#1720).
//!
//! The reason already existed: `install_error_response` builds an honest body with the stable
//! `code` of hub#139 (`install_cloud_unavailable`, `install_download_failed`,
//! `install_missing_sha256`…) and the shell already translates it
//! (`apps/web/src/lib/module-failure-message.ts`). What it did NOT survive was the **status** it
//! travelled in: a `502`.
//!
//! The hub is the ORIGIN, not a gateway. A `502` minted by the origin is indistinguishable from a
//! `502` minted by the edge in front of it, so the edge answers with its own `error code: 502`
//! page and REPLACES the body. Measured in PRE on 2026-09-09: the motive was logged in the
//! container and never reached the browser — the person could not tell «my credential is missing»
//! from «that module does not exist» from «the Cloud is down». All three looked the same: an
//! install that failed saying nothing.
//!
//! So the contract this file fixes is: **no failure of the install/update pipeline leaves the hub
//! as a 5xx**. A 4xx carries its body through any proxy untouched, and `res.ok === false` keeps
//! the shell's existing error path working unchanged.
//!
//! 🔴 This is a PATTERN, not a point: the companion guard in `module_api.rs`
//! (`no_install_failure_is_reported_as_a_server_error`) walks EVERY variant of `InstallError`, so
//! a variant added tomorrow cannot go back to 502 either.

use axum::body::Body;
use axum::http::Request;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::Value;
use tower::ServiceExt; // oneshot

fn config(cloud_base_url: String) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-hub1720-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-1720".into(),
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

/// An address on the loopback with **nothing listening**: every call to it fails at connect, which
/// is the cheap, deterministic stand-in for «the Cloud did not answer» — the very case the person
/// in PRE hit. Same helper as `cloud_errors_never_name_the_control_plane.rs`.
async fn a_cloud_that_is_not_listening() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    format!("http://{address}")
}

/// The marketplace's «Install» button, driven exactly as the shell drives it, against a Cloud that
/// is down: the answer has to be one the browser can still read.
#[tokio::test]
async fn an_install_that_fails_because_the_cloud_is_down_still_says_why() {
    let cloud_base_url = a_cloud_that_is_not_listening().await;
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-1720");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let router = app(AppState::with_config(rt, config(cloud_base_url)));

    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/modules/request-install")
                .header("x-hub-session", &session)
                .header("content-type", "application/json")
                .body(Body::from(r#"{"module_id":"sales","version":"1.0.0"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    let status = response.status();
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let text = String::from_utf8_lossy(&bytes).to_string();

    // 🔴 The regression itself: a 5xx is a body the edge is free to replace with its own page, and
    // it does. Whatever the hub wants to say has to travel in a status that arrives.
    assert!(
        !status.is_server_error(),
        "an install failure answered {status}: the edge replaces the body of a 5xx with its own \
         page, so the motive never reaches the browser — body was {text}"
    );
    assert!(
        status.is_client_error(),
        "a failed install still has to be an ERROR for the shell (`res.ok === false`), got {status}"
    );

    // And the motive itself, which is the whole point of the status change: the stable code the
    // shell translates (ADR-0055 — the test asserts the CODE, never the prose).
    let body: Value = serde_json::from_str(&text).expect("the answer is JSON, not an edge page");
    assert_eq!(body["ok"], Value::Bool(false), "body was {text}");
    assert_eq!(
        body["code"], "install_cloud_unavailable",
        "the person has to be able to tell «the Cloud is down» from the other failures: {text}"
    );
}

/// A Cloud that answers **every** marketplace call with one status and nothing else. It stands in
/// for the two refusals the person cannot act on today: the credential this hub presents is not
/// accepted (`401`/`403`), and the module is not in the catalogue this hub can see (`404`).
async fn a_cloud_that_refuses_with(status: u16) -> String {
    use axum::routing::any;
    use axum::Router;

    let app = Router::new().fallback(any(move || async move {
        axum::http::StatusCode::from_u16(status).unwrap()
    }));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("http://{addr}")
}

/// Drives «Install» once and hands back `(status, body)`.
async fn install_against(cloud_base_url: String) -> (axum::http::StatusCode, Value) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-1720");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let router = app(AppState::with_config(rt, config(cloud_base_url)));

    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/modules/request-install")
                .header("x-hub-session", &session)
                .header("content-type", "application/json")
                .body(Body::from(r#"{"module_id":"sales","version":"1.0.0"}"#))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let text = String::from_utf8_lossy(&bytes).to_string();
    let body: Value =
        serde_json::from_str(&text).unwrap_or_else(|_| panic!("the answer is JSON: {text}"));
    (status, body)
}

/// **The three causes the person has to be able to tell apart** (hub#1720).
///
/// The status was only half of it. The other half is that all three answered the SAME code:
/// `send_text` ran `error_for_status()` through `cloud_unreachable`, so a Cloud that ANSWERED —
/// refusing the credential, or saying that module is not in this hub's catalogue — was reported as
/// a Cloud that never answered. The screen said «erplora.com is unreachable, try again in a few
/// minutes» to somebody whose key was rejected: unactionable, and false. Retrying forever was the
/// only thing it suggested.
#[tokio::test]
async fn a_cloud_that_refuses_the_credential_is_not_a_cloud_that_is_down() {
    let (status, body) = install_against(a_cloud_that_refuses_with(401).await).await;

    assert!(
        !status.is_server_error(),
        "answered {status}: the edge replaces the body of a 5xx — body was {body}"
    );
    assert_ne!(
        body["code"], "install_cloud_unavailable",
        "a Cloud that ANSWERED 401 is not a Cloud that is down: telling the shop to «try again in \
         a few minutes» hides a credential it has to fix — {body}"
    );
    assert_eq!(body["code"], "install_cloud_denied", "{body}");
    assert_eq!(body["ok"], Value::Bool(false), "{body}");
}

/// The same, for the module the catalogue does not have: it is a `404`, and it says so.
#[tokio::test]
async fn a_module_the_catalogue_does_not_have_says_so_instead_of_blaming_the_network() {
    let (status, body) = install_against(a_cloud_that_refuses_with(404).await).await;

    assert!(
        !status.is_server_error(),
        "answered {status}: the edge replaces the body of a 5xx — body was {body}"
    );
    assert_eq!(
        status,
        axum::http::StatusCode::NOT_FOUND,
        "«that app is not in your catalogue» is a 404, not a gateway failure: {body}"
    );
    assert_eq!(body["code"], "install_not_in_catalog", "{body}");
    assert_eq!(body["ok"], Value::Bool(false), "{body}");
}
