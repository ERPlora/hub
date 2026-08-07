//! Tests de integración de la **API pública por módulo** (ADR-0057, public-api.md) por HTTP
//! (sin red): gestión de keys, superficie de datos con `Auth::ApiKey` (doble puerta `expose_api`),
//! y el OpenAPI 3.1 dinámico per-hub. Usa `tower::ServiceExt::oneshot` como `tests/http.rs`.
use std::path::PathBuf;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB_ID: &str = "hub-pub-1";

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_public_api")
}

fn dev_config() -> HubConfig {
    HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache: std::env::temp_dir().join("erplora-pubapi-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        // El fixture valida la API pública, no el alta inicial de la máquina.
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-pubapi-media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: None,
    }
}

/// App con el módulo `catalog` instalado + tablas de sistema (incluida `hub_api_key`).
async fn make_app() -> axum::Router {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    app(AppState::with_config(rt, dev_config()))
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// POST admin (Dev mode confía en cabeceras; el gate admin pasa en Dev).
fn admin_post(uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .header("x-hub-id", HUB_ID)
        .header("x-user-id", "admin-1")
        .header("x-permissions", "*")
        .body(Body::from(body.to_string()))
        .unwrap()
}

/// POST a la superficie de datos con un Bearer de API key.
fn api_post(uri: &str, token: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .header("authorization", format!("Bearer {token}"))
        .body(Body::from(body.to_string()))
        .unwrap()
}

/// Crea una key con scope `read`+`write` sobre `catalog` y devuelve `(id, secret)`.
async fn create_key(app: &axum::Router) -> (String, String) {
    let resp = app
        .clone()
        .oneshot(admin_post(
            "/api/keys",
            json!({ "name": "Test", "scope": [{ "module": "catalog", "read": true, "write": true }] }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(true));
    let data = &j["data"];
    let secret = data["secret"].as_str().unwrap().to_string();
    assert!(secret.starts_with("erpl_live_"), "secret = {secret}");
    (data["id"].as_str().unwrap().to_string(), secret)
}

#[tokio::test]
async fn full_lifecycle_create_use_rotate_revoke() {
    let app = make_app().await;
    let (id, secret) = create_key(&app).await;

    // El listado muestra la key (sin secreto), con last_used_at vacío hasta el primer uso.
    let resp = app.clone().oneshot(admin_post("/api/keys", json!({ "name": "x", "scope": [] }))).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK); // (segunda key, ignoramos su secreto)
    let resp = app
        .clone()
        .oneshot(Request::builder().method("GET").uri("/api/keys")
            .header("x-hub-id", HUB_ID).header("x-permissions", "*").body(Body::empty()).unwrap())
        .await
        .unwrap();
    let j = body_json(resp).await;
    assert!(j["data"].as_array().unwrap().len() >= 2);

    // Escribe un item con la key (command expuesto) → 200.
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/c/item.create", &secret, json!({ "payload": { "name": "Widget" } })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "{:?}", body_json(resp).await);

    // Lee con la key (query de lista expuesta) → 200 con el item creado (página paginada).
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/q/items.list", &secret, json!({ "params": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(true));
    assert_eq!(j["data"]["total"], json!(1));
    assert_eq!(j["data"]["rows"][0]["name"], json!("Widget"));

    // Rotar invalida el secreto anterior.
    let resp = app
        .clone()
        .oneshot(admin_post(&format!("/api/keys/{id}/rotate"), json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let new_secret = body_json(resp).await["data"]["secret"].as_str().unwrap().to_string();
    // El secreto viejo ya no funciona; el nuevo sí.
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/q/items.list", &secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/q/items.list", &new_secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    // Revocar = kill-switch inmediato.
    let resp = app
        .clone()
        .oneshot(Request::builder().method("DELETE").uri(format!("/api/keys/{id}"))
            .header("x-hub-id", HUB_ID).header("x-permissions", "*").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/q/items.list", &new_secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn double_gate_blocks_unexposed_and_unknown() {
    let app = make_app().await;
    let (_id, secret) = create_key(&app).await;

    // Operación NO expuesta (expose_api ausente) → 404 aunque exista y la key tenga scope.
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/q/items.secret", &secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    // Command no expuesto → 404.
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/c/item.purge", &secret, json!({ "payload": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    // Operación inexistente → 404.
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/q/does.not.exist", &secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    // Namespace cruzado: pedir una query de catalog bajo otro módulo en la ruta → 404.
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/other/q/items.list", &secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn read_only_key_cannot_write() {
    let app = make_app().await;
    // Key con solo lectura sobre catalog.
    let resp = app
        .clone()
        .oneshot(admin_post(
            "/api/keys",
            json!({ "name": "RO", "scope": [{ "module": "catalog", "read": true, "write": false }] }),
        ))
        .await
        .unwrap();
    let secret = body_json(resp).await["data"]["secret"].as_str().unwrap().to_string();

    // Leer va bien.
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/q/items.list", &secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    // Escribir con una key de solo-lectura → 403 (la key no tiene `catalog.write` en su scope).
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/c/item.create", &secret, json!({ "payload": { "name": "X" } })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn data_surface_rejects_non_api_key_bearer() {
    let app = make_app().await;
    // Un Bearer que no es de API key (no empieza por erpl_live_) → 401 en la superficie de datos.
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/q/items.list", "some-jwt-token", json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// GET con cabeceras de **sesión de usuario** (en `AuthMode::Dev` del fixture, la identidad la
/// llevan las cabeceras `x-hub-id`/`x-user-id`/`x-permissions`, igual que el resto de endpoints
/// gateados por sesión). Es la forma del fixture de "montar una sesión" sin Cloud.
fn session_get(uri: &str) -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri(uri)
        .header("x-hub-id", HUB_ID)
        .header("x-user-id", "user-1")
        .header("x-permissions", "*")
        .body(Body::empty())
        .unwrap()
}

/// Habilita el setting `api_docs_enabled` (PUT admin). El OpenAPI interno está deshabilitado por
/// defecto (404 server-side); los tests que ejercitan el gate de sesión deben encenderlo primero.
async fn enable_api_docs(app: &axum::Router) {
    let resp = app
        .clone()
        .oneshot(Request::builder()
            .method("PUT")
            .uri("/api/settings")
            .header("content-type", "application/json")
            .header("x-hub-id", HUB_ID)
            .header("x-permissions", "*")
            .body(Body::from(json!({ "api_docs_enabled": true }).to_string()))
            .unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn openapi_lists_only_exposed_operations() {
    let app = make_app().await;
    enable_api_docs(&app).await;
    // El spec interno exige sesión de usuario (ADR-0057 §4 refinado): mandamos la sesión del fixture.
    let resp = app.clone().oneshot(session_get("/api/v1/openapi.json")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let spec = body_json(resp).await;
    assert_eq!(spec["openapi"], json!("3.1.0"));
    let paths = spec["paths"].as_object().unwrap();
    // Las dos operaciones expuestas aparecen…
    assert!(paths.contains_key("/api/v1/catalog/q/items.list"));
    assert!(paths.contains_key("/api/v1/catalog/c/item.create"));
    // …y las privadas NO.
    assert!(!paths.contains_key("/api/v1/catalog/q/items.secret"));
    assert!(!paths.contains_key("/api/v1/catalog/c/item.purge"));
    // El securityScheme es http bearer.
    assert_eq!(spec["components"]["securitySchemes"]["ApiKey"]["scheme"], json!("bearer"));
    // El listSpec de la query se tradujo a params (search/sort/limit) en el requestBody.
    let q_params = &spec["paths"]["/api/v1/catalog/q/items.list"]["post"]["requestBody"]
        ["content"]["application/json"]["schema"]["properties"]["params"]["properties"];
    assert!(q_params.get("search").is_some());
    assert!(q_params.get("sort").is_some());
    assert!(q_params.get("limit").is_some());
}

#[tokio::test]
async fn api_key_cannot_bypass_public_gate_through_internal_dispatcher() {
    let app = make_app().await;
    let (_id, secret) = create_key(&app).await;
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/command",
            &secret,
            json!({ "name": "catalog.item.create", "payload": { "name": "Bypass" } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

// ── Settings del hub (tabla `hub_settings`, GET/PUT /api/settings) ───────────────────────────────

/// GET parcial sobre la superficie de settings. En `AuthMode::Dev` la sesión la llevan las cabeceras.
fn settings_get() -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri("/api/settings")
        .header("x-hub-id", HUB_ID)
        .header("x-user-id", "user-1")
        .header("x-permissions", "*")
        .body(Body::empty())
        .unwrap()
}

/// PUT admin a /api/settings (Dev mode: el gate admin pasa por cabeceras).
fn settings_put(body: Value) -> Request<Body> {
    Request::builder()
        .method("PUT")
        .uri("/api/settings")
        .header("content-type", "application/json")
        .header("x-hub-id", HUB_ID)
        .header("x-permissions", "*")
        .body(Body::from(body.to_string()))
        .unwrap()
}

#[tokio::test]
async fn settings_get_returns_defaults() {
    let app = make_app().await;
    let resp = app.clone().oneshot(settings_get()).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    // Objeto plano (contrato del frontend), con el conjunto completo de claves conocidas.
    assert_eq!(j["currency"], json!("EUR"));
    assert_eq!(j["language"], json!("es"));
    assert_eq!(j["api_docs_enabled"], json!(false));
}

#[tokio::test]
async fn settings_put_admin_persists_and_returns_full_object() {
    let app = make_app().await;
    // PUT parcial: cambia moneda+idioma (la moneda en minúsculas se normaliza a mayúsculas).
    let resp = app
        .clone()
        .oneshot(settings_put(json!({ "currency": "usd", "language": "en" })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["currency"], json!("USD"));
    assert_eq!(j["language"], json!("en"));
    assert_eq!(j["api_docs_enabled"], json!(false), "clave no tocada conserva su default");

    // Persistido: un GET posterior lo refleja.
    let resp = app.clone().oneshot(settings_get()).await.unwrap();
    let j = body_json(resp).await;
    assert_eq!(j["currency"], json!("USD"));
    assert_eq!(j["language"], json!("en"));
}

#[tokio::test]
async fn settings_put_rejects_invalid_currency_and_language() {
    let app = make_app().await;
    // Moneda inválida → 422 (InvalidPayload).
    let resp = app
        .clone()
        .oneshot(settings_put(json!({ "currency": "EUROS" })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);

    // Idioma no soportado → 422.
    let resp = app
        .clone()
        .oneshot(settings_put(json!({ "language": "fr" })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);

    // Clave desconocida → 422.
    let resp = app
        .clone()
        .oneshot(settings_put(json!({ "not_a_setting": "x" })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);

    // Nada se persistió (sigue en defaults).
    let resp = app.clone().oneshot(settings_get()).await.unwrap();
    let j = body_json(resp).await;
    assert_eq!(j["currency"], json!("EUR"));
    assert_eq!(j["language"], json!("es"));
}

/// PUT por un usuario **no admin** → 403. Requiere `AuthMode::Session` (en Dev el gate admin siempre
/// pasa). Se montan dos sesiones reales (admin + cajero) antes de construir la app y se prueban ambas.
#[tokio::test]
async fn settings_put_non_admin_is_403_in_session_mode() {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    // Crea un cajero (rol no admin) + un admin y abre sesiones server-side reales.
    let cashier_id = rt.create_user("Caja", "", "cashier", None).await.unwrap();
    let admin_id = rt.create_user("Jefa", "", "admin", None).await.unwrap();
    let cashier_token = rt.create_session(&cashier_id, 3600, None).await.unwrap();
    let admin_token = rt.create_session(&admin_id, 3600, None).await.unwrap();

    let mut cfg = dev_config();
    cfg.auth_mode = AuthMode::Session;
    let app = app(AppState::with_config(rt, cfg));

    // Cajero (no admin) → 403.
    let resp = app
        .clone()
        .oneshot(Request::builder()
            .method("PUT")
            .uri("/api/settings")
            .header("content-type", "application/json")
            .header("x-hub-session", &cashier_token)
            .body(Body::from(json!({ "currency": "GBP" }).to_string()))
            .unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "no-admin → 401/403; el gate admin lo mapea a 401");

    // Admin → 200 y persiste.
    let resp = app
        .clone()
        .oneshot(Request::builder()
            .method("PUT")
            .uri("/api/settings")
            .header("content-type", "application/json")
            .header("x-hub-session", &admin_token)
            .body(Body::from(json!({ "currency": "GBP" }).to_string()))
            .unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["currency"], json!("GBP"));

    // El cajero SÍ puede leer (GET = cualquier sesión de usuario).
    let resp = app
        .clone()
        .oneshot(Request::builder()
            .method("GET")
            .uri("/api/settings")
            .header("x-hub-session", &cashier_token)
            .body(Body::empty())
            .unwrap())
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["currency"], json!("GBP"));
}

/// El toggle de docs API es server-side: `openapi.json` da **404** cuando `api_docs_enabled=false`
/// (su default) y **200** (con sesión) cuando se enciende. Defensa en profundidad sobre el gate de
/// sesión.
#[tokio::test]
async fn openapi_404_when_docs_disabled_then_200_when_enabled() {
    let app = make_app().await;

    // Por defecto (api_docs_enabled=false): 404 incluso con una sesión válida.
    let resp = app.clone().oneshot(session_get("/api/v1/openapi.json")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    // Habilita el setting (PUT admin) → ahora el spec se sirve a una sesión válida (200).
    enable_api_docs(&app).await;
    let resp = app.clone().oneshot(session_get("/api/v1/openapi.json")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["openapi"], json!("3.1.0"));
}

/// El server YA NO sirve Swagger UI (ADR-0057 §4 refinado 2026-06-24): `/api/docs` y sus activos
/// se eliminaron (la doc la renderiza una vista Vue interna del Hub). La ruta debe devolver 404.
#[tokio::test]
async fn docs_html_route_is_gone() {
    let app = make_app().await;
    for uri in [
        "/api/docs",
        "/api/docs/swagger-ui.css",
        "/api/docs/swagger-ui-bundle.js",
        "/api/docs/swagger-initializer.js",
    ] {
        let resp = app
            .clone()
            .oneshot(Request::builder().method("GET").uri(uri).body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND, "{uri} ya no debe servirse");
    }
}

/// El spec interno **rechaza el principal API-key** (ADR-0057 §4 refinado): un holder de key NO saca
/// el spec interno completo por aquí (ese es el caso "integraciones" futuro, fuera de alcance). El
/// rechazo es explícito y ocurre en cualquier `auth_mode`, así que se prueba en el fixture Dev.
#[tokio::test]
async fn openapi_rejects_api_key_principal() {
    let app = make_app().await;
    enable_api_docs(&app).await; // habilitado, para ejercitar el gate de sesión (no el de docs)
    let (_id, secret) = create_key(&app).await;
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/v1/openapi.json")
                .header("authorization", format!("Bearer {secret}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// En `AuthMode::Session`, una petición **anónima** (sin `X-Hub-Session`) al spec interno no obtiene
/// nada. Con el setting `api_docs_enabled` en su default (`false`), el gate de docs server-side
/// responde **404** (la ruta "no existe") ANTES del gate de sesión. Sin login y con docs apagadas =
/// nada (ADR-0057 §4 refinado + setting `api_docs_enabled`).
#[tokio::test]
async fn openapi_anonymous_in_session_mode_with_docs_off_is_404() {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    let mut cfg = dev_config();
    cfg.auth_mode = AuthMode::Session;
    let app = app(AppState::with_config(rt, cfg));

    let resp = app
        .clone()
        .oneshot(Request::builder().method("GET").uri("/api/v1/openapi.json").body(Body::empty()).unwrap())
        .await
        .unwrap();
    // Docs apagadas por defecto → 404 server-side (defensa en profundidad), sin llegar al gate de sesión.
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}
