//! Tests de integración de la capa SERVER del export/import de blueprints (ADR-0113).
//!
//! Cubre la superficie HTTP (`/api/hub/export`, `/api/hub/import/inspect`, `/api/hub/import`)
//! La mayoría valida la capa HTTP sin depender del motor del runtime: auth 401, validación de
//! payload 4xx, anti zip-slip, integridad sha256 y limpieza del temporal. Los dos flujos
//! completos (export → zip → inspect → import) atraviesan el motor REAL de
//! `export_hub`/`import_sections` (Fase 1-2, verde desde 2026-07-12).
//!
//! Patrón: router en memoria + `tower::ServiceExt::oneshot` (como `tests/http.rs`).
use std::io::Write as _;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::SqliteAdapter;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// Config de test aislada: cache/media en un dir temporal ÚNICO por test (tag), sin red real
/// (`cloud_base_url` apunta a un puerto cerrado: cualquier llamada al Cloud falla rápido).
fn test_config(auth_mode: AuthMode, tag: &str) -> HubConfig {
    let base = std::env::temp_dir().join(format!("erplora_expimp_{}_{tag}", std::process::id()));
    HubConfig {
        hub_id: "hub-test".into(),
        cloud_base_url: "http://127.0.0.1:1".into(),
        module_cache: base.join("module_cache"),
        auth_mode,
        jwt_public_key: None,
        // Estos tests validan export/import y su auth de usuario, no el bootstrap de máquina.
        // Marcar la máquina como registrada permite atravesar la barrera global y llegar a la
        // superficie que cada caso pretende comprobar.
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: base.join("media"),
        sector: None,
    }
}

async fn make_app(auth_mode: AuthMode, tag: &str) -> axum::Router {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let rt = Runtime::with_hub_id(Box::new(db), "hub-test");
    app(AppState::with_config(rt, test_config(auth_mode, tag)))
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// POST JSON (modo Dev: el gate admin concede sin sesión).
fn post_json(uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .body(Body::from(body.to_string()))
        .unwrap()
}

/// POST del zip crudo (`application/octet-stream`) — contrato del inspect.
fn post_zip(uri: &str, bytes: Vec<u8>) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/octet-stream")
        .body(Body::from(bytes))
        .unwrap()
}

/// Construye en memoria un zip con las entradas `(nombre, contenido)` dadas (patrón de
/// `erplora-source`); permite nombres maliciosos (`../evil`) para los tests de zip-slip.
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
    let d = Sha256::digest(bytes);
    d.iter().map(|b| format!("{b:02x}")).collect()
}

/// `manifest.json` mínimo válido (contrato `BlueprintManifest` del runtime) con el mapa
/// `sha256` dado. `schema_version` parametrizable para el test de versión desconocida.
fn manifest_json(schema_version: u32, sha256: Value) -> String {
    json!({
        "schema_version": schema_version,
        "name": "barberia",
        "locale": "es",
        "hub": { "name": "Demo", "country": "ES", "currency": "EUR" },
        "created_at": "2026-07-12T00:00:00Z",
        "modules": [],
        "sections": [],
        "sha256": sha256,
    })
    .to_string()
}

// ─────────────────────────── POST /api/hub/export ───────────────────────────

