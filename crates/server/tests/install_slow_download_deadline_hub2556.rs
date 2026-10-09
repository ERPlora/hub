//! **A download that crawls but never stops still ENDS** (hub#2556).
//!
//! hub#2251 gave every wait on the marketplace a stall limit: 30 s without a byte and the install
//! gives up with `install_cloud_timeout`. A line that keeps sending a little every few seconds
//! never trips it, and the hub had no limit on the whole call: the row stayed in «Installing…»
//! for as long as the trickle lasted, and since hub#2508 every other app change (another install,
//! an update, a template, an uninstall) waited behind it without knowing for how long.
//!
//! The contract fixed here: each call to the marketplace has a ceiling on its WHOLE duration, so
//! a trickling zip ends the install with the stable code `install_cloud_timeout` (and an update
//! with the previous version kept and that same code as its cause), in a bounded time — by the
//! plan path production takes and by the manifest fallback. The marketplace below sends one byte
//! every few milliseconds, far inside the stall limit, forever. Both limits are shortened for the
//! test through the same builder production uses.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use axum::body::Body;
use axum::http::Request;
use axum::Router;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{
    app, marketplace_client, AppState, AuthMode, HubConfig, MARKETPLACE_CALL_TIMEOUT,
    MARKETPLACE_STALL_TIMEOUT,
};
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// Silence the test tolerates: the trickle below never comes close to it.
const TEST_STALL: Duration = Duration::from_millis(800);

/// The ceiling of a whole call in the test.
const TEST_CEILING: Duration = Duration::from_millis(1500);

/// One byte of the zip every this often: well inside [`TEST_STALL`].
const DRIP_EVERY: Duration = Duration::from_millis(40);

/// If the answer has not come by then, the install is hanging on the trickle — the very bug.
const HANGING: Duration = Duration::from_secs(15);

fn config(cloud_base_url: String, tag: &str) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-hub2556-{tag}-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-2556".into(),
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

/// Which way the hub reaches the zip.
#[derive(Clone, Copy, Debug, PartialEq)]
enum Path {
    /// erplora.com's install plan names the app: the path production takes.
    Plan,
    /// No plan (an older erplora.com answers 404): the hub resolves by manifest.
    Manifest,
}

