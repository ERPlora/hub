//! **While an app installs or updates, the till keeps charging** (hub#2508).
//!
//! `request-install` and `update` took the runtime's write lock and kept it for the whole install:
//! asking erplora.com for the plan and the versions, downloading the zip, verifying it, and only at
//! the end registering it. Every other request of the hub — a sale, the menu, `/readyz` — waits on
//! that lock, so for as long as the download lasted the shop could not charge on any device.
//!
//! The contract fixed here: while an install, an update or a template import is waiting on the
//! marketplace, the hub keeps answering and nobody holds the runtime — a writer (an app switched
//! on, a session adopting the hub id) gets it at once. The lock is taken only for the step that
//! changes the runtime (registering the verified package). The marketplace below holds one of its
//! answers (the plan, the versions or the zip) until the test releases it, so the install is
//! provably waiting on erplora.com when the other requests arrive.
//!
//! And since the write lock no longer serializes them, installs, updates, template imports and
//! uninstalls wait for each other instead.

use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::Router;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, marketplace_client, AppState, AuthMode, HubConfig, SharedRuntime};
use serde_json::{json, Value};
use tokio::sync::Notify;
use tower::ServiceExt; // oneshot

/// A request that needs the runtime has this long to answer while an install waits on erplora.com.
/// Loopback answers in milliseconds; waiting for the install to finish is the bug.
const MUST_ANSWER_WITHIN: Duration = Duration::from_secs(3);

/// The marketplace's own stall limit for the test: far above the time the test holds an answer.
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

/// Which answer of the marketplace waits for the test.
#[derive(Clone, Copy, PartialEq)]
enum Hold {
    /// The install plan (it then says 404, so the hub resolves by manifest).
    Plan,
    /// The list of versions: the resolver of an update, and the install's version lookup.
    Versions,
    /// The zip, after a first chunk.
    Download,
}

/// What the test sees of the marketplace: `held` flips when a held answer starts waiting,
/// `release` lets one go, and `downloads` counts the downloads that started.
#[derive(Clone, Default)]
struct Marketplace {
    held: Arc<AtomicBool>,
    release: Arc<Notify>,
    downloads: Arc<AtomicUsize>,
}

