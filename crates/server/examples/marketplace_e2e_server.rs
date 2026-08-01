//! Entorno reproducible para los E2E reales del Marketplace (hub#68 y hub#69).
//!
//! Sirve el router de producción del Hub en `127.0.0.1:8787` y, detrás, un mini-SaaS efímero
//! que implementa el contrato real catalog/install-plan/download/mark_installed. Los paquetes se
//! firman con ed25519 y el Hub corre con `dev_mode=false`, así Playwright recorre de verdad
//! navegador → proxy Vite → Axum → Cloud → verificación → Runtime, sin interceptar `/api`.

use std::collections::HashMap;
use std::io::Write;
use std::sync::Arc;

use axum::extract::{Path, Query, State};
use axum::routing::{get, post};
use axum::{Json, Router};
use cloud_client::{ModuleSignature, Signer};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

#[derive(Clone)]
struct Package {
    bytes: Vec<u8>,
    sha256: String,
    signature: ModuleSignature,
}

#[derive(Clone)]
struct CloudState {
    packages: Arc<HashMap<String, Package>>,
}

#[derive(Debug, Default, Deserialize)]
struct CatalogQuery {
    countries: Option<String>,
    region: Option<String>,
}

async fn catalog(Query(query): Query<CatalogQuery>) -> Json<Value> {
    let country = query.countries.as_deref().unwrap_or("ES").to_ascii_uppercase();
    let region = query.region.as_deref().map(str::to_ascii_uppercase);
    // El Hub de la prueba está en ES-MD. Para cualquier otro país, arrastrar MD sería un fallo:
    // devolvemos catálogo vacío y Playwright no podría encontrar el módulo de ese país.
    let module = match (country.as_str(), region.as_deref()) {
        ("ES", Some("MD") | None) => Some(json!({
            "id": 68,
            "module_id": "verifactu",
            "name": "VeriFactu",
            "description": "Cumplimiento fiscal español",
            "version": "1.0.0",
            "module_type": "free",
            "is_free": true,
            "is_active": true,
            "countries": ["ES"],
            "country_links": [{"country": "ES", "regions": [], "excluded_regions": []}]
        })),
        ("FR", None) => Some(json!({
            "id": 69,
            "module_id": "facturx",
            "name": "Factur-X",
            "description": "Facturation électronique française",
            "version": "1.0.0",
            "module_type": "free",
            "is_free": true,
            "is_active": true,
            "countries": ["FR"],
            "country_links": [{"country": "FR", "regions": [], "excluded_regions": []}]
        })),
        ("DE", None) => Some(json!({
            "id": 690,
            "module_id": "xrechnung",
            "name": "XRechnung",
            "description": "Deutsche E-Rechnung",
            "version": "1.0.0",
            "module_type": "free",
            "is_free": true,
            "is_active": true,
            "countries": ["DE"]
        })),
        ("IT", None) => Some(json!({
            "id": 691,
            "module_id": "fatturapa",
            "name": "FatturaPA",
            "description": "Fatturazione elettronica italiana",
            "version": "1.0.0",
            "module_type": "free",
            "is_free": true,
            "is_active": true,
            "countries": ["IT"]
        })),
        _ => None,
    };
    Json(json!({ "results": module.into_iter().collect::<Vec<_>>() }))
}

