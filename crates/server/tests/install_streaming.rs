//! hub#981: the module zip download STREAMS to a temp file in the module cache instead of
//! buffering the whole archive (twice) in RAM. The contract these tests fix:
//!
//!  - a zip served by the marketplace still installs end to end (streaming must not regress
//!    the install contract), and after installing, the module cache holds ONLY the extracted
//!    module — no temp zip, no partial download left behind;
//!  - a wrong sha256 rejects the install BEFORE anything is touched (ADR-0015, unchanged),
//!    installs nothing, and cleans the temp download file up.
//!
//! Mock pattern: same mini-Cloud as `tests/install_progress.rs` (`versions/`, `download/`,
//! `mark_installed/`) serving a real zip; `versions/` exposes whatever sha the test chooses.

use std::collections::HashMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use axum::extract::{Path as AxumPath, State};
use axum::routing::{get, post};
use axum::{Json, Router};
use cloud_client::Auth;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::install::{dev_signature_policy, install_from_cloud};
use serde_json::json;

/// `module.zip` mínimo instalable: `module.json` con id/name/version.
fn module_zip(id: &str) -> Vec<u8> {
    let manifest = json!({ "id": id, "name": id, "version": "1.0.0" });
    let mut buf = Vec::new();
    {
        let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        w.start_file("module.json", opts).unwrap();
        w.write_all(manifest.to_string().as_bytes()).unwrap();
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

/// id → (zip, sha256 expuesto en `versions/`). El sha lo elige el test: correcto o corrupto.
type Catalog = Arc<HashMap<String, (Vec<u8>, String)>>;

async fn spawn_mock_cloud(catalog: Catalog) -> String {
    async fn versions(
        State(cat): State<Catalog>,
        AxumPath(id): AxumPath<String>,
    ) -> Json<serde_json::Value> {
        let sha = cat.get(&id).map(|(_, s)| s.clone()).unwrap_or_default();
        Json(json!([{ "version": "1.0.0", "is_active": true, "sha256": sha }]))
    }
    async fn download(State(cat): State<Catalog>, AxumPath(id): AxumPath<String>) -> Vec<u8> {
        cat.get(&id).map(|(z, _)| z.clone()).unwrap_or_default()
    }
    async fn mark_installed() -> Json<serde_json::Value> {
        Json(json!({ "ok": true }))
    }
    let app = Router::new()
        .route("/api/v1/marketplace/modules/:id/versions/", get(versions))
        .route("/api/v1/marketplace/modules/:id/download/", get(download))
        .route(
            "/api/v1/marketplace/modules/:id/mark_installed/",
            post(mark_installed),
        )
        .with_state(catalog);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("http://{addr}")
}

/// Every FILE under `root`, relative — to assert the cache holds only what it should.
fn files_under(root: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_dir() {
                stack.push(p);
            } else {
                out.push(p.strip_prefix(root).unwrap().to_path_buf());
            }
        }
    }
    out.sort();
    out
}

fn fresh_cache(tag: &str) -> PathBuf {
    let cache = std::env::temp_dir().join(format!(
        "erplora-install-streaming-{tag}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&cache);
    cache
}

#[tokio::test]
async fn streamed_download_installs_and_leaves_only_the_extracted_module() {
    let zip = module_zip("notes");
    let mut cat = HashMap::new();
    cat.insert("notes".to_string(), (zip.clone(), sha256_hex(&zip)));
    let base_url = spawn_mock_cloud(Arc::new(cat)).await;

    let http = reqwest::Client::new();
    let auth = Auth::HubToken {
        hub_id: "hub-test".into(),
        token: "tok".into(),
    };
    let cache = fresh_cache("ok");
    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.ensure_system_tables().await.unwrap();

    let installed = install_from_cloud(
        &http,
        &base_url,
        &cache,
        &auth,
        &mut rt,
        "notes",
        "latest",
        &|_, _| {},
        &dev_signature_policy(),
    )
    .await
    .expect("a served zip must install end to end");
    assert_eq!(installed.module_id, "notes");
    assert!(rt.registry().is_installed("notes"));

    // The cache holds ONLY the extracted module: no temp zip, no partial download.
    let files = files_under(&cache);
    assert!(
        files.iter().all(|f| f.starts_with("notes/1.0.0")),
        "unexpected leftovers in the module cache: {files:?}"
    );
    assert!(
        files.contains(&PathBuf::from("notes/1.0.0/module.json")),
        "the extracted module must be in the cache: {files:?}"
    );
    let _ = std::fs::remove_dir_all(&cache);
}

#[tokio::test]
async fn wrong_sha_rejects_installs_nothing_and_cleans_the_temp_file() {
    let zip = module_zip("notes");
    let mut cat = HashMap::new();
    // `versions/` promises the sha of OTHER bytes: the streamed download must be rejected.
    cat.insert("notes".to_string(), (zip, sha256_hex(b"other bytes")));
    let base_url = spawn_mock_cloud(Arc::new(cat)).await;

    let http = reqwest::Client::new();
    let auth = Auth::HubToken {
        hub_id: "hub-test".into(),
        token: "tok".into(),
    };
    let cache = fresh_cache("badsha");
    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.ensure_system_tables().await.unwrap();

    let err = install_from_cloud(
        &http,
        &base_url,
        &cache,
        &auth,
        &mut rt,
        "notes",
        "latest",
        &|_, _| {},
        &dev_signature_policy(),
    )
    .await
    .expect_err("a zip whose sha does not match must be rejected (ADR-0015)");
    assert_eq!(err.code(), "install_download_failed", "{err:?}");
    assert!(
        !rt.registry().is_installed("notes"),
        "nothing must be installed"
    );

    // No temp download, no staging, no extracted files: the rejection leaves no trace.
    let files = files_under(&cache);
    assert!(
        files.is_empty(),
        "a rejected download must clean up after itself: {files:?}"
    );
    let _ = std::fs::remove_dir_all(&cache);
}
