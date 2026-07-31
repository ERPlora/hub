//! TDD (feedback visual de instalación, 2026-07-12): el pipeline `install_from_cloud` debe
//! REPORTAR su progreso por fases (resolving → downloading → verifying → installing) vía un
//! callback, incluyendo las dependencias anidadas, para que el server lo retransmita por WS
//! (`module.install.progress`) y el Hub pinte en la card del catálogo en qué punto está.
//!
//! El mock replica las formas EXACTAS de URL que consume `CloudClient` (§2.2): `versions/`,
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
    Sha256::digest(bytes).iter().map(|b| format!("{b:02x}")).collect()
}

/// `module.zip` mínimo instalable: `module.json` con id/name/version + depends_on.
fn module_zip(id: &str, deps: &[&str]) -> Vec<u8> {
    let manifest = json!({ "id": id, "name": id, "version": "1.0.0", "depends_on": deps });
    build_zip(&[("module.json", serde_json::to_string(&manifest).unwrap().as_bytes())])
}

/// id → (zip, sha256) del catálogo publicado en el mini-Cloud.
type Catalog = Arc<HashMap<String, (Vec<u8>, String)>>;

/// Levanta el mini-Cloud en un puerto efímero y devuelve su base URL.
async fn spawn_mock_cloud(catalog: Catalog) -> String {
    async fn versions(State(cat): State<Catalog>, Path(id): Path<String>) -> Json<serde_json::Value> {
        let sha = cat.get(&id).map(|(_, s)| s.clone()).unwrap_or_default();
        Json(json!([{ "version": "1.0.0", "is_active": true, "sha256": sha }]))
    }
    async fn download(State(cat): State<Catalog>, Path(id): Path<String>) -> Vec<u8> {
        cat.get(&id).map(|(z, _)| z.clone()).unwrap_or_default()
    }
    async fn mark_installed() -> Json<serde_json::Value> {
        Json(json!({ "ok": true }))
    }
    let app = Router::new()
        .route("/api/v1/marketplace/modules/:id/versions/", get(versions))
        .route("/api/v1/marketplace/modules/:id/download/", get(download))
        .route("/api/v1/marketplace/modules/:id/mark_installed/", post(mark_installed))
        .with_state(catalog);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("http://{addr}")
}

#[tokio::test]
async fn install_from_cloud_reports_progress_phases_including_nested_deps() {
    // Catálogo: `dependent` declara depends_on ["leaf"]; ambos publicados en el mock.
    let mut cat = HashMap::new();
    let leaf = module_zip("leaf", &[]);
    let dependent = module_zip("dependent", &["leaf"]);
    cat.insert("leaf".to_string(), (leaf.clone(), sha256_hex(&leaf)));
    cat.insert("dependent".to_string(), (dependent.clone(), sha256_hex(&dependent)));
    let base_url = spawn_mock_cloud(Arc::new(cat)).await;

    let http = reqwest::Client::new();
    let auth = Auth::HubToken { hub_id: "hub-test".into(), token: "tok".into() };
    let cache = std::env::temp_dir().join(format!("erplora-install-progress-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&cache);
    let mut rt = Runtime::new(Box::new(fresh_db().await));

    // Colector de fases: (module_id, fase) en orden de emisión.
    let seen: Arc<Mutex<Vec<(String, String)>>> = Arc::new(Mutex::new(Vec::new()));
    let sink = seen.clone();
    let on_progress = move |module_id: &str, phase: &str| {
        sink.lock().unwrap().push((module_id.to_string(), phase.to_string()));
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

    // Orden esperado: el headline se resuelve/descarga/verifica primero; su dep se instala
    // COMPLETA antes (incluida su fase installing); el headline instala (migra) el último.
    let got = seen.lock().unwrap().clone();
    let expect: Vec<(String, String)> = [
        ("dependent", "resolving"),
        ("dependent", "downloading"),
        ("dependent", "verifying"),
        ("leaf", "resolving"),
        ("leaf", "downloading"),
        ("leaf", "verifying"),
        ("leaf", "installing"),
        ("dependent", "installing"),
    ]
    .iter()
    .map(|(m, p)| (m.to_string(), p.to_string()))
    .collect();
    assert_eq!(got, expect);
    let _ = std::fs::remove_dir_all(&cache);
}
