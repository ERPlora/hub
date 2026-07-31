//! Gestor de media (`/api/media*`) en Hub Cloud (Postgres-only, ADR-0154): cada endpoint es un
//! **proxy autenticado Hub→Cloud→Object Storage**. El fixture arranca un **mini-Cloud** que captura
//! las peticiones (mismo patrón que `module_storage`) y apunta `cloud_base_url` a él, para poder
//! afirmar tanto el 2xx del endpoint como que el Cloud recibió la petición esperada.
//!
//! Las afirmaciones de autorización (anónimo → 401, empleado no-admin → 401) corren ANTES del
//! dispatch al backend, así que no tocan el Cloud.

use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::{Request, State};
use axum::http::StatusCode;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

/// Petición capturada por el mini-Cloud: (método, path).
type Captured = Arc<Mutex<Vec<(String, String)>>>;

/// Mini-Cloud: captura cada petición y responde `200 {}` (JSON parseable → el proxy del listado no
/// falla al deserializar, y el `{}` vacío degrada con los defaults del contrato del frontend).
async fn capture(State(captured): State<Captured>, request: Request) -> Json<Value> {
    let method = request.method().to_string();
    let path = request.uri().path().to_string();
    captured.lock().unwrap().push((method, path));
    Json(json!({}))
}

/// Levanta el mini-Cloud en un puerto efímero; devuelve (base_url, captura).
async fn spawn_mock_cloud() -> (String, Captured) {
    let captured: Captured = Arc::new(Mutex::new(Vec::new()));
    let appx = Router::new().fallback(capture).with_state(captured.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, appx).await.unwrap() });
    (format!("http://{addr}"), captured)
}

/// Fixture: BD Postgres efímera (esquema propio) + Cloud simulado. Devuelve el router, las sesiones
/// de admin y empleado, y la captura de peticiones del Cloud.
async fn fixture() -> (axum::Router, String, String, Captured) {
    let (cloud_base_url, captured) = spawn_mock_cloud().await;

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-media");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let employee_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();

    let cfg = HubConfig {
        hub_id: "hub-media".into(),
        cloud_base_url,
        module_cache: std::env::temp_dir().join("erplora-media-api-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        // El fixture prueba autorización humana de media + el proxy al Cloud, no el alta de máquina.
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-media-api-scratch"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
    };
    (app(AppState::with_config(rt, cfg)), admin, employee, captured)
}

#[tokio::test]
async fn media_requires_a_human_session_even_for_reads() {
    let (router, _admin, employee, captured) = fixture().await;

    // Anónimo → 401 ANTES de tocar el Cloud.
    let anonymous = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/media")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    // Sesión de usuario → 200; el listado se proxya al Cloud.
    let authenticated = router
        .oneshot(
            Request::builder()
                .uri("/api/media")
                .header("x-hub-session", employee)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(authenticated.status(), StatusCode::OK);

    // El Cloud recibió el listado (GET a …/media/).
    let calls = captured.lock().unwrap();
    assert!(
        calls
            .iter()
            .any(|(method, path)| method == "GET" && path.ends_with("/media/")),
        "el proxy debe pedir el listado al Cloud, got {calls:?}",
    );
}

#[tokio::test]
async fn only_admin_can_modify_media() {
    let (router, admin, employee, captured) = fixture().await;
    let body = json!({ "parent": "", "name": "facturas" }).to_string();

    // Empleado no-admin → 401 ANTES de tocar el Cloud.
    let denied = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/media/folder")
                .header("content-type", "application/json")
                .header("x-hub-session", employee)
                .body(Body::from(body.clone()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);
    assert!(
        captured.lock().unwrap().is_empty(),
        "un 401 no debe llegar a proxyar al Cloud",
    );

    // Admin → 200; la creación de carpeta se proxya al Cloud.
    let allowed = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/media/folder")
                .header("content-type", "application/json")
                .header("x-hub-session", admin)
                .body(Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(allowed.status(), StatusCode::OK);

    // El Cloud recibió la creación de carpeta (POST a …/media/folder/).
    let calls = captured.lock().unwrap();
    assert!(
        calls
            .iter()
            .any(|(method, path)| method == "POST" && path.ends_with("/media/folder/")),
        "el proxy debe crear la carpeta en el Cloud, got {calls:?}",
    );
}