/// Sin credencial (modo Session, sin `X-Hub-Session`) → 401, sin tocar el motor.
#[tokio::test]
async fn export_without_session_is_401() {
    let app = make_app(AuthMode::Session, "export_401").await;
    let resp = app
        .oneshot(post_json(
            "/api/hub/export",
            json!({ "name": "barberia", "locale": "es", "selection": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(body_json(resp).await["ok"], json!(false));
}

/// Nombre con separadores de ruta (`../evil`) → 422 (el nombre acaba en un filename).
#[tokio::test]
async fn export_with_traversal_name_is_422() {
    let app = make_app(AuthMode::Dev, "export_badname").await;
    let resp = app
        .oneshot(post_json(
            "/api/hub/export",
            json!({ "name": "../evil", "locale": "es", "selection": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// Nombre vacío → 422.
#[tokio::test]
async fn export_with_empty_name_is_422() {
    let app = make_app(AuthMode::Dev, "export_emptyname").await;
    let resp = app
        .oneshot(post_json("/api/hub/export", json!({ "name": "", "selection": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// Locale con basura (`e/s`) → 422.
#[tokio::test]
async fn export_with_invalid_locale_is_422() {
    let app = make_app(AuthMode::Dev, "export_badlocale").await;
    let resp = app
        .oneshot(post_json(
            "/api/hub/export",
            json!({ "name": "barberia", "locale": "e/s", "selection": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// Body ausente/no-JSON → 4xx (nunca 5xx ni panic).
#[tokio::test]
async fn export_without_body_is_4xx() {
    let app = make_app(AuthMode::Dev, "export_nobody").await;
    let resp = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/export")
                .header("content-type", "application/json")
                .body(Body::from("no-json"))
                .unwrap(),
        )
        .await
        .unwrap();
    assert!(resp.status().is_client_error(), "status = {}", resp.status());
}

/// Flujo completo: export → zip con manifest.json. Atraviesa `export_hub` del runtime.
#[tokio::test]
async fn export_returns_blueprint_zip() {
    let app = make_app(AuthMode::Dev, "export_full").await;
    let resp = app
        .oneshot(post_json(
            "/api/hub/export",
            json!({
                "name": "barberia",
                "locale": "es",
                "selection": {
                    "users": true, "settings": true, "settings_items": null,
                    "fiscal": false, "media": false, "modules": []
                }
            }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let ct = resp.headers().get("content-type").unwrap().to_str().unwrap().to_string();
    assert_eq!(ct, "application/zip");
    let cd = resp.headers().get("content-disposition").unwrap().to_str().unwrap().to_string();
    assert!(cd.contains("barberia_es.blueprint.zip"), "content-disposition = {cd}");
    // El body es un zip real con manifest.json en la raíz.
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let mut ar = zip::ZipArchive::new(std::io::Cursor::new(bytes.to_vec())).unwrap();
    assert!(ar.by_name("manifest.json").is_ok());
}

// ─────────────────────── POST /api/hub/import/inspect ───────────────────────

/// Sin credencial → 401 antes de tocar el zip.
#[tokio::test]
async fn inspect_without_session_is_401() {
    let app = make_app(AuthMode::Session, "inspect_401").await;
    let zip = build_zip(&[("manifest.json", manifest_json(1, json!({})).as_bytes())]);
    let resp = app.oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// Bytes que no son un zip → 422.
#[tokio::test]
async fn inspect_rejects_non_zip_payload() {
    let app = make_app(AuthMode::Dev, "inspect_garbage").await;
    let resp = app
        .oneshot(post_zip("/api/hub/import/inspect", b"esto no es un zip".to_vec()))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// Cuerpo vacío → 422.
#[tokio::test]
async fn inspect_rejects_empty_body() {
    let app = make_app(AuthMode::Dev, "inspect_empty").await;
    let resp = app.oneshot(post_zip("/api/hub/import/inspect", Vec::new())).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// Zip válido pero sin manifest.json → 422.
#[tokio::test]
async fn inspect_rejects_zip_without_manifest() {
    let app = make_app(AuthMode::Dev, "inspect_nomanifest").await;
    let zip = build_zip(&[("readme.txt", b"sin manifest")]);
    let resp = app.oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// Zip con path-traversal (`../evil`) → rechazado ANTES de leer nada (anti zip-slip).
#[tokio::test]
async fn inspect_rejects_path_traversal_zip() {
    let app = make_app(AuthMode::Dev, "inspect_slip").await;
    let zip = build_zip(&[
        ("manifest.json", manifest_json(1, json!({})).as_bytes()),
        ("../evil", b"pwned"),
    ]);
    let resp = app.oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(false));
}

/// Zip con ruta absoluta (`/etc/evil`) → rechazado (anti zip-slip).
#[tokio::test]
async fn inspect_rejects_absolute_path_zip() {
    let app = make_app(AuthMode::Dev, "inspect_abs").await;
    let zip = build_zip(&[
        ("manifest.json", manifest_json(1, json!({})).as_bytes()),
        ("/etc/evil", b"pwned"),
    ]);
    let resp = app.oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// `schema_version` desconocida → 422 (un bundle de un formato futuro se rechaza sin efectos).
#[tokio::test]
async fn inspect_rejects_unknown_schema_version() {
    let app = make_app(AuthMode::Dev, "inspect_schema").await;
    let zip = build_zip(&[("manifest.json", manifest_json(99, json!({})).as_bytes())]);
    let resp = app.oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// manifest.json que no cumple el struct (campos ausentes) → 422.
#[tokio::test]
async fn inspect_rejects_invalid_manifest_shape() {
    let app = make_app(AuthMode::Dev, "inspect_shape").await;
    let zip = build_zip(&[("manifest.json", br#"{ "schema_version": 1 }"#.as_slice())]);
    let resp = app.oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// Zip válido → 200 `{ ok, upload_id, manifest }` (no atraviesa el motor: solo valida y guarda).
#[tokio::test]
async fn inspect_ok_returns_upload_id_and_manifest() {
    let app = make_app(AuthMode::Dev, "inspect_ok").await;
    let zip = build_zip(&[("manifest.json", manifest_json(1, json!({})).as_bytes())]);
    let resp = app.oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(true));
    let upload_id = j["upload_id"].as_str().unwrap();
    assert!(!upload_id.is_empty());
    // El upload_id es un identificador simple (sin separadores: se usa como componente de ruta).
    assert!(upload_id.chars().all(|c| c.is_ascii_alphanumeric()), "upload_id = {upload_id}");
    assert_eq!(j["manifest"]["name"], json!("barberia"));
    assert_eq!(j["manifest"]["locale"], json!("es"));
}

// ─────────────────────────── POST /api/hub/import ───────────────────────────

/// Sin credencial → 401.
#[tokio::test]
async fn import_without_session_is_401() {
    let app = make_app(AuthMode::Session, "import_401").await;
    let resp = app
        .oneshot(post_json("/api/hub/import", json!({ "upload_id": "abc", "selection": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// upload_id inexistente → 404 (el temporal no existe o caducó).
#[tokio::test]
async fn import_unknown_upload_is_404() {
    let app = make_app(AuthMode::Dev, "import_404").await;
    let resp = app
        .oneshot(post_json(
            "/api/hub/import",
            json!({ "upload_id": "deadbeefdeadbeefdeadbeefdeadbeef", "selection": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    assert_eq!(body_json(resp).await["ok"], json!(false));
}

/// upload_id con traversal (`../../…`) → 404 sin tocar el filesystem fuera del temporal.
#[tokio::test]
async fn import_traversal_upload_id_is_rejected() {
    let app = make_app(AuthMode::Dev, "import_slip").await;
    let resp = app
        .oneshot(post_json(
            "/api/hub/import",
            json!({ "upload_id": "../../../etc/passwd", "selection": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

/// Body sin `upload_id` (payload inválido) → 4xx.
#[tokio::test]
async fn import_without_upload_id_is_4xx() {
    let app = make_app(AuthMode::Dev, "import_nopayload").await;
    let resp = app.oneshot(post_json("/api/hub/import", json!({ "selection": {} }))).await.unwrap();
    assert!(resp.status().is_client_error(), "status = {}", resp.status());
}

/// sha256 que no casa → 422 SIN efectos, y el temporal se borra IGUALMENTE (también en error):
/// un segundo import con el mismo upload_id da 404.
#[tokio::test]
async fn import_sha256_mismatch_is_422_and_cleans_tmp() {
    let app = make_app(AuthMode::Dev, "import_sha").await;
    // manifest declara data/x.sql con un hash que NO corresponde al contenido real.
    let manifest = manifest_json(1, json!({ "data/x.sql": "00".repeat(32) }));
    let zip = build_zip(&[("manifest.json", manifest.as_bytes()), ("data/x.sql", b"hola")]);
    let resp = app.clone().oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let upload_id = body_json(resp).await["upload_id"].as_str().unwrap().to_string();

    // (1) integridad dura: 422 sin efectos.
    let resp = app
        .clone()
        .oneshot(post_json("/api/hub/import", json!({ "upload_id": upload_id, "selection": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);

    // (2) el temporal se borró también en el error → repetir da 404.
    let resp = app
        .oneshot(post_json("/api/hub/import", json!({ "upload_id": upload_id, "selection": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

/// Fichero presente en el zip pero NO listado en `manifest.sha256` → 422 (integridad estricta
/// en ambas direcciones: nada entra sin hash verificable).
#[tokio::test]
async fn import_unlisted_file_is_422() {
    let app = make_app(AuthMode::Dev, "import_unlisted").await;
    let manifest = manifest_json(1, json!({}));
    let zip = build_zip(&[("manifest.json", manifest.as_bytes()), ("data/extra.sql", b"sorpresa")]);
    let resp = app.clone().oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let upload_id = body_json(resp).await["upload_id"].as_str().unwrap().to_string();

    let resp = app
        .oneshot(post_json("/api/hub/import", json!({ "upload_id": upload_id, "selection": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// Flujo completo: import válido → 200 `{ ok, report }` con el informe del runtime EXTENDIDO
/// (installed_modules / media / fiscal). Atraviesa `import_sections` del runtime.
#[tokio::test]
async fn import_valid_bundle_returns_extended_report() {
    let app = make_app(AuthMode::Dev, "import_full").await;
    let sql = b"-- vacio".as_slice();
    let manifest = manifest_json(1, json!({ "data/hub_settings.sql": sha256_hex(sql) }));
    let zip = build_zip(&[("manifest.json", manifest.as_bytes()), ("data/hub_settings.sql", sql)]);
    let resp = app.clone().oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let upload_id = body_json(resp).await["upload_id"].as_str().unwrap().to_string();

    let resp = app
        .clone()
        .oneshot(post_json(
            "/api/hub/import",
            json!({ "upload_id": upload_id, "selection": { "settings": true } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(true));
    assert!(j["report"]["sections"].is_array());
    // Extensión de la capa server: módulos instalados + media + fiscal.
    assert!(j["report"]["installed_modules"].is_array());
    assert_eq!(j["report"]["fiscal"]["certificate"], json!("skipped"));

    // El temporal se consume: repetir el mismo upload_id da 404.
    let resp = app
        .oneshot(post_json("/api/hub/import", json!({ "upload_id": upload_id, "selection": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}
