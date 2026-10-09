//! **Once an update has put the new version in place, the next app change goes** (hub#2663).
//!
//! App changes — install, update, template import, uninstall — take turns on one queue
//! (`module_ops`, hub#2508). Installing gives its turn back as soon as the app is registered, and
//! only then teaches the assistant the app's texts (`index_module_embeddings`: a call to
//! erplora.com that may take up to its 60 s limit). Updating kept the turn until the very end of
//! the request, indexing included, so an administrator who updated an app and then tried to
//! uninstall another one waited up to a minute more with nothing on screen saying why.
//!
//! The contract fixed here, through the REAL router: while an update that already put the new
//! version in place is waiting on erplora.com's embeddings, an uninstall goes through at once; and
//! the update still indexes the new version's texts once erplora.com answers.

use std::io::Write;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use axum::body::Body;
use axum::http::Request;
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use erplora_vector::{MemoryVectorStore, VectorStore};
use serde_json::{json, Value};
use tokio::sync::Notify;
use tower::ServiceExt;

const HUB_ID: &str = "hub-2663";

/// The next app change has this long to finish while the update waits on erplora.com's
/// embeddings. Loopback uninstalls in milliseconds; waiting for the indexing is the bug.
const MUST_GO_THROUGH_WITHIN: Duration = Duration::from_secs(3);

fn build_zip(entries: &[(&str, &[u8])]) -> Vec<u8> {
    let mut buf = Vec::new();
    {
        let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        for (name, bytes) in entries {
            w.start_file(*name, opts).unwrap();
            w.write_all(bytes).unwrap();
        }
        w.finish().unwrap();
    }
    buf
}

fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// `parts@version`, with a description for the assistant: that is what makes the update index.
fn parts_manifest(version: &str) -> String {
    json!({
        "id": "parts",
        "name": "Parts",
        "version": version,
        "agent": { "description": format!("Spare parts, version {version}") },
    })
    .to_string()
}

/// What the test sees of erplora.com: `held` flips when the embeddings call starts waiting and
/// `release` lets it answer.
#[derive(Clone, Default)]
struct Embeddings {
    held: Arc<AtomicBool>,
    release: Arc<Notify>,
}

impl Embeddings {
    async fn wait_until_held(&self) {
        tokio::time::timeout(Duration::from_secs(10), async {
            while !self.held.load(Ordering::SeqCst) {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("the update never reached erplora.com's embeddings");
    }
}

/// A marketplace that serves `parts@2.0.0` for real, and an embeddings proxy that holds its
/// answer until the test releases it.
async fn erplora_com(package: Vec<u8>) -> (String, Embeddings) {
    let sha = sha256_hex(&package);
    let embeddings = Embeddings::default();
    let router = Router::new()
        .route(
            "/api/v1/marketplace/install-plan/",
            post({
                let sha = sha.clone();
                move || async move {
                    Json(json!({
                        "requested": "parts",
                        "plan": [{
                            "module_id": "parts", "version": "2.0.0", "sha256": sha,
                            "tier": "free", "entitled": true, "requires_purchase": false,
                            "reason": "requested",
                        }],
                        "already_satisfied": [],
                        "blocked": false,
                        "blocked_on": [],
                    }))
                }
            }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/versions/",
            get(move || async move {
                Json(json!([{ "version": "2.0.0", "is_active": true, "sha256": sha }]))
            }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/download/",
            get(move || async move { package }),
        )
        .route(
            "/api/v1/marketplace/modules/:id/mark_installed/",
            post(|| async { Json(json!({ "ok": true })) }),
        )
        .route(
            "/api/v1/hub/device/assistant/embeddings/",
            post({
                let embeddings = embeddings.clone();
                move |Json(asked): Json<Value>| async move {
                    embeddings.held.store(true, Ordering::SeqCst);
                    embeddings.release.notified().await;
                    let texts = asked["texts"].as_array().map_or(0, Vec::len);
                    Json(json!({ "embeddings": vec![vec![1.0_f32, 0.0]; texts], "model": "test" }))
                }
            }),
        );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{addr}"), embeddings)
}

/// A hub with `parts@1.0.0` and `notes@1.0.0` installed, an administrator and an assistant index.
async fn a_hub(cloud_base_url: String) -> (Router, String, AppState, Arc<MemoryVectorStore>) {
    let temp = std::env::temp_dir().join(format!("erplora-hub2663-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&temp);
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    for (id, manifest) in [
        ("parts", parts_manifest("1.0.0")),
        (
            "notes",
            r#"{"id":"notes","name":"Notes","version":"1.0.0"}"#.to_string(),
        ),
    ] {
        let dir = temp.join("seed").join(id);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("module.json"), manifest).unwrap();
        rt.install_from_dir(&dir).await.expect("seed install");
    }
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let config = HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
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
        // Empty ring ⇒ `Sha256Only`: integrity still mandatory, signature not required.
        module_trusted_keys: Vec::new(),
    };
    let store = Arc::new(MemoryVectorStore::new());
    let state = AppState::with_config(rt, config).with_vector(store.clone());
    (app(state.clone()), session, state, store)
}

fn post_as(session: &str, uri: &str) -> Request<Body> {
    Request::post(uri)
        .header("x-hub-session", session)
        .header("content-type", "application/json")
        .body(Body::from("{}"))
        .unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes)
        .unwrap_or_else(|_| panic!("not JSON: {}", String::from_utf8_lossy(&bytes)))
}

#[tokio::test]
async fn an_update_gives_the_app_turn_back_before_indexing_hub2663() {
    let package = build_zip(&[("module.json", parts_manifest("2.0.0").as_bytes())]);
    let (cloud, embeddings) = erplora_com(package).await;
    let (router, session, state, store) = a_hub(cloud).await;

    let update = tokio::spawn(
        router
            .clone()
            .oneshot(post_as(&session, "/api/modules/parts/update")),
    );
    embeddings.wait_until_held().await;
    assert_eq!(
        state
            .runtime
            .read()
            .await
            .registry()
            .module_version("parts"),
        "2.0.0",
        "the update is indexing, so the new version is already in place"
    );

    // The next app change, while erplora.com has not answered the embeddings yet.
    let uninstall = tokio::time::timeout(
        MUST_GO_THROUGH_WITHIN,
        router
            .clone()
            .oneshot(post_as(&session, "/api/modules/notes/uninstall")),
    )
    .await
    .expect("an uninstall waited for the update's indexing to finish (hub#2663)")
    .unwrap();
    let uninstalled = body_json(uninstall).await;
    assert_eq!(uninstalled["ok"], Value::Bool(true), "{uninstalled}");

    // erplora.com answers: the update ends as an update and the new version's texts are indexed.
    embeddings.release.notify_one();
    let response = tokio::time::timeout(Duration::from_secs(10), update)
        .await
        .expect("the update never ended once erplora.com answered")
        .unwrap()
        .unwrap();
    let updated = body_json(response).await;
    assert_eq!(updated["data"]["updated"], Value::Bool(true), "{updated}");
    assert_eq!(updated["data"]["version"], "2.0.0", "{updated}");
    let indexed = store
        .search(HUB_ID, &[1.0, 0.0], 10, Some(&["parts".to_string()]))
        .await
        .unwrap();
    assert!(
        indexed
            .iter()
            .any(|hit| hit.chunk.version == "2.0.0" && hit.chunk.content.contains("version 2.0.0")),
        "the update must still index the new version for the assistant: {:?}",
        indexed
            .iter()
            .map(|h| (&h.chunk.version, &h.chunk.content))
            .collect::<Vec<_>>()
    );
}
