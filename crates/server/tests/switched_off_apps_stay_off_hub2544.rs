//! TDD (hub#2544): **an app the owner switched off stays off after a redeploy.**
//!
//! In Hub Cloud the download cache lives in `/tmp` and is emptied on every deploy, so at boot every
//! installed app is registered again by downloading it from the catalogue (or, with the catalogue
//! down, from the copy the hub keeps in its own database). Registering always recorded the app as
//! `active`, so an app the owner had switched off came back on — menu, screens and scheduled tasks —
//! on every deploy, and the next boot could not even tell it had been off: the row already said
//! `active`. Registering again is not a decision: whatever on/off state the hub recorded is kept.
//!
//! Each test boots the hub twice (two "lives" of the container on the same database, cache emptied
//! in between), the way the issue was reported.

use std::collections::HashMap;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Arc;

use axum::extract::{Path, State};
use axum::routing::{get, post};
use axum::{Json, Router};
use cloud_client::Auth;
use erplora_db::testutil::TestDb;
use erplora_runtime::{ModuleStatus, Runtime};
use erplora_server::install::{install_from_cloud, restore_from_local_packages};
use serde_json::{json, Value};

const HUB: &str = "hub-2544";

fn module_zip(id: &str, version: &str, deps: &[&str]) -> Vec<u8> {
    let manifest = json!({ "id": id, "name": id, "version": version, "depends_on": deps });
    let mut buf = Vec::new();
    {
        let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        w.start_file("module.json", opts).unwrap();
        w.write_all(serde_json::to_string(&manifest).unwrap().as_bytes())
            .unwrap();
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

type Catalog = Arc<HashMap<String, (Vec<u8>, String)>>;

/// Minimal marketplace (no install plan: the hub resolves by manifest, as in the boot restore).
async fn spawn_cloud(apps: &[(&str, &[&str])]) -> (String, tokio::task::JoinHandle<()>) {
    let catalog: Catalog = Arc::new(
        apps.iter()
            .map(|(id, deps)| {
                let zip = module_zip(id, "1.0.0", deps);
                let sha = sha256_hex(&zip);
                (id.to_string(), (zip, sha))
            })
            .collect(),
    );
    async fn versions(State(c): State<Catalog>, Path(id): Path<String>) -> Json<Value> {
        let sha = c.get(&id).map(|(_, s)| s.clone()).unwrap_or_default();
        Json(json!([{ "version": "1.0.0", "is_active": true, "sha256": sha }]))
    }
    async fn download(State(c): State<Catalog>, Path(id): Path<String>) -> Vec<u8> {
        c.get(&id).map(|(z, _)| z.clone()).unwrap_or_default()
    }
    async fn mark_installed() -> Json<Value> {
        Json(json!({ "ok": true }))
    }
    async fn no_plan() -> axum::response::Response {
        use axum::response::IntoResponse;
        (axum::http::StatusCode::NOT_FOUND, Json(json!({}))).into_response()
    }
    let app = Router::new()
        .route("/api/v1/marketplace/modules/:id/versions/", get(versions))
        .route("/api/v1/marketplace/modules/:id/download/", get(download))
        .route(
            "/api/v1/marketplace/modules/:id/mark_installed/",
            post(mark_installed),
        )
        .route("/api/v1/marketplace/install-plan/", post(no_plan))
        .with_state(catalog);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let handle = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (format!("http://{addr}"), handle)
}

/// A catalogue nobody answers: the port is reserved and released.
async fn cloud_that_is_down() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    drop(listener);
    format!("http://{addr}")
}

fn empty_cache(tag: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-2544-{}-{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn auth() -> Auth {
    Auth::HubToken {
        hub_id: HUB.into(),
        token: "machine-secret".into(),
    }
}

/// What the registry serves AND what `hub_module` records: both have to say the same.
async fn status_of(rt: &Runtime, id: &str) -> (Option<ModuleStatus>, Option<ModuleStatus>) {
    let served = rt
        .modules()
        .into_iter()
        .find(|m| m.id == id)
        .map(|m| m.status);
    let recorded = erplora_runtime::installer::installed_status_versioned(rt.db(), HUB)
        .await
        .unwrap()
        .into_iter()
        .find(|(m, _, _)| m == id)
        .map(|(_, _, s)| s);
    (served, recorded)
}

/// One boot of a Hub Cloud container: empty cache, so what `hub_module` says installed is
/// downloaded again — the same steps `boot` takes, in the same order.
async fn boot_downloading(db: &TestDb, cloud: &str, tag: &str) -> Runtime {
    let cache = empty_cache(tag);
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.rehydrate_installed(&cache).await.unwrap();
    let policy = erplora_server::install::dev_signature_policy();
    let http = reqwest::Client::new();
    for (id, version) in rt.installed_but_unregistered().await.unwrap() {
        if rt.registry().is_installed(&id) {
            continue; // brought in as a dependency of an earlier one
        }
        install_from_cloud(
            &http,
            cloud,
            &cache,
            &auth(),
            &mut rt,
            &id,
            &version,
            &|_, _| {},
            &policy,
        )
        .await
        .unwrap_or_else(|e| panic!("download {id}@{version} again: {e}"));
    }
    assert!(rt.installed_but_unregistered().await.unwrap().is_empty());
    rt
}

/// First life: install `apps` from the catalogue and hand the runtime back.
async fn first_life(db: &TestDb, cloud: &str, apps: &[&str]) -> Runtime {
    let cache = empty_cache("life1");
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    for id in apps {
        install_from_cloud(
            &reqwest::Client::new(),
            cloud,
            &cache,
            &auth(),
            &mut rt,
            id,
            "1.0.0",
            &|_, _| {},
            &erplora_server::install::dev_signature_policy(),
        )
        .await
        .unwrap_or_else(|e| panic!("install {id}: {e}"));
    }
    rt
}

/// **The issue.** The owner switches `notes` off; ERPlora deploys twice; `notes` is still off.
#[tokio::test]
async fn an_app_switched_off_stays_off_when_every_deploy_downloads_it_again() {
    let db = TestDb::new().await;
    let (cloud, _handle) = spawn_cloud(&[("notes", &[]), ("tasks", &[])]).await;

    let mut rt = first_life(&db, &cloud, &["notes", "tasks"]).await;
    rt.deactivate("notes").await.unwrap();
    drop(rt);

    for deploy in ["deploy1", "deploy2"] {
        let rt = boot_downloading(&db, &cloud, deploy).await;
        assert_eq!(
            status_of(&rt, "notes").await,
            (Some(ModuleStatus::Inactive), Some(ModuleStatus::Inactive)),
            "{deploy}: the app the owner switched off has to stay off"
        );
        assert_eq!(
            status_of(&rt, "tasks").await,
            (Some(ModuleStatus::Active), Some(ModuleStatus::Active)),
            "{deploy}: the apps left on stay on"
        );
    }
}

/// Same, with the catalogue down: the hub puts the app back from its own copy.
#[tokio::test]
async fn an_app_switched_off_stays_off_when_the_local_copy_puts_it_back() {
    let db = TestDb::new().await;
    let (cloud, handle) = spawn_cloud(&[("notes", &[])]).await;

    let mut rt = first_life(&db, &cloud, &["notes"]).await;
    rt.deactivate("notes").await.unwrap();
    drop(rt);
    handle.abort();
    let down = cloud_that_is_down().await;

    for deploy in ["local1", "local2"] {
        let cache = empty_cache(deploy);
        let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
        rt.ensure_system_tables().await.unwrap();
        rt.rehydrate_installed(&cache).await.unwrap();
        let missing = rt.installed_but_unregistered().await.unwrap();
        assert!(
            install_from_cloud(
                &reqwest::Client::new(),
                &down,
                &cache,
                &auth(),
                &mut rt,
                "notes",
                "1.0.0",
                &|_, _| {},
                &erplora_server::install::dev_signature_policy(),
            )
            .await
            .is_err(),
            "the catalogue has to be DOWN for this test to prove anything"
        );
        let policy = erplora_server::install::dev_signature_policy();
        let restored = restore_from_local_packages(&cache, &mut rt, &missing, &policy).await;
        assert_eq!(restored, vec!["notes".to_string()]);
        assert_eq!(
            status_of(&rt, "notes").await,
            (Some(ModuleStatus::Inactive), Some(ModuleStatus::Inactive)),
            "{deploy}: put back from the local copy, still off"
        );
    }
}

/// The cascade survives too: the app switched off by hand stays off by hand, and the one that fell
/// with it stays off waiting for it (and comes back when the owner switches the first one on).
#[tokio::test]
async fn an_app_that_fell_in_cascade_stays_off_and_comes_back_with_its_dependency() {
    let db = TestDb::new().await;
    let (cloud, _handle) = spawn_cloud(&[("ledger", &[]), ("invoicing", &["ledger"])]).await;

    let mut rt = first_life(&db, &cloud, &["invoicing"]).await;
    rt.deactivate("ledger").await.unwrap();
    assert_eq!(
        status_of(&rt, "invoicing").await.0,
        Some(ModuleStatus::InactiveAuto)
    );
    drop(rt);

    let mut rt = boot_downloading(&db, &cloud, "cascade").await;
    assert_eq!(
        status_of(&rt, "ledger").await,
        (Some(ModuleStatus::Inactive), Some(ModuleStatus::Inactive)),
        "switched off by hand, still off by hand"
    );
    assert_eq!(
        status_of(&rt, "invoicing").await,
        (
            Some(ModuleStatus::InactiveAuto),
            Some(ModuleStatus::InactiveAuto)
        ),
        "fell with ledger, still waiting for it"
    );

    rt.activate("ledger").await.unwrap();
    assert_eq!(
        status_of(&rt, "invoicing").await,
        (Some(ModuleStatus::Active), Some(ModuleStatus::Active)),
        "switching ledger back on brings invoicing back"
    );
}

/// Tenancy: the state kept is the one THIS hub recorded. Another hub on the same database that
/// switched the app off does not make a fresh install here start off.
#[tokio::test]
async fn the_state_kept_is_the_one_this_hub_recorded() {
    let db = TestDb::new().await;
    let root = empty_cache("tenancy");
    std::fs::write(
        root.join("module.json"),
        json!({ "id": "notes", "name": "notes", "version": "1.0.0" }).to_string(),
    )
    .unwrap();

    let mut other = Runtime::with_hub_id(Box::new(db.adapter().await), "hub-other");
    other.ensure_system_tables().await.unwrap();
    other.install_from_dir(&root).await.unwrap();
    other.deactivate("notes").await.unwrap();

    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&root).await.unwrap();
    assert_eq!(
        status_of(&rt, "notes").await,
        (Some(ModuleStatus::Active), Some(ModuleStatus::Active)),
        "a first install in this hub starts on, whatever another hub did"
    );
}

/// HUB-F23 step 5, same root: updating an app that is off leaves it off.
#[tokio::test]
async fn updating_an_app_that_is_off_leaves_it_off() {
    let db = TestDb::new().await;
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    let root = empty_cache("update");
    for version in ["1.0.0", "1.1.0"] {
        let dir = root.join(version);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(
            dir.join("module.json"),
            json!({ "id": "notes", "name": "notes", "version": version }).to_string(),
        )
        .unwrap();
    }

    rt.install_from_dir(&root.join("1.0.0")).await.unwrap();
    rt.deactivate("notes").await.unwrap();
    rt.install_from_dir(&root.join("1.1.0")).await.unwrap();

    let info = rt.modules().into_iter().find(|m| m.id == "notes").unwrap();
    assert_eq!(info.version, "1.1.0", "the update did land");
    assert_eq!(
        status_of(&rt, "notes").await,
        (Some(ModuleStatus::Inactive), Some(ModuleStatus::Inactive)),
        "updating is not switching on"
    );
}
