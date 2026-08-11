//! Tests de integración de la capa SERVER del RESET del hub (ADR-0170 Fase 4).
//!
//! Superficie: `POST /api/hub/reset/plan` (dry-run) y `POST /api/hub/reset`.
//! Gate = **sesión admin (owner/admin)**, el MISMO que `PUT /api/settings`, el certificado y el
//! export — es la operación más destructiva del producto, no puede tener un gate más flojo.
//!
//! Patrón: router en memoria + `tower::ServiceExt::oneshot` (como `export_import_test.rs`).

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

fn test_config(auth_mode: AuthMode, tag: &str) -> HubConfig {
    let base = std::env::temp_dir().join(format!("erplora_reset_{}_{tag}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-test".into(),
        cloud_base_url: "http://127.0.0.1:1".into(),
        module_cache: base.join("module_cache"),
        auth_mode,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: base.join("media"),
        sector: None,
        // Confinamiento del install/import (endurecimiento de seguridad de `main`): el reset no
        // instala nada, pero `HubConfig` es exhaustivo y el test debe declarar el modo real de
        // producción — dev OFF.
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

async fn make_app(auth_mode: AuthMode, tag: &str) -> axum::Router {
    let db = fresh_db().await;
    // Las tablas de sistema (`hub_settings`, `hub_user`, …) las crea el server AL ARRANCAR; el
    // harness de test no pasa por ese boot, así que se aplican aquí. Sin esto el hub de test no
    // tiene ninguna tabla que resetear y los casos pasarían por vacío en vez de por correctos.
    erplora_runtime::identity::ensure_tables(&db).await.expect("tablas de identidad");
    // `hub_module` primero: las migraciones de sistema la migran, así que debe existir antes
    // (mismo orden que `installer::installed_status` en el arranque real).
    erplora_runtime::installer::ensure_hub_module_table(&db).await.expect("tabla hub_module");
    erplora_runtime::system_migrations::apply(&db, "hub-test").await.expect("migraciones de sistema");
    let rt = Runtime::with_hub_id(Box::new(db), "hub-test");
    app(AppState::with_config(rt, test_config(auth_mode, tag)))
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

fn post_json(uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .body(Body::from(body.to_string()))
        .unwrap()
}

// ── El gate: owner/admin, igual que settings ────────────────────────────────────────────

/// Sin sesión (modo Session, sin `X-Hub-Session`) → 401 **sin tocar la BD**. Un reset sin
/// autenticar sería el peor agujero posible del Hub.
#[tokio::test]
async fn reset_without_session_is_401() {
    let app = make_app(AuthMode::Session, "reset_401").await;
    let resp = app
        .oneshot(post_json("/api/hub/reset", json!({ "selection": {} })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(body_json(resp).await["ok"], json!(false));
}

/// El dry-run también va detrás del gate: enumera lo que hay en el hub (cuántos productos,
/// clientes…), así que es información del negocio.
#[tokio::test]
async fn plan_without_session_is_401() {
    let app = make_app(AuthMode::Session, "plan_401").await;
    let resp = app
        .oneshot(post_json("/api/hub/reset/plan", json!({})))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

// ── El dry-run ──────────────────────────────────────────────────────────────────────────

/// El plan devuelve las secciones con sus conteos: es lo que el panel pinta ANTES de que nadie
/// confirme, y de donde salen las cifras del alert.
#[tokio::test]
async fn plan_returns_sections_with_counts() {
    let app = make_app(AuthMode::Dev, "plan_ok").await;
    let resp = app.oneshot(post_json("/api/hub/reset/plan", json!({}))).await.unwrap();

    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
    let sections = body["plan"]["sections"].as_array().expect("plan.sections");
    // Un hub recién creado ya tiene las secciones a nivel hub, aunque estén a cero.
    let names: Vec<&str> = sections.iter().filter_map(|s| s["section"].as_str()).collect();
    assert!(names.contains(&"hub_settings"), "falta hub_settings en el plan: {names:?}");
    assert!(names.contains(&"hub_users"), "falta hub_users en el plan: {names:?}");
    // Cada sección trae su contador (la UI muestra cifras, no adjetivos).
    for s in sections {
        assert!(s["rows"].is_i64(), "sección sin contador de filas: {s}");
    }
}

// ── El reset ────────────────────────────────────────────────────────────────────────────

/// Body ausente → 422 (y no un 500): el reset nunca se ejecuta «por defecto».
#[tokio::test]
async fn reset_without_body_is_422() {
    let app = make_app(AuthMode::Dev, "reset_nobody").await;
    let resp = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/reset")
                .header("content-type", "application/json")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// Selección vacía → 200 con informe vacío: no se borra nada. El «reset» por accidente (body
/// `{}`) no puede vaciar el hub.
#[tokio::test]
async fn reset_with_empty_selection_deletes_nothing() {
    let app = make_app(AuthMode::Dev, "reset_empty").await;
    let resp = app
        .oneshot(post_json("/api/hub/reset", json!({ "selection": {} })))
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
    let sections = body["report"]["sections"].as_array().expect("report.sections");
    assert!(sections.is_empty(), "una selección vacía no puede borrar nada: {sections:?}");
}

/// El informe vuelve por sección con las filas borradas — contrato que la UI pinta tal cual.
#[tokio::test]
async fn reset_reports_deleted_rows_per_section() {
    let app = make_app(AuthMode::Dev, "reset_report").await;
    let resp = app
        .oneshot(post_json("/api/hub/reset", json!({ "selection": { "settings": true } })))
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    let sections = body["report"]["sections"].as_array().expect("report.sections");
    let s = sections
        .iter()
        .find(|s| s["section"] == json!("hub_settings"))
        .expect("la sección seleccionada debe aparecer en el informe");
    assert!(s["rows_deleted"].is_i64(), "el informe debe traer rows_deleted: {s}");
}

// ── El juego de roles del hub (hub#417) ─────────────────────────────────────────────────

/// El plan ofrece la sección `roles` — el espejo de lo que el export ya se lleva (ADR-0242): sin
/// ella el panel no puede pintarla y el dueño no tiene forma de RETIRAR un rol que encendió una
/// plantilla, salvo desinstalando el módulo que lo declara.
#[tokio::test]
async fn plan_offers_the_role_set_as_its_own_section() {
    let app = make_app(AuthMode::Dev, "plan_roles").await;
    let resp = app.oneshot(post_json("/api/hub/reset/plan", json!({}))).await.unwrap();

    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    let sections = body["plan"]["sections"].as_array().expect("plan.sections");
    let names: Vec<&str> = sections.iter().filter_map(|s| s["section"].as_str()).collect();
    assert!(names.contains(&"roles"), "falta `roles` en el plan: {names:?}");
}

/// El booleano cruza el CABLE. `ResetSelectionReq` es un espejo serde a mano de `ResetSelection`:
/// un campo que se añade al motor y se olvida aquí deja la sección muerta en silencio —el body
/// llega, el servidor lo ignora y responde `ok: true` sin haber apagado nada—. Se comprueba por
/// el efecto (la fila de la sección en el informe), no por el tipo.
#[tokio::test]
async fn the_role_set_can_be_reset_over_http() {
    let app = make_app(AuthMode::Dev, "reset_roles").await;
    let resp = app
        .oneshot(post_json("/api/hub/reset", json!({ "selection": { "roles": true } })))
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    let sections = body["report"]["sections"].as_array().expect("report.sections");
    assert!(
        sections.iter().any(|s| s["section"] == json!("roles")),
        "pedir `roles` tiene que llegar al motor: {sections:?}"
    );
}

/// Y no al revés: un body que NO nombra los roles no los apaga. `#[serde(default)]` en todo el
/// espejo existe para eso — un shell anterior al campo, o un cliente que manda medio body, nunca
/// puede AMPLIAR lo que se borra.
#[tokio::test]
async fn a_body_that_does_not_name_the_roles_leaves_them_alone() {
    let app = make_app(AuthMode::Dev, "reset_roles_off").await;
    let resp = app
        .oneshot(post_json("/api/hub/reset", json!({ "selection": { "settings": true } })))
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    let sections = body["report"]["sections"].as_array().expect("report.sections");
    assert!(
        !sections.iter().any(|s| s["section"] == json!("roles")),
        "nadie pidió los roles: no pueden aparecer en el informe: {sections:?}"
    );
}

// ── Lotes de importación: listar y deshacer (ADR-0170) ──────────────────────────────────

/// Listar las importaciones enseña qué trajo cada blueprint: es información del negocio y va
/// tras el mismo gate admin que el resto.
#[tokio::test]
async fn import_batches_without_session_is_401() {
    let app = make_app(AuthMode::Session, "batches_401").await;
    let resp = app
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/hub/import/batches")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// Deshacer una importación borra datos: nunca sin sesión admin.
#[tokio::test]
async fn undo_import_without_session_is_401() {
    let app = make_app(AuthMode::Session, "undo_401").await;
    let resp = app
        .oneshot(post_json("/api/hub/import/undo", json!({ "batch_id": "x" })))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// Sin importaciones, la lista es vacía (no un 404 ni un 500): el panel la pinta tal cual.
#[tokio::test]
async fn import_batches_lists_empty_on_a_fresh_hub() {
    let app = make_app(AuthMode::Dev, "batches_empty").await;
    let resp = app
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/hub/import/batches")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
    assert!(body["batches"].as_array().expect("batches").is_empty());
}

/// Deshacer un lote inexistente es un **no-op 200**, no un error: el usuario puede pulsar dos
/// veces o reintentar tras una red mala, y eso no puede parecer un fallo.
#[tokio::test]
async fn undo_import_of_unknown_batch_is_a_noop() {
    let app = make_app(AuthMode::Dev, "undo_noop").await;
    let resp = app
        .oneshot(post_json("/api/hub/import/undo", json!({ "batch_id": "no-existe" })))
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
    assert!(body["report"]["sections"].as_array().expect("sections").is_empty());
}

/// Sin `batch_id` → 422: deshacer nunca se dispara «por defecto».
#[tokio::test]
async fn undo_import_without_batch_id_is_422() {
    let app = make_app(AuthMode::Dev, "undo_nobatch").await;
    let resp = app.oneshot(post_json("/api/hub/import/undo", json!({}))).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}
