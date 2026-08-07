//! Tests de integración del **gate de entitlement** en el dispatcher HTTP (sin red):
//! un módulo bloqueado por la revalidación híbrida (ver `src/entitlement.rs`) recibe el error
//! estable `module_entitlement_blocked` en `POST /api/query` y `POST /api/command`; un módulo
//! entitled (o un estado sin refresh exitoso = fail-open) pasa con normalidad.
use std::path::PathBuf;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use cloud_client::{EntitledModule, EntitlementClaims};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

fn fixture() -> PathBuf {
    // Reusa el fixture del runtime (módulo inventory completo), como en http.rs.
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_inventory")
}

/// App + estado: devolvemos también el `AppState` para manipular la celda de revalidación
/// desde el test (es exactamente lo que hace el job de background en producción).
async fn make_app() -> (axum::Router, AppState) {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.unwrap();
    let state = AppState::with_config(rt, HubConfig::from_env_with_auth(AuthMode::Dev));
    (app(state.clone()), state)
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

fn post(uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u1")
        .header("x-permissions", "*")
        .body(Body::from(body.to_string()))
        .unwrap()
}

/// Claims verificadas de prueba (campos `pub`; la firma la cubre `verify_entitlement`).
fn claims(modules: &[&str], grace_until: i64) -> EntitlementClaims {
    EntitlementClaims {
        hub_id: "h1".into(),
        modules: modules
            .iter()
            .map(|id| EntitledModule {
                module_id: (*id).to_string(),
                tier: "premium".into(),
                version: "1.0.0".into(),
            })
            .collect(),
        iat: 1_000,
        exp: 2_000,
        grace_until,
        paid_grace_until: None,
        plan: None,
        max_devices: 0,
        max_database_size_gb: 0,
    }
}

#[tokio::test]
async fn query_de_modulo_bloqueado_devuelve_module_entitlement_blocked() {
    let (router, state) = make_app().await;
    // El último refresh EXITOSO no incluye `inventory` → bloqueado ya (verdad del servidor).
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims(&["otro_modulo"], i64::MAX), 1_000);

    let resp = router
        .oneshot(post("/api/query", json!({ "name": "inventory.products.list", "params": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::PAYMENT_REQUIRED);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(false));
    assert_eq!(body["error"]["code"], json!("module_entitlement_blocked"));
    assert_eq!(body["error"]["module_id"], json!("inventory"));
}

#[tokio::test]
async fn command_de_modulo_bloqueado_devuelve_module_entitlement_blocked() {
    let (router, state) = make_app().await;
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims(&["otro_modulo"], i64::MAX), 1_000);

    let resp = router
        .oneshot(post(
            "/api/command",
            json!({ "name": "inventory.products.create", "payload": { "sku": "A-1", "name": "Widget" } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::PAYMENT_REQUIRED);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(false));
    assert_eq!(body["error"]["code"], json!("module_entitlement_blocked"));
    assert_eq!(body["error"]["module_id"], json!("inventory"));
}

#[tokio::test]
async fn modulo_entitled_pasa_con_normalidad() {
    let (router, state) = make_app().await;
    // El último refresh OK SÍ incluye `inventory` → el gate no interfiere.
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims(&["inventory"], i64::MAX), 1_000);

    let resp = router
        .oneshot(post("/api/query", json!({ "name": "inventory.products.list", "params": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
}

#[tokio::test]
async fn sin_refresh_exitoso_el_gate_es_fail_open() {
    // Estado inicial (dev/local sin enrolar): nada bloqueado, todo funciona como hoy.
    let (router, _state) = make_app().await;
    let resp = router
        .oneshot(post("/api/query", json!({ "name": "inventory.products.list", "params": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
}

#[tokio::test]
async fn proxy_entitlement_incluye_revalidation_aunque_el_cloud_no_responda() {
    // Cloud inalcanzable (puerto de descarte, conexión rechazada): el proxy sigue devolviendo su
    // error (502, contrato actual) pero con el bloque ADITIVO `revalidation`, para que la UI
    // pueda pintar «funcionará hasta {fecha}» incluso offline.
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.unwrap();
    let cfg = HubConfig {
        hub_id: "h1".into(),
        cloud_base_url: "http://127.0.0.1:9".into(), // puerto discard: rechazo inmediato
        module_cache: std::env::temp_dir().join("erplora-test-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("tok-maquina".into()), // hub enrolado → el proxy intenta la red
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-test-media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: None,
    };
    let state = AppState::with_config(rt, cfg);
    // Estado sembrado por el job: último token válido con gracia 9_000, sin bloqueos.
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims(&["inventory"], 9_000), 1_000);
    let router = app(state.clone());

    let resp = router
        .oneshot(Request::builder().uri("/api/entitlement").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_GATEWAY); // contrato actual intacto
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(false)); // contrato actual intacto
    assert_eq!(body["revalidation"]["grace_until"], json!(9_000)); // bloque aditivo nuevo
    assert_eq!(body["revalidation"]["blocked_modules"], json!([]));
    assert_eq!(body["revalidation"]["last_refresh_ok_at"], json!(1_000));
}