async fn install_plan(
    State(state): State<CloudState>,
    Json(body): Json<Value>,
) -> Json<Value> {
    let requested = body["module_id"].as_str().unwrap_or_default();
    let installed: Vec<&str> = body["installed"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .collect();
    let ordered = if requested == "verifactu" {
        vec![("invoice", "dependency"), ("verifactu", "requested")]
    } else {
        vec![(requested, "requested")]
    };
    let plan: Vec<Value> = ordered
        .into_iter()
        .filter(|(id, _)| !installed.contains(id))
        .filter_map(|(id, reason)| {
            let package = state.packages.get(id)?;
            Some(json!({
                "module_id": id,
                "version": "1.0.0",
                "sha256": package.sha256,
                "signature": package.signature,
                "tier": "free",
                "entitled": true,
                "requires_purchase": false,
                "reason": reason
            }))
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

async fn download(State(state): State<CloudState>, Path(id): Path<String>) -> Vec<u8> {
    state
        .packages
        .get(&id)
        .map(|package| package.bytes.clone())
        .unwrap_or_default()
}

async fn mark_installed() -> Json<Value> {
    Json(json!({ "ok": true }))
}

async fn entitlement() -> Json<Value> {
    Json(json!({
        "modules": [
            {"module_id": "invoice", "tier": "free", "version": "1.0.0"},
            {"module_id": "verifactu", "tier": "free", "version": "1.0.0"}
        ]
    }))
}

fn module_zip(id: &str, dependencies: &[&str]) -> Vec<u8> {
    let manifest = json!({
        "id": id,
        "name": id,
        "version": "1.0.0",
        "depends_on": dependencies
    });
    let mut bytes = Vec::new();
    {
        let mut zip = zip::ZipWriter::new(std::io::Cursor::new(&mut bytes));
        let options: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        zip.start_file("module.json", options).expect("module.json");
        zip.write_all(manifest.to_string().as_bytes()).expect("manifest");
        zip.finish().expect("finish zip");
    }
    bytes
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

async fn spawn_cloud(signer: &Signer) -> String {
    let packages = [("invoice", Vec::<&str>::new()), ("verifactu", vec!["invoice"])]
        .into_iter()
        .map(|(id, dependencies)| {
            let bytes = module_zip(id, &dependencies);
            let package = Package {
                sha256: hex(&Sha256::digest(&bytes)),
                signature: signer.sign("marketplace-e2e", &bytes),
                bytes,
            };
            (id.to_string(), package)
        })
        .collect();
    let state = CloudState {
        packages: Arc::new(packages),
    };
    let router = Router::new()
        .route("/api/v1/marketplace/modules/", get(catalog))
        .route("/api/v1/marketplace/install-plan/", post(install_plan))
        .route("/api/v1/marketplace/modules/:id/download/", get(download))
        .route(
            "/api/v1/marketplace/modules/:id/mark_installed/",
            post(mark_installed),
        )
        .route("/api/v1/hub/device/entitlement/", get(entitlement))
        .with_state(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind mock cloud");
    let address = listener.local_addr().expect("mock cloud address");
    tokio::spawn(async move { axum::serve(listener, router).await.expect("serve mock cloud") });
    format!("http://{address}")
}

#[tokio::main]
async fn main() {
    let rng = ring::rand::SystemRandom::new();
    let (signer, _) = Signer::generate(&rng);
    let cloud_base_url = spawn_cloud(&signer).await;
    let hub_id = "hub-marketplace-playwright";
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.expect("system tables");
    let mut settings = Map::new();
    settings.insert("country_code".into(), json!("ES"));
    settings.insert("region_code".into(), json!("MD"));
    rt.set_settings(&settings, "playwright")
        .await
        .expect("seed marketplace context");

    let temp = std::env::temp_dir().join(format!(
        "erplora-marketplace-playwright-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&temp);
    let cfg = HubConfig {
        hub_id: hub_id.into(),
        cloud_base_url,
        module_cache: temp.join("module-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("playwright-machine-token".into()),
        device_trust_enforce: false,
        media_dir: temp.join("media"),
        sector: None,
        // Producción deliberada: la instalación debe validar firma, no usar DevTrust.
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: vec![format!("marketplace-e2e={}", hex(&signer.public_key()))],
    };
    let state = AppState::with_config(rt, cfg);
    let bind = std::env::var("MARKETPLACE_E2E_BIND")
        .unwrap_or_else(|_| "127.0.0.1:8787".into());
    let listener = tokio::net::TcpListener::bind(&bind)
        .await
        .expect("bind marketplace e2e server");
    println!("marketplace e2e server listening on http://{bind}");
    axum::serve(listener, app(state))
        .await
        .expect("serve marketplace e2e server");
}