/// A marketplace that publishes `version` and sends its zip one byte at a time, forever. Returns
/// its base URL and the number of bytes it has sent.
async fn a_marketplace_that_trickles(
    path: Path,
    version: &'static str,
) -> (String, Arc<AtomicUsize>) {
    use axum::response::IntoResponse;
    use axum::routing::{get, post};

    let sent = Arc::new(AtomicUsize::new(0));
    let router = Router::new()
        .route(
            "/api/v1/marketplace/install-plan/",
            post(move |axum::Json(asked): axum::Json<Value>| async move {
                if path == Path::Manifest {
                    return axum::http::StatusCode::NOT_FOUND.into_response();
                }
                axum::Json(json!({
                    "requested": asked["module_id"],
                    "plan": [{
                        "module_id": asked["module_id"],
                        "version": version,
                        "sha256": "0".repeat(64),
                        "tier": "free",
                        "entitled": true,
                        "requires_purchase": false,
                        "reason": "requested",
                    }],
                    "already_satisfied": [],
                    "blocked": false,
                    "blocked_on": [],
                }))
                .into_response()
            }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/versions/",
            get(move || async move {
                axum::Json(json!([{
                    "version": version,
                    "is_active": true,
                    "sha256": "0".repeat(64),
                }]))
            }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/download/",
            get({
                let sent = sent.clone();
                move || {
                    let sent = sent.clone();
                    async move {
                        let trickle = futures_util::stream::unfold(sent, |sent| async move {
                            tokio::time::sleep(DRIP_EVERY).await;
                            sent.fetch_add(1, Ordering::SeqCst);
                            Some((
                                Ok::<_, std::io::Error>(axum::body::Bytes::from_static(b"x")),
                                sent,
                            ))
                        });
                        axum::response::Response::builder()
                            .header("content-type", "application/zip")
                            .body(Body::from_stream(trickle))
                            .unwrap()
                    }
                }
            }),
        );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{addr}"), sent)
}

struct Hub {
    router: Router,
    session: String,
    runtime: erplora_server::SharedRuntime,
}

/// A hub with an administrator and, if given, the app `notes` already installed at `notes_version`,
/// whose marketplace client is the production builder at the test's limits.
async fn a_hub(cloud: String, tag: &str, notes_version: Option<&str>) -> Hub {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "hub-2556");
    rt.ensure_system_tables().await.unwrap();
    if let Some(version) = notes_version {
        let seed = std::env::temp_dir()
            .join(format!("erplora-hub2556-seed-{tag}-{}", std::process::id()))
            .join(version);
        let _ = std::fs::remove_dir_all(&seed);
        std::fs::create_dir_all(&seed).unwrap();
        std::fs::write(
            seed.join("module.json"),
            format!(r#"{{"id":"notes","name":"notes","version":"{version}"}}"#),
        )
        .unwrap();
        rt.install_from_dir(&seed).await.expect("seed install");
    }
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let mut state = AppState::with_config(rt, config(cloud, tag));
    state.marketplace_http = marketplace_client(TEST_STALL, TEST_CEILING);
    let runtime = state.runtime.clone();
    Hub {
        router: app(state),
        session,
        runtime,
    }
}

impl Hub {
    /// Sends `body` to `uri` and hands back `(status, body, elapsed)`, or fails if it hangs.
    async fn post(&self, uri: &str, body: Value) -> (axum::http::StatusCode, Value, Duration) {
        let started = Instant::now();
        let response = tokio::time::timeout(
            HANGING,
            self.router.clone().oneshot(
                Request::post(uri)
                    .header("x-hub-session", &self.session)
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            ),
        )
        .await
        .unwrap_or_else(|_| panic!("{uri} is still waiting on a trickling download (hub#2556)"))
        .unwrap();
        let elapsed = started.elapsed();
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let body: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
        (status, body, elapsed)
    }
}

/// The trickle really kept going: the stall limit alone would never have ended this call.
fn assert_it_never_went_silent(sent: &AtomicUsize, elapsed: Duration) {
    let bytes = sent.load(Ordering::SeqCst);
    assert!(
        elapsed > TEST_STALL && bytes as u128 >= TEST_STALL.as_millis() / DRIP_EVERY.as_millis(),
        "the marketplace sent {bytes} bytes in {elapsed:?}: the test must outlast the stall limit"
    );
}

#[tokio::test]
async fn an_install_whose_download_trickles_ends_with_install_cloud_timeout() {
    for path in [Path::Plan, Path::Manifest] {
        let (cloud, sent) = a_marketplace_that_trickles(path, "1.0.0").await;
        let hub = a_hub(cloud, &format!("install-{path:?}"), None).await;

        let (status, body, elapsed) = hub
            .post(
                "/api/modules/request-install",
                json!({ "module_id": "notes", "version": "1.0.0" }),
            )
            .await;

        assert_eq!(body["code"], "install_cloud_timeout", "{path:?}: {body}");
        assert!(
            status.is_client_error(),
            "{path:?}: a 4xx carries the body to the screen, got {status}"
        );
        assert!(
            elapsed < TEST_CEILING * 3,
            "{path:?}: the ceiling ends the call, took {elapsed:?}"
        );
        assert_it_never_went_silent(&sent, elapsed);
        assert!(
            !hub.runtime.read().await.registry().is_installed("notes"),
            "{path:?}: nothing is installed from half a zip"
        );
    }
}

#[tokio::test]
async fn an_update_whose_download_trickles_keeps_the_previous_version_and_says_why() {
    for path in [Path::Plan, Path::Manifest] {
        let (cloud, sent) = a_marketplace_that_trickles(path, "2.0.0").await;
        let hub = a_hub(cloud, &format!("update-{path:?}"), Some("1.0.0")).await;

        let (status, body, elapsed) = hub.post("/api/modules/notes/update", json!({})).await;

        assert!(
            status.is_success(),
            "{path:?}: the app keeps working, got {status}: {body}"
        );
        assert_eq!(
            body["warning"]["code"], "module.update_failed_kept_previous",
            "{path:?}: {body}"
        );
        assert_eq!(
            body["warning"]["cause"], "install_cloud_timeout",
            "{path:?}: the screen needs to know WHY to say «try again»: {body}"
        );
        assert_eq!(body["data"]["updated"], false, "{path:?}: {body}");
        assert!(
            elapsed < TEST_CEILING * 4,
            "{path:?}: the ceiling ends the call, took {elapsed:?}"
        );
        assert_it_never_went_silent(&sent, elapsed);
        assert_eq!(
            hub.runtime.read().await.registry().module_version("notes"),
            "1.0.0",
            "{path:?}: a failed update keeps the version the app had"
        );
    }
}

/// The other app changes wait for the trickling one only up to the ceiling (hub#2508 queues them).
#[tokio::test]
async fn the_next_app_change_waits_only_up_to_the_ceiling() {
    let (cloud, sent) = a_marketplace_that_trickles(Path::Plan, "1.0.0").await;
    let hub = Arc::new(a_hub(cloud, "queue", Some("1.0.0")).await);

    let installing = {
        let hub = hub.clone();
        tokio::spawn(async move {
            hub.post(
                "/api/modules/request-install",
                json!({ "module_id": "other", "version": "1.0.0" }),
            )
            .await
        })
    };
    tokio::time::timeout(HANGING, async {
        while sent.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("the install never started downloading");

    let (status, body, elapsed) = hub.post("/api/modules/notes/uninstall", json!({})).await;
    assert!(
        status.is_success(),
        "the uninstall goes through after the install gives up: {status} {body}"
    );
    assert!(
        elapsed < TEST_CEILING * 3,
        "the uninstall waited {elapsed:?} behind a trickle"
    );
    let (_, first, _) = installing.await.unwrap();
    assert_eq!(first["code"], "install_cloud_timeout", "{first}");
}

/// The production ceiling: long enough for the biggest published package (~3 MB zipped in
/// 2026-10) on a poor line (~10 KB/s), short enough that the next app change is not left waiting
/// for the better part of an hour. Silence still ends a call sooner, at the stall limit. And it is
/// the one the hub really builds its marketplace client with.
#[tokio::test]
async fn the_production_marketplace_client_has_the_ceiling() {
    assert!(MARKETPLACE_CALL_TIMEOUT >= Duration::from_secs(5 * 60));
    assert!(MARKETPLACE_CALL_TIMEOUT <= Duration::from_secs(10 * 60));
    assert!(MARKETPLACE_CALL_TIMEOUT > MARKETPLACE_STALL_TIMEOUT);

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-2556");
    let state = AppState::with_config(rt, config("http://127.0.0.1:9".into(), "production"));
    let described = format!("{:?}", state.marketplace_http);
    assert!(
        described.contains(&format!("TotalTimeout: {MARKETPLACE_CALL_TIMEOUT:?}")),
        "the marketplace client has no ceiling on a whole call: {described}"
    );
}
