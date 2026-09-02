//! `GET /api/app/release` — the one thing the till cannot find out on its own (hub#400).
//!
//! The web app is served under `connect-src 'self' ipc:`, so it cannot ask erplora.com anything
//! directly: the CSP kills the request, and it kills it **silently**, which from the page looks
//! exactly like "there is no new version". So the runtime asks on its behalf, from the server side
//! where no CSP applies and where the Cloud address is already configured.
//!
//! Two properties are load-bearing and both are asserted here: the question carries **no
//! credential** (the answer must reach a hub that is in demo, unenrolled or asleep — otherwise the
//! tills that most need an update are the ones that never hear about it), and a Cloud that does not
//! answer produces an **error**, never a version. Inventing one would send a till at an installer
//! that does not exist; answering "up to date" would be worse still, because it is a lie the user
//! believes.

use axum::body::Body;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::json;
use tower::ServiceExt;

const RELEASE_URI: &str = "/api/app/release";

fn config(hub_id: &str, cloud_base_url: String, tag: &str) -> HubConfig {
    let temp =
        std::env::temp_dir().join(format!("erplora-app-release-{tag}-{}", std::process::id()));
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

/// A router with one signed-in session, pointed at `cloud_base_url`.
async fn fixture(cloud_base_url: String, tag: &str) -> (Router, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-release");
    rt.ensure_system_tables().await.unwrap();
    let user = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let session = rt.create_session(&user, 3600, None).await.unwrap();
    (
        app(AppState::with_config(
            rt,
            config("hub-release", cloud_base_url, tag),
        )),
        session,
    )
}

fn signed_in(session: &str) -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri(RELEASE_URI)
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap()
}

async fn body_json(response: axum::response::Response) -> serde_json::Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(serde_json::Value::Null)
}

#[tokio::test]
async fn the_published_version_reaches_the_till_and_carries_no_credential() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let mock_cloud = Router::new().route(
        "/api/v1/app/release/",
        get(|headers: HeaderMap| async move {
            // A credential here would 401 exactly the hubs that need this most: demo, unenrolled,
            // or woken from sleep with a stale token. The version of a public download is not a
            // secret — it is written on the store listing.
            if headers.contains_key("authorization")
                || headers.contains_key("x-hub-id")
                || headers.contains_key("x-hub-token")
            {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({ "error": "the release question carried credentials" })),
                );
            }
            (StatusCode::OK, Json(json!({ "version": "1.4.0" })))
        }),
    );
    let cloud = tokio::spawn(async move { axum::serve(listener, mock_cloud).await.unwrap() });

    let (router, session) = fixture(format!("http://{address}"), "ok").await;
    let response = router.oneshot(signed_in(&session)).await.unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(body_json(response).await["version"], "1.4.0");
    cloud.abort();
}

#[tokio::test]
async fn a_cloud_that_does_not_answer_yields_an_error_and_never_a_version() {
    // Nothing is listening on that address: the morning the internet is down in the bar.
    let (router, session) = fixture("http://127.0.0.1:1/".into(), "down").await;

    let response = router.oneshot(signed_in(&session)).await.unwrap();

    assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    // The page turns anything that is not a version into `unknown` — silence. What it must never
    // receive is a number the runtime made up, nor a body that reads as "you are up to date".
    assert!(body_json(response).await.get("version").is_none());
}

#[tokio::test]
async fn an_error_from_the_cloud_is_passed_on_as_an_error() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let mock_cloud = Router::new().route(
        "/api/v1/app/release/",
        get(|| async {
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({ "detail": "nope" })),
            )
        }),
    );
    let cloud = tokio::spawn(async move { axum::serve(listener, mock_cloud).await.unwrap() });

    let (router, session) = fixture(format!("http://{address}"), "5xx").await;
    let response = router.oneshot(signed_in(&session)).await.unwrap();

    assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    cloud.abort();
}

#[tokio::test]
async fn nobody_asks_the_runtime_anything_without_a_session() {
    let (router, _session) = fixture("http://127.0.0.1:1/".into(), "anon").await;

    let response = router
        .oneshot(
            Request::builder()
                .method("GET")
                .uri(RELEASE_URI)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}
