//! E2E del server: **frontera de la capa web PÚBLICA** del Hub (ADR-0179, F0).
//!
//! Invariante crítica: la parte pública SOLO existe cuando el flag `public.landing.visible` (tabla
//! `hub_settings`, default **false**) está activo. Con el flag desactivado, `/`, `/p/*` y
//! `/api/public/*` se comportan EXACTAMENTE como hoy (gate 428 / fallback SPA→login). El flag se lee
//! del snapshot cacheado en el `AppState` al arrancar (NO se pega a `hub_settings` en cada request).
//!
//! Estos tests inyectan el snapshot directamente (`with_public_snapshot`) para fijar el contrato del
//! router sin depender de la persistencia; la lectura flag←settings se cubre en la unidad
//! (`crate::public::PublicSnapshot::from_settings`) y en `runtime::settings`.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::public::{PublicSnapshot, PUBLIC_CSP};
use erplora_server::{app, build_router, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use tower::ServiceExt; // oneshot

const HUB_ID: &str = "hub-pub-1";
const BUSINESS_NAME: &str = "Bar Pepe";
const BUSINESS_ADDRESS: &str = "Calle Mayor 1";

/// `AppState` en modo `Session`, hub NO enrolado (`cloud_api_token: None` → `machine_registered()`
/// = false), con el snapshot público sembrado según `landing_visible`.
async fn fixture(landing_visible: bool) -> (AppState, std::path::PathBuf) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let temp = std::env::temp_dir().join(format!(
        "erplora-public-f0-{}-{}",
        std::process::id(),
        if landing_visible { "on" } else { "off" }
    ));
    let cfg = HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: None,
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let snap = PublicSnapshot {
        landing_visible,
        business_name: BUSINESS_NAME.into(),
        business_address: BUSINESS_ADDRESS.into(),
        public_origin: Some("https://public.example".into()),
    };
    let state = AppState::with_config(rt, cfg).with_public_snapshot(snap);
    (state, temp)
}

fn get(uri: &str) -> Request<Body> {
    Request::get(uri)
        .header("host", "public.example")
        .body(Body::empty())
        .unwrap()
}

async fn body_string(resp: axum::response::Response) -> String {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    String::from_utf8_lossy(&bytes).into_owned()
}

fn csp_of(resp: &axum::response::Response) -> Option<String> {
    resp.headers()
        .get("content-security-policy")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string())
}

fn cleanup(temp: std::path::PathBuf) {
    let _ = std::fs::remove_dir_all(temp);
}

#[tokio::test]
async fn flag_off_root_and_protected_are_gated_as_today() {
    // Sin capa pública (flag off) y hub sin registrar: `/` y una ruta protegida dan 428, como hoy.
    let (st, temp) = fixture(false).await;

    let resp = app(st.clone()).oneshot(get("/")).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::PRECONDITION_REQUIRED,
        "flag off → GET / se comporta como hoy (428)"
    );

    let resp = app(st).oneshot(get("/api/settings")).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::PRECONDITION_REQUIRED,
        "ruta protegida → 428"
    );
    cleanup(temp);
}

#[tokio::test]
async fn flag_on_root_serves_landing_with_business_data_and_strict_csp() {
    let (st, temp) = fixture(true).await;
    let router = app(st);
    let resp = router.clone().oneshot(get("/")).await.unwrap();

    assert_eq!(resp.status(), StatusCode::OK, "flag on → landing 200 anónima");
    assert_eq!(
        csp_of(&resp).as_deref(),
        Some(PUBLIC_CSP),
        "la landing lleva la CSP estricta"
    );
    let body = body_string(resp).await;
    assert!(
        body.contains(BUSINESS_NAME),
        "la landing pinta un dato de hub_settings (nombre del negocio); body = {body}"
    );

    let etag = router
        .clone()
        .oneshot(get("/"))
        .await
        .unwrap()
        .headers()
        .get("etag")
        .and_then(|value| value.to_str().ok())
        .expect("la landing emite ETag")
        .to_string();
    for matcher in [format!("W/{etag}"), "*".to_string()] {
        let conditional = Request::get("/")
            .header("host", "public.example")
            .header("if-none-match", matcher)
            .body(Body::empty())
            .unwrap();
        assert_eq!(
            router.clone().oneshot(conditional).await.unwrap().status(),
            StatusCode::NOT_MODIFIED
        );
    }
    cleanup(temp);
}

#[tokio::test]
async fn flag_on_page_returns_placeholder_not_gated() {
    let (st, temp) = fixture(true).await;
    let resp = app(st).oneshot(get("/p/algo")).await.unwrap();

    assert_ne!(
        resp.status(),
        StatusCode::PRECONDITION_REQUIRED,
        "/p/* no está gateado con el flag on"
    );
    assert_eq!(
        resp.status(),
        StatusCode::NOT_FOUND,
        "F0: /p/* es un placeholder 404 server-side (las páginas ricas llegan en F1)"
    );
    assert_eq!(csp_of(&resp).as_deref(), Some(PUBLIC_CSP), "placeholder con CSP estricta");
    cleanup(temp);
}

#[tokio::test]
async fn flag_on_protected_route_still_428() {
    let (st, temp) = fixture(true).await;
    let resp = app(st).oneshot(get("/api/settings")).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::PRECONDITION_REQUIRED,
        "con la capa pública abierta, una ruta NO pública sin registro sigue dando 428"
    );
    cleanup(temp);
}

#[tokio::test]
async fn flag_on_healthz_and_context_still_pass() {
    let (st, temp) = fixture(true).await;

    let resp = app(st.clone()).oneshot(get("/healthz")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "/healthz sigue pasando");

    let resp = app(st).oneshot(get("/api/hub/context")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "/api/hub/context sigue pasando");
    let context: serde_json::Value = serde_json::from_str(&body_string(resp).await).unwrap();
    assert_eq!(context["public_landing_visible"], serde_json::json!(true));
    cleanup(temp);
}

#[tokio::test]
async fn flag_on_public_routes_win_over_spa_fallback() {
    // Con front estático montado (build_router), las rutas públicas son EXPLÍCITAS → ganan al
    // fallback SPA: nunca se sirve el index.html haciéndose pasar por landing/página.
    let (st, temp) = fixture(true).await;
    let dist = temp.join("dist");
    std::fs::create_dir_all(&dist).unwrap();
    std::fs::write(
        dist.join("index.html"),
        "<!doctype html><title>ERPlora SPA</title><div id=app></div>",
    )
    .unwrap();
    let web = dist.to_string_lossy().into_owned();

    let resp = build_router(st.clone(), Some(&web))
        .oneshot(get("/"))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_string(resp).await;
    assert!(body.contains(BUSINESS_NAME), "landing, no SPA");
    assert!(!body.contains("ERPlora SPA"), "la landing gana al fallback SPA");

    let resp = build_router(st, Some(&web))
        .oneshot(get("/p/algo"))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let body = body_string(resp).await;
    assert!(
        !body.contains("ERPlora SPA"),
        "el placeholder de /p/* gana al fallback SPA"
    );
    cleanup(temp);
}
