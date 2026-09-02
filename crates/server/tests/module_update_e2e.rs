//! TDD (hub#516): **the update route**. Publishing v2 of a module with a bug fixed has to be able
//! to reach a hub that already has v1 installed.
//!
//! Until now there was no way: `install`/`request-install` skip what is already installed
//! (`already_satisfied`), so the fix never landed — *a module bug was unfixable across the fleet*.
//! What is pinned here is the whole contract of the new door:
//!
//!   1. an update downloads the new version through the SAME verified pipeline and repoints
//!      `hub_module.version`;
//!   2. **verification is not optional on an update either** (ADR-0015/0193/0194): a bad SHA256 or
//!      a signature that does not verify is refused, and the module keeps running what it had;
//!   3. a new version whose manifest breaks a contract leaves the module on the old one — it never
//!      ends up half-installed;
//!   4. if the new version needs a premium dependency this hub has not bought, the update is
//!      **blocked** with the purchase pointer and **nothing is charged** (ADR-0060);
//!   5. «there is nothing newer» is an answer, not a failure;
//!   6. a version in **quarantine** is never the target — that is what quarantine is for.

use std::collections::HashMap;
use std::io::Write;
use std::sync::{Arc, Mutex};

use axum::extract::{Path as AxumPath, Query, State};
use axum::routing::{get, post};
use axum::{Json, Router};
use cloud_client::Auth;
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::Runtime;
use erplora_server::install::{update_from_cloud, InstallError};
use serde_json::{json, Value};

// ── Mock marketplace serving SEVERAL versions per module ─────────────────────────────────

/// One published version of a module: the zip bytes, its sha256, and whether it is active
/// (`is_active = false` = quarantined, «marked as broken»).
#[derive(Clone)]
struct Published {
    version: String,
    zip: Vec<u8>,
    sha256: String,
    is_active: bool,
    /// Overrides the sha256 the catalogue ADVERTISES (to forge a mismatch). `None` = the real one.
    advertised_sha: Option<String>,
}

struct MockCloud {
    /// module id → published versions, newest last.
    catalog: HashMap<String, Vec<Published>>,
    /// Canned `install-plan` responses by requested module id. Absent → 404 (older Cloud).
    plans: HashMap<String, Value>,
    calls: Mutex<Vec<String>>,
}

type Shared = Arc<MockCloud>;

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

/// A published version carrying `manifest` plus any extra package files.
fn publish(version: &str, manifest: Value, files: &[(&str, &str)]) -> Published {
    let manifest_bytes = serde_json::to_string(&manifest).unwrap();
    let mut entries: Vec<(&str, &[u8])> = vec![("module.json", manifest_bytes.as_bytes())];
    for (name, body) in files {
        entries.push((name, body.as_bytes()));
    }
    let zip = build_zip(&entries);
    let sha256 = sha256_hex(&zip);
    Published {
        version: version.into(),
        zip,
        sha256,
        is_active: true,
        advertised_sha: None,
    }
}

/// The plain manifest of `id`@`version`, with one table migration so an update has real work.
fn plain_manifest(id: &str, version: &str) -> Value {
    json!({
        "id": id,
        "name": id,
        "version": version,
        "migrations": { "postgres": [format!("migrations/postgres/001_init.sql")] }
    })
}

fn init_sql(id: &str) -> String {
    format!("CREATE TABLE IF NOT EXISTS {id}_item (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);")
}

#[derive(serde::Deserialize)]
struct VersionQuery {
    version: Option<String>,
}

