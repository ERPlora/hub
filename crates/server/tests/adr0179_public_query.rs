//! Tests de integración de la INTEGRACIÓN de la capa web pública (ADR-0179, Wave 2) por HTTP
//! (sin red): el endpoint anónimo `POST /api/public/query` (default-deny + `hub_id` de sistema) y
//! el cableado de `GET /p/<path>` (bloques → HTML seguro). Mismo estilo que `tests/public_api.rs`
//! (`tower::ServiceExt::oneshot`).
//!
//! INVARIANTE (Ioan): TODO lo público solo existe con `public.landing.visible == true`; con el flag
//! desactivado el árbol público no está montado y el hub se comporta como hoy.
use std::path::PathBuf;

use axum::body::Body;
use axum::extract::ConnectInfo;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::Runtime;
use erplora_server::public::{PublicSnapshot, PUBLIC_CSP};
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};

const HUB_ID: &str = "hub-public-1";

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_public_query")
}

fn dev_config() -> HubConfig {
    HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache: std::env::temp_dir().join("erplora-public-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        // La máquina está "registrada" para que el gate 428 no enmascare el resultado que probamos.
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-public-media"),
        sector: None,
        dev_mode: true,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

/// Snapshot con la capa pública ACTIVA (flag on).
fn snapshot_on() -> PublicSnapshot {
    PublicSnapshot {
        landing_visible: true,
        business_name: "Bar Pepe".into(),
        business_address: "Calle Mayor 1".into(),
        public_origin: Some("https://public.example".into()),
    }
}

/// Runtime con el módulo `menu` instalado (query pública + query privada + command) y las tablas
/// de sistema. Devuelve el runtime SIN moverlo al AppState (para poder sembrar antes).
async fn make_runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    rt
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn body_text(resp: axum::response::Response) -> String {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    String::from_utf8(bytes.to_vec()).unwrap()
}

fn public_query(query: &str, params: Value) -> Request<Body> {
    public_query_from(query, params, Ipv4Addr::new(127, 0, 0, 1))
}

fn public_query_from(query: &str, params: Value, ip: Ipv4Addr) -> Request<Body> {
    let mut request = Request::builder()
        .method("POST")
        .uri("/api/public/query")
        .header("host", "public.example")
        .header("content-type", "application/json")
        .body(Body::from(json!({ "query": query, "params": params }).to_string()))
        .unwrap();
    request.extensions_mut().insert(ConnectInfo(SocketAddr::new(IpAddr::V4(ip), 43210)));
    request
}

fn get(uri: &str) -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri(uri)
        .header("host", "public.example")
        .body(Body::empty())
        .unwrap()
}

fn admin_json(method: &str, uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method(method)
        .uri(uri)
        .header("host", "public.example")
        .header("content-type", "application/json")
        .header("x-hub-id", HUB_ID)
        .header("x-user-id", "owner")
        .header("x-permissions", "*")
        .body(Body::from(body.to_string()))
        .unwrap()
}

// ── Flag OFF: el árbol público NO existe (comportamiento de hoy) ────────────────────────────────

#[tokio::test]
async fn flag_off_public_query_not_accessible() {
    // Sin snapshot → capa pública CERRADA (default). La ruta no está montada.
    let app = app(AppState::with_config(make_runtime().await, dev_config()));
    let resp = app
        .oneshot(public_query("menu.items.list", json!({})))
        .await
        .unwrap();
    // Con el flag off NO hay endpoint público: nunca devuelve 200 con datos.
    assert_ne!(resp.status(), StatusCode::OK, "flag off no debe exponer datos públicos");
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn flag_off_page_behaves_like_today() {
    let app = app(AppState::with_config(make_runtime().await, dev_config()));
    let resp = app.oneshot(get("/p/menu")).await.unwrap();
    // `/p/*` no está montado con el flag off → no es una página pública.
    assert_ne!(resp.status(), StatusCode::OK);
}

// ── Flag ON: endpoint anónimo de queries ────────────────────────────────────────────────────────

#[tokio::test]
async fn flag_on_public_query_returns_rows_with_system_hub_id() {
    let app = app(AppState::with_config(make_runtime().await, dev_config())
        .with_public_snapshot(snapshot_on()));
    let resp = app
        .oneshot(public_query("menu.items.list", json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(true));
    let rows = j["data"].as_array().expect("data es un array de filas");
    assert_eq!(rows.len(), 1, "la seed del módulo aporta 1 fila: {j}");
    assert_eq!(rows[0]["name"], json!("Cafe con leche"));
    // El hub_id lo inyecta el runtime (contexto de sistema), no el cliente.
    assert_eq!(rows[0]["hub_id"], json!(HUB_ID));
}

#[tokio::test]
async fn flag_on_non_public_query_is_default_denied() {
    let app = app(AppState::with_config(make_runtime().await, dev_config())
        .with_public_snapshot(snapshot_on()));
    // `menu.items.secret` EXISTE pero no está marcada `public` → default-deny, sin revelar existencia.
    let resp = app
        .oneshot(public_query("menu.items.secret", json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn flag_on_command_via_public_query_is_rejected() {
    let app = app(AppState::with_config(make_runtime().await, dev_config())
        .with_public_snapshot(snapshot_on()));
    // Un command NUNCA es ejecutable por esta vía (solo queries): el nombre no resuelve a query pública.
    let resp = app
        .oneshot(public_query("menu.item.create", json!({ "name": "Hack" })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn public_command_surface_does_not_exist() {
    let app = app(AppState::with_config(make_runtime().await, dev_config())
        .with_public_snapshot(snapshot_on()));
    let response = app
        .oneshot(
            Request::post("/api/public/command")
                .header("content-type", "application/json")
                .body(Body::from("{}"))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn public_query_returns_429_with_retry_after_after_the_quota() {
    let app = app(AppState::with_config(make_runtime().await, dev_config())
        .with_public_snapshot(snapshot_on()));
    for request_number in 1..=120 {
        let response = app
            .clone()
            .oneshot(public_query_from(
                "menu.items.list",
                json!({}),
                Ipv4Addr::new(10, 0, 0, 1),
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "request {request_number}");
    }
    let other_ip = app
        .clone()
        .oneshot(public_query_from(
            "menu.items.list",
            json!({}),
            Ipv4Addr::new(10, 0, 0, 2),
        ))
        .await
        .unwrap();
    assert_eq!(other_ip.status(), StatusCode::OK, "otra IP conserva su cuota");
    let response = app
        .oneshot(public_query_from(
            "menu.items.list",
            json!({}),
            Ipv4Addr::new(10, 0, 0, 1),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
    assert!(response.headers().contains_key("retry-after"));
}

// ── Flag ON: cableado de /p/<path> ──────────────────────────────────────────────────────────────

#[tokio::test]
async fn flag_on_page_with_stored_json_renders_html_with_strict_csp() {
    let rt = make_runtime().await;
    // Sembramos el JSON de bloques de la página bajo `public.page.<path>` en el settings store
    // existente (misma tabla que el flag y la landing). Escritura de autoría = fase posterior; aquí
    // seed directo para ejercer el RENDER.
    let doc = json!({
        "blocks": [
            { "type": "header", "data": { "text": "Nuestra carta", "level": 1 } },
            { "type": "paragraph", "data": { "text": "Bienvenido al <b>bar</b>" } }
        ]
    });
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB_ID));
    p.insert("key".into(), json!("public.page.menu"));
    p.insert("value".into(), json!(doc.to_string()));
    p.insert("now".into(), json!("2026-01-01T00:00:00Z"));
    p.insert("by".into(), json!("test"));
    rt.db_for_test()
        .execute(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at, updated_by) \
             VALUES (:hub_id, :key, :value, :now, :by)",
            &p,
        )
        .await
        .unwrap();

    let app = app(AppState::with_config(rt, dev_config()).with_public_snapshot(snapshot_on()));

    // Página con JSON → 200 HTML del renderer seguro + CSP estricta pública.
    let resp = app.clone().oneshot(get("/p/menu")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let etag = resp
        .headers()
        .get("etag")
        .and_then(|value| value.to_str().ok())
        .expect("SSR page emits ETag")
        .to_string();
    let csp = resp
        .headers()
        .get("content-security-policy")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    assert_eq!(csp, PUBLIC_CSP, "la página pública lleva la CSP estricta");
    let html = body_text(resp).await;
    assert!(html.contains("<h1>Nuestra carta</h1>"), "salió: {html}");
    assert!(html.contains("<b>bar</b>"), "el inline saneado se conserva: {html}");
    assert!(html.contains("Cafe con leche"), "la read pública se renderiza server-side: {html}");
    assert!(!html.contains("<script"), "nunca JS del usuario");

    let conditional = Request::builder()
        .method("GET")
        .uri("/p/menu")
        .header("host", "public.example")
        .header("if-none-match", etag)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(conditional).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_MODIFIED);

    // Path sin página almacenada → 404 (como hoy).
    let resp = app.oneshot(get("/p/no-existe")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn authenticated_editor_roundtrips_block_json_then_public_page_renders_it() {
    let app = app(
        AppState::with_config(make_runtime().await, dev_config())
            .with_public_snapshot(snapshot_on()),
    );
    let doc = json!({
        "blocks": [{ "type": "paragraph", "data": { "text": "Carta <b>de hoy</b>" } }]
    });
    let response = app
        .clone()
        .oneshot(admin_json("PUT", "/api/public-pages/menu", doc.clone()))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let response = app
        .clone()
        .oneshot(admin_json("GET", "/api/public-pages/menu", json!({})))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(body_json(response).await["data"], doc);

    let response = app.oneshot(get("/p/menu")).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert!(body_text(response).await.contains("Carta <b>de hoy</b>"));
}

#[tokio::test]
async fn authoring_catalog_and_home_are_derived_from_active_manifest() {
    let rt = make_runtime().await;
    rt.set_public_page(
        "menu",
        &json!({ "blocks": [{ "type": "paragraph", "data": { "text": "Hoy" } }] }),
        "test",
    )
    .await
    .unwrap();
    let app = app(AppState::with_config(rt, dev_config()).with_public_snapshot(snapshot_on()));

    let response = app
        .clone()
        .oneshot(admin_json("GET", "/api/public-pages", json!({})))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["data"][0]["path"], json!("menu"));
    assert_eq!(body["data"][0]["title"], json!("Menu"));
    assert_eq!(body["data"][0]["reads"], json!(["menu.items.list"]));
    assert_eq!(body["data"][0]["slot"], json!("public.home.sections"));

    let response = app
        .clone()
        .oneshot(admin_json(
            "PUT",
            "/api/public-pages/inventada",
            json!({ "blocks": [] }),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::NOT_FOUND);

    let response = app.oneshot(get("/")).await.unwrap();
    let html = body_text(response).await;
    assert!(html.contains("href=\"/p/menu\""));
    assert!(html.contains("data-module=\"menu\""));
    assert!(html.contains("Cafe con leche"));
}

#[tokio::test]
async fn configured_origin_binds_host_and_generates_seo() {
    let rt = make_runtime().await;
    rt.set_public_page("menu", &json!({ "blocks": [] }), "test")
        .await
        .unwrap();
    let snapshot = snapshot_on()
        .with_origin(Some("https://menu.example"))
        .unwrap();
    let app = app(AppState::with_config(rt, dev_config()).with_public_snapshot(snapshot));

    let wrong = app.clone().oneshot(get("/p/menu")).await.unwrap();
    assert_eq!(wrong.status(), StatusCode::MISDIRECTED_REQUEST);

    let request = Request::get("/p/menu")
        .header("host", "menu.example")
        .body(Body::empty())
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let html = body_text(response).await;
    assert!(html.contains("rel=\"canonical\" href=\"https://menu.example/p/menu\""));

    let request = Request::get("/sitemap.xml")
        .header("host", "menu.example")
        .body(Body::empty())
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert!(body_text(response).await.contains("https://menu.example/p/menu"));
}
