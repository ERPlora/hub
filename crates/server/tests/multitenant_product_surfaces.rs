//! Regresión multi-tenant de las superficies de producto que no pasan por `/api/query`:
//! settings, catálogo, preview e instalación. Todas deben resolver el Runtime y la identidad Cloud
//! desde `X-Hub-Id`, nunca desde el runtime bootstrap del proceso compartido.

use std::collections::HashMap;
use std::io::Write;
use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::{Query, State};
use axum::http::{HeaderMap, Request, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{
    app, AppState, AuthMode, EnvOrgResolver, HubConfig, OrgDescriptor, OrgId, RuntimeFactory,
    TenantRouter,
};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tower::ServiceExt;

fn module_zip() -> Vec<u8> {
    let manifest = json!({ "id": "notes", "name": "Notes", "version": "1.0.0" });
    let mut bytes = Vec::new();
    {
        let mut zip = zip::ZipWriter::new(std::io::Cursor::new(&mut bytes));
        let options: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        zip.start_file("module.json", options).unwrap();
        zip.write_all(manifest.to_string().as_bytes()).unwrap();
        zip.finish().unwrap();
    }
    bytes
}

#[derive(Clone)]
struct CloudState {
    package: Arc<Vec<u8>>,
    sha256: String,
    signature: cloud_client::ModuleSignature,
    seen: Arc<Mutex<Vec<Value>>>,
}

fn request_hub(headers: &HeaderMap) -> String {
    headers
        .get("x-hub-id")
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
        .to_string()
}

async fn install_plan(
    State(state): State<CloudState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Json<Value> {
    let hub_id = request_hub(&headers);
    state.seen.lock().unwrap().push(json!({
        "kind": "plan", "hub_id": hub_id, "installed": body["installed"]
    }));
    let already = body["installed"]
        .as_array()
        .is_some_and(|items| items.iter().any(|item| item == "notes"));
    let plan = (!already)
        .then(|| {
            json!({
                "module_id": "notes",
                "version": "1.0.0",
                "sha256": state.sha256,
                "signature": state.signature,
                "tier": "free",
                "entitled": true,
                "requires_purchase": false,
                "reason": "requested"
            })
        })
        .into_iter()
        .collect::<Vec<_>>();
    Json(json!({
        "requested": "notes", "plan": plan, "already_satisfied": [],
        "blocked": false, "blocked_on": []
    }))
}

async fn download(State(state): State<CloudState>, headers: HeaderMap) -> Vec<u8> {
    state.seen.lock().unwrap().push(json!({
        "kind": "download", "hub_id": request_hub(&headers)
    }));
    state.package.as_ref().clone()
}

async fn mark_installed(State(state): State<CloudState>, headers: HeaderMap) -> Json<Value> {
    state.seen.lock().unwrap().push(json!({
        "kind": "mark", "hub_id": request_hub(&headers)
    }));
    Json(json!({ "ok": true }))
}

async fn catalog(
    State(state): State<CloudState>,
    headers: HeaderMap,
    Query(query): Query<HashMap<String, String>>,
) -> Json<Value> {
    let hub_id = request_hub(&headers);
    let countries = query.get("countries").cloned().unwrap_or_default();
    let region = query.get("region").cloned();
    state.seen.lock().unwrap().push(json!({
        "kind": "catalog", "hub_id": hub_id, "countries": countries, "region": region
    }));
    Json(json!({ "hub_id": hub_id, "countries": countries, "region": region, "results": [] }))
}

async fn spawn_cloud(signer: &cloud_client::Signer) -> (String, Arc<Mutex<Vec<Value>>>) {
    let package = module_zip();
    let state = CloudState {
        sha256: Sha256::digest(&package)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect(),
        signature: signer.sign("multitenant-test", &package),
        package: Arc::new(package),
        seen: Arc::new(Mutex::new(Vec::new())),
    };
    let seen = state.seen.clone();
    let router = Router::new()
        .route("/api/v1/marketplace/install-plan/", post(install_plan))
        .route("/api/v1/marketplace/modules/notes/download/", get(download))
        .route(
            "/api/v1/marketplace/modules/notes/mark_installed/",
            post(mark_installed),
        )
        .route("/api/v1/marketplace/modules/", get(catalog))
        .with_state(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{address}"), seen)
}

fn tenant_factory() -> RuntimeFactory {
    Arc::new(|descriptor: &OrgDescriptor| {
        let org_id = descriptor.org_id.0.clone();
        Box::pin(async move {
            let db = fresh_db().await;
            let mut runtime = Runtime::with_hub_id(Box::new(db), org_id.clone());
            runtime.ensure_system_tables().await.unwrap();
            if org_id == "org-a" {
                let fixture = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../runtime/tests/fixture_inventory");
                runtime.install_from_dir(&fixture).await.unwrap();
            }
            Ok(runtime)
        })
    })
}

async fn shared_app(
    cloud_base_url: String,
    trusted_key: String,
) -> (axum::Router, Arc<TenantRouter>, std::path::PathBuf) {
    let mut map = HashMap::new();
    for (hub, org) in [("hub-a1", "org-a"), ("hub-b1", "org-b")] {
        map.insert(
            hub.to_string(),
            OrgDescriptor {
                org_id: OrgId(org.into()),
                dsn: "unused".into(),
            },
        );
    }
    let tenants = Arc::new(TenantRouter::with_factory(
        Arc::new(EnvOrgResolver::new(map)),
        tenant_factory(),
        8,
    ));
    let temp = std::env::temp_dir().join(format!(
        "erplora-multitenant-product-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&temp);
    let bootstrap = Runtime::with_hub_id(Box::new(fresh_db().await), "bootstrap");
    let config = HubConfig {
        hub_id: "bootstrap".into(),
        cloud_base_url,
        module_cache: temp.join("modules"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("shared-machine-token".into()),
        device_trust_enforce: false,
        media_dir: temp.join("media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: vec![trusted_key],
    };
    let router = app(AppState::with_config(bootstrap, config).with_tenants(tenants.clone()));
    (router, tenants, temp)
}

fn request(method: &str, hub_id: &str, uri: &str, body: Option<Value>) -> Request<Body> {
    let mut builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("x-hub-id", hub_id)
        .header("x-user-id", "owner")
        .header("x-permissions", "*");
    let body = match body {
        Some(value) => {
            builder = builder.header("content-type", "application/json");
            Body::from(value.to_string())
        }
        None => Body::empty(),
    };
    builder.body(body).unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

#[tokio::test]
async fn preview_install_settings_and_catalog_are_isolated_by_request_hub() {
    let rng = ring::rand::SystemRandom::new();
    let (signer, _) = cloud_client::Signer::generate(&rng);
    let (cloud, seen) = spawn_cloud(&signer).await;
    let trusted = format!(
        "multitenant-test={}",
        signer
            .public_key()
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    );
    let (app, tenants, temp) = shared_app(cloud, trusted).await;

    for (hub, country, region) in [("hub-a1", "FR", "IDF"), ("hub-b1", "DE", "BE")] {
        let response = app
            .clone()
            .oneshot(request(
                "PUT",
                hub,
                "/api/settings",
                Some(json!({ "country_code": country, "region_code": region })),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let response = app
            .clone()
            .oneshot(request("GET", hub, "/api/settings", None))
            .await
            .unwrap();
        let settings = body_json(response).await;
        assert_eq!(settings["country_code"], json!(country));
        assert_eq!(settings["region_code"], json!(region));

        let response = app
            .clone()
            .oneshot(request("GET", hub, "/api/marketplace/catalog", None))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let catalog = body_json(response).await;
        assert_eq!(catalog["hub_id"], json!(hub));
        assert_eq!(catalog["countries"], json!(country));
        assert_eq!(catalog["region"], json!(region));
    }

    for hub in ["hub-a1", "hub-b1"] {
        let response = app
            .clone()
            .oneshot(request(
                "POST",
                hub,
                "/api/modules/install-plan",
                Some(json!({ "module_id": "notes" })),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "preview {hub}");
    }
    let observations = seen.lock().unwrap().clone();
    let plan_a = observations
        .iter()
        .find(|item| item["kind"] == "plan" && item["hub_id"] == "hub-a1")
        .unwrap();
    let plan_b = observations
        .iter()
        .find(|item| item["kind"] == "plan" && item["hub_id"] == "hub-b1")
        .unwrap();
    assert!(plan_a["installed"]
        .as_array()
        .unwrap()
        .iter()
        .any(|module| module == "inventory"));
    assert!(plan_b["installed"].as_array().unwrap().is_empty());

    for hub in ["hub-b1", "hub-a1"] {
        let response = app
            .clone()
            .oneshot(request(
                "POST",
                hub,
                "/api/modules/request-install",
                Some(json!({ "module_id": "notes" })),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "install {hub}");
        let runtime = tenants.resolve_runtime(hub).await.unwrap();
        assert!(runtime
            .lock()
            .await
            .modules()
            .iter()
            .any(|module| module.id == "notes"));
    }

    let observations = seen.lock().unwrap();
    for hub in ["hub-a1", "hub-b1"] {
        assert!(observations
            .iter()
            .any(|item| item["kind"] == "catalog" && item["hub_id"] == hub));
        assert!(observations
            .iter()
            .any(|item| item["kind"] == "mark" && item["hub_id"] == hub));
    }

    let _ = std::fs::remove_dir_all(temp);
}
