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
use erplora_db::{testutil::fresh_db, Params};
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
        m.calls
            .lock()
            .unwrap()
            .push(format!("download:{id}@{asked}"));
        m.packages
            .get(&(id, asked))
            .map(|(z, _)| z.clone())
            .unwrap_or_default()
    }
    async fn mark_installed(
        State(m): State<Shared>,
        AxumPath(id): AxumPath<String>,
    ) -> Json<Value> {
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
        m.calls.lock().unwrap().push(format!(
            "plan:{requested}@{version}:known={}",
            already.len()
        ));

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
async fn fixture(tag: &str, mock: Shared) -> (axum::Router, String, AppState, std::path::PathBuf) {
    let cloud_base_url = spawn_mock_cloud(mock).await;
    let temp = std::env::temp_dir().join(format!("erplora-upd-route-{}-{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&temp);

    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "hub-upd");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
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
    std::fs::write(v1_dir.join("migrations/postgres/001_init.sql"), PARTS_INIT).unwrap();
    let mut rt = rt;
    rt.install_from_dir(&v1_dir)
        .await
        .expect("seed parts@1.0.0");

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
    let rt = state.runtime.read().await;
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
    let v2 = parts_package(
        "2.0.0",
        Some((
            "002_add_note.sql",
            "ALTER TABLE parts_item ADD COLUMN IF NOT EXISTS note TEXT;",
        )),
    );
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
        state
            .runtime
            .read()
            .await
            .registry()
            .module_version("parts"),
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
    let broken = parts_package(
        "2.0.0",
        Some((
            "002_broken.sql",
            "ALTER TABLE parts_missing ADD COLUMN note TEXT;",
        )),
    );
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
        state
            .runtime
            .read()
            .await
            .registry()
            .module_version("parts"),
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
        !state.runtime.read().await.registry().is_installed("ghost"),
        "an update must never be a back door for installing something new"
    );

    let _ = std::fs::remove_dir_all(temp);
}

// ── 5. What the owner is told about it afterwards (hub#564) ──────────────────────────────

/// An update that happened has to survive the request that caused it.
///
/// The response and the `module.updated` event carry the `from → to`, but both are gone the moment
/// the screen closes. If the transition is not written down **when it happens** it cannot be
/// recovered later: the hub knows the version it runs NOW, and a current state cannot be subtracted
/// from itself to produce a history. This is the assertion that keeps the door wired to the record.
#[tokio::test]
async fn an_update_leaves_a_trace_the_owner_can_read_later() {
    let v2 = parts_package("2.0.0", None);
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
    let (router, session, state, temp) = fixture("history", mock).await;

    let response = router
        .oneshot(update_request(&session, "{}"))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let rt = state.runtime.read().await;
    let history = erplora_runtime::update_history::recent(
        rt.db(),
        "hub-upd",
        erplora_runtime::update_history::DEFAULT_LIMIT,
        erplora_runtime::update_history::DEFAULT_MAX_AGE_DAYS,
    )
    .await
    .unwrap();

    assert_eq!(history.len(), 1, "one update, one entry: {history:?}");
    assert_eq!(history[0].component, "module");
    assert_eq!(history[0].id, "parts");
    assert_eq!(
        history[0].name, "Parts",
        "the name the owner reads, not the id (ADR-0254)"
    );
    assert_eq!(
        history[0].from_version, "1.0.0",
        "«2.0.0» alone says nothing"
    );
    assert_eq!(history[0].to_version, "2.0.0");
    assert_eq!(history[0].outcome, "updated");
    drop(rt);

    let _ = std::fs::remove_dir_all(temp);
}

/// A hub already on the latest version writes NOTHING.
///
/// Rule 1 of hub#564, checked at the door that gets pressed most: opening Apps and clicking
/// «Update» on something that is already current is a non-event, and a history that fills up with
/// non-events is one nobody reads twice.
#[tokio::test]
async fn pressing_update_on_something_already_current_writes_nothing() {
    let mock = Arc::new(MockCloud {
        packages: HashMap::new(),
        offered: HashMap::from([("parts".to_string(), vec!["1.0.0".to_string()])]),
        calls: Mutex::new(Vec::new()),
    });
    let (router, session, state, temp) = fixture("nonevent", mock).await;

    let response = router
        .oneshot(update_request(&session, "{}"))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let rt = state.runtime.read().await;
    let history = erplora_runtime::update_history::recent(
        rt.db(),
        "hub-upd",
        erplora_runtime::update_history::DEFAULT_LIMIT,
        erplora_runtime::update_history::DEFAULT_MAX_AGE_DAYS,
    )
    .await
    .unwrap();
    assert!(
        history.is_empty(),
        "nothing changed, so nothing is written: {history:?}"
    );
    drop(rt);

    let _ = std::fs::remove_dir_all(temp);
}

// ── 6. An explicit version cannot walk around the support pin or go backwards (hub#2546) ────────

/// What support writes when it pins a module on this hub (`hub_module.pinned_version`).
async fn pin_support_version(state: &AppState, version: &str) {
    let rt = state.runtime.read().await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("hub-upd"));
    p.insert("module_id".into(), json!("parts"));
    p.insert("pin".into(), json!(version));
    rt.db()
        .execute(
            "UPDATE hub_module SET pinned_version = :pin \
             WHERE hub_id = :hub_id AND module_id = :module_id",
            &p,
        )
        .await
        .expect("pin parts");
}

