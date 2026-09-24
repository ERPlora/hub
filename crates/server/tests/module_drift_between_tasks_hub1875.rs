//! hub#1875 — two tasks of the SAME hub, one database: what one of them installs or updates, the
//! other one has to end up serving too.
//!
//! Measured on `banco-pre` on 2026-09-15 (Loki): a rolling deploy starts the new task first, and
//! the new task builds its module registry from `hub_module` as it boots. The owner pressed
//! «Update» on `verifactu` 1.5.38 → 1.5.39 and the request landed on the OUTGOING task, which was
//! still serving while it drained. That task wrote `hub_module.version = 1.5.39` — but the task that
//! stayed alive had read 1.5.38 a minute earlier and never looked again. From then on the module
//! list and `versions` (memory) said 1.5.38, `updates` (the database) said 1.5.39, and the runtime
//! kept serving the code of 1.5.38 until someone pressed «Update» again.
//!
//! Each test here builds the two tasks as two `AppState`s over two connection pools on the same
//! schema — two containers, one Postgres — and asserts that the reconciliation brings the task that
//! did NOT do the operation to what the database says, without losing what it was serving when that
//! cannot be done.

use std::collections::HashMap;
use std::io::Write;
use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::{Path as AxumPath, Query, State};
use axum::http::{Request, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::{testutil::two_adapters_sharing_a_schema, Params};
use erplora_runtime::Runtime;
use erplora_server::module_reconcile::ModuleReconciler;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-drift";

// ── Mock marketplace (same shape as `module_update_route.rs`) ─────────────────────────────

struct MockCloud {
    /// `(module_id, version)` → (zip, sha256)
    packages: HashMap<(String, String), (Vec<u8>, String)>,
    /// module id → versions offered, newest last.
    offered: HashMap<String, Vec<String>>,
    calls: Mutex<Vec<String>>,
}

type Shared = Arc<MockCloud>;

impl MockCloud {
    fn with(packages: &[(&str, &str, Vec<u8>)]) -> Shared {
        let mut map = HashMap::new();
        let mut offered: HashMap<String, Vec<String>> = HashMap::new();
        for (id, version, zip) in packages {
            map.insert(
                (id.to_string(), version.to_string()),
                (zip.clone(), sha256_hex(zip)),
            );
            offered
                .entry(id.to_string())
                .or_default()
                .push(version.to_string());
        }
        Arc::new(MockCloud {
            packages: map,
            offered,
            calls: Mutex::new(Vec::new()),
        })
    }

    fn downloads(&self) -> Vec<String> {
        self.calls
            .lock()
            .unwrap()
            .iter()
            .filter(|c| c.starts_with("download:"))
            .cloned()
            .collect()
    }

    fn call_count(&self) -> usize {
        self.calls.lock().unwrap().len()
    }
}

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

const INIT_SQL: &str =
    "CREATE TABLE IF NOT EXISTS {id}_item (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);";

fn manifest(id: &str, version: &str) -> String {
    serde_json::to_string(&json!({
        "id": id,
        "name": id,
        "version": version,
        "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
    }))
    .unwrap()
}

fn package(id: &str, version: &str) -> Vec<u8> {
    let manifest = manifest(id, version);
    let sql = INIT_SQL.replace("{id}", id);
    build_zip(&[
        ("module.json", manifest.as_bytes()),
        ("migrations/postgres/001_init.sql", sql.as_bytes()),
    ])
}

/// The same package extracted on disk, as a boot leaves it before the task starts serving.
fn package_dir(root: &std::path::Path, id: &str, version: &str) -> std::path::PathBuf {
    let dir = root.join("seed").join(id).join(version);
    std::fs::create_dir_all(dir.join("migrations/postgres")).unwrap();
    std::fs::write(dir.join("module.json"), manifest(id, version)).unwrap();
    std::fs::write(
        dir.join("migrations/postgres/001_init.sql"),
        INIT_SQL.replace("{id}", id),
    )
    .unwrap();
    dir
}

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
    /// The Cloud's real plan shape: whatever the hub says it already has is `already_satisfied`.
    async fn install_plan(State(m): State<Shared>, Json(body): Json<Value>) -> Json<Value> {
        let requested = body["module_id"].as_str().unwrap_or_default().to_string();
        let already: Vec<String> = body["installed"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default();
        let version = body["version"].as_str().unwrap_or("").to_string();
        m.calls
            .lock()
            .unwrap()
            .push(format!("plan:{requested}@{version}"));
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

// ── The two tasks ─────────────────────────────────────────────────────────────────────────

struct TwoTasks {
    /// The task that performs the operation (in production: the outgoing one, draining).
    outgoing: AppState,
    /// The task that stays alive and must catch up.
    staying: AppState,
    /// A session both tasks accept: sessions live in the shared database.
    session: String,
    temp: std::path::PathBuf,
}

fn config(cloud_base_url: &str, cache: std::path::PathBuf, media: std::path::PathBuf) -> HubConfig {
    HubConfig {
        demo: false,
        hub_id: HUB.into(),
        cloud_base_url: cloud_base_url.to_string(),
        module_cache: cache,
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: media,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

/// Both tasks booted with `parts@1.0.0`, each with its OWN download cache (two containers).
async fn two_tasks(tag: &str, mock: Shared) -> TwoTasks {
    let cloud = spawn_mock_cloud(mock).await;
    let temp = std::env::temp_dir().join(format!("erplora-drift-{}-{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&temp);
    let seed = package_dir(&temp, "parts", "1.0.0");

    let (db_out, db_stay) = two_adapters_sharing_a_schema().await;

    let mut rt_out = Runtime::with_hub_id(Box::new(db_out), HUB);
    rt_out.ensure_system_tables().await.unwrap();
    let admin = rt_out
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let session = rt_out.create_session(&admin, 3600, None).await.unwrap();
    rt_out
        .install_from_dir(&seed)
        .await
        .expect("outgoing: seed parts@1.0.0");

    let mut rt_stay = Runtime::with_hub_id(Box::new(db_stay), HUB);
    rt_stay.ensure_system_tables().await.unwrap();
    rt_stay
        .install_from_dir(&seed)
        .await
        .expect("staying: seed parts@1.0.0");

    let outgoing = AppState::with_config(
        rt_out,
        config(&cloud, temp.join("cache-outgoing"), temp.join("media-out")),
    );
    let staying = AppState::with_config(
        rt_stay,
        config(&cloud, temp.join("cache-staying"), temp.join("media-stay")),
    );
    TwoTasks {
        outgoing,
        staying,
        session,
        temp,
    }
}

async fn json_body(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

async fn call(state: &AppState, session: &str, method: &str, uri: &str, body: &str) -> Value {
    let request = Request::builder()
        .method(method)
        .uri(uri)
        .header("x-hub-session", session)
        .header("content-type", "application/json")
        .body(Body::from(body.to_owned()))
        .unwrap();
    let response = app(state.clone()).oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK, "{method} {uri}");
    json_body(response).await
}

/// What `GET /api/modules` — the module list the owner looks at — says about `id`.
async fn listed(state: &AppState, session: &str, id: &str) -> Option<Value> {
    let body = call(state, session, "GET", "/api/modules", "").await;
    body["data"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["id"] == json!(id))
        .cloned()
}

async fn recorded(state: &AppState, id: &str) -> (String, String) {
    let rt = state.runtime.read().await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("module_id".into(), json!(id));
    let res = rt
        .db()
        .query(
            "SELECT version, status FROM hub_module WHERE hub_id = :hub_id AND module_id = :module_id",
            &p,
        )
        .await
        .unwrap();
    let row = res.rows.first().expect("hub_module row");
    (
        row["version"].as_str().unwrap_or_default().to_string(),
        row["status"].as_str().unwrap_or_default().to_string(),
    )
}

// ── 1. The report of hub#1875 ─────────────────────────────────────────────────────────────

/// The exact sequence of banco-pre: update on one task, read on the other. After reconciling, the
/// list, `versions` and the code the runtime actually serves are the new version — and it comes
/// from the copy of the package the other task already stored in the database, not from a second
/// download.
#[tokio::test]
async fn an_update_made_by_the_other_task_is_what_this_task_lists_and_serves() {
    let mock = MockCloud::with(&[
        ("parts", "1.0.0", package("parts", "1.0.0")),
        ("parts", "2.0.0", package("parts", "2.0.0")),
    ]);
    let t = two_tasks("update", mock.clone()).await;

    let updated = call(
        &t.outgoing,
        &t.session,
        "POST",
        "/api/modules/parts/update",
        "{}",
    )
    .await;
    assert_eq!(updated["data"]["version"], json!("2.0.0"), "{updated}");
    assert_eq!(recorded(&t.staying, "parts").await.0, "2.0.0");
    let downloads_before = mock.downloads();

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert_eq!(
        report.reloaded,
        vec![("parts".to_string(), "2.0.0".to_string())],
        "{report:?}"
    );
    assert_eq!(
        listed(&t.staying, &t.session, "parts").await.unwrap()["version"],
        json!("2.0.0"),
        "the module list must show the version the hub runs"
    );
    let versions = call(
        &t.staying,
        &t.session,
        "GET",
        "/api/modules/parts/versions",
        "",
    )
    .await;
    assert_eq!(versions["data"]["installed"], json!("2.0.0"), "{versions}");
    assert_eq!(
        t.staying
            .runtime
            .read()
            .await
            .registry()
            .module_version("parts"),
        "2.0.0",
        "and the runtime serves the new code, not only a new label"
    );
    assert_eq!(
        mock.downloads(),
        downloads_before,
        "the package the other task stored is enough: no second download"
    );

    let _ = std::fs::remove_dir_all(&t.temp);
}

// ── 2. An install made by the other task ──────────────────────────────────────────────────

/// A module installed through the other task does not exist here at all until reconciled. Without a
/// stored copy of THAT version the marketplace is the source, at exactly the recorded version.
#[tokio::test]
async fn a_module_installed_by_the_other_task_appears_here_at_the_recorded_version() {
    let mock = MockCloud::with(&[
        ("parts", "1.0.0", package("parts", "1.0.0")),
        ("extras", "1.0.0", package("extras", "1.0.0")),
        ("extras", "1.1.0", package("extras", "1.1.0")),
    ]);
    let t = two_tasks("install", mock.clone()).await;
    let extras = package_dir(&t.temp, "extras", "1.0.0");
    t.outgoing
        .runtime
        .write()
        .await
        .install_from_dir(&extras)
        .await
        .unwrap();
    assert!(listed(&t.staying, &t.session, "extras").await.is_none());

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert_eq!(
        report.reloaded,
        vec![("extras".to_string(), "1.0.0".to_string())],
        "{report:?}"
    );
    assert_eq!(
        listed(&t.staying, &t.session, "extras").await.unwrap()["version"],
        json!("1.0.0"),
        "the recorded version, not the newest one the marketplace offers"
    );
    assert!(
        mock.downloads()
            .contains(&"download:extras@1.0.0".to_string()),
        "{:?}",
        mock.downloads()
    );

    let _ = std::fs::remove_dir_all(&t.temp);
}

// ── 3. The admin's «off» survives ─────────────────────────────────────────────────────────

/// Reloading a module is not activating it: if the other task left it switched off, it is switched
/// off here too — in memory and in the database.
#[tokio::test]
async fn a_module_the_other_task_left_switched_off_stays_off_here() {
    let mock = MockCloud::with(&[
        ("parts", "1.0.0", package("parts", "1.0.0")),
        ("parts", "2.0.0", package("parts", "2.0.0")),
    ]);
    let t = two_tasks("inactive", mock.clone()).await;
    call(
        &t.outgoing,
        &t.session,
        "POST",
        "/api/modules/parts/update",
        "{}",
    )
    .await;
    t.outgoing
        .runtime
        .write()
        .await
        .deactivate("parts")
        .await
        .unwrap();
    assert_eq!(
        recorded(&t.staying, "parts").await,
        ("2.0.0".into(), "inactive".into())
    );

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert_eq!(report.reloaded.len(), 1, "{report:?}");
    let parts = listed(&t.staying, &t.session, "parts").await.unwrap();
    assert_eq!(parts["version"], json!("2.0.0"), "{parts}");
    assert_eq!(parts["status"], json!("inactive"), "{parts}");
    assert_eq!(
        recorded(&t.staying, "parts").await,
        ("2.0.0".into(), "inactive".into()),
        "reloading must not write «active» over the admin's choice"
    );

    let _ = std::fs::remove_dir_all(&t.temp);
}

// ── 4. What cannot be loaded ──────────────────────────────────────────────────────────────

/// A recorded version that nobody can provide (no cache, no stored copy, not in the marketplace):
/// the task keeps serving what it had — never ends up WITHOUT the module — and does not hammer the
/// marketplace for the same version on every tick.
#[tokio::test]
async fn a_version_that_cannot_be_loaded_keeps_the_old_one_and_is_not_retried_every_tick() {
    let mock = MockCloud::with(&[("parts", "1.0.0", package("parts", "1.0.0"))]);
    let t = two_tasks("unloadable", mock.clone()).await;
    {
        let rt = t.outgoing.runtime.read().await;
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(HUB));
        rt.db()
            .execute(
                "UPDATE hub_module SET version = '9.9.9' WHERE hub_id = :hub_id AND module_id = 'parts'",
                &p,
            )
            .await
            .unwrap();
    }
    let reconciler = ModuleReconciler::new();

    let first = reconciler.reconcile_once(&t.staying).await;
    assert!(first.reloaded.is_empty(), "{first:?}");
    assert_eq!(first.failed.len(), 1, "{first:?}");
    assert_eq!(first.failed[0].0, "parts");
    assert_eq!(first.failed[0].1, "9.9.9");
    assert_eq!(
        t.staying
            .runtime
            .read()
            .await
            .registry()
            .module_version("parts"),
        "1.0.0",
        "a failed reload leaves the module serving, never missing"
    );
    let calls_after_first = mock.call_count();

    let second = reconciler.reconcile_once(&t.staying).await;
    assert!(
        second.reloaded.is_empty() && second.failed.is_empty(),
        "{second:?}"
    );
    assert_eq!(
        mock.call_count(),
        calls_after_first,
        "the same version is not asked for again on every tick"
    );

    let _ = std::fs::remove_dir_all(&t.temp);
}

// ── 5. The normal case costs nothing ──────────────────────────────────────────────────────

#[tokio::test]
async fn when_memory_and_database_agree_nothing_is_touched() {
    let mock = MockCloud::with(&[("parts", "1.0.0", package("parts", "1.0.0"))]);
    let t = two_tasks("agree", mock.clone()).await;

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert!(
        report.reloaded.is_empty() && report.failed.is_empty(),
        "{report:?}"
    );
    assert!(
        report.removed.is_empty() && report.status_changed.is_empty(),
        "{report:?}"
    );
    assert_eq!(mock.call_count(), 0, "{:?}", mock.calls.lock().unwrap());

    let _ = std::fs::remove_dir_all(&t.temp);
}

// ── 6. A package that is not what it says ────────────────────────────────────────────────

/// The marketplace answers the recorded version with a package whose manifest carries ANOTHER one
/// (a mislabelled publication). That is not «reloaded at the recorded version», and saying so would
/// hide that this task now runs something nobody asked for.
#[tokio::test]
async fn a_package_that_carries_another_version_is_reported_as_a_failure() {
    let mislabelled = package("extras", "1.2.0");
    let mock = MockCloud::with(&[
        ("parts", "1.0.0", package("parts", "1.0.0")),
        ("extras", "1.0.0", mislabelled),
    ]);
    let t = two_tasks("mislabelled", mock.clone()).await;
    let extras = package_dir(&t.temp, "extras", "1.0.0");
    t.outgoing
        .runtime
        .write()
        .await
        .install_from_dir(&extras)
        .await
        .unwrap();

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert!(report.reloaded.is_empty(), "{report:?}");
    assert_eq!(report.failed.len(), 1, "{report:?}");
    assert_eq!(
        (report.failed[0].0.as_str(), report.failed[0].1.as_str()),
        ("extras", "1.0.0"),
        "{report:?}"
    );

    let _ = std::fs::remove_dir_all(&t.temp);
}

// ── 7. What fell in cascade stays fallen ─────────────────────────────────────────────────

/// A module that went off IN CASCADE because its dependency was switched off (ADR-0128) is
/// reloaded as what it is — `inactive_auto` — and not as active on top of a dependency that is off.
#[tokio::test]
async fn a_module_that_fell_in_cascade_is_reloaded_still_fallen() {
    let addon_manifest = serde_json::to_string(&json!({
        "id": "addon", "name": "addon", "version": "1.0.0", "depends_on": ["parts"],
        "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
    }))
    .unwrap();
    let addon_sql = INIT_SQL.replace("{id}", "addon");
    let addon_zip = build_zip(&[
        ("module.json", addon_manifest.as_bytes()),
        ("migrations/postgres/001_init.sql", addon_sql.as_bytes()),
    ]);
    let mock = MockCloud::with(&[
        ("parts", "1.0.0", package("parts", "1.0.0")),
        ("addon", "1.0.0", addon_zip),
    ]);
    let t = two_tasks("cascade", mock.clone()).await;
    let addon = t.temp.join("seed").join("addon").join("1.0.0");
    std::fs::create_dir_all(addon.join("migrations/postgres")).unwrap();
    std::fs::write(addon.join("module.json"), &addon_manifest).unwrap();
    std::fs::write(addon.join("migrations/postgres/001_init.sql"), &addon_sql).unwrap();
    {
        let mut rt = t.outgoing.runtime.write().await;
        rt.install_from_dir(&addon).await.unwrap();
        rt.deactivate("parts").await.unwrap();
    }
    assert_eq!(recorded(&t.staying, "addon").await.1, "inactive_auto");

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert!(
        report
            .reloaded
            .contains(&("addon".to_string(), "1.0.0".to_string())),
        "{report:?}"
    );
    assert_eq!(
        listed(&t.staying, &t.session, "addon").await.unwrap()["status"],
        json!("inactive_auto")
    );
    assert_eq!(recorded(&t.staying, "addon").await.1, "inactive_auto");

    let _ = std::fs::remove_dir_all(&t.temp);
}

// ── 8. `hub_module` has no topological order ─────────────────────────────────────────────

/// The other task installs a module AND the dependency it pulls in. `hub_module` keeps no
/// topological order (the boot restore loops for the same reason), so the dependent may come first
/// in a pass: failing it then is a matter of turn, not a version nobody can provide — it has to be
/// loaded once its dependency is, and not written off until `hub_module` changes.
#[tokio::test]
async fn a_dependent_read_before_its_dependency_is_loaded_in_the_same_pass() {
    let addon_manifest = serde_json::to_string(&json!({
        "id": "addon", "name": "addon", "version": "1.0.0", "depends_on": ["extras"],
        "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
    }))
    .unwrap();
    let addon_sql = INIT_SQL.replace("{id}", "addon");
    let addon_zip = build_zip(&[
        ("module.json", addon_manifest.as_bytes()),
        ("migrations/postgres/001_init.sql", addon_sql.as_bytes()),
    ]);
    // Neither is in the marketplace: the copies the other task stored are the only source, as
    // after any install through the route (the marketplace path pulls dependencies by itself).
    let mock = MockCloud::with(&[("parts", "1.0.0", package("parts", "1.0.0"))]);
    let t = two_tasks("topo", mock.clone()).await;
    let extras = package_dir(&t.temp, "extras", "1.0.0");
    let addon = t.temp.join("seed").join("addon").join("1.0.0");
    std::fs::create_dir_all(addon.join("migrations/postgres")).unwrap();
    std::fs::write(addon.join("module.json"), &addon_manifest).unwrap();
    std::fs::write(addon.join("migrations/postgres/001_init.sql"), &addon_sql).unwrap();
    {
        let mut rt = t.outgoing.runtime.write().await;
        rt.install_from_dir(&extras).await.unwrap();
        rt.install_from_dir(&addon).await.unwrap();
        for (id, zip) in [("extras", package("extras", "1.0.0")), ("addon", addon_zip)] {
            erplora_runtime::module_package::save(
                rt.db(),
                HUB,
                id,
                "1.0.0",
                &sha256_hex(&zip),
                None,
                &zip,
            )
            .await
            .unwrap();
        }
        // The dependency's row rewritten after the dependent's: a plain scan now reads the dependent
        // first — how a real table ends up out of order after enough writes.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(HUB));
        rt.db()
            .execute(
                "WITH gone AS (DELETE FROM hub_module WHERE hub_id = :hub_id AND module_id = 'extras' RETURNING *) \
                 INSERT INTO hub_module SELECT * FROM gone",
                &p,
            )
            .await
            .unwrap();
        let order = rt
            .db()
            .query(
                "SELECT module_id FROM hub_module WHERE hub_id = :hub_id",
                &p,
            )
            .await
            .unwrap();
        let order: Vec<&str> = order
            .rows
            .iter()
            .filter_map(|r| r["module_id"].as_str())
            .collect();
        assert!(
            order.iter().position(|m| *m == "addon") < order.iter().position(|m| *m == "extras"),
            "the scan must read the dependent first for this test to mean anything: {order:?}"
        );
    }

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert!(report.failed.is_empty(), "{report:?}");
    assert!(
        report
            .reloaded
            .contains(&("addon".to_string(), "1.0.0".to_string())),
        "{report:?}"
    );
    assert_eq!(
        listed(&t.staying, &t.session, "addon").await.unwrap()["version"],
        json!("1.0.0")
    );

    let _ = std::fs::remove_dir_all(&t.temp);
}

// ── 9. The loop `serve()` starts ─────────────────────────────────────────────────────────

/// What `serve()` launches after the boot restore: nobody calls `reconcile_once` by hand in
/// production, so the loop itself has to bring the staying task to the other task's update.
#[tokio::test]
async fn the_loop_serve_starts_catches_up_without_anyone_calling_it() {
    let mock = MockCloud::with(&[
        ("parts", "1.0.0", package("parts", "1.0.0")),
        ("parts", "2.0.0", package("parts", "2.0.0")),
    ]);
    let t = two_tasks("loop", mock.clone()).await;
    let reconciling = erplora_server::module_reconcile::spawn(
        t.staying.clone(),
        std::time::Duration::from_millis(100),
    );

    call(
        &t.outgoing,
        &t.session,
        "POST",
        "/api/modules/parts/update",
        "{}",
    )
    .await;

    let mut listed_version = Value::Null;
    for _ in 0..100 {
        listed_version = listed(&t.staying, &t.session, "parts").await.unwrap()["version"].clone();
        if listed_version == json!("2.0.0") {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    }
    reconciling.abort();
    assert_eq!(listed_version, json!("2.0.0"));

    let _ = std::fs::remove_dir_all(&t.temp);
}

// ── hub#2039: what the other task uninstalls or switches on/off ──────────────────────────

/// `addon@1.0.0`, which needs `parts`, extracted on disk.
fn addon_dir(temp: &std::path::Path) -> std::path::PathBuf {
    let dir = temp.join("seed").join("addon").join("1.0.0");
    std::fs::create_dir_all(dir.join("migrations/postgres")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string(&json!({
            "id": "addon", "name": "addon", "version": "1.0.0", "depends_on": ["parts"],
            "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
        }))
        .unwrap(),
    )
    .unwrap();
    std::fs::write(
        dir.join("migrations/postgres/001_init.sql"),
        INIT_SQL.replace("{id}", "addon"),
    )
    .unwrap();
    dir
}

async fn has_row(state: &AppState, id: &str) -> bool {
    let rt = state.runtime.read().await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("module_id".into(), json!(id));
    !rt.db()
        .query(
            "SELECT 1 FROM hub_module WHERE hub_id = :hub_id AND module_id = :module_id",
            &p,
        )
        .await
        .unwrap()
        .rows
        .is_empty()
}

/// Uninstalled through the other task: here it stops being listed AND stops existing for the
/// dispatcher — and nothing is written back, the other task already did all the writing.
#[tokio::test]
async fn a_module_uninstalled_by_the_other_task_is_gone_here_too() {
    let mock = MockCloud::with(&[("parts", "1.0.0", package("parts", "1.0.0"))]);
    let t = two_tasks("uninstall", mock.clone()).await;
    t.outgoing
        .runtime
        .write()
        .await
        .uninstall("parts")
        .await
        .unwrap();
    assert!(listed(&t.staying, &t.session, "parts").await.is_some());

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert_eq!(report.removed, vec!["parts".to_string()], "{report:?}");
    assert!(listed(&t.staying, &t.session, "parts").await.is_none());
    assert!(
        !t.staying
            .runtime
            .read()
            .await
            .registry()
            .is_installed("parts"),
        "its queries and commands must stop existing here, not only its row in the list"
    );
    assert!(!has_row(&t.staying, "parts").await, "nothing written back");
    assert_eq!(mock.call_count(), 0, "{:?}", mock.calls.lock().unwrap());

    let _ = std::fs::remove_dir_all(&t.temp);
}

/// Switched off through the other task, same version: here it is off too, and the database keeps
/// saying «off» (following is reading, not deciding again).
#[tokio::test]
async fn a_module_switched_off_by_the_other_task_is_off_here_too() {
    let mock = MockCloud::with(&[("parts", "1.0.0", package("parts", "1.0.0"))]);
    let t = two_tasks("switch-off", mock.clone()).await;
    t.outgoing
        .runtime
        .write()
        .await
        .deactivate("parts")
        .await
        .unwrap();
    assert_eq!(
        listed(&t.staying, &t.session, "parts").await.unwrap()["status"],
        json!("active")
    );

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert!(
        report.reloaded.is_empty(),
        "same version: nothing to reload {report:?}"
    );
    assert_eq!(report.status_changed.len(), 1, "{report:?}");
    assert_eq!(
        listed(&t.staying, &t.session, "parts").await.unwrap()["status"],
        json!("inactive")
    );
    assert!(!t.staying.runtime.read().await.registry().is_active("parts"));
    assert_eq!(recorded(&t.staying, "parts").await.1, "inactive");
    assert_eq!(mock.call_count(), 0, "{:?}", mock.calls.lock().unwrap());

    let _ = std::fs::remove_dir_all(&t.temp);
}

/// And back on: switching it on through the other task turns it on here too.
#[tokio::test]
async fn a_module_switched_back_on_by_the_other_task_is_on_here_too() {
    let mock = MockCloud::with(&[("parts", "1.0.0", package("parts", "1.0.0"))]);
    let t = two_tasks("switch-on", mock.clone()).await;
    let reconciler = ModuleReconciler::new();
    t.outgoing
        .runtime
        .write()
        .await
        .deactivate("parts")
        .await
        .unwrap();
    reconciler.reconcile_once(&t.staying).await;
    assert!(!t.staying.runtime.read().await.registry().is_active("parts"));

    t.outgoing
        .runtime
        .write()
        .await
        .activate("parts")
        .await
        .unwrap();
    let report = reconciler.reconcile_once(&t.staying).await;

    assert_eq!(report.status_changed.len(), 1, "{report:?}");
    assert_eq!(
        listed(&t.staying, &t.session, "parts").await.unwrap()["status"],
        json!("active")
    );
    assert!(t.staying.runtime.read().await.registry().is_active("parts"));

    let _ = std::fs::remove_dir_all(&t.temp);
}

/// Switching off a dependency through the other task takes its dependents down IN CASCADE there;
/// here each one ends as the database recorded it — the root `inactive`, the dependent
/// `inactive_auto` — so that switching the root back on revives the dependent (ADR-0128).
#[tokio::test]
async fn a_cascade_made_by_the_other_task_arrives_here_as_it_was_recorded() {
    let mock = MockCloud::with(&[("parts", "1.0.0", package("parts", "1.0.0"))]);
    let t = two_tasks("cascade-off", mock.clone()).await;
    let addon = addon_dir(&t.temp);
    t.outgoing
        .runtime
        .write()
        .await
        .install_from_dir(&addon)
        .await
        .unwrap();
    t.staying
        .runtime
        .write()
        .await
        .install_from_dir(&addon)
        .await
        .unwrap();
    t.outgoing
        .runtime
        .write()
        .await
        .deactivate("parts")
        .await
        .unwrap();

    let report = ModuleReconciler::new().reconcile_once(&t.staying).await;

    assert_eq!(report.status_changed.len(), 2, "{report:?}");
    assert_eq!(
        listed(&t.staying, &t.session, "parts").await.unwrap()["status"],
        json!("inactive")
    );
    assert_eq!(
        listed(&t.staying, &t.session, "addon").await.unwrap()["status"],
        json!("inactive_auto")
    );
    assert_eq!(recorded(&t.staying, "addon").await.1, "inactive_auto");

    let _ = std::fs::remove_dir_all(&t.temp);
}
