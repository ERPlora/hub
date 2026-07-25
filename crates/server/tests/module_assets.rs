//! Contrato: los **assets web de un módulo instalado** (`module.json`, `dist/*.esm.js`, wasm/icons)
//! se sirven desde la CACHÉ de descargas por versión (`/modules/<id>/<path>` →
//! `module_cache/<id>/<version>/<path>`).
//!
//! Bug de producción (sweep Playwright 2026-07-09): en Hub Cloud los módulos se descargan en runtime
//! al `module_cache` (no se hornean en el `web_dir`), pero el server solo servía el `web_dir` con
//! fallback SPA → `/modules/<id>/module.json` devolvía el `index.html` (`200 text/html`), el
//! `JSON.parse` del cargador petaba y NINGÚN Web Component cargaba: toda la UI de módulos muerta.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_server::{app, AppState, AuthMode, HubConfig};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use http_body_util::BodyExt;
use std::path::{Path, PathBuf};
use tower::ServiceExt; // oneshot

fn cfg(module_cache: PathBuf) -> HubConfig {
    HubConfig {
        hub_id: "hub-assets".into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache,
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        // El fixture valida el servido desde caché, no el alta inicial de la máquina.
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-test-media-assets"),
        sector: None,
    }
}

/// Escribe un módulo mínimo en `cache/<id>/<version>/` (module.json + un bundle dist) y devuelve el dir.
fn write_module(cache: &Path, id: &str, version: &str) -> PathBuf {
    let dir = cache.join(id).join(version);
    std::fs::create_dir_all(dir.join("dist")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        format!(r#"{{"id":"{id}","name":"{id}","version":"{version}"}}"#),
    )
    .unwrap();
    std::fs::write(dir.join("dist").join(format!("{id}.esm.js")), "export const x=1;\n").unwrap();
    dir
}

async fn get(router: axum::Router, uri: &str) -> (StatusCode, String, String) {
    let resp = router.oneshot(Request::get(uri).body(Body::empty()).unwrap()).await.unwrap();
    let status = resp.status();
    let ct = resp
        .headers()
        .get(axum::http::header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();
    let body = String::from_utf8(resp.into_body().collect().await.unwrap().to_bytes().to_vec()).unwrap();
    (status, ct, body)
}

#[tokio::test]
async fn serves_installed_module_assets_from_cache() {
    let cache = std::env::temp_dir().join(format!("erplora-assets-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&cache);
    let dir = write_module(&cache, "demo", "9.9.9");

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&dir).await.unwrap(); // registra demo@9.9.9 en el runtime
    let state = AppState::with_config(rt, cfg(cache.clone()));

    // module.json → JSON real del cache, NO el index.html del fallback SPA.
    let (status, ct, body) = get(app(state.clone()), "/modules/demo/module.json").await;
    assert_eq!(status, StatusCode::OK);
    assert!(ct.contains("application/json"), "content-type debe ser JSON, no text/html: {ct}");
    assert!(body.contains("\"id\":\"demo\""), "debe servir el module.json real: {body}");

    // El bundle del Web Component.
    let (status, ct, body) = get(app(state.clone()), "/modules/demo/dist/demo.esm.js").await;
    assert_eq!(status, StatusCode::OK);
    assert!(ct.contains("javascript"), "content-type debe ser JS: {ct}");
    assert!(body.contains("export const x"), "debe servir el bundle real del WC");

    // Módulo no instalado → 404 (no cae al SPA).
    let (status, ..) = get(app(state.clone()), "/modules/ausente/module.json").await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    // Guard anti path-traversal (%2e%2e = `..`) → 404.
    let (status, ..) = get(app(state), "/modules/demo/%2e%2e/%2e%2e/secret").await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    let _ = std::fs::remove_dir_all(&cache);
}
