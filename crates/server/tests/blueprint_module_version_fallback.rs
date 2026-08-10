//! TDD (hub#751 / hub#752): a template's pinned module version is a SNAPSHOT, not a requirement.
//!
//! A blueprint is a hub exported at a point in time, so `manifest.modules[].version` records
//! whatever that hub happened to be running. The marketplace, meanwhile, keeps only the last N
//! versions of each module: after enough releases the pinned zip is **deleted**, and the exact
//! match the installer demands stops existing.
//!
//! That is what took the four published templates down at once — `sales@2.12.8` and
//! `verifactu@1.4.1` were pruned, so importing «Peluquería» left the salon with neither sales nor
//! VeriFactu: no charge, no ticket, no fiscal record. The bundle was still perfectly good.
//!
//! What is pinned here:
//!   1. a pin that is GONE installs the newest COMPATIBLE version instead (same major, never
//!      older) and says so in the report, instead of failing the module;
//!   2. a pin that is still published is honoured EXACTLY — the fallback is a recovery, never a
//!      silent upgrade;
//!   3. when nothing compatible exists (the major itself is gone) it still fails, loudly: a
//!      template's data was written against that major and installing across it is not a fix.

use std::collections::HashMap;
use std::io::Write as _;
use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::{Path, State};
use axum::http::{Request, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

// ─────────────────────────── mini-Cloud (real HTTP) ───────────────────────────

/// What the marketplace serves. The catalog is keyed by `(module_id, version)` so a test can put
/// a version in `versions/` **and** have `download/` answer for exactly that one — the point of
/// these cases is which version gets asked for, so it cannot be faked.
struct MockCloud {
    /// module id → versions it publishes, newest first (as the Cloud orders them).
    published: HashMap<String, Vec<String>>,
    /// (module id, version) → (zip bytes, sha256).
    artifacts: HashMap<(String, String), (Vec<u8>, String)>,
    /// Every `download/?version=` served, so a test can assert WHICH version was fetched.
    downloads: Mutex<Vec<String>>,
}

type Shared = Arc<MockCloud>;

async fn spawn_mock_cloud(mock: Shared) -> String {
    async fn versions(State(m): State<Shared>, Path(id): Path<String>) -> Json<Value> {
        let list: Vec<Value> = m
            .published
            .get(&id)
            .map(|vs| {
                vs.iter()
                    .map(|v| {
                        let sha = m
                            .artifacts
                            .get(&(id.clone(), v.clone()))
                            .map(|(_, s)| s.clone())
                            .unwrap_or_default();
                        json!({ "version": v, "is_active": true, "sha256": sha })
                    })
                    .collect()
            })
            .unwrap_or_default();
        Json(Value::Array(list))
    }

    #[derive(serde::Deserialize)]
    struct VersionQuery {
        #[serde(default)]
        version: String,
    }

    async fn download(
        State(m): State<Shared>,
        Path(id): Path<String>,
        axum::extract::Query(q): axum::extract::Query<VersionQuery>,
    ) -> Vec<u8> {
        m.downloads
            .lock()
            .unwrap()
            .push(format!("{id}@{}", q.version));
        m.artifacts
            .get(&(id, q.version))
            .map(|(z, _)| z.clone())
            .unwrap_or_default()
    }

    async fn mark_installed(Path(_id): Path<String>) -> Json<Value> {
        Json(json!({ "ok": true }))
    }

    // The install-plan endpoint 404s for a version the marketplace no longer has — exactly what
    // production does (`_node_artifact` raises `UnknownModuleError`). The Hub degrades to
    // resolving through `versions/`, which is the path under test.
    async fn install_plan() -> axum::response::Response {
        use axum::response::IntoResponse;
        (
            StatusCode::NOT_FOUND,
            Json(json!({ "detail": "Not found." })),
        )
            .into_response()
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

// ─────────────────────────── zip / manifest helpers ───────────────────────────

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

/// A minimal installable `module.zip` declaring its own id + version.
fn module_zip(id: &str, version: &str) -> (Vec<u8>, String) {
    let manifest = json!({ "id": id, "name": id, "version": version, "depends_on": [] });
    let zip = build_zip(&[(
        "module.json",
        serde_json::to_string(&manifest).unwrap().as_bytes(),
    )]);
    let sha = sha256_hex(&zip);
    (zip, sha)
}

/// A blueprint bundle whose only content is the module list (no data sections): the case under
/// test is version resolution, not the SQL engine.
fn blueprint_zip(modules: Value) -> Vec<u8> {
    let manifest = json!({
        "schema_version": 1,
        "name": "peluqueria",
        "locale": "es",
        "hub": { "name": "Salon", "country": "ES", "currency": "EUR" },
        "created_at": "2026-08-10T00:00:00Z",
        "modules": modules,
        "sections": [],
        "sha256": {},
    })
    .to_string();
    build_zip(&[("manifest.json", manifest.as_bytes())])
}

// ─────────────────────────── hub under test ───────────────────────────

fn test_config(cloud_base_url: &str, tag: &str) -> HubConfig {
    let base = std::env::temp_dir().join(format!("erplora_bp_ver_{}_{tag}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-test".into(),
        cloud_base_url: cloud_base_url.to_string(),
        module_cache: base.join("module_cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: base.join("media"),
        sector: None,
        // The mock marketplace does not sign its zips: DevTrust is the documented escape hatch.
        dev_mode: true,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

async fn make_app(cloud_base_url: &str, tag: &str) -> axum::Router {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-test");
    let _ = std::fs::remove_dir_all(std::env::temp_dir().join(format!(
        "erplora_bp_ver_{}_{tag}",
        std::process::id()
    )));
    app(AppState::with_config(
        rt,
        test_config(cloud_base_url, tag),
    ))
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// inspect → import, returning `report.installed_modules[]`.
async fn import_blueprint(router: axum::Router, zip: Vec<u8>) -> Vec<Value> {
    let resp = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/import/inspect")
                .header("content-type", "application/octet-stream")
                .body(Body::from(zip))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "inspect");
    let upload_id = body_json(resp).await["upload_id"]
        .as_str()
        .unwrap()
        .to_string();

    let resp = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/import")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({ "upload_id": upload_id, "selection": {} }).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "import");
    let j = body_json(resp).await;
    j["report"]["installed_modules"]
        .as_array()
        .expect("installed_modules")
        .clone()
}

// ─────────────────────────── the cases ───────────────────────────

/// hub#752: the pinned version was pruned from the marketplace. The salon must still get `sales`.
#[tokio::test]
async fn a_pin_the_marketplace_no_longer_publishes_installs_the_newest_compatible_version() {
    let (zip, sha) = module_zip("sales", "2.13.10");
    let mock = Arc::new(MockCloud {
        // 2.12.8 is GONE (pruned): only the 2.13.x line survives.
        published: HashMap::from([(
            "sales".to_string(),
            vec!["2.13.10".to_string(), "2.13.9".to_string()],
        )]),
        artifacts: HashMap::from([
            (("sales".into(), "2.13.10".into()), (zip.clone(), sha.clone())),
            (("sales".into(), "2.13.9".into()), (zip, sha)),
        ]),
        downloads: Mutex::new(Vec::new()),
    });
    let cloud = spawn_mock_cloud(mock.clone()).await;
    let router = make_app(&cloud, "gone_pin").await;

    let entries = import_blueprint(
        router,
        blueprint_zip(json!([{ "id": "sales", "version": "2.12.8", "with_data": false }])),
    )
    .await;

    let sales = &entries[0];
    assert_eq!(
        sales["status"], "installed",
        "una plantilla cuyo pin ya no se publica deja el negocio sin vender: {sales}"
    );
    assert_eq!(
        sales["version"], "2.13.10",
        "debe caer a la más nueva COMPATIBLE, no a una cualquiera: {sales}"
    );
    assert_eq!(
        sales["requested_version"], "2.12.8",
        "el informe tiene que decir que se instaló otra distinta de la pedida: {sales}"
    );
    assert_eq!(
        mock.downloads.lock().unwrap().as_slice(),
        ["sales@2.13.10"],
        "se descarga la versión resuelta, no el pin muerto"
    );
}

/// The fallback is a RECOVERY, not a silent upgrade: a pin that is still published wins.
#[tokio::test]
async fn a_pin_that_is_still_published_is_installed_exactly() {
    let (old_zip, old_sha) = module_zip("sales", "2.13.9");
    let (new_zip, new_sha) = module_zip("sales", "2.13.10");
    let mock = Arc::new(MockCloud {
        published: HashMap::from([(
            "sales".to_string(),
            vec!["2.13.10".to_string(), "2.13.9".to_string()],
        )]),
        artifacts: HashMap::from([
            (("sales".into(), "2.13.10".into()), (new_zip, new_sha)),
            (("sales".into(), "2.13.9".into()), (old_zip, old_sha)),
        ]),
        downloads: Mutex::new(Vec::new()),
    });
    let cloud = spawn_mock_cloud(mock.clone()).await;
    let router = make_app(&cloud, "live_pin").await;

    let entries = import_blueprint(
        router,
        blueprint_zip(json!([{ "id": "sales", "version": "2.13.9", "with_data": false }])),
    )
    .await;

    assert_eq!(entries[0]["status"], "installed", "{}", entries[0]);
    assert_eq!(
        entries[0]["version"], "2.13.9",
        "el pin vivo manda: nada de subir de versión por su cuenta: {}",
        entries[0]
    );
    assert!(
        entries[0]["requested_version"].is_null(),
        "sin sustitución no hay nada que anotar: {}",
        entries[0]
    );
}

/// Nothing compatible left (the whole major is gone): still a failure, and a named one. The
/// bundle's rows were written against that major; installing across it is not a fix.
#[tokio::test]
async fn a_pin_with_no_compatible_version_left_still_fails() {
    let (zip, sha) = module_zip("verifactu", "2.0.0");
    let mock = Arc::new(MockCloud {
        published: HashMap::from([("verifactu".to_string(), vec!["2.0.0".to_string()])]),
        artifacts: HashMap::from([(("verifactu".into(), "2.0.0".into()), (zip, sha))]),
        downloads: Mutex::new(Vec::new()),
    });
    let cloud = spawn_mock_cloud(mock.clone()).await;
    let router = make_app(&cloud, "no_compat").await;

    let entries = import_blueprint(
        router,
        blueprint_zip(json!([{ "id": "verifactu", "version": "1.4.1", "with_data": false }])),
    )
    .await;

    assert_eq!(entries[0]["status"], "failed", "{}", entries[0]);
    assert_eq!(
        entries[0]["code"], "install_version_not_found",
        "{}",
        entries[0]
    );
    assert!(
        mock.downloads.lock().unwrap().is_empty(),
        "no se cruza un major a la brava"
    );
}
