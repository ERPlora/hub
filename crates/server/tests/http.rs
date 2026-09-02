//! Tests de integración del server por HTTP (sin red): `tower::ServiceExt::oneshot`.
use std::path::PathBuf;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, with_static_frontend, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

fn fixture() -> PathBuf {
    // Reusa el fixture del runtime (módulo inventory completo).
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_inventory")
}

async fn make_app() -> axum::Router {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.unwrap();
    app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ))
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

#[tokio::test]
async fn healthz_ok() {
    let resp = make_app()
        .await
        .oneshot(
            Request::builder()
                .uri("/healthz")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn static_frontend_serves_index_and_keeps_api() {
    // dir temporal con un index.html (simula el dist/ de Vite).
    let dir = std::env::temp_dir().join(format!("erplora_static_{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("index.html"),
        "<!doctype html><title>erplora</title>",
    )
    .unwrap();

    let router = with_static_frontend(make_app().await, dir.to_str().unwrap());

    // Una ruta sin fichero/ni API → fallback SPA al index.html.
    let resp = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/dashboard")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    assert!(String::from_utf8_lossy(&bytes).contains("erplora"));

    // /healthz sigue siendo ruta de API (no la pisa el estático).
    let resp = router
        .oneshot(
            Request::builder()
                .uri("/healthz")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    assert_eq!(&bytes[..], b"ok");

    std::fs::remove_dir_all(&dir).ok();
}

/// hub#504: this test used to assert that `/api/events` answered `200 text/event-stream` **with no
/// credential at all** — it consecrated the hole instead of catching it. What it pins now is the
/// refusal; that the stream still streams for a key that may read is asserted in
/// `tests/event_stream_ws.rs`, next to the WebSocket half of the same door.
///
/// Note the app here runs in `AuthMode::Dev`: the event channel asks for an API key regardless of
/// the auth mode, exactly like the rest of the public API surface (ADR-0057).
#[tokio::test]
async fn sse_events_refuses_a_request_without_a_credential() {
    let resp = make_app()
        .await
        .oneshot(
            Request::builder()
                .uri("/api/events")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    let body = body_json(resp).await;
    assert_eq!(body["error"]["code"], "unauthenticated");
}

#[tokio::test]
async fn navigation_lists_module_menu() {
    let resp = make_app()
        .await
        .oneshot(
            Request::builder()
                .uri("/api/navigation")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["ok"], json!(true));
    assert_eq!(j["data"][0]["component"], json!("erp-inventory-products"));
}

#[tokio::test]
async fn command_then_query_roundtrip() {
    let app = make_app().await;

    let create = app
        .clone()
        .oneshot(post(
            "/api/command",
            json!({ "name": "inventory.products.create",
                    "payload": { "name": "Café", "sku": "CAF", "price": 4.5, "stock": 10 } }),
        ))
        .await
        .unwrap();
    assert_eq!(create.status(), StatusCode::OK);
    assert_eq!(body_json(create).await["ok"], json!(true));

    let list = app
        .oneshot(post(
            "/api/query",
            json!({ "name": "inventory.products.list" }),
        ))
        .await
        .unwrap();
    assert_eq!(list.status(), StatusCode::OK);
    let j = body_json(list).await;
    assert_eq!(j["data"].as_array().unwrap().len(), 1);
    assert_eq!(j["data"][0]["name"], json!("Café"));
}

#[tokio::test]
async fn permission_denied_is_403() {
    let req = Request::builder()
        .method("POST")
        .uri("/api/command")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u2")
        .header("x-permissions", "inventory.products.read") // sin create
        .body(Body::from(
            json!({ "name": "inventory.products.create",
                    "payload": { "name": "X", "sku": "X", "price": 1, "stock": 1 } })
            .to_string(),
        ))
        .unwrap();
    let resp = make_app().await.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(resp).await["error"]["code"],
        json!("permission_denied")
    );
}

/// hub#360 (paso 2b, rule 1): a refusal a MANAGER could approve crosses the HTTP border as its
/// own stable code, carrying the missing permission as a **field** — the dialog of hub#363 has to
/// name what it asks approval for, and must not parse it out of a sentence. Still a `403`: it is
/// a refusal, not a permit.
#[tokio::test]
async fn requires_elevation_is_403_naming_the_missing_permission() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(
        &PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_elevation"),
    )
    .await
    .unwrap();
    let app = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ));

    let req = Request::builder()
        .method("POST")
        .uri("/api/command")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u2")
        .header("x-permissions", "till.view_sale,till.add_sale") // a cashier
        .body(Body::from(
            json!({ "name": "till.sale.take_payment", "payload": { "label": "table 4" } })
                .to_string(),
        ))
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let body = body_json(resp).await;
    assert_eq!(body["error"]["code"], json!("requires_elevation"));
    assert_eq!(body["error"]["permission"], json!("till.take_payment"));
}

// ── hub#361 helpers: a till, a manager who can approve and a cashier who cannot ──────────────

/// The `till` fixture plus two real `hub_user` rows with PINs, in `Dev` auth mode (the cashier's
/// identity comes from the headers, exactly as in the hub#360 tests above).
async fn elevation_app() -> AppState {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(
        &PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_elevation"),
    )
    .await
    .unwrap();
    rt.create_user("Sofía", "8317", "manager", None)
        .await
        .unwrap();
    rt.create_user("Nacho", "4692", "employee", None)
        .await
        .unwrap();
    AppState::with_config(rt, HubConfig::from_env_with_auth(AuthMode::Dev))
}

/// `POST /api/command` as the cashier, optionally presenting an approval.
fn take_payment_request(token: Option<&str>) -> Request<Body> {
    let mut req = Request::builder()
        .method("POST")
        .uri("/api/command")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u-cashier")
        .header("x-permissions", "till.view_sale,till.add_sale");
    if let Some(token) = token {
        req = req.header("x-elevation-token", token);
    }
    req.body(Body::from(
        json!({ "name": "till.sale.take_payment", "payload": { "label": "table 4" } }).to_string(),
    ))
    .unwrap()
}

/// `POST /api/elevation/approve` — the cashier's request, the approver's digits.
fn approve_request(approver: &str, pin: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/elevation/approve")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u-cashier")
        .header("x-permissions", "till.view_sale,till.add_sale")
        .body(Body::from(
            json!({
                "approver": approver,
                "pin": pin,
                "command": "till.sale.take_payment",
                "payload": { "label": "table 4" }
            })
            .to_string(),
        ))
        .unwrap()
}

