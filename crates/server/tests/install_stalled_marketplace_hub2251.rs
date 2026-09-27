//! **«Installing…» has to END when the marketplace stops answering** (hub#2251).
//!
//! hub#1720 and hub#2244 made every failure of «Install» reach the screen with «Retry»: the Cloud
//! down (nothing listening), a refusal (4xx), a crash (5xx). The case none of them covered is the
//! marketplace that ACCEPTS the connection and then says nothing — a stuck proxy, a worker that
//! never answers. The hub called it with a client without any time limit, so `request-install`
//! never returned, the runtime kept its write lock, and the shop stared at «Installing…» forever.
//!
//! The contract fixed here: a silent marketplace ends the install with the stable code
//! `install_cloud_timeout` (a 4xx, so the edge carries the body — hub#1720), in a bounded time,
//! whether it goes silent before answering or in the middle of the zip. The stall limit is
//! shortened for the test through the same builder production uses.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use axum::body::Body;
use axum::http::Request;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{
    app, marketplace_client, AppState, AuthMode, HubConfig, MARKETPLACE_STALL_TIMEOUT,
};
use serde_json::Value;
use tower::ServiceExt; // oneshot

/// The stall limit the tests run with: long enough for a loopback answer, short enough to wait.
const TEST_STALL: Duration = Duration::from_millis(400);

/// If the answer has not come by then, the install is hanging — the very bug.
const HANGING: Duration = Duration::from_secs(10);

fn config(cloud_base_url: String) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-hub2251-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-2251".into(),
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

/// A marketplace that accepts every connection and never writes a byte back. Returns its base URL
/// and how many connections it has taken.
async fn a_marketplace_that_never_answers() -> (String, Arc<AtomicUsize>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let accepted = Arc::new(AtomicUsize::new(0));
    let counter = accepted.clone();
    tokio::spawn(async move {
        let mut held = Vec::new();
        while let Ok((socket, _)) = listener.accept().await {
            counter.fetch_add(1, Ordering::SeqCst);
            held.push(socket); // kept open, never answered
        }
    });
    (format!("http://{addr}"), accepted)
}