/// A marketplace that publishes `parts` 0.5.0, 1.0.0 and 2.0.0, every one of them installable: if
/// the door lets a version through, it really lands, so a refusal is the only way to stay put.
fn three_published_versions() -> Shared {
    let mut packages = HashMap::new();
    for version in ["0.5.0", "1.0.0", "2.0.0"] {
        let zip = parts_package(version, None);
        let sha = sha256_hex(&zip);
        packages.insert(("parts".to_string(), version.to_string()), (zip, sha));
    }
    Arc::new(MockCloud {
        packages,
        offered: HashMap::from([(
            "parts".to_string(),
            vec!["0.5.0".into(), "1.0.0".into(), "2.0.0".into()],
        )]),
        calls: Mutex::new(Vec::new()),
    })
}

/// The refusal hub#2546 asks for: its own code, nothing downloaded, the module where it was.
async fn assert_refused_and_untouched(
    response: axum::response::Response,
    mock: &Shared,
    state: &AppState,
) {
    assert_eq!(response.status(), StatusCode::CONFLICT);
    let body = json_body(response).await;
    assert_eq!(body["ok"], json!(false), "{body}");
    assert_eq!(body["code"], json!("update_version_not_offered"), "{body}");
    let calls = mock.calls.lock().unwrap().clone();
    assert!(
        !calls.iter().any(|c| c.starts_with("download:")),
        "a refused version is never downloaded: {calls:?}"
    );
    assert_eq!(recorded_version(state).await, "1.0.0");
    assert_eq!(
        state
            .runtime
            .read()
            .await
            .registry()
            .module_version("parts"),
        "1.0.0",
        "the module keeps serving the version it had"
    );
}

/// hub#2546: with support's pin on 1.0.0, an administrator asking the API for 0.5.0 got 0.5.0. The
/// pin is support's lever, not the owner's: an explicit version other than the pin is refused.
#[tokio::test]
async fn hub2546_an_explicit_older_version_does_not_walk_around_the_support_pin() {
    let mock = three_published_versions();
    let (router, session, state, temp) = fixture("hub2546-pin-down", mock.clone()).await;
    pin_support_version(&state, "1.0.0").await;

    let response = router
        .oneshot(update_request(&session, r#"{"version":"0.5.0"}"#))
        .await
        .unwrap();
    assert_refused_and_untouched(response, &mock, &state).await;

    let _ = std::fs::remove_dir_all(temp);
}

/// hub#2546: the pin also holds against an explicit NEWER version — «stay on 1.0.0 while 2.0.0 is
/// fixed» is exactly what the pin is for, and the version list (HUB-F24) offers nothing pinned.
#[tokio::test]
async fn hub2546_an_explicit_newer_version_does_not_walk_around_the_support_pin() {
    let mock = three_published_versions();
    let (router, session, state, temp) = fixture("hub2546-pin-up", mock.clone()).await;
    pin_support_version(&state, "1.0.0").await;

    let response = router
        .oneshot(update_request(&session, r#"{"version":"2.0.0"}"#))
        .await
        .unwrap();
    assert_refused_and_untouched(response, &mock, &state).await;

    let _ = std::fs::remove_dir_all(temp);
}

/// hub#2546: without a pin, an explicit version only goes forwards, like the version list
/// (HUB-F24). Going back would re-run a schema the newer version already moved past.
#[tokio::test]
async fn hub2546_an_explicit_older_version_is_refused_without_a_pin() {
    let mock = three_published_versions();
    let (router, session, state, temp) = fixture("hub2546-down", mock.clone()).await;

    let response = router
        .oneshot(update_request(&session, r#"{"version":"0.5.0"}"#))
        .await
        .unwrap();
    assert_refused_and_untouched(response, &mock, &state).await;

    let _ = std::fs::remove_dir_all(temp);
}

/// hub#2546, the other side: the guard refuses what the version list would not offer and nothing
/// else. An explicit newer version without a pin still installs.
#[tokio::test]
async fn hub2546_an_explicit_newer_version_without_a_pin_still_installs() {
    let mock = three_published_versions();
    let (router, session, state, temp) = fixture("hub2546-up", mock.clone()).await;

    let response = router
        .oneshot(update_request(&session, r#"{"version":"2.0.0"}"#))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = json_body(response).await;
    assert_eq!(body["data"]["updated"], json!(true), "{body}");
    assert_eq!(recorded_version(&state).await, "2.0.0");

    let _ = std::fs::remove_dir_all(temp);
}

/// hub#2546: asking explicitly for the pinned version is what support's pin already does on its
/// own (the resolver goes to the pin), so it goes through — the guard is about walking AROUND the
/// pin, not about the word «explicit».
#[tokio::test]
async fn hub2546_an_explicit_request_for_the_pinned_version_goes_to_the_pin() {
    let mock = three_published_versions();
    let (router, session, state, temp) = fixture("hub2546-pin-eq", mock.clone()).await;
    pin_support_version(&state, "0.5.0").await;

    let response = router
        .oneshot(update_request(&session, r#"{"version":"0.5.0"}"#))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = json_body(response).await;
    assert_eq!(body["data"]["version"], json!("0.5.0"), "{body}");
    assert_eq!(recorded_version(&state).await, "0.5.0");

    let _ = std::fs::remove_dir_all(temp);
}

/// hub#2546: `"latest"` is the resolver's word, not a version — it is not held to the explicit
/// version rule and goes where the resolver says.
#[tokio::test]
async fn hub2546_latest_is_still_the_resolver_and_not_an_explicit_version() {
    let mock = three_published_versions();
    let (router, session, state, temp) = fixture("hub2546-latest", mock.clone()).await;

    let response = router
        .oneshot(update_request(&session, r#"{"version":"latest"}"#))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = json_body(response).await;
    assert_eq!(body["data"]["version"], json!("2.0.0"), "{body}");
    assert_eq!(recorded_version(&state).await, "2.0.0");

    let _ = std::fs::remove_dir_all(temp);
}