/// hub#361 (paso 2b, rules 2 and 4): the manager's PIN crosses the border **once**, to
/// `POST /api/elevation/approve`, and what comes back is a token the cashier presents on the
/// retry in `X-Elevation-Token` — a header, deliberately **not** a payload field, so the body of a
/// command stays pure data and nothing about authority can be smuggled through it.
#[tokio::test]
async fn the_managers_approval_crosses_the_border_and_the_retry_goes_through() {
    let app = app(elevation_app().await);

    // Without approval: the 403 of hub#360.
    let resp = app
        .clone()
        .oneshot(take_payment_request(None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);

    let resp = app
        .clone()
        .oneshot(approve_request("Sofía", "8317"))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
    assert_eq!(body["data"]["permission"], json!("till.take_payment"));
    assert_eq!(body["data"]["approver_name"], json!("Sofía"));
    assert_eq!(body["data"]["expires_in_seconds"], json!(120));
    let token = body["data"]["token"].as_str().unwrap().to_string();
    assert!(!token.is_empty());

    let resp = app
        .clone()
        .oneshot(take_payment_request(Some(&token)))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the approved action runs");

    // Spent. The same token, the same action, one request later: back to asking the manager.
    let resp = app
        .oneshot(take_payment_request(Some(&token)))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(resp).await["error"]["code"],
        json!("requires_elevation")
    );
}