/// A marketplace that has no install plan (old Cloud: the hub degrades to the manifest), lists
/// version 1.0.0 and then starts sending the zip — one chunk — and goes silent mid-download.
async fn a_marketplace_that_stalls_mid_download() -> String {
    use axum::routing::{get, post};
    use axum::Router;
    use futures_util::StreamExt;

    let app = Router::new()
        .route(
            "/api/v1/marketplace/install-plan/",
            post(|| async { axum::http::StatusCode::NOT_FOUND }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/versions/",
            get(|| async {
                axum::Json(serde_json::json!([{
                    "version": "1.0.0",
                    "is_active": true,
                    "sha256": "0".repeat(64),
                }]))
            }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/download/",
            get(|| async {
                let first = futures_util::stream::once(async {
                    Ok::<_, std::io::Error>(axum::body::Bytes::from_static(b"PK\x03\x04partial"))
                });
                let body = Body::from_stream(first.chain(futures_util::stream::pending()));
                axum::response::Response::builder()
                    .header("content-type", "application/zip")
                    .header("content-length", "1000000")
                    .body(body)
                    .unwrap()
            }),
        );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("http://{addr}")
}

/// Drives «Install» exactly as the shell does, with the marketplace client built by the production
/// builder at `stall`. Hands back `(status, body, elapsed)`, or fails if it hangs.
async fn install_against(cloud_base_url: String) -> (axum::http::StatusCode, Value, Duration) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-2251");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let mut state = AppState::with_config(rt, config(cloud_base_url));
    state.marketplace_http = marketplace_client(TEST_STALL);
    let router = app(state);

    let started = Instant::now();
    let response = tokio::time::timeout(
        HANGING,
        router.oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/modules/request-install")
                .header("x-hub-session", &session)
                .header("content-type", "application/json")
                .body(Body::from(r#"{"module_id":"sales","version":"1.0.0"}"#))
                .unwrap(),
        ),
    )
    .await
    .expect("request-install is still «Installing…» against a silent marketplace (hub#2251)")
    .unwrap();
    let elapsed = started.elapsed();

    let status = response.status();
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let body: Value = serde_json::from_slice(&bytes)
        .unwrap_or_else(|_| panic!("not JSON: {}", String::from_utf8_lossy(&bytes)));
    (status, body, elapsed)
}

#[tokio::test]
async fn an_install_against_a_marketplace_that_never_answers_ends_with_a_timeout() {
    let (cloud, accepted) = a_marketplace_that_never_answers().await;

    let (status, body, elapsed) = install_against(cloud).await;

    assert!(
        status.is_client_error(),
        "a silent marketplace is an install failure the edge must carry (4xx), got {status}: {body}"
    );
    assert_eq!(body["ok"], Value::Bool(false), "{body}");
    assert_eq!(body["code"], "install_cloud_timeout", "{body}");
    // The plan is the first call: once it has gone silent, asking the same marketplace for the
    // version list only doubles the wait. One silence ends the install.
    assert_eq!(
        accepted.load(Ordering::SeqCst),
        1,
        "after the install plan timed out the hub kept calling the silent marketplace"
    );
    assert!(elapsed < HANGING, "took {elapsed:?}");
}

#[tokio::test]
async fn an_install_whose_zip_stops_arriving_ends_with_a_timeout() {
    let cloud = a_marketplace_that_stalls_mid_download().await;

    let (status, body, _) = install_against(cloud).await;

    assert!(status.is_client_error(), "got {status}: {body}");
    assert_eq!(body["code"], "install_cloud_timeout", "{body}");
}

/// A marketplace address whose packets are dropped (a firewall, a dead route): the connection is
/// never refused, it just never opens. Without a connect limit the OS keeps trying for minutes.
#[tokio::test]
async fn an_install_whose_connection_never_opens_ends() {
    // RFC 5737 TEST-NET-1: documentation-only, routed nowhere, answered by no one.
    let (status, body, _) = install_against("http://192.0.2.1:81".into()).await;

    assert!(status.is_client_error(), "got {status}: {body}");
    assert_eq!(body["code"], "install_cloud_timeout", "{body}");
}

/// «Update» walks the same marketplace: a silent one must end «Updating…» too, and the app keeps
/// running the version it had.
#[tokio::test]
async fn an_update_against_a_marketplace_that_never_answers_ends() {
    let (cloud, _) = a_marketplace_that_never_answers().await;
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "hub-2251");
    rt.ensure_system_tables().await.unwrap();
    let seed = std::env::temp_dir()
        .join(format!("erplora-hub2251-seed-{}", std::process::id()))
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
    let mut state = AppState::with_config(rt, config(cloud));
    state.marketplace_http = marketplace_client(TEST_STALL);
    let runtime = state.runtime.clone();
    let router = app(state);

    let response = tokio::time::timeout(
        HANGING,
        router.oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/modules/notes/update")
                .header("x-hub-session", &session)
                .header("content-type", "application/json")
                .body(Body::from(r#"{"version":"2.0.0"}"#))
                .unwrap(),
        ),
    )
    .await
    .expect("the update is still «Updating…» against a silent marketplace (hub#2251)")
    .unwrap();

    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let body: Value = serde_json::from_slice(&bytes).unwrap();
    // Same answer as any other update that failed with the app still running (hub#516).
    assert_eq!(body["data"]["updated"], Value::Bool(false), "{body}");
    assert_eq!(
        body["warning"]["code"], "module.update_failed_kept_previous",
        "{body}"
    );
    assert_eq!(
        runtime.read().await.registry().module_version("notes"),
        "1.0.0",
        "the app has to keep running the version it had"
    );
}

/// The production hub gives up after [`MARKETPLACE_STALL_TIMEOUT`] of silence, not never: the
/// client `AppState` builds carries the stall limit.
#[tokio::test]
async fn the_production_marketplace_client_has_a_stall_limit() {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-2251");
    let state = AppState::with_config(rt, config("http://127.0.0.1:9".into()));
    let described = format!("{:?}", state.marketplace_http);
    assert!(
        described.contains(&format!("read_timeout: {MARKETPLACE_STALL_TIMEOUT:?}")),
        "the marketplace client has no stall limit: {described}"
    );
    assert!(
        MARKETPLACE_STALL_TIMEOUT <= Duration::from_secs(60),
        "nobody waits more than a minute in front of «Installing…»"
    );
}

/// Every server call into the marketplace goes through `marketplace_http`, not the shared `http`
/// (which has no limit, for the assistant's stream): boot, reconcile, import, and the update and
/// version lists hang the same way when the marketplace goes silent. The functions are the ones
/// in `install.rs` that take the HTTP client first, so a new one is covered the day it appears.
#[test]
fn every_marketplace_call_uses_the_client_with_the_stall_limit() {
    let src = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let install = std::fs::read_to_string(src.join("install.rs")).expect("install.rs");
    let squash = |s: &str| s.split_whitespace().collect::<Vec<_>>().join(" ");
    let install_flat = squash(&install);
    let takes_client: Vec<String> = install_flat
        .split("async fn ")
        .skip(1)
        .filter(|rest| {
            rest.split_once('(')
                .is_some_and(|(_, args)| args.trim_start().starts_with("http: &reqwest::Client"))
        })
        .map(|rest| rest.split('(').next().unwrap_or_default().to_string())
        .collect();
    assert!(
        takes_client.iter().any(|f| f == "install_from_cloud")
            && takes_client.iter().any(|f| f == "update_from_cloud"),
        "the scan no longer finds the marketplace functions: {takes_client:?}"
    );

    let mut calls = 0;
    let mut wrong = Vec::new();
    for entry in std::fs::read_dir(&src).expect("src") {
        let path = entry.expect("entry").path();
        if path.extension().and_then(|e| e.to_str()) != Some("rs") {
            continue;
        }
        let flat = squash(&std::fs::read_to_string(&path).expect("source"));
        for f in &takes_client {
            let needle = format!("install::{f}(");
            for (at, _) in flat.match_indices(&needle) {
                calls += 1;
                let first_arg = flat[at + needle.len()..]
                    .split(',')
                    .next()
                    .unwrap_or_default()
                    .trim();
                if !first_arg.ends_with(".marketplace_http") {
                    let file = path.file_name().unwrap_or_default().to_string_lossy();
                    wrong.push(format!("{file}: install::{f}({first_arg}, …)"));
                }
            }
        }
    }
    assert!(
        calls >= 10,
        "the scan found only {calls} marketplace calls — it no longer sees them"
    );
    assert!(
        wrong.is_empty(),
        "marketplace calls without the stall limit: {wrong:#?}"
    );
}
