//! **While an app installs or updates, the till keeps charging** (hub#2508).
//!
//! `request-install` and `update` took the runtime's write lock and kept it for the whole install:
//! asking erplora.com for the plan and the versions, downloading the zip, verifying it, and only at
//! the end registering it. Every other request of the hub — a sale, the menu, `/readyz` — waits on
//! that lock, so for as long as the download lasted the shop could not charge on any device.
//!
//! The contract fixed here: the hub keeps answering while an install or an update is still talking
//! to the marketplace. The lock is taken only for the step that changes the runtime (registering
//! the verified package). The marketplace below hands out the zip's first bytes and then holds the
//! rest until the test releases it, so the install is provably in the middle of its download when
//! the other requests arrive.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::Router;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, marketplace_client, AppState, AuthMode, HubConfig};
use serde_json::Value;
use tokio::sync::Notify;
use tower::ServiceExt; // oneshot

/// A request that needs the runtime has this long to answer while an install is downloading.
/// Loopback answers in milliseconds; waiting for the install to finish is the bug.
const MUST_ANSWER_WITHIN: Duration = Duration::from_secs(3);

/// The marketplace's own stall limit for the test: far above the time the test holds the zip.
const STALL: Duration = Duration::from_secs(30);

fn config(cloud_base_url: String, tag: &str) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-hub2508-{tag}-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-2508".into(),
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

/// A marketplace with no install plan (the hub resolves by manifest), that publishes `version` and
/// whose download sends a first chunk, flags `downloading`, and waits for `release` before ending.
/// The bytes are not a real zip, so once released the install fails its checksum: what is under
/// test is what the REST of the hub does meanwhile, not the install's outcome.
async fn a_marketplace_that_holds_the_zip(
    version: &'static str,
    downloading: Arc<AtomicBool>,
    release: Arc<Notify>,
) -> String {
    use axum::routing::{get, post};
    use futures_util::StreamExt;

    let app = Router::new()
        .route(
            "/api/v1/marketplace/install-plan/",
            post(|| async { StatusCode::NOT_FOUND }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/versions/",
            get(move || async move {
                axum::Json(serde_json::json!([{
                    "version": version,
                    "is_active": true,
                    "sha256": "0".repeat(64),
                }]))
            }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/download/",
            get(move || {
                let downloading = downloading.clone();
                let release = release.clone();
                async move {
                    let first = futures_util::stream::once(async {
                        Ok::<_, std::io::Error>(axum::body::Bytes::from_static(b"PK\x03\x04first"))
                    });
                    let rest = futures_util::stream::once(async move {
                        downloading.store(true, Ordering::SeqCst);
                        release.notified().await;
                        Ok::<_, std::io::Error>(axum::body::Bytes::from_static(b"rest"))
                    });
                    axum::response::Response::builder()
                        .header("content-type", "application/zip")
                        .body(Body::from_stream(first.chain(rest)))
                        .unwrap()
                }
            }),
        );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("http://{addr}")
}

async fn wait_until(flag: &AtomicBool) {
    tokio::time::timeout(Duration::from_secs(10), async {
        while !flag.load(Ordering::SeqCst) {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("the install never reached the download");
}

/// What the till depends on, asked while the install is downloading: readiness (Swarm and the
/// edge) and the list of apps (every screen). Both read the runtime.
async fn the_hub_still_answers(router: &Router, session: &str, gesture: &str) {
    let ready = tokio::time::timeout(
        MUST_ANSWER_WITHIN,
        router
            .clone()
            .oneshot(Request::get("/readyz").body(Body::empty()).unwrap()),
    )
    .await
    .unwrap_or_else(|_| panic!("/readyz waited for the {gesture} to finish (hub#2508)"))
    .unwrap();
    assert_ne!(ready.status(), StatusCode::REQUEST_TIMEOUT);

    let apps = tokio::time::timeout(
        MUST_ANSWER_WITHIN,
        router.clone().oneshot(
            Request::get("/api/modules")
                .header("x-hub-session", session)
                .body(Body::empty())
                .unwrap(),
        ),
    )
    .await
    .unwrap_or_else(|_| panic!("the list of apps waited for the {gesture} to finish (hub#2508)"))
    .unwrap();
    assert_eq!(apps.status(), StatusCode::OK);
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes)
        .unwrap_or_else(|_| panic!("not JSON: {}", String::from_utf8_lossy(&bytes)))
}

#[tokio::test]
async fn the_hub_keeps_answering_while_an_app_installs() {
    let downloading = Arc::new(AtomicBool::new(false));
    let release = Arc::new(Notify::new());
    let cloud = a_marketplace_that_holds_the_zip("1.0.0", downloading.clone(), release.clone()).await;

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-2508");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let mut state = AppState::with_config(rt, config(cloud, "install"));
    state.marketplace_http = marketplace_client(STALL);
    let router = app(state);

    let install = tokio::spawn({
        let router = router.clone();
        let session = session.clone();
        async move {
            router
                .oneshot(
                    Request::post("/api/modules/request-install")
                        .header("x-hub-session", &session)
                        .header("content-type", "application/json")
                        .body(Body::from(r#"{"module_id":"sales","version":"1.0.0"}"#))
                        .unwrap(),
                )
                .await
                .unwrap()
        }
    });
    wait_until(&downloading).await;

    the_hub_still_answers(&router, &session, "install").await;

    release.notify_one();
    let response = tokio::time::timeout(Duration::from_secs(10), install)
        .await
        .expect("the install never ended once the zip arrived")
        .unwrap();
    // The bytes are not the advertised zip: the install fails its checksum, as it must.
    let body = body_json(response).await;
    assert_eq!(body["ok"], Value::Bool(false), "{body}");
}

#[tokio::test]
async fn the_hub_keeps_answering_while_an_app_updates() {
    let downloading = Arc::new(AtomicBool::new(false));
    let release = Arc::new(Notify::new());
    let cloud = a_marketplace_that_holds_the_zip("2.0.0", downloading.clone(), release.clone()).await;

    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "hub-2508");
    rt.ensure_system_tables().await.unwrap();
    let seed = std::env::temp_dir()
        .join(format!("erplora-hub2508-seed-{}", std::process::id()))
        .join("1.0.0");
    let _ = std::fs::remove_dir_all(&seed);
    std::fs::create_dir_all(&seed).unwrap();
    std::fs::write(
        seed.join("module.json"),
        r#"{"id":"notes","name":"notes","version":"1.0.0"}"#,
    )
    .unwrap();
    rt.install_from_dir(&seed).await.expect("seed install");
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let mut state = AppState::with_config(rt, config(cloud, "update"));
    state.marketplace_http = marketplace_client(STALL);
    let runtime = state.runtime.clone();
    let router = app(state);

    let update = tokio::spawn({
        let router = router.clone();
        let session = session.clone();
        async move {
            router
                .oneshot(
                    Request::post("/api/modules/notes/update")
                        .header("x-hub-session", &session)
                        .header("content-type", "application/json")
                        .body(Body::from("{}"))
                        .unwrap(),
                )
                .await
                .unwrap()
        }
    });
    wait_until(&downloading).await;

    the_hub_still_answers(&router, &session, "update").await;

    release.notify_one();
    let response = tokio::time::timeout(Duration::from_secs(10), update)
        .await
        .expect("the update never ended once the zip arrived")
        .unwrap();
    let body = body_json(response).await;
    assert_eq!(
        body["warning"]["code"], "module.update_failed_kept_previous",
        "{body}"
    );
    assert_eq!(
        runtime.read().await.registry().module_version("notes"),
        "1.0.0",
        "a failed update keeps the version the app had"
    );
}
