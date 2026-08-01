//! TDD (feedback visual de instalación, 2026-07-12): el pipeline `install_from_cloud` debe
//! REPORTAR su progreso por fases (resolving → downloading → verifying → installing) vía un
//! callback, incluyendo las dependencias anidadas, para que el server lo retransmita por WS
//! (`module.install.progress`) y el Hub pinte en la card del catálogo en qué punto está.
//!
//! El mock replica las formas EXACTAS del contrato canónico que consume el Hub: `install-plan/`,
//! `download/?version=` y `mark_installed/`, sirviendo zips reales con SHA256 correcto para
//! ejercitar el pipeline completo (ADR-0015: verificación obligatoria) sin red externa.

use std::collections::HashMap;
use std::io::Write;
use std::sync::{Arc, Mutex};

use axum::extract::{Path, State};
use axum::routing::{get, post};
use axum::{Json, Router};
use cloud_client::Auth;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::install::install_from_cloud;
use serde_json::json;

/// Zip en memoria con las entradas dadas (mismo patrón que `export_import_test`).
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

/// `module.zip` mínimo instalable: `module.json` con id/name/version + depends_on.
fn module_zip(id: &str, deps: &[&str]) -> Vec<u8> {
    let manifest = json!({ "id": id, "name": id, "version": "1.0.0", "depends_on": deps });
    build_zip(&[(
        "module.json",
        serde_json::to_string(&manifest).unwrap().as_bytes(),
    )])
}

/// id → (zip, sha256) del catálogo publicado en el mini-Cloud.
type Catalog = Arc<HashMap<String, (Vec<u8>, String)>>;

#[derive(Clone)]
struct MockCloudState {
    catalog: Catalog,
    installed_requests: Arc<Mutex<Vec<Vec<String>>>>,
}