/// A PIN is four digits typed in front of customers: without a limit on the attempts, approval is
/// decorative. The approval door shares the pinpad's guard (`LoginThrottle`), so a script cannot
/// walk 10,000 combinations here either — and a lock earned at one door holds at the other,
/// because it is the same credential.
#[tokio::test]
async fn wrong_pins_are_refused_and_then_locked_out() {
    let app = app(elevation_app().await);

    for attempt in 1..=erplora_server::login_throttle::MAX_FAILURES {
        let resp = app
            .clone()
            .oneshot(approve_request("Sofía", "0000"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::CONFLICT, "attempt {attempt}");
        assert_eq!(
            body_json(resp).await["error"]["code"],
            json!("hub.elevation.rejected")
        );
    }

    // Locked — and now even the RIGHT PIN waits, or the lock would be a suggestion.
    let resp = app
        .clone()
        .oneshot(approve_request("Sofía", "8317"))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(
        body_json(resp).await["error"]["code"],
        json!("too_many_attempts")
    );
}

/// A refusal that is **not** about the digits must not spend an attempt: picking the wrong person
/// in the dialog is a mistake anybody makes, and locking their account for it would teach the shop
/// to stop using the dialog.
#[tokio::test]
async fn a_refusal_that_is_not_about_the_pin_does_not_count_towards_the_lock() {
    let app = app(elevation_app().await);

    for _ in 0..(erplora_server::login_throttle::MAX_FAILURES + 3) {
        let resp = app
            .clone()
            .oneshot(approve_request("Nacho", "4692"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::CONFLICT);
        assert_eq!(
            body_json(resp).await["error"]["code"],
            json!("hub.elevation.approver_cannot")
        );
    }

    // Nacho's PIN was right every time, so nothing is locked: he simply cannot approve this.
    let resp = app.oneshot(approve_request("Sofía", "8317")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}

/// The other half of the same contract: an `admin` permission never advertises a PIN dialog
/// (rule 5). `fixture_inventory` grants nothing to `manager`, so the shape the 24 published
/// modules have keeps answering exactly what it answered before — see `permission_denied_is_403`.
#[tokio::test]
async fn a_flat_denial_carries_no_permission_field() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(
        &PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_elevation"),
    )
    .await
    .unwrap();
    let app = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ));

    let req = Request::builder()
        .method("POST")
        .uri("/api/command")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u2")
        .header("x-permissions", "till.view_sale,till.add_sale")
        .body(Body::from(
            json!({ "name": "till.settings.save", "payload": { "label": "x" } }).to_string(),
        ))
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let body = body_json(resp).await;
    assert_eq!(body["error"]["code"], json!("permission_denied"));
    assert_eq!(
        body["error"]["permission"],
        json!(null),
        "a flat refusal must not look like an offer to elevate"
    );
}