impl Marketplace {
    async fn wait_until_held(&self) {
        tokio::time::timeout(Duration::from_secs(10), async {
            while !self.held.load(Ordering::SeqCst) {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("the install never reached the marketplace answer the test holds");
    }

    /// Let the held answer go and get ready to catch the next one.
    fn let_go(&self) {
        self.held.store(false, Ordering::SeqCst);
        self.release.notify_one();
    }
}

/// A marketplace with no install plan that publishes `version` and holds the answer `hold`. The
/// zip is not a real one, so the install fails its checksum: what is under test is what the REST
/// of the hub does meanwhile, not the install's outcome.
async fn a_marketplace_that_holds(hold: Hold, version: &'static str) -> (String, Marketplace) {
    use axum::routing::{get, post};
    use futures_util::StreamExt;

    let market = Marketplace::default();
    let wait = move |stage: Hold, market: Marketplace| async move {
        if stage == hold {
            market.held.store(true, Ordering::SeqCst);
            market.release.notified().await;
        }
    };
    let router = Router::new()
        .route(
            "/api/v1/marketplace/install-plan/",
            post({
                let market = market.clone();
                move || async move {
                    wait(Hold::Plan, market).await;
                    StatusCode::NOT_FOUND
                }
            }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/versions/",
            get({
                let market = market.clone();
                move || async move {
                    wait(Hold::Versions, market).await;
                    axum::Json(json!([{
                        "version": version,
                        "is_active": true,
                        "sha256": "0".repeat(64),
                    }]))
                }
            }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/download/",
            get({
                let market = market.clone();
                move || {
                    let market = market.clone();
                    market.downloads.fetch_add(1, Ordering::SeqCst);
                    async move {
                        let first = futures_util::stream::once(async {
                            Ok::<_, std::io::Error>(axum::body::Bytes::from_static(
                                b"PK\x03\x04first",
                            ))
                        });
                        let rest = futures_util::stream::once(async move {
                            wait(Hold::Download, market).await;
                            Ok::<_, std::io::Error>(axum::body::Bytes::from_static(b"rest"))
                        });
                        axum::response::Response::builder()
                            .header("content-type", "application/zip")
                            .body(Body::from_stream(first.chain(rest)))
                            .unwrap()
                    }
                }
            }),
        );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{addr}"), market)
}

struct Hub {
    router: Router,
    session: String,
    runtime: SharedRuntime,
}

/// A hub with an administrator and, if given, the app `notes` already installed at `notes_version`.
async fn a_hub(cloud: String, tag: &str, notes_version: Option<&str>) -> Hub {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "hub-2508");
    rt.ensure_system_tables().await.unwrap();
    if let Some(version) = notes_version {
        let seed = std::env::temp_dir()
            .join(format!("erplora-hub2508-seed-{tag}-{}", std::process::id()))
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
    state.marketplace_http = marketplace_client(STALL);
    let runtime = state.runtime.clone();
    Hub {
        router: app(state),
        session,
        runtime,
    }
}

impl Hub {
    fn post(&self, uri: &str, body: String) -> Request<Body> {
        Request::post(uri)
            .header("x-hub-session", &self.session)
            .header("content-type", "application/json")
            .body(Body::from(body))
            .unwrap()
    }

    fn install(&self, module_id: &str) -> Request<Body> {
        self.post(
            "/api/modules/request-install",
            json!({ "module_id": module_id, "version": "1.0.0" }).to_string(),
        )
    }

    fn update(&self, module_id: &str) -> Request<Body> {
        self.post(&format!("/api/modules/{module_id}/update"), "{}".into())
    }

    fn uninstall(&self, module_id: &str) -> Request<Body> {
        self.post(&format!("/api/modules/{module_id}/uninstall"), "{}".into())
    }

    /// Upload a template that installs `module_id`, and the request that imports it.
    async fn template_import(&self, module_id: &str) -> Request<Body> {
        let manifest = json!({
            "schema_version": 1,
            "name": "salon",
            "locale": "es",
            "hub": { "name": "Demo", "country": "ES", "currency": "EUR" },
            "created_at": "2026-10-06T00:00:00Z",
            "modules": [{ "id": module_id, "version": "1.0.0", "with_data": false }],
            "sections": [],
            "sha256": {},
        })
        .to_string();
        let mut zip_bytes = Vec::new();
        {
            let mut zip = zip::ZipWriter::new(std::io::Cursor::new(&mut zip_bytes));
            let options: zip::write::FileOptions<()> = zip::write::FileOptions::default();
            zip.start_file("manifest.json", options).unwrap();
            std::io::Write::write_all(&mut zip, manifest.as_bytes()).unwrap();
            zip.finish().unwrap();
        }
        let inspected = self
            .router
            .clone()
            .oneshot(
                Request::post("/api/hub/import/inspect")
                    .header("x-hub-session", &self.session)
                    .header("content-type", "application/octet-stream")
                    .body(Body::from(zip_bytes))
                    .unwrap(),
            )
            .await
            .unwrap();
        let inspected = body_json(inspected).await;
        let upload_id = inspected["upload_id"]
            .as_str()
            .unwrap_or_else(|| panic!("inspect gave no upload_id: {inspected}"));
        self.post(
            "/api/hub/import",
            json!({ "upload_id": upload_id, "selection": {} }).to_string(),
        )
    }

    fn send(&self, request: Request<Body>) -> tokio::task::JoinHandle<axum::response::Response> {
        let router = self.router.clone();
        tokio::spawn(async move { router.oneshot(request).await.unwrap() })
    }

    /// What the till depends on, asked while an app change waits on erplora.com: readiness (Swarm
    /// and the edge), the list of apps (every screen), and a writer getting the runtime at once —
    /// with a lock held, the writer would queue and every request after it would queue behind.
    async fn still_answers(&self, gesture: &str) {
        let ready = tokio::time::timeout(
            MUST_ANSWER_WITHIN,
            self.router
                .clone()
                .oneshot(Request::get("/readyz").body(Body::empty()).unwrap()),
        )
        .await
        .unwrap_or_else(|_| panic!("/readyz waited for the {gesture} to finish (hub#2508)"))
        .unwrap();
        assert_ne!(ready.status(), StatusCode::REQUEST_TIMEOUT);

        let apps = tokio::time::timeout(
            MUST_ANSWER_WITHIN,
            self.router.clone().oneshot(
                Request::get("/api/modules")
                    .header("x-hub-session", &self.session)
                    .body(Body::empty())
                    .unwrap(),
            ),
        )
        .await
        .unwrap_or_else(|_| panic!("the list of apps waited for the {gesture} to finish (hub#2508)"))
        .unwrap();
        assert_eq!(apps.status(), StatusCode::OK);

        tokio::time::timeout(MUST_ANSWER_WITHIN, self.runtime.write())
            .await
            .unwrap_or_else(|_| {
                panic!("the {gesture} holds the runtime while erplora.com answers (hub#2508)")
            });
    }
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes)
        .unwrap_or_else(|_| panic!("not JSON: {}", String::from_utf8_lossy(&bytes)))
}

async fn ends(gesture: &str, request: tokio::task::JoinHandle<axum::response::Response>) -> Value {
    let response = tokio::time::timeout(Duration::from_secs(10), request)
        .await
        .unwrap_or_else(|_| panic!("the {gesture} never ended once released"))
        .unwrap();
    body_json(response).await
}

#[tokio::test]
async fn the_hub_keeps_answering_while_an_app_installs() {
    for hold in [Hold::Plan, Hold::Versions, Hold::Download] {
        let (cloud, market) = a_marketplace_that_holds(hold, "1.0.0").await;
        let hub = a_hub(cloud, "install", None).await;

        let install = hub.send(hub.install("sales"));
        market.wait_until_held().await;

        hub.still_answers("install").await;

        market.let_go();
        // The bytes are not the advertised zip: the install fails its checksum, as it must.
        let body = ends("install", install).await;
        assert_eq!(body["ok"], Value::Bool(false), "{body}");
    }
}

#[tokio::test]
async fn the_hub_keeps_answering_while_an_app_updates() {
    for hold in [Hold::Versions, Hold::Download] {
        let (cloud, market) = a_marketplace_that_holds(hold, "2.0.0").await;
        let hub = a_hub(cloud, "update", Some("1.0.0")).await;

        let update = hub.send(hub.update("notes"));
        market.wait_until_held().await;

        hub.still_answers("update").await;

        market.let_go();
        if hold == Hold::Versions {
            // The resolver asked first; the install it starts asks for the versions once more.
            market.wait_until_held().await;
            market.let_go();
        }
        let body = ends("update", update).await;
        assert_eq!(
            body["warning"]["code"], "module.update_failed_kept_previous",
            "{body}"
        );
        assert_eq!(
            hub.runtime.read().await.registry().module_version("notes"),
            "1.0.0",
            "a failed update keeps the version the app had"
        );
    }
}

/// Importing a template installs its apps by the same door: the till keeps charging meanwhile.
#[tokio::test]
async fn the_hub_keeps_answering_while_a_template_installs_its_apps() {
    let (cloud, market) = a_marketplace_that_holds(Hold::Download, "1.0.0").await;
    let hub = a_hub(cloud, "template", None).await;

    let import = hub.send(hub.template_import("sales").await);
    market.wait_until_held().await;

    hub.still_answers("template import").await;

    market.let_go();
    // The app itself fails its checksum; the import reports it and carries on (best-effort).
    let body = ends("template import", import).await;
    assert_eq!(
        body["report"]["installed_modules"][0]["status"], "failed",
        "{body}"
    );
}

/// Without the write lock around the whole install, something else has to keep app changes from
/// interleaving (they resolve against the same registry and register into it): an update, a
/// template import and an uninstall that arrive while an install downloads each wait for the one
/// before, in order.
#[tokio::test]
async fn app_changes_wait_for_each_other() {
    let (cloud, market) = a_marketplace_that_holds(Hold::Download, "2.0.0").await;
    let hub = a_hub(cloud, "queue", Some("1.0.0")).await;
    let started = || market.downloads.load(Ordering::SeqCst);
    // Loopback reaches the download in milliseconds: the time each queued change gets to start
    // its own if nothing holds it back.
    let settle = || tokio::time::sleep(Duration::from_millis(400));

    let install = hub.send(hub.install("sales"));
    market.wait_until_held().await;

    let update = hub.send(hub.update("notes"));
    settle().await;
    assert_eq!(started(), 1, "an update ran during an install (hub#2508)");

    let import = hub.send(hub.template_import("taxes").await);
    settle().await;
    assert_eq!(
        started(),
        1,
        "a template import ran during an install (hub#2508)"
    );

    let uninstall = hub.send(hub.uninstall("notes"));
    settle().await;
    assert!(
        !uninstall.is_finished(),
        "an app was uninstalled during an install (hub#2508)"
    );

    // One at a time, in the order they came.
    market.let_go();
    assert_eq!(ends("install", install).await["ok"], Value::Bool(false));
    market.wait_until_held().await;
    assert_eq!(started(), 2);
    market.let_go();
    let updated = ends("update", update).await;
    assert_eq!(
        updated["warning"]["code"], "module.update_failed_kept_previous",
        "{updated}"
    );
    market.wait_until_held().await;
    assert_eq!(started(), 3);
    market.let_go();
    let imported = ends("template import", import).await;
    assert_eq!(
        imported["report"]["installed_modules"][0]["status"], "failed",
        "{imported}"
    );
    let uninstalled = ends("uninstall", uninstall).await;
    assert_eq!(uninstalled["ok"], Value::Bool(true), "{uninstalled}");
}