/// Levanta el mini-Cloud en un puerto efímero y devuelve su base URL.
async fn spawn_mock_cloud(catalog: Catalog) -> (String, Arc<Mutex<Vec<Vec<String>>>>) {
    async fn install_plan(
        State(state): State<MockCloudState>,
        Json(body): Json<serde_json::Value>,
    ) -> Json<serde_json::Value> {
        let requested = body["module_id"].as_str().unwrap_or_default();
        let installed: Vec<String> = body["installed"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|value| value.as_str().map(str::to_string))
            .collect();
        state.installed_requests.lock().unwrap().push(installed.clone());
        let mut ids: Vec<&str> = if requested == "dependent" {
            vec!["leaf", "dependent"]
        } else {
            vec![requested]
        };
        ids.retain(|id| !installed.iter().any(|active| active == id));
        let plan: Vec<_> = ids
            .into_iter()
            .map(|id| {
                json!({
                    "module_id": id,
                    "version": "1.0.0",
                    "sha256": state.catalog.get(id).map(|(_, s)| s.clone()).unwrap_or_default(),
                    "tier": "free",
                    "entitled": true,
                    "requires_purchase": false,
                    "reason": if id == requested { "requested" } else { "dependency" }
                })
            })
            .collect();
        Json(json!({
            "requested": requested,
            "plan": plan,
            "already_satisfied": installed,
            "blocked": false,
            "blocked_on": []
        }))
    }
    async fn download(State(state): State<MockCloudState>, Path(id): Path<String>) -> Vec<u8> {
        state
            .catalog
            .get(&id)
            .map(|(z, _)| z.clone())
            .unwrap_or_default()
    }
    async fn mark_installed() -> Json<serde_json::Value> {
        Json(json!({ "ok": true }))
    }
    let installed_requests = Arc::new(Mutex::new(Vec::new()));
    let state = MockCloudState {
        catalog,
        installed_requests: installed_requests.clone(),
    };
    let app = Router::new()
        .route("/api/v1/marketplace/install-plan/", post(install_plan))
        .route("/api/v1/marketplace/modules/:id/download/", get(download))
        .route(
            "/api/v1/marketplace/modules/:id/mark_installed/",
            post(mark_installed),
        )
        .with_state(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (format!("http://{addr}"), installed_requests)
}

#[tokio::test]
async fn install_from_cloud_reports_progress_phases_including_nested_deps() {
    // Catálogo: `dependent` declara depends_on ["leaf"]; ambos publicados en el mock.
    let mut cat = HashMap::new();
    let leaf = module_zip("leaf", &[]);
    let dependent = module_zip("dependent", &["leaf"]);
    cat.insert("leaf".to_string(), (leaf.clone(), sha256_hex(&leaf)));
    cat.insert(
        "dependent".to_string(),
        (dependent.clone(), sha256_hex(&dependent)),
    );
    let (base_url, _) = spawn_mock_cloud(Arc::new(cat)).await;

    let http = reqwest::Client::new();
    let auth = Auth::HubToken {
        hub_id: "hub-test".into(),
        token: "tok".into(),
    };
    let cache =
        std::env::temp_dir().join(format!("erplora-install-progress-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&cache);
    let mut rt = Runtime::new(Box::new(fresh_db().await));

    // Colector de fases: (module_id, fase) en orden de emisión.
    let seen: Arc<Mutex<Vec<(String, String)>>> = Arc::new(Mutex::new(Vec::new()));
    let sink = seen.clone();
    let on_progress = move |module_id: &str, phase: &str| {
        sink.lock()
            .unwrap()
            .push((module_id.to_string(), phase.to_string()));
    };

    let installed = install_from_cloud(
        &http,
        &base_url,
        &cache,
        &auth,
        &mut rt,
        "dependent",
        "latest",
        &on_progress,
        // El mock cloud de este test no firma los zips (prueba las fases de progreso, no la
        // autenticidad — esa va en install_surface). DevTrust admite sin firma.
        &erplora_server::install::dev_signature_policy(),
    )
    .await
    .expect("instalación con dep anidada debe funcionar");
    assert_eq!(installed.module_id, "dependent");

    // Orden del plan canónico: el root entra en resolving mientras Cloud calcula el cierre;
    // después cada nodo completa sus fases en topo-orden (dependencia antes que dependiente).
    let got = seen.lock().unwrap().clone();
    let expect: Vec<(String, String)> = [
        ("dependent", "resolving"),
        ("leaf", "resolving"),
        ("leaf", "downloading"),
        ("leaf", "verifying"),
        ("leaf", "installing"),
        ("dependent", "resolving"),
        ("dependent", "downloading"),
        ("dependent", "verifying"),
        ("dependent", "installing"),
    ]
    .iter()
    .map(|(m, p)| (m.to_string(), p.to_string()))
    .collect();
    assert_eq!(got, expect);
    let _ = std::fs::remove_dir_all(&cache);
}

#[tokio::test]
async fn inactive_dependency_is_not_reported_satisfied_and_finishes_active() {
    let mut cat = HashMap::new();
    let leaf = module_zip("leaf", &[]);
    let dependent = module_zip("dependent", &["leaf"]);
    cat.insert("leaf".to_string(), (leaf.clone(), sha256_hex(&leaf)));
    cat.insert(
        "dependent".to_string(),
        (dependent.clone(), sha256_hex(&dependent)),
    );
    let (base_url, requests) = spawn_mock_cloud(Arc::new(cat)).await;
    let cache = std::env::temp_dir().join(format!(
        "erplora-install-inactive-dependency-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&cache);
    let mut rt = Runtime::new(Box::new(fresh_db().await));
    let auth = Auth::HubToken {
        hub_id: "hub-test".into(),
        token: "tok".into(),
    };

    install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache,
        &auth,
        &mut rt,
        "dependent",
        "latest",
        &|_, _| {},
        &erplora_server::install::dev_signature_policy(),
    )
    .await
    .unwrap();
    rt.deactivate("leaf").await.unwrap();
    let inactive: HashMap<_, _> = rt
        .modules()
        .into_iter()
        .map(|module| (module.id, module.status))
        .collect();
    assert_eq!(inactive["leaf"], erplora_runtime::ModuleStatus::Inactive);
    assert_eq!(
        inactive["dependent"],
        erplora_runtime::ModuleStatus::InactiveAuto
    );

    install_from_cloud(
        &reqwest::Client::new(),
        &base_url,
        &cache,
        &auth,
        &mut rt,
        "dependent",
        "latest",
        &|_, _| {},
        &erplora_server::install::dev_signature_policy(),
    )
    .await
    .unwrap();

    let seen = requests.lock().unwrap();
    assert_eq!(seen.len(), 2);
    assert!(
        seen[1].is_empty(),
        "Inactive/InactiveAuto no se envían a Cloud como satisfied: {seen:?}"
    );
    let statuses: HashMap<_, _> = rt
        .modules()
        .into_iter()
        .map(|module| (module.id, module.status))
        .collect();
    assert_eq!(statuses["leaf"], erplora_runtime::ModuleStatus::Active);
    assert_eq!(statuses["dependent"], erplora_runtime::ModuleStatus::Active);
    let _ = std::fs::remove_dir_all(&cache);
}

#[tokio::test]
async fn blocked_plan_stops_before_any_download_or_install() {
    let downloads = Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let seen_downloads = downloads.clone();
    async fn blocked() -> Json<serde_json::Value> {
        Json(json!({
            "requested": "premium",
            "plan": [{
                "module_id": "premium", "version": "1.0.0", "sha256": "aa",
                "tier": "premium", "entitled": false, "requires_purchase": true,
                "reason": "requested",
                "purchase": {"module_type":"subscription","price":"19.99","currency":"EUR","purchase_url":"/premium"}
            }],
            "already_satisfied": [], "blocked": true, "blocked_on": ["premium"]
        }))
    }
    async fn should_not_download(
        State(counter): State<Arc<std::sync::atomic::AtomicUsize>>,
    ) -> Vec<u8> {
        counter.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        Vec::new()
    }
    let app = Router::new()
        .route("/api/v1/marketplace/install-plan/", post(blocked))
        .route(
            "/api/v1/marketplace/modules/:id/download/",
            get(should_not_download),
        )
        .with_state(seen_downloads);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    let result = install_from_cloud(
        &reqwest::Client::new(),
        &format!("http://{addr}"),
        &std::env::temp_dir().join("erplora-blocked-plan"),
        &Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "tok".into(),
        },
        &mut rt,
        "premium",
        "latest",
        &|_, _| {},
        &erplora_server::install::dev_signature_policy(),
    )
    .await;
    assert!(matches!(
        result,
        Err(erplora_server::install::InstallError::Blocked { .. })
    ));
    assert_eq!(downloads.load(std::sync::atomic::Ordering::SeqCst), 0);
    assert!(
        rt.modules().is_empty(),
        "blocked=true no deja instalación parcial"
    );
}