#[tokio::test]
async fn unknown_query_is_404() {
    let resp = make_app()
        .await
        .oneshot(post("/api/query", json!({ "name": "nope.q" })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn get_api_query_route_does_not_exist_405_never_404_never_spa() {
    // hub#332: a production hub's console showed `GET /api/query → 404` on every panel load.
    // The query endpoint is POST-only by contract and the GET has NO legitimate caller — none
    // exists in the shell, the module SDK, any module bundle, or their full git histories.
    // This pins the router shape on both sides:
    //   - a stray GET answers 405 (method not allowed), NOT 404 (which would suggest the
    //     endpoint itself is missing) — and nobody may "fix" the console noise by registering
    //     a GET handler (that would mask the symptom instead of removing the caller);
    //   - the SPA static fallback never swallows it into a 200 index.html either.
    let get = |uri: &str| {
        Request::builder()
            .method("GET")
            .uri(uri)
            .body(Body::empty())
            .unwrap()
    };

    // Bare API router.
    let resp = make_app().await.oneshot(get("/api/query")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::METHOD_NOT_ALLOWED);

    // Wrapped with the static frontend (what production serves): same answer, no SPA fallback.
    let dir = std::env::temp_dir().join(format!("erplora_static_332_{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("index.html"), "<!doctype html><title>x</title>").unwrap();
    let router = with_static_frontend(make_app().await, dir.to_str().unwrap());
    let resp = router.oneshot(get("/api/query")).await.unwrap();
    assert_eq!(resp.status(), StatusCode::METHOD_NOT_ALLOWED);
    std::fs::remove_dir_all(&dir).ok();
}

#[tokio::test]
async fn hub_context_returns_configured_hub_id() {
    use erplora_server::HubConfig;
    let db = fresh_db().await;
    let rt = Runtime::new(Box::new(db));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-xyz".into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache: std::env::temp_dir().join("erplora-test-cache"),
        auth_mode: erplora_server::AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: None,
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-test-media"),
        sector: Some("hosteleria".into()),
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let app = app(AppState::with_config(rt, cfg));
    let resp = app
        .oneshot(
            Request::builder()
                .uri("/api/hub/context")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["hub_id"], json!("hub-xyz"));
    assert_eq!(j["user"], Value::Null);
    assert_eq!(j["demo"], json!(false));
    assert_eq!(j["machine_registered"], json!(false));
    assert_eq!(j["registration_required"], json!(true));
    assert_eq!(j["public_key_loaded"], json!(false));
    // El sector se expone como `business_type` + alias `sector` (ADR-0054, contrato del frontend).
    assert_eq!(j["business_type"], json!("hosteleria"));
    assert_eq!(j["sector"], json!("hosteleria"));
    // hub#731: la zona horaria del negocio, ya RESUELTA (la declarada, o la deducida del país).
    // `/api/settings` devuelve la clave cruda —`null` mientras se deduzca—, así que sin esto la
    // UI no tiene forma de decir a qué hora local va a dispararse un flujo, que es justo lo que
    // el issue pide enseñar al lado del campo.
    assert_eq!(j["timezone"], json!("Europe/Madrid"));
}

#[tokio::test]
async fn hub_context_adopts_machine_identity_without_restart() {
    use std::sync::{Arc, RwLock};

    use erplora_server::{AuthMode, HubConfig, HubId, MachineToken};

    let db = fresh_db().await;
    let rt = Runtime::new(Box::new(db));
    let cfg = HubConfig {
        demo: false,
        hub_id: erplora_server::DEV_HUB_ID.into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache: std::env::temp_dir().join("erplora-live-identity-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: Some("public-key-loaded".into()),
        cloud_api_token: None,
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-live-identity-media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let token: MachineToken = Arc::new(RwLock::new(None));
    let hub_id: HubId = Arc::new(RwLock::new(erplora_server::DEV_HUB_ID.into()));
    let state = AppState::with_config_cells(rt, cfg, token.clone(), hub_id.clone());

    *token.write().unwrap() = Some("machine-secret".into());
    *hub_id.write().unwrap() = "real-hub-id".into();

    let resp = app(state.clone())
        .oneshot(
            Request::builder()
                .uri("/api/hub/context")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j = body_json(resp).await;
    assert_eq!(j["hub_id"], json!("real-hub-id"));
    assert_eq!(j["machine_registered"], json!(true));
    assert_eq!(j["registration_required"], json!(false));
    assert_eq!(j["public_key_loaded"], json!(true));
    assert_eq!(state.runtime.read().await.hub_id(), "real-hub-id");
}

#[tokio::test]
async fn demo_catalog_uses_public_saas_metadata_without_hub_credentials() {
    use axum::http::HeaderMap;
    use axum::routing::get;
    use axum::{Json, Router};
    use erplora_server::{AuthMode, HubConfig, DEV_HUB_ID};

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let mock_cloud = Router::new().route(
        "/api/v1/marketplace/catalog/",
        get(|headers: HeaderMap| async move {
            if headers.contains_key("authorization")
                || headers.contains_key("x-hub-id")
                || headers.contains_key("x-hub-token")
            {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({ "error": "public catalog received credentials" })),
                );
            }
            if headers
                .get("accept-language")
                .and_then(|value| value.to_str().ok())
                != Some("es")
            {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({ "error": "public catalog did not receive the UI language" })),
                );
            }
            (
                StatusCode::OK,
                Json(json!({
                    "results": [{
                        "module_id": "inventory",
                        "name": "Inventory",
                        "module_type": "free",
                        "is_free": true
                    }]
                })),
            )
        }),
    );
    let cloud_task = tokio::spawn(async move {
        axum::serve(listener, mock_cloud).await.unwrap();
    });

    let db = fresh_db().await;
    let rt = Runtime::new(Box::new(db));
    let cfg = HubConfig {
        demo: false,
        hub_id: DEV_HUB_ID.into(),
        cloud_base_url: format!("http://{address}"),
        module_cache: std::env::temp_dir().join("erplora-demo-catalog-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: None,
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-demo-catalog-media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };

    let response = app(AppState::with_config(rt, cfg))
        .oneshot(
            Request::builder()
                .uri("/api/marketplace/catalog")
                .header("accept-language", "es")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        body_json(response).await["results"][0]["module_id"],
        "inventory"
    );
    cloud_task.abort();
}

#[tokio::test]
async fn real_catalog_uses_private_saas_endpoint_with_machine_credentials() {
    use axum::http::HeaderMap;
    use axum::routing::get;
    use axum::{Json, Router};
    use erplora_server::{AuthMode, HubConfig};

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let mock_cloud = Router::new().route(
        "/api/v1/marketplace/modules/",
        get(|headers: HeaderMap| async move {
            let valid_machine = headers
                .get("x-hub-id")
                .and_then(|value| value.to_str().ok())
                == Some("real-hub")
                && headers
                    .get("x-hub-token")
                    .and_then(|value| value.to_str().ok())
                    == Some("machine-secret")
                && !headers.contains_key("authorization");
            if !valid_machine {
                return (
                    StatusCode::UNAUTHORIZED,
                    Json(json!({ "error": "private catalog did not receive machine credentials" })),
                );
            }
            (
                StatusCode::OK,
                Json(json!({ "results": [{ "module_id": "inventory" }] })),
            )
        }),
    );
    let cloud_task = tokio::spawn(async move {
        axum::serve(listener, mock_cloud).await.unwrap();
    });

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "real-hub");
    let cfg = HubConfig {
        demo: false,
        hub_id: "real-hub".into(),
        cloud_base_url: format!("http://{address}"),
        module_cache: std::env::temp_dir().join("erplora-real-catalog-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-real-catalog-media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };

    let response = app(AppState::with_config(rt, cfg))
        .oneshot(
            Request::builder()
                .uri("/api/marketplace/catalog")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        body_json(response).await["results"][0]["module_id"],
        "inventory"
    );
    cloud_task.abort();
}

#[tokio::test]
async fn real_machine_cannot_use_business_api_before_registration() {
    use erplora_server::{AuthMode, HubConfig};

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "real-but-unregistered");
    rt.ensure_system_tables().await.unwrap();
    let cfg = HubConfig {
        demo: false,
        hub_id: "real-but-unregistered".into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache: std::env::temp_dir().join("erplora-unregistered-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: Some("public-key-loaded".into()),
        cloud_api_token: None,
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-unregistered-media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };

    let resp = app(AppState::with_config(rt, cfg))
        .oneshot(
            Request::builder()
                .uri("/api/navigation")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::PRECONDITION_REQUIRED);
    let body = body_json(resp).await;
    assert_eq!(
        body["error"]["code"],
        json!("machine_registration_required")
    );
}

#[tokio::test]
async fn request_install_without_bearer_is_401() {
    // Sin `Authorization: Bearer`, el flujo de instalación se rechaza antes de tocar el Cloud.
    let req = Request::builder()
        .method("POST")
        .uri("/api/modules/request-install")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .body(Body::from(
            json!({ "module_id": "inventory", "version": "1.0.0" }).to_string(),
        ))
        .unwrap();
    let resp = make_app().await.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(body_json(resp).await["ok"], json!(false));
}

#[tokio::test]
async fn assistant_stream_without_bearer_is_401() {
    let req = Request::builder()
        .method("POST")
        .uri("/api/assistant/chat/stream")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .body(Body::from(
            json!({ "messages": [{ "role": "user", "content": "hi" }] }).to_string(),
        ))
        .unwrap();
    let resp = make_app().await.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// App in `AuthMode::Session` (the production door) plus a signed-in employee's session token —
/// `AuthMode::Dev` trusts headers, so only this app can show the anonymous 401 (hub#946).
async fn make_session_app() -> (axum::Router, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-946");
    rt.ensure_system_tables().await.unwrap();
    let user_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    let session = rt.create_session(&user_id, 3600, None).await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-http-946-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-946".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    (app(AppState::with_config(rt, cfg)), session)
}

fn report_request(session: Option<&str>, body: Value) -> Request<Body> {
    let mut builder = Request::builder()
        .method("POST")
        .uri("/api/assistant/report")
        .header("content-type", "application/json");
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    builder.body(Body::from(body.to_string())).unwrap()
}

/// hub#946: reporting AI content requires a signed-in hub user — an anonymous request is refused
/// at the door.
#[tokio::test]
async fn assistant_report_without_session_is_401() {
    let (router, _session) = make_session_app().await;
    let resp = router
        .oneshot(report_request(
            None,
            json!({ "message_id": "m-1", "assistant_message": "bad answer" }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// hub#946: ANY signed-in hub user may report — no admin gate. The person offended by the content
/// is whoever is in front of the screen, so an employee's session opens the door.
#[tokio::test]
async fn assistant_report_any_signed_in_user_may_report() {
    let (router, session) = make_session_app().await;
    let resp = router
        .oneshot(report_request(
            Some(&session),
            json!({ "message_id": "m-946", "assistant_message": "an inappropriate answer" }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
}

/// hub#946: a signed-in user's report is accepted and acknowledged with `{ok: true}` (the event
/// itself travels through the global error registry, not through a table of its own — ADR-0052).
#[tokio::test]
async fn assistant_report_with_session_is_accepted() {
    let resp = make_app()
        .await
        .oneshot(post(
            "/api/assistant/report",
            json!({
                "message_id": "m-e2e-1",
                "assistant_message": "an inappropriate answer",
                "user_message": "what happened?",
                "comment": "this is offensive",
                "reason": "offensive"
            }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
}

/// hub#946: an empty `assistant_message` is a malformed report, never a silent 200.
#[tokio::test]
async fn assistant_report_empty_assistant_message_is_rejected() {
    let resp = make_app()
        .await
        .oneshot(post(
            "/api/assistant/report",
            json!({ "message_id": "m-1", "assistant_message": "" }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(false));
    assert_eq!(body["error"]["code"], "invalid_payload");
}