async fn spawn_mock_cloud(mock: Shared) -> String {
    async fn versions(State(m): State<Shared>, AxumPath(id): AxumPath<String>) -> Json<Value> {
        m.calls.lock().unwrap().push(format!("versions:{id}"));
        let list: Vec<Value> = m
            .catalog
            .get(&id)
            .map(|versions| {
                versions
                    .iter()
                    .rev() // the real endpoint orders by `-created_at`
                    .map(|v| {
                        json!({
                            "version": v.version,
                            "is_active": v.is_active,
                            "sha256": v.advertised_sha.clone().unwrap_or_else(|| v.sha256.clone()),
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();
        Json(json!(list))
    }
    async fn download(
        State(m): State<Shared>,
        AxumPath(id): AxumPath<String>,
        Query(q): Query<VersionQuery>,
    ) -> Vec<u8> {
        let asked = q.version.unwrap_or_default();
        m.calls
            .lock()
            .unwrap()
            .push(format!("download:{id}@{asked}"));
        m.catalog
            .get(&id)
            .and_then(|versions| {
                versions
                    .iter()
                    .find(|v| v.version == asked)
                    .or_else(|| versions.last())
            })
            .map(|v| v.zip.clone())
            .unwrap_or_default()
    }
    async fn mark_installed(
        State(m): State<Shared>,
        AxumPath(id): AxumPath<String>,
    ) -> Json<Value> {
        m.calls.lock().unwrap().push(format!("mark:{id}"));
        Json(json!({ "ok": true }))
    }
    async fn install_plan(
        State(m): State<Shared>,
        Json(body): Json<Value>,
    ) -> axum::response::Response {
        use axum::response::IntoResponse;
        let requested = body
            .get("module_id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        m.calls.lock().unwrap().push(format!("plan:{requested}"));
        match m.plans.get(&requested) {
            Some(p) => Json(p.clone()).into_response(),
            None => (
                axum::http::StatusCode::NOT_FOUND,
                Json(json!({ "detail": "Not found." })),
            )
                .into_response(),
        }
    }
    let app = Router::new()
        .route("/api/v1/marketplace/modules/:id/versions/", get(versions))
        .route("/api/v1/marketplace/modules/:id/download/", get(download))
        .route(
            "/api/v1/marketplace/modules/:id/mark_installed/",
            post(mark_installed),
        )
        .route("/api/v1/marketplace/install-plan/", post(install_plan))
        .with_state(mock);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("http://{addr}")
}

fn cache_dir(tag: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-mod-update-{}-{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    dir
}

fn auth() -> Auth {
    Auth::HubToken {
        hub_id: "hub-test".into(),
        token: "tok".into(),
    }
}

fn dev_policy() -> cloud_client::SignaturePolicy {
    erplora_server::install::dev_signature_policy()
}

/// Installs `id`@`version` straight from a package written on disk (the hub's starting point).
async fn install_locally(
    rt: &mut Runtime,
    tag: &str,
    id: &str,
    version: &str,
    files: &[(&str, &str)],
) {
    let dir = std::env::temp_dir()
        .join(format!(
            "erplora-mod-update-seed-{}-{tag}",
            std::process::id()
        ))
        .join(version);
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string(&plain_manifest(id, version)).unwrap(),
    )
    .unwrap();
    for (rel, body) in files {
        let path = dir.join(rel);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, body).unwrap();
    }
    rt.install_from_dir(&dir).await.expect("seed install");
}

/// What `hub_module` says this hub runs.
async fn recorded_version(rt: &Runtime, module_id: &str) -> String {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(rt.hub_id()));
    p.insert("module_id".into(), json!(module_id));
    rt.db_for_test()
        .query(
            "SELECT version FROM hub_module WHERE hub_id = :hub_id AND module_id = :module_id",
            &p,
        )
        .await
        .map(|res| {
            res.rows
                .first()
                .map(|r| r["version"].as_str().unwrap_or_default().to_string())
                .unwrap_or_default()
        })
        .unwrap_or_default()
}

fn mock_with(catalog: HashMap<String, Vec<Published>>, plans: HashMap<String, Value>) -> Shared {
    Arc::new(MockCloud {
        catalog,
        plans,
        calls: Mutex::new(Vec::new()),
    })
}

/// The plan the Cloud returns for a straight one-module update.
fn single_node_plan(id: &str, version: &str, sha: &str) -> Value {
    json!({
        "requested": id,
        "plan": [{
            "module_id": id, "version": version, "sha256": sha, "tier": "free",
            "entitled": true, "requires_purchase": false, "reason": "requested",
        }],
        "already_satisfied": [],
        "blocked": false,
        "blocked_on": [],
    })
}

// ── 1. The happy path: v1 → v2 ───────────────────────────────────────────────────────────

#[tokio::test]
async fn updating_installs_the_newer_version_and_repoints_hub_module() {
    let sql = init_sql("parts");
    let files = [("migrations/postgres/001_init.sql", sql.as_str())];
    let v2 = publish("2.0.0", plain_manifest("parts", "2.0.0"), &files);
    let sha = v2.sha256.clone();
    let mut catalog = HashMap::new();
    catalog.insert("parts".to_string(), vec![v2]);
    let mut plans = HashMap::new();
    plans.insert(
        "parts".to_string(),
        single_node_plan("parts", "2.0.0", &sha),
    );
    let mock = mock_with(catalog, plans);
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_locally(&mut rt, "happy", "parts", "1.0.0", &files).await;

    let updated = update_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("happy"),
        &auth(),
        &mut rt,
        "parts",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("the update goes through");

    assert!(updated.updated, "there WAS a newer version");
    assert_eq!(updated.from, "1.0.0");
    assert_eq!(updated.to, "2.0.0");
    assert_eq!(
        rt.registry().module_version("parts"),
        "2.0.0",
        "the runtime now serves the new version"
    );
    assert_eq!(
        recorded_version(&rt, "parts").await,
        "2.0.0",
        "hub_module is repointed, so a restart brings back the NEW version"
    );
}

// ── 2. Verification is not optional on an update either ──────────────────────────────────

/// ADR-0015: the SHA256 of the zip is checked on an update exactly like on an install. A package
/// whose bytes do not match what the catalogue advertised is refused, and the hub keeps v1.
#[tokio::test]
async fn an_update_whose_zip_does_not_match_its_sha256_is_refused_and_v1_keeps_running() {
    let sql = init_sql("parts");
    let files = [("migrations/postgres/001_init.sql", sql.as_str())];
    let mut v2 = publish("2.0.0", plain_manifest("parts", "2.0.0"), &files);
    // The catalogue advertises a hash that is not the zip's: tampered bytes in flight.
    v2.advertised_sha = Some("00".repeat(32));
    let forged = v2.advertised_sha.clone().unwrap();
    let mut catalog = HashMap::new();
    catalog.insert("parts".to_string(), vec![v2]);
    let mut plans = HashMap::new();
    plans.insert(
        "parts".to_string(),
        single_node_plan("parts", "2.0.0", &forged),
    );
    let mock = mock_with(catalog, plans);
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_locally(&mut rt, "badsha", "parts", "1.0.0", &files).await;

    let error = update_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("badsha"),
        &auth(),
        &mut rt,
        "parts",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect_err("integrity failure must abort the update");

    assert_eq!(error.code(), "install_download_failed");
    assert_eq!(
        rt.registry().module_version("parts"),
        "1.0.0",
        "the module keeps running the version that verified"
    );
    assert_eq!(recorded_version(&rt, "parts").await, "1.0.0");
}

/// ADR-0193/0194: under `Enforce`, a package without a valid ed25519 signature is refused **before
/// being unzipped**. The update door does not open a way in without a signature.
#[tokio::test]
async fn an_unsigned_new_version_is_refused_when_signatures_are_enforced() {
    let sql = init_sql("parts");
    let files = [("migrations/postgres/001_init.sql", sql.as_str())];
    let v2 = publish("2.0.0", plain_manifest("parts", "2.0.0"), &files);
    let sha = v2.sha256.clone();
    let mut catalog = HashMap::new();
    catalog.insert("parts".to_string(), vec![v2]);
    let mut plans = HashMap::new();
    plans.insert(
        "parts".to_string(),
        single_node_plan("parts", "2.0.0", &sha),
    );
    let mock = mock_with(catalog, plans);
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_locally(&mut rt, "unsigned", "parts", "1.0.0", &files).await;

    // Production policy: an empty keyring trusts nobody, so nothing verifies.
    let enforce = cloud_client::SignaturePolicy::Enforce(cloud_client::TrustedKeyRing::empty());
    let error = update_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("unsigned"),
        &auth(),
        &mut rt,
        "parts",
        "latest",
        &|_, _| {},
        &enforce,
    )
    .await
    .expect_err("an unsigned package must not update anything");

    assert_eq!(error.code(), "install_bad_signature");
    assert_eq!(rt.registry().module_version("parts"), "1.0.0");
}

// ── 3. A new version that breaks a contract leaves the module on the old one ─────────────

/// The manifest of the new version is validated at the same door as an install. Rejected → the
/// module is NOT left half-installed: it keeps serving v1, and `hub_module` still says v1.
#[tokio::test]
async fn a_new_version_whose_manifest_breaks_a_contract_leaves_the_module_on_the_old_one() {
    let sql = init_sql("parts");
    let files = [("migrations/postgres/001_init.sql", sql.as_str())];
    // hub#139: a command cannot combine the legacy row gate with the translatable one.
    let mut broken = plain_manifest("parts", "2.0.0");
    broken["commands"] = json!({
        "parts.touch": {
            "permission": "parts.write",
            "sql": ["sql/touch.sql"],
            "min_affected_rows": 1,
            "expect_rows": { "at_least": 1, "error": "parts.nothing_touched" }
        }
    });
    let v2 = publish(
        "2.0.0",
        broken,
        &[
            ("migrations/postgres/001_init.sql", sql.as_str()),
            ("sql/touch.sql", "UPDATE parts_item SET id = id"),
        ],
    );
    let sha = v2.sha256.clone();
    let mut catalog = HashMap::new();
    catalog.insert("parts".to_string(), vec![v2]);
    let mut plans = HashMap::new();
    plans.insert(
        "parts".to_string(),
        single_node_plan("parts", "2.0.0", &sha),
    );
    let mock = mock_with(catalog, plans);
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_locally(&mut rt, "badmanifest", "parts", "1.0.0", &files).await;

    let error = update_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("badmanifest"),
        &auth(),
        &mut rt,
        "parts",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect_err("a manifest that breaks a contract must not be installed");

    assert_eq!(error.code(), "install_runtime_failed");
    assert!(
        rt.registry().is_installed("parts"),
        "the module must still be there"
    );
    assert_eq!(rt.registry().module_version("parts"), "1.0.0");
    assert!(
        !rt.registry().commands.contains_key("parts.touch"),
        "nothing of the rejected version is registered"
    );
    assert_eq!(recorded_version(&rt, "parts").await, "1.0.0");
}

// ── 4. A new version with an unbought premium dependency: blocked, never charged ─────────

#[tokio::test]
async fn a_new_version_needing_an_unbought_premium_dependency_is_blocked_and_charges_nothing() {
    let sql = init_sql("parts");
    let files = [("migrations/postgres/001_init.sql", sql.as_str())];
    let mut needs_premium = plain_manifest("parts", "2.0.0");
    needs_premium["depends_on"] = json!(["invoice"]);
    let v2 = publish("2.0.0", needs_premium, &files);
    let sha = v2.sha256.clone();
    let mut catalog = HashMap::new();
    catalog.insert("parts".to_string(), vec![v2]);
    let mut plans = HashMap::new();
    plans.insert(
        "parts".to_string(),
        json!({
            "requested": "parts",
            "plan": [
                {"module_id":"invoice","version":"1.0.0","sha256":"aa","tier":"premium",
                 "entitled":false,"requires_purchase":true,"reason":"dependency",
                 "purchase":{"module_type":"premium","price":"9.00","currency":"EUR",
                             "purchase_url":"/marketplace/invoice/"}},
                {"module_id":"parts","version":"2.0.0","sha256": sha, "tier":"free",
                 "entitled":true,"requires_purchase":false,"reason":"requested"}
            ],
            "already_satisfied": [],
            "blocked": true,
            "blocked_on": ["invoice"],
        }),
    );
    let mock = mock_with(catalog, plans);
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_locally(&mut rt, "blocked", "parts", "1.0.0", &files).await;

    let error = update_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("blocked"),
        &auth(),
        &mut rt,
        "parts",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect_err("a blocked plan must not update");

    match &error {
        InstallError::Blocked {
            blocked_on,
            purchase,
            ..
        } => {
            assert_eq!(blocked_on, &["invoice".to_string()]);
            let pointer = purchase
                .iter()
                .find(|p| p.module_id == "invoice")
                .expect("the purchase pointer travels to the UI");
            assert_eq!(pointer.price, "9.00");
        }
        other => panic!("expected InstallError::Blocked, got {other:?}"),
    }
    assert_eq!(error.code(), "install_blocked");
    assert_eq!(
        rt.registry().module_version("parts"),
        "1.0.0",
        "blocked = nothing changed"
    );
    assert!(!rt.registry().is_installed("invoice"));
    let calls = mock.calls.lock().unwrap().clone();
    assert!(
        !calls.iter().any(|c| c.starts_with("download:")),
        "nothing is downloaded, and above all nothing is charged: {calls:?}"
    );
}

// ── 5. «Nothing newer» is an answer, not a failure ───────────────────────────────────────

#[tokio::test]
async fn nothing_newer_is_reported_as_no_update_not_as_an_error() {
    let sql = init_sql("parts");
    let files = [("migrations/postgres/001_init.sql", sql.as_str())];
    let v1 = publish("1.0.0", plain_manifest("parts", "1.0.0"), &files);
    let mut catalog = HashMap::new();
    catalog.insert("parts".to_string(), vec![v1]);
    let mock = mock_with(catalog, HashMap::new());
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_locally(&mut rt, "noop", "parts", "1.0.0", &files).await;

    let result = update_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("noop"),
        &auth(),
        &mut rt,
        "parts",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("being up to date is not a failure");

    assert!(!result.updated);
    assert_eq!(result.from, "1.0.0");
    assert_eq!(result.to, "1.0.0");
    let calls = mock.calls.lock().unwrap().clone();
    assert!(
        !calls.iter().any(|c| c.starts_with("download:")),
        "with nothing to update, nothing is downloaded: {calls:?}"
    );
}

/// Quarantine (`is_active = false`) is precisely what stops a broken version from spreading. The
/// button must not be a way around it.
#[tokio::test]
async fn a_quarantined_new_version_is_never_the_target_of_an_update() {
    let sql = init_sql("parts");
    let files = [("migrations/postgres/001_init.sql", sql.as_str())];
    let mut broken_release = publish("2.0.0", plain_manifest("parts", "2.0.0"), &files);
    broken_release.is_active = false;
    let mut catalog = HashMap::new();
    catalog.insert(
        "parts".to_string(),
        vec![
            publish("1.0.0", plain_manifest("parts", "1.0.0"), &files),
            broken_release,
        ],
    );
    let mock = mock_with(catalog, HashMap::new());
    let base_url = spawn_mock_cloud(mock.clone()).await;

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_locally(&mut rt, "quarantine", "parts", "1.0.0", &files).await;

    let result = update_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("quarantine"),
        &auth(),
        &mut rt,
        "parts",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect("a quarantined version is simply not offered");

    assert!(!result.updated, "2.0.0 is quarantined: it is not a target");
    assert_eq!(rt.registry().module_version("parts"), "1.0.0");
}

// ── 6. Updating what is not installed is not an update ───────────────────────────────────

#[tokio::test]
async fn updating_a_module_that_is_not_installed_is_refused() {
    let mock = mock_with(HashMap::new(), HashMap::new());
    let base_url = spawn_mock_cloud(mock).await;
    let mut rt = Runtime::new(Box::new(fresh_db().await));

    let error = update_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache_dir("absent"),
        &auth(),
        &mut rt,
        "parts",
        "latest",
        &|_, _| {},
        &dev_policy(),
    )
    .await
    .expect_err("there is nothing to update");

    assert_eq!(error.code(), "update_not_installed");
    assert!(
        !rt.registry().is_installed("parts"),
        "an update must never be a back door for installing something new"
    );
}
