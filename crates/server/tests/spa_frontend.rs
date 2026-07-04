//! Contrato de servir el frontend en el MISMO origen que la API (ADR-0050, "app unificada").
//!
//! Hub Cloud ya lo cumple: el Axum sirve el `dist/` (`HUB_WEB_DIR` → [`with_static_frontend`]) y el
//! front habla HTTP+WS al MISMO origen, sin `invoke`/IPC para datos. Completar ADR-0050 en Hub Local
//! consiste en que el runtime embebido (loopback `127.0.0.1:8787`) sirva también el `dist/`, para que
//! el webview de Tauri cargue front + datos del mismo origen (el cambio de wiring del shell es columna
//! core/humano). Este test fija el contrato del mecanismo que ese wiring reutiliza:
//!   - las rutas de API (`/api/*`, `/healthz`) NO quedan ensombrecidas por el estático;
//!   - cualquier otra ruta cae al `index.html` (fallback SPA) → el router de cliente funciona.
//!
//! Si esto se rompe, "el front y los datos comparten origen" deja de cumplirse y reaparece la
//! tentación del puente IPC que ADR-0050 elimina.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::routing::get;
use axum::Router;
use http_body_util::BodyExt;
use tower::ServiceExt; // oneshot

const INDEX_HTML: &str = "<!doctype html><title>ERPlora SPA</title><div id=app></div>";

/// Prepara un `dist/` temporal con un `index.html` reconocible. Sin `Date`/`rand` (no disponibles en
/// el sandbox de scripts ni necesarios aquí): el nombre se deriva del PID del proceso de test.
fn temp_dist() -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora_adr0050_spa_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).expect("crear dist temporal");
    std::fs::write(dir.join("index.html"), INDEX_HTML).expect("escribir index.html");
    dir
}

async fn body_string(resp: axum::response::Response) -> String {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    String::from_utf8(bytes.to_vec()).unwrap()
}

/// Construye el router de prueba: dos rutas de API + el frontend estático con fallback SPA, igual que
/// monta el runtime cuando sirve el `dist/`.
fn router_with_front(dist: &std::path::Path) -> Router {
    let api = Router::new()
        .route("/api/ping", get(|| async { "pong" }))
        .route("/healthz", get(|| async { "ok" }));
    erplora_server::with_static_frontend(api, dist.to_str().unwrap())
}

#[tokio::test]
async fn api_routes_are_not_shadowed_by_the_static_frontend() {
    let dist = temp_dist();
    let resp = router_with_front(&dist)
        .oneshot(Request::get("/api/ping").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_string(resp).await, "pong", "la API gana sobre el estático");

    let resp = router_with_front(&dist)
        .oneshot(Request::get("/healthz").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_string(resp).await, "ok");

    let _ = std::fs::remove_dir_all(&dist);
}

#[tokio::test]
async fn root_serves_index_html_same_origin() {
    let dist = temp_dist();
    let resp = router_with_front(&dist)
        .oneshot(Request::get("/").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert!(
        body_string(resp).await.contains("ERPlora SPA"),
        "GET / sirve el index.html del dist (mismo origen que /api)"
    );
    let _ = std::fs::remove_dir_all(&dist);
}

#[tokio::test]
async fn unknown_client_route_falls_back_to_spa_index() {
    let dist = temp_dist();
    // Una ruta del router de cliente (sin fichero en disco) debe servir el index.html, no 404 — así
    // un refresco en `/dashboard` o `/modules/...` carga la SPA en lugar de romper.
    let resp = router_with_front(&dist)
        .oneshot(Request::get("/dashboard/inventory").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert!(
        body_string(resp).await.contains("ERPlora SPA"),
        "ruta SPA desconocida → fallback al index.html"
    );
    let _ = std::fs::remove_dir_all(&dist);
}
