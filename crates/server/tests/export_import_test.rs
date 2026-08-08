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
use erplora_db::testutil::fresh_db;
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
        demo: false,
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
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: None,
    }
}

async fn make_app(auth_mode: AuthMode, tag: &str) -> axum::Router {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-test");
    app(AppState::with_config(rt, test_config(auth_mode, tag)))
}

/// Router + a SECOND handle on the same ephemeral schema, so a test can seed system tables the HTTP
/// surface has no endpoint for (the delegated certificate slot arrives from the control plane, not
/// from a request — ADR-0202 §2). The system schema is migrated first, exactly as boot does it.
async fn make_app_with_db(auth_mode: AuthMode, tag: &str) -> (axum::Router, erplora_db::PgAdapter) {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-test");
    rt.ensure_system_tables().await.expect("esquema de sistema");
    let side = test_db.adapter().await;
    (app(AppState::with_config(rt, test_config(auth_mode, tag))), side)
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

// ── ADR-0202 §2.1 (hub#316): el slot `delegated` NUNCA sale del hub ─────────────────────────

/// Bytes reales de cada slot: el `.p12` del NEGOCIO y el de ERPlora. No comparten subcadena, así
/// que un test que afirma que uno no se filtró no puede pasar por casualidad sobre el otro.
const OWN_P12: &[u8] = b"OWN-PKCS12";
const DELEGATED_P12: &[u8] = b"DELEGATED-PKCS12";
/// Sus base64, que es como viven en `_hub_certificate.pkcs12_b64`.
const OWN_P12_B64: &str = "T1dOLVBLQ1MxMg==";
const DELEGATED_P12_B64: &str = "REVMRUdBVEVELVBLQ1MxMg==";

/// Siembra un slot de `_hub_certificate` **en claro** (fila legacy, anterior al cifrado at-rest de
/// hub#114): el core la sigue leyendo sin master key, así que el test no depende de una variable de
/// entorno global que otro test en paralelo podría estar cambiando.
async fn seed_certificate_slot(db: &erplora_db::PgAdapter, kind: &str, pkcs12_b64: &str) {
    use erplora_db::DatabaseAdapter as _;
    db.execute_batch(&format!(
        "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES ('hub-test', '{kind}', '{pkcs12_b64}', 'pw-{kind}', '2026-08-07T00:00:00Z', 'seed');"
    ))
    .await
    .unwrap();
}

/// Todas las entradas del zip `(nombre, bytes)` — el artefacto REAL que se descarga.
fn zip_entries(bytes: &[u8]) -> Vec<(String, Vec<u8>)> {
    use std::io::Read as _;
    let mut ar = zip::ZipArchive::new(std::io::Cursor::new(bytes.to_vec())).unwrap();
    let mut out = Vec::new();
    for i in 0..ar.len() {
        let mut f = ar.by_index(i).unwrap();
        let name = f.name().to_string();
        let mut buf = Vec::new();
        f.read_to_end(&mut buf).unwrap();
        out.push((name, buf));
    }
    out
}

/// ¿Aparecen estos bytes en ALGUNA entrada del zip? Se busca sobre el artefacto entero —manifest
/// incluido—, no sobre una lista de rutas conocidas: una fuga que estrenase un fichero nuevo pasaría
/// por delante de una comprobación que solo mira `data/fiscal/certificate.p12`.
fn zip_contains(entries: &[(String, Vec<u8>)], needle: &[u8]) -> bool {
    entries.iter().any(|(_, bytes)| bytes.windows(needle.len()).any(|w| w == needle))
}

async fn export_with_fiscal(app: axum::Router, tag: &str) -> Vec<(String, Vec<u8>)> {
    let body = json!({
        "name": tag,
        "locale": "es",
        "selection": {
            "users": true, "settings": true, "settings_items": null,
            "fiscal": true, "media": false, "modules": []
        }
    });
    // `X-Hub-Id` fija el hub del PLANO DE DATOS: en modo Dev el export vuelca el hub de la cabecera
    // (`local` por defecto), no el de la config, así que sin esto miraría un hub sin certificados.
    let req = Request::builder()
        .method("POST")
        .uri("/api/hub/export")
        .header("content-type", "application/json")
        .header("x-hub-id", "hub-test")
        .body(Body::from(body.to_string()))
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    zip_entries(&bytes)
}

/// **La regla de hub#316, sobre el zip de verdad.**
///
/// El certificado delegado es la clave privada con la que ERPlora se identifica ante la AEAT por
/// apoderamiento, para TODA la flota. Un bundle se descarga, se publica en el catálogo y se importa
/// en el hub de otro: si sale una vez, sale para siempre y no compromete a un negocio, sino a todos.
/// El propio sí viaja (es el backup de su dueño, y su contraseña no va dentro).
///
/// Recorre los **dos** estados del hub, y el orden importa: con certificado propio la regla se
/// cumple sola (el propio gana la selección y el delegado ni se lee), así que un test que solo
/// mirase ese caso pasaría igual con la exclusión quitada. El estado que de verdad la ejercita es el
/// hub que SOLO tiene el delegado — el que va a ser normal en cuanto el plano de control reparta
/// (hub#317). Mutación que este test tiene que cazar:
/// `CertificateKind::Delegated => may_leave_the_hub() = true`.
#[tokio::test]
async fn the_export_never_carries_the_delegated_certificate() {
    let (app, db) = make_app_with_db(AuthMode::Dev, "export_delegated_out").await;

    // (1) Hub que FIRMA con el delegado porque no tiene propio: exporta CERO certificados. Es el
    //     caso que separa las dos preguntas — «con cuál firmo» y «cuál puede salir» no son la misma.
    seed_certificate_slot(&db, "delegated", DELEGATED_P12_B64).await;
    let entries = export_with_fiscal(app.clone(), "solodelegado").await;
    assert!(
        !entries.iter().any(|(name, _)| name == "data/fiscal/certificate.p12"),
        "sin certificado propio no hay certificado que exportar"
    );
    assert!(
        !zip_contains(&entries, DELEGATED_P12),
        "el .p12 delegado de ERPlora ha salido del hub dentro del bundle: {:?}",
        entries.iter().map(|(n, _)| n).collect::<Vec<_>>()
    );

    // (2) El negocio sube el suyo: ese sí viaja, y el delegado sigue sin aparecer.
    seed_certificate_slot(&db, "own", OWN_P12_B64).await;
    let entries = export_with_fiscal(app, "conlosdos").await;
    let cert = entries
        .iter()
        .find(|(name, _)| name == "data/fiscal/certificate.p12")
        .map(|(_, b)| b.clone())
        .expect("el certificado PROPIO del negocio sí viaja en su backup");
    assert_eq!(cert, OWN_P12, "viaja el del negocio, no otro");
    assert!(!zip_contains(&entries, DELEGATED_P12), "el .p12 delegado se ha colado en el bundle");
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

/// Zip-slip DENTRO de `media/` (`media/../../evil`, hub#239): los `media/**` son las únicas
/// entradas del bundle que aterrizan en DISCO, así que la travesía se rechaza en el inspect —
/// antes de guardar el temporal y mucho antes de copiar nada.
#[tokio::test]
async fn inspect_rejects_media_path_traversal_zip() {
    let app = make_app(AuthMode::Dev, "inspect_media_slip").await;
    let zip = build_zip(&[
        ("manifest.json", manifest_json(1, json!({})).as_bytes()),
        ("media/../../evil", b"pwned"),
    ]);
    let resp = app.oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(false));
    assert!(
        j["error"]["message"].as_str().unwrap_or_default().contains("zip inseguro"),
        "el motivo nombra la ruta insegura: {j}"
    );
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

/// 🔴 [ADR-0195, hub#305] El certificado fiscal lo materializa ESTA capa, no el motor: el `.p12`
/// nunca se aplica solo (su contraseña no viaja), pero el informe decía `pending` — «súbelo en
/// Ajustes → Negocio». Con un bundle `template`, ese `pending` es una invitación a instalarse la
/// identidad fiscal **de otro negocio**: NIF, entorno VeriFactu y certificado de firma ajenos.
///
/// Es el mismo plano consumidor que el guard del runtime, en la única sección que el runtime no
/// puede cerrar porque no es suya.
#[tokio::test]
async fn una_plantilla_no_ofrece_el_certificado_fiscal_que_traiga() {
    let app = make_app(AuthMode::Dev, "import_template_fiscal").await;
    let p12 = b"no soy un .p12 de verdad, pero ocupo su sitio".as_slice();
    let manifest = json!({
        "schema_version": 1,
        // Lo que hace de este bundle un artefacto público: declara ser una plantilla…
        "purpose": "template",
        "name": "restaurante",
        "locale": "es",
        "hub": { "name": "Demo", "country": "ES", "currency": "EUR" },
        "created_at": "2026-08-03T00:00:00Z",
        "modules": [],
        "sections": ["fiscal"],
        "sha256": { "data/fiscal/certificate.p12": sha256_hex(p12) },
    })
    .to_string();
    // …y aun así lleva el certificado dentro (bundle anterior al gate, o fichero local).
    let zip = build_zip(&[
        ("manifest.json", manifest.as_bytes()),
        ("data/fiscal/certificate.p12", p12),
    ]);
    let resp = app.clone().oneshot(post_zip("/api/hub/import/inspect", zip)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let upload_id = body_json(resp).await["upload_id"].as_str().unwrap().to_string();

    // Se PIDE fiscal explícitamente: el propósito tiene que ganar a la casilla.
    let resp = app
        .oneshot(post_json(
            "/api/hub/import",
            json!({ "upload_id": upload_id, "selection": { "fiscal": true } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(
        j["report"]["fiscal"]["certificate"],
        json!("ignored"),
        "una plantilla no puede ofrecer el certificado de otro negocio: {}",
        j["report"]["fiscal"]
    );
    // Y la sección del motor lo dice con su motivo, no en silencio.
    let fiscal = j["report"]["sections"]
        .as_array()
        .expect("sections")
        .iter()
        .find(|s| s["section"] == json!("fiscal"))
        .expect("la sección fiscal debe salir en el informe")
        .clone();
    assert!(
        fiscal["status"]["Ignored"].is_string(),
        "fiscal debía reportarse como Ignored con motivo: {fiscal}"
    );
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
