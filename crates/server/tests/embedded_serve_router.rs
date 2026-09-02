//! ADR-0050 (mismo origen): el runtime —construido DESDE la config con `web_dir` seteado— sirve el
//! `dist/` Y la API en el MISMO router (sin CORS), para que `HttpWsTransport` (RUNTIME_URL='')
//! alcance el servidor. Cubre el camino REAL config→router (`build_router`), no
//! `with_static_frontend` aislado (que ya cubre `spa_frontend.rs` con un router de API falso).
//!
//! (Decía «igual que `embedded_serve_config` del shell Tauri»: ese runtime embebido ya no existe —
//! la ventana navega al servidor remoto, ADR-0159.) La CSP vive ahora en `cloud_csp.rs`; lo que
//! queda aquí de `with_csp` es solo que el header sale en la respuesta.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{build_router, with_csp, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use tower::ServiceExt; // oneshot

const INDEX_HTML: &str = "<!doctype html><title>ERPlora SPA</title><div id=app></div>";

/// `dist/` temporal con un `index.html` reconocible. Sin `Date`/`rand`: nombre por PID del test.
fn temp_dist() -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora_adr0050_embed_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("index.html"), INDEX_HTML).unwrap();
    dir
}

/// `AppState` mínimo (SQLite en memoria, sin módulos): basta para `/healthz` + estático. Mismo patrón
/// que `tests/http.rs::make_app`.
async fn make_state() -> AppState {
    let db = fresh_db().await;
    let rt = Runtime::new(Box::new(db));
    AppState::with_config(rt, HubConfig::from_env_with_auth(AuthMode::Dev))
}

async fn body(resp: axum::response::Response) -> Vec<u8> {
    resp.into_body()
        .collect()
        .await
        .unwrap()
        .to_bytes()
        .to_vec()
}

#[tokio::test]
async fn embedded_router_serves_index_and_api_same_origin() {
    let dist = temp_dist();
    let web_dir = dist.to_string_lossy().into_owned();

    // GET / → index.html (el origen del runtime sirve el front).
    let resp = build_router(make_state().await, Some(&web_dir))
        .oneshot(Request::get("/").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert!(
        String::from_utf8_lossy(&body(resp).await).contains("ERPlora SPA"),
        "GET / sirve el index.html del dist (mismo origen que /api)"
    );

    // GET /healthz → API, MISMO router ⇒ HttpWsTransport(RUNTIME_URL='') alcanza el loopback.
    let resp = build_router(make_state().await, Some(&web_dir))
        .oneshot(Request::get("/healthz").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        body(resp).await,
        b"ok",
        "la API gana sobre el estático en el mismo router"
    );

    // Una ruta del router de cliente (sin fichero) cae al index.html (fallback SPA).
    let resp = build_router(make_state().await, Some(&web_dir))
        .oneshot(
            Request::get("/dashboard/inventory")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert!(String::from_utf8_lossy(&body(resp).await).contains("ERPlora SPA"));

    let _ = std::fs::remove_dir_all(&dist);
}

#[tokio::test]
async fn with_csp_emite_el_header_content_security_policy() {
    // ADR-0050: al servir el documento desde Axum (mismo origen), la CSP de `tauri.conf` ya NO
    // aplica al doc → el runtime debe emitir el header. Guarda que `with_csp` lo añade a las
    // respuestas (cubre tanto el SPA como la API; en la API es inocuo).
    let policy = "default-src 'self'; connect-src 'self' ipc:; object-src 'none'";
    let router = with_csp(build_router(make_state().await, None), policy);
    let resp = router
        .oneshot(Request::get("/healthz").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        resp.headers()
            .get("content-security-policy")
            .map(|v| v.to_str().unwrap()),
        Some(policy),
        "el runtime emite la CSP como header de respuesta"
    );
}

#[tokio::test]
async fn embedded_router_without_web_dir_is_api_only() {
    // `web_dir=None` (estado HOY del embebido en Tauri): el front NO se sirve mismo-origen → GET /
    // es 404 (no hay fallback estático). Guarda el gap que cierra ADR-0050; la API sigue intacta.
    let resp = build_router(make_state().await, None)
        .oneshot(Request::get("/").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    let resp = build_router(make_state().await, None)
        .oneshot(Request::get("/healthz").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "sin web_dir la API sigue funcionando"
    );
}
