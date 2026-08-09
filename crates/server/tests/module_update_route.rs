//! `POST /api/modules/:id/update` end to end, through the REAL router (hub#516 · hub#675).
//!
//! The unit-level contract lives in `module_update_e2e.rs`. What this file exists for is the thing
//! that only shows up when the whole door is wired: **the update has to actually install the new
//! version**.
//!
//! It is easy to get a green «updated» that did nothing. With the install plan (ADR-0060) the hub
//! sends the Cloud its installed set, the Cloud answers `already_satisfied` for what is already
//! there, and `execute_plan` **skips** it — so an update routed through `install_from_cloud` reports
//! success without downloading a byte. The assertion below is the one that catches that: after the
//! call, `hub_module.version` must have MOVED.
//!
//! The other half is the failure: a version that cannot install must leave the module **serving the
//! one it had**, and say so with a warning — not a 5xx, because the hub is not broken.

use std::collections::HashMap;
use std::io::Write;
use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::{Path as AxumPath, Query, State};
use axum::http::{Request, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

// ── Mock marketplace ─────────────────────────────────────────────────────────────────────

struct MockCloud {
    /// `(module_id, version)` → (zip, sha256)
    packages: HashMap<(String, String), (Vec<u8>, String)>,
    /// module id → versions offered by `versions/`, newest last.
    offered: HashMap<String, Vec<String>>,
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

/// A package of `parts`@`version`. `001_init.sql` travels in every version with the same name and
/// the same body — `_hub_migrations` dedupes by filename, so it is applied once and never again.
/// `adds` is the migration the new version BRINGS (`(filename, sql)`), which is the only one that
/// actually runs on an update.
fn parts_package(version: &str, adds: Option<(&str, &str)>) -> Vec<u8> {
    let mut files = vec!["migrations/postgres/001_init.sql".to_string()];
    if let Some((name, _)) = adds {
        files.push(format!("migrations/postgres/{name}"));
    }
    let manifest = json!({
        "id": "parts",
        "name": "Parts",
        "version": version,
        "migrations": { "postgres": files },
    });
    let manifest = serde_json::to_string(&manifest).unwrap();
    let extra_path = adds.map(|(name, _)| format!("migrations/postgres/{name}"));
    let mut entries: Vec<(&str, &[u8])> = vec![
        ("module.json", manifest.as_bytes()),
        ("migrations/postgres/001_init.sql", PARTS_INIT.as_bytes()),
    ];
    if let (Some(path), Some((_, sql))) = (&extra_path, adds) {
        entries.push((path.as_str(), sql.as_bytes()));
    }
    build_zip(&entries)
}

const PARTS_INIT: &str =
    "CREATE TABLE IF NOT EXISTS parts_item (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);";

#[derive(serde::Deserialize)]
struct VersionQuery {
    version: Option<String>,
}

async fn spawn_mock_cloud(mock: Shared) -> String {
    async fn versions(State(m): State<Shared>, AxumPath(id): AxumPath<String>) -> Json<Value> {
        m.calls.lock().unwrap().push(format!("versions:{id}"));
        let list: Vec<Value> = m
            .offered
            .get(&id)
            .map(|versions| {
                versions
                    .iter()
                    .rev()
                    .map(|v| {
                        let sha = m
                            .packages
                            .get(&(id.clone(), v.clone()))
                            .map(|(_, s)| s.clone())
                            .unwrap_or_default();
                        json!({ "version": v, "is_active": true, "sha256": sha })
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
        m.calls.lock().unwrap().push(format!("download:{id}@{asked}"));
        m.packages
            .get(&(id, asked))
            .map(|(z, _)| z.clone())
            .unwrap_or_default()
    }
    async fn mark_installed(State(m): State<Shared>, AxumPath(id): AxumPath<String>) -> Json<Value> {
        m.calls.lock().unwrap().push(format!("mark:{id}"));
        Json(json!({ "ok": true }))
    }
    /// The REAL shape of the Cloud's plan: it drops whatever the hub says it already has. This is
    /// what turns a naive update into a no-op, so the mock must reproduce it faithfully.
    async fn install_plan(State(m): State<Shared>, Json(body): Json<Value>) -> Json<Value> {
        let requested = body
            .get("module_id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let already: Vec<String> = body
            .get("installed")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default();
        let version = body
            .get("version")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        m.calls
            .lock()
            .unwrap()
            .push(format!("plan:{requested}@{version}:known={}", already.len()));

        if already.contains(&requested) {
            return Json(json!({
                "requested": requested, "plan": [], "already_satisfied": [requested],
                "blocked": false, "blocked_on": [],
            }));
        }
        let version = if version.is_empty() {
            m.offered
                .get(&requested)
                .and_then(|v| v.last().cloned())
                .unwrap_or_default()
        } else {
            version
        };
        let sha = m
            .packages
            .get(&(requested.clone(), version.clone()))
            .map(|(_, s)| s.clone())
            .unwrap_or_default();
        Json(json!({
            "requested": requested,
            "plan": [{
                "module_id": requested, "version": version, "sha256": sha, "tier": "free",
                "entitled": true, "requires_purchase": false, "reason": "requested",
            }],
            "already_satisfied": [],
            "blocked": false,
            "blocked_on": [],
        }))
    }
    let router = Router::new()
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
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    format!("http://{addr}")
}

// ── Hub under test ───────────────────────────────────────────────────────────────────────

/// A hub with `parts@1.0.0` already installed, its router, and an admin session.
async fn fixture(
    tag: &str,
    mock: Shared,
) -> (axum::Router, String, AppState, std::path::PathBuf) {
    let cloud_base_url = spawn_mock_cloud(mock).await;
    let temp = std::env::temp_dir().join(format!("erplora-upd-route-{}-{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&temp);

    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "hub-upd");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin_id, 3600, None).await.unwrap();

    // The starting point: v1 installed from a package on disk (as a boot would leave it).
    let v1_dir = temp.join("seed").join("1.0.0");
    std::fs::create_dir_all(v1_dir.join("migrations/postgres")).unwrap();
    std::fs::write(
        v1_dir.join("module.json"),
        serde_json::to_string(&json!({
            "id": "parts", "name": "Parts", "version": "1.0.0",
            "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
        }))
        .unwrap(),
    )
    .unwrap();
    std::fs::write(
        v1_dir.join("migrations/postgres/001_init.sql"),
        PARTS_INIT,
    )
    .unwrap();
    let mut rt = rt;
    rt.install_from_dir(&v1_dir).await.expect("seed parts@1.0.0");

    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-upd".into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        // Present so the hub can talk to the marketplace on its own behalf.
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        // Empty ring ⇒ `Sha256Only` (ADR-0194): integrity still mandatory, signature not required.
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: None,
    };
    let state = AppState::with_config(rt, cfg);
    (app(state.clone()), session, state, temp)
}

fn update_request(session: &str, body: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/modules/parts/update")
        .header("x-hub-session", session)
        .header("content-type", "application/json")
        .body(Body::from(body.to_owned()))
        .unwrap()
}

async fn json_body(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// What `hub_module` says this hub runs — the only answer that survives a restart.
async fn recorded_version(state: &AppState) -> String {
    let rt = state.runtime.lock().await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("hub-upd"));
    p.insert("module_id".into(), json!("parts"));
    rt.db()
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

// ── 1. The update actually installs ──────────────────────────────────────────────────────

/// The regression this file exists for: with the plan skipping what is already installed, an update
/// can answer «updated» having downloaded nothing. Here the version must MOVE.
#[tokio::test]
async fn updating_really_installs_the_new_version_and_does_not_just_say_it_did() {
    let v2 = parts_package("2.0.0", Some(("002_add_note.sql", "ALTER TABLE parts_item ADD COLUMN IF NOT EXISTS note TEXT;")));
    let mut packages = HashMap::new();
    packages.insert(
        ("parts".to_string(), "2.0.0".to_string()),
        (v2.clone(), sha256_hex(&v2)),
    );
    let mock = Arc::new(MockCloud {
        packages,
        offered: HashMap::from([("parts".to_string(), vec!["2.0.0".to_string()])]),
        calls: Mutex::new(Vec::new()),
    });
    let (router, session, state, temp) = fixture("installs", mock.clone()).await;

    let response = router
        .oneshot(update_request(&session, "{}"))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = json_body(response).await;

    assert_eq!(body["ok"], json!(true), "{body}");
    assert_eq!(body["data"]["updated"], json!(true), "{body}");
    assert_eq!(body["data"]["from"], json!("1.0.0"), "{body}");
    assert_eq!(body["data"]["version"], json!("2.0.0"), "{body}");

    let calls = mock.calls.lock().unwrap().clone();
    assert!(
        calls.iter().any(|c| c == "download:parts@2.0.0"),
        "the new version has to be DOWNLOADED, not assumed: {calls:?}"
    );
    assert_eq!(
        recorded_version(&state).await,
        "2.0.0",
        "hub_module must point at the new version, or the next restart undoes the update"
    );
    assert_eq!(
        state.runtime.lock().await.registry().module_version("parts"),
        "2.0.0",
        "and the live runtime serves it"
    );

    let _ = std::fs::remove_dir_all(temp);
}

// ── 2. A version that cannot install leaves the module serving the old one ───────────────

/// 200 + `warning`, not 5xx: the update did not happen, but the hub is **not** broken — it is
/// serving exactly what it served a minute ago.
#[tokio::test]
async fn a_version_that_cannot_install_keeps_the_old_one_and_says_so_without_a_5xx() {
    // The v2 package is corrupt: its migration explodes (the table it alters does not exist).
    // Passes the migration guard (expand, own table prefix) but explodes: the table is not there.
    let broken = parts_package("2.0.0", Some(("002_broken.sql", "ALTER TABLE parts_missing ADD COLUMN note TEXT;")));
    let mut packages = HashMap::new();
    packages.insert(
        ("parts".to_string(), "2.0.0".to_string()),
        (broken.clone(), sha256_hex(&broken)),
    );
    let mock = Arc::new(MockCloud {
        packages,
        offered: HashMap::from([("parts".to_string(), vec!["2.0.0".to_string()])]),
        calls: Mutex::new(Vec::new()),
    });
    let (router, session, state, temp) = fixture("rollback", mock).await;

    let response = router
        .oneshot(update_request(&session, "{}"))
        .await
        .unwrap();
    assert_eq!(
        response.status(),
        StatusCode::OK,
        "a module that keeps working is not a server error"
    );
    let body = json_body(response).await;

    assert_eq!(body["ok"], json!(true), "{body}");
    assert_eq!(body["data"]["updated"], json!(false), "{body}");
    assert_eq!(body["data"]["version"], json!("1.0.0"), "{body}");
    assert_eq!(
        body["warning"]["code"],
        json!("module.update_failed_kept_previous"),
        "the failure is NAMED, not swallowed: {body}"
    );

    assert_eq!(
        state.runtime.lock().await.registry().module_version("parts"),
        "1.0.0",
        "the module still serves the version that works"
    );
    assert_eq!(recorded_version(&state).await, "1.0.0");

    let _ = std::fs::remove_dir_all(temp);
}

// ── 3. Already on the latest ─────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_hub_already_on_the_latest_is_told_so_without_downloading_anything() {
    let v1 = parts_package("1.0.0", None);
    let mut packages = HashMap::new();
    packages.insert(
        ("parts".to_string(), "1.0.0".to_string()),
        (v1.clone(), sha256_hex(&v1)),
    );
    let mock = Arc::new(MockCloud {
        packages,
        offered: HashMap::from([("parts".to_string(), vec!["1.0.0".to_string()])]),
        calls: Mutex::new(Vec::new()),
    });
    let (router, session, _state, temp) = fixture("uptodate", mock.clone()).await;

    let response = router
        .oneshot(update_request(&session, "{}"))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = json_body(response).await;
    assert_eq!(body["data"]["updated"], json!(false), "{body}");
    assert_eq!(body["data"]["version"], json!("1.0.0"), "{body}");

    let calls = mock.calls.lock().unwrap().clone();
    assert!(
        !calls.iter().any(|c| c.starts_with("download:")),
        "nothing to update ⇒ nothing downloaded: {calls:?}"
    );

    let _ = std::fs::remove_dir_all(temp);
}

// ── 4. Updating something this hub does not have ─────────────────────────────────────────

#[tokio::test]
async fn updating_a_module_this_hub_does_not_have_is_a_404_not_an_install() {
    let mock = Arc::new(MockCloud {
        packages: HashMap::new(),
        offered: HashMap::new(),
        calls: Mutex::new(Vec::new()),
    });
    let (router, session, state, temp) = fixture("absent", mock).await;

    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/modules/ghost/update")
                .header("x-hub-session", &session)
                .header("content-type", "application/json")
                .body(Body::from("{}"))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let body = json_body(response).await;
    assert_eq!(body["code"], json!("update_not_installed"), "{body}");
    assert!(
        !state.runtime.lock().await.registry().is_installed("ghost"),
        "an update must never be a back door for installing something new"
    );

    let _ = std::fs::remove_dir_all(temp);
}
