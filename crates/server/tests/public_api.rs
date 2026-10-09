//! Tests de integración de la **API pública por módulo** (ADR-0057, public-api.md) por HTTP
//! (sin red): gestión de keys, superficie de datos con `Auth::ApiKey` (doble puerta `expose_api`),
//! y el OpenAPI 3.1 dinámico per-hub. Usa `tower::ServiceExt::oneshot` como `tests/http.rs`.
use std::path::PathBuf;
use std::sync::atomic::{AtomicI64, Ordering};
use std::sync::Arc;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::{fresh_db, TestDb};
use erplora_db::{DatabaseAdapter, Params};
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
        demo: false,
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

/// Unix second 59 of a minute (1_800_000_000 is a whole minute): the worst instant for a test
/// that reads the wall clock, the one where the next call already lands in another window.
const LAST_SECOND_OF_A_MINUTE: i64 = 1_800_000_059;

/// Same app, but the API-key quota reads `now` instead of the wall clock (hub#2628): a test that
/// expects two calls to share the minute owns the minute.
async fn make_app_at(now: Arc<AtomicI64>) -> axum::Router {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.set_api_key_clock(Arc::new(move || now.load(Ordering::SeqCst)));
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    app(AppState::with_config(rt, dev_config()))
}

/// A `catalog` read+write key allowed `per_minute` calls; returns its secret.
async fn create_key_with_quota(app: &axum::Router, per_minute: i64) -> String {
    let resp = app
        .clone()
        .oneshot(admin_post(
            "/api/keys",
            json!({
                "name": "Limited",
                "scope": [{ "module": "catalog", "read": true, "write": true }],
                "rate_limit_per_minute": per_minute
            }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    body_json(resp).await["data"]["secret"]
        .as_str()
        .unwrap()
        .to_string()
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
    let resp = app
        .clone()
        .oneshot(admin_post("/api/keys", json!({ "name": "x", "scope": [] })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK); // (segunda key, ignoramos su secreto)
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/keys")
                .header("x-hub-id", HUB_ID)
                .header("x-permissions", "*")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let j = body_json(resp).await;
    assert!(j["data"].as_array().unwrap().len() >= 2);

    // Escribe un item con la key (command expuesto) → 200.
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/c/item.create",
            &secret,
            json!({ "payload": { "name": "Widget" } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "{:?}", body_json(resp).await);

    // Lee con la key (query de lista expuesta) → 200 con el item creado (página paginada).
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &secret,
            json!({ "params": {} }),
        ))
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
    let new_secret = body_json(resp).await["data"]["secret"]
        .as_str()
        .unwrap()
        .to_string();
    // El secreto viejo ya no funciona; el nuevo sí.
    let resp = app
        .clone()
        .oneshot(api_post("/api/v1/catalog/q/items.list", &secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &new_secret,
            json!({}),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    // Revocar = kill-switch inmediato.
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("DELETE")
                .uri(format!("/api/keys/{id}"))
                .header("x-hub-id", HUB_ID)
                .header("x-permissions", "*")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &new_secret,
            json!({}),
        ))
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
        .oneshot(api_post(
            "/api/v1/catalog/q/items.secret",
            &secret,
            json!({}),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    // Command no expuesto → 404.
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/c/item.purge",
            &secret,
            json!({ "payload": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    // Operación inexistente → 404.
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/does.not.exist",
            &secret,
            json!({}),
        ))
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
    let secret = body_json(resp).await["data"]["secret"]
        .as_str()
        .unwrap()
        .to_string();

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
        .oneshot(api_post(
            "/api/v1/catalog/c/item.create",
            &secret,
            json!({ "payload": { "name": "X" } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
}

/// hub#361: an integration is **never** invited to ask a manager. `catalog.write` is granted to
/// `manager` in the fixture, so for a person this refusal would be `requires_elevation` (hub#360)
/// — the offer of a PIN dialog. An API key gets the flat `permission_denied` it always got:
/// nobody is standing at a nightly job to type four digits, and now that an approval GRANTS, a
/// stored, copied, long-lived credential must not have a second way in.
#[tokio::test]
async fn an_api_key_is_never_offered_the_pin_dialog() {
    let app = make_app().await;
    let resp = app
        .clone()
        .oneshot(admin_post(
            "/api/keys",
            json!({ "name": "RO", "scope": [{ "module": "catalog", "read": true, "write": false }] }),
        ))
        .await
        .unwrap();
    let secret = body_json(resp).await["data"]["secret"]
        .as_str()
        .unwrap()
        .to_string();

    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/c/item.create",
            &secret,
            json!({ "payload": { "name": "X" } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let body = body_json(resp).await;
    assert_eq!(body["error"]["code"], json!("permission_denied"));
    assert_eq!(
        body["error"]["permission"],
        json!(null),
        "and no permission field: this is not an offer to elevate"
    );
}

#[tokio::test]
async fn data_surface_rejects_non_api_key_bearer() {
    let app = make_app().await;
    // Un Bearer que no es de API key (no empieza por erpl_live_) → 401 en la superficie de datos.
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            "some-jwt-token",
            json!({}),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// POST to the data surface with no credential at all.
fn anonymous_post(uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .body(Body::from(body.to_string()))
        .unwrap()
}

/// The paths a prober tries: an exposed query and command, operations that exist but are private,
/// operations that do not exist, an exposed query under the wrong module, and a module that is not
/// installed at all. Without a usable key every one of them must look the same.
const PROBED_PATHS: [&str; 8] = [
    "/api/v1/catalog/q/items.list",
    "/api/v1/catalog/c/item.create",
    "/api/v1/catalog/q/items.secret",
    "/api/v1/catalog/c/item.purge",
    "/api/v1/catalog/q/does.not.exist",
    "/api/v1/catalog/c/does.not.exist",
    "/api/v1/other/q/items.list",
    "/api/v1/nope/q/anything",
];

/// hub#2550: the key is checked BEFORE the operation is looked up. Answering `404` for an
/// operation that is not published and `401` for one that is told anybody without a key which
/// operations a hub has installed and open, by trying names. Without a usable key the answer is
/// the same `401` with the same body, whatever is asked for.
#[tokio::test]
async fn without_a_usable_key_every_operation_answers_the_same_401_hub2550() {
    let app = make_app().await;
    let credentials: [(&str, Option<&str>); 3] = [
        ("no credential", None),
        (
            "an invented key",
            Some("erpl_live_deadbeef_notasecretatall"),
        ),
        ("a bearer that is not a key", Some("some-jwt-token")),
    ];
    for (label, token) in credentials {
        let mut bodies = Vec::new();
        for path in PROBED_PATHS {
            let request = match token {
                Some(token) => api_post(path, token, json!({})),
                None => anonymous_post(path, json!({})),
            };
            let resp = app.clone().oneshot(request).await.unwrap();
            assert_eq!(
                resp.status(),
                StatusCode::UNAUTHORIZED,
                "{label} at {path} must be 401, not a hint of whether the operation exists"
            );
            bodies.push((path, body_json(resp).await));
        }
        let (_, first) = &bodies[0];
        for (path, body) in &bodies {
            assert_eq!(
                body, first,
                "{label}: the body at {path} must not differ from the one at an exposed operation"
            );
        }
    }
}

/// hub#2550: with a valid key, asking for an operation that is not published is still `404`, and
/// that answer is paid from the key's quota like any other call — otherwise a key holder could
/// map the private surface of the hub without ever meeting the limit.
#[tokio::test]
async fn an_unpublished_operation_asked_with_a_valid_key_spends_its_quota_hub2550() {
    // The clock is pinned (hub#2628): on the wall clock the second call sometimes landed in the
    // next minute, found a fresh quota and answered 200.
    let app = make_app_at(Arc::new(AtomicI64::new(LAST_SECOND_OF_A_MINUTE))).await;
    // (unpublished operation, published one of the same kind, body of the published one)
    let cases = [
        (
            "/api/v1/catalog/q/does.not.exist",
            "/api/v1/catalog/q/items.list",
            json!({}),
        ),
        (
            "/api/v1/catalog/c/item.purge",
            "/api/v1/catalog/c/item.create",
            json!({ "payload": { "name": "X" } }),
        ),
    ];
    for (unpublished, published, body) in cases {
        let secret = create_key_with_quota(&app, 1).await;

        let resp = app
            .clone()
            .oneshot(api_post(unpublished, &secret, json!({})))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND, "{unpublished}");
        assert_eq!(body_json(resp).await["error"]["code"], json!("not_found"));

        let resp = app
            .clone()
            .oneshot(api_post(published, &secret, body))
            .await
            .unwrap();
        assert_eq!(
            resp.status(),
            StatusCode::TOO_MANY_REQUESTS,
            "the 404 at {unpublished} must have spent the only call of the minute"
        );
        assert_eq!(
            body_json(resp).await["error"]["code"],
            json!("rate_limited")
        );
    }
}

/// hub#2628: a key's quota window is the clock minute the runtime reads. Pinned at the last
/// second of a minute, a one-a-minute key is refused the second call and told to come back in
/// one second; one second later the minute has turned and the same call goes through — which is
/// exactly what the hub#2550 test met on a slow runner when it read the wall clock.
#[tokio::test]
async fn a_key_quota_window_is_the_minute_of_the_runtime_clock_hub2628() {
    let now = Arc::new(AtomicI64::new(LAST_SECOND_OF_A_MINUTE));
    let app = make_app_at(Arc::clone(&now)).await;
    let secret = create_key_with_quota(&app, 1).await;
    let list = "/api/v1/catalog/q/items.list";

    let resp = app
        .clone()
        .oneshot(api_post(list, &secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the only call of the minute");

    let resp = app
        .clone()
        .oneshot(api_post(list, &secret, json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(
        resp.headers()
            .get(axum::http::header::RETRY_AFTER)
            .and_then(|v| v.to_str().ok()),
        Some("1"),
        "at second 59 the window reopens in one second"
    );
    assert_eq!(
        body_json(resp).await["error"]["code"],
        json!("rate_limited")
    );

    now.fetch_add(1, Ordering::SeqCst);
    let resp = app
        .clone()
        .oneshot(api_post(list, &secret, json!({})))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "the minute turned: the key has a new call"
    );
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
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri("/api/settings")
                .header("content-type", "application/json")
                .header("x-hub-id", HUB_ID)
                .header("x-permissions", "*")
                .body(Body::from(json!({ "api_docs_enabled": true }).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn openapi_lists_only_exposed_operations() {
    let app = make_app().await;
    enable_api_docs(&app).await;
    // El spec interno exige sesión de usuario (ADR-0057 §4 refinado): mandamos la sesión del fixture.
    let resp = app
        .clone()
        .oneshot(session_get("/api/v1/openapi.json"))
        .await
        .unwrap();
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
    assert_eq!(
        spec["components"]["securitySchemes"]["ApiKey"]["scheme"],
        json!("bearer")
    );
    // El listSpec de la query se tradujo a params (search/sort/limit) en el requestBody.
    let q_params = &spec["paths"]["/api/v1/catalog/q/items.list"]["post"]["requestBody"]["content"]
        ["application/json"]["schema"]["properties"]["params"]["properties"];
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
    assert_eq!(
        j["api_docs_enabled"],
        json!(false),
        "clave no tocada conserva su default"
    );

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
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri("/api/settings")
                .header("content-type", "application/json")
                .header("x-hub-session", &cashier_token)
                .body(Body::from(json!({ "currency": "GBP" }).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::UNAUTHORIZED,
        "no-admin → 401/403; el gate admin lo mapea a 401"
    );

    // Admin → 200 y persiste.
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri("/api/settings")
                .header("content-type", "application/json")
                .header("x-hub-session", &admin_token)
                .body(Body::from(json!({ "currency": "GBP" }).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["currency"], json!("GBP"));

    // El cajero SÍ puede leer (GET = cualquier sesión de usuario).
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/settings")
                .header("x-hub-session", &cashier_token)
                .body(Body::empty())
                .unwrap(),
        )
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
    let resp = app
        .clone()
        .oneshot(session_get("/api/v1/openapi.json"))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    // Habilita el setting (PUT admin) → ahora el spec se sirve a una sesión válida (200).
    enable_api_docs(&app).await;
    let resp = app
        .clone()
        .oneshot(session_get("/api/v1/openapi.json"))
        .await
        .unwrap();
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
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri(uri)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(
            resp.status(),
            StatusCode::NOT_FOUND,
            "{uri} ya no debe servirse"
        );
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
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/v1/openapi.json")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    // Docs apagadas por defecto → 404 server-side (defensa en profundidad), sin llegar al gate de sesión.
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

// ── hub#1187 · lo que el contrato de esta puerta no fijaba ───────────────────────────────────

/// Regression test for ERPlora/hub#1187 — the `422 unknown_filter` contract of hub#1173 pinned on
/// the PUBLIC door (`POST /api/v1/{module}/q/{name}`), not only on the internal dispatcher.
///
/// The failure hub#1173 closed is the **silent success**: a param the list query does not declare
/// used to be ignored, and the page answered `200 ok` **with the whole list** — indistinguishable
/// from a filter that ran and matched everything. Fixing it in the runtime and asserting it on
/// `/api/query` left the door a third party actually calls untested: `api_keys.rs` reuses
/// `crate::err_response`, so it *should* travel, but "should" is what a regression is made of, and
/// here the caller is an integration we do not control, wiring itself against a list it believes
/// it narrowed.
///
/// Both halves are asserted on purpose: a door that answered `422` to everything would pass the
/// negative on its own. A DECLARED param still opens the door and still narrows the page.
#[tokio::test]
async fn an_undeclared_filter_is_422_on_the_public_door_hub1187() {
    let app = make_app().await;
    let (_id, secret) = create_key(&app).await;

    for name in ["Alpha", "Beta"] {
        let resp = app
            .clone()
            .oneshot(api_post(
                "/api/v1/catalog/c/item.create",
                &secret,
                json!({ "payload": { "name": name } }),
            ))
            .await
            .unwrap();
        assert_eq!(
            resp.status(),
            StatusCode::OK,
            "seeding `{name}` by the public door"
        );
    }

    // Positivo 1 — la puerta ABRE: sin params sale la lista entera.
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &secret,
            json!({ "params": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["data"]["total"], json!(2), "{j}");

    // Positivo 2 — un param DECLARADO (`list.search = ["name"]`) filtra de verdad: salen menos
    // filas. Sin esto, un `422` a todo pasaría el negativo de abajo sin probar nada.
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &secret,
            json!({ "params": { "search": "Alpha" } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(
        j["data"]["total"],
        json!(1),
        "un param declarado filtra: {j}"
    );
    assert_eq!(j["data"]["rows"][0]["name"], json!("Alpha"), "{j}");

    // Negativo 1 — el descuido clásico: la COLUMNA sin el prefijo `f_` del motor. Antes de
    // hub#1173 esto devolvía `200` con las dos filas, como si hubiera filtrado por «Alpha».
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &secret,
            json!({ "params": { "name": "Alpha" } }),
        ))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::UNPROCESSABLE_ENTITY,
        "un param que la lista no declara se rehúsa; nunca 200 con la lista entera"
    );
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(false), "{j}");
    assert_eq!(j["error"]["code"], json!("unknown_filter"), "{j}");
    assert!(j["data"].is_null(), "una refusal no trae página: {j}");

    // Negativo 2 — el param inventado, y el mensaje lo NOMBRA: es lo único con lo que un tercero
    // encuentra su propia errata desde fuera (mismo contrato que en `/api/query`, hub#1241).
    let resp = app
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &secret,
            json!({ "params": { "active_only": true } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
    let j = body_json(resp).await;
    assert_eq!(j["error"]["code"], json!("unknown_filter"), "{j}");
    assert!(
        j["error"]["message"]
            .as_str()
            .unwrap_or_default()
            .contains("active_only"),
        "el param rechazado se nombra o el tercero no puede arreglar la llamada: {j}"
    );
}

/// Two deployments, two `hub_id`s, **one schema**: the worst case the row contract of ADR-0201 has
/// to hold in. Each hub seeds its own row through the door that injects `hub_id` (its own API key
/// on `POST /api/v1/catalog/c/item.create`) — never a seeding helper, which would prove nothing
/// about the door under test.
async fn public_api_app_for(db: &TestDb, hub_id: &str) -> axum::Router {
    let adapter = db.adapter().await;
    let mut rt = Runtime::with_hub_id(Box::new(adapter), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    let mut cfg = dev_config();
    cfg.hub_id = hub_id.to_string();
    app(AppState::with_config(rt, cfg))
}

/// POST admin contra la puerta de gestión de un hub concreto (el `x-hub-id` que inyecta su
/// despliegue).
fn admin_post_as_hub(hub_id: &str, uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .header("x-hub-id", hub_id)
        .header("x-user-id", "admin-1")
        .header("x-permissions", "*")
        .body(Body::from(body.to_string()))
        .unwrap()
}

/// Regression test for ERPlora/hub#1187 — tenancy on the PUBLIC door.
///
/// `tests/multitenant.rs` proves a hub only touches its own pool, but it proves it on `/api/query`
/// and with a database per org, so the row-level `hub_id` scoping is never the thing under test.
/// Here both hubs share ONE schema on purpose: if the scoping holds when the tables are literally
/// the same, it holds a fortiori with a database per hub (ADR-0201). Everything goes through the
/// enforcing door — seeding included — because a helper that writes the rows itself proves nothing
/// about the door.
#[tokio::test]
async fn a_key_of_one_hub_never_reads_rows_of_another_hub1187() {
    const HUB_A: &str = "hub-pub-a";
    const HUB_B: &str = "hub-pub-b";

    let db = TestDb::new().await;
    let app_a = public_api_app_for(&db, HUB_A).await;
    let app_b = public_api_app_for(&db, HUB_B).await;

    // Una key por hub, cada una por la puerta de gestión de SU despliegue.
    let mut secrets = Vec::new();
    for (app, hub_id, item) in [(&app_a, HUB_A, "Only in A"), (&app_b, HUB_B, "Only in B")] {
        let resp = app
            .clone()
            .oneshot(admin_post_as_hub(
                hub_id,
                "/api/keys",
                json!({ "name": hub_id, "scope": [{ "module": "catalog", "read": true, "write": true }] }),
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let secret = body_json(resp).await["data"]["secret"]
            .as_str()
            .unwrap()
            .to_string();
        // Y su fila, escrita por la puerta pública: el `hub_id` lo pone el despliegue, no el body.
        let resp = app
            .clone()
            .oneshot(api_post(
                "/api/v1/catalog/c/item.create",
                &secret,
                json!({ "payload": { "name": item } }),
            ))
            .await
            .unwrap();
        assert_eq!(
            resp.status(),
            StatusCode::OK,
            "{hub_id} siembra su fila por su puerta"
        );
        secrets.push(secret);
    }
    let (secret_a, secret_b) = (secrets[0].clone(), secrets[1].clone());

    // CONTROL DEL POSITIVO: las dos filas están de verdad en la MISMA tabla. Sin esto, un
    // aislamiento «verde» podría serlo porque la fila del vecino nunca llegó a existir.
    let probe = db.adapter().await;
    let rows = probe
        .query(
            "SELECT hub_id, name FROM catalog_items ORDER BY name",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows;
    assert_eq!(rows.len(), 2, "las dos filas comparten tabla: {rows:?}");
    assert_eq!(rows[0]["hub_id"], json!(HUB_A), "{rows:?}");
    assert_eq!(rows[1]["hub_id"], json!(HUB_B), "{rows:?}");

    // La key de A solo ve lo de A…
    let resp = app_a
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &secret_a,
            json!({ "params": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(
        j["data"]["total"],
        json!(1),
        "la key de A no cuenta las filas de B: {j}"
    );
    assert_eq!(j["data"]["rows"][0]["name"], json!("Only in A"), "{j}");

    // …y la de B, solo lo de B (el aislamiento va en los dos sentidos, no solo hacia el que probé).
    let resp = app_b
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &secret_b,
            json!({ "params": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(
        j["data"]["total"],
        json!(1),
        "la key de B no cuenta las filas de A: {j}"
    );
    assert_eq!(j["data"]["rows"][0]["name"], json!("Only in B"), "{j}");

    // Y la key de A presentada en el despliegue de B ni siquiera autentica: la búsqueda de la key
    // filtra por `hub_id`, así que un secreto robado de otro hub no abre esta puerta.
    let resp = app_b
        .clone()
        .oneshot(api_post(
            "/api/v1/catalog/q/items.list",
            &secret_a,
            json!({ "params": {} }),
        ))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::UNAUTHORIZED,
        "la key de A no es una key de B: {:?}",
        body_json(resp).await
    );
}
